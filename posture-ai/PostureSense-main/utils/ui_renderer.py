"""
UI Renderer for PostureSense
Enhanced visual overlay drawn via OpenCV — dark themed HUD with confidence bars,
coaching panel, session stats, and calibration overlays.

All positions are calculated relative to frame dimensions for responsive layout.
"""

import cv2
import numpy as np
import time
import math
from typing import Optional


class UIRenderer:
    """Draws all UI elements on the camera frame."""

    # ── Color palette (BGR) ──
    BG_DARK = (30, 30, 30)
    BG_PANEL = (40, 40, 45)
    TEXT_WHITE = (240, 240, 240)
    TEXT_DIM = (160, 160, 160)
    TEXT_MUTED = (100, 100, 100)

    COLOR_GOOD = (0, 230, 118)       # Green
    COLOR_FAIR = (0, 180, 255)       # Amber/Orange
    COLOR_POOR = (60, 60, 255)       # Red
    COLOR_ACCENT = (255, 180, 50)    # Cyan-blue accent
    COLOR_CELEBRATION = (50, 220, 255)  # Gold

    FONT = cv2.FONT_HERSHEY_SIMPLEX
    FONT_BOLD = cv2.FONT_HERSHEY_DUPLEX

    def __init__(self) -> None:
        self._alert_pulse_phase: float = 0.0
        self._celebration_alpha: float = 0.0

    def _get_status_color(self, label_name: str) -> tuple:
        if label_name == "Good":
            return self.COLOR_GOOD
        elif label_name == "Fair":
            return self.COLOR_FAIR
        else:
            return self.COLOR_POOR

    def _draw_rounded_rect(self, img: np.ndarray, pt1: tuple, pt2: tuple,
                           color: tuple, thickness: int = -1,
                           radius: int = 10, alpha: float = 0.7) -> None:
        """Draw a semi-transparent rounded rectangle."""
        overlay = img.copy()
        x1, y1 = pt1
        x2, y2 = pt2

        # Draw filled rectangle (simplified — true rounded corners are expensive)
        cv2.rectangle(overlay, (x1 + radius, y1), (x2 - radius, y2), color, thickness)
        cv2.rectangle(overlay, (x1, y1 + radius), (x2, y2 - radius), color, thickness)

        # Corner circles
        cv2.circle(overlay, (x1 + radius, y1 + radius), radius, color, thickness)
        cv2.circle(overlay, (x2 - radius, y1 + radius), radius, color, thickness)
        cv2.circle(overlay, (x1 + radius, y2 - radius), radius, color, thickness)
        cv2.circle(overlay, (x2 - radius, y2 - radius), radius, color, thickness)

        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

    def _draw_progress_bar(self, img: np.ndarray, x: int, y: int,
                           width: int, height: int, progress: float,
                           color: tuple, bg_color: tuple = (60, 60, 60)) -> None:
        """Draw a progress bar with rounded ends."""
        # Background
        cv2.rectangle(img, (x, y), (x + width, y + height), bg_color, -1)
        # Fill
        fill_width = int(width * min(1.0, max(0.0, progress)))
        if fill_width > 0:
            cv2.rectangle(img, (x, y), (x + fill_width, y + height), color, -1)
        # Border
        cv2.rectangle(img, (x, y), (x + width, y + height), (80, 80, 80), 1)

    def _scale(self, value: int, frame_width: int, ref_width: int = 640) -> int:
        """Scale a pixel value relative to a reference frame width."""
        return int(value * frame_width / ref_width)

    def draw_top_hud(self, img: np.ndarray, prediction: dict, coaching_info: Optional[dict]) -> None:
        """Draw the top status bar with posture status and confidence."""
        h, w = img.shape[:2]
        hud_height = self._scale(70, w)

        label_name = prediction.get("label_name", "Unknown")
        confidence = prediction.get("confidence", 0)
        status_color = self._get_status_color(label_name)

        # Semi-transparent background
        margin = self._scale(8, w)
        self._draw_rounded_rect(img, (margin, margin), (w - margin, hud_height),
                                self.BG_DARK, radius=self._scale(12, w), alpha=0.75)

        # Status indicator dot
        dot_x = self._scale(35, w)
        dot_y = self._scale(28, w)
        cv2.circle(img, (dot_x, dot_y), self._scale(8, w), status_color, -1)
        cv2.circle(img, (dot_x, dot_y), self._scale(8, w), (255, 255, 255), 1)

        # Posture status text
        text_x = self._scale(52, w)
        font_scale = max(0.4, w / 900)
        cv2.putText(img, f"Posture: {label_name}", (text_x, self._scale(33, w)),
                    self.FONT_BOLD, font_scale * 0.7, status_color, 1, cv2.LINE_AA)

        # Confidence text
        conf_text = f"AI Confidence: {confidence:.0%}"
        cv2.putText(img, conf_text, (text_x, self._scale(58, w)),
                    self.FONT, font_scale * 0.45, self.TEXT_DIM, 1, cv2.LINE_AA)

        # Confidence bar
        bar_x = self._scale(250, w)
        bar_w = min(self._scale(200, w), w - bar_x - self._scale(80, w))
        if bar_w > self._scale(50, w):
            self._draw_progress_bar(img, bar_x, self._scale(48, w), bar_w,
                                    self._scale(12, w), confidence, status_color)

        # Streak info (right side)
        streak = coaching_info.get("streak_seconds", 0) if coaching_info else 0
        if streak > 0:
            streak_text = f"Streak: {self._format_time(streak)}"
            text_size = cv2.getTextSize(streak_text, self.FONT, font_scale * 0.5, 1)[0]
            cv2.putText(img, streak_text, (w - text_size[0] - self._scale(25, w), self._scale(33, w)),
                        self.FONT, font_scale * 0.5, self.COLOR_CELEBRATION, 1, cv2.LINE_AA)

        # Anomaly indicator
        if prediction.get("is_anomaly", False):
            cv2.putText(img, "ANOMALY", (w - self._scale(100, w), self._scale(58, w)),
                        self.FONT, font_scale * 0.4, self.COLOR_POOR, 1, cv2.LINE_AA)

    def draw_coaching_panel(self, img: np.ndarray, coaching_info: dict) -> None:
        """Draw the coaching tip panel on the right side."""
        if not coaching_info:
            return

        h, w = img.shape[:2]
        tip = coaching_info.get("tip", "")

        if not tip:
            return

        # Panel dimensions — responsive
        panel_w = min(self._scale(300, w), w // 3)
        panel_h = self._scale(80, w)
        panel_x = w - panel_w - self._scale(12, w)
        panel_y = self._scale(80, w)

        self._draw_rounded_rect(img, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h),
                                (20, 20, 50), radius=self._scale(10, w), alpha=0.8)

        # Icon area
        icon = coaching_info.get("tip_icon", "")
        icon_labels = {
            "neck": "NECK",
            "shoulders": "SHLD",
            "spine": "BACK",
            "posture": "POSE",
        }
        icon_label = icon_labels.get(icon, "TIP")

        font_scale = max(0.3, w / 1600)
        cv2.putText(img, icon_label, (panel_x + self._scale(10, w), panel_y + self._scale(22, w)),
                    self.FONT, font_scale, self.COLOR_ACCENT, 1, cv2.LINE_AA)

        # Coaching tip text (word wrap)
        self._draw_wrapped_text(img, tip, panel_x + self._scale(10, w), panel_y + self._scale(42, w),
                                panel_w - self._scale(20, w), self.FONT, font_scale, self.TEXT_WHITE)

    def draw_bottom_stats(self, img: np.ndarray, session_manager, coaching_info: Optional[dict]) -> None:
        """Draw the bottom statistics bar."""
        h, w = img.shape[:2]
        bar_height = self._scale(50, w)
        margin = self._scale(8, w)
        bar_y = h - bar_height - margin

        self._draw_rounded_rect(img, (margin, bar_y), (w - margin, h - margin),
                                self.BG_DARK, radius=self._scale(12, w), alpha=0.75)

        font_scale = max(0.3, w / 1400)

        # Session time
        duration = session_manager.duration
        time_text = f"Session: {self._format_time(duration)}"
        cv2.putText(img, time_text, (self._scale(25, w), bar_y + self._scale(22, w)),
                    self.FONT, font_scale, self.TEXT_DIM, 1, cv2.LINE_AA)

        # Good posture percentage
        good_pct = session_manager.good_percentage
        pct_color = self.COLOR_GOOD if good_pct >= 70 else (
            self.COLOR_FAIR if good_pct >= 40 else self.COLOR_POOR
        )
        pct_text = f"Good: {good_pct}%"
        col2_x = self._scale(200, w)
        cv2.putText(img, pct_text, (col2_x, bar_y + self._scale(22, w)),
                    self.FONT, font_scale, pct_color, 1, cv2.LINE_AA)

        # Good posture mini bar
        bar_start_x = self._scale(290, w)
        self._draw_progress_bar(img, bar_start_x, bar_y + self._scale(12, w),
                                self._scale(100, w), self._scale(10, w), good_pct / 100, pct_color)

        # Best streak
        best_streak = coaching_info.get("best_streak", 0) if coaching_info else 0
        if best_streak > 0:
            streak_text = f"Best: {self._format_time(best_streak)}"
            col3_x = self._scale(410, w)
            cv2.putText(img, streak_text, (col3_x, bar_y + self._scale(22, w)),
                        self.FONT, font_scale, self.TEXT_DIM, 1, cv2.LINE_AA)

        # Fatigue level
        fatigue = coaching_info.get("fatigue_level", 0) if coaching_info else 0
        if fatigue > 0.2:
            fatigue_text = f"Fatigue: {fatigue:.0%}"
            fatigue_color = self.COLOR_POOR if fatigue > 0.6 else self.COLOR_FAIR
            cv2.putText(img, fatigue_text, (w - self._scale(150, w), bar_y + self._scale(22, w)),
                        self.FONT, font_scale, fatigue_color, 1, cv2.LINE_AA)

        # Help hint
        cv2.putText(img, "C:Calibrate  Q:Quit  H:Help",
                    (self._scale(25, w), bar_y + self._scale(42, w)),
                    self.FONT, font_scale * 0.8, self.TEXT_MUTED, 1, cv2.LINE_AA)

    def draw_alert_overlay(self, img: np.ndarray, poor_duration: float, tip: str = "") -> None:
        """Draw a pulsing alert overlay for prolonged poor posture."""
        h, w = img.shape[:2]
        self._alert_pulse_phase += 0.15

        # Pulsing border
        pulse = (math.sin(self._alert_pulse_phase) + 1) / 2  # 0 to 1
        border_alpha = 0.15 + pulse * 0.25
        border_thickness = int(4 + pulse * 4)

        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), self.COLOR_POOR, border_thickness)
        cv2.addWeighted(overlay, border_alpha, img, 1 - border_alpha, 0, img)

        # Central alert box — responsive
        box_w = min(self._scale(420, w), w - 40)
        box_h = self._scale(100, w)
        box_x = (w - box_w) // 2
        box_y = (h - box_h) // 2

        self._draw_rounded_rect(img, (box_x, box_y), (box_x + box_w, box_y + box_h),
                                (30, 20, 80), radius=self._scale(15, w), alpha=0.85)

        font_scale = max(0.4, w / 900)

        # Alert icon and text
        cv2.putText(img, "! FIX YOUR POSTURE", (box_x + 20, box_y + self._scale(35, w)),
                    self.FONT_BOLD, font_scale * 0.75, self.COLOR_POOR, 1, cv2.LINE_AA)

        duration_text = f"Poor posture for {int(poor_duration)}s"
        cv2.putText(img, duration_text, (box_x + 20, box_y + self._scale(60, w)),
                    self.FONT, font_scale * 0.5, self.TEXT_DIM, 1, cv2.LINE_AA)

        if tip:
            cv2.putText(img, tip, (box_x + 20, box_y + self._scale(85, w)),
                        self.FONT, font_scale * 0.42, self.COLOR_ACCENT, 1, cv2.LINE_AA)

    def draw_celebration(self, img: np.ndarray, text: str) -> None:
        """Draw a celebration banner for streaks and milestones."""
        if not text:
            return

        h, w = img.shape[:2]
        font_scale = max(0.5, w / 800)
        text_size = cv2.getTextSize(text, self.FONT_BOLD, font_scale * 0.8, 2)[0]
        text_x = (w - text_size[0]) // 2
        text_y = h // 3

        # Glowing background
        pad = 20
        self._draw_rounded_rect(
            img,
            (text_x - pad, text_y - text_size[1] - pad),
            (text_x + text_size[0] + pad, text_y + pad),
            (20, 60, 40), radius=15, alpha=0.8
        )

        cv2.putText(img, text, (text_x, text_y),
                    self.FONT_BOLD, font_scale * 0.8, self.COLOR_CELEBRATION, 2, cv2.LINE_AA)

    def draw_calibration_overlay(self, img: np.ndarray, calib_info: Optional[dict]) -> None:
        """Draw the calibration UI overlay."""
        if not calib_info:
            return

        h, w = img.shape[:2]
        state = calib_info.get("state", "")

        # Full-screen semi-transparent overlay
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.4, img, 0.6, 0, img)

        # Central panel — responsive
        panel_w = min(self._scale(500, w), w - 40)
        panel_h = self._scale(250, w)
        px = (w - panel_w) // 2
        py = (h - panel_h) // 2

        color = calib_info.get("color", self.COLOR_ACCENT)
        self._draw_rounded_rect(img, (px, py), (px + panel_w, py + panel_h),
                                self.BG_PANEL, radius=self._scale(20, w), alpha=0.9)

        # Border accent
        cv2.rectangle(img, (px + 2, py + 2), (px + panel_w - 2, py + panel_h - 2), color, 2)

        font_scale = max(0.4, w / 1000)

        # Title
        phase_num = calib_info.get("phase_num", 1)
        total = calib_info.get("total_phases", 1)
        mode_label = "QUICK" if calib_info.get("mode") == "quick" else "FULL"
        title = f"CALIBRATION ({mode_label}) — Step {phase_num}/{total}"
        cv2.putText(img, title, (px + 20, py + self._scale(35, w)),
                    self.FONT_BOLD, font_scale * 0.6, color, 1, cv2.LINE_AA)

        # Phase name
        phase_name = calib_info.get("phase_name", "")
        cv2.putText(img, phase_name, (px + 20, py + self._scale(70, w)),
                    self.FONT_BOLD, font_scale * 0.8, self.TEXT_WHITE, 1, cv2.LINE_AA)

        # Instruction
        instruction = calib_info.get("instruction", "")
        cv2.putText(img, instruction, (px + 20, py + self._scale(105, w)),
                    self.FONT, font_scale * 0.5, self.TEXT_DIM, 1, cv2.LINE_AA)

        if state == "countdown":
            # Big countdown number
            countdown = calib_info.get("countdown", 0)
            count_text = str(countdown)
            text_size = cv2.getTextSize(count_text, self.FONT_BOLD, 3, 3)[0]
            cx = px + (panel_w - text_size[0]) // 2
            cy = py + self._scale(190, w)
            cv2.putText(img, count_text, (cx, cy),
                        self.FONT_BOLD, 3, color, 3, cv2.LINE_AA)

        elif state == "collecting":
            # Progress bar
            progress = calib_info.get("progress", 0)
            bar_y = py + self._scale(140, w)
            self._draw_progress_bar(img, px + 20, bar_y, panel_w - 40, 20, progress, color)

            # Percentage
            pct_text = f"{int(progress * 100)}%"
            cv2.putText(img, pct_text, (px + panel_w // 2 - 20, bar_y + 50),
                        self.FONT_BOLD, font_scale * 0.7, color, 1, cv2.LINE_AA)

            # Samples collected
            samples = calib_info.get("samples_collected", 0)
            cv2.putText(img, f"{samples} samples collected", (px + 20, bar_y + 50),
                        self.FONT, font_scale * 0.4, self.TEXT_DIM, 1, cv2.LINE_AA)

        elif state == "training":
            cv2.putText(img, "Training AI model...", (px + 20, py + self._scale(160, w)),
                        self.FONT_BOLD, font_scale * 0.7, self.COLOR_ACCENT, 1, cv2.LINE_AA)

        elif state == "complete":
            result = calib_info.get("result_message", "")
            self._draw_wrapped_text(img, result, px + 20, py + self._scale(150, w),
                                    panel_w - 40, self.FONT, font_scale * 0.5, self.COLOR_GOOD)

        # Cancel hint
        cv2.putText(img, "Press ESC to cancel", (px + 20, py + panel_h - 15),
                    self.FONT, font_scale * 0.35, self.TEXT_MUTED, 1, cv2.LINE_AA)

    def draw_help_overlay(self, img: np.ndarray) -> None:
        """Draw the help/controls overlay."""
        h, w = img.shape[:2]

        # Darken background
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)

        panel_w = min(self._scale(400, w), w - 40)
        panel_h = self._scale(320, w)
        px = (w - panel_w) // 2
        py = (h - panel_h) // 2

        self._draw_rounded_rect(img, (px, py), (px + panel_w, py + panel_h),
                                self.BG_PANEL, radius=self._scale(20, w), alpha=0.92)

        font_scale = max(0.35, w / 1400)

        cv2.putText(img, "PostureSense — Controls", (px + 20, py + self._scale(35, w)),
                    self.FONT_BOLD, font_scale * 1.2, self.COLOR_ACCENT, 1, cv2.LINE_AA)

        controls = [
            ("Q", "Quit application"),
            ("C", "Quick calibration (15s)"),
            ("F", "Full calibration (45s)"),
            ("R", "Reset personal calibration"),
            ("S", "Toggle stats display"),
            ("H", "Toggle this help menu"),
            ("ESC", "Cancel calibration"),
        ]

        y_start = py + self._scale(70, w)
        row_height = self._scale(32, w)
        for i, (key, desc) in enumerate(controls):
            y = y_start + i * row_height

            # Key badge
            badge_w = self._scale(40, w)
            cv2.rectangle(img, (px + 25, y - 15), (px + 25 + badge_w, y + 5), (60, 60, 70), -1)
            cv2.putText(img, key, (px + 30, y),
                        self.FONT_BOLD, font_scale, self.COLOR_ACCENT, 1, cv2.LINE_AA)

            # Description
            cv2.putText(img, desc, (px + 35 + badge_w, y),
                        self.FONT, font_scale, self.TEXT_WHITE, 1, cv2.LINE_AA)

        cv2.putText(img, "Press H to close", (px + 20, py + panel_h - 15),
                    self.FONT, font_scale * 0.7, self.TEXT_MUTED, 1, cv2.LINE_AA)

    def draw_no_person(self, img: np.ndarray) -> None:
        """Draw 'no person detected' message."""
        h, w = img.shape[:2]
        font_scale = max(0.5, w / 800)
        text = "No person detected"
        text_size = cv2.getTextSize(text, self.FONT_BOLD, font_scale * 0.8, 1)[0]
        tx = (w - text_size[0]) // 2
        ty = h // 2

        self._draw_rounded_rect(img, (tx - 20, ty - 30), (tx + text_size[0] + 20, ty + 15),
                                self.BG_DARK, radius=12, alpha=0.8)
        cv2.putText(img, text, (tx, ty),
                    self.FONT_BOLD, font_scale * 0.8, self.COLOR_FAIR, 1, cv2.LINE_AA)


    # ── Helpers ──

    def _draw_wrapped_text(self, img: np.ndarray, text: str, x: int, y: int,
                           max_width: int, font: int, scale: float, color: tuple) -> None:
        """Draw text with word wrapping."""
        words = text.split()
        line = ""
        line_y = y

        for word in words:
            test_line = f"{line} {word}".strip()
            text_size = cv2.getTextSize(test_line, font, scale, 1)[0]

            if text_size[0] > max_width and line:
                cv2.putText(img, line, (x, line_y), font, scale, color, 1, cv2.LINE_AA)
                line = word
                line_y += int(text_size[1] * 1.8)
            else:
                line = test_line

        if line:
            cv2.putText(img, line, (x, line_y), font, scale, color, 1, cv2.LINE_AA)

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds into a human-readable string."""
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
