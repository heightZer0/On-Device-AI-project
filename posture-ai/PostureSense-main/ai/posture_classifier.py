"""
Posture Classifier for PostureSense
Uses scikit-learn Random Forest + One-Class SVM for posture classification.
Ships with a synthetic pre-trained model; supports personalized calibration.
"""

import os
import numpy as np
import joblib
from typing import Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler

from .feature_extractor import FeatureExtractor
import config


# Class labels
LABEL_GOOD = 0
LABEL_FAIR = 1
LABEL_POOR = 2
LABEL_NAMES = {LABEL_GOOD: "Good", LABEL_FAIR: "Fair", LABEL_POOR: "Poor"}


class PostureClassifier:
    """
    ML-based posture classifier using scikit-learn.

    Two models:
    - Random Forest: Primary classifier (Good/Fair/Poor) with confidence
    - One-Class SVM: Personalization model trained on user's 'good' posture
    """

    MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
    RF_MODEL_PATH = os.path.join(MODEL_DIR, "rf_model.pkl")
    SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")
    OCSVM_MODEL_PATH = os.path.join(MODEL_DIR, "ocsvm_model.pkl")
    OCSVM_SCALER_PATH = os.path.join(MODEL_DIR, "ocsvm_scaler.pkl")

    def __init__(self) -> None:
        self.rf_model: Optional[RandomForestClassifier] = None
        self.scaler: Optional[StandardScaler] = None
        self.ocsvm_model: Optional[OneClassSVM] = None
        self.ocsvm_scaler: Optional[StandardScaler] = None
        self.is_rf_trained: bool = False
        self.is_ocsvm_trained: bool = False

        os.makedirs(self.MODEL_DIR, exist_ok=True)

        # Try to load existing models
        self._load_models()

        # If no RF model, generate synthetic data and train
        if not self.is_rf_trained:
            print("[AI] No saved model found. Training on synthetic data...")
            X, y = self.generate_synthetic_data()
            self.train_rf(X, y)
            print("[AI] Synthetic model ready.")

    # ──────────────────────────────────────────────
    # Synthetic Data Generation
    # ──────────────────────────────────────────────

    def generate_synthetic_data(self, n_samples: int = 0) -> tuple[np.ndarray, np.ndarray]:
        """
        Generate synthetic training data based on known posture biomechanics.

        Feature order matches FeatureExtractor.FEATURE_NAMES:
        0: neck_inclination       (good: ~5-15°,  poor: 25-50°)
        1: torso_inclination      (good: ~2-8°,   poor: 15-35°)
        2: shoulder_tilt          (good: ~0-5°,   poor: 8-20°)
        3: head_forward_offset    (good: ~-0.1-0.1, poor: 0.2-0.5)
        4: spine_curvature        (good: ~0-0.05, poor: 0.1-0.3)
        5: shoulder_hip_ratio     (good: ~0.7-1.0, all similar)
        6: left_right_symmetry    (good: ~0-0.05, poor: 0.08-0.2)
        7: head_vertical_offset   (good: ~0.5-0.8, poor: 0.2-0.5)
        8: shoulder_elevation     (good: ~0.4-0.6, poor: 0.2-0.4 or 0.7-0.9)
        9: lateral_lean           (good: ~-0.05-0.05, poor: 0.1-0.3)
        10: chin_tuck             (good: ~80-120°, poor: 40-75°)
        11: upper_body_compactness (good: ~1.3-1.6, poor: 1.0-1.3)
        """
        if n_samples <= 0:
            n_samples = config.SYNTHETIC_SAMPLES

        n_per_class = n_samples // 3
        rng = np.random.RandomState(config.SYNTHETIC_RANDOM_SEED)

        def _sample(means: list, stds: list, n: int) -> np.ndarray:
            return np.column_stack([
                rng.normal(m, s, n) for m, s in zip(means, stds)
            ])

        # Good posture
        good_means = [10, 4, 2, 0.0, 0.02, 0.85, 0.02, 0.65, 0.50, 0.0, 100, 1.45]
        good_stds =  [3,  2, 1.5, 0.05, 0.015, 0.08, 0.015, 0.08, 0.06, 0.025, 10, 0.08]
        X_good = _sample(good_means, good_stds, n_per_class)

        # Fair posture
        fair_means = [20, 10, 6, 0.12, 0.07, 0.82, 0.05, 0.50, 0.42, 0.06, 75, 1.25]
        fair_stds =  [4,  3, 2, 0.06, 0.03, 0.08, 0.025, 0.08, 0.07, 0.04, 10, 0.08]
        X_fair = _sample(fair_means, fair_stds, n_per_class)

        # Poor posture
        poor_means = [35, 22, 12, 0.30, 0.18, 0.80, 0.10, 0.35, 0.32, 0.15, 55, 1.10]
        poor_stds =  [6,  5, 4, 0.10, 0.06, 0.10, 0.05, 0.10, 0.10, 0.07, 12, 0.10]
        X_poor = _sample(poor_means, poor_stds, n_per_class)

        X = np.vstack([X_good, X_fair, X_poor])
        y = np.array(
            [LABEL_GOOD] * n_per_class +
            [LABEL_FAIR] * n_per_class +
            [LABEL_POOR] * n_per_class
        )

        # Shuffle
        idx = rng.permutation(len(X))
        return X[idx], y[idx]

    # ──────────────────────────────────────────────
    # Training
    # ──────────────────────────────────────────────

    def train_rf(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train the Random Forest classifier."""
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.rf_model = RandomForestClassifier(
            n_estimators=config.RF_N_ESTIMATORS,
            max_depth=config.RF_MAX_DEPTH,
            min_samples_split=config.RF_MIN_SAMPLES_SPLIT,
            min_samples_leaf=config.RF_MIN_SAMPLES_LEAF,
            random_state=config.SYNTHETIC_RANDOM_SEED,
            n_jobs=-1,
        )
        self.rf_model.fit(X_scaled, y)
        self.is_rf_trained = True
        self._save_rf()

    def train_personal(self, X_good: np.ndarray) -> bool:
        """
        Train the One-Class SVM on user's 'good posture' data for personalization.

        Args:
            X_good: Feature array from calibration (user's good posture only)
        """
        if len(X_good) < config.CALIBRATION_MIN_SAMPLES:
            print(f"[AI] Not enough calibration data. Need at least {config.CALIBRATION_MIN_SAMPLES} samples.")
            return False

        self.ocsvm_scaler = StandardScaler()
        X_scaled = self.ocsvm_scaler.fit_transform(X_good)

        self.ocsvm_model = OneClassSVM(
            kernel=config.OCSVM_KERNEL,
            gamma="scale",
            nu=config.OCSVM_NU,
        )
        self.ocsvm_model.fit(X_scaled)
        self.is_ocsvm_trained = True
        self._save_ocsvm()
        print("[AI] Personal calibration model trained successfully!")
        return True

    def retrain_rf_with_calibration(self, X_calib: np.ndarray, y_calib: np.ndarray) -> None:
        """
        Retrain RF model by combining synthetic data with user's calibration data.
        Calibration data is weighted higher for personalization.
        """
        X_synth, y_synth = self.generate_synthetic_data(n_samples=900)

        # Combine datasets — oversample calibration data for emphasis
        X_combined = np.vstack([X_synth, np.tile(X_calib, (3, 1))])
        y_combined = np.concatenate([y_synth, np.tile(y_calib, 3)])

        self.train_rf(X_combined, y_combined)
        print("[AI] Random Forest retrained with your calibration data!")

    # ──────────────────────────────────────────────
    # Prediction
    # ──────────────────────────────────────────────

    def predict(self, features: Optional[np.ndarray]) -> dict:
        """
        Predict posture class with confidence.

        Args:
            features: np.ndarray of shape (NUM_FEATURES,)

        Returns:
            dict: {
                "label": int (0=Good, 1=Fair, 2=Poor),
                "label_name": str,
                "confidence": float (0-1),
                "probabilities": dict {class_name: prob},
                "is_anomaly": bool (from One-Class SVM, if trained),
            }
        """
        if features is None or not self.is_rf_trained:
            return {
                "label": LABEL_FAIR,
                "label_name": "Unknown",
                "confidence": 0.0,
                "probabilities": {"Good": 0.33, "Fair": 0.34, "Poor": 0.33},
                "is_anomaly": False,
            }

        X = features.reshape(1, -1)
        X_scaled = self.scaler.transform(X)

        # Random Forest prediction
        label = int(self.rf_model.predict(X_scaled)[0])
        proba = self.rf_model.predict_proba(X_scaled)[0]
        confidence = float(np.max(proba))

        probabilities = {LABEL_NAMES[i]: float(proba[i]) for i in range(len(proba))}

        # One-Class SVM anomaly check (if trained)
        is_anomaly = False
        if self.is_ocsvm_trained:
            X_ocsvm = self.ocsvm_scaler.transform(X)
            ocsvm_pred = self.ocsvm_model.predict(X_ocsvm)[0]
            is_anomaly = (ocsvm_pred == -1)  # -1 = anomaly (not good posture)

            # If OCSVM says anomaly but RF says Good, bump to Fair
            if is_anomaly and label == LABEL_GOOD:
                label = LABEL_FAIR
                confidence = max(0.5, confidence * 0.7)

        return {
            "label": label,
            "label_name": LABEL_NAMES.get(label, "Unknown"),
            "confidence": confidence,
            "probabilities": probabilities,
            "is_anomaly": is_anomaly,
        }

    def get_feature_importance(self) -> dict[str, float]:
        """Get feature importance from the Random Forest model."""
        if not self.is_rf_trained:
            return {}
        importances = self.rf_model.feature_importances_
        return {
            name: float(imp)
            for name, imp in zip(FeatureExtractor.FEATURE_NAMES, importances)
        }

    # ──────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────

    def _save_rf(self) -> None:
        joblib.dump(self.rf_model, self.RF_MODEL_PATH)
        joblib.dump(self.scaler, self.SCALER_PATH)

    def _save_ocsvm(self) -> None:
        joblib.dump(self.ocsvm_model, self.OCSVM_MODEL_PATH)
        joblib.dump(self.ocsvm_scaler, self.OCSVM_SCALER_PATH)

    def _load_models(self) -> None:
        # Load Random Forest
        if os.path.exists(self.RF_MODEL_PATH) and os.path.exists(self.SCALER_PATH):
            try:
                self.rf_model = joblib.load(self.RF_MODEL_PATH)
                self.scaler = joblib.load(self.SCALER_PATH)
                self.is_rf_trained = True
                print("[AI] Random Forest model loaded.")
            except Exception as e:
                print(f"[AI] Failed to load RF model: {e}")
                print("[AI] Will retrain from synthetic data.")

        # Load One-Class SVM
        if os.path.exists(self.OCSVM_MODEL_PATH) and os.path.exists(self.OCSVM_SCALER_PATH):
            try:
                self.ocsvm_model = joblib.load(self.OCSVM_MODEL_PATH)
                self.ocsvm_scaler = joblib.load(self.OCSVM_SCALER_PATH)
                self.is_ocsvm_trained = True
                print("[AI] Personal calibration model loaded.")
            except Exception as e:
                print(f"[AI] Failed to load OCSVM model: {e}")

    def reset_personal_model(self) -> None:
        """Delete the personal calibration model."""
        self.ocsvm_model = None
        self.ocsvm_scaler = None
        self.is_ocsvm_trained = False
        for path in [self.OCSVM_MODEL_PATH, self.OCSVM_SCALER_PATH]:
            if os.path.exists(path):
                os.remove(path)
        print("[AI] Personal calibration reset.")
