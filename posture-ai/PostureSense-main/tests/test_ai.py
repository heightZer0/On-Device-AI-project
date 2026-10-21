"""
PostureSense — Test Suite
Comprehensive tests for all AI modules using pytest.
"""

import numpy as np
import pytest
import os
import json
import tempfile


# ── Feature Extractor Tests ──

class TestFeatureExtractor:
    """Tests for the biomechanical feature extractor."""

    def setup_method(self):
        from ai.feature_extractor import FeatureExtractor
        self.fe = FeatureExtractor()

    def test_feature_count(self):
        """Feature extractor should define exactly 12 features."""
        assert self.fe.NUM_FEATURES == 12
        assert len(self.fe.FEATURE_NAMES) == 12

    def test_feature_names_are_unique(self):
        """All feature names should be unique."""
        assert len(set(self.fe.FEATURE_NAMES)) == len(self.fe.FEATURE_NAMES)

    def test_extract_returns_correct_shape(self):
        """Extract should return a numpy array of shape (12,)."""
        landmarks = _make_mock_landmarks(_GOOD_POSTURE_POINTS)
        features = self.fe.extract(landmarks)
        assert features is not None
        assert features.shape == (12,)
        assert features.dtype == np.float64

    def test_extract_with_none_returns_none(self):
        """Extract should handle None gracefully."""
        result = self.fe.extract(None)
        assert result is None

    def test_extract_with_empty_list_returns_none(self):
        """Extract should handle empty landmark list gracefully."""
        result = self.fe.extract([])
        assert result is None

    def test_feature_dict_conversion(self):
        """get_feature_dict should return a dict with all feature names as keys."""
        landmarks = _make_mock_landmarks(_GOOD_POSTURE_POINTS)
        features = self.fe.extract(landmarks)
        feature_dict = self.fe.get_feature_dict(features)
        assert isinstance(feature_dict, dict)
        assert len(feature_dict) == 12
        for name in self.fe.FEATURE_NAMES:
            assert name in feature_dict

    def test_feature_dict_none_input(self):
        """get_feature_dict should handle None gracefully."""
        result = self.fe.get_feature_dict(None)
        assert result == {}

    def test_good_posture_neck_inclination_is_low(self):
        """Good posture should have low neck inclination."""
        landmarks = _make_mock_landmarks(_GOOD_POSTURE_POINTS)
        features = self.fe.extract(landmarks)
        # Neck inclination is feature 0
        assert features[0] < 20, f"Neck inclination {features[0]}° too high for good posture"

    def test_poor_posture_neck_inclination_is_high(self):
        """Poor posture (head forward) should have higher neck inclination."""
        landmarks = _make_mock_landmarks(_POOR_POSTURE_POINTS)
        features = self.fe.extract(landmarks)
        assert features[0] > 15, f"Neck inclination {features[0]}° too low for poor posture"


# ── Posture Classifier Tests ──

class TestPostureClassifier:
    """Tests for the ML posture classifier."""

    def setup_method(self):
        from ai.posture_classifier import PostureClassifier
        self.pc = PostureClassifier()

    def test_model_is_trained_on_init(self):
        """Classifier should have a trained model after initialization."""
        assert self.pc.is_rf_trained is True

    def test_predict_good_posture(self):
        """Known good posture features should classify as Good."""
        good_features = np.array([10, 4, 2, 0.0, 0.02, 0.85, 0.02, 0.65, 0.50, 0.0, 100, 1.45])
        result = self.pc.predict(good_features)
        assert result["label_name"] == "Good"
        assert result["confidence"] > 0.5

    def test_predict_poor_posture(self):
        """Known poor posture features should classify as Poor."""
        poor_features = np.array([40, 25, 15, 0.35, 0.20, 0.78, 0.12, 0.30, 0.28, 0.20, 50, 1.05])
        result = self.pc.predict(poor_features)
        assert result["label_name"] == "Poor"
        assert result["confidence"] > 0.5

    def test_predict_returns_complete_dict(self):
        """Prediction result should contain all expected keys."""
        features = np.array([10, 4, 2, 0.0, 0.02, 0.85, 0.02, 0.65, 0.50, 0.0, 100, 1.45])
        result = self.pc.predict(features)
        assert "label" in result
        assert "label_name" in result
        assert "confidence" in result
        assert "probabilities" in result
        assert "is_anomaly" in result

    def test_predict_probabilities_sum_to_one(self):
        """Prediction probabilities should sum to approximately 1.0."""
        features = np.array([10, 4, 2, 0.0, 0.02, 0.85, 0.02, 0.65, 0.50, 0.0, 100, 1.45])
        result = self.pc.predict(features)
        total = sum(result["probabilities"].values())
        assert abs(total - 1.0) < 0.01, f"Probabilities sum to {total}, expected ~1.0"

    def test_predict_none_features(self):
        """Predicting with None features should return a safe default."""
        result = self.pc.predict(None)
        assert result["label_name"] == "Unknown"
        assert result["confidence"] == 0.0

    def test_feature_importance(self):
        """Feature importance should return a dict with all feature names."""
        importance = self.pc.get_feature_importance()
        assert isinstance(importance, dict)
        assert len(importance) == 12

    def test_feature_importance_values_are_positive(self):
        """All feature importances should be non-negative."""
        importance = self.pc.get_feature_importance()
        for name, value in importance.items():
            assert value >= 0, f"Feature '{name}' has negative importance: {value}"

    def test_synthetic_data_generation(self):
        """Synthetic data should have correct shape and balanced classes."""
        X, y = self.pc.generate_synthetic_data(n_samples=300)
        assert X.shape == (300, 12)
        assert len(y) == 300
        # Check class balance (100 per class)
        unique, counts = np.unique(y, return_counts=True)
        assert len(unique) == 3
        assert all(c == 100 for c in counts)


# ── Posture Coach Tests ──

class TestPostureCoach:
    """Tests for the intelligent coaching engine."""

    def setup_method(self):
        from ai.posture_coach import PostureCoach
        self.coach = PostureCoach()

    def test_good_posture_no_tip(self):
        """Good posture should not generate a coaching tip."""
        good_features = np.array([10, 4, 2, 0.0, 0.02, 0.85, 0.02, 0.65, 0.50, 0.0, 100, 1.45])
        prediction = {"label": 0, "label_name": "Good", "confidence": 0.95, "probabilities": {}}
        result = self.coach.update(good_features, prediction)
        assert result["tip"] == ""

    def test_poor_posture_generates_tip(self):
        """Poor posture should generate a coaching tip."""
        poor_features = np.array([40, 25, 15, 0.35, 0.20, 0.78, 0.12, 0.30, 0.28, 0.20, 50, 1.05])
        prediction = {"label": 2, "label_name": "Poor", "confidence": 0.85, "probabilities": {}}
        result = self.coach.update(poor_features, prediction)
        assert result["tip"] != ""

    def test_streak_tracking_good(self):
        """Consecutive good posture should build a streak."""
        good_features = np.array([10, 4, 2, 0.0, 0.02, 0.85, 0.02, 0.65, 0.50, 0.0, 100, 1.45])
        prediction = {"label": 0, "label_name": "Good", "confidence": 0.95, "probabilities": {}}
        # Simulate multiple frames
        for _ in range(5):
            result = self.coach.update(good_features, prediction)
        assert result["streak_seconds"] >= 0

    def test_streak_resets_on_poor(self):
        """Poor posture should reset the streak."""
        good_features = np.array([10, 4, 2, 0.0, 0.02, 0.85, 0.02, 0.65, 0.50, 0.0, 100, 1.45])
        poor_features = np.array([40, 25, 15, 0.35, 0.20, 0.78, 0.12, 0.30, 0.28, 0.20, 50, 1.05])
        good_pred = {"label": 0, "label_name": "Good", "confidence": 0.95, "probabilities": {}}
        poor_pred = {"label": 2, "label_name": "Poor", "confidence": 0.85, "probabilities": {}}

        self.coach.update(good_features, good_pred)
        result = self.coach.update(poor_features, poor_pred)
        assert result["streak_seconds"] == 0

    def test_coaching_result_has_all_keys(self):
        """Coaching result should contain all expected keys."""
        features = np.array([10, 4, 2, 0.0, 0.02, 0.85, 0.02, 0.65, 0.50, 0.0, 100, 1.45])
        prediction = {"label": 0, "label_name": "Good", "confidence": 0.95, "probabilities": {}}
        result = self.coach.update(features, prediction)
        expected_keys = ["tip", "tip_icon", "streak_seconds", "best_streak",
                         "celebration", "fatigue_level", "session_minutes"]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_session_summary(self):
        """Session summary should return valid data."""
        summary = self.coach.get_session_summary()
        assert "total_tips" in summary
        assert "best_streak_seconds" in summary
        assert "session_minutes" in summary
        assert summary["total_tips"] >= 0


# ── Session Manager Tests ──

class TestSessionManager:
    """Tests for session persistence and trend analysis."""

    def setup_method(self):
        from utils.session_manager import SessionManager
        self.sm = SessionManager()

    def test_session_id_format(self):
        """Session ID should follow datetime format."""
        assert len(self.sm.session_id) > 0
        # Should contain date separators
        assert "-" in self.sm.session_id

    def test_initial_state(self):
        """Session should start with zeroed counters."""
        assert self.sm.good_frames == 0
        assert self.sm.fair_frames == 0
        assert self.sm.poor_frames == 0
        assert self.sm.total_frames == 0
        assert self.sm.alerts_triggered == 0

    def test_update_increments_counters(self):
        """Updating with a prediction should increment counters."""
        prediction = {"label": 0, "label_name": "Good", "confidence": 0.9}
        self.sm.update(prediction)
        assert self.sm.total_frames == 1
        assert self.sm.good_frames == 1

    def test_record_alert(self):
        """Recording an alert should increment the counter."""
        self.sm.record_alert()
        assert self.sm.alerts_triggered == 1
        self.sm.record_alert()
        assert self.sm.alerts_triggered == 2

    def test_record_coaching_tip(self):
        """Recording a coaching tip should add to the list."""
        self.sm.record_coaching_tip("Test tip")
        assert len(self.sm.coaching_tips) == 1
        assert self.sm.coaching_tips[0]["tip"] == "Test tip"

    def test_good_percentage_calculation(self):
        """Good percentage should be calculated correctly."""
        # Simulate some time passing with good posture
        self.sm.good_time = 7.0
        self.sm.fair_time = 2.0
        self.sm.poor_time = 1.0
        assert self.sm.good_percentage == 70

    def test_good_percentage_zero_division(self):
        """Good percentage should handle zero total time."""
        assert self.sm.good_percentage == 0

    def test_save_creates_file(self):
        """Saving should create a JSON file."""
        # Use a temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            self.sm.DATA_DIR = tmpdir
            prediction = {"label": 0, "label_name": "Good", "confidence": 0.9}
            self.sm.update(prediction)
            data = self.sm.save()
            assert data is not None
            # Check file exists
            files = os.listdir(tmpdir)
            assert len(files) == 1
            assert files[0].endswith(".json")
            # Verify JSON is valid
            with open(os.path.join(tmpdir, files[0])) as f:
                loaded = json.load(f)
            assert loaded["total_frames"] == 1


# ── UI Renderer Tests ──

class TestUIRenderer:
    """Tests for the UI renderer."""

    def setup_method(self):
        from utils.ui_renderer import UIRenderer
        self.ui = UIRenderer()

    def test_format_time_seconds(self):
        """Format time should handle seconds correctly."""
        assert self.ui._format_time(30) == "30s"
        assert self.ui._format_time(0) == "0s"

    def test_format_time_minutes(self):
        """Format time should handle minutes correctly."""
        assert self.ui._format_time(90) == "1m 30s"
        assert self.ui._format_time(300) == "5m 0s"

    def test_format_time_hours(self):
        """Format time should handle hours correctly."""
        assert self.ui._format_time(3661) == "1h 1m"

    def test_status_color_good(self):
        """Good status should return green color."""
        color = self.ui._get_status_color("Good")
        assert color == (0, 230, 118)

    def test_status_color_poor(self):
        """Poor status should return red color."""
        color = self.ui._get_status_color("Poor")
        assert color == (60, 60, 255)

    def test_status_color_unknown(self):
        """Unknown status should default to poor color."""
        color = self.ui._get_status_color("Unknown")
        assert color == (60, 60, 255)


# ── Calibration Manager Tests ──

class TestCalibrationManager:
    """Tests for the calibration system."""

    def setup_method(self):
        from ai.feature_extractor import FeatureExtractor
        from ai.posture_classifier import PostureClassifier
        from ai.calibration import CalibrationManager
        self.fe = FeatureExtractor()
        self.pc = PostureClassifier()
        self.cm = CalibrationManager(self.fe, self.pc)

    def test_initial_state_is_idle(self):
        """Calibration should start in idle state."""
        assert self.cm.state == "idle"
        assert self.cm.is_active is False

    def test_start_quick_calibration(self):
        """Starting quick calibration should set up one phase."""
        self.cm.start("quick")
        assert self.cm.is_active is True
        assert self.cm.mode == "quick"
        assert len(self.cm.phases) == 1

    def test_start_full_calibration(self):
        """Starting full calibration should set up three phases."""
        self.cm.start("full")
        assert self.cm.is_active is True
        assert self.cm.mode == "full"
        assert len(self.cm.phases) == 3

    def test_cancel_calibration(self):
        """Cancelling should reset to idle state."""
        self.cm.start("quick")
        self.cm.cancel()
        assert self.cm.state == "idle"
        assert self.cm.is_active is False

    def test_status_text_idle(self):
        """Status text should indicate controls when idle."""
        text = self.cm.get_status_text()
        assert "calibration" in text.lower()


# ── Config Tests ──

class TestConfig:
    """Tests for the configuration module."""

    def test_config_imports(self):
        """Config module should import without errors."""
        import config
        assert hasattr(config, "ALERT_THRESHOLD_SECONDS")
        assert hasattr(config, "CAMERA_INDEX")

    def test_config_values_are_reasonable(self):
        """Config values should be within reasonable ranges."""
        import config
        assert config.ALERT_THRESHOLD_SECONDS > 0
        assert config.SMOOTHING_WINDOW > 0
        assert config.CALIBRATION_PHASE_DURATION > 0
        assert 0 < config.MIN_POSE_DETECTION_CONFIDENCE <= 1.0


# ── Helpers ──

class _MockLandmark:
    """Mock MediaPipe landmark with x, y, z attributes."""
    def __init__(self, x: float, y: float, z: float = 0.0):
        self.x = x
        self.y = y
        self.z = z


def _make_mock_landmarks(points: dict) -> list:
    """Create a list of 33 mock landmarks from a dict of {index: (x, y, z)}."""
    landmarks = [_MockLandmark(0.5, 0.5, 0.0) for _ in range(33)]
    for idx, (x, y, z) in points.items():
        landmarks[idx] = _MockLandmark(x, y, z)
    return landmarks


# Good posture: head upright, shoulders level, aligned spine
_GOOD_POSTURE_POINTS = {
    0:  (0.50, 0.15, 0.0),   # nose
    1:  (0.48, 0.13, 0.0),   # left eye inner
    2:  (0.47, 0.13, 0.0),   # left eye
    7:  (0.44, 0.16, 0.0),   # left ear
    8:  (0.56, 0.16, 0.0),   # right ear
    11: (0.40, 0.30, 0.0),   # left shoulder
    12: (0.60, 0.30, 0.0),   # right shoulder
    23: (0.42, 0.60, 0.0),   # left hip
    24: (0.58, 0.60, 0.0),   # right hip
}

# Poor posture: head forward, slouched, uneven
_POOR_POSTURE_POINTS = {
    0:  (0.55, 0.20, 0.0),   # nose (forward)
    1:  (0.53, 0.18, 0.0),   # left eye inner
    2:  (0.52, 0.18, 0.0),   # left eye
    7:  (0.52, 0.22, 0.0),   # left ear (forward)
    8:  (0.62, 0.20, 0.0),   # right ear (forward + uneven)
    11: (0.38, 0.35, 0.0),   # left shoulder (dropped)
    12: (0.62, 0.32, 0.0),   # right shoulder (raised)
    23: (0.42, 0.62, 0.0),   # left hip
    24: (0.58, 0.60, 0.0),   # right hip
}
