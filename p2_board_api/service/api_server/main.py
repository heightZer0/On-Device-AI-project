"""실행: BAJAHOE_DEVICE_TOKEN=... python -m service.api_server.main"""
import logging
import sys
from pathlib import Path

import uvicorn

from service.api_server.app import create_app
from service.api_server.mdns import Mdns
from service.config import load_config, load_yaml
from service.hub.clients import HttpLLMClient, HttpSpeakClient
from service.hub.command_service import CommandService
from service.hub.hub import Hub
from service.session_service.store import Store


def build():
    cfg = load_config()
    # The supplied P1 module is a sibling project directory in this ZIP.
    p1_root = Path(__file__).resolve().parents[3] / "desk_pacemaker_p1_v1"
    sys.path.insert(0, str(p1_root.resolve()))
    try:
        from posture.engine import PostureEngine          # P1
    except ImportError as e:
        raise SystemExit("P1 PostureEngine(posture/engine.py)이 필요해요. 개발 중에는 tests/api/fakes.py 의 mock 을 쓰세요.") from e
    import command as p4
    processor = p4
    phrases, words = load_yaml(cfg["phrases_path"]), load_yaml(cfg["part_words_path"])["parts"]
    speak = HttpSpeakClient(cfg["speak_url"], cfg["tts_wait_timeout_sec"])
    llm = HttpLLMClient(cfg["llm_url"], cfg["llm_model"], cfg["llm_timeout_sec"])
    hub = Hub(cfg, PostureEngine(), Store(cfg["storage"]["json_path"]), speak, llm, phrases)
    cmd = CommandService(hub, llm, processor, phrases, words)
    return create_app(hub, cmd, cfg, background=True, mdns=Mdns(cfg)), cfg


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app, cfg = build()
    uvicorn.run(app, host=cfg["server"]["host"], port=cfg["server"]["port"])
