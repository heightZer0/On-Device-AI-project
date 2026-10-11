"""
자세 상태 판정 (순수 로직: 카메라·MediaPipe 의존 없음, 명세 P1-5~P1-7).

- 고정된 side 의 귀·어깨만 쓴다. 반대쪽으로 대체하지 않는다. (C2-1, C2-5)
- 판정 지표는 H 하나. 부호 있는 비교(ΔH > T_forward)만 쓴다. 절댓값 금지. (C2-2, C2-3)
- 기준값(cal)은 모니터링 중 바꾸지 않는다. (C2-4)
- S(어깨 화면 이동량)는 debug 모드의 get_state()에만 노출하고 판정·이벤트에는 쓰지 않는다. (C2-2)
- 한 프레임으로 경고하지 않는다: 신뢰도 연속 프레임 + 지속 시간. (C2-6)
"""
import collections
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

UNAVAILABLE_REASONS = (
    "low_confidence", "occluded", "out_of_frame", "ear_not_detected",
    "shoulder_not_detected", "invalid_geometry", "not_calibrated",
)


@dataclass
class Obs:
    """고정된 side 한쪽의 귀·어깨 관측값 (픽셀 좌표)."""
    ts: float
    detected: bool = False
    xe: float = 0.0
    ye: float = 0.0
    xs: float = 0.0
    ys: float = 0.0
    ve: float = 0.0
    vs: float = 0.0
    width: int = 0
    height: int = 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class PostureAnalyzer:
    def __init__(self, cfg, calibration: Optional[dict] = None,
                 emit: Optional[Callable[[dict], None]] = None):
        self.cfg = cfg
        self._emit = emit or (lambda ev: None)
        self.debug = False
        self.cal = None
        self.set_calibration(calibration)

    # ---------- 설정 ----------
    def set_calibration(self, cal: Optional[dict]):
        self.cal = dict(cal) if cal else None
        self.reset()

    def reset(self):
        """런타임 타이머·상태 초기화 (기준값은 유지)."""
        self.state = "normal" if self.cal else "unavailable"
        self.reason = None if self.cal else "not_calibrated"
        self._hist = collections.deque(maxlen=max(1, self.cfg.smooth_window))
        self._fwd_t = 0.0
        self._unavail_t = 0.0
        self._stable = 0
        self._low_run = 0
        self._attention_active = False   # attention_started 를 낸 뒤 recovered 전까지 True
        self._last_alert_ts = 0.0
        self._prolonged_sent = False
        self._crossed_reset = False
        self._episodes = collections.deque()
        self._last_ts = None
        self._last_obs = None
        self._state_since = None
        self._dH = 0.0
        self._H = None
        self._S = None
        self._measured = False
        self._updated_at = _now_iso()

    # ---------- 입력 ----------
    def update(self, obs: Obs):
        dt = 0.0 if self._last_ts is None else max(0.0, min(obs.ts - self._last_ts, self.cfg.max_dt_sec))
        self._last_ts = obs.ts
        self._last_obs = obs
        self._updated_at = _now_iso()
        self._measured = False
        if self.cal is None:
            self._set_state("unavailable", "not_calibrated", obs.ts)
            return
        reason = self._check(obs)
        if reason == "pending":          # 신뢰도 저하가 N_low_vis 연속 전: 판단 보류
            self._stable = 0
            return
        if reason:
            self._on_unavailable(obs, reason, dt)
        else:
            self._on_measured(obs, dt)

    # ---------- 측정 불가 판정 (P1-6) ----------
    def _check(self, obs: Obs) -> Optional[str]:
        cfg = self.cfg
        if not obs.detected:
            self._low_run = 0
            return "ear_not_detected"    # 가정: 사람/랜드마크 미검출은 ear_not_detected 로 표시
        if obs.ve < cfg.T_vis or obs.vs < cfg.T_vis:
            self._low_run += 1
            return "low_confidence" if self._low_run >= cfg.N_low_vis else "pending"
        self._low_run = 0
        mx, my = cfg.frame_margin * obs.width, cfg.frame_margin * obs.height
        for x, y in ((obs.xe, obs.ye), (obs.xs, obs.ys)):
            if not (mx <= x <= obs.width - mx and my <= y <= obs.height - my):
                return "out_of_frame"
        if obs.ye > obs.ys:              # 귀가 어깨보다 아래(이미지 y 는 아래로 증가)
            return "invalid_geometry"
        # occluded(가림) 는 판별 방법이 명세에 TBD 라서 구현하지 않음 (C9)
        return None

    def _on_unavailable(self, obs: Obs, reason: str, dt: float):
        cfg = self.cfg
        if self.state != "unavailable":              # 새 측정 불가 구간 시작
            self._unavail_t = 0.0
            self._prolonged_sent = False
            self._crossed_reset = False
            self._hist.clear()
        self._stable = 0
        self._unavail_t += dt
        self._set_state("unavailable", reason, obs.ts)
        # 측정 불가 중에는 주의 타이머를 증가시키지 않는다(=일시정지). T_reset 초과 시 초기화.
        if self._unavail_t > cfg.T_reset_sec and not self._crossed_reset:
            self._crossed_reset = True
            self._fwd_t = 0.0
            self._attention_active = False           # 주의 구간 종료로 간주 (recovered 안 냄)
            self._record_episode(obs.ts)
        if self._unavail_t >= cfg.unavailable_prolonged_sec and not self._prolonged_sent:
            self._prolonged_sent = True
            self._event("unavailable_prolonged", None)

    def _record_episode(self, ts: float):
        cfg, q = self.cfg, self._episodes
        q.append(ts)
        while q and ts - q[0] > cfg.recalib_window_sec:
            q.popleft()
        if len(q) >= cfg.recalib_suggest_count:
            q.clear()
            self._event("recalibration_suggested", None)   # 안내만. 자동 재캘리브레이션 금지

    # ---------- 정상 측정 ----------
    def _on_measured(self, obs: Obs, dt: float):
        cfg, cal = self.cfg, self.cal
        self._stable += 1
        if self.state == "unavailable" and self._stable < cfg.K_recover:
            return                                    # 연속 안정 K_recover 프레임 전에는 재개하지 않음
        H = cal["d"] * (obs.xe - obs.xs) / cal["L_ref_fixed"]     # L_ref_fixed 재계산 없음
        self._hist.append(H - cal["H_base"])
        dH = statistics.median(self._hist)
        self._dH, self._H, self._measured = dH, H, True
        # S 는 로그/검증 전용: 판정·이벤트에 쓰지 않고, 일반 모드 get_state() 에도 넣지 않는다.
        self._S = cal["d"] * (obs.xs - cal["x_shoulder_base"]) / cal["L_ref_fixed"]
        # 히스테리시스: 주의 진입은 T_forward, 주의 해제는 T_release (null 이면 T_forward 와 동일)
        release = cfg.T_forward if cfg.T_release is None else cfg.T_release
        threshold = release if self.state == "attention" else cfg.T_forward
        if dH > threshold:                            # 부호 있는 비교 (후방 이동은 주의 아님)
            self._fwd_t += dt
        else:
            self._fwd_t = 0.0
        new_state = "attention" if self._fwd_t >= cfg.T_hold_sec else "normal"
        self._set_state(new_state, None, obs.ts)
        if new_state == "attention":
            if not self._attention_active:
                self._attention_active = True
                self._last_alert_ts = obs.ts
                self._event("attention_started", dH)
            elif obs.ts - self._last_alert_ts >= cfg.alert_interval_sec:
                self._last_alert_ts = obs.ts
                self._event("attention_started", dH)   # 재알림
        elif self._attention_active:
            self._attention_active = False
            self._event("recovered", dH)

    # ---------- 출력 ----------
    def _set_state(self, state: str, reason: Optional[str], ts: float):
        if state != self.state or self._state_since is None:
            self._state_since = ts
        self.state, self.reason = state, reason

    def _event(self, etype: str, delta: Optional[float]):
        self._emit({"type": etype, "ts": _now_iso(),
                    "delta": None if delta is None else round(float(delta), 4)})

    def metrics(self) -> dict:
        """실험 로그용. 마지막 update 가 정상 측정이었을 때만 값이 있다. (S 는 로그 전용)"""
        if not self._measured:
            return {"H": None, "dH": None, "S": None}
        return {"H": self._H, "dH": self._dH, "S": self._S}

    def get_state(self) -> dict:
        """PostureState (C6). 내부 전용 observing 은 normal 로 노출된다."""
        cfg, o = self.cfg, self._last_obs
        unavailable = self.state == "unavailable"
        ear_ok = bool(o and o.detected and o.ve >= cfg.T_vis)
        sh_ok = bool(o and o.detected and o.vs >= cfg.T_vis)
        dur = 0
        if o is not None and self._state_since is not None:
            dur = int(max(0.0, o.ts - self._state_since))
        st = {
            "state": self.state,
            "indicators": {} if unavailable else
            {"head_relative_position": {"delta": round(self._dH, 4), "status": self.state}},
            "landmarks_ok": {"ear": ear_ok, "shoulder": sh_ok, "side": self.cal["side"] if self.cal else None},
            "confidence": round(min(o.ve, o.vs), 3) if (o and o.detected) else 0.0,
            "duration_sec": dur,       # 가정: 현재 상태가 유지된 시간
            "reason": self.reason if unavailable else None,
            "updated_at": self._updated_at,
        }
        if self.debug:
            st["debug"] = {"shoulder_screen_shift": self._S, "validated": False}
        return st
