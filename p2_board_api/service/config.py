"""설정 로더. 주소·포트·타임아웃은 config/api.yaml 에서만 읽는다(C8)."""
import copy
from pathlib import Path
import yaml

DEFAULTS = {
    "server": {"host": "0.0.0.0", "port": 8000},
    "speak_url": "http://127.0.0.1:8081",
    "llm_url": "http://127.0.0.1:8080/v1/chat/completions",
    "llm_model": "rkllm",
    "llm_system_prompt": "",
    "llm_timeout_sec": 30,
    "tts_wait_timeout_sec": 10,
    "auth": {"enabled": True, "token_env": "BAJAHOE_DEVICE_TOKEN"},
    "rate_limit": {"per_client_per_sec": None},  # TODO(실험)
    "request_id_cache": {"ttl_sec": 300, "max_items": 1000},  # PLACEHOLDER
    "poll_hint_sec": 1,
    "session": {"tick_sec": 1, "checkpoint_sec": 30},
    "storage": {"json_path": "data/store"},
    "mdns": {"enabled": False, "service_type": "_bajahoe._tcp", "name": "bajahoe"},
    "preview_stream_enabled": False,
    "conversation_ttl_sec": 10,  # PLACEHOLDER
    "break_alarm_replace": True,  # TODO(CP0)
    "health_refresh_sec": 5,
    "phrases_path": "config/phrases.yaml",
    "part_words_path": "command/schema/part_words.yaml",
}


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path="config/api.yaml"):
    p = Path(path)
    return _merge(DEFAULTS, load_yaml(p) if p.exists() else {})
