"""sherpa-onnx SenseVoice 오프라인 인식 래퍼 (CPU, 한국어)."""
from __future__ import annotations

import numpy as np


class SenseVoiceSTT:
    def __init__(self, model: str, tokens: str, num_threads: int = 4, language: str = "ko", use_itn: bool = True):
        import sherpa_onnx

        self._rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model, tokens=tokens, num_threads=num_threads,
            use_itn=use_itn, language=language, debug=False,
        )

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        s = self._rec.create_stream()
        s.accept_waveform(sample_rate, samples)
        self._rec.decode_stream(s)
        return (s.result.text or "").strip()
