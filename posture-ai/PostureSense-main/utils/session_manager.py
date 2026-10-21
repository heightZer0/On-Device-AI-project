"""
Session Manager for PostureSense
Persists session data to JSON files and provides trend analysis.
"""

import os
import json
import time
from datetime import datetime
from typing import Optional

import config


class SessionManager:
    """Tracks session statistics and persists them to disk."""

    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sessions")

    def __init__(self) -> None:
        os.makedirs(self.DATA_DIR, exist_ok=True)
        self.session_id: str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.start_time: float = time.time()

        # Counters
        self.good_frames: int = 0
        self.fair_frames: int = 0
        self.poor_frames: int = 0
        self.total_frames: int = 0

        # Time tracking
        self.good_time: float = 0.0
        self.fair_time: float = 0.0
        self.poor_time: float = 0.0

        self.alerts_triggered: int = 0
        self.calibration_done: bool = False
        self.confidence_sum: float = 0.0

        # Timeline (sampled at configured interval)
        self.timeline: list[dict] = []
        self._last_timeline_sample: float = 0
        self._last_update_time: float = time.time()

        # Coaching tips given
        self.coaching_tips: list[dict] = []

    @property
    def duration(self) -> float:
        return time.time() - self.start_time

    @property
    def good_percentage(self) -> int:
        total = self.good_time + self.fair_time + self.poor_time
        if total == 0:
            return 0
        return int((self.good_time / total) * 100)

    @property
    def avg_confidence(self) -> float:
        if self.total_frames == 0:
            return 0
        return self.confidence_sum / self.total_frames

    def update(self, prediction: dict, coaching_info: Optional[dict] = None) -> None:
        """
        Update session with current frame data.

        Args:
            prediction: dict from PostureClassifier.predict()
            coaching_info: dict from PostureCoach.update()
        """
        now = time.time()
        dt = now - self._last_update_time
        self._last_update_time = now

        label_name = prediction.get("label_name", "Unknown")
        confidence = prediction.get("confidence", 0)

        self.total_frames += 1
        self.confidence_sum += confidence

        if label_name == "Good":
            self.good_frames += 1
            self.good_time += dt
        elif label_name == "Fair":
            self.fair_frames += 1
            self.fair_time += dt
        else:
            self.poor_frames += 1
            self.poor_time += dt

        # Sample timeline at configured interval
        sample_interval = config.TIMELINE_SAMPLE_INTERVAL
        if now - self._last_timeline_sample >= sample_interval:
            self._last_timeline_sample = now
            self.timeline.append({
                "t": round(now - self.start_time, 1),
                "status": label_name,
                "confidence": round(confidence, 2),
            })

    def record_alert(self) -> None:
        """Record that an alert was triggered."""
        self.alerts_triggered += 1

    def record_coaching_tip(self, tip_text: str) -> None:
        """Record a coaching tip that was shown."""
        self.coaching_tips.append({
            "time": round(time.time() - self.start_time, 1),
            "tip": tip_text,
        })

    def save(self) -> dict:
        """Save session data to a JSON file."""
        data = {
            "session_id": self.session_id,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "duration_seconds": round(self.duration),
            "total_frames": self.total_frames,
            "good_posture_pct": self.good_percentage,
            "fair_posture_pct": int((self.fair_time / max(1, self.duration)) * 100),
            "poor_posture_pct": int((self.poor_time / max(1, self.duration)) * 100),
            "good_time_seconds": round(self.good_time),
            "fair_time_seconds": round(self.fair_time),
            "poor_time_seconds": round(self.poor_time),
            "alerts_triggered": self.alerts_triggered,
            "avg_confidence": round(self.avg_confidence, 3),
            "calibration_used": self.calibration_done,
            "coaching_tips_count": len(self.coaching_tips),
            "timeline": self.timeline,
            "coaching_tips": self.coaching_tips[-config.MAX_COACHING_TIPS_SAVED:],
        }

        filepath = os.path.join(self.DATA_DIR, f"session_{self.session_id}.json")
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        print(f"\n[Session] Saved to {filepath}")
        return data

    def get_trend_analysis(self) -> Optional[dict]:
        """
        Analyze past sessions for trends.

        Returns:
            dict with trend information or None if insufficient data.
        """
        if not os.path.isdir(self.DATA_DIR):
            return None

        session_files = sorted([
            f for f in os.listdir(self.DATA_DIR)
            if f.startswith("session_") and f.endswith(".json")
        ])

        if len(session_files) < 2:
            return None

        sessions: list[dict] = []
        for f in session_files[-10:]:  # Last 10 sessions
            try:
                with open(os.path.join(self.DATA_DIR, f)) as fp:
                    sessions.append(json.load(fp))
            except (json.JSONDecodeError, IOError):
                continue

        if len(sessions) < 2:
            return None

        # Calculate trends
        good_pcts = [s.get("good_posture_pct", 0) for s in sessions]
        avg_confidences = [s.get("avg_confidence", 0) for s in sessions]

        recent_avg = sum(good_pcts[-3:]) / min(3, len(good_pcts[-3:]))
        older_avg = sum(good_pcts[:-3]) / max(1, len(good_pcts[:-3])) if len(good_pcts) > 3 else good_pcts[0]

        trend = "improving" if recent_avg > older_avg + 2 else (
            "declining" if recent_avg < older_avg - 2 else "stable"
        )

        return {
            "total_sessions": len(sessions),
            "avg_good_posture_pct": round(sum(good_pcts) / len(good_pcts), 1),
            "latest_good_posture_pct": good_pcts[-1],
            "trend": trend,
            "avg_confidence": round(sum(avg_confidences) / len(avg_confidences), 3),
            "total_time_minutes": sum(s.get("duration_seconds", 0) for s in sessions) // 60,
        }

    def print_summary(self) -> None:
        """Print a formatted session summary to console."""
        duration = self.duration
        print("\n" + "=" * 50)
        print("  PostureSense — Session Summary")
        print("=" * 50)
        print(f"  Duration:         {int(duration // 60)}m {int(duration % 60)}s")
        print(f"  Good posture:     {self.good_percentage}% ({int(self.good_time)}s)")
        print(f"  Fair posture:     {int((self.fair_time / max(1, duration)) * 100)}% ({int(self.fair_time)}s)")
        print(f"  Poor posture:     {int((self.poor_time / max(1, duration)) * 100)}% ({int(self.poor_time)}s)")
        print(f"  AI confidence:    {self.avg_confidence:.1%}")
        print(f"  Alerts triggered: {self.alerts_triggered}")
        print(f"  Coaching tips:    {len(self.coaching_tips)}")
        print("=" * 50)

        # Show trend if available
        trend = self.get_trend_analysis()
        if trend:
            print(f"\n  Trend: {trend['trend'].upper()}")
            print(f"  Avg good posture: {trend['avg_good_posture_pct']}%")
            print(f"  Sessions tracked: {trend['total_sessions']}")
            print(f"  Total time:       {trend['total_time_minutes']}min")
