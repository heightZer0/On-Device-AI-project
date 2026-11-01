"""세션 시간 누적. 내부는 정수 ms. 같은 dt를 한 곳(add)에서만 분배 → 불변식이 구조적으로 보장된다."""
from dataclasses import dataclass


@dataclass
class SessionTracker:
    session_id: str
    started_at: str
    sitting_ms: int = 0
    monitoring_ms: int = 0
    normal_ms: int = 0
    attention_ms: int = 0
    unavailable_ms: int = 0
    warnings: int = 0

    def add(self, dt_ms, state, running):
        self.sitting_ms += dt_ms            # 일시정지·측정 불가 포함(가정)
        if not running:
            return
        self.monitoring_ms += dt_ms
        if state == "normal":
            self.normal_ms += dt_ms
        elif state == "attention":
            self.attention_ms += dt_ms
        else:                               # unavailable 및 알 수 없는 값은 측정 불가로 처리(C2-5)
            self.unavailable_ms += dt_ms

    def snapshot(self):
        m, n, a = self.monitoring_ms // 1000, self.normal_ms // 1000, self.attention_ms // 1000
        return {"sitting_sec": self.sitting_ms // 1000, "monitoring_sec": m, "normal_sec": n,
                "attention_sec": a, "unavailable_sec": m - n - a,   # 반올림 오차 보정(v10.2 S6)
                "alert_count": self.warnings}


def to_api(session_id, started_at, ended_at, snap):
    """내부 저장명(alert_count) → API명(warning_count)."""
    focus = int(snap["normal_sec"] + snap["attention_sec"])
    good = int(snap["normal_sec"])
    attention = int(snap["attention_sec"])
    unavailable = int(snap["unavailable_sec"])
    return {"session_id": session_id, "started_at": started_at, "ended_at": ended_at,
            "sitting_sec": snap["sitting_sec"], "monitoring_sec": snap["monitoring_sec"],
            "state_durations": {"normal_sec": snap["normal_sec"], "attention_sec": snap["attention_sec"],
                                "unavailable_sec": snap["unavailable_sec"]},
            "warning_count": snap["alert_count"],
            # P1 cannot distinguish absence from occlusion or out-of-frame.
            "focus_sec": focus, "good_sec": good, "attention_sec": attention,
            "unavailable_sec": unavailable,
            "posture_rate": int(good * 100 / focus) if focus else 0,
            "top_issue": "head_relative_position" if attention else None}


def row_to_api(r):
    return to_api(r["id"], r["started_at"], r["ended_at"], r)
