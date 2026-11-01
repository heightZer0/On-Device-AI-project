"""silero VAD (sherpa-onnx) 래퍼. 임의 길이 입력을 512 샘플 창으로 잘라 넣고 완성된 발화 구간을 돌려준다."""
from __future__ import annotations

import numpy as np

WINDOW = 512  # silero VAD 16 kHz 창 크기


class VadSegmenter:
    def __init__(self, model: str, threshold: float, min_silence_sec: float,
                 min_speech_sec: float, max_speech_sec: float, sample_rate: int = 16000):
        import sherpa_onnx

        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = model
        cfg.silero_vad.threshold = threshold
        cfg.silero_vad.min_silence_duration = min_silence_sec
        cfg.silero_vad.min_speech_duration = min_speech_sec
        cfg.silero_vad.max_speech_duration = max_speech_sec
        cfg.sample_rate = sample_rate
        self._vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=30)
        self._buf = np.zeros(0, dtype=np.float32)

    def feed(self, samples: np.ndarray) -> list[np.ndarray]:
        self._buf = np.concatenate([self._buf, samples.astype(np.float32, copy=False)])
        while len(self._buf) >= WINDOW:
            self._vad.accept_waveform(self._buf[:WINDOW])
            self._buf = self._buf[WINDOW:]
        segs = []
        while not self._vad.empty():
            segs.append(np.asarray(self._vad.front.samples, dtype=np.float32))
            self._vad.pop()
        return segs

    def reset(self) -> None:
        self._buf = np.zeros(0, dtype=np.float32)
        self._vad.reset()
