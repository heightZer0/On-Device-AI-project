# Contributing to PostureSense

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/PostureSense.git
   cd PostureSense
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install pytest  # for running tests
   ```

4. **Verify everything works**
   ```bash
   pytest tests/ -v
   ```

## Project Structure

```
PostureSense/
├── ai/                          # AI & ML modules
│   ├── feature_extractor.py     # Biomechanical feature extraction
│   ├── posture_classifier.py    # Random Forest + One-Class SVM
│   ├── calibration.py           # Guided calibration system
│   └── posture_coach.py         # Coaching engine
├── utils/                       # Utility modules
│   ├── session_manager.py       # Session persistence & trends
│   └── ui_renderer.py           # OpenCV UI renderer
├── tests/                       # Test suite
│   └── test_ai.py               # AI module tests
├── data/
│   ├── models/                  # Saved ML models (auto-generated)
│   └── sessions/                # Session history (auto-generated)
├── config.py                    # All configurable settings
├── posture_monitor.py           # Main application
└── start_posture_monitor.py     # Launcher with dependency checks
```

## Making Changes

1. **Create a branch** for your feature or fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Follow existing code style**:
   - Use descriptive variable names
   - Add docstrings to all public functions and classes
   - Keep functions focused and under ~50 lines where possible
   - Add type hints to function signatures

3. **Write tests** for new functionality in the `tests/` directory

4. **Test your changes**:
   ```bash
   pytest tests/ -v
   ```

5. **Submit a Pull Request** with:
   - A clear description of the change
   - Any relevant issue numbers
   - Screenshots/GIFs for UI changes

## Areas Where Help Is Wanted

- 🖥️ **Web Dashboard** — Visualize session history with charts
- 🍎 **macOS / Linux Testing** — Verify cross-platform compatibility
- 📱 **Mobile Support** — Explore running via phone camera
- 🧪 **More Tests** — Edge cases, integration tests
- 🎨 **UI Improvements** — Better overlays, themes
- 📊 **ML Improvements** — Better features, model architectures
- 🌍 **Internationalization** — Multi-language coaching tips
- ♿ **Accessibility** — Screen reader support, audio-only mode

## Reporting Bugs

Open a GitHub Issue with:
- Python version (`python --version`)
- OS and version
- Steps to reproduce
- Error output / traceback
- Webcam model (if relevant)

## Code of Conduct

Be respectful and constructive. We're all here to learn and build cool things.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
