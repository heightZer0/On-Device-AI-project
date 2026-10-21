"""Quick verification test for all AI modules."""
import sys
import numpy as np

print("=== PostureSense - AI Module Verification ===\n")

# 1. Feature Extractor
from ai.feature_extractor import FeatureExtractor
fe = FeatureExtractor()
print(f"[OK] FeatureExtractor - {fe.NUM_FEATURES} features defined")

# 2. Posture Classifier
from ai.posture_classifier import PostureClassifier
pc = PostureClassifier()
print(f"[OK] PostureClassifier - RF trained: {pc.is_rf_trained}")

# 3. Test prediction with synthetic good posture features
good_features = np.array([10, 4, 2, 0.0, 0.02, 0.85, 0.02, 0.65, 0.50, 0.0, 100, 1.45])
result = pc.predict(good_features)
print(f"     Prediction (good posture): {result['label_name']} ({result['confidence']:.0%})")

# 4. Test prediction with synthetic poor posture features
poor_features = np.array([40, 25, 15, 0.35, 0.20, 0.78, 0.12, 0.30, 0.28, 0.20, 50, 1.05])
result2 = pc.predict(poor_features)
print(f"     Prediction (poor posture): {result2['label_name']} ({result2['confidence']:.0%})")

# 5. Feature importance
importance = pc.get_feature_importance()
top3 = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:3]
print(f"     Top 3 features: {', '.join(f'{k} ({v:.2f})' for k, v in top3)}")

# 6. Posture Coach
from ai.posture_coach import PostureCoach
coach = PostureCoach()
coaching = coach.update(poor_features, result2)
print(f"[OK] PostureCoach - tip: \"{coaching['tip']}\"")

# 7. Calibration Manager
from ai.calibration import CalibrationManager
cm = CalibrationManager(fe, pc)
print(f"[OK] CalibrationManager - modes: quick, full")

# 8. Session Manager
from utils.session_manager import SessionManager
sm = SessionManager()
sm.update(result)
sm.update(result2)
print(f"[OK] SessionManager - session: {sm.session_id}")

# 9. UI Renderer
from utils.ui_renderer import UIRenderer
ui = UIRenderer()
print(f"[OK] UIRenderer - ready")

# 10. MediaPipe Tasks API
import mediapipe as mp
from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions
print(f"[OK] MediaPipe Tasks API - v{mp.__version__}")

print(f"\n{'='*50}")
print(f"  ALL MODULES VERIFIED SUCCESSFULLY!")
print(f"  Python: {sys.version.split()[0]}")
print(f"{'='*50}")
