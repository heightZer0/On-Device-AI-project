"""
PostureSense — Configuration
All user-configurable settings in one place.
Edit this file to customize thresholds, timings, and behavior.
"""


# ── Camera Settings ──
CAMERA_INDEX = 0                    # Webcam index (0 = default, 1 = external, etc.)
MIRROR_FRAME = True                 # Mirror the webcam feed horizontally

# ── Alert Settings ──
ALERT_THRESHOLD_SECONDS = 10       # Seconds of poor posture before triggering an alert
ENABLE_SOUND_ALERTS = True         # Play alert.wav when poor posture is detected

# ── AI / Classification ──
SMOOTHING_WINDOW = 8               # Number of frames to average for prediction smoothing
MIN_POSE_DETECTION_CONFIDENCE = 0.5
MIN_POSE_PRESENCE_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5

# ── Coaching ──
TIP_COOLDOWN_SECONDS = 30          # Minimum seconds between repeating the same tip
BREAK_REMINDER_MINUTES = 25        # Suggest a break after this many minutes (Pomodoro-style)

# Coaching thresholds — adjust these if tips trigger too early or too late
THRESHOLD_NECK_INCLINATION = 25    # Degrees — triggers "head drifting forward" tip
THRESHOLD_HEAD_FORWARD_OFFSET = 0.15  # Ratio — triggers "pull head back" tip
THRESHOLD_SHOULDER_TILT = 8       # Degrees — triggers "uneven shoulders" tip
THRESHOLD_SHOULDER_ELEVATION = 0.65  # Ratio — triggers "shoulders tensing" tip
THRESHOLD_TORSO_INCLINATION = 15   # Degrees — triggers "leaning forward" tip
THRESHOLD_LATERAL_LEAN = 0.10      # Ratio — triggers "leaning to the side" tip
THRESHOLD_SPINE_CURVATURE = 0.10   # Ratio — triggers "back rounding" tip
THRESHOLD_UPPER_BODY_COMPACTNESS = 1.2  # Ratio — triggers "slouching" tip
THRESHOLD_CHIN_TUCK = 65          # Degrees — triggers "chin tuck" tip

# ── Streak Milestones (seconds) ──
STREAK_MILESTONES = [60, 300, 600, 900, 1800]  # 1m, 5m, 10m, 15m, 30m

# ── Calibration ──
CALIBRATION_PHASE_DURATION = 15    # Seconds per calibration phase
CALIBRATION_COUNTDOWN = 3         # Countdown seconds before each phase
CALIBRATION_MIN_SAMPLES = 10      # Minimum samples needed for valid calibration

# ── Session Tracking ──
TIMELINE_SAMPLE_INTERVAL = 5      # Seconds between timeline data points
ENABLE_SESSION_LOGGING = True     # Save session data to data/sessions/
MAX_COACHING_TIPS_SAVED = 20      # Max tips to save per session

# ── Synthetic Training Data ──
SYNTHETIC_SAMPLES = 1500          # Number of synthetic training samples
SYNTHETIC_RANDOM_SEED = 42        # Random seed for reproducibility

# ── Random Forest Hyperparameters ──
RF_N_ESTIMATORS = 100
RF_MAX_DEPTH = 12
RF_MIN_SAMPLES_SPLIT = 5
RF_MIN_SAMPLES_LEAF = 2

# ── One-Class SVM ──
OCSVM_KERNEL = "rbf"
OCSVM_NU = 0.1                   # Expected fraction of outliers
