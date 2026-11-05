"""POST /command 처리 (v10.2 S4). 발화 원문·STT 텍스트는 로그에 남기지 않는다."""
import logging
import json
import os
import re
import threading
import time

from service.api_server.errors import ApiError
from service.hub.clients import LLMTimeout, LLMUnavailable

log = logging.getLogger("p2.command")
_YES = {"응", "네", "예", "맞아", "맞아요", "그래", "그래요", "웅"}
_NO = {"아니", "아냐", "아니야", "아니요", "싫어", "싫어요"}


def _norm(s):
    return re.sub(r"[\s\.\?\!,~]+", "", s or "")


def resolve_part(utterance, part_words):
    """후속 발화 → part 코드. 정확히 한 코드만 걸리면 성공, 0개·여러 개면 None(모호)."""
    u = _norm(utterance)
    hits = {code for code, words in part_words.items() if any(w in u for w in words)}
    return next(iter(hits)) if len(hits) == 1 else None


class CommandService:
    def __init__(self, hub, llm, processor, phrases, part_words, mono=time.monotonic):
        self.hub, self.llm, self.processor, self.phrases = hub, llm, processor, phrases
        self.part_words, self.mono = part_words, mono
        self.ttl = 30
        self.conv, self.lock = {}, threading.Lock()       # session_id -> ConversationState, memory only
        self._ai_log_lock = threading.Lock()

    def _ai_log(self, req, utterance, raw, output, started, error=None):
        if not self.hub.cfg.get("ai_log_enabled", False):
            return
        path = self.hub.cfg.get("ai_log_path", "data/ai_log.jsonl")
        row = {"request_id": req.request_id, "model_version": self.hub.cfg.get("llm_model"),
               "stt_text": utterance, "llm_output": raw, "validation": output,
               "latency_ms": round((time.monotonic() - started) * 1000), "error_code": error}
        with self._ai_log_lock:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _reply(self, ok, code, text, result=None):
        return {"success": ok, "ok": ok, "code": code, "tts_text": text, "result": result or {}}

    def _conversation(self, u, session_key):
        """Resolve one of the V6 clarification turns from session memory."""
        with self.lock:
            c = self.conv.get(session_key)
            if c and self.mono() - c["ts"] > self.ttl:
                self.conv.pop(session_key, None)
                return self._reply(False, "CLARIFICATION_TIMEOUT",
                                   self.phrases.get("errors", {}).get("CLARIFICATION_TIMEOUT", "재질문 시간이 지나 요청을 취소했어요."),
                                   {"reason": "timeout"})
            if not c:
                return None
            n = _norm(u)
            if c["pending"] == "body_part":
                code = resolve_part(u, self.part_words)
                if code is not None:
                    self.conv.pop(session_key, None)
                    return f'<stretch>(command="recommend", part="{code}")<suda_end>'
                if any(w in n for w in ("자세", "모니터링", "휴식알림", "착석시간", "공부시간")):
                    self.conv.pop(session_key, None)
                    return None
                return self._retry(c, "body_part", session_key)
            if c["pending"] == "intent":
                if any(w in n for w in ("자세", "머리", "거북목")):
                    self.conv.pop(session_key, None)
                    return '<posture>(command="check", type="1")<suda_end>'
                if any(w in n for w in ("스트레칭", "풀어", "펴")):
                    code = c.get("known_body_part")
                    if code is not None:
                        self.conv.pop(session_key, None)
                        return f'<stretch>(command="recommend", part="{code}")<suda_end>'
                    c["pending"] = "body_part"
                    c["retries"] = 0
                    c["ts"] = self.mono()
                    return self._reply(True, "OK", self.phrases.get("clarify", {}).get("body_part", "어느 부위인지 말씀해 주세요."), {"awaiting": "body_part"})
                return self._retry(c, "intent", session_key)
            if c["pending"] == "time":
                from command import parse_duration_minutes
                if parse_duration_minutes(u) is None:
                    if any(w in n for w in ("자세", "모니터링", "스트레칭", "착석시간")):
                        self.conv.pop(session_key, None)
                        return None
                    return self._retry(c, "time", session_key)
                self.conv.pop(session_key, None)
                return '<break>(command="set_alarm", minutes="N")<suda_end>'
            self.conv.pop(session_key, None)
            return None

    def _retry(self, c, kind, session_key):
        if c["retries"] < 1:
            c["retries"] += 1
            c["ts"] = self.mono()
            message = self.phrases.get("clarify", {}).get(kind, "다시 말씀해 주세요.")
            return self._reply(True, "OK", message, {"awaiting": kind})
        self.conv.pop(session_key, None)
        message = self.phrases.get("errors", {}).get("CLARIFICATION_TIMEOUT", "재질문 요청을 취소했어요. 다시 말씀해 주세요.")
        return self._reply(False, "CLARIFICATION_TIMEOUT", message, {"reason": "retry_exhausted"})

    def _from_llm(self, utterance):
        try:
            return self.llm.complete(utterance)
        except LLMTimeout:
            raise ApiError(504, "AI_INFERENCE_TIMEOUT", "음성 명령 처리가 지연되고 있어요.",
                           {"tts_text": self.phrases["errors"]["llm_timeout"]})
        except LLMUnavailable:
            raise ApiError(503, "AI_MODULE_UNAVAILABLE", "음성 명령 모듈을 사용할 수 없어요.",
                           {"tts_text": self.phrases["errors"]["llm_unavailable"]})

    def handle(self, req):
        if (req.utterance is not None) + (req.command is not None) != 1:
            raise ApiError(400, "INVALID_REQUEST", "utterance 또는 command 중 하나만 보내 주세요.")
        if not (req.utterance if req.utterance is not None else req.command).strip():
            raise ApiError(400, "INVALID_REQUEST", "내용이 비어 있어요.")
        t0, utterance, raw = time.monotonic(), None, req.command
        llm_output = None
        if raw is None:
            utterance = req.utterance
            active = getattr(self.hub, "session", None)
            session_key = req.session_id or (active.session_id if active else "device")
            step = self._conversation(utterance, session_key)
            if isinstance(step, dict):
                return step
            raw = step if isinstance(step, str) else self._from_llm(utterance)
            llm_output = raw if step is None else None
        try:
            # P4 exposes process(raw, services, *, utterance=...). Keep the old
            # protocol for the small fake processors used by P2 fixtures.
            if hasattr(self.processor, "process_p2"):
                out = self.processor.process_p2(raw, utterance, self.hub)
            else:
                out = self.processor.process(raw, utterance, self.hub)
        except Exception as e:
            log.warning("processor failed: %s", type(e).__name__)
            return self._reply(False, "ERROR", self.phrases["errors"]["command_failed"])
        code = out.get("code", "ERROR")
        self._ai_log(req, utterance, llm_output, {"code": code, "intent": out.get("intent"),
                                                  "validated_command": out.get("validated_command"),
                                                  "reason": (out.get("result") or {}).get("reason")}, t0,
                     code if code != "OK" else None)
        with self.lock:
            p = out.get("pending")
            if p is None and out.get("result", {}).get("awaiting"):
                p = {"type": out["result"]["awaiting"],
                     "minutes": out.get("result", {}).get("minutes")}
            known = resolve_part(utterance or "", self.part_words) if utterance else None
            session_key = req.session_id or (self.hub.session.session_id if getattr(self.hub, "session", None) else "device")
            if p and p.get("type") in ("body_part", "intent", "time"):
                self.conv[session_key] = {"pending": p["type"], "known_body_part": known, "retries": 0, "ts": self.mono()}
            else:
                self.conv.pop(session_key, None)
        log.info("command code=%s ms=%d", code, int((time.monotonic() - t0) * 1000))   # 코드·소요시간만
        reply = self._reply(code == "OK", code, out.get("tts_text", ""), out.get("result"))
        for field in ("intent", "validated_command", "precondition"):
            if out.get(field) is not None:
                reply[field] = out[field]
        return reply
