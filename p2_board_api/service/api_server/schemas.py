from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

Reason = Literal["low_confidence", "occluded", "out_of_frame", "ear_not_detected",
                 "shoulder_not_detected", "invalid_geometry", "not_calibrated", "camera_disconnected"]


class Indicator(BaseModel):
    delta: Optional[float] = None
    status: Literal["normal", "attention"]


class PostureState(BaseModel):
    """C6 PostureState. 엔진이 보낸 알 수 없는 최상위 필드는 버린다(extra=ignore)."""
    model_config = ConfigDict(extra="ignore")
    state: Literal["normal", "attention", "unavailable"]
    reason: Optional[Reason] = None
    indicators: dict = {}
    landmarks_ok: dict = {}
    confidence: float = 0.0
    duration_sec: int = 0
    updated_at: datetime
    debug: Optional[dict] = None   # debug_mode 에서만 응답에 남긴다


class ControlReq(BaseModel):
    model_config = ConfigDict(extra="ignore")
    request_id: Optional[str] = None
    source: Optional[Literal["app", "voice"]] = None


class CalibrationStartReq(ControlReq):
    duration_sec: int = Field(5, ge=3, le=10)


class CalibrationConfirmReq(ControlReq):
    calibration_id: Optional[str] = None
    confirm: bool = True


class CommandReq(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source: Literal["voice", "app"]
    utterance: Optional[str] = None
    command: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = Field(None, min_length=1, max_length=128)


class DebugLabelReq(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str
    request_id: Optional[str] = None
