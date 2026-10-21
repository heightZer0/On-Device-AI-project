# Changelog

All notable changes to PostureSense will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-14

### Added
- Real-time posture monitoring using MediaPipe Pose Landmarker (Tasks API)
- Random Forest classifier trained on synthetic biomechanical data
- One-Class SVM for personal calibration (anomaly detection)
- 12 scale-invariant biomechanical features for ML classification
- Quick calibration mode (15s — learn your good posture)
- Full calibration mode (45s — learn good, fair, and poor posture)
- Intelligent coaching engine with specific, actionable feedback
- Good posture streak tracking with milestone celebrations
- Fatigue detection based on posture degradation over time
- Pomodoro-style break reminders (every 25 minutes)
- Session persistence to JSON with trend analysis across sessions
- Dark-themed HUD with confidence bars, coaching panel, and stats
- Centralized configuration file (`config.py`) for all settings
- CLI arguments for camera selection, alert threshold, and more
- Cross-platform launcher script
- Comprehensive `.gitignore` for clean Git history
- MIT License
- Contributing guidelines (`CONTRIBUTING.md`)
- Proper test suite using `pytest`
- `pyproject.toml` for standard Python packaging
