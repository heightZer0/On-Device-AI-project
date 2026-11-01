"""마이크 입력. 16 kHz mono float32 를 목표로 하며, 장치가 16 kHz 를 못 열면 기본 샘플레이트로 열어 리샘플한다."""
from __future__ import annotations

import logging
import queue
import time
from typing import Optional

import numpy as np

log = logging.getLogger("voice.audio")


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return x
    if src % dst == 0:                      # 정수배 다운샘플: 박스 필터(평균)
        k = src // dst
        n = (len(x) // k) * k
        if n:
            return x[:n].reshape(-1, k).mean(axis=1).astype(np.float32)
    n_out = max(1, int(round(len(x) * dst / src)))
    return np.interp(np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x).astype(np.float32)


class MicStream:
    def __init__(self, device=None, sample_rate: int = 16000, block_ms: int = 32, max_blocks: int = 300):
        self._device = device
        self._target = sample_rate
        self._block_ms = block_ms
        self._q: queue.Queue = queue.Queue(maxsize=max_blocks)
        self._stream = None
        self._rate = sample_rate
        self._last = 0.0

    @property
    def running(self) -> bool:
        return self._stream is not None

    @property
    def stalled(self) -> bool:
        """3초 이상 데이터가 안 들어오면 장치 끊김으로 본다."""
        return self.running and (time.monotonic() - self._last) > 3.0

    def start(self) -> None:
        import sounddevice as sd

        try:
            self._open(sd, self._target)
        except Exception:  # noqa: BLE001  16 kHz 불가 -> 장치 기본값
            rate = int(sd.query_devices(self._device, "input")["default_samplerate"])
            self._open(sd, rate)

    def _open(self, sd, rate: int) -> None:
        self._rate = rate
        self.flush()
        self._stream = sd.InputStream(device=self._device, channels=1, dtype="float32", samplerate=rate,
                                      blocksize=int(rate * self._block_ms / 1000), callback=self._cb)
        self._stream.start()
        self._last = time.monotonic()
        log.info("mic opened rate=%d", rate)

    def _cb(self, indata, frames, t, status) -> None:
        self._last = time.monotonic()
        x = resample(indata[:, 0].copy(), self._rate, self._target)
        try:
            self._q.put_nowait(x)
        except queue.Full:
            pass

    def read(self, timeout: float = 0.2) -> Optional[np.ndarray]:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush(self) -> None:
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def stop(self) -> None:
        s, self._stream = self._stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:  # noqa: BLE001
                pass
        self.flush()
