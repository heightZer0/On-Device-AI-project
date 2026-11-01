"""P2 -> P3 HTTP 규격 (v10.2 P3-S4): /speak, /speak/warmup, /speak/state, /mic.
마이크가 꺼져도 /speak 는 동작한다."""
from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class SpeakReq(BaseModel):
    text: str
    kind: Literal["alert", "reply"] = "reply"
    volume: Optional[float] = Field(None, ge=0, le=1)
    speed: Optional[float] = Field(None, gt=0, le=3)


class WarmupReq(BaseModel):
    texts: List[str]


class MicReq(BaseModel):
    enabled: bool


class SettingsReq(BaseModel):
    tts_volume: float = Field(ge=0, le=1)
    tts_speed: float = Field(gt=0, le=3)


def _err(status: int, code: str, msg: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": msg}}, status_code=status)


def create_app(speaker, agent) -> FastAPI:
    app = FastAPI(title="voice_agent")

    @app.post("/speak")
    def speak(req: SpeakReq):
        if not req.text.strip():
            return _err(400, "EMPTY_TEXT", "text is empty")
        n = speaker.enqueue(req.text, req.kind, req.volume, req.speed)
        return {"accepted": True, "queue_len": n}

    @app.post("/speak/warmup")
    def warmup(req: WarmupReq):
        try:
            return {"cached": speaker.warmup(req.texts)}
        except Exception:  # noqa: BLE001
            return _err(503, "TTS_UNAVAILABLE", "tts warmup failed")

    @app.get("/speak/state")
    def state():
        s = speaker.state()
        mic = agent.mic_state()
        stt = "error" if mic == "error" else "ready"
        return {"stt": stt, "tts": s["tts"], "mic": mic, "queue_len": s["queue_len"]}

    @app.post("/mic")
    def mic(req: MicReq):
        return {"mic": agent.set_mic(req.enabled)}

    @app.post("/settings")
    def settings(req: SettingsReq):
        speaker.update_defaults(volume=req.tts_volume, speed=req.tts_speed)
        return {"success": True}

    return app
