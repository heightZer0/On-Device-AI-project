"""
캘리브레이션 (명세 P1-8).

- 기준값은 영상이 아니라 숫자(H_base, x_shoulder_base, L_ref_fixed, side, d)로만 저장한다. (C2-8)
- 안정 프레임의 '중앙값'으로 계산한다. 귀가 어깨보다 아래인 프레임(invalid_geometry)은 제외한다.
- 변동 폭(IQR)은 항상 info 에 남긴다. 거부 기준(calib_max_spread)은 명세상 TBD → null 이면 거부하지 않는다.
- d 판별(코 x 와 귀 x 비교)은 명세상 0단계 검증 대상인 가정이다.
"""
import json
import math
import os
import statistics
from datetime import datetime
from typing import Optional, Tuple

CAL_KEYS = ("H_base", "x_shoulder_base", "L_ref_fixed", "side", "d", "created_at")   # C6 Calibration


def ref_len(mode: str, p: dict) -> float:
    if mode == "C":                       # |y_어깨 - y_귀| (기본)
        return abs(p["ys"] - p["ye"])
    if mode == "A":                       # 귀-눈 거리
        return math.hypot(p["xe"] - p["ex"], p["ye"] - p["ey"])
    return float(p["h"])                  # B: 이미지 높이


def sample_ok(p: dict, cfg) -> bool:
    mx, my = cfg.frame_margin * p["w"], cfg.frame_margin * p["h"]
    if p["ve"] < cfg.T_vis or p["vs"] < cfg.T_vis:
        return False
    if not all(mx <= x <= p["w"] - mx and my <= y <= p["h"] - my
               for x, y in ((p["xe"], p["ye"]), (p["xs"], p["ys"]))):
        return False
    if p["ye"] > p["ys"]:                 # invalid_geometry 프레임 제외
        return False
    if cfg.l_ref_mode == "A" and p["vey"] < cfg.T_vis:
        return False
    return True


_EMPTY = dict(xe=0.0, ye=0.0, xs=0.0, ys=0.0, xn=0.0, ex=0.0, ey=0.0, ve=0.0, vs=0.0, vey=0.0)


class CalibrationCollector:
    """calib_duration_sec 동안 프레임을 모은다. 시작 시각은 첫 프레임의 ts."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.samples = {"left": [], "right": []}
        self.t0: Optional[float] = None
        self.last_ts: Optional[float] = None

    def add(self, frame):
        if self.t0 is None:
            self.t0 = frame.ts
        self.last_ts = frame.ts
        for side in ("left", "right"):
            base = frame.pose.get(side) if frame.pose else None
            # 사람 미검출 프레임도 기록(가시성 0) → 안정 프레임 비율에 반영
            self.samples[side].append(dict(base or _EMPTY, w=frame.width, h=frame.height))

    def progress(self) -> float:
        if self.t0 is None or self.last_ts is None:
            return 0.0
        return max(0.0, min(1.0, (self.last_ts - self.t0) / max(self.cfg.calib_duration_sec, 1e-9)))

    def done(self) -> bool:
        return self.t0 is not None and self.last_ts - self.t0 >= self.cfg.calib_duration_sec


def compute_calibration(samples: dict, cfg) -> Tuple[Optional[dict], dict]:
    """(Calibration 또는 None, info). 실패하면 info['error'] 에 사유 코드가 들어간다."""
    info = {"l_ref_mode": cfg.l_ref_mode}
    mean_vis = {s: (statistics.mean((p["ve"] + p["vs"]) / 2 for p in lst) if lst else 0.0)
                for s, lst in samples.items()}
    info["mean_vis"] = {k: round(v, 3) for k, v in mean_vis.items()}
    side = max(mean_vis, key=mean_vis.get)         # 양쪽 visibility 평균이 높은 쪽
    lst = samples[side]
    good = [p for p in lst if sample_ok(p, cfg)]
    info.update(side=side, n_all=len(lst), n_good=len(good))
    if len(lst) < cfg.calib_min_frames:
        info["error"] = "too_few_frames"
        return None, info
    if len(good) < cfg.calib_min_stable_ratio * len(lst) or not good:
        info["error"] = "too_few_stable_frames"
        return None, info
    L = statistics.median(ref_len(cfg.l_ref_mode, p) for p in good)
    if L < 1e-6:
        info["error"] = "invalid_reference_length"
        return None, info
    dir_val = statistics.median(p["xn"] - p["xe"] for p in good)
    if dir_val == 0:
        info["error"] = "direction_unknown"
        return None, info
    d = 1 if dir_val > 0 else -1                   # 코가 귀보다 오른쪽이면 오른쪽을 향함(+1)
    hs = [d * (p["xe"] - p["xs"]) / L for p in good]
    if len(hs) >= 2:
        q = statistics.quantiles(hs, n=4)
        spread = q[2] - q[0]
    else:
        spread = 0.0
    info["spread_iqr"] = round(spread, 4)          # 변동 폭은 항상 로그로 남긴다
    if cfg.calib_max_spread is not None and spread > cfg.calib_max_spread:
        info["error"] = "too_much_variation"
        return None, info
    cal = {
        "H_base": statistics.median(hs),
        "x_shoulder_base": statistics.median(p["xs"] for p in good),
        "L_ref_fixed": L, "side": side, "d": d,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    return cal, info


def save_calibration(cal: dict, path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: cal[k] for k in CAL_KEYS}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)                          # 쓰다 중단돼도 기존 파일이 깨지지 않도록


def load_calibration(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            cal = json.load(f)
        return cal if all(k in cal for k in CAL_KEYS) else None
    except (OSError, ValueError):
        return None
