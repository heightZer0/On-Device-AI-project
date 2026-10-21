
import time
from collections import deque
from statistics import mean, pstdev


class HeadPostureDetector:
    def __init__(self):
        self.baseline = None
        self.good_start = None
        self.samples = []
        self.history = deque(maxlen=10)

        # Temporary experimental threshold
        self.threshold = 0.10

    def update(self, label, head_offset, visible=True):
        now = time.monotonic()

        if not visible:
            self.good_start = None
            self.samples.clear()
            self.history.clear()
            return {"status": "not_detected"}

        # Calibration
        if self.baseline is None:
            if label == "Good":
                if self.good_start is None:
                    self.good_start = now

                self.samples.append(head_offset)

                elapsed = now - self.good_start

                if elapsed >= 5:
                    if len(self.samples) < 10 or pstdev(self.samples) > 0.05:
                        self.good_start = None
                        self.samples.clear()
                        return {"status": "retry"}

                    self.baseline = mean(self.samples)
                    self.history.clear()

                    return {
                        "status": "calibrated",
                        "baseline": self.baseline
                    }

                return {
                    "status": "calibrating",
                    "progress": min(elapsed / 5, 1.0)
                }

            self.good_start = None
            self.samples.clear()
            return {"status": "waiting_good"}

        # Normal monitoring
        self.history.append(head_offset)
        current = mean(self.history)

        # Direction-independent deviation for initial testing
        deviation = abs(current - self.baseline)

        return {
            "status": "monitoring",
            "baseline": self.baseline,
            "current": current,
            "deviation": deviation,
            "head_changed": deviation > self.threshold
        }

    def reset(self):
        self.baseline = None
        self.good_start = None
        self.samples.clear()
        self.history.clear()
