"""
PostureSense — Launcher Script
Checks Python version, installs dependencies, and starts the posture monitor.
"""

import os
import sys
import subprocess
import time

MIN_PYTHON_VERSION = (3, 10)
MAX_PYTHON_VERSION = (3, 14, 99)  # MediaPipe 0.10.35 supports up to 3.14.x

def check_python_version():
    """Check if the current Python version is compatible."""
    current_version = sys.version_info
    if not (MIN_PYTHON_VERSION <= current_version < MAX_PYTHON_VERSION):
        print(f"ERROR: Incompatible Python version.")
        print(f"MediaPipe (a key dependency) requires Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]} to {MAX_PYTHON_VERSION[0]}.{MAX_PYTHON_VERSION[1]}.")
        print(f"You are currently using Python {current_version.major}.{current_version.minor}.{current_version.micro}.")
        print("Please use a compatible Python version.")
        return False
    return True


def check_dependencies():
    """Check if all required dependencies are installed"""
    required_packages = [
        ("opencv-python", "cv2"),
        ("mediapipe", "mediapipe"),
        ("numpy", "numpy"),
        ("scikit-learn", "sklearn"),
        ("joblib", "joblib"),
        ("scipy", "scipy"),
    ]

    missing_packages = []

    for package_name, import_name in required_packages:
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(package_name)

    return missing_packages

def install_dependencies(packages):
    """Install missing dependencies"""
    print("Installing missing dependencies...")
    for package in packages:
        print(f"  Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("All dependencies installed successfully!\n")

def check_alert_sound():
    """Check if alert sound file exists"""
    if not os.path.exists("alert.wav"):
        print("Alert sound file not found.")
        create_sound = input("Would you like to create an alert sound? (y/n): ")
        if create_sound.lower() == 'y':
            try:
                import create_alert_sound
                create_alert_sound.generate_alert_sound()
                print("Alert sound created successfully!")
            except Exception as e:
                print(f"Error creating alert sound: {e}")
                print("The program will run without sound alerts.")
        else:
            print("The program will run without sound alerts.")

def ensure_data_dirs():
    """Create data directories if they don't exist."""
    dirs = [
        os.path.join(os.path.dirname(__file__), "data", "models"),
        os.path.join(os.path.dirname(__file__), "data", "sessions"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

def main():
    """Main function to start the posture monitor"""
    print()
    print("===================================================")
    print("|     PostureSense — AI-Powered Posture Monitor   |")
    print("===================================================")
    print("|  Powered by scikit-learn + MediaPipe            |")
    print("===================================================")
    print()

    # Check Python version first
    if not check_python_version():
        input("Press Enter to exit...")
        return

    # Check dependencies
    missing_packages = check_dependencies()
    if missing_packages:
        print(f"Missing dependencies: {', '.join(missing_packages)}")
        install = input("Would you like to install them now? (y/n): ")
        if install.lower() == 'y':
            install_dependencies(missing_packages)
        else:
            print("Cannot continue without required dependencies. Exiting...")
            return

    # Ensure data directories exist
    ensure_data_dirs()

    # Check for alert sound
    check_alert_sound()

    # Start the posture monitor
    print("\nStarting PostureSense...")
    print("Position yourself so your upper body is visible in the webcam.")
    print()
    print("Controls:")
    print("  Q  — Quit            C  — Quick Calibration")
    print("  F  — Full Calibration   H  — Help")
    print("  R  — Reset Calibration  S  — Toggle Stats")
    print()
    time.sleep(1)

    try:
        import posture_monitor
        monitor = posture_monitor.PostureMonitor()
        monitor.run()
    except Exception as e:
        print(f"\nError running posture monitor: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()