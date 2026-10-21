"""
PostureSense — AI-Powered Posture Monitoring System
Main application module.

Uses MediaPipe Tasks API (0.10.30+) for pose detection and
scikit-learn ML models for posture classification, personal calibration,
intelligent coaching, and session tracking.

Controls:
    Q       — Quit
    C       — Quick calibration (15s, One-Class SVM)
    F       — Full calibration (45s, Random Forest retrain)
    R       — Reset personal calibration
    S       — Toggle stats display
    H       — Toggle help overlay
    ESC     — Cancel calibration
"""

import os
import sys
import cv2
import numpy as np
import time
import argparse
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
import urllib.request
from datetime import datetime
from typing import Optional

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    PoseLandmarker,
    PoseLandmarkerOptions,
    PoseLandmarksConnections,
    RunningMode,
)
from mediapipe.tasks.python.vision.drawing_utils import draw_landmarks, DrawingSpec

from ai.feature_extractor import FeatureExtractor
from ai.head_posture_detector import HeadPostureDetector
from ai.posture_classifier import PostureClassifier, LABEL_NAMES
from ai.calibration import CalibrationManager
from ai.posture_coach import PostureCoach
from utils.session_manager import SessionManager
from utils.ui_renderer import UIRenderer
import config


# ── Model download ──
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
MODEL_DIR = os.path.join(os.path.dirname(__file__), "data", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "pose_landmarker_lite.task")


def ensure_model() -> None:
    """Download the MediaPipe pose landmarker model if not present."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    if not os.path.exists(MODEL_PATH):
        print("[Init] Downloading MediaPipe Pose model (~4 MB)...")
        try:
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            print("[Init] Model downloaded successfully.")
        except Exception as e:
            print(f"[Init] ERROR: Failed to download model: {e}")
            print(f"[Init] Please download manually from:\n       {MODEL_URL}")
            print(f"[Init] And place it at: {MODEL_PATH}")
            sys.exit(1)
        # Verify the download isn't a partial file
        file_size = os.path.getsize(MODEL_PATH)
        if file_size < 100_000:  # Model should be ~4 MB
            os.remove(MODEL_PATH)
            print("[Init] ERROR: Downloaded file appears corrupt (too small). Deleted.")
            print(f"[Init] Please download manually from:\n       {MODEL_URL}")
            sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="PostureSense — AI-Powered Posture Monitoring System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Controls (while running):
  Q       Quit
  C       Quick calibration (15s)
  F       Full calibration (45s)
  R       Reset personal calibration
  S       Toggle stats display
  H       Toggle help overlay
  ESC     Cancel calibration
        """,
    )
    parser.add_argument(
        "--camera", type=int, default=config.CAMERA_INDEX,
        help=f"Webcam index (default: {config.CAMERA_INDEX})"
    )
    parser.add_argument(
        "--alert-time", type=int, default=config.ALERT_THRESHOLD_SECONDS,
        help=f"Seconds of poor posture before alert (default: {config.ALERT_THRESHOLD_SECONDS})"
    )
    parser.add_argument(
        "--no-sound", action="store_true",
        help="Disable sound alerts"
    )
    parser.add_argument(
        "--no-mirror", action="store_true",
        help="Disable horizontal mirroring of webcam feed"
    )
    parser.add_argument(
        "--no-session-log", action="store_true",
        help="Disable saving session data to disk"
    )
    return parser.parse_args()


class PostureMonitor:
    """AI-powered real-time posture monitoring system."""

    def __init__(self, args: Optional[argparse.Namespace] = None):
        print("\n=== PostureSense — AI-Powered Posture Monitor ===\n")

        self.args = args or parse_args()

        # ── Ensure model is available ──
        ensure_model()

        # ── MediaPipe Pose Landmarker (Tasks API) ──
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=config.MIN_POSE_DETECTION_CONFIDENCE,
            min_pose_presence_confidence=config.MIN_POSE_PRESENCE_CONFIDENCE,
            min_tracking_confidence=config.MIN_TRACKING_CONFIDENCE,
        )
        self.pose_landmarker = PoseLandmarker.create_from_options(options)

        # Connection set for drawing
        self.pose_connections = PoseLandmarksConnections.POSE_LANDMARKS

        # ── Webcam ──
        self.cap = cv2.VideoCapture(self.args.camera)
        if not self.cap.isOpened():
            print(f"[ERROR] Failed to open webcam (index {self.args.camera}).")
            print("  Possible fixes:")
            print("    1. Make sure your webcam is connected")
            print("    2. Close other apps using the camera")
            print("    3. Try a different camera index: --camera 1")
            sys.exit(1)

        # ── AI Modules ──
        print("[Init] Loading AI modules...")
        self.feature_extractor = FeatureExtractor()
        self.classifier = PostureClassifier()
        self.head_detector = HeadPostureDetector()
        self.calibration = CalibrationManager(self.feature_extractor, self.classifier)
        self.coach = PostureCoach()

        # ── Session & UI ──
        self.session = SessionManager()
        self.ui = UIRenderer()

        # ── Alert sound ──
        self.has_sound = False
        if not self.args.no_sound and config.ENABLE_SOUND_ALERTS and PYGAME_AVAILABLE:
            try:
                pygame.mixer.init()
                pygame.mixer.music.load("alert.wav")
                self.has_sound = True
            except Exception:
                print("[Init] No alert.wav found — running without sound alerts.")
                print("       Run 'python create_alert_sound.py' to generate one.")
        else:
            if PYGAME_AVAILABLE:
                try:
                    pygame.mixer.init()
                except Exception:
                    pass

        # ── State ──
        self.posture_status: str = "Good"
        self.poor_posture_start_time: Optional[float] = None
        self.poor_posture_duration: float = 0
        self.alert_threshold: int = self.args.alert_time
        self.mirror: bool = not self.args.no_mirror

        self.show_help: bool = False
        self.show_stats: bool = True

        # Smoothing buffer
        self._prediction_history: list = []
        self._history_length: int = config.SMOOTHING_WINDOW

        # Current prediction (for display)
        self._current_prediction: dict = {
            "label": 0, "label_name": "Good",
            "confidence": 0, "probabilities": {}, "is_anomaly": False
        }
        self._current_coaching: Optional[dict] = None

        # Frame timestamp — use real time for accurate timestamps
        self._start_time_ms: int = int(time.time() * 1000)

        print("[Init] Ready! Position yourself in front of the webcam.")
        print("[Init] Press 'H' for help, 'C' to calibrate, 'Q' to quit.\n")

    def _smooth_prediction(self, prediction: dict) -> dict:
        """Smooth predictions over a sliding window to reduce flickering."""
        self._prediction_history.append(prediction)
        if len(self._prediction_history) > self._history_length:
            self._prediction_history.pop(0)

        # Majority vote for label
        labels = [p["label"] for p in self._prediction_history]
        label_counts: dict[int, int] = {}
        for l in labels:
            label_counts[l] = label_counts.get(l, 0) + 1
        smoothed_label = max(label_counts, key=label_counts.get)

        # Average confidence
        avg_confidence = sum(p["confidence"] for p in self._prediction_history) / len(self._prediction_history)

        # Average probabilities
        avg_probs: dict[str, float] = {}
        for key in prediction.get("probabilities", {}):
            avg_probs[key] = sum(
                p.get("probabilities", {}).get(key, 0)
                for p in self._prediction_history
            ) / len(self._prediction_history)

        return {
            "label": smoothed_label,
            "label_name": LABEL_NAMES.get(smoothed_label, "Unknown"),
            "confidence": avg_confidence,
            "probabilities": avg_probs,
            "is_anomaly": prediction.get("is_anomaly", False),
        }

    def _update_posture_timing(self, label_name: str) -> None:
        """Update poor posture duration tracking."""
        now = time.time()

        if label_name == "Poor":
            if self.poor_posture_start_time is None:
                self.poor_posture_start_time = now
            self.poor_posture_duration = now - self.poor_posture_start_time
        else:
            self.poor_posture_start_time = None
            self.poor_posture_duration = 0

    def _check_alert(self) -> bool:
        """Check and trigger alert for prolonged poor posture."""
        if self.posture_status == "Poor" and self.poor_posture_duration >= self.alert_threshold:
            if self.has_sound and PYGAME_AVAILABLE and not pygame.mixer.music.get_busy():
                pygame.mixer.music.play()
            self.session.record_alert()
            return True
        return False

    def _handle_keypress(self, key: int) -> bool:
        """Handle keyboard input. Returns True if should quit."""
        if key == ord('q') or key == ord('Q'):
            return True

        elif key == ord('h') or key == ord('H'):
            self.show_help = not self.show_help

        elif key == ord('s') or key == ord('S'):
            self.show_stats = not self.show_stats

        elif key == ord('c') or key == ord('C'):
            if not self.calibration.is_active:
                self.calibration.start(CalibrationManager.MODE_QUICK)

        elif key == ord('f') or key == ord('F'):
            if not self.calibration.is_active:
                self.calibration.start(CalibrationManager.MODE_FULL)

        elif key == ord('r') or key == ord('R'):
            self.classifier.reset_personal_model()

        elif key == 27:  # ESC
            if self.calibration.is_active:
                self.calibration.cancel()

        return False

    def _draw_landmarks_on_frame(self, frame: np.ndarray, pose_landmarks, label_name: str = "Good") -> None:
        """Draw pose landmarks on the frame using the new Tasks API drawing utils."""
        color = self.ui._get_status_color(label_name)

        landmark_spec = DrawingSpec(color=color, thickness=2, circle_radius=3)
        connection_spec = DrawingSpec(color=(200, 200, 200), thickness=2, circle_radius=1)

        draw_landmarks(
            frame,
            pose_landmarks,
            self.pose_connections,
            landmark_spec,
            connection_spec,
        )

    def run(self) -> None:
        """Main application loop."""
        print("Starting Posture Monitor...")
        print("Press 'Q' to quit, 'H' for help\n")

        while self.cap.isOpened():
            success, frame = self.cap.read()
            if not success:
                print("[ERROR] Failed to read from webcam. Is it disconnected?")
                break

            # Mirror the image
            if self.mirror:
                frame = cv2.flip(frame, 1)

            # Convert to RGB for MediaPipe
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Create MediaPipe Image and detect pose — use real timestamps
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            current_timestamp_ms = int(time.time() * 1000) - self._start_time_ms
            result = self.pose_landmarker.detect_for_video(mp_image, current_timestamp_ms)

            if result.pose_landmarks and len(result.pose_landmarks) > 0:
                # Get first person's landmarks
                pose_landmarks = result.pose_landmarks[0]

                # ── Calibration mode ──
                if self.calibration.is_active:
                    calib_info = self.calibration.update(pose_landmarks)

                    # Draw landmarks even during calibration
                    self._draw_landmarks_on_frame(frame, pose_landmarks, "Good")

                    # Draw calibration overlay
                    self.ui.draw_calibration_overlay(frame, calib_info)

                    # Check if calibration just completed
                    if self.calibration.state == CalibrationManager.STATE_COMPLETE:
                        self.session.calibration_done = True
                        if not hasattr(self, '_calib_complete_time'):
                            self._calib_complete_time = time.time()
                        elif time.time() - self._calib_complete_time > 3:
                            self.calibration.state = CalibrationManager.STATE_IDLE
                            del self._calib_complete_time
                else:
                    # ── Normal operation ──

                    # Extract features
                    features = self.feature_extractor.extract(pose_landmarks)

                    if features is not None:
                        # ML prediction
                        raw_prediction = self.classifier.predict(features)
                        prediction = self._smooth_prediction(raw_prediction)
                        self._current_prediction = prediction

                        # Get posture features
                        feature_dict = self.feature_extractor.get_feature_dict(features)

                        # Right-side landmark coordinates
                        right_ear = pose_landmarks[8]
                        right_shoulder = pose_landmarks[12]

                        # Print once per second
                        if not hasattr(self, "_last_debug_time"):
                            self._last_debug_time = 0.0

                        if time.time() - self._last_debug_time >= 1.0:
                            print(
                                f"[Posture] {self.posture_status} | "
                                f"Ear: ({right_ear.x:.3f}, {right_ear.y:.3f}) | "
                                f"Shoulder: ({right_shoulder.x:.3f}, {right_shoulder.y:.3f}) | "
                                f"Neck: {feature_dict['neck_inclination']:.1f} deg | "
                                f"Head offset: {feature_dict['head_forward_offset']:.3f}"
                            )
                            self._last_debug_time = time.time()

                        # Update status
                        self.posture_status = prediction["label_name"]
                        self._update_posture_timing(self.posture_status)

                        # Head posture calibration and monitoring
                        feature_dict = self.feature_extractor.get_feature_dict(features)

                        head_result = self.head_detector.update(
                            label=self.posture_status,
                            head_offset=feature_dict["head_forward_offset"],
                            visible=(
                                pose_landmarks[7].visibility >= 0.5
                                and pose_landmarks[8].visibility >= 0.5
                                and pose_landmarks[11].visibility >= 0.5
                                and pose_landmarks[12].visibility >= 0.5
                            )
                        )

                        # Print state changes and periodic monitoring results
                        if not hasattr(self, "_last_head_status"):
                            self._last_head_status = None
                            self._last_head_print = 0.0

                        status = head_result["status"]
                        now = time.monotonic()

                        if status != self._last_head_status or now - self._last_head_print >= 2:
                            print("[Head]", head_result)
                            self._last_head_status = status
                            self._last_head_print = now
                        

                        # Coaching
                        coaching_info = self.coach.update(features, prediction)
                        self._current_coaching = coaching_info

                        # Session tracking
                        self.session.update(prediction, coaching_info)

                        # Record coaching tip if new
                        tip = coaching_info.get("tip", "")
                        if tip and (not self.session.coaching_tips or
                                    self.session.coaching_tips[-1].get("tip") != tip):
                            self.session.record_coaching_tip(tip)

                    # ── Draw UI ──

                    # Pose landmarks
                    self._draw_landmarks_on_frame(
                        frame, pose_landmarks,
                        self._current_prediction["label_name"]
                    )

                    # Top HUD
                    self.ui.draw_top_hud(frame, self._current_prediction, self._current_coaching)

                    # Coaching panel
                    if self._current_coaching:
                        self.ui.draw_coaching_panel(frame, self._current_coaching)

                    # Bottom stats
                    if self.show_stats:
                        self.ui.draw_bottom_stats(frame, self.session, self._current_coaching)

                    # Alert overlay
                    alert_active = self._check_alert()
                    if alert_active:
                        tip = self._current_coaching.get("tip", "") if self._current_coaching else ""
                        self.ui.draw_alert_overlay(frame, self.poor_posture_duration, tip)

                    # Celebration
                    if self._current_coaching:
                        celebration = self._current_coaching.get("celebration", "")
                        if celebration:
                            self.ui.draw_celebration(frame, celebration)
            else:
                # No person detected
                self.ui.draw_no_person(frame)

                # Still show bottom stats
                if self.show_stats:
                    self.ui.draw_bottom_stats(frame, self.session, self._current_coaching)

            # Help overlay (drawn last, on top of everything)
            if self.show_help:
                self.ui.draw_help_overlay(frame)

            # Display
            cv2.imshow("PostureSense", frame)

            # Handle keyboard input
            key = cv2.waitKey(5) & 0xFF
            if key != 255:  # A key was pressed
                should_quit = self._handle_keypress(key)
                if should_quit:
                    break

        # ── Cleanup ──
        self._shutdown()

    def _shutdown(self) -> None:
        """Clean up resources and save session."""
        self.pose_landmarker.close()
        self.cap.release()
        cv2.destroyAllWindows()
        if PYGAME_AVAILABLE:
            pygame.mixer.quit()

        # Save session
        self.session.print_summary()
        if not self.args.no_session_log and config.ENABLE_SESSION_LOGGING:
            self.session.save()

        # Show coaching summary
        coach_summary = self.coach.get_session_summary()
        if coach_summary["total_tips"] > 0:
            print(f"\n  Coaching tips given: {coach_summary['total_tips']}")
            print(f"  Best streak: {UIRenderer._format_time(coach_summary['best_streak_seconds'])}")

        # Show trend analysis
        trend = self.session.get_trend_analysis()
        if trend:
            print(f"\n  Overall trend: {trend['trend'].upper()}")


def main() -> None:
    """Entry point for the application."""
    args = parse_args()
    monitor = PostureMonitor(args)
    monitor.run()


if __name__ == "__main__":
    main()