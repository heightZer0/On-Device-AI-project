"""설정 키·범위. 범위 값은 전부 PLACEHOLDER (TODO(실험)/기획 확정 후 교체)."""
SPECS = {
    "microphone_enabled":     {"kind": bool, "default": True},
    "voice_feedback_enabled": {"kind": bool, "default": True},
    "tts_volume":             {"kind": float, "lo": 0.0, "hi": 1.0, "default": 0.7},   # P0 D-10
    "tts_speed":              {"kind": float, "lo": 0.5, "hi": 2.0, "default": 1.0},   # PLACEHOLDER
    "alert_interval_sec":     {"kind": int, "lo": 30, "hi": 600, "default": 300},     # P0 D-10
    "posture_sensitivity":    {"kind": str, "choices": ["low", "normal", "high"], "default": "normal"}, # T_forward 매핑 TODO(실험)
    "debug_mode":             {"kind": bool, "default": False},
    "event_log_enabled":      {"kind": bool, "default": False},
    "preview_stream_enabled": {"kind": bool, "default": False},
    "time_crosscheck_mode":   {"kind": str, "choices": ["off", "confirm", "override"], "default": "confirm"},
}
DEFAULTS = {k: v["default"] for k, v in SPECS.items()}


def validate_patch(patch):
    errors = {}
    for k, v in patch.items():
        s = SPECS.get(k)
        if s is None:
            errors[k] = "알 수 없는 설정이에요"
            continue
        kind = s["kind"]
        if kind is bool:
            ok = isinstance(v, bool)
        elif kind is int:
            ok = isinstance(v, int) and not isinstance(v, bool) and s["lo"] <= v <= s["hi"]
        elif kind is float:
            ok = isinstance(v, (int, float)) and not isinstance(v, bool) and s["lo"] <= v <= s["hi"]
        else:
            ok = isinstance(v, str) and v in s["choices"]
        if not ok:
            errors[k] = "값 형식 또는 범위가 올바르지 않아요"
    return errors
