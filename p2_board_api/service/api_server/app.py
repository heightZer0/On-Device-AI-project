import hmac
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import APIRouter, Body, Depends, FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from service.api_server.errors import ApiError, error_body
from service.api_server.schemas import (CalibrationConfirmReq, CalibrationStartReq,
                                        CommandReq, ControlReq, DebugLabelReq)
from service.api_server.preview_page import PREVIEW_HTML

log = logging.getLogger("p2.api")


def create_app(hub, cmd, cfg, background=False, mdns=None):
    token = None
    if cfg["auth"]["enabled"]:
        token = cfg["auth"].get("token") or os.environ.get(cfg["auth"]["token_env"])
        if not token:       # 인증이 켜져 있는데 토큰이 없으면 시작하지 않는다(fail closed)
            raise RuntimeError(f"auth.enabled=true 인데 토큰이 없습니다. 환경변수 {cfg['auth']['token_env']} 를 설정하세요.")
    rl = cfg["rate_limit"]["per_client_per_sec"]
    hits = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(app):
        if background:
            hub.start_background()
            hub.warmup()
            if mdns:
                mdns.start()
        yield
        if background:
            hub.stop_background()
            if mdns:
                mdns.stop()

    app = FastAPI(title="Bajahoe P2 Board API", lifespan=lifespan)

    @app.get("/preview", response_class=HTMLResponse, include_in_schema=False)
    def preview_page():
        # The page itself contains no device data; its JPEG/settings calls require the API token.
        return HTMLResponse(PREVIEW_HTML, headers={"Cache-Control": "no-store"})

    def guard(request: Request):
        if rl:
            now, q = time.monotonic(), hits[request.client.host if request.client else "?"]
            while q and now - q[0] > 1:
                q.popleft()
            if len(q) >= rl:
                raise ApiError(429, "RATE_LIMITED", "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.")
            q.append(now)
        if token:
            h = request.headers.get("authorization", "")
            if not h.lower().startswith("bearer "):
                raise ApiError(401, "UNAUTHORIZED", "인증 토큰이 필요해요.")
            if not hmac.compare_digest(h[7:].strip().encode(), token.encode()):
                raise ApiError(403, "FORBIDDEN", "토큰이 올바르지 않아요.")

    # ---------- 오류 형식 ----------
    def err(request, status, code, message, details=None):
        return JSONResponse(error_body(code, message, details, getattr(request.state, "request_id", None)), status_code=status)

    @app.exception_handler(ApiError)
    async def _api(request, e):
        return err(request, e.status, e.code, e.message, e.details)

    @app.exception_handler(RequestValidationError)
    async def _val(request, e):
        fields = [{"loc": [str(x) for x in d.get("loc", [])], "msg": d.get("msg")} for d in e.errors()]
        return err(request, 400, "INVALID_REQUEST", "요청 형식이 올바르지 않아요.", {"errors": fields})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request, e):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(e.status_code, "HTTP_ERROR")
        return err(request, e.status_code, code, str(e.detail))

    @app.exception_handler(Exception)
    async def _any(request, e):
        log.error("unhandled: %s", type(e).__name__)      # 본문·발화 로그 금지
        return err(request, 500, "INTERNAL_ERROR", "서버 내부 오류가 발생했어요.")

    def ok(data, status=200):
        return JSONResponse(hub.scrub(jsonable_encoder(data)), status_code=status)   # S 노출 방지 공통 필터

    def rid_of(request, body):
        rid = getattr(body, "request_id", None)
        request.state.request_id = rid
        return rid

    # ---------- 인증 불필요 ----------
    @app.get("/api/v1/health")
    def health():
        data = hub.health()
        data["updated_at"] = data.get("timestamp")
        return ok(data)

    api = APIRouter(prefix="/api/v1", dependencies=[Depends(guard)])

    @api.get("/status")
    def status():
        return ok(hub.status())

    @api.get("/posture/current")
    def posture():
        return ok(hub.get_posture())                       # 래퍼 없는 PostureState

    @api.get("/preview/frame", include_in_schema=False)
    def preview_frame():
        import cv2
        frame = hub.get_preview_frame()
        encoded, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not encoded:
            raise ApiError(503, "CAMERA_UNAVAILABLE", "웹캠 프레임을 JPEG로 변환할 수 없어요.")
        return Response(content=jpeg.tobytes(), media_type="image/jpeg",
                        headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

    @api.get("/session/current")
    def session_current():
        return ok(hub.get_session())                       # D-20: 세션이 없어도 0값 객체

    @api.get("/session/history")
    def session_history(limit: int = Query(20, ge=1, le=100), cursor: Optional[str] = Query(None)):
        try:
            offset = max(0, int(cursor or "0"))
        except ValueError:
            raise ApiError(400, "INVALID_REQUEST", "페이지 커서 형식이 올바르지 않아요.")
        return ok(hub.history(limit, offset))

    @api.get("/session/calendar")
    def session_calendar(month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
                         timezone_name: str = Query("Asia/Seoul", alias="timezone")):
        return ok(hub.calendar(month, timezone_name))

    @api.get("/settings")
    def settings_get():
        from datetime import datetime, timezone
        return ok({"settings": hub.settings,
                   "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})

    @api.put("/settings")
    def settings_put(patch: dict = Body(...)):
        from datetime import datetime, timezone
        settings = hub.update_settings(patch)
        return ok({"success": True, "settings": settings,
                   "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})

    def control(name, fn):
        def route(request: Request, body: Optional[ControlReq] = Body(default=None)):
            return ok(hub.idem(rid_of(request, body), name, fn))
        api.post(f"/{name}")(route)

    control("monitoring/start", hub.monitoring_start)
    control("monitoring/pause", hub.monitoring_pause)
    control("monitoring/stop", hub.monitoring_stop)
    @api.post("/calibration/start")
    def calibration_start(request: Request, body: CalibrationStartReq = Body(default=CalibrationStartReq())):
        rid = rid_of(request, body)
        return ok(hub.idem(rid, "calibration/start", lambda: hub.calibration_start(body.duration_sec)))

    @api.get("/calibration/preview")
    def calibration_preview(calibration_id: Optional[str] = Query(None)):
        return ok(hub.calibration_preview(calibration_id))

    @api.post("/calibration/confirm")
    def calibration_confirm(request: Request, body: CalibrationConfirmReq = Body(default=CalibrationConfirmReq())):
        rid = rid_of(request, body)
        return ok(hub.idem(rid, "calibration/confirm",
                            lambda: hub.calibration_confirm(body.calibration_id, body.confirm)))

    @api.post("/command")
    def command(request: Request, req: CommandReq):
        result = hub.idem(rid_of(request, req), "command", lambda: cmd.handle(req))
        if result.get("success", result.get("ok", False)):
            return ok(result)
        internal = result.get("code", "ERROR")
        mapping = {
            "INVALID_LLM_COMMAND": (422, "INVALID_LLM_COMMAND"),
            "INVALID_FORMAT": (422, "INVALID_LLM_COMMAND"),
            "NOT_ALLOWED": (422, "INVALID_LLM_COMMAND"),
            "DISABLED": (422, "INVALID_LLM_COMMAND"),
            "BAD_PARAM": (422, "INVALID_LLM_COMMAND"),
            "UNSUPPORTED": (422, "UNSUPPORTED_COMMAND"),
            "MULTI_COMMAND": (422, "MULTI_COMMAND_NOT_SUPPORTED"),
            "INVALID_TIME_RANGE": (422, "INVALID_TIME_RANGE"),
            "CLARIFICATION_TIMEOUT": (408, "CLARIFICATION_TIMEOUT"),
            "ERROR": (500, "INTERNAL_ERROR"),
        }
        status, external = mapping.get(internal, (500, "INTERNAL_ERROR"))
        details = {"tts_text": result.get("tts_text", "")}
        details.update(result.get("result") or {})
        if internal == "PRECONDITION":
            precondition = result.get("precondition")
            if precondition == "CALIBRATION_REQUIRED":
                status, external = 409, "CALIBRATION_REQUIRED"
            elif precondition == "SESSION_NOT_FOUND":
                status, external = 404, "SESSION_NOT_FOUND"
            elif precondition in ("POSTURE_DATA_UNAVAILABLE", "CAMERA_NOT_READY"):
                status, external = (503, "CAMERA_NOT_READY") if precondition == "CAMERA_NOT_READY" else (409, "POSTURE_DATA_UNAVAILABLE")
            else:
                status, external = 409, "INVALID_STATE"
                details["reason"] = (result.get("result") or {}).get("reason") or "state_idle"
        raise ApiError(status, external, result.get("tts_text", "명령을 처리하지 못했어요."), details)

    @api.post("/test-sound")
    def test_sound():
        return ok(hub.test_sound())

    @api.post("/debug/label")
    def debug_label(request: Request, req: DebugLabelReq):
        rid_of(request, req)
        if not hub.settings["debug_mode"]:
            raise ApiError(404, "NOT_FOUND", "찾을 수 없어요.")     # 일반 모드에서는 존재하지 않는 것처럼
        fn = getattr(hub.engine, "set_debug_label", None)
        if not fn:
            raise ApiError(501, "NOT_IMPLEMENTED", "엔진이 라벨 기록을 지원하지 않아요.")
        fn(req.label)
        return ok({"label": req.label})

    app.include_router(api)
    return app
