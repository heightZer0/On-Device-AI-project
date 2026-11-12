"""P3 테스트 (모델·오디오 장치 없이 동작). 프로젝트 루트에서: python -m pytest tests/voice_agent -q"""
import os
import threading
import time

import httpx
import numpy as np
import yaml
from fastapi.testclient import TestClient

from service.voice_agent.agent import VoiceAgent, preprocess
from service.voice_agent.speak_server import create_app
from service.voice_agent.tts import Speaker, split_text

CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "service", "voice_agent", "config.yaml")


def load_cfg():
    with open(CFG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["metrics"]["enabled"] = False
    return cfg


class FakeEngine:
    def __init__(self):
        self.calls = 0

    def synth(self, text, speed):
        self.calls += 1
        return np.full(1, float(ord(text[0])), dtype=np.float32), 16000


class GatePlayer:
    def __init__(self, open_=False):
        self.played, self.gate, self.started = [], threading.Event(), threading.Event()
        if open_:
            self.gate.set()

    def __call__(self, samples, sr, vol):
        self.started.set()
        self.gate.wait(2)
        self.played.append(chr(int(samples[0])))


def make_speaker(player, **kw):
    sp = Speaker(FakeEngine(), player, post_play_mute_ms=50, **kw)
    sp.start()
    return sp


# ---------------- T-P3-01 큐 ----------------
def test_reply_goes_before_waiting_alert():
    p = GatePlayer()
    sp = make_speaker(p)
    sp.enqueue("A", "alert")
    assert p.started.wait(1)           # A 는 이미 재생 중 -> 끊지 않음
    sp.enqueue("B", "alert")
    sp.enqueue("R", "reply")
    p.gate.set()
    assert sp.wait_idle()
    assert p.played == ["A", "R", "B"]


def test_queue_overflow_drops_oldest_alert():
    p = GatePlayer()
    sp = make_speaker(p, max_queue=2)
    sp.enqueue("X", "alert")
    assert p.started.wait(1)
    for t in ("a", "b", "c"):
        sp.enqueue(t, "alert")
    p.gate.set()
    assert sp.wait_idle()
    assert p.played == ["X", "b", "c"]


def test_split_text_keeps_words_and_limits_len():
    txt = "머리가 기준보다 앞쪽에 있는 상태가 이어지고 있어요. 턱을 살짝 당겨 볼까요?"
    chunks = split_text(txt, 40)
    assert all(len(c) <= 40 for c in chunks)
    assert "".join(chunks).replace(" ", "") == txt.replace(" ", "")


# ---------------- /speak 서버: 400, mic off 에서도 재생 (T-P3-01, 06) ----------------
class FakeAgent:
    def __init__(self):
        self.mic = "on"

    def mic_state(self):
        return self.mic

    def set_mic(self, e):
        self.mic = "on" if e else "off"
        return self.mic


def test_speak_api_empty_400_and_mic_off_still_speaks():
    p = GatePlayer(open_=True)
    sp = make_speaker(p)
    c = TestClient(create_app(sp, FakeAgent()))
    assert c.post("/speak", json={"text": "  ", "kind": "alert"}).status_code == 400
    assert c.post("/mic", json={"enabled": False}).json() == {"mic": "off"}
    r = c.post("/speak", json={"text": "Z", "kind": "alert"})
    assert r.status_code == 200 and r.json()["accepted"] is True
    assert sp.wait_idle() and p.played == ["Z"]
    st = c.get("/speak/state").json()
    assert st["mic"] == "off" and st["tts"] in ("ready", "busy")


# ---------------- T-P3-02 warmup 캐시 ----------------
def test_warmup_cache_hit_skips_synthesis():
    p = GatePlayer(open_=True)
    sp = make_speaker(p)
    assert sp.warmup(["Q"]) == 1
    calls = sp._engine.calls
    sp.enqueue("Q", "alert")
    assert sp.wait_idle()
    assert sp._engine.calls == calls and p.played == ["Q"]


# ---------------- T-P3-05 에코 가드 ----------------
def test_echo_guard_mutes_during_and_after_playback():
    p = GatePlayer()
    sp = make_speaker(p)
    sp.enqueue("E", "reply")
    assert p.started.wait(1) and sp.is_muted()
    p.gate.set()
    assert sp.wait_idle()
    assert sp.is_muted()               # 재생 직후 post_play_mute
    time.sleep(0.12)
    assert not sp.is_muted()


# ---------------- T-P3-04 전처리 ----------------
def test_preprocess_strips_trailing_punct_keeps_numbers():
    assert preprocess(" 15분 뒤에 쉬라고 알려줘. ") == "15분 뒤에 쉬라고 알려줘"
    assert preprocess("지금 내 자세 어때?") == "지금 내 자세 어때"
    assert preprocess("십오 분 뒤에 알려줘!?") == "십오 분 뒤에 알려줘"
    assert preprocess("") == ""


# ---------------- T-P3-03 / 09 P2 mock ----------------
class Resp:
    def __init__(self, code, data=None):
        self.status_code, self._d = code, data

    def json(self):
        if self._d is None:
            raise ValueError
        return self._d


class FakeHttp:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.posts = resp, exc, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append((url, json))
        if self.exc:
            raise self.exc
        return self.resp


def agent_with(http, **over):
    cfg = load_cfg()
    cfg.update(over)
    return VoiceAgent(cfg, None, None, None, None, http=http)


def test_p2_200_returns_tts_text_and_body_shape():
    http = FakeHttp(Resp(200, {"ok": False, "code": "PRECONDITION", "tts_text": "먼저 기준 자세를 설정해 주세요"}))
    out = agent_with(http)._call_p2("지금 내 자세 어때")
    assert out == "먼저 기준 자세를 설정해 주세요"
    url, body = http.posts[0]
    assert url.endswith(":8000/api/v1/command")
    assert body["source"] == "voice" and body["utterance"] == "지금 내 자세 어때"
    assert body["confidence"] is None and body["request_id"] and body["conversation_id"]


def test_p2_errors_read_error_message():
    for code, msg in ((422, "형식 오류"), (504, "응답 지연"), (503, "AI 서버 불가")):
        http = FakeHttp(Resp(code, {"error": {"code": "X", "message": msg}}))
        assert agent_with(http)._call_p2("가") == msg


def test_p2_connection_failure_uses_fallback():
    http = FakeHttp(exc=httpx.ConnectError("offline", request=httpx.Request("POST", "http://p2.test")))
    assert agent_with(http)._call_p2("가") == load_cfg()["fallback_phrases"]["p2_down"]


def test_default_mode_never_calls_llm_server():
    http = FakeHttp(Resp(200, {"tts_text": "ok"}))
    a = agent_with(http)
    spoken = []

    class Sp:
        def enqueue(self, t, k, **kw):
            spoken.append(t)

    a._speaker = Sp()
    a.process_text("자세 확인해줘", time.monotonic(), time.monotonic())
    assert spoken == ["ok"]
    assert all("8080" not in u for u, _ in http.posts)      # legacy_direct_mode=false


def test_empty_stt_ignored_by_default():
    a = agent_with(FakeHttp(Resp(200, {})))
    spoken = []

    class Sp:
        def enqueue(self, *a, **k):
            spoken.append(a)

    a._speaker = Sp()
    a.process_text("", 0, 0)
    assert spoken == []


# ---------------- T-P3-07 / 08 ----------------
def test_default_config_does_not_save_audio_or_log_text():
    cfg = load_cfg()
    assert "debug" not in cfg and "legacy_direct_mode" not in cfg
    a = VoiceAgent(cfg, None, None, None, None)
    assert a._debug_dir is None
