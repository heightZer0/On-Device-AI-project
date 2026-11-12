from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from service.api_server.app import create_app
from service.config import load_config, load_yaml
from service.hub.command_service import CommandService
from service.hub.hub import Hub
from service.session_service.store import Store
from tests.api.fakes import FakeEngine, FakeLLM, FakeProcessor, FakeSpeak

TOKEN = "test-token"


def make(calibrated=False, db=":memory:", **cfg_over):
    cfg = load_config()
    cfg["auth"] = {"enabled": True, "token": TOKEN, "token_env": "X"}
    cfg["storage"]["json_path"] = db
    cfg.update(cfg_over)
    phrases, words = load_yaml(cfg["phrases_path"]), load_yaml(cfg["part_words_path"])["parts"]
    eng, spk, llm, proc, store = FakeEngine(calibrated), FakeSpeak(), FakeLLM(), FakeProcessor(), Store(db)
    hub = Hub(cfg, eng, store, spk, llm, phrases, async_speak=False)
    clock = SimpleNamespace(t=0.0)
    cmd = CommandService(hub, llm, proc, phrases, words, mono=lambda: clock.t)
    app = create_app(hub, cmd, cfg)
    client = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    return SimpleNamespace(cfg=cfg, eng=eng, spk=spk, llm=llm, proc=proc, store=store, hub=hub, cmd=cmd,
                           clock=clock, c=client, app=app)


@pytest.fixture
def env():
    return make(calibrated=True)


@pytest.fixture
def env_uncal():
    return make(calibrated=False)
