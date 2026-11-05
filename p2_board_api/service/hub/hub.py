"""P2 허브: 상태 머신 · 세션 누적 · 이벤트→음성 · 설정 전파 · 서비스 핸들(P4 실행기용)."""
import copy
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from collections import defaultdict

from pydantic import ValidationError

from service.api_server.errors import ApiError
from service.api_server.schemas import PostureState
from service.hub import settings as S
from service.session_service.tracker import SessionTracker, to_api, row_to_api

log = logging.getLogger("p2.hub")
IDLE, CAL, MON, PAUSED = "IDLE", "CALIBRATING", "MONITORING", "PAUSED"   # ⚑ system_state 4종 (가정)
_MONITORING = {IDLE: "stopped", CAL: "stopped", MON: "running", PAUSED: "paused"}
_S_KEYS = {"debug", "shoulder_screen_shift"}                              # 일반 모드에서 제거


def _strip(o):
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if k not in _S_KEYS}
    if isinstance(o, list):
        return [_strip(v) for v in o]
    return o


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class Hub:
    def __init__(self, cfg, engine, store, speak, llm, phrases, clock=None, async_speak=True):
        self.cfg, self.engine, self.store, self.speak, self.llm, self.phrases = cfg, engine, store, speak, llm, phrases
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = threading.RLock()
        self.state, self._resume_to = IDLE, IDLE
        self.session = None
        self.calibration_id = None
        self.notices = set()
        self._since_ckpt_ms = 0
        self._cache, self._cache_lock = {}, threading.Lock()
        self._pool = ThreadPoolExecutor(2) if async_speak else None
        self._break, self._break_timer = None, None
        self._health, self._stop_evt, self._threads = None, threading.Event(), []

        store.recover_unfinished()
        last = store.last_ended()
        self.last_session = row_to_api(last) if last else None
        self.settings = {**S.DEFAULTS, **{k: v for k, v in store.get_settings().items() if k in S.SPECS}}
        engine.on_event(self.on_event)
        self._apply_runtime(self.settings, first=True)
        self.refresh_health()

    # ---------- 공통 ----------
    def scrub(self, data):
        return data if self.settings["debug_mode"] else _strip(data)

    def idem(self, rid, endpoint, fn):
        """request_id 중복 방지. 같은 id가 다른 엔드포인트에 오면 400. 성공 응답만 캐시."""
        if not rid:
            return fn()
        c = self.cfg["request_id_cache"]
        now = time.monotonic()
        with self._cache_lock:
            for k in [k for k, v in self._cache.items() if now - v[1] > c["ttl_sec"]]:
                del self._cache[k]
            hit = self._cache.get(rid)
            if hit:
                if hit[0] != endpoint:
                    raise ApiError(400, "INVALID_REQUEST", "같은 request_id가 다른 요청에 쓰였어요.")
                return copy.deepcopy(hit[2])
        body = fn()
        with self._cache_lock:
            self._cache[rid] = (endpoint, now, copy.deepcopy(body))
            while len(self._cache) > c["max_items"]:
                self._cache.pop(next(iter(self._cache)))
        return body

    def calibrated(self):
        return self.engine.get_calibration() is not None

    def ensure_camera_ready(self):
        """Probe a lazily opened P1 camera when a start command needs it."""
        probe = getattr(self.engine, "ensure_camera_ready", None)
        if probe is None:
            return (self._health or {}).get("camera") == "ready"
        ready = bool(probe())
        try:
            camera = self.engine.get_health().get("camera", "error")
        except Exception:
            camera = "error"
        with self.lock:
            health = dict(self._health or {})
            health["camera"] = camera
            health["status"] = "ok" if camera == "ready" and not any(
                value == "error" for value in (health.get("ai_modules") or {}).values()) else "degraded"
            self._health = health
        return ready

    def _control(self, message, **extra):
        s = self.session
        return {"system_state": self.state, "monitoring": _MONITORING[self.state],
                "session_id": s.session_id if s else None, "started_at": s.started_at if s else None,
                "message": message, **extra}

    # ---------- 모니터링 상태 머신 (멱등) ----------
    def monitoring_start(self):
        with self.lock:
            if self.state == CAL:
                raise ApiError(409, "INVALID_STATE", "캘리브레이션 중에는 시작할 수 없어요.")
            if self.state == MON:
                return self._control("이미 모니터링 중이에요.")
            if self.state == PAUSED:
                if not self.ensure_camera_ready():
                    raise ApiError(503, "CAMERA_NOT_READY", "카메라를 사용할 수 있을 때 다시 시도해 주세요.")
                self.engine.resume()
                self.state = MON
                return self._control("모니터링을 다시 시작했어요.")
            if not self.calibrated():
                raise ApiError(409, "CALIBRATION_REQUIRED", "기준 자세를 먼저 설정해 주세요.")
            if not self.ensure_camera_ready():
                raise ApiError(503, "CAMERA_NOT_READY", "카메라를 사용할 수 있을 때 다시 시도해 주세요.")
            self.engine.start()
            now = iso(self.clock())
            self.session = SessionTracker(session_id="session_" + uuid.uuid4().hex[:12], started_at=now)
            self.store.create_session(self.session.session_id, now)
            self._since_ckpt_ms = 0
            self.state = MON
            return self._control("모니터링을 시작했어요.")

    def monitoring_pause(self):
        with self.lock:
            if self.state != MON:
                return self._control("일시정지할 모니터링이 없어요.")
            self.engine.pause()
            self.state = PAUSED
            return self._control("일시정지했어요.")

    def monitoring_stop(self):
        with self.lock:
            if self.state == IDLE:
                return self._control("이미 중지 상태예요.", session_summary=self.last_session)
            if self.state == CAL:
                cancel = getattr(self.engine, "cancel_calibration", None)
                if cancel:
                    cancel()
            if self.session:
                self._end_session()
                self.engine.stop()
            self.state, self._resume_to = IDLE, IDLE
            return self._control("모니터링을 종료했어요.", session_summary=self.last_session)

    def _end_session(self):
        now = iso(self.clock())
        snap = self.session.snapshot()
        self.store.save_session(self.session.session_id, snap, now, ended_at=now)
        self.last_session = to_api(self.session.session_id, self.session.started_at, now, snap)
        self.session = None

    # ---------- 캘리브레이션 ----------
    def calibration_start(self, duration_sec=None):
        with self.lock:
            if self.state not in (IDLE, PAUSED):
                raise ApiError(409, "INVALID_STATE", "지금은 캘리브레이션을 시작할 수 없어요.")
            detection = self.engine.begin_calibration(duration_sec) if duration_sec is not None else self.engine.begin_calibration()
            self._resume_to, self.state = self.state, CAL
            self.calibration_id = "cal_" + uuid.uuid4().hex[:12]
            return {"system_state": self.state, "state": self.state,
                    "calibration_id": self.calibration_id, "detection": detection,
                    "guide": "카메라에 머리와 어깨가 보이도록 하고 편안한 기준 자세를 유지해 주세요."}

    def _require_cal(self):
        if self.state != CAL:
            raise ApiError(409, "INVALID_STATE", "캘리브레이션을 먼저 시작해 주세요.")

    def calibration_preview(self, calibration_id=None):
        with self.lock:
            self._require_cal()
            if calibration_id and calibration_id != self.calibration_id:
                raise ApiError(404, "NOT_FOUND", "캘리브레이션을 찾을 수 없어요.")
            preview = self.engine.preview_calibration()
            phase = preview.get("phase", "collecting")
            return {"system_state": self.state, "state": phase.upper(), "preview": preview,
                    "progress": preview.get("progress", 0.0), "summary": preview.get("summary", {})}

    def calibration_confirm(self, calibration_id=None, confirm=True):
        with self.lock:
            self._require_cal()
            if calibration_id and calibration_id != self.calibration_id:
                raise ApiError(404, "NOT_FOUND", "캘리브레이션을 찾을 수 없어요.")
            if not confirm:
                cancel = getattr(self.engine, "cancel_calibration", None)
                if cancel:
                    cancel()
                self.state = self._resume_to
                self.calibration_id = None
                return {"system_state": self.state, "calibrated": self.calibrated(), "confirmed": False}
            preview = self.engine.preview_calibration()
            quality = (preview.get("summary") or {}).get("usable_frame_ratio")
            result = self.engine.confirm_calibration()
            if isinstance(result, dict) and (result.get("saved") is False or result.get("ok") is False):
                return {"system_state": self.state, "saved": False, "calibration": result}
            self.state = self._resume_to
            self.calibration_id = None
            self.notices.discard("recalibration_suggested")
            cal = result.get("calibration", result) if isinstance(result, dict) else {}
            return {"system_state": self.state, "saved": True, "calibrated": self.calibrated(),
                    "side": cal.get("side"), "quality": quality, "calibration": result}

    # ---------- 세션 누적 ----------
    def tick(self, dt_ms):
        with self.lock:
            if not self.session:
                return
            should_read = self.state == MON
        st = None
        if should_read:
            try:
                st = self.engine.get_state().get("state")
            except Exception:
                st = "unavailable"
        with self.lock:
            if not self.session:
                return
            running = self.state == MON
            self.session.add(dt_ms, st if running else None, running)
            self._since_ckpt_ms += dt_ms
            if self._since_ckpt_ms >= self.cfg["session"]["checkpoint_sec"] * 1000:
                self._since_ckpt_ms = 0
                self.store.save_session(self.session.session_id, self.session.snapshot(), iso(self.clock()))

    def get_session(self):
        with self.lock:
            s = self.session
            return to_api(s.session_id, s.started_at, None, s.snapshot()) if s else to_api(
                None, None, None, {"sitting_sec": 0, "monitoring_sec": 0, "normal_sec": 0,
                                   "attention_sec": 0, "unavailable_sec": 0, "alert_count": 0})

    def get_last_session(self):
        return self.last_session

    def history(self, limit, offset):
        rows, total = self.store.list_sessions(limit, offset)
        items = []
        for row in rows:
            item = row_to_api(row)
            item.update(item.pop("state_durations"))  # C12 history uses flat duration fields.
            items.append(item)
        next_offset = offset + len(rows)
        return {"items": items, "total": total, "limit": limit,
                "next_cursor": str(next_offset) if next_offset < total else None}

    def calendar(self, month: str, timezone_name: str = "Asia/Seoul"):
        """Monthly app payload grouped by the client's local session start date."""
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as e:
            raise ApiError(400, "INVALID_REQUEST", "시간대 이름을 확인해 주세요.") from e
        try:
            year_text, month_text = month.split("-", 1)
            year, month_num = int(year_text), int(month_text)
            datetime(year, month_num, 1, tzinfo=zone)
        except (TypeError, ValueError):
            raise ApiError(400, "INVALID_REQUEST", "월 형식은 YYYY-MM이어야 해요.")
        rows = self.store.all_sessions()
        with self.lock:
            if self.session:
                rows.append({"id": self.session.session_id, "started_at": self.session.started_at,
                             "ended_at": None, **self.session.snapshot()})
        days = defaultdict(lambda: {"focus_sec": 0, "good_sec": 0, "attention_sec": 0,
                                    "unavailable_sec": 0, "warning_count": 0, "session_count": 0})
        session_items = []
        for row in rows:
            try:
                started = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00")).astimezone(zone)
            except (KeyError, ValueError, TypeError):
                continue
            if started.year != year or started.month != month_num:
                continue
            item = row_to_api(row)
            item.update(item.pop("state_durations"))
            day = started.date().isoformat()
            item["local_date"] = day
            session_items.append(item)
            bucket = days[day]
            for key in ("focus_sec", "good_sec", "attention_sec", "unavailable_sec", "warning_count"):
                bucket[key] += item[key]
            bucket["session_count"] += 1
        day_items = [{"date": key, **value,
                      "posture_rate": int(value["good_sec"] * 100 / value["focus_sec"]) if value["focus_sec"] else 0}
                     for key, value in sorted(days.items())]
        totals = {key: sum(d[key] for d in day_items) for key in
                  ("focus_sec", "good_sec", "attention_sec", "unavailable_sec", "warning_count", "session_count")}
        totals["study_days"] = sum(d["focus_sec"] > 0 for d in day_items)
        totals["posture_rate"] = int(totals["good_sec"] * 100 / totals["focus_sec"]) if totals["focus_sec"] else 0
        return {"month": month, "timezone": timezone_name, "totals": totals,
                "days": day_items, "sessions": sorted(session_items, key=lambda x: x["started_at"])}

    # ---------- 자세·상태 ----------
    def get_posture(self):
        try:
            d = PostureState.model_validate(self.engine.get_state()).model_dump(mode="json")
        except (ValidationError, Exception) as e:
            log.warning("engine state invalid: %s", type(e).__name__)
            raise ApiError(503, "AI_MODULE_UNAVAILABLE", "자세 분석 모듈 상태를 읽을 수 없어요.")
        if d["state"] == "unavailable":
            d["indicators"] = {}
        if d.get("debug") is None or not self.settings["debug_mode"]:
            d.pop("debug", None)
        return d

    def get_preview_frame(self):
        """Return one in-memory camera frame for the authenticated local preview only."""
        with self.lock:
            if not (self.settings.get("debug_mode") and self.settings.get("preview_stream_enabled")):
                raise ApiError(404, "NOT_FOUND", "카메라 미리보기가 꺼져 있어요.")
            active_capture = self.state in (CAL, MON)

        source = self.engine.source
        source_lock = getattr(self.engine, "_source_lock", self.lock)
        with source_lock:
            # The P1 loop owns capture while calibrating/monitoring. In idle or paused
            # preview mode this request advances the same camera source itself.
            if not active_capture or source.last_frame is None:
                source.read(("left", "right"))
            if getattr(source, "status", None) != "ready" or source.last_frame is None:
                raise ApiError(503, "CAMERA_UNAVAILABLE", "웹캠 프레임을 읽을 수 없어요.")
            return source.last_frame.copy()

    def status(self):
        # P1 reads happen before hub.lock so status polling never nests hub -> engine locks.
        posture = self.get_posture()
        calibrated = self.calibrated()
        with self.lock:
            s = self.session
            return {"system_state": self.state, "monitoring": _MONITORING[self.state],
                    "camera": (self._health or {}).get("camera", "unavailable"),
                    "calibrated": calibrated, "posture": posture,
                    "session": to_api(s.session_id, s.started_at, None, s.snapshot()) if s else None,
                    "notices": sorted(self.notices), "poll_hint_sec": self.cfg["poll_hint_sec"],
                    "updated_at": iso(self.clock())}

    def refresh_health(self):
        try:
            eh = self.engine.get_health()
        except Exception:
            eh = {"camera": "error", "pose": "error"}
        try:
            sp = self.speak.state()
        except Exception:
            sp = {"stt": "error", "tts": "error"}
        try:
            llm = self.llm.health()
        except Exception:
            llm = "error"
        mods = {"pose": eh.get("pose", "error"), "stt": sp.get("stt", "error"), "tts": sp.get("tts", "error"), "llm": llm}
        camera = eh.get("camera", "error")
        degraded = camera == "error" or "error" in mods.values()
        health = {"status": "degraded" if degraded else "ok", "camera": camera, "ai_modules": mods}
        with self.lock:
            self._health = health

    def health(self):
        self.refresh_health()
        return {**self._health, "timestamp": iso(self.clock())}

    # ---------- 설정 ----------
    def get_setting(self, key):
        return self.settings.get(key)

    def update_settings(self, patch):
        errors = S.validate_patch(patch)
        with self.lock:
            new = {**self.settings, **patch}
            if patch.get("debug_mode") is False:
                new["preview_stream_enabled"] = False
            if not errors and new["preview_stream_enabled"] and not new["debug_mode"]:
                errors["preview_stream_enabled"] = "debug_mode에서만 켤 수 있어요"
            if errors:
                raise ApiError(400, "INVALID_REQUEST", "설정 값이 올바르지 않아요.", {"fields": errors})
            changed = {k: v for k, v in new.items() if self.settings.get(k) != v}
            self.store.set_settings(new)
            self.settings = new
            self._apply_runtime(changed)
            return dict(self.settings)

    def _apply_runtime(self, changed, first=False):
        try:
            rt = {k: changed[k] for k in ("alert_interval_sec", "posture_sensitivity") if k in changed or first}
            if first:
                rt = {k: self.settings[k] for k in rt}
            if rt:
                self.engine.update_runtime_settings(**rt)
            if "debug_mode" in changed or first:
                self.engine.set_debug(self.settings["debug_mode"])
        except Exception as e:
            log.warning("engine settings push failed: %s", type(e).__name__)
        if "microphone_enabled" in changed or first:
            try:
                self.speak.set_mic(self.settings["microphone_enabled"])
            except Exception as e:      # P3가 아직 안 떠 있을 수 있음
                log.warning("mic push failed: %s", type(e).__name__)
        if "tts_volume" in changed or "tts_speed" in changed or first:
            try:
                self.speak.set_settings(self.settings)
            except Exception as e:
                log.warning("voice settings push failed: %s", type(e).__name__)

    # ---------- 이벤트 → 음성 ----------
    def on_event(self, e):
        t = e.get("type")
        with self.lock:
            if self.settings["event_log_enabled"]:
                self.store.log_event(t, e.get("ts", iso(self.clock())), e.get("delta"))
            if t == "attention_started" and self.session and self.state == MON:
                self.session.warnings += 1                      # D-16: 음성 설정과 무관
            if t == "recalibration_suggested":
                self.notices.add(t)                             # 자동 재캘리브레이션 금지: 안내만
            text = (self.phrases.get("events") or {}).get(t)
            if text and self.settings["voice_feedback_enabled"] and self.state == MON:
                self._speak(text, "alert")

    def _speak(self, text, kind):
        def job():
            for _ in range(2):                                   # 실패 시 1회 재시도 후 로그
                try:
                    self.speak.speak(text, kind, self.settings["tts_volume"])
                    return
                except Exception as e:
                    err = type(e).__name__
            log.warning("speak failed: %s", err)
        if self._pool:
            self._pool.submit(job)
        else:
            job()

    def warmup(self):
        texts = [v for sec in ("events", "alarms", "errors") for v in (self.phrases.get(sec) or {}).values() if v]
        try:
            self.speak.warmup(texts)
        except Exception as e:
            log.warning("warmup failed: %s", type(e).__name__)

    def test_sound(self):
        if not self.settings["voice_feedback_enabled"]:
            raise ApiError(409, "INVALID_STATE", "음성 안내가 꺼져 있어요. 설정에서 음소거를 해제해 주세요.")
        self._speak("음성 안내 테스트입니다.", "reply")
        return {"accepted": True, "message": "테스트 음성을 재생했어요."}

    # ---------- 휴식 알림 / 스트레칭 (P4 실행기용 핸들) ----------
    def set_break_alarm(self, minutes):
        with self.lock:
            if self._break and not self.cfg["break_alarm_replace"]:
                return {"set": False, "reason": "already_set", "minutes": self._break["minutes"]}
            replaced = self._break is not None
            if self._break_timer:
                self._break_timer.cancel()
            self._break = {"minutes": minutes, "due": time.monotonic() + minutes * 60}
            self._break_timer = threading.Timer(minutes * 60, self._on_break_alarm)
            self._break_timer.daemon = True
            self._break_timer.start()
            return {"set": True, "replaced": replaced, "minutes": minutes}

    def _on_break_alarm(self):
        with self.lock:
            self._break = None
            text = (self.phrases.get("alarms") or {}).get("break")
            if text and self.settings["voice_feedback_enabled"]:
                self._speak(text, "alert")

    def get_break_status(self):
        with self.lock:
            if not self._break:
                return {"set": False}
            return {"set": True, "minutes": self._break["minutes"],
                    "remaining_sec": max(0, int(self._break["due"] - time.monotonic()))}

    def get_stretch_guide(self, part):
        return None      # TODO(기획): 스트레칭 안내 데이터 미확정

    # ---------- 백그라운드 ----------
    def start_background(self):
        start_engine = getattr(self.engine, "run_in_background", None)
        if start_engine:
            start_engine()
        def tick_loop():
            last = time.monotonic()
            while not self._stop_evt.wait(self.cfg["session"]["tick_sec"]):
                now = time.monotonic()
                self.tick(int((now - last) * 1000))
                last = now

        def health_loop():
            while not self._stop_evt.wait(self.cfg["health_refresh_sec"]):
                self.refresh_health()
        for fn in (tick_loop, health_loop):
            t = threading.Thread(target=fn, daemon=True)
            t.start()
            self._threads.append(t)

    def stop_background(self):
        self._stop_evt.set()
        with self.lock:
            if self.session:             # 종료 시 현재 세션 보존
                self.store.save_session(self.session.session_id, self.session.snapshot(), iso(self.clock()))
        close_engine = getattr(self.engine, "close", None)
        if close_engine:
            close_engine()
