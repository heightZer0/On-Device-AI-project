"""P4 command parser, validator and safe executor.

The inference runtime is deliberately outside this package. Any OpenAI-compatible
model server can be swapped through P2's llm_url/llm_model configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"


@dataclass(frozen=True)
class Options:
    require_suda_end: bool = True


@dataclass(frozen=True)
class ParsedCommand:
    function: str
    command: str | None
    params: dict[str, str]
    duplicate_params: frozenset[str] = frozenset()


_TOKEN = object()


@dataclass(frozen=True, init=False)
class ValidatedCommand:
    """Command value that can only be constructed by this module's validator."""
    function: str
    command: str
    params: dict[str, str]
    intent: str
    raw: str
    _token: object

    def __init__(self, function, command, params, intent, raw, token=None):
        if token is not _TOKEN:
            raise TypeError("ValidatedCommand instances are created by the validator")
        object.__setattr__(self, "function", function)
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "params", dict(params))
        object.__setattr__(self, "intent", intent)
        object.__setattr__(self, "raw", raw)
        object.__setattr__(self, "_token", token)


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _schema() -> dict:
    return _load_yaml(SCHEMA_DIR / "commands.yaml")


def _phrases() -> dict:
    return _load_yaml(ROOT / "config" / "phrases_command.yaml")


def _parse(raw: str, require_suda_end: bool) -> ParsedCommand:
    source = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)
    source = re.sub(r"\s+", "", source).strip()
    if not source:
        raise _Failure("INVALID_LLM_COMMAND", reason="empty")
    if "\n" in source or "\r" in source:
        # Distinguish an actual multi-command response from malformed multiline text.
        if len(re.findall(r"<[a-z_]+>\([^()]*\)(?:<suda_end>)?", source)) > 1:
            raise _Failure("MULTI_COMMAND")
        raise _Failure("INVALID_LLM_COMMAND", reason="not_command_format")
    match = re.fullmatch(r"<(?P<fn>[a-z_]+)>\((?P<args>[^()]*)\)(?P<end><suda_end>)?", source)
    if not match:
        if len(re.findall(r"<[a-z_]+>\([^()]*\)(?:<suda_end>)?", source)) > 1:
            raise _Failure("MULTI_COMMAND")
        raise _Failure("INVALID_LLM_COMMAND", reason="not_command_format")
    if require_suda_end and match.group("end") is None:
        raise _Failure("INVALID_LLM_COMMAND", reason="missing_suda_end")

    params: dict[str, str] = {}
    duplicates: set[str] = set()
    arg_text = match.group("args")
    if arg_text:
        # Whitespace is normalized away before exact command matching.
        for item in arg_text.split(","):
            pair = re.fullmatch(r'([a-z_]+)="([^"()]*)"', item)
            if not pair:
                raise _Failure("INVALID_LLM_COMMAND", reason="not_command_format")
            key, value = pair.groups()
            if key in params:
                duplicates.add(key)
            params[key] = value
    return ParsedCommand(match.group("fn"), params.pop("command", None), params, frozenset(duplicates))


class _Failure(Exception):
    def __init__(self, code: str, *, precondition: str | None = None,
                 result: dict | None = None, message_key: str | None = None,
                 awaiting: str | None = None, minutes: int | None = None,
                 reason: str | None = None):
        super().__init__(code)
        self.code, self.precondition = code, precondition
        self.result, self.message_key = result or {}, message_key
        self.awaiting, self.minutes = awaiting, minutes
        self.reason = reason


def _duration_value(text: str) -> int | None:
    native = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3,
              "네": 4, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
    digits = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6,
              "칠": 7, "팔": 8, "구": 9}
    if text.isdigit():
        return int(text)
    if text in native:
        return native[text]
    if not text or any(ch not in "일이삼사오육칠팔구십백" for ch in text):
        return None
    total = 0
    section = 0
    number = 0
    for ch in text:
        if ch in digits:
            number = digits[ch]
        elif ch == "십":
            section += (number or 1) * 10
            number = 0
        elif ch == "백":
            section += (number or 1) * 100
            number = 0
    return total + section + number


_DURATION_ATOM = r"[0-9]+|하나|한|둘|두|셋|세|넷|네|다섯|여섯|일곱|여덟|아홉|열|[일이삼사오육칠팔구십백]+"


def parse_duration_minutes(utterance: str) -> int | None:
    """Extract duration expressions; clock times such as '3시에' are ignored."""
    compact = re.sub(r"\s+", "", utterance or "")
    parts = list(re.finditer(rf"(?P<h>{_DURATION_ATOM})시간(?P<half>반)?|(?P<m>{_DURATION_ATOM})분", compact))
    if "반시간" in compact:
        parts.append(re.search("반시간", compact))
        total = 30
        # Also allow a leading hour duration, e.g. '한시간 반시간' is intentionally not normalized.
        if len(parts) == 1:
            return total
    total = 0
    found = False
    for part in parts:
        if part is None or part.group(0) == "반시간":
            continue
        found = True
        if part.group("h") is not None:
            value = _duration_value(part.group("h"))
            if value is None:
                return None
            total += value * 60 + (30 if part.group("half") else 0)
        else:
            value = _duration_value(part.group("m"))
            if value is None:
                return None
            total += value
    if "반시간" in compact:
        return total + 30 if found else 30
    return total if found else None


def _part_words() -> dict[str, list[str]]:
    data = _load_yaml(SCHEMA_DIR / "part_words.yaml")
    return data.get("parts", {})


def resolve_part(utterance: str) -> int | None:
    text = re.sub(r"[\s.?!,~]+", "", utterance or "")
    hits = {int(code) for code, words in _part_words().items() if any(word in text for word in words)}
    return next(iter(hits)) if len(hits) == 1 else None


def _functional_groups(text: str) -> set[str]:
    t = re.sub(r"\s+", "", text or "")
    terms = {
        "posture": ("자세", "거북목", "머리위치"),
        "monitor": ("모니터링", "측정시작", "측정중지", "모니터링시작", "모니터링중지"),
        "stretch": ("스트레칭", "목풀", "어깨풀", "허리풀"),
        "sitting": ("착석시간", "앉은시간", "공부시간"),
        "break": ("휴식알림", "쉬는시간", "알림설정", "쉬라고"),
    }
    return {group for group, words in terms.items() if any(word in t for word in words)}


def _result(ok: bool, code: str, text: str, *, result: dict | None = None,
            intent: str | None = None, validated: str | None = None,
            precondition: str | None = None, pending: dict | None = None) -> dict:
    out = {"ok": ok, "success": ok, "code": code, "tts_text": text, "result": result or {}}
    if intent:
        out["intent"] = intent
    if validated:
        out["validated_command"] = validated
    if precondition:
        out["precondition"] = precondition
        out["result"]["precondition"] = precondition
    if pending:
        out["pending"] = pending
        out["result"]["awaiting"] = pending["type"]
        if "minutes" in pending:
            out["result"]["minutes"] = pending["minutes"]
    return out


def _message(code: str, phrases: dict, key: str | None = None) -> str:
    errors = phrases.get("errors", {})
    return errors.get(key or code, errors.get("execution", "명령을 처리하지 못했어요."))


def _validate(parsed: ParsedCommand, raw: str, services, schema: dict) -> ValidatedCommand:
    if parsed.function not in schema.get("functions", {}):
        raise _Failure("INVALID_LLM_COMMAND", reason="unknown_command")
    function = schema["functions"][parsed.function]
    if parsed.command is None:
        raise _Failure("INVALID_LLM_COMMAND", message_key="BAD_PARAM_missing", reason="unknown_command")
    if parsed.command not in function.get("commands", {}):
        raise _Failure("INVALID_LLM_COMMAND", reason="unknown_command")
    spec = function["commands"][parsed.command]
    allowed_params = spec.get("params", {})
    internal_params = {k for k in parsed.params if k.startswith("_")}
    if parsed.duplicate_params or set(parsed.params) - set(allowed_params) - internal_params:
        raise _Failure("INVALID_LLM_COMMAND", reason="invalid_parameter")
    missing = set(spec.get("required", [])) - set(parsed.params)
    if missing:
        if spec.get("on_missing") == "clarify" and "part" in missing:
            raise _Failure("INVALID_LLM_COMMAND", message_key="BAD_PARAM_missing", awaiting="body_part", reason="missing_parameter")
        raise _Failure("INVALID_LLM_COMMAND", message_key="BAD_PARAM_missing", reason="missing_parameter")
    for name, rule in allowed_params.items():
        if name not in parsed.params:
            continue
        value = parsed.params[name]
        if rule.get("type") == "int":
            if rule.get("literal") == "N":
                if value != "N":
                    raise _Failure("INVALID_LLM_COMMAND", reason="minutes_not_literal")
            else:
                if not re.fullmatch(r"[1-9][0-9]*", value):
                    raise _Failure("INVALID_LLM_COMMAND", reason="invalid_parameter")
                number = int(value)
                if not rule["min"] <= number <= rule["max"]:
                    raise _Failure("INVALID_LLM_COMMAND", reason="invalid_parameter")
        elif value in rule.get("disabled", []):
            raise _Failure("INVALID_LLM_COMMAND", reason="disabled_value")
        elif value not in rule.get("values", []):
            raise _Failure("INVALID_LLM_COMMAND", reason="invalid_parameter")

    pre = set(spec.get("prereq", []))
    if (parsed.function, parsed.command) == ("monitor", "pause") and getattr(services, "state", None) != "MONITORING":
        state = getattr(services, "state", None)
        raise _Failure("PRECONDITION", precondition="INVALID_STATE", reason="state_paused" if state == "PAUSED" else "state_idle", message_key="INVALID_STATE")
    if (parsed.function, parsed.command) == ("monitor", "start") and getattr(services, "state", None) == "MONITORING":
        pre.discard("camera_ready")
        pre.discard("calibrated")
    if "calibrated" in pre and not services.calibrated():
        raise _Failure("PRECONDITION", precondition="CALIBRATION_REQUIRED", message_key="CALIBRATION_REQUIRED")
    if "camera_ready" in pre:
        ensure_camera = getattr(services, "ensure_camera_ready", None)
        camera_ready = ensure_camera() if ensure_camera else (getattr(services, "_health", None) or {}).get("camera") == "ready"
        if not camera_ready:
            raise _Failure("PRECONDITION", precondition="CAMERA_NOT_READY", message_key="CAMERA_NOT_READY")
    if "monitoring" in pre and getattr(services, "state", None) != "MONITORING":
        posture = services.get_posture() if hasattr(services, "get_posture") else {}
        reason = "not_monitoring"
        if posture.get("state") == "unavailable":
            reason = "unavailable:" + str(posture.get("reason") or "unknown")
        raise _Failure("PRECONDITION", precondition="POSTURE_DATA_UNAVAILABLE", reason=reason, message_key="POSTURE_DATA_UNAVAILABLE")
    if "not_unavailable" in pre:
        state = services.get_posture().get("state")
        if state == "unavailable":
            raise _Failure("PRECONDITION", precondition="POSTURE_DATA_UNAVAILABLE", reason="unavailable", result={"reason": "unavailable"}, message_key="POSTURE_DATA_UNAVAILABLE")
    if "session" in pre:
        if not (getattr(services, "session", None) or (services.get_session() or {}).get("session_id")):
            raise _Failure("PRECONDITION", precondition="SESSION_NOT_FOUND", message_key="SESSION_NOT_FOUND")
    if "session_or_last" in pre:
        current = services.get_session()
        last = services.get_last_session()
        if not ((current or {}).get("session_id") or last):
            raise _Failure("PRECONDITION", precondition="SESSION_NOT_FOUND", message_key="SESSION_NOT_FOUND")
    intent = f"{parsed.function}_{parsed.command}"
    return ValidatedCommand(parsed.function, parsed.command, parsed.params, intent, raw, _TOKEN)


def _duration_text(seconds: int) -> str:
    minutes = max(0, int(seconds)) // 60
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours}시간 {rest}분"
    if hours:
        return f"{hours}시간"
    return f"{rest}분"


def _execute(command: ValidatedCommand, services, phrases: dict, conversation: dict | None = None) -> dict:
    if command._token is not _TOKEN:
        raise TypeError("executor accepts validated commands only")
    fn, action, p = command.function, command.command, command.params
    if fn == "posture":
        posture = services.get_posture()
        state = posture.get("state", "unavailable")
        result = {"state": state}
        if posture.get("reason"):
            result["reason"] = posture["reason"]
        indicator = (posture.get("indicators") or {}).get("head_relative_position") or {}
        if isinstance(indicator, dict) and indicator.get("delta") is not None:
            result["delta"] = indicator["delta"]
        prefix = phrases.get("posture_check_all_prefix", "") if p.get("type") == "0" else ""
        message = phrases.get("posture_state", {}).get(state)
        if state == "unavailable":
            message = phrases.get("posture_unavailable", "지금은 자세를 측정할 수 없어요.")
        text = " ".join(part for part in (prefix, message) if part)
        result["message"] = text
        return _result(True, "OK", text, result=result, intent=command.intent, validated=command.raw)

    if fn == "monitor":
        if action == "start" and getattr(services, "state", None) == "MONITORING":
            return _result(True, "OK", "이미 자세 모니터링 중입니다.", result={"system_state": "MONITORING"}, intent=command.intent, validated=command.raw)
        method_name = {"start": "monitoring_start",
                       "pause": "monitoring_pause",
                       "stop": "monitoring_stop"}[action]
        response = getattr(services, method_name)()
        system_state = response.get("system_state", getattr(services, "state", None))
        text = response.get("message") or {"start": "모니터링을 시작했어요.",
                                           "pause": "모니터링을 일시정지했어요.",
                                           "stop": "모니터링을 종료했어요."}[action]
        return _result(True, "OK", text, result={"system_state": system_state}, intent=command.intent, validated=command.raw)

    if fn == "clarify":
        key = command.params.get("_pending", command.command)
        prompts = phrases.get("clarify", {})
        return _result(True, "OK", prompts.get(key, phrases.get("clarify_part", "다시 말씀해 주세요.")),
                       intent=command.intent, validated=command.raw, pending={"type": key})
    if fn == "unsupported":
        category = command.params.get("_category", "general")
        messages = phrases.get("unsupported", {})
        return _result(False, "UNSUPPORTED", messages.get(category, messages.get("general", "아직 지원하지 않는 요청이에요.")),
                       result={"reason": category}, intent=command.intent, validated=command.raw)

    if fn == "stretch":
        catalog = _load_yaml(ROOT / "config" / "stretch_exercises.yaml")
        exercises = catalog.get(str(p["part"]), [])
        context = conversation or {}
        last = context.get("last_stretch") or {}
        mode = context.get("stretch_mode", "first")
        selected = None
        if mode == "repeat" and str(last.get("part")) == str(p["part"]):
            selected = next((x for x in exercises if x.get("id") == last.get("last_exercise_id")), None)
        elif mode == "another" and str(last.get("part")) == str(p["part"]):
            shown = set(last.get("shown_exercise_ids", []))
            selected = next((x for x in exercises if x.get("id") not in shown), None)
            if selected is None:
                text = "현재 안내할 수 있는 다른 동작은 없어요. 방금 동작을 다시 안내할까요?"
                return _result(False, "UNSUPPORTED", text, result={"reason": "no_alternative_exercise", "part": int(p["part"])},
                               intent=command.intent, validated=command.raw)
        if selected is None and exercises:
            selected = exercises[0]
        if selected is None:
            return _result(False, "UNSUPPORTED", "해당 부위의 스트레칭 안내를 준비하지 못했어요.",
                           result={"reason": "stretch_content_unavailable", "part": int(p["part"])},
                           intent=command.intent, validated=command.raw)
        steps = selected.get("steps", [])
        title = selected.get("title", phrases.get("stretch", {}).get(p["part"], "스트레칭 안내"))
        text = " ".join([title, *steps])
        return _result(True, "OK", text, result={"part": int(p["part"]), "title": title,
                                                  "steps": steps, "exercise_id": selected["id"]},
                       intent=command.intent, validated=command.raw)

    if fn in ("sitting", "break") and action in ("time", "check"):
        current = services.get_session() or {}
        last = services.get_last_session()
        if current.get("session_id"):
            duration = _duration_text(current.get("sitting_sec", 0))
            text = phrases.get("sitting_current", "현재 착석 시간은 {duration}이에요.").format(duration=duration)
        else:
            duration = _duration_text((last or {}).get("sitting_sec", 0))
            text = phrases.get("sitting_previous", "직전 세션 착석 시간은 {duration}이에요.").format(duration=duration)
        if fn == "break":
            text = phrases.get("break_check", "현재 착석 시간은 {duration}이에요.").format(duration=duration)
        return _result(True, "OK", text, result={"sitting_sec": current.get("sitting_sec", (last or {}).get("sitting_sec", 0))},
                       intent=command.intent, validated=command.raw)

    if fn == "break" and action == "set_alarm":
        minutes = p.get("_minutes")
        if minutes is None:
            return _result(True, "OK", phrases.get("clarify", {}).get("time", "몇 분 뒤로 설정할까요?"),
                           intent=command.intent, validated=command.raw, pending={"type": "time"})
        response = services.set_break_alarm(int(minutes))
        if not response.get("set"):
            text = phrases.get("alarm_already_set", "기존 알림이 설정되어 있어요.")
        else:
            text = phrases.get("alarm_set", "{minutes}분 뒤에 알려 드릴게요.").format(minutes=minutes)
        return _result(True, "OK", text, result=response, intent=command.intent, validated=command.raw)

    raise _Failure("INVALID_LLM_COMMAND", reason="unknown_command")


def process(raw: str, services, *, utterance: str | None = None,
            options: Options | dict | None = None, conversation: dict | None = None) -> dict:
    """Parse → guard → validate → execute. Compatible with P2 service handles."""
    schema = _schema()
    phrases = _phrases()
    if options is None:
        options = Options(bool(schema.get("require_suda_end", True)))
    elif isinstance(options, dict):
        options = Options(**options)
    try:
        normalized_raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)
        normalized_raw = re.sub(r"\s+", "", normalized_raw).strip()
        parsed = _parse(normalized_raw, options.require_suda_end)
        raw = normalized_raw
        if parsed.function == "unsupported":
            normalized = re.sub(r"\s+", "", utterance or "")
            medical = _load_yaml(SCHEMA_DIR / "out_of_scope.yaml").get("medical", [])
            urgent = _load_yaml(SCHEMA_DIR / "out_of_scope.yaml").get("medical_urgent", [])
            category = "medical_urgent" if any(w in normalized for w in urgent) else "medical" if any(w in normalized for w in medical) else "general"
            parsed = ParsedCommand(parsed.function, parsed.command, {"_category": category}, parsed.duplicate_params)
            groups = _functional_groups(utterance or "")
            guard_mode = _load_yaml(ROOT / "config" / "api.yaml").get("multi_guard", "unsupported_only")
            if guard_mode != "off" and len(groups) >= 2:
                raise _Failure("MULTI_COMMAND", reason="multiple_function_groups")
        if utterance and parsed.function != "unsupported":
            normalized = re.sub(r"\s+", "", utterance)
            guard = _load_yaml(SCHEMA_DIR / "out_of_scope.yaml")
            words = guard.get(parsed.function, [])
            if any(word in normalized for word in words):
                raise _Failure("UNSUPPORTED", reason="general", message_key="out_of_scope")
        validated = _validate(parsed, raw.strip(), services, schema)
        if utterance:
            cfg = _load_yaml(ROOT / "config" / "api.yaml")
            guard_mode = cfg.get("multi_guard", "unsupported_only")
            groups = _functional_groups(utterance)
            if guard_mode == "block" and len(groups) >= 2 and re.search(r"그리고|하고|한뒤|하고나서|다음에|후에", utterance):
                raise _Failure("MULTI_COMMAND", reason="multiple_function_groups")
        if (validated.function, validated.command) == ("break", "set_alarm"):
            rule_minutes = parse_duration_minutes(utterance or "")
            if rule_minutes is None and conversation:
                rule_minutes = conversation.get("duration_minutes")
            if rule_minutes is None:
                return _result(True, "OK", phrases.get("clarify", {}).get("time", "몇 분 뒤로 설정할까요?"),
                               intent=validated.intent, validated=validated.raw, pending={"type": "time"})
            if not 1 <= rule_minutes <= 180:
                raise _Failure("INVALID_TIME_RANGE", reason="alarm_too_short" if rule_minutes < 1 else "alarm_too_long")
            params = dict(validated.params)
            params["_minutes"] = str(rule_minutes)
            validated = ValidatedCommand(validated.function, validated.command, params,
                                         validated.intent, validated.raw, _TOKEN)
        return _execute(validated, services, phrases, conversation)
    except _Failure as failure:
        text = _message(failure.code, phrases, failure.message_key)
        pending = {"type": failure.awaiting} if failure.awaiting else None
        result = dict(failure.result)
        if failure.reason:
            result["reason"] = failure.reason
        return _result(failure.code == "OK", failure.code, text, result=result,
                       precondition=failure.precondition, pending=pending)
    except Exception as error:
        # Do not include utterances, raw model output, or exception bodies in logs/API.
        import logging
        logging.getLogger("p4.command").warning("command execution failed: %s", type(error).__name__)
        return _result(False, "ERROR", _message("ERROR", phrases, "execution"))


def process_raw(raw: str, services) -> dict:
    return process(raw, services)


def process_p2(raw: str, utterance: str | None, services, *, conversation: dict | None = None) -> dict:
    """Adapter for the P2 CommandService's existing processor protocol."""
    return process(raw, services, utterance=utterance, conversation=conversation)


__all__ = ["Options", "ParsedCommand", "ValidatedCommand", "process", "process_raw",
           "process_p2", "resolve_part", "parse_duration_minutes"]
