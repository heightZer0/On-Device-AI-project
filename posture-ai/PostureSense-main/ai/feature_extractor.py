"""
Feature Extractor for PostureSense
Extracts ML-ready features from MediaPipe pose landmarks.
All features are scale-invariant (angles, ratios, normalized distances).

Compatible with MediaPipe Tasks API (0.10.30+).
"""

import numpy as np
from typing import Optional


# Landmark indices (matching MediaPipe PoseLandmark enum)
# These are the same indices regardless of the API version.
_NOSE = 0
_LEFT_EYE_INNER = 1
_LEFT_EYE = 2
_LEFT_EAR = 7
_RIGHT_EAR = 8
_LEFT_SHOULDER = 11
_RIGHT_SHOULDER = 12
_LEFT_HIP = 23
_RIGHT_HIP = 24


class FeatureExtractor:
    """Extracts engineered features from MediaPipe pose landmarks for ML classification."""

    # Feature names for interpretability
    FEATURE_NAMES = [
        "neck_inclination",        # 0  – angle of neck from vertical
        "torso_inclination",       # 1  – angle of torso from vertical
        "shoulder_tilt",           # 2  – tilt angle between shoulders
        "head_forward_offset",     # 3  – ear-to-shoulder horizontal ratio
        "spine_curvature",         # 4  – deviation of midpoints from straight line
        "shoulder_hip_ratio",      # 5  – shoulder width vs torso height
        "left_right_symmetry",     # 6  – symmetry between left/right shoulder-hip
        "head_vertical_offset",    # 7  – how high/low the head is relative to shoulders
        "shoulder_elevation",      # 8  – are shoulders raised/tensed
        "lateral_lean",            # 9  – left-right lean of torso
        "chin_tuck",               # 10 – chin angle relative to neck
        "upper_body_compactness",  # 11 – overall compression of upper body
    ]

    NUM_FEATURES = len(FEATURE_NAMES)

    def __init__(self) -> None:
        self._prev_features: Optional[np.ndarray] = None

    def _get_point(self, landmarks, idx: int) -> np.ndarray:
        """Get (x, y, z) for a landmark by integer index. Returns numpy array."""
        lm = landmarks[idx]
        return np.array([lm.x, lm.y, lm.z])

    def _angle_from_vertical(self, p1: np.ndarray, p2: np.ndarray) -> float:
        """Calculate the angle (degrees) of the line p1->p2 from the vertical axis."""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        angle = np.degrees(np.arctan2(abs(dx), abs(dy)))
        return float(angle)

    def _angle_between_three(self, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
        """Angle at point b formed by a-b-c (degrees)."""
        ba = a - b
        bc = c - b
        cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
        cos_angle = np.clip(cos_angle, -1.0, 1.0)
        return float(np.degrees(np.arccos(cos_angle)))

    def extract(self, landmarks) -> Optional[np.ndarray]:
        """
        Extract feature vector from MediaPipe landmarks.

        Args:
            landmarks: List of landmark objects with .x, .y, .z attributes.
                       Works with both legacy mp.solutions and new Tasks API.

        Returns:
            np.ndarray of shape (NUM_FEATURES,) or None if extraction fails
        """
        try:
            if landmarks is None or len(landmarks) == 0:
                return None

            # Key points (using integer indices for API compatibility)
            left_ear = self._get_point(landmarks, _LEFT_EAR)
            right_ear = self._get_point(landmarks, _RIGHT_EAR)
            left_shoulder = self._get_point(landmarks, _LEFT_SHOULDER)
            right_shoulder = self._get_point(landmarks, _RIGHT_SHOULDER)
            left_hip = self._get_point(landmarks, _LEFT_HIP)
            right_hip = self._get_point(landmarks, _RIGHT_HIP)
            nose = self._get_point(landmarks, _NOSE)

            # Midpoints
            ear_mid = (left_ear + right_ear) / 2
            shoulder_mid = (left_shoulder + right_shoulder) / 2
            hip_mid = (left_hip + right_hip) / 2

            # Reference length: torso height (shoulder midpoint to hip midpoint)
            torso_height = np.linalg.norm(shoulder_mid[:2] - hip_mid[:2]) + 1e-8

            # ── Feature 0: Neck inclination ──
            neck_inclination = self._angle_from_vertical(shoulder_mid, ear_mid)

            # ── Feature 1: Torso inclination ──
            torso_inclination = self._angle_from_vertical(hip_mid, shoulder_mid)

            # ── Feature 2: Shoulder tilt ──
            dy_shoulders = abs(left_shoulder[1] - right_shoulder[1])
            dx_shoulders = abs(left_shoulder[0] - right_shoulder[0]) + 1e-8
            shoulder_tilt = np.degrees(np.arctan2(dy_shoulders, dx_shoulders))

            # ── Feature 3: Head forward offset ──
            head_forward_offset = (ear_mid[0] - shoulder_mid[0]) / torso_height

            # ── Feature 4: Spine curvature ──
            line_vec = hip_mid[:2] - ear_mid[:2]
            line_len = np.linalg.norm(line_vec) + 1e-8
            point_vec = shoulder_mid[:2] - ear_mid[:2]
            cross = abs(line_vec[0] * point_vec[1] - line_vec[1] * point_vec[0])
            spine_curvature = cross / (line_len * torso_height)

            # ── Feature 5: Shoulder-hip width ratio ──
            shoulder_width = np.linalg.norm(left_shoulder[:2] - right_shoulder[:2])
            shoulder_hip_ratio = shoulder_width / torso_height

            # ── Feature 6: Left-right symmetry ──
            left_dist = np.linalg.norm(left_shoulder[:2] - left_hip[:2])
            right_dist = np.linalg.norm(right_shoulder[:2] - right_hip[:2])
            left_right_symmetry = abs(left_dist - right_dist) / torso_height

            # ── Feature 7: Head vertical offset ──
            head_vertical_offset = (shoulder_mid[1] - ear_mid[1]) / torso_height

            # ── Feature 8: Shoulder elevation ──
            neck_length = np.linalg.norm(ear_mid[:2] - shoulder_mid[:2])
            shoulder_elevation = neck_length / torso_height

            # ── Feature 9: Lateral lean ──
            lateral_lean = (shoulder_mid[0] - hip_mid[0]) / torso_height

            # ── Feature 10: Chin tuck ──
            chin_tuck = self._angle_between_three(nose, ear_mid, shoulder_mid)

            # ── Feature 11: Upper body compactness ──
            total_span = np.linalg.norm(ear_mid[:2] - hip_mid[:2])
            upper_body_compactness = total_span / torso_height

            features = np.array([
                neck_inclination,
                torso_inclination,
                shoulder_tilt,
                head_forward_offset,
                spine_curvature,
                shoulder_hip_ratio,
                left_right_symmetry,
                head_vertical_offset,
                shoulder_elevation,
                lateral_lean,
                chin_tuck,
                upper_body_compactness,
            ], dtype=np.float64)

            self._prev_features = features.copy()
            return features

        except (IndexError, TypeError, ValueError) as e:
            import logging
            logging.debug(f"Feature extraction failed: {e}")
            return None

    def get_feature_dict(self, features: Optional[np.ndarray]) -> dict[str, float]:
        """Convert feature vector to a labeled dictionary for interpretability."""
        if features is None:
            return {}
        return {name: float(val) for name, val in zip(self.FEATURE_NAMES, features)}
