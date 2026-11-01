"""POST /command 처리 (v10.2 S4). 발화 원문·STT 텍스트는 로그에 남기지 않는다."""
import logging
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
        self.ttl = hub.cfg["conversation_ttl_sec"]
        self.conv, self.lock = None, threading.Lock()     # ConversationState: 메모리 전용, 영속 저장 안 함

    def _reply(self, ok, code, text, result=None):
        return {"success": ok, "ok": ok, "code": code, "tts_text": text, "result": result or {}}

    def _conversation(self, u):
        """대기 중인 재질문(part / 분 확인)이 있으면 처리. dict=최종 응답, str=raw 명령, None=일반 흐름."""
        with self.lock:
            c = self.conv
            if c and self.mono() - c["ts"] > self.ttl:
                self.conv = c = None
            if not c:
                return None
            n = _norm(u)
            if c["pending"] == "part":
                code = resolve_part(u, self.part_words)
                if code is not None:
                    self.conv = None
                    return f'<stretch>(command="recommend", part="{code}")<suda_end>'
                if c["retries"] < 1:
                    c["retries"] += 1
                    c["ts"] = self.mono()
                    return self._reply(False, "BAD_PARAM", self.phrases["prompts"]["ask_part"], {"pending": "part"})
                self.conv = None                          # 재질문 1회 후 해제 → 일반 흐름(가정)
                return None
            self.conv = None                              # confirm_minutes
            if n in _YES:
                return f'<break>(command="set_alarm", minutes="{c["minutes"]}")<suda_end>'
            if n in _NO:
                return self._reply(True, "OK", self.phrases["prompts"]["break_cancelled"], {"cancelled": True})
            return None

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
        if raw is None:
            utterance = req.utterance
            step = self._conversation(utterance)
            if isinstance(step, dict):
                return step
            raw = step if isinstance(step, str) else self._from_llm(utterance)
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
        with self.lock:
            p = out.get("pending")
            if p is None and out.get("result", {}).get("awaiting"):
                p = {"type": out["result"]["awaiting"],
                     "minutes": out.get("result", {}).get("minutes")}
            self.conv = ({"pending": p["type"], "minutes": p.get("minutes"), "retries": 0, "ts": self.mono()}
                         if p and p.get("type") in ("part", "confirm_minutes") else None)
        log.info("command code=%s ms=%d", code, int((time.monotonic() - t0) * 1000))   # 코드·소요시간만
        reply = self._reply(code == "OK", code, out.get("tts_text", ""), out.get("result"))
        for field in ("intent", "validated_command", "precondition"):
            if out.get(field) is not None:
                reply[field] = out[field]
        return reply
