import random

import pytest
from tests.api.conftest import make

P = "/api/v1/"


def test_T04_start_requires_calibration(env_uncal):
    r = env_uncal.c.post(P + "monitoring/start")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CALIBRATION_REQUIRED"


def test_T04_full_state_table(env):
    c, hub = env.c, env.hub
    # IDLE: pause/stop 은 변경 없음(성공)
    assert c.post(P + "monitoring/pause").json()["system_state"] == "IDLE"
    assert c.post(P + "monitoring/stop").json()["system_state"] == "IDLE"
    # IDLE -> MONITORING (+새 세션)
    j = c.post(P + "monitoring/start").json()
    assert j["system_state"] == "MONITORING" and j["session_id"] and j["monitoring"] == "running"
    sid = j["session_id"]
    # MONITORING: start 멱등(같은 세션), calibration/start 409
    assert c.post(P + "monitoring/start").json()["session_id"] == sid
    assert c.post(P + "calibration/start").status_code == 409
    # pause -> PAUSED, pause 멱등, start -> 같은 세션 재개
    assert c.post(P + "monitoring/pause").json()["system_state"] == "PAUSED"
    assert c.post(P + "monitoring/pause").json()["system_state"] == "PAUSED"
    assert c.post(P + "monitoring/start").json()["session_id"] == sid
    # stop -> IDLE + 세션 요약, 두 번째 stop 도 성공
    j = c.post(P + "monitoring/stop").json()
    assert j["system_state"] == "IDLE" and j["session_summary"]["session_id"] == sid
    assert c.post(P + "monitoring/stop").json()["session_summary"]["session_id"] == sid
    assert env.eng.calls.count("start") == 1


def test_T04_calibrating_rules(env_uncal):
    c = env_uncal.c
    assert c.get(P + "calibration/preview").status_code == 409          # 시작 전 preview 거부
    r = c.post(P + "calibration/start").json()
    assert r["system_state"] == "CALIBRATING" and r["detection"]["ear_detected"]
    assert c.post(P + "calibration/start").status_code == 409
    assert c.post(P + "monitoring/start").status_code == 409            # CALIBRATING 중 start 거부
    assert c.post(P + "monitoring/pause").json()["system_state"] == "CALIBRATING"
    assert c.get(P + "calibration/preview").json()["preview"]["side"] == "left"
    j = c.post(P + "calibration/confirm").json()
    assert j["saved"] is True and j["system_state"] == "IDLE"
    assert c.get(P + "status").json()["calibrated"] is True
    assert c.post(P + "monitoring/start").status_code == 200
    # CALIBRATING 중 stop = 취소 후 IDLE
    env_uncal.hub.monitoring_stop()
    c.post(P + "calibration/start")
    assert c.post(P + "monitoring/stop").json()["system_state"] == "IDLE"
    assert "cancel_cal" in env_uncal.eng.calls


def test_recalibration_from_paused_keeps_session(env):
    c = env.c
    sid = c.post(P + "monitoring/start").json()["session_id"]
    c.post(P + "monitoring/pause")
    assert c.post(P + "calibration/start").json()["system_state"] == "CALIBRATING"
    j = c.post(P + "calibration/confirm").json()
    assert j["system_state"] == "PAUSED"
    assert c.get(P + "session/current").json()["session_id"] == sid


def test_confirm_not_saved_stays_calibrating(env):
    env.c.post(P + "calibration/start")
    env.eng.confirm_calibration = lambda: {"saved": False, "reason": "variance_high"}
    j = env.c.post(P + "calibration/confirm").json()
    assert j["saved"] is False and j["system_state"] == "CALIBRATING"


def test_T03_request_id_dedup(env):
    a = env.c.post(P + "monitoring/start", json={"request_id": "r1"}).json()
    env.c.post(P + "monitoring/stop")           # 상태를 바꾼 뒤 같은 request_id 재전송
    b = env.c.post(P + "monitoring/start", json={"request_id": "r1"}).json()
    assert a == b and env.hub.state == "IDLE"   # 재실행되지 않고 저장된 응답 반환
    assert env.eng.calls.count("start") == 1
    rows, total = env.store.list_sessions(10, 0)
    assert total == 1 and len(rows) == 1
    r = env.c.post(P + "monitoring/pause", json={"request_id": "r1"})   # 다른 엔드포인트에 같은 id
    assert r.status_code == 400 and r.json()["request_id"] == "r1"


def test_T10_invariant_random_10k_ticks(env):
    env.c.post(P + "monitoring/start")
    rnd = random.Random(7)
    for i in range(10000):
        env.eng.set_state(rnd.choice(["normal", "attention", "unavailable"]), None)
        if i % 997 == 0:
            env.hub.monitoring_pause() if env.hub.state == "MONITORING" else env.hub.monitoring_start()
        env.hub.tick(rnd.choice([250, 500, 1000, 333]))
        s = env.hub.get_session()
        d = s["state_durations"]
        assert s["monitoring_sec"] == d["normal_sec"] + d["attention_sec"] + d["unavailable_sec"]
        assert min(d.values()) >= 0 and s["sitting_sec"] >= s["monitoring_sec"]


def test_T10_unavailable_still_accumulates_time(env):
    env.c.post(P + "monitoring/start")
    env.eng.set_state("unavailable", "occluded")
    for _ in range(10):
        env.hub.tick(1000)
    s = env.hub.get_session()
    assert s["sitting_sec"] == 10 and s["monitoring_sec"] == 10
    assert s["state_durations"] == {"normal_sec": 0, "attention_sec": 0, "unavailable_sec": 10}


def test_pause_excluded_from_monitoring_but_in_sitting(env):
    env.c.post(P + "monitoring/start")
    env.hub.tick(5000)
    env.c.post(P + "monitoring/pause")
    env.hub.tick(3000)
    s = env.hub.get_session()
    assert s["sitting_sec"] == 8 and s["monitoring_sec"] == 5


def test_engine_failure_counts_as_unavailable(env):
    env.c.post(P + "monitoring/start")
    env.eng.get_state = lambda: (_ for _ in ()).throw(RuntimeError("cam"))
    env.hub.tick(2000)
    assert env.hub.get_session()["state_durations"]["unavailable_sec"] == 2


def test_history_newest_first(env):
    for _ in range(3):
        env.c.post(P + "monitoring/start")
        env.hub.tick(1000)
        env.c.post(P + "monitoring/stop")
    h = env.c.get(P + "session/history?limit=2").json()
    assert h["total"] == 3 and len(h["items"]) == 2
    assert h["items"][0]["started_at"] >= h["items"][1]["started_at"]
    assert {"session_id", "sitting_sec", "monitoring_sec", "normal_sec", "attention_sec", "unavailable_sec", "warning_count"} <= set(h["items"][0])
    assert env.c.get(P + "session/history?limit=0").status_code == 400


def test_T13_checkpoint_and_crash_recovery(tmp_path):
    store_dir = str(tmp_path / "store")
    a = make(calibrated=True, db=store_dir)
    a.c.post(P + "monitoring/start")
    for _ in range(31):
        a.hub.tick(1000)                    # 30초 체크포인트 경과
    sid = a.hub.session.session_id
    row = a.store.get_session(sid)
    assert row["monitoring_sec"] >= 30 and row["ended_at"] is None
    b = make(calibrated=True, db=store_dir)  # 비정상 종료 후 재부팅
    row = b.store.get_session(sid)
    assert row["ended_at"] is not None and row["monitoring_sec"] >= 30
    assert b.hub.last_session["session_id"] == sid and b.hub.get_session()["session_id"] is None
