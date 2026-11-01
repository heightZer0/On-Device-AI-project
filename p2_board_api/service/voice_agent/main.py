"""프로세스 B 진입점.  프로젝트 루트에서:  python -m service.voice_agent.main [--config path]

모델 로딩에 실패해도 /speak 서버는 뜬다(상태가 error 로 보임). 보장선: LLM·P2 없이 /speak 만으로 경고 음성 재생.
"""
from __future__ import annotations

import argparse
import logging

import uvicorn
import yaml

from .agent import DisabledAgent, VoiceAgent
from .speak_server import create_app
from .tts import SherpaTTS, Speaker, UnavailableEngine, make_sd_player

log = logging.getLogger("voice.main")


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build(cfg: dict):
    p, th = cfg["paths"], cfg["threads"]
    # --- TTS (최우선) ---
    try:
        engine = SherpaTTS(p["tts_model"], p["tts_tokens"], p["tts_data_dir"], th["tts"], cfg["tts"]["sid"])
    except Exception as e:  # noqa: BLE001
        log.error("TTS model load failed: %s", type(e).__name__)
        engine = UnavailableEngine(str(type(e).__name__))
    try:
        player = make_sd_player(cfg["audio"]["output_device"])
    except Exception as e:  # noqa: BLE001
        log.error("audio output unavailable: %s", type(e).__name__)
        def player(*_a, **_k):
            raise RuntimeError("no audio output")
    t = cfg["tts"]
    speaker = Speaker(engine, player, speed=t["speed"], volume=t["volume"],
                      max_chars=t["max_chars_per_chunk"], max_queue=cfg["speaker_queue"]["max_len"],
                      post_play_mute_ms=cfg["echo_guard"]["post_play_mute_ms"])
    speaker.start()

    # --- VAD / STT / 마이크 (실패해도 /speak 는 계속) ---
    try:
        from .audio_io import MicStream
        from .stt import SenseVoiceSTT
        from .vad import VadSegmenter

        v = cfg["vad"]
        vad = VadSegmenter(p["vad"], v["threshold"], v["min_silence_sec"], v["min_speech_sec"],
                           v["max_speech_sec"], cfg["audio"]["sample_rate"])
        stt = SenseVoiceSTT(p["stt_model"], p["stt_tokens"], th["stt"], cfg["stt"]["language"], cfg["stt"]["use_itn"])
        mic = MicStream(cfg["audio"]["input_device"], cfg["audio"]["sample_rate"])
        agent = VoiceAgent(cfg, mic, vad, stt, speaker)
        agent.start()
    except Exception as e:  # noqa: BLE001
        log.error("voice pipeline disabled: %s", type(e).__name__)
        agent = DisabledAgent()
    return speaker, agent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="service/voice_agent/config.yaml")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    speaker, agent = build(cfg)
    try:
        s = cfg["speak_server"]
        uvicorn.run(create_app(speaker, agent), host=s["host"], port=s["port"], log_level="info")
    finally:
        if hasattr(agent, "stop"):
            agent.stop()
        speaker.stop()


if __name__ == "__main__":
    main()
