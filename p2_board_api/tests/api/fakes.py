"""P1/P3/P4 mock. 보드·모델 없이 P2 단독 테스트용."""
import re
from datetime import datetime, timezone

from service.hub.clients import LLMTimeout, LLMUnavailable


class FakeEngine:
    def __init__(self, calibrated=False):
        self.calibration = {"H_base": 0.1} if calibrated else None
        self.state = "normal"
        self.reason = None
        self.leak_debug = True          # 일부러 S를 흘려서 P2 필터가 막는지 검증
        self.calls, self.cb, self.runtime, self.debug = [], None, {}, None
        self.health = {"camera": "ready", "pose": "ready"}

    def set_state(self, s, reason=None):
        self.state, self.reason = s, reason

    def start(self): self.calls.append("start")
    def pause(self): self.calls.append("pause")
    def resume(self): self.calls.append("resume")
    def stop(self): self.calls.append("stop")
    def cancel_calibration(self): self.calls.append("cancel_cal")

    def get_state(self):
        s = {"state": self.state, "reason": self.reason,
             "indicators": {} if self.state == "unavailable" else {"head_relative_position": {"delta": 0.12, "status": self.state}},
             "landmarks_ok": {"ear": True, "shoulder": True, "side": "left"}, "confidence": 0.9,
             "duration_sec": 3, "updated_at": datetime.now(timezone.utc).isoformat()}
        if self.leak_debug:
            s["debug"] = {"shoulder_screen_shift": 0.05, "validated": False}
        return s

    def begin_calibration(self, duration_sec=None): self.calls.append("begin_cal"); return {"ear_detected": True, "shoulder_detected": True}
    def preview_calibration(self): return {"H_base": 0.1, "L_ref_fixed": 80.0, "side": "left", "d": 1}
    def confirm_calibration(self): self.calibration = {"H_base": 0.1}; return {"H_base": 0.1, "side": "left", "d": 1}
    def get_calibration(self): return self.calibration
    def on_event(self, cb): self.cb = cb
    def emit(self, t, delta=0.1): self.cb({"type": t, "ts": "2026-01-01T00:00:00Z", "delta": delta})
    def set_debug(self, e): self.debug = e
    def update_runtime_settings(self, **kw): self.runtime.update(kw)
    def get_health(self): return self.health


class FakeSpeak:
    def __init__(self):
        self.spoken, self.fail, self.mic, self.st, self.settings = [], False, None, {"stt": "ready", "tts": "ready"}, {}

    def speak(self, text, kind, volume):
        if self.fail:
            raise RuntimeError("down")
        self.spoken.append((text, kind, volume))

    def warmup(self, texts): self.warm = texts
    def set_mic(self, e): self.mic = e
    def set_settings(self, settings): self.settings = dict(settings)
    def state(self): return self.st


class FakeLLM:
    def __init__(self, out='<posture>(command="check", type="0")<suda_end>'):
        self.out, self.calls, self.err, self.h = out, 0, None, "ready"

    def complete(self, utterance):
        self.calls += 1
        if self.err == "timeout": raise LLMTimeout()
        if self.err == "down": raise LLMUnavailable()
        return self.out

    def health(self): return self.h


_FMT = re.compile(r'^<(\w+)>\((.*)\)<suda_end>$')


class FakeProcessor:
    """P4 검증기·실행기 대역. 형식이 맞으면 OK, 아니면 INVALID_FORMAT. clarify/알림은 pending 으로 응답."""
    def __init__(self): self.calls = []

    def process(self, raw, utterance, services):
        self.calls.append(raw)
        m = _FMT.match(raw.strip())
        if not m:
            return {"success": False, "code": "INVALID_FORMAT", "result": {}, "tts_text": "다시 말씀해 주세요."}
        fn, args = m.groups()
        if fn == "clarify":
            kind = "time" if '"time"' in args else "intent" if '"intent"' in args else "body_part"
            text = {"time": "몇 분 뒤로 설정할까요?", "intent": "자세를 확인할까요, 스트레칭을 안내할까요?",
                    "body_part": "어느 부위 스트레칭을 알려 드릴까요?"}[kind]
            return {"success": True, "code": "OK", "result": {"awaiting": kind},
                    "intent": f"clarify_{kind}", "tts_text": text}
        if fn == "monitor":
            r = services.monitoring_start() if 'start' in args else services.monitoring_stop()
            return {"success": True, "code": "OK", "result": r, "tts_text": "알겠어요."}
        if fn == "break" and "set_alarm" in args:
            from command import parse_duration_minutes
            mm = parse_duration_minutes(utterance or "")
            if mm is None:
                return {"success": False, "code": "INVALID_FORMAT", "result": {}, "tts_text": "시간을 확인해 주세요."}
            return {"success": True, "code": "OK", "result": services.set_break_alarm(mm), "tts_text": f"{mm}분 뒤에 알려 드릴게요."}
        return {"success": True, "code": "OK", "result": {"args": args}, "tts_text": "현재는 머리 상대 위치 기준으로 확인한 결과예요."}
