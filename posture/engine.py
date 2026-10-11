"""
PostureEngine — P2 가 호출하는 단일 진입점 (명세 P1-9).

step() 은 프레임 한 장을 처리한다. 배경 스레드(run_in_background)나 데모의 메인 루프가 반복 호출한다.
- 카메라가 끊겨도 예외를 던지지 않고 unavailable 로 처리한다. (P1-9)
- 이벤트 콜백은 처리 스레드에서 호출된다. 오래 걸리는 일은 콜백 안에서 하지 말 것.
- 모니터링 중에는 고정된 side 한쪽의 좌표만 소스에 요청한다. (C2-1, C2-5)
"""
import csv
import logging
import threading
import time
from typing import Callable, Optional

from posture.analyzer.analyzer import Obs, PostureAnalyzer
from posture.calibration.calibration import (CalibrationCollector, compute_calibration,
                                             load_calibration, save_calibration)
from posture.rules.config import load_config

log = logging.getLogger(__name__)

LOG_HEADER = ["ts", "subject", "note", "side", "d", "state", "reason", "H", "dH", "S", "confidence"]


class PostureEngine:
    def __init__(self, cfg=None, source=None, clock: Callable[[], float] = time.monotonic):
        self.cfg = cfg or load_config()
        self._source = source
        self._clock = clock
        self._lock = threading.RLock()
        self._source_lock = threading.Lock()
        self._callbacks = []
        self._status = "stopped"                 # stopped | running | paused
        self._phase = "idle"                     # 캘리브레이션: idle | collecting | ready | failed
        self._collector = None
        self._pending = None
        self._info = None
        self._thread = None
        self._stop_evt = threading.Event()
        self._log_fh = self._log_w = None
        self._log_meta, self._log_t0, self._log_n = ("", ""), None, 0
        cal = load_calibration(self.cfg.calibration_path)     # 재시작 후에도 기준값 로드
        self._analyzer = PostureAnalyzer(self.cfg, cal, emit=self._dispatch)

    # ---------- 소스 ----------
    @property
    def source(self):
        if self._source is None:
            from posture.pose_estimation.mediapipe_source import MediaPipeSource
            self._source = MediaPipeSource(self.cfg)
        return self._source

    def get_camera_status(self) -> str:
        return getattr(self._source, "status", "unavailable") if self._source is not None else "unavailable"

    # ---------- 모니터링 제어 (멱등) ----------
    @property
    def status(self) -> str:
        return self._status

    def start(self) -> str:
        with self._lock:
            if self._status != "running":
                self._analyzer.reset()           # 타이머 초기화 후 시작/재개
                self._status = "running"
            return self._status

    def pause(self) -> str:
        with self._lock:
            if self._status == "running":
                self._status = "paused"
            return self._status

    def resume(self) -> str:
        with self._lock:
            if self._status == "paused":
                self._analyzer.reset()
                self._status = "running"
            return self._status

    def stop(self) -> str:
        with self._lock:
            self._status = "stopped"
            return self._status

    # ---------- 상태·이벤트 ----------
    def get_state(self) -> dict:
        with self._lock:
            return self._analyzer.get_state()

    def on_event(self, callback: Callable[[dict], None]):
        self._callbacks.append(callback)

    def _dispatch(self, event: dict):
        for cb in list(self._callbacks):
            try:
                cb(event)
            except Exception:
                log.exception("event callback failed")

    def set_debug(self, enabled: bool):
        with self._lock:
            self._analyzer.debug = bool(enabled)

    # ---------- 캘리브레이션 ----------
    def begin_calibration(self) -> dict:
        """수집 시작. 시작 직전 한 프레임으로 귀·어깨 검출 여부를 확인해 돌려준다."""
        with self._source_lock:
            try:
                frame = self.source.read(("left", "right"))
            except Exception:
                log.exception("camera read failed")
                frame = None
        detected = {}
        for s in ("left", "right"):
            p = frame.pose.get(s) if (frame is not None and frame.pose) else None
            detected[s] = {"ear": bool(p and p["ve"] >= self.cfg.T_vis),
                           "shoulder": bool(p and p["vs"] >= self.cfg.T_vis)}
        detected["any"] = any(v["ear"] and v["shoulder"] for k, v in detected.items())
        with self._lock:
            self._collector = CalibrationCollector(self.cfg)
            self._pending = self._info = None
            self._phase = "collecting"
        return {"phase": "collecting", "camera": self.get_camera_status(), "detected": detected}

    def preview_calibration(self) -> dict:
        with self._lock:
            out = {"phase": self._phase}
            if self._phase == "collecting" and self._collector:
                out["progress"] = round(self._collector.progress(), 3)
            elif self._phase == "ready":
                out["summary"] = {**{k: self._pending[k] for k in ("H_base", "L_ref_fixed", "side", "d")}, **self._info}
            elif self._phase == "failed":
                out["error"] = self._info.get("error")
                out["info"] = dict(self._info)
            return out

    def confirm_calibration(self) -> dict:
        """미리보기를 사용자가 확인한 뒤 저장. 이후 side/d/L_ref_fixed/H_base 는 다음 재캘리브레이션 전까지 불변."""
        with self._lock:
            if self._phase != "ready":
                return {"ok": False, "error": "not_ready"}
            cal = self._pending
            try:
                save_calibration(cal, self.cfg.calibration_path)
            except OSError:
                log.exception("calibration save failed")
                return {"ok": False, "error": "save_failed"}
            self._analyzer.set_calibration(cal)
            self._phase, self._pending = "idle", None
            return {"ok": True, "calibration": dict(cal)}

    def get_calibration(self) -> Optional[dict]:
        with self._lock:
            return dict(self._analyzer.cal) if self._analyzer.cal else None

    def _collect(self, frame):
        c = self._collector
        c.add(frame)
        if c.done():
            cal, info = compute_calibration(c.samples, self.cfg)
            self._info = info
            if cal is None:
                self._phase = "failed"
            else:
                self._pending, self._phase = cal, "ready"

    # ---------- 실험용 CSV 로그 (개발 전용) ----------
    def start_experiment_log(self, path: str, subject: str = "", note: str = ""):
        """프레임별 H·ΔH·S·상태를 CSV 로 남긴다 (0단계 실험 E3~E6용). 실험이 끝나면 파일을 삭제할 것.
        영상·귀/어깨 좌표는 기록하지 않는다. 좌표가 필요하면 tools/h_logger.py 를 쓴다."""
        with self._lock:
            self.stop_experiment_log()
            self._log_fh = open(path, "w", newline="", encoding="utf-8")
            self._log_w = csv.writer(self._log_fh)
            self._log_w.writerow(LOG_HEADER)
            self._log_meta, self._log_t0, self._log_n = (subject, note), None, 0

    def stop_experiment_log(self):
        with self._lock:
            if self._log_fh is not None:
                self._log_fh.close()
            self._log_fh = self._log_w = None

    def _write_log(self, obs: Obs):
        if self._log_w is None:
            return
        if self._log_t0 is None:
            self._log_t0 = obs.ts
        st, m, cal = self._analyzer.get_state(), self._analyzer.metrics(), self._analyzer.cal or {}
        fmt = lambda v: "" if v is None else f"{v:.4f}"
        self._log_w.writerow([f"{obs.ts - self._log_t0:.3f}", *self._log_meta, cal.get("side", ""),
                              cal.get("d", ""), st["state"], st["reason"] or "",
                              fmt(m["H"]), fmt(m["dH"]), fmt(m["S"]), st["confidence"]])
        self._log_n += 1
        if self._log_n % 30 == 0:
            self._log_fh.flush()

    # ---------- 처리 루프 ----------
    def _to_obs(self, frame) -> Obs:
        cal = self._analyzer.cal
        if frame is None:                                    # 카메라 끊김 → 측정 불가로 처리
            return Obs(ts=self._clock(), detected=False)
        side = cal["side"] if cal else None
        p = frame.pose.get(side) if (frame.pose and side) else None
        if p is None:
            return Obs(ts=frame.ts, detected=False, width=frame.width, height=frame.height)
        return Obs(ts=frame.ts, detected=True, xe=p["xe"], ye=p["ye"], xs=p["xs"], ys=p["ys"],
                   ve=p["ve"], vs=p["vs"], width=frame.width, height=frame.height)

    def step(self) -> bool:
        """프레임 한 장 처리. 할 일이 없으면(paused/stopped 이고 수집 중도 아님) False."""
        with self._lock:
            collecting = self._phase == "collecting"
            running = self._status == "running"
            cal = self._analyzer.cal
        if not (collecting or running):
            return False
        sides = ("left", "right") if (collecting or cal is None) else (cal["side"],)
        with self._source_lock:
            try:
                frame = self.source.read(sides)
            except Exception:
                log.exception("camera read failed")
                frame = None
        with self._lock:
            if self._phase == "collecting":
                if frame is not None:
                    self._collect(frame)
            elif self._status == "running":
                obs = self._to_obs(frame)
                self._analyzer.update(obs)
                self._write_log(obs)
        return True

    def run_in_background(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, name="posture-engine", daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop_evt.is_set():
            if not self.step():
                time.sleep(0.05)

    def close(self):
        self.stop_experiment_log()
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._source is not None and hasattr(self._source, "close"):
            self._source.close()
