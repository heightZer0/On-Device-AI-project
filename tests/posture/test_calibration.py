import json
import os

import pytest
from helpers import make_cfg
from posture.calibration.calibration import (CAL_KEYS, compute_calibration, load_calibration,
                                             save_calibration)


def sample(H=0.0, d=1, L=100.0, ve=0.9, vs=0.9, ye=200.0, w=640, h=480):
    xs, ys = 300.0, 300.0
    xe = xs + d * H * L
    return dict(xe=xe, ye=ye, xs=xs, ys=ys, xn=xe + 10 * d, ex=xe + 5 * d, ey=ye,
                ve=ve, vs=vs, vey=0.9, w=w, h=h)


def samples(n=30, left=None, right=None, **kw):
    left = left or {}
    right = right or {"ve": 0.6, "vs": 0.6}
    return {"left": [sample(**{**kw, **left}) for _ in range(n)],
            "right": [sample(**{**kw, **right}) for _ in range(n)]}


def test_basic_calibration_values():
    cal, info = compute_calibration(samples(H=0.2), make_cfg())
    assert cal["side"] == "left"                                   # visibility 평균이 높은 쪽
    assert cal["d"] == 1
    assert cal["L_ref_fixed"] == pytest.approx(100.0)               # 후보 C = |y_어깨 - y_귀|
    assert cal["H_base"] == pytest.approx(0.2)
    assert cal["x_shoulder_base"] == pytest.approx(300.0)
    assert set(cal) == set(CAL_KEYS)                                # C6 스키마 그대로


def test_direction_left_gives_minus_one_and_forward_is_larger_H():
    cal, _ = compute_calibration(samples(H=0.2, d=-1), make_cfg())
    assert cal["d"] == -1 and cal["H_base"] == pytest.approx(0.2)


def test_side_choice_follows_visibility():
    cal, _ = compute_calibration(samples(left={"ve": 0.55, "vs": 0.55}, right={"ve": 0.95, "vs": 0.95}), make_cfg())
    assert cal["side"] == "right"


def test_invalid_geometry_frames_are_excluded():
    s = samples(n=30)
    for p in s["left"][:10]:
        p["ye"], p["xe"] = 350.0, 900.0                             # 귀가 어깨보다 아래(+ 값 튐)
    cal, info = compute_calibration(s, make_cfg())
    assert info["n_good"] == 20 and cal["H_base"] == pytest.approx(0.0)


def test_rejects_too_few_frames_and_too_few_stable():
    _, info = compute_calibration(samples(n=5), make_cfg())
    assert info["error"] == "too_few_frames"
    cal, info = compute_calibration(samples(left={"ve": 0.1, "vs": 0.1}, right={"ve": 0.05, "vs": 0.05}), make_cfg())
    assert cal is None and info["error"] == "too_few_stable_frames"


def test_spread_is_logged_and_rejected_only_when_threshold_set():
    s = samples(n=40)
    for i, p in enumerate(s["left"]):
        p["xe"] += 40 * (i % 2)                                     # H 가 0.0 / 0.4 로 번갈아 흔들림
    cal, info = compute_calibration(s, make_cfg(calib_max_spread=None))
    assert cal is not None and info["spread_iqr"] > 0.1             # 기준 TBD: 거부 없이 로그만
    cal, info = compute_calibration(s, make_cfg(calib_max_spread=0.05))
    assert cal is None and info["error"] == "too_much_variation"


def test_save_load_roundtrip_and_only_numbers_stored(tmp_path):
    cal, _ = compute_calibration(samples(H=0.2), make_cfg())
    path = str(tmp_path / "calibration.json")
    save_calibration(cal, path)
    assert load_calibration(path) == cal
    assert set(json.load(open(path, encoding="utf-8"))) == set(CAL_KEYS)
    assert os.listdir(tmp_path) == ["calibration.json"]             # 영상·좌표 원본 없음, tmp 파일도 남지 않음


def test_load_missing_or_corrupt_returns_none(tmp_path):
    assert load_calibration(str(tmp_path / "none.json")) is None
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_calibration(str(p)) is None
