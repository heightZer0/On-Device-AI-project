from tests.api.conftest import make

GET_PATHS = ["/api/v1/status", "/api/v1/posture/current", "/api/v1/session/current",
             "/api/v1/session/history", "/api/v1/settings", "/api/v1/health"]


def test_T01_status_schema(env):
    j = env.c.get("/api/v1/status").json()
    assert set(j) >= {"system_state", "monitoring", "camera", "calibrated", "posture", "session", "notices", "updated_at"}
    assert j["system_state"] == "IDLE" and j["monitoring"] == "stopped" and j["calibrated"] is True
    assert j["camera"] == "ready"


def test_T01_posture_has_no_wrapper(env):
    j = env.c.get("/api/v1/posture/current").json()
    assert "posture" not in j and j["state"] == "normal"
    assert set(j) >= {"state", "reason", "indicators", "landmarks_ok", "confidence", "duration_sec", "updated_at"}


def test_unavailable_clears_indicators(env):
    env.eng.set_state("unavailable", "occluded")
    j = env.c.get("/api/v1/posture/current").json()
    assert j["indicators"] == {} and j["reason"] == "occluded"


def test_session_current_null_and_history_empty(env):
    current = env.c.get("/api/v1/session/current").json()
    assert current["session_id"] is None and current["sitting_sec"] == 0
    h = env.c.get("/api/v1/session/history").json()
    assert h["items"] == [] and h["total"] == 0


def test_T02_error_format_and_mapping(env):
    r = env.c.get("/api/v1/nope")
    j = r.json()
    assert r.status_code == 404 and j["success"] is False
    assert set(j["error"]) == {"code", "message", "details"} and "request_id" in j and "timestamp" in j
    r = env.c.post("/api/v1/command", json={"source": "voice"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"
    r = env.c.post("/api/v1/command", json={"source": "x", "utterance": "a"})
    assert r.status_code == 400


def test_T12_auth(env):
    import httpx
    from fastapi.testclient import TestClient
    bare = TestClient(env.app)
    assert bare.get("/api/v1/health").status_code == 200
    assert bare.get("/api/v1/status").status_code == 401
    assert bare.get("/api/v1/status", headers={"Authorization": "Bearer wrong"}).status_code == 403
    assert bare.post("/api/v1/monitoring/start").status_code == 401


def test_auth_fail_closed_without_token():
    import pytest
    from service.api_server.app import create_app
    e = make()
    cfg = dict(e.cfg, auth={"enabled": True, "token_env": "NOT_SET_ENV_XYZ"})
    with pytest.raises(RuntimeError):
        create_app(e.hub, e.cmd, cfg)


def test_T09_no_S_in_normal_mode_all_endpoints(env):
    env.eng.leak_debug = True
    env.c.post("/api/v1/monitoring/start")
    for p in GET_PATHS:
        assert "shoulder_screen_shift" not in env.c.get(p).text, p
    assert "debug" not in env.c.get("/api/v1/posture/current").json()
    assert env.c.post("/api/v1/debug/label", json={"label": "x"}).status_code == 404


def test_T09_debug_mode_exposes_S(env):
    assert env.c.put("/api/v1/settings", json={"debug_mode": True}).status_code == 200
    assert env.eng.debug is True
    assert env.c.get("/api/v1/posture/current").json()["debug"]["shoulder_screen_shift"] == 0.05
    assert "shoulder_screen_shift" in env.c.get("/api/v1/status").text
    assert env.c.post("/api/v1/debug/label", json={"label": "x"}).status_code == 501   # FakeEngine 에 라벨 기능 없음


def test_T14_settings_validation_and_propagation(env):
    r = env.c.put("/api/v1/settings", json={"tts_volume": 0.3, "alert_interval_sec": 60,
                                            "posture_sensitivity": "high", "microphone_enabled": False})
    assert r.status_code == 200
    assert env.eng.runtime["alert_interval_sec"] == 60 and env.eng.runtime["posture_sensitivity"] == "high"
    assert env.spk.mic is False
    for bad in ({"unknown": 1}, {"tts_volume": 999}, {"tts_volume": True}, {"debug_mode": "yes"},
                {"preview_stream_enabled": True}):
        r = env.c.put("/api/v1/settings", json=bad)
        assert r.status_code == 400, bad
    assert env.c.get("/api/v1/settings").json()["settings"]["tts_volume"] == 0.3  # 거부된 요청은 반영 안 됨


def test_settings_persist_across_restart(tmp_path):
    store_dir = str(tmp_path / "store")
    a = make(db=store_dir)
    a.c.put("/api/v1/settings", json={"tts_volume": 0.12})
    b = make(db=store_dir)
    assert b.c.get("/api/v1/settings").json()["settings"]["tts_volume"] == 0.12


def test_health_degraded(env):
    assert env.c.get("/api/v1/health").json()["status"] == "ok"
    env.llm.h = "error"
    j = env.c.get("/api/v1/health").json()
    assert j["status"] == "degraded" and j["ai_modules"]["llm"] == "error"
