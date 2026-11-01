"""TTS: sherpa-onnx VITS 합성 + 우선순위 큐 재생 (/speak 의 실체).

- 문구는 가공하지 않는다. 문장/길이 단위 분할은 합성 지연을 줄이기 위한 것뿐.
- 다음 청크를 미리 합성하는 파이프라인으로 첫 소리 지연을 줄인다.
- 큐 정책(가정, 설정화): reply 는 alert 보다 앞서되 재생 중인 청크는 끊지 않는다(청크 경계에서 전환).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

log = logging.getLogger("voice.tts")

_SENT_SPLIT = re.compile(r"(?<=[.!?。…])\s+|\n+")


def split_text(text: str, max_chars: int) -> list[str]:
    """문장 단위로 나누고, 너무 긴 문장은 공백/쉼표 기준으로 max_chars 이내로 자른다. 글자는 바꾸지 않는다."""
    chunks: list[str] = []
    for sent in (s.strip() for s in _SENT_SPLIT.split(text.strip())):
        while len(sent) > max_chars:
            cut = max(sent.rfind(" ", 0, max_chars), sent.rfind(",", 0, max_chars))
            if cut <= 0:
                cut = max_chars
            chunks.append(sent[:cut].strip())
            sent = sent[cut:].lstrip()
        if sent:
            chunks.append(sent)
    return [c for c in chunks if c]


class SherpaTTS:
    """sherpa-onnx OfflineTts(VITS) 래퍼. CPU, num_threads=설정값."""

    def __init__(self, model: str, tokens: str, data_dir: str, num_threads: int = 2, sid: int = 0):
        import sherpa_onnx  # 지연 import: 테스트/미설치 환경 대비

        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=model, tokens=tokens, data_dir=data_dir),
                num_threads=num_threads,
                provider="cpu",
            )
        )
        self._tts = sherpa_onnx.OfflineTts(cfg)
        self._sid = sid

    def synth(self, text: str, speed: float) -> tuple[np.ndarray, int]:
        audio = self._tts.generate(text, sid=self._sid, speed=speed)
        return np.asarray(audio.samples, dtype=np.float32), int(audio.sample_rate)


class UnavailableEngine:
    """모델 로딩 실패 시 대체. /speak/state 가 error 로 보이게 한다."""

    def __init__(self, reason: str = "tts model unavailable"):
        self.reason = reason

    def synth(self, text: str, speed: float):
        raise RuntimeError(self.reason)


def make_sd_player(device=None) -> Callable[[np.ndarray, int, float], None]:
    """sounddevice 블로킹 재생. 볼륨은 후처리 게인(가정: 합성 파라미터 아님)."""
    import sounddevice as sd

    def play(samples: np.ndarray, sr: int, volume: float) -> None:
        data = np.clip(samples * float(np.clip(volume, 0.0, 1.0)), -1.0, 1.0).astype(np.float32)
        sd.play(data, sr, device=device, blocking=True)

    return play


@dataclass
class _Item:
    kind: str
    chunks: list
    volume: float
    speed: float
    on_first_audio: Optional[Callable[[], None]] = None


class Speaker:
    def __init__(self, engine, player, *, speed: float = 1.0, volume: float = 1.0,
                 max_chars: int = 40, max_queue: int = 8, post_play_mute_ms: int = 400):
        self._engine = engine
        self._player = player
        self._speed = speed
        self._volume = volume
        self._max_chars = max_chars
        self._max_queue = max_queue
        self._post_mute = post_play_mute_ms / 1000.0

        self._cv = threading.Condition()
        self._alerts: deque[_Item] = deque()
        self._replies: deque[_Item] = deque()
        self._playing = False
        self._mute_until = 0.0
        self._error = False
        self._stop = False
        self._cache: dict = {}            # (chunk, speed) -> (samples, sr)  (메모리 전용)
        self._synth_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts-synth")
        self._thread = threading.Thread(target=self._run, name="speaker", daemon=True)

    # ---- 수명주기 ----
    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify_all()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ---- 외부 API ----
    def enqueue(self, text: str, kind: str = "reply", volume: Optional[float] = None,
                speed: Optional[float] = None, on_first_audio: Optional[Callable[[], None]] = None) -> int:
        text = (text or "").strip()
        if not text:
            raise ValueError("empty text")
        if kind not in ("alert", "reply"):
            raise ValueError("kind must be alert|reply")
        item = _Item(kind, split_text(text, self._max_chars),
                     self._volume if volume is None else volume,
                     self._speed if speed is None else speed, on_first_audio)
        with self._cv:
            (self._replies if kind == "reply" else self._alerts).append(item)
            while len(self._alerts) + len(self._replies) > self._max_queue:
                (self._alerts or self._replies).popleft()   # 오래된 alert 부터 버림
                log.warning("speak queue overflow: dropped oldest item")
            self._cv.notify()
            return len(self._alerts) + len(self._replies)

    def update_defaults(self, *, volume: float, speed: float) -> None:
        with self._cv:
            self._volume = float(volume)
            self._speed = float(speed)

    def warmup(self, texts: list[str]) -> int:
        """고정 문장 사전 합성(메모리 캐시). 캐시된 문장 수 반환."""
        n = 0
        for t in texts:
            t = (t or "").strip()
            if not t:
                continue
            for c in split_text(t, self._max_chars):
                key = (c, round(self._speed, 3))
                if key not in self._cache:
                    with self._synth_lock:
                        self._cache[key] = self._engine.synth(c, self._speed)
            n += 1
        return n

    def is_muted(self) -> bool:
        """에코 방지용: 재생 중 / 대기 중 / 재생 직후 post_play_mute 동안 True."""
        with self._cv:
            if self._playing or self._alerts or self._replies:
                return True
            return time.monotonic() < self._mute_until

    def state(self) -> dict:
        with self._cv:
            qlen = len(self._alerts) + len(self._replies)
            busy = self._playing or qlen > 0
            tts = "error" if self._error else ("busy" if busy else "ready")
            return {"tts": tts, "queue_len": qlen}

    def wait_idle(self, timeout: float = 5.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._cv:
                if not (self._playing or self._alerts or self._replies):
                    return True
            time.sleep(0.01)
        return False

    # ---- 내부 ----
    def _run(self) -> None:
        while True:
            with self._cv:
                while not (self._replies or self._alerts) and not self._stop:
                    self._cv.wait()
                if self._stop:
                    return
                item = self._replies.popleft() if self._replies else self._alerts.popleft()
                self._playing = True
            try:
                self._play_item(item)
                self._error = False
            except Exception as e:  # noqa: BLE001  합성/재생 실패 -> state=error, 로그만
                self._error = True
                log.error("tts failed: %s", type(e).__name__)
            finally:
                with self._cv:
                    self._playing = False
                    self._mute_until = time.monotonic() + self._post_mute

    def _audio(self, chunk: str, speed: float):
        hit = self._cache.get((chunk, round(speed, 3)))
        if hit is not None:
            return hit
        with self._synth_lock:
            return self._engine.synth(chunk, speed)

    def _play_item(self, item: _Item) -> None:
        n = len(item.chunks)
        if n == 0:
            return
        fut = self._pool.submit(self._audio, item.chunks[0], item.speed)
        for i in range(n):
            samples, sr = fut.result()
            fut = self._pool.submit(self._audio, item.chunks[i + 1], item.speed) if i + 1 < n else None
            if i == 0 and item.on_first_audio:
                try:
                    item.on_first_audio()
                except Exception:  # noqa: BLE001
                    pass
            self._player(samples, sr, item.volume)
            if item.kind == "alert" and i + 1 < n:
                with self._cv:
                    if self._replies:   # 청크 경계에서 reply 에 양보, 나머지는 alert 맨 앞에 되돌림
                        self._alerts.appendleft(_Item("alert", item.chunks[i + 1:], item.volume, item.speed))
                        return
