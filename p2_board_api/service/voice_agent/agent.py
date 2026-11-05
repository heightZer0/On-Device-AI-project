"""음성 명령 흐름 (v10.2 D-03).

mic -> VAD -> STT -> 전처리 -> POST P2 /api/v1/command {source:"voice", utterance, confidence}
     -> tts_text (또는 error.message) 재생.  P3 는 LLM 서버를 호출하지 않는다.
P3는 LLM을 직접 호출하지 않는다.

개인정보: 오디오 버퍼는 STT 직후 폐기, 로그/메트릭에 STT 텍스트·문구를 남기지 않는다(길이·시간·성공 여부만).
"""
from __future__ import annotations

import csv
import logging
import os
import re
import threading
import time
import uuid
from typing import Optional

import numpy as np
import requests

log = logging.getLogger("voice.agent")

_TRAIL = re.compile(r"[\s.?!。？！]+$")


def preprocess(text: str) -> str:
    """끝의 문장부호(. ? !)와 앞뒤 공백만 제거. 숫자·수사는 건드리지 않는다."""
    return _TRAIL.sub("", (text or "").strip()).strip()


class DisabledAgent:
    """VAD/STT/마이크 준비 실패 시 대체. /speak 는 계속 동작하고 mic 는 error 로 보인다."""

    def mic_state(self) -> str:
        return "error"

    def set_mic(self, enabled: bool) -> str:
        return "error"


class VoiceAgent(threading.Thread):
    def __init__(self, cfg: dict, mic, vad, stt, speaker, http=requests):
        super().__init__(daemon=True, name="voice-agent")
        self._cfg = cfg
        self._mic, self._vad, self._stt, self._speaker, self._http = mic, vad, stt, speaker, http
        self._stop_evt = threading.Event()
        self._debug_dir = None  # Audio-file debugging is deliberately disabled by P0.
        self._enabled = True
        self._state = "off"
        self._mic_open = False
        self._csv_lock = threading.Lock()
        self._conversation_id = uuid.uuid4().hex

    # ---- 외부 제어 ----
    def mic_state(self) -> str:
        return "off" if not self._enabled else self._state

    def set_mic(self, enabled: bool) -> str:
        self._enabled = bool(enabled)
        if not self._enabled:
            self._state = "off"
            if self._vad is not None:
                self._vad.reset()
            if self._mic is not None:
                self._mic.flush()
        return self.mic_state()

    def stop(self) -> None:
        self._stop_evt.set()

    # ---- 메인 루프 ----
    def run(self) -> None:
        while not self._stop_evt.is_set():
            if not self._enabled:
                if self._mic_open:
                    self._close_mic()
                self._stop_evt.wait(0.1)
                continue
            if not self._mic_open and not self._open_mic():
                self._stop_evt.wait(3.0)
                continue
            chunk = self._mic.read(0.2)
            if chunk is None:
                if self._mic.stalled:
                    log.error("mic stalled; reopening")
                    self._close_mic()
                    self._state = "error"
                    self._stop_evt.wait(3.0)
                continue
            if self._speaker.is_muted():          # 에코 방지: 재생 중·직후에는 입력 무시
                self._vad.reset()
                continue
            segs = self._vad.feed(chunk)
            if segs:
                try:
                    self._handle_segment(segs[0])
                except Exception as e:  # noqa: BLE001
                    log.error("segment handling failed: %s", type(e).__name__)
                finally:
                    self._mic.flush()             # 처리 중 쌓인 오래된 입력 폐기
                    self._vad.reset()
        self._close_mic()

    def _open_mic(self) -> bool:
        try:
            self._mic.start()
            self._mic_open = True
            self._state = "on"
            return True
        except Exception as e:  # noqa: BLE001
            self._state = "error"
            log.error("mic open failed: %s", type(e).__name__)
            return False

    def _close_mic(self) -> None:
        try:
            self._mic.stop()
        finally:
            self._mic_open = False
            if self._state == "on":
                self._state = "off"

    # ---- 발화 1건 처리 ----
    def _handle_segment(self, samples: np.ndarray) -> None:
        t_end = time.monotonic()
        text = self._stt.transcribe(samples) or ""
        samples = None  # noqa: F841  오디오 버퍼 즉시 폐기
        self.process_text(text, t_end, time.monotonic())

    def process_text(self, text: str, t_end: float, t_stt: float) -> None:
        if not preprocess(text):
            phrase = self._cfg["fallback_phrases"].get("stt_empty")
            if phrase:
                self._speaker.enqueue(phrase, "reply")
            return
        phrase = self._call_p2(text)
        t_cmd = time.monotonic()
        log.info("voice cmd chars=%d stt_ms=%d cmd_ms=%d ok=%s", len(text),
                 (t_stt - t_end) * 1000, (t_cmd - t_stt) * 1000, bool(phrase))
        if phrase and phrase.strip():
            self._speaker.enqueue(
                phrase, "reply",
                on_first_audio=lambda: self._record(t_end, t_stt, t_cmd, time.monotonic()))
        else:
            self._record(t_end, t_stt, t_cmd, None)

    # ---- P2 호출 ----
    def _p2_headers(self) -> dict:
        tok = os.environ.get(self._cfg["p2"].get("token_env", ""), "")
        return {"Authorization": f"Bearer {tok}"} if tok else {}

    def _post_command(self, url: str, body: dict, timeout: float) -> Optional[str]:
        fb = self._cfg["fallback_phrases"]["p2_down"]
        try:
            r = self._http.post(url, json=body, headers=self._p2_headers(), timeout=timeout)
        except requests.RequestException:
            return fb                              # 연결 실패/타임아웃
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code == 200:
            return data.get("tts_text")            # ok=false 여도 tts_text 재생
        return (data.get("error") or {}).get("message") or fb

    def _call_p2(self, utterance: str) -> Optional[str]:
        p2 = self._cfg["p2"]
        body = {"source": "voice", "utterance": utterance, "confidence": None,
                "request_id": uuid.uuid4().hex,
                "conversation_id": self._conversation_id}  # keep raw STT text for P2 context and duration parsing
        return self._post_command(p2["command_url"], body, p2["timeout_sec"])

    # ---- 측정(P7 공유): 텍스트·문구는 기록하지 않음 ----
    def _record(self, t_end, t_stt, t_cmd, t_tts) -> None:
        m = self._cfg.get("metrics", {})
        if not m.get("enabled"):
            return
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
        except Exception:  # noqa: BLE001
            cpu = ""
        row = {
            "stt_ms": round((t_stt - t_end) * 1000), "cmd_ms": round((t_cmd - t_stt) * 1000),
            "tts_first_audio_ms": "" if t_tts is None else round((t_tts - t_cmd) * 1000),
            "total_ms": "" if t_tts is None else round((t_tts - t_end) * 1000), "cpu_percent": cpu,
        }
        path = m["csv_path"]
        with self._csv_lock:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            new = not os.path.exists(path)
            with open(path, "a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(row))
                if new:
                    w.writeheader()
                w.writerow(row)

