import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from posture.analyzer.analyzer import Obs, PostureAnalyzer   # noqa: E402
from posture.rules.config import load_config                  # noqa: E402

W, HH, DT = 640, 480, 0.1


def make_cfg(**kw):
    """테스트는 설정 파일의 placeholder 값에 의존하지 않도록 값을 명시한다."""
    base = dict(
        T_vis=0.5, N_low_vis=3, frame_margin=0.05, T_forward=0.10, T_hold_sec=5.0,
        T_reset_sec=3.0, K_recover=3, alert_interval_sec=20.0, calib_duration_sec=2.0,
        smooth_window=1, unavailable_prolonged_sec=2.0, recalib_suggest_count=3,
        recalib_window_sec=1000.0, calib_min_frames=10, calib_min_stable_ratio=0.5,
        calib_max_spread=None, T_release=None, max_dt_sec=1.0, l_ref_mode="C", camera_retry_sec=0.0)
    base.update(kw)
    return load_config(**base)


def make_cal(d=1, side="left", H_base=0.0, L=100.0):
    return {"H_base": H_base, "x_shoulder_base": 300.0, "L_ref_fixed": L,
            "side": side, "d": d, "created_at": "2026-01-01T00:00:00"}


def obs(ts, H=0.0, d=1, L=100.0, ve=0.9, vs=0.9, detected=True, xe=None, ye=200.0, ys=300.0):
    xs = 300.0
    if xe is None:
        xe = xs + d * H * L          # H = d*(xe-xs)/L
    return Obs(ts=ts, detected=detected, xe=xe, ye=ye, xs=xs, ys=ys, ve=ve, vs=vs, width=W, height=HH)


BAD = dict(ye=350.0)                 # 귀가 어깨(ys=300)보다 아래 → invalid_geometry


class Feeder:
    def __init__(self, cfg=None, cal="default", **cfgkw):
        self.cfg = cfg or make_cfg(**cfgkw)
        self.events = []
        self.cal = make_cal() if cal == "default" else cal
        self.a = PostureAnalyzer(self.cfg, self.cal, emit=self.events.append)
        self.t = 0.0

    def feed(self, n, **kw):
        for _ in range(n):
            self.a.update(obs(self.t, **kw))
            self.t += DT
        return self.a.get_state()

    def types(self, name=None):
        t = [e["type"] for e in self.events]
        return t if name is None else [x for x in t if x == name]
