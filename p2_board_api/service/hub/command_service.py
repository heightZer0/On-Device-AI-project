"""P2 command orchestration and short-lived per-conversation memory."""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone

from service.api_server.errors import ApiError
from service.hub.clients import LLMTimeout, LLMUnavailable

log = logging.getLogger("p2.command")
_CANCEL = {"취소", "취소할게", "됐어", "그만", "괜찮아"}
_PART_ALIASES = {
    "0": ("전체", "전신", "온몸"),
    "1": ("목", "거북목"),
    "2": ("어깨", "승모근"),
    "3": ("허리", "등"),
}
_PART_SUFFIX = re.compile(r"(?:이요|요|이에요|예요|입니다|이|은|는|을|를|으로|로)$")


def _norm(text):
    return re.sub(r"[\s\.,?!~。？！]+", "", text or "").lower()


def _short_part(text):
    """Only accept a concise part answer. In particular, 손목 must not match 목."""
    value = _norm(text)
    value = _PART_SUFFIX.sub("", value)
    for code, names in _PART_ALIASES.items():
        if value in names:
            return code
    return None


def _explicit_part(text):
    """Find an explicitly selected body part in a full request, respecting '말고'."""
    value = _norm(text)
    if "손목" in value:
        value = value.replace("손목", "")
    if "말고" in value:
        value = value.rsplit("말고", 1)[1]
    hits = {code for code, names in _PART_ALIASES.items() if any(name in value for name in names)}
    return next(iter(hits)) if len(hits) == 1 else None


def _is_cancel(text):
    return _norm(text) in _CANCEL


def _is_new_command(text, kind):
    value = _norm(text)
    if kind == "body_part" and _short_part(text) is not None:
        return False
    if kind == "body_part" and ("말고" in value or "이번" in value) and _explicit_part(text) is not None:
        return True
    if kind == "intent" and ("자세" in value or "위치확인" in value or "스트레칭" in value or "풀어" in value):
        return False
    if kind == "time" and (re.fullmatch(r"[0-9]+", value) or re.search(r"\d+분|[가-힣]+시간|[가-힣]+분", value)):
        return False
    # Complete requests should cancel an unrelated clarification and go through the LLM.
    return any(word in value for word in (
        "모니터링", "측정", "자세", "거북목", "스트레칭", "휴식알림", "착석시간", "앉은시간",
        "시작", "재개", "일시정지", "종료", "중지", "멈춰", "알림설정",
    ))


def _requested_stretch_action(text):
    value = _norm(text)
    if any(x in value for x in ("다시알려", "다시안내", "방금동작", "같은동작", "한번더")):
        return "repeat"
    if any(x in value for x in ("다른동작", "다른스트레칭", "또다른동작", "다른것도")):
        return "another"
    return None


class CommandService:
    def __init__(self, hub, llm, processor, phrases, part_words, mono=time.monotonic):
        self.hub, self.llm, self.processor, self.phrases = hub, llm, processor, phrases
        self.part_words, self.mono = part_words, mono
        self.pending_ttl_sec, self.stretch_ttl_sec = 30, 300
        self.conversations = {}  # conversation_id -> independent pending/last_stretch state
        self._guard = threading.Lock()
        self._conversation_locks = {}
        self._ai_log_lock = threading.Lock()

    def _lock_for(self, conversation_id):
        with self._guard:
            return self._conversation_locks.setdefault(conversation_id, threading.RLock())

    def _prune_expired_conversations(self, keep_id):
        now = self.mono()
        for cid in list(self.conversations):
            if cid == keep_id:
                continue
            lock = self._lock_for(cid)
            if not lock.acquire(blocking=False):
                continue
            try:
                state = self.conversations.get(cid)
                if not state:
                    continue
                pending = state.get("pending_clarification")
                stretch = state.get("last_stretch")
                if pending and now > pending["expires_at"]:
                    state["pending_clarification"] = None
                if stretch and now > stretch["expires_at"]:
                    state["last_stretch"] = None
                if not state.get("pending_clarification") and not state.get("last_stretch"):
                    self.conversations.pop(cid, None)
            finally:
                lock.release()

    def _ai_log(self, req, utterance, raw, output, started, error=None):
        if not self.hub.cfg.get("ai_log_enabled", False):
            return
        path = self.hub.cfg.get("ai_log_path", "data/ai_log.jsonl")
        row = {"request_id": req.request_id, "conversation_id": req.conversation_id,
               "model_version": self.hub.cfg.get("llm_model"),
               "stt_text": utterance, "llm_output": raw, "validation": output,
               "latency_ms": round((time.monotonic() - started) * 1000), "error_code": error}
        with self._ai_log_lock:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _reply(self, ok, code, text, result=None):
        return {"success": ok, "ok": ok, "code": code, "tts_text": text, "result": result or {}}

    def _prompt_body_part(self, pending_action, last_stretch=None):
        if pending_action == "stretch_alternative" and not last_stretch:
            return "어느 부위의 다른 스트레칭을 안내할까요? 목, 어깨, 허리 또는 전체 중 말씀해 주세요."
        return self.phrases.get("clarify", {}).get("body_part", "어느 부위 스트레칭을 알려 드릴까요?")

    def _set_pending(self, state, kind, original, action, slots=None, choices=None, retry=0):
        state["pending_clarification"] = {
            "kind": kind, "original_utterance": original, "pending_action": action,
            "slots": slots or {}, "allowed_choices": choices or [],
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "expires_at": self.mono() + self.pending_ttl_sec, "retry_count": retry,
        }

    def _clarify_reply(self, pending, message):
        return self._reply(True, "OK", message, {"awaiting": pending["kind"]})

    def _retry_pending(self, state, pending, message, *, range_error=False):
        if pending["retry_count"] < 1:
            pending["retry_count"] += 1
            pending["expires_at"] = self.mono() + self.pending_ttl_sec
            state["pending_clarification"] = pending
            code = "INVALID_TIME_RANGE" if range_error else "OK"
            return self._reply(not range_error, code, message, {"awaiting": pending["kind"]})
        state["pending_clarification"] = None
        return self._reply(False, "CLARIFICATION_TIMEOUT",
                           self.phrases.get("errors", {}).get("CLARIFICATION_TIMEOUT", "요청이 취소되었어요."),
                           {"reason": "retry_exhausted"})

    def _resolve_intent(self, text):
        value = _norm(text)
        posture = any(x in value for x in ("자세", "위치확인", "자세확인", "머리위치"))
        stretch = any(x in value for x in ("스트레칭", "풀어", "펴줘", "늘려"))
        if posture == stretch:
            return None
        return "posture" if posture else "stretch"

    def _resolve_pending(self, text, state):
        from command import parse_duration_minutes

        pending = state.get("pending_clarification")
        if not pending:
            return None
        now = self.mono()
        if now > pending["expires_at"]:
            state["pending_clarification"] = None
            compact = _norm(text)
            if _short_part(text) is not None or re.fullmatch(r"[0-9]+", compact):
                return self._reply(False, "CLARIFICATION_TIMEOUT",
                                   self.phrases.get("errors", {}).get("CLARIFICATION_TIMEOUT", "재질문 시간이 지나 요청을 취소했어요."),
                                   {"reason": "timeout"})
            pending = None
        if not pending:
            return None

        if _is_cancel(text):
            state["pending_clarification"] = None
            return self._reply(True, "OK", "재질문을 취소했어요.", {"cancelled": True})

        if pending["kind"] == "body_part" and _requested_stretch_action(text):
            state["pending_clarification"] = None
            return None

        if _is_new_command(text, pending["kind"]):
            state["pending_clarification"] = None
            return None

        kind = pending["kind"]
        if kind == "body_part":
            part = _short_part(text)
            if part is None:
                return self._retry_pending(state, pending, self._prompt_body_part(pending["pending_action"], state.get("last_stretch")))
            state["pending_clarification"] = None
            mode = "another" if pending["pending_action"] == "stretch_alternative" and state.get("last_stretch") else "first"
            return {"raw": f'<stretch>(command="recommend", part="{part}")<suda_end>',
                    "context": {"stretch_mode": mode, "last_stretch": state.get("last_stretch")}}

        if kind == "intent":
            choice = self._resolve_intent(text)
            if choice is None:
                return self._retry_pending(state, pending, self._intent_prompt(pending.get("slots", {}).get("body_part")))
            part = _explicit_part(text) or pending.get("slots", {}).get("body_part")
            state["pending_clarification"] = None
            if choice == "stretch":
                if part is None:
                    self._set_pending(state, "body_part", pending["original_utterance"], "stretch_recommend",
                                      choices=list(_PART_ALIASES))
                    new_pending = state["pending_clarification"]
                    return self._clarify_reply(new_pending, self._prompt_body_part("stretch_recommend"))
                return {"raw": f'<stretch>(command="recommend", part="{part}")<suda_end>',
                        "context": {"stretch_mode": "first", "last_stretch": state.get("last_stretch")}}
            posture_type = "0" if part == "0" else "1"
            note = None if part in (None, "0", "1") else f"현재는 머리 위치만 확인할 수 있습니다. {self._part_name(part)} 자세는 확인할 수 없어 머리 위치를 확인합니다."
            return {"raw": f'<posture>(command="check", type="{posture_type}")<suda_end>',
                    "context": {"prefix_notice": note}}

        if kind == "time":
            compact = _norm(text)
            duration = parse_duration_minutes(text)
            if duration is None and re.fullmatch(r"[0-9]+", compact):
                duration = int(compact)  # Unitless numbers mean minutes only in this pending state.
            if duration is None:
                return self._retry_pending(state, pending, self.phrases.get("clarify", {}).get("time", "몇 분 뒤로 설정할까요?"))
            if not 1 <= duration <= 180:
                return self._retry_pending(state, pending,
                    "휴식 알림은 1분부터 180분까지 설정할 수 있어요. 몇 분 뒤로 설정할까요?", range_error=True)
            state["pending_clarification"] = None
            return {"raw": '<break>(command="set_alarm", minutes="N")<suda_end>',
                    "context": {"duration_minutes": duration}}
        return None

    def _intent_prompt(self, part):
        name = self._part_name(part) if part is not None else None
        if name == "목":
            return "목 위치를 확인할까요, 목 스트레칭을 안내할까요?"
        if name in ("어깨", "허리"):
            return f"현재는 머리 위치만 확인할 수 있습니다. {name} 스트레칭을 안내할까요, 머리 위치를 확인할까요?"
        return self.phrases.get("clarify", {}).get("intent", "자세 확인과 스트레칭 중 무엇을 원하시나요?")

    @staticmethod
    def _part_name(part):
        return {"0": "전체", "1": "목", "2": "어깨", "3": "허리"}.get(str(part))

    def _resolve_last_stretch(self, text, state):
        action = _requested_stretch_action(text)
        last = state.get("last_stretch")
        if last and self.mono() > last["expires_at"]:
            state["last_stretch"] = last = None

        explicit = _explicit_part(text)
        value = _norm(text)
        if "다른부위" in value and explicit is None:
            self._set_pending(state, "body_part", text, "stretch_recommend", choices=list(_PART_ALIASES))
            pending = state["pending_clarification"]
            return self._clarify_reply(pending, self._prompt_body_part("stretch_recommend"))

        changes_part = explicit is not None and (
            any(x in value for x in ("이번", "말고", "부위")) or
            (action is not None and (last is None or str(explicit) != str(last.get("part"))))
        )
        if changes_part and not any(x in value for x in ("자세", "위치확인", "거북목")):
            action = action or "first"
        if not action:
            return None

        # An explicitly named new part takes precedence over a remembered part.
        if changes_part:
            return {"raw": f'<stretch>(command="recommend", part="{explicit}")<suda_end>',
                    "context": {"stretch_mode": "first", "last_stretch": last}}
        if not last:
            self._set_pending(state, "body_part", text, "stretch_alternative", choices=list(_PART_ALIASES))
            pending = state["pending_clarification"]
            return self._clarify_reply(pending, self._prompt_body_part("stretch_alternative", None))
        return {"raw": f'<stretch>(command="recommend", part="{last["part"]}")<suda_end>',
                "context": {"stretch_mode": action, "last_stretch": last}}

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
        # One configured bearer token identifies this P2 device; clients may supply
        # a separate conversation_id. Measurement session_id is deliberately not used.
        conversation_id = req.conversation_id or "default"
        self._prune_expired_conversations(conversation_id)
        with self._lock_for(conversation_id):
            return self._handle_locked(req, conversation_id)

    def _handle_locked(self, req, conversation_id):
        t0, utterance, raw = time.monotonic(), req.utterance, req.command
        llm_output, execution_context = None, {}
        state = self.conversations.setdefault(conversation_id, {"pending_clarification": None, "last_stretch": None})

        if utterance is not None:
            step = self._resolve_pending(utterance, state)
            if isinstance(step, dict) and "raw" not in step:
                return step
            if step is None:
                step = self._resolve_last_stretch(utterance, state)
                if isinstance(step, dict) and "raw" not in step:
                    return step
            if step is not None:
                raw, execution_context = step["raw"], step.get("context", {})
            else:
                raw = self._from_llm(utterance)
                llm_output = raw

        try:
            if hasattr(self.processor, "process_p2"):
                out = self.processor.process_p2(raw, utterance, self.hub, conversation=execution_context)
            else:
                out = self.processor.process(raw, utterance, self.hub)
        except Exception as e:
            log.warning("processor failed: %s", type(e).__name__)
            return self._reply(False, "ERROR", self.phrases["errors"]["command_failed"])

        code = out.get("code", "ERROR")
        result = out.get("result") or {}
        if execution_context.get("prefix_notice") and out.get("success", out.get("ok", False)):
            out["tts_text"] = execution_context["prefix_notice"] + " " + out.get("tts_text", "")
            result["message"] = out["tts_text"]

        if code == "INVALID_TIME_RANGE" and utterance is not None and "쉬" in utterance:
            pending = {"kind": "time", "original_utterance": utterance, "pending_action": "break_alarm",
                       "slots": {}, "allowed_choices": [], "expires_at": self.mono() + self.pending_ttl_sec,
                       "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                       "retry_count": 0}
            state["pending_clarification"] = pending
            out.setdefault("result", {})["awaiting"] = "time"
            out["tts_text"] += " 몇 분 뒤로 설정할까요?"

        if out.get("success", out.get("ok", False)):
            if out.get("intent") == "clarify_body_part":
                self._set_pending(state, "body_part", utterance or "", "stretch_recommend", choices=list(_PART_ALIASES))
            elif out.get("intent") == "clarify_intent":
                part = _explicit_part(utterance or "")
                slots = {"body_part": part} if part is not None else {}
                self._set_pending(state, "intent", utterance or "", "posture_or_stretch", slots,
                                  choices=["posture_check", "stretch_recommend"])
                out["tts_text"] = self._intent_prompt(part)
            elif out.get("intent") == "clarify_time" or result.get("awaiting") == "time":
                self._set_pending(state, "time", utterance or "", "break_alarm", choices=["duration_minutes"])
            else:
                state["pending_clarification"] = None

        exercise_id = result.get("exercise_id")
        part = result.get("part")
        if out.get("success", out.get("ok", False)) and exercise_id and part is not None:
            prior = execution_context.get("last_stretch") or state.get("last_stretch")
            if prior and str(prior.get("part")) == str(part):
                shown = list(prior.get("shown_exercise_ids", []))
            else:
                shown = []
            if exercise_id not in shown:
                shown.append(exercise_id)
            state["last_stretch"] = {
                "part": str(part), "last_exercise_id": exercise_id,
                "shown_exercise_ids": shown,
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "expires_at": self.mono() + self.stretch_ttl_sec,
            }

        self._ai_log(req, utterance, llm_output,
                     {"code": code, "intent": out.get("intent"),
                      "validated_command": out.get("validated_command"),
                      "reason": result.get("reason")}, t0, code if code != "OK" else None)
        log.info("command code=%s ms=%d", code, int((time.monotonic() - t0) * 1000))
        reply = self._reply(bool(out.get("success", out.get("ok", False))), code,
                            out.get("tts_text", ""), result)
        for field in ("intent", "validated_command", "precondition"):
            if out.get(field) is not None:
                reply[field] = out[field]
        return reply
