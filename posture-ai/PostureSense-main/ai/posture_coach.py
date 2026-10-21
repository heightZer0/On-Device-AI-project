"""
Posture Coach for PostureSense
Provides intelligent, context-aware coaching feedback based on posture analysis.
"""

import time
from collections import deque
from typing import Optional

from .feature_extractor import FeatureExtractor
import config


class PostureCoach:
    """
    Analyzes posture features to give specific, actionable feedback.
    Tracks patterns over time for fatigue detection and break reminders.
    """

    def __init__(self) -> None:
        self.current_tip: str = ""
        self.current_tip_icon: str = ""
        self.tip_history: list[tuple[float, str]] = []
        self._tip_timestamps: dict[str, float] = {}  # tip_key → last shown time

        # Streak tracking
        self.good_streak_start: Optional[float] = None
        self.good_streak_duration: float = 0
        self.best_streak: float = 0
        self.last_streak_milestone: int = 0

        # Fatigue tracking
        self._posture_scores: deque = deque(maxlen=300)  # ~5 min at 1 fps
        self._session_start: float = time.time()
        self._last_break_reminder: float = time.time()

        # Celebration state
        self.celebration_text: str = ""
        self.celebration_time: float = 0

    def update(self, features, prediction: dict) -> dict:
        """
        Update coach with current frame data.

        Args:
            features: np.ndarray from FeatureExtractor
            prediction: dict from PostureClassifier.predict()

        Returns:
            dict with coaching info for the UI
        """
        now = time.time()
        label_name = prediction.get("label_name", "Unknown")

        # Track posture score for fatigue detection
        if features is not None:
            self._posture_scores.append((now, prediction.get("label", 1)))

        # Update streak
        self._update_streak(label_name, now)

        # Generate coaching tip based on features
        if features is not None and label_name in ("Fair", "Poor"):
            self._generate_tip(features, label_name, now)
        elif label_name == "Good":
            self.current_tip = ""
            self.current_tip_icon = ""

        # Check for break reminder
        self._check_break_reminder(now)

        # Fade celebration
        if self.celebration_text and (now - self.celebration_time > 5):
            self.celebration_text = ""

        return {
            "tip": self.current_tip,
            "tip_icon": self.current_tip_icon,
            "streak_seconds": int(self.good_streak_duration),
            "best_streak": int(self.best_streak),
            "celebration": self.celebration_text,
            "fatigue_level": self._get_fatigue_level(),
            "session_minutes": int((now - self._session_start) / 60),
        }

    def _update_streak(self, label_name: str, now: float) -> None:
        """Track good posture streaks."""
        if label_name == "Good":
            if self.good_streak_start is None:
                self.good_streak_start = now
            self.good_streak_duration = now - self.good_streak_start

            # Check milestones
            for milestone in config.STREAK_MILESTONES:
                if (self.good_streak_duration >= milestone and
                        self.last_streak_milestone < milestone):
                    self.last_streak_milestone = milestone
                    mins = milestone // 60
                    secs = milestone % 60
                    if mins > 0:
                        self.celebration_text = f"{mins}min perfect streak!"
                    else:
                        self.celebration_text = f"{secs}s perfect streak!"
                    self.celebration_time = now
                    break

            # Update best
            if self.good_streak_duration > self.best_streak:
                self.best_streak = self.good_streak_duration
        else:
            self.good_streak_start = None
            self.good_streak_duration = 0
            self.last_streak_milestone = 0

    def _generate_tip(self, features, severity: str, now: float) -> None:
        """Generate a specific coaching tip based on feature analysis."""
        feat = dict(zip(FeatureExtractor.FEATURE_NAMES, features))

        tips: list[tuple[str, str, str]] = []

        # ── Head position ──
        if feat["neck_inclination"] > config.THRESHOLD_NECK_INCLINATION:
            tips.append(("head_forward", "Your head is drifting forward — tuck your chin back", "neck"))
        elif feat["head_forward_offset"] > config.THRESHOLD_HEAD_FORWARD_OFFSET:
            tips.append(("head_offset", "Pull your head back over your shoulders", "neck"))

        # ── Shoulder issues ──
        if feat["shoulder_tilt"] > config.THRESHOLD_SHOULDER_TILT:
            tips.append(("shoulder_tilt", "Your shoulders are uneven — try to level them", "shoulders"))
        if feat["shoulder_elevation"] > config.THRESHOLD_SHOULDER_ELEVATION:
            tips.append(("shoulder_tension", "Your shoulders are tensing up — relax and drop them", "shoulders"))

        # ── Spine & torso ──
        if feat["torso_inclination"] > config.THRESHOLD_TORSO_INCLINATION:
            tips.append(("torso_lean", "You're leaning forward — sit back against your chair", "spine"))
        if abs(feat["lateral_lean"]) > config.THRESHOLD_LATERAL_LEAN:
            side = "right" if feat["lateral_lean"] > 0 else "left"
            tips.append(("lateral_lean", f"You're leaning to the {side} — center yourself", "spine"))
        if feat["spine_curvature"] > config.THRESHOLD_SPINE_CURVATURE:
            tips.append(("spine_curve", "Your back is rounding — straighten your spine", "spine"))

        # ── Overall slouch ──
        if feat["upper_body_compactness"] < config.THRESHOLD_UPPER_BODY_COMPACTNESS:
            tips.append(("slouch", "You're compressing down — sit up tall and lengthen your spine", "posture"))

        # ── Chin tuck ──
        if feat["chin_tuck"] < config.THRESHOLD_CHIN_TUCK:
            tips.append(("chin_tuck", "Tuck your chin slightly — imagine a string pulling you up", "neck"))

        # Select the most important tip that hasn't been shown recently
        tip_cooldown = config.TIP_COOLDOWN_SECONDS
        for tip_key, tip_text, tip_icon in tips:
            last_shown = self._tip_timestamps.get(tip_key, 0)
            if now - last_shown >= tip_cooldown:
                self.current_tip = tip_text
                self.current_tip_icon = tip_icon
                self._tip_timestamps[tip_key] = now
                self.tip_history.append((now, tip_text))
                return

        # If all tips are on cooldown, keep showing the most relevant one
        if tips:
            self.current_tip = tips[0][1]
            self.current_tip_icon = tips[0][2]

    def _check_break_reminder(self, now: float) -> None:
        """Suggest breaks after prolonged sitting."""
        break_interval = config.BREAK_REMINDER_MINUTES * 60
        if now - self._last_break_reminder >= break_interval:
            session_min = int((now - self._session_start) / 60)
            self.celebration_text = f"{session_min}min session — time for a stretch break!"
            self.celebration_time = now
            self._last_break_reminder = now

    def _get_fatigue_level(self) -> float:
        """
        Detect posture fatigue — how much posture has degraded over time.
        Returns: float 0.0 (fresh) to 1.0 (fatigued)
        """
        if len(self._posture_scores) < 30:
            return 0.0

        scores = [s[1] for s in self._posture_scores]
        n = len(scores)
        first_half = scores[:n // 2]
        second_half = scores[n // 2:]

        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)

        # Higher label = worse posture, so degradation = increase
        degradation = max(0, avg_second - avg_first)
        return min(1.0, degradation / 1.5)

    def get_session_summary(self) -> dict:
        """Get a summary of coaching tips given during the session."""
        return {
            "total_tips": len(self.tip_history),
            "best_streak_seconds": int(self.best_streak),
            "session_minutes": int((time.time() - self._session_start) / 60),
            "tips": [(t[0] - self._session_start, t[1]) for t in self.tip_history[-10:]],
        }
