"""설정 로더. 값은 config/posture.yaml 한 곳에서만 정의하고 모든 모듈이 이 로더로 읽는다. (명세 C5, C9)"""
import os
from dataclasses import dataclass, fields
from typing import Optional

import yaml

DEFAULT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "posture.yaml"))


@dataclass(frozen=True)
class PostureConfig:
    T_vis: float
    N_low_vis: int
    frame_margin: float
    T_forward: float
    T_release: Optional[float]
    T_hold_sec: float
    T_reset_sec: float
    K_recover: int
    alert_interval_sec: float
    calib_duration_sec: float
    l_ref_mode: str
    smooth_window: int
    max_dt_sec: float
    calib_min_frames: int
    calib_min_stable_ratio: float
    calib_max_spread: Optional[float]
    unavailable_prolonged_sec: float
    recalib_suggest_count: int
    recalib_window_sec: float
    calibration_path: str
    camera_index: int
    camera_retry_sec: float
    model_complexity: int


def load_config(path=None, **overrides) -> PostureConfig:
    with open(path or DEFAULT_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    raw.update(overrides)
    names = {f.name for f in fields(PostureConfig)}
    unknown, missing = set(raw) - names, names - set(raw)
    if unknown:
        raise ValueError(f"알 수 없는 설정 키: {sorted(unknown)}")
    if missing:
        raise ValueError(f"누락된 설정 키: {sorted(missing)}")
    cfg = PostureConfig(**raw)
    if cfg.l_ref_mode not in ("A", "B", "C"):
        raise ValueError("l_ref_mode 는 A, B, C 중 하나여야 한다")
    if cfg.T_release is not None and cfg.T_release > cfg.T_forward:
        raise ValueError("T_release 는 T_forward 이하여야 한다 (해제 기준이 진입 기준보다 높으면 안 됨)")
    return cfg
