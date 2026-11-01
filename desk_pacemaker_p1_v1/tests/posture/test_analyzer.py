import copy
import json

import pytest
from helpers import BAD, Feeder, make_cal, obs
from posture.analyzer.analyzer import UNAVAILABLE_REASONS, PostureAnalyzer
from helpers import make_cfg


# ---------- 방향·부호 ----------
@pytest.mark.parametrize("d", [1, -1])
def test_forward_always_increases_dH(d):
    f = Feeder(cal=make_cal(d=d))
    st = f.feed(5, H=0.3, d=d)
    assert st["indicators"]["head_relative_position"]["delta"] == pytest.approx(0.3, abs=1e-6)


def test_backward_is_never_attention():
    f = Feeder()
    st = f.feed(300, H=-0.5)                          # 후방 이동(ΔH<0)을 오래 유지
    assert st["state"] == "normal"
    assert f.types() == []


# ---------- 지속 시간 ----------
def test_hold_time():
    f = Feeder()
    assert f.feed(45, H=0.3)["state"] == "normal"      # 4.4초: 미달 (내부 observing → normal 로 노출)
    assert f.types() == []
    assert f.feed(12, H=0.3)["state"] == "attention"   # 5.5초: 초과
    assert f.types("attention_started") == ["attention_started"]


def test_single_frame_does_not_alert():
    f = Feeder()
    f.feed(20, H=0.0)
    f.feed(1, H=0.9)                                   # 한 프레임 튐
    assert f.feed(20, H=0.0)["state"] == "normal"
    assert f.types() == []


# ---------- 측정 불가: 사유 ----------
def test_unavailable_reasons():
    f = Feeder()
    assert f.feed(1, **BAD)["reason"] == "invalid_geometry"
    f = Feeder()
    assert f.feed(1, detected=False)["reason"] == "ear_not_detected"
    f = Feeder()
    assert f.feed(1, xe=5.0)["reason"] == "out_of_frame"      # frame_margin 안쪽
    f = Feeder()
    f.feed(2, vs=0.1)
    assert f.a.get_state()["state"] == "normal"               # N_low_vis(3) 연속 전: 판단 보류
    assert f.feed(1, vs=0.1)["reason"] == "low_confidence"


def test_low_vis_streak_must_be_consecutive():
    f = Feeder()
    f.feed(2, vs=0.1)
    f.feed(1)                                                  # 정상 프레임이 끼면 연속이 끊김
    assert f.feed(2, vs=0.1)["state"] == "normal"


def test_not_calibrated():
    f = Feeder(cal=None)
    st = f.feed(10, H=0.5)
    assert st["state"] == "unavailable" and st["reason"] == "not_calibrated"
    assert st["indicators"] == {} and f.events == []


# ---------- 타이머 일시정지 / 초기화 / 재개 ----------
def test_timer_pauses_during_short_unavailable():
    f = Feeder()
    f.feed(31, H=0.3)                       # 주의 타이머 ≈ 3.0초
    f.feed(10, **BAD)                       # 1.0초 측정 불가 (< T_reset 3초) → 일시정지
    assert f.feed(2, H=0.3)["state"] == "unavailable"          # K_recover(3) 전
    assert f.feed(15, H=0.3)["state"] == "normal"              # 3.0 + 1.5 = 4.5 < 5
    assert f.feed(10, H=0.3)["state"] == "attention"           # 5.5 ≥ 5 (일시정지였기 때문에 이어서 누적)


def test_timer_resets_after_long_unavailable():
    f = Feeder()
    f.feed(31, H=0.3)
    f.feed(45, **BAD)                       # 4.4초 > T_reset 3초 → 초기화
    f.feed(3, H=0.3)
    assert f.feed(30, H=0.3)["state"] == "normal"              # 처음부터 다시 3초
    assert f.types("attention_started") == []
    assert f.feed(30, H=0.3)["state"] == "attention"


def test_k_recover_requires_consecutive_stable_frames():
    f = Feeder()
    f.feed(5, **BAD)
    assert f.feed(2)["state"] == "unavailable"
    f.feed(1, **BAD)                        # 연속이 끊김
    assert f.feed(2)["state"] == "unavailable"
    assert f.feed(1)["state"] == "normal"


# ---------- 이벤트 ----------
def test_attention_started_once_then_realert_then_recovered_once():
    f = Feeder()
    f.feed(60, H=0.3)
    assert f.types() == ["attention_started"]
    f.feed(200, H=0.3)                                         # 약 26초: alert_interval(20초) 경과
    assert f.types("attention_started") == ["attention_started"] * 2
    f.feed(5, H=0.0)
    assert f.types("recovered") == ["recovered"]
    f.feed(50, H=0.0)
    assert f.types("recovered") == ["recovered"]               # 1회만


def test_no_attention_event_while_unavailable():
    f = Feeder()
    f.feed(31, H=0.3)
    f.feed(80, **BAD)
    assert f.types("attention_started") == []


def test_unavailable_prolonged_once_per_episode():
    f = Feeder()
    f.feed(50, **BAD)
    assert f.types("unavailable_prolonged") == ["unavailable_prolonged"]
    f.feed(5)
    f.feed(50, **BAD)
    assert f.types("unavailable_prolonged") == ["unavailable_prolonged"] * 2


def test_recalibration_suggested_after_repeated_unavailable():
    f = Feeder(T_reset_sec=1.0)
    for i in range(2):
        f.feed(30, **BAD)
        f.feed(5)
    assert f.types("recalibration_suggested") == []
    f.feed(30, **BAD)                                          # 3번째 → 안내
    assert f.types("recalibration_suggested") == ["recalibration_suggested"]
    f.feed(5)
    f.feed(30, **BAD)
    assert len(f.types("recalibration_suggested")) == 1        # 카운터 초기화됨


def test_short_unavailable_does_not_count_for_recalibration():
    f = Feeder(T_reset_sec=1.0)
    for i in range(5):
        f.feed(5, **BAD)                                       # 0.5초 (< T_reset)
        f.feed(5)
    assert f.types("recalibration_suggested") == []


def test_recovered_after_short_unavailable_but_not_after_long():
    f = Feeder()
    f.feed(60, H=0.3)
    f.feed(10, **BAD)                                          # 짧은 측정 불가
    f.feed(5, H=0.0)
    assert f.types("recovered") == ["recovered"]

    g = Feeder()
    g.feed(60, H=0.3)
    g.feed(50, **BAD)                                          # T_reset 초과: 주의 구간 종료로 간주
    g.feed(10, H=0.0)
    assert g.types("recovered") == []
    g.feed(60, H=0.3)
    assert g.types("attention_started") == ["attention_started"] * 2


# ---------- 불변 조건 ----------
def test_calibration_values_never_change_while_monitoring():
    f = Feeder()
    before = copy.deepcopy(f.a.cal)
    f.feed(100, H=0.4)
    f.feed(20, **BAD)
    f.feed(100, H=-0.2)
    assert f.a.cal == before                                   # L_ref_fixed, side, d, H_base 불변


def test_analyzer_only_uses_given_side_observation():
    # 분석기는 Obs(고정 side 한쪽) 외에는 입력이 없다 → 반대쪽으로 대체할 방법 자체가 없다.
    f = Feeder(cal=make_cal(side="right"))
    f.feed(5, ve=0.1, vs=0.1)
    assert f.a.get_state()["landmarks_ok"]["side"] == "right"


# ---------- PostureState 스키마 / S 비노출 ----------
def test_state_schema_and_no_S_in_normal_mode():
    f = Feeder()
    for kw in (dict(H=0.0), dict(H=0.3), BAD, dict(detected=False)):
        st = f.feed(60, **kw)
        assert st["state"] in ("normal", "attention", "unavailable")      # observing 은 노출 안 함
        assert set(st) == {"state", "indicators", "landmarks_ok", "confidence",
                           "duration_sec", "reason", "updated_at"}
        if st["state"] == "unavailable":
            assert st["reason"] in UNAVAILABLE_REASONS and st["indicators"] == {}
        else:
            assert st["reason"] is None
            assert st["indicators"]["head_relative_position"]["status"] == st["state"]
        assert "shoulder_screen_shift" not in json.dumps(st) and "debug" not in st


def test_debug_mode_exposes_S_only_there():
    f = Feeder()
    f.a.debug = True
    st = f.feed(3, H=0.0)
    assert st["debug"]["validated"] is False
    assert "shoulder_screen_shift" in st["debug"]
    assert st["debug"]["shoulder_screen_shift"] == pytest.approx(0.0, abs=1e-9)


def test_S_does_not_affect_decision():
    # 어깨가 크게 움직여도(S 큼) H 가 같으면 판정은 같다.
    f = Feeder()
    f.a.debug = True
    f.feed(60, H=0.0)
    st = f.a.get_state()
    assert st["state"] == "normal" and f.types() == []


# ---------- 히스테리시스 (T_release) ----------
def test_hysteresis_keeps_attention_until_release_threshold():
    f = Feeder(T_release=0.05)
    assert f.feed(100, H=0.08)["state"] == "normal"            # 진입은 T_forward(0.10) 초과여야 함
    f.feed(60, H=0.3)
    assert f.types() == ["attention_started"]
    assert f.feed(30, H=0.08)["state"] == "attention"          # 0.05 < ΔH ≤ 0.10: 주의 유지
    assert f.types("recovered") == []
    assert f.feed(5, H=0.02)["state"] == "normal"              # ΔH ≤ T_release: 해제
    assert f.types("recovered") == ["recovered"]


def test_release_null_behaves_like_forward_threshold():
    f = Feeder(T_release=None)
    f.feed(60, H=0.3)
    assert f.feed(5, H=0.08)["state"] == "normal"              # T_forward 아래로 내려오면 바로 해제
    assert f.types("recovered") == ["recovered"]


def test_release_above_forward_is_rejected():
    with pytest.raises(ValueError):
        make_cfg(T_release=0.5)


# ---------- 실험 로그용 metrics ----------
def test_metrics_only_when_measured_and_S_not_in_normal_state():
    f = Feeder()
    f.feed(3, H=0.3)
    m = f.a.metrics()
    assert m["H"] == pytest.approx(0.3) and m["dH"] == pytest.approx(0.3) and m["S"] == pytest.approx(0.0)
    f.feed(1, **BAD)
    assert f.a.metrics() == {"H": None, "dH": None, "S": None}
    assert "shoulder_screen_shift" not in json.dumps(f.a.get_state())   # 일반 모드에는 여전히 비노출
