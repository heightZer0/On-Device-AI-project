from tests.api.conftest import make

C = "/api/v1/command"
POSTURE = '<posture>(command="check", type="0")<suda_end>'


def test_T05_exactly_one_of_utterance_command(env):
    assert env.c.post(C, json={"source": "voice", "utterance": "a", "command": POSTURE}).status_code == 400
    assert env.c.post(C, json={"source": "voice"}).status_code == 400
    assert env.c.post(C, json={"source": "voice", "utterance": "  "}).status_code == 400


def test_command_mode_skips_llm(env):
    j = env.c.post(C, json={"source": "app", "command": POSTURE}).json()
    assert j["ok"] is True and j["code"] == "OK" and "머리 상대 위치" in j["tts_text"]
    assert env.llm.calls == 0


def test_utterance_goes_through_llm_and_processor(env):
    j = env.c.post(C, json={"source": "voice", "utterance": "지금 내 자세 어때"}).json()
    assert env.llm.calls == 1 and env.proc.calls == [env.llm.out] and j["ok"]


def test_invalid_llm_output_not_ok_but_200(env):
    env.llm.out = "자세가 좋아 보여요"
    r = env.c.post(C, json={"source": "voice", "utterance": "x"})
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["code"] == "INVALID_FORMAT"


def test_T06_llm_timeout_and_down(env):
    env.llm.err = "timeout"
    r = env.c.post(C, json={"source": "voice", "utterance": "x"})
    assert r.status_code == 504 and r.json()["error"]["code"] == "AI_INFERENCE_TIMEOUT"
    assert "다시 말씀" in r.json()["error"]["details"]["tts_text"]
    env.llm.err = "down"
    r = env.c.post(C, json={"source": "voice", "utterance": "x"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "AI_MODULE_UNAVAILABLE"
    assert env.c.post("/api/v1/monitoring/start").status_code == 200      # LLM 장애와 무관하게 앱 버튼 경로 동작


def test_processor_exception_returns_error_code(env):
    env.proc.process = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    j = env.c.post(C, json={"source": "app", "command": POSTURE}).json()
    assert j["code"] == "ERROR" and j["ok"] is False and j["tts_text"]


def test_T07_clarify_then_part(env):
    env.llm.out = '<clarify>(command="body_part")<suda_end>'
    j = env.c.post(C, json={"source": "voice", "utterance": "스트레칭 알려줘"}).json()
    assert j["result"] == {} and "어느 부위" in j["tts_text"]
    env.llm.calls = 0
    env.c.post(C, json={"source": "voice", "utterance": "목이요"})
    assert env.proc.calls[-1] == '<stretch>(command="recommend", part="1")<suda_end>'
    assert env.llm.calls == 0                                          # 후속 발화는 LLM 을 거치지 않음
    assert env.cmd.conv is None


def test_T07_clarify_ttl_expiry(env):
    env.llm.out = '<clarify>(command="body_part")<suda_end>'
    env.c.post(C, json={"source": "voice", "utterance": "스트레칭"})
    env.clock.t = 11                                                    # TTL(10초) 경과
    env.llm.out = POSTURE
    env.c.post(C, json={"source": "voice", "utterance": "목"})
    assert env.llm.calls == 2 and not env.proc.calls[-1].startswith("<stretch>")   # 일반 흐름으로 처리


def test_T07_unrelated_reask_once_then_release(env):
    env.llm.out = '<clarify>(command="body_part")<suda_end>'
    env.c.post(C, json={"source": "voice", "utterance": "스트레칭"})
    env.llm.out = POSTURE
    j = env.c.post(C, json={"source": "voice", "utterance": "응?"}).json()
    assert j["code"] == "BAD_PARAM" and "어느 부위" in j["tts_text"]
    assert env.llm.calls == 1                                           # 재질문은 LLM 호출 없음
    env.c.post(C, json={"source": "voice", "utterance": "응?"})         # 두 번째 무관 발화 → 해제 후 LLM
    assert env.llm.calls == 2 and env.cmd.conv is None


def test_part_ambiguous_asks_again(env):
    env.llm.out = '<clarify>(command="body_part")<suda_end>'
    env.c.post(C, json={"source": "voice", "utterance": "스트레칭"})
    j = env.c.post(C, json={"source": "voice", "utterance": "목이랑 어깨"}).json()
    assert j["code"] == "BAD_PARAM"


def test_confirm_minutes_yes_and_no(env):
    env.llm.out = '<break>(command="ask")<suda_end>'
    env.c.post(C, json={"source": "voice", "utterance": "쉬라고 알려줘"})
    j = env.c.post(C, json={"source": "voice", "utterance": "응"}).json()
    assert env.proc.calls[-1] == '<break>(command="set_alarm", minutes="30")<suda_end>' and j["ok"]
    assert env.hub.get_break_status()["set"] is True
    env.hub._break_timer.cancel()
    env.c.post(C, json={"source": "voice", "utterance": "쉬라고 알려줘"})
    j = env.c.post(C, json={"source": "voice", "utterance": "아니"}).json()
    assert j["ok"] and j["result"] == {"cancelled": True}


def test_command_request_id_dedup(env):
    body = {"source": "voice", "utterance": "x", "request_id": "q1"}
    env.c.post(C, json=body)
    env.c.post(C, json=body)
    assert env.llm.calls == 1


def test_monitor_command_idempotent_via_services(env):
    s = '<monitor>(command="start")<suda_end>'
    assert env.c.post(C, json={"source": "app", "command": s}).json()["ok"]
    assert env.c.post(C, json={"source": "app", "command": s}).json()["ok"]
    assert env.hub.state == "MONITORING" and env.eng.calls.count("start") == 1


def test_no_utterance_in_logs(env, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    env.c.post(C, json={"source": "voice", "utterance": "비밀발화문장"})
    assert "비밀발화문장" not in caplog.text and "test-token" not in caplog.text


# ---------- 이벤트 → 음성 (T-P2-11) ----------
def test_T11_attention_speaks_only_when_monitoring_and_enabled(env):
    env.eng.emit("attention_started")                                   # IDLE: 호출 안 함
    assert env.spk.spoken == []
    env.c.post("/api/v1/monitoring/start")
    env.eng.emit("attention_started")
    assert len(env.spk.spoken) == 1 and env.spk.spoken[0][1] == "alert" and env.spk.spoken[0][2] == 70
    assert "턱을 살짝" in env.spk.spoken[0][0]
    env.c.put("/api/v1/settings", json={"voice_feedback_enabled": False})
    env.eng.emit("attention_started")
    assert len(env.spk.spoken) == 1                                     # 음성 꺼짐
    assert env.hub.get_session()["warning_count"] == 2                  # 경고 횟수는 음성 설정과 무관(D-16)
    env.c.put("/api/v1/settings", json={"voice_feedback_enabled": True})
    env.c.post("/api/v1/monitoring/pause")
    env.eng.emit("recovered")
    assert len(env.spk.spoken) == 1                                     # paused


def test_T11_null_phrase_no_speak_but_notice(env):
    env.c.post("/api/v1/monitoring/start")
    env.eng.emit("recalibration_suggested")
    assert env.spk.spoken == []
    assert env.c.get("/api/v1/status").json()["notices"] == ["recalibration_suggested"]
    env.c.post("/api/v1/monitoring/pause")
    env.c.post("/api/v1/calibration/start")
    env.c.post("/api/v1/calibration/confirm")
    assert env.c.get("/api/v1/status").json()["notices"] == []          # 재캘리브레이션 확정 시 해제(자동 갱신은 하지 않음)


def test_T11_speak_failure_does_not_break_loop(env):
    env.spk.fail = True
    env.c.post("/api/v1/monitoring/start")
    env.eng.emit("attention_started")                                   # 예외 전파 없음
    env.hub.tick(1000)
    assert env.hub.get_session()["monitoring_sec"] == 1


def test_break_alarm_replace_policy_and_expiry(env):
    a = env.hub.set_break_alarm(30)
    b = env.hub.set_break_alarm(10)
    assert a["set"] and b["replaced"] and env.hub.get_break_status()["minutes"] == 10
    env.hub._on_break_alarm()
    assert "쉬어 갈 시간" in env.spk.spoken[-1][0] and env.hub.get_break_status() == {"set": False}
    e2 = make(break_alarm_replace=False)
    e2.hub.set_break_alarm(30)
    assert e2.hub.set_break_alarm(5)["set"] is False
    e2.hub._break_timer.cancel()


def test_event_log_flag_default_off(env):
    env.eng.emit("attention_started")
    assert env.store._q("SELECT COUNT(*) n FROM events")[0]["n"] == 0
    env.c.put("/api/v1/settings", json={"event_log_enabled": True})
    env.eng.emit("attention_started")
    assert env.store._q("SELECT COUNT(*) n FROM events")[0]["n"] == 1


def test_rate_limit_429_when_configured():
    e = make(rate_limit={"per_client_per_sec": 2})
    codes = [e.c.get("/api/v1/status").status_code for _ in range(4)]
    assert 429 in codes and codes[:2] == [200, 200]
