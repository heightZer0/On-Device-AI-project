# PostureSense — AI-Powered Posture Monitoring System

<p align="center">
  <strong>An AI system that watches your posture so you don't have to think about it — built to fix my own slouching habit while coding for hours.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12%20|%203.13-blue" alt="Python">
  <img src="https://img.shields.io/badge/ML-scikit--learn-orange" alt="scikit-learn">
  <img src="https://img.shields.io/badge/CV-MediaPipe-green" alt="MediaPipe">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">
  <img src="https://img.shields.io/badge/Status-Active-brightgreen" alt="Status">
  <img src="https://img.shields.io/badge/Built%20by-A%20fellow%20slouch-purple" alt="Personal Project">
</p>

---

## Why I Built This

Like most CS students, I spend 8–10 hours a day hunched over a laptop — coding, debugging, watching lectures, scrolling. Somewhere along the way, "sit up straight" became background noise I'd ignore within five minutes.

Sticky notes didn't work. Reminder apps that buzz every 30 minutes are annoying and get muted. What I actually needed was something that *understood* posture — not a timer that yells at me regardless of whether I'm actually slouching.

So I built **PostureSense**: a webcam-based AI that watches my posture in real-time, learns what *my* good posture looks like, and tells me specifically what's wrong — "your head is drifting forward, tuck your chin" instead of a generic beep.

This is a personal project born out of a personal problem. If it helps other laptop-hunched developers too, even better.

---

## What It Does

PostureSense uses your webcam and machine learning to monitor your sitting posture in real-time. Unlike rule-based systems, it uses **trained ML models** to understand posture and gives **specific, actionable coaching** instead of generic alerts.

### Key Features

| Feature | Description |
|---|---|
| **ML Classification** | Random Forest classifier trained on biomechanical features — not hardcoded thresholds |
| **Personal Calibration** | Learns *your* body and posture via One-Class SVM anomaly detection |
| **Intelligent Coaching** | Specific feedback like "Head drifting forward — tuck your chin" |
| **Streak Tracking** | Celebrates good posture streaks with milestone notifications |
| **Fatigue Detection** | Detects posture degradation over time and suggests breaks |
| **Session History** | Persists session data to JSON with trend analysis across sessions |
| **Enhanced UI** | Dark-themed HUD with confidence bars, coaching panel, and stats |
| **Configurable** | All thresholds and settings customizable via `config.py` |
| **CLI Arguments** | Camera selection, alert timing, sound toggle, and more |

---

## Architecture

```
PostureSense/
├── ai/                          # AI & ML modules
│   ├── feature_extractor.py     # 12 biomechanical features from landmarks
│   ├── posture_classifier.py    # Random Forest + One-Class SVM (scikit-learn)
│   ├── calibration.py           # Guided calibration system (quick & full)
│   └── posture_coach.py         # Intelligent coaching engine
├── utils/                       # Utility modules
│   ├── session_manager.py       # Session persistence & trend analysis
│   └── ui_renderer.py           # Enhanced OpenCV UI renderer (responsive)
├── tests/                       # Test suite
│   └── test_ai.py               # Comprehensive pytest tests
├── data/
│   ├── models/                  # Saved ML models (auto-generated, .gitignored)
│   └── sessions/                # Session history (auto-generated, .gitignored)
├── config.py                    # All configurable settings
├── posture_monitor.py           # Main application
├── start_posture_monitor.py     # Launcher with dependency checks
├── create_alert_sound.py        # Alert sound generator
├── pyproject.toml               # Python packaging & tool configuration
└── requirements.txt
```

---

## How the AI Works

### Feature Extraction
MediaPipe detects 33 body landmarks. From these, we compute **12 scale-invariant biomechanical features**:

- **Neck inclination** — angle of neck from vertical
- **Torso inclination** — forward lean angle
- **Shoulder tilt** — unevenness between shoulders
- **Head forward offset** — ear-to-shoulder horizontal displacement
- **Spine curvature** — deviation from a straight spine line
- **Left-right symmetry** — body symmetry ratio
- **Chin tuck angle** — chin position relative to neck
- And 5 more...

### Classification
Two scikit-learn models work together:

1. **Random Forest** (primary) — Classifies posture as Good / Fair / Poor with confidence scores
2. **One-Class SVM** (personalization) — Trained on *your* good posture during calibration, detects deviations

The system ships with a **pre-trained synthetic model**, so it works immediately — no calibration required.

### Coaching Engine
Instead of generic "Fix your posture!", the coach analyzes *which* features are off and gives targeted advice:

| What It Detects | What It Says |
|---|---|
| High neck inclination | "Your head is drifting forward — tuck your chin back" |
| Uneven shoulders | "Your shoulders are uneven — try to level them" |
| Forward torso lean | "You're leaning forward — sit back against your chair" |
| Lateral lean | "You're leaning to the right — center yourself" |
| Spine rounding | "Your back is rounding — straighten your spine" |

All coaching thresholds are configurable in `config.py`.

---

## Requirements

- **Python 3.10 to 3.13**
- **Webcam**
- Required packages (auto-installed by launcher):

```
opencv-python>=4.5.0
mediapipe>=0.10.30
numpy>=1.19.0
pygame>=2.0.0
scikit-learn>=1.3.0
joblib>=1.3.0
scipy>=1.10.0
```

---

## Installation

1. Clone or download this repository:
   ```bash
   git clone https://github.com/KDGIT005/PostureSense.git
   cd PostureSense
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. (Optional) Generate an alert sound:
   ```bash
   python create_alert_sound.py
   ```

---

## Usage

### Quick Start
```bash
python start_posture_monitor.py
```
The launcher checks your Python version, installs missing dependencies, and starts the monitor.

### Direct Start
```bash
python posture_monitor.py
```

### Command-Line Options
```bash
python posture_monitor.py --camera 1          # Use a specific webcam
python posture_monitor.py --alert-time 15     # Alert after 15s of poor posture
python posture_monitor.py --no-sound          # Disable sound alerts
python posture_monitor.py --no-mirror         # Disable horizontal mirroring
python posture_monitor.py --no-session-log    # Don't save session data
```

### Controls

| Key | Action |
|---|---|
| `Q` | Quit application |
| `C` | Quick calibration (15s — learn your good posture) |
| `F` | Full calibration (45s — learn good, fair, and poor) |
| `R` | Reset personal calibration |
| `S` | Toggle stats display |
| `H` | Toggle help overlay |
| `ESC` | Cancel calibration |

---

## Configuration

All settings can be customized in `config.py`:

- **Camera settings** — webcam index, mirroring
- **Alert settings** — threshold duration, sound toggle
- **AI settings** — confidence thresholds, smoothing window
- **Coaching thresholds** — when to trigger each type of tip
- **Calibration settings** — phase duration, countdown, min samples
- **Session tracking** — sample interval, logging toggle
- **ML hyperparameters** — Random Forest and One-Class SVM parameters

---

## Calibration

Calibration is **optional** but recommended for best results.

### Quick Calibration (Press `C`)
- Sit in your best posture for 15 seconds
- Trains a One-Class SVM to learn *your* ideal posture
- Anything deviating from your baseline is flagged

### Full Calibration (Press `F`)
- Demonstrate Good posture (15s) → Fair posture (15s) → Poor posture (15s)
- Retrains the Random Forest on your personal data
- Most accurate, fully personalized

Calibration data is saved and persists across sessions.

---

## Session Data

Sessions are automatically saved to `data/sessions/` as JSON files containing:
- Duration, posture percentages, and confidence scores
- Timeline of posture changes (sampled every 5 seconds)
- Coaching tips given during the session
- Alert count and calibration status

After multiple sessions, the system shows **trend analysis** (improving / stable / declining) — so over a few weeks, you can actually *see* if your posture is getting better.

Session logging can be disabled with `--no-session-log` or in `config.py`.

---

## Testing

Run the test suite:
```bash
pip install pytest
pytest tests/ -v
```

---

## Tech Stack

- **Computer Vision**: MediaPipe Pose Landmarker (Tasks API)
- **Machine Learning**: scikit-learn (Random Forest, One-Class SVM, StandardScaler)
- **Model Persistence**: joblib
- **UI Rendering**: OpenCV
- **Audio**: pygame
- **Data**: NumPy, SciPy

---

## Privacy

- **Camera data** is processed locally — no video leaves your machine
- **Session data** is stored locally in `data/sessions/` as JSON files
- Session files contain posture statistics and timestamps, but **no images or video**
- Session logging can be disabled via `--no-session-log` or `config.py`
- All session files are excluded from Git via `.gitignore`

---

## Roadmap / Ideas

A few things I'm considering for future iterations:
- Posture history dashboard (web-based, charts over weeks/months)
- Desk stretch reminders integrated with fatigue detection
- Multi-monitor camera angle support
- Lightweight background mode (system tray)

---

## Contributing

This started as a personal project to solve my own desk-posture problem, but contributions, issues, and ideas are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on setting up the development environment, coding style, and submitting pull requests.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
