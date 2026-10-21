"""
Calibration Manager for PostureSense
Guides the user through a calibration process to personalize the AI model.
"""

import time
from typing import Optional

import numpy as np

from .feature_extractor import FeatureExtractor
from .posture_classifier import PostureClassifier, LABEL_GOOD, LABEL_FAIR, LABEL_POOR
import config


class CalibrationPhase:
    """Represents a single phase in the calibration process."""

    def __init__(self, name: str, label: int, duration: int, instruction: str, color: tuple) -> None:
        self.name = name
        self.label = label
        self.duration = duration
        self.instruction = instruction
        self.color = color  # BGR
        self.samples: list[np.ndarray] = []
        self.start_time: Optional[float] = None
        self.is_complete: bool = False

    @property
    def elapsed(self) -> float:
        if self.start_time is None:
            return 0
        return time.time() - self.start_time

    @property
    def progress(self) -> float:
        return min(1.0, self.elapsed / self.duration)

    @property
    def remaining(self) -> float:
        return max(0, self.duration - self.elapsed)


class CalibrationManager:
    """
    Manages the calibration process for personalized posture detection.

    Two modes:
    - Quick: Only 'good' posture → trains One-Class SVM (~15s)
    - Full:  Good + Fair + Poor posture → retrains Random Forest (~45s)
    """

    MODE_QUICK = "quick"
    MODE_FULL = "full"

    # States
    STATE_IDLE = "idle"
    STATE_COUNTDOWN = "countdown"
    STATE_COLLECTING = "collecting"
    STATE_TRAINING = "training"
    STATE_COMPLETE = "complete"

    def __init__(self, feature_extractor: FeatureExtractor, classifier: PostureClassifier) -> None:
        self.feature_extractor = feature_extractor
        self.classifier = classifier
        self.state: str = self.STATE_IDLE
        self.mode: Optional[str] = None
        self.phases: list[CalibrationPhase] = []
        self.current_phase_idx: int = 0
        self.countdown_start: Optional[float] = None
        self.result_message: str = ""

    @property
    def is_active(self) -> bool:
        return self.state not in (self.STATE_IDLE, self.STATE_COMPLETE)

    @property
    def current_phase(self) -> Optional[CalibrationPhase]:
        if 0 <= self.current_phase_idx < len(self.phases):
            return self.phases[self.current_phase_idx]
        return None

    def start(self, mode: str = MODE_QUICK) -> None:
        """Start the calibration process."""
        self.mode = mode
        self.current_phase_idx = 0
        phase_duration = config.CALIBRATION_PHASE_DURATION

        if mode == self.MODE_QUICK:
            self.phases = [
                CalibrationPhase(
                    "Good Posture", LABEL_GOOD, phase_duration,
                    "Sit up straight in your BEST posture",
                    (0, 230, 118)  # Green
                ),
            ]
        else:  # FULL
            self.phases = [
                CalibrationPhase(
                    "Good Posture", LABEL_GOOD, phase_duration,
                    "Sit up straight in your BEST posture",
                    (0, 230, 118)  # Green
                ),
                CalibrationPhase(
                    "Fair Posture", LABEL_FAIR, phase_duration,
                    "Relax slightly — sit how you normally do",
                    (0, 180, 255)  # Orange
                ),
                CalibrationPhase(
                    "Poor Posture", LABEL_POOR, phase_duration,
                    "Slouch forward — show your WORST posture",
                    (60, 60, 255)  # Red
                ),
            ]

        self.state = self.STATE_COUNTDOWN
        self.countdown_start = time.time()
        self.result_message = ""
        print(f"\n[Calibration] Starting {mode} calibration...")

    def cancel(self) -> None:
        """Cancel calibration."""
        self.state = self.STATE_IDLE
        self.phases = []
        self.current_phase_idx = 0
        print("[Calibration] Cancelled.")

    def update(self, landmarks) -> Optional[dict]:
        """
        Update calibration with current frame landmarks.
        Call this every frame while calibration is active.

        Returns:
            dict with calibration UI info, or None if not active.
        """
        if self.state == self.STATE_IDLE or self.state == self.STATE_COMPLETE:
            return None

        phase = self.current_phase
        if phase is None:
            return None

        info = {
            "state": self.state,
            "mode": self.mode,
            "phase_name": phase.name,
            "instruction": phase.instruction,
            "color": phase.color,
            "phase_num": self.current_phase_idx + 1,
            "total_phases": len(self.phases),
            "progress": 0,
            "countdown": 0,
            "samples_collected": len(phase.samples),
            "result_message": self.result_message,
        }

        # ── Countdown state ──
        if self.state == self.STATE_COUNTDOWN:
            elapsed = time.time() - self.countdown_start
            countdown_duration = config.CALIBRATION_COUNTDOWN
            remaining = max(0, countdown_duration - elapsed)
            info["countdown"] = int(remaining) + 1

            if elapsed >= countdown_duration:
                # Start collecting
                self.state = self.STATE_COLLECTING
                phase.start_time = time.time()
                print(f"[Calibration] Collecting: {phase.name}...")

            return info

        # ── Collecting state ──
        if self.state == self.STATE_COLLECTING:
            info["progress"] = phase.progress

            # Collect features from landmarks
            if landmarks is not None:
                features = self.feature_extractor.extract(landmarks)
                if features is not None:
                    phase.samples.append(features)

            # Check if phase is complete
            if phase.elapsed >= phase.duration:
                phase.is_complete = True
                print(f"[Calibration] {phase.name}: {len(phase.samples)} samples collected.")

                # Move to next phase or finish
                self.current_phase_idx += 1
                if self.current_phase_idx >= len(self.phases):
                    self._finish_calibration()
                else:
                    self.state = self.STATE_COUNTDOWN
                    self.countdown_start = time.time()

            return info

        # ── Training state ──
        if self.state == self.STATE_TRAINING:
            info["state"] = self.STATE_TRAINING
            return info

        return info

    def _finish_calibration(self) -> None:
        """Train the model with collected calibration data."""
        self.state = self.STATE_TRAINING
        print("[Calibration] Training model with your data...")

        try:
            if self.mode == self.MODE_QUICK:
                # Train One-Class SVM with good posture data
                good_samples = np.array(self.phases[0].samples)
                success = self.classifier.train_personal(good_samples)
                if success:
                    self.result_message = f"Calibration complete! Learned from {len(good_samples)} samples."
                else:
                    self.result_message = "Not enough data collected. Please try again."
            else:
                # Train Random Forest with all phases
                X_list, y_list = [], []
                for phase in self.phases:
                    if phase.samples:
                        X_list.append(np.array(phase.samples))
                        y_list.extend([phase.label] * len(phase.samples))

                if X_list:
                    X_calib = np.vstack(X_list)
                    y_calib = np.array(y_list)
                    self.classifier.retrain_rf_with_calibration(X_calib, y_calib)

                    # Also train OCSVM on just the good data
                    good_samples = np.array(self.phases[0].samples)
                    self.classifier.train_personal(good_samples)

                    self.result_message = f"Full calibration complete! Trained on {len(X_calib)} samples."
                else:
                    self.result_message = "No data collected. Please try again."

            print(f"[Calibration] {self.result_message}")
        except Exception as e:
            self.result_message = f"Calibration failed: {str(e)}"
            print(f"[Calibration] Error: {e}")

        self.state = self.STATE_COMPLETE

    def get_status_text(self) -> str:
        """Get a human-readable status string."""
        if self.state == self.STATE_IDLE:
            return "Press 'C' for quick calibration, 'F' for full calibration"
        elif self.state == self.STATE_COMPLETE:
            return self.result_message
        elif self.state == self.STATE_TRAINING:
            return "Training AI model..."
        else:
            phase = self.current_phase
            if phase:
                return f"{phase.name}: {phase.instruction}"
            return ""
