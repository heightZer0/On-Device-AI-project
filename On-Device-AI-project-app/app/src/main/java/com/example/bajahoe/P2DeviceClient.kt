package com.example.bajahoe

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.UUID

/**
 * 팀 백엔드(p2_board_api) 연결.
 *
 * - REST API, 모든 요청에 Authorization: Bearer <토큰>
 * - 실시간 상태는 GET /api/v1/status 를 1초마다 조회 (서버 poll_hint_sec)
 * - 앱 화면이 쓰는 DeviceMessage(Detect, Calibration, Status, Error)로 바꿔서 전달하므로
 *   화면 코드는 WebSocket 기기와 똑같이 동작한다.
 */
class P2DeviceClient(
    override val info: DeviceInfo,
    private val scope: CoroutineScope,
) : DeviceClient() {

    private val base = "http://${info.host}:${info.port}/api/v1"
    private val mutex = Mutex()
    private var pollJob: Job? = null
    private var closed = false
    private var failures = 0

    // 기준 자세 측정
    private var calibrationId: String? = null
    private var restartAt = 0L
    private var beginEar = false
    private var beginShoulder = false

    // 미리보기를 켜기 전 서버 설정 (나갈 때 되돌림)
    private var previewRestore: JSONObject? = null

    /** 서버가 앞으로 나온 자세를 일정 시간 유지해야 attention 을 보내므로 앱은 추가로 거의 기다리지 않는다 */
    override val warnDelaySec: Int get() = 1

    override fun connect() {
        closed = false
        linkState.value = LinkState.CONNECTING
        pollJob?.cancel()
        pollJob = scope.launch(Dispatchers.IO) {
            while (isActive && !closed) {
                poll()
                delay(if (currentMode == Protocol.MODE_CALIBRATE) 500L else 1000L)
            }
        }
    }

    override fun close() {
        closed = true
        pollJob?.cancel()
        if (calibrationId != null || previewRestore != null) {
            scope.launch(Dispatchers.IO) {
                mutex.withLock {
                    cancelCalibration()
                    restorePreview()
                }
            }
        }
        linkState.value = LinkState.DISCONNECTED
    }

    /** P2 는 WebSocket 메시지를 쓰지 않는다 */
    override fun send(json: String) = Unit

    // ======================= HTTP =======================

    private suspend fun api(method: String, path: String, body: JSONObject? = null): Pair<Int, JSONObject?>? =
        withContext(Dispatchers.IO) {
            AppLog.sent("$method $path${if (body != null) " $body" else ""}")
            val r = Http.call(method, base + path, info.token, body)
            if (r == null) AppLog.w("기기 요청 실패 $method $path")
            else AppLog.received("${r.first} $path ${r.second ?: ""}")
            r
        }

    /** 제어 요청 공통 본문 */
    private fun control(): JSONObject =
        JSONObject().put("source", "app").put("request_id", UUID.randomUUID().toString())

    private fun errorCode(r: Pair<Int, JSONObject?>?): String =
        r?.second?.optJSONObject("error")?.optString("code").orEmpty()

    private fun errorMessage(r: Pair<Int, JSONObject?>?): String =
        r?.second?.optJSONObject("error")?.optString("message")?.takeIf { it.isNotBlank() }
            ?: "기기가 요청을 처리하지 못했어요."

    private fun launchLocked(block: suspend () -> Unit) {
        scope.launch(Dispatchers.IO) { mutex.withLock { block() } }
    }

    // ======================= 상태 조회 =======================

    private suspend fun poll() = mutex.withLock {
        val r = api("GET", "/status")
        if (r == null) {
            failures++
            if (failures >= 2) linkState.value = LinkState.RECONNECTING
            return@withLock
        }
        if (r.first == 401 || r.first == 403) {
            linkState.value = LinkState.RECONNECTING
            incoming.tryEmit(DeviceMessage.Error("UNAUTHORIZED", "기기 토큰이 올바르지 않아요."))
            return@withLock
        }
        failures = 0
        linkState.value = LinkState.CONNECTED
        val body = r.second
        if (r.first != 200 || body == null) {
            // 503 AI_MODULE_UNAVAILABLE 등: 판정 보류
            if (currentMode == Protocol.MODE_MONITOR) {
                incoming.tryEmit(DeviceMessage.Status(PostureState.UNKNOWN, -1, emptyList()))
            }
            return@withLock
        }
        val posture = body.optJSONObject("posture")
        when (currentMode) {
            Protocol.MODE_MONITOR -> incoming.tryEmit(toStatus(posture))
            Protocol.MODE_CALIBRATE -> pollCalibration(body.optString("system_state"), posture)
        }
    }

    /** 서버 자세 상태 → 앱 상태. attention 의 원인은 머리 상대 위치(거북목) 하나다 */
    private fun toStatus(p: JSONObject?): DeviceMessage.Status {
        val score = ((p?.optDouble("confidence", 0.0) ?: 0.0) * 100).toInt()
        return when (p?.optString("state")) {
            "normal" -> DeviceMessage.Status(PostureState.GOOD, score, emptyList())
            "attention" -> DeviceMessage.Status(PostureState.BAD, score, listOf(PostureIssue.FORWARD_HEAD))
            "unavailable" -> DeviceMessage.Status(PostureState.NO_PERSON, 0, emptyList())
            else -> DeviceMessage.Status(PostureState.UNKNOWN, -1, emptyList())
        }
    }

    // ======================= 기준 자세 측정 =======================

    private fun earOk(p: JSONObject?) = p?.optJSONObject("landmarks_ok")?.optBoolean("ear") == true || beginEar
    private fun shoulderOk(p: JSONObject?) =
        p?.optJSONObject("landmarks_ok")?.optBoolean("shoulder") == true || beginShoulder

    private suspend fun pollCalibration(systemState: String, posture: JSONObject?) {
        val id = calibrationId
        if (id == null || systemState != "CALIBRATING") {
            calibrationId = null
            if (System.currentTimeMillis() >= restartAt) startCalibration(systemState)
            return
        }
        val r = api("GET", "/calibration/preview?calibration_id=$id")
        val b = r?.second
        if (r == null || r.first != 200 || b == null) {
            if (r?.first == 404 || r?.first == 409) calibrationId = null
            return
        }
        when (b.optString("state")) {
            "READY" -> incoming.tryEmit(DeviceMessage.Detect(true, true, true, progress = 1f))
            "FAILED" -> {
                val reason = b.optJSONObject("preview")?.optString("error")?.takeIf { it.isNotBlank() }
                    ?: "too_few_frames"
                AppLog.i("기준 자세 측정 실패: $reason. 2초 뒤 다시 측정")
                incoming.tryEmit(
                    DeviceMessage.Detect(earOk(posture), shoulderOk(posture), false, 0f, failReason = reason)
                )
                cancelCalibration()
                restartAt = System.currentTimeMillis() + 2000
            }
            else -> {
                val progress = b.optDouble("progress", 0.0).toFloat()
                incoming.tryEmit(DeviceMessage.Detect(earOk(posture), shoulderOk(posture), false, progress))
            }
        }
    }

    private suspend fun startCalibration(systemState: String) {
        // 앱이 비정상 종료되어 서버에 남은 작업 정리
        if (systemState == "MONITORING" || systemState == "PAUSED") api("POST", "/monitoring/stop", control())
        if (systemState == "CALIBRATING") {
            api("POST", "/calibration/confirm", control().put("confirm", false))
        }
        enablePreview()
        val r = api("POST", "/calibration/start", control().put("duration_sec", 5))
        val b = r?.second
        if (r?.first == 200 && b != null) {
            calibrationId = b.optString("calibration_id").takeIf { it.isNotBlank() }
            val det = b.optJSONObject("detection")?.optJSONObject("detected")
            val left = det?.optJSONObject("left")
            val right = det?.optJSONObject("right")
            beginEar = left?.optBoolean("ear") == true || right?.optBoolean("ear") == true
            beginShoulder = left?.optBoolean("shoulder") == true || right?.optBoolean("shoulder") == true
            AppLog.i("기준 자세 측정 시작 $calibrationId (귀 $beginEar, 어깨 $beginShoulder)")
            incoming.tryEmit(DeviceMessage.Detect(beginEar, beginShoulder, false, progress = 0f))
        } else {
            restartAt = System.currentTimeMillis() + 3000
            val code = errorCode(r).ifBlank { if (r == null) "timeout" else "CAMERA_NOT_READY" }
            AppLog.w("기준 자세 측정 시작 실패 $code ${errorMessage(r)}")
            incoming.tryEmit(DeviceMessage.Detect(false, false, false, 0f, failReason = code))
        }
    }

    private suspend fun cancelCalibration() {
        val id = calibrationId ?: return
        calibrationId = null
        api("POST", "/calibration/confirm", control().put("calibration_id", id).put("confirm", false))
    }

    override fun setMode(mode: String) {
        val prev = currentMode
        currentMode = mode
        when {
            mode == Protocol.MODE_CALIBRATE -> restartAt = 0L
            // 공부 중에도 내 모습을 볼 수 있게 미리보기를 켜 둔다
            mode == Protocol.MODE_MONITOR -> launchLocked {
                cancelCalibration()
                enablePreview()
            }
            prev == Protocol.MODE_CALIBRATE || prev == Protocol.MODE_MONITOR -> launchLocked {
                cancelCalibration()
                restorePreview()
            }
        }
    }

    override fun calibrate() = launchLocked {
        val id = calibrationId
        val r = api("POST", "/calibration/confirm", control().put("calibration_id", id).put("confirm", true))
        val b = r?.second
        val msg = when {
            r == null -> DeviceMessage.Calibration(false, "timeout")
            r.first == 200 && b?.optBoolean("saved") == true -> {
                calibrationId = null
                // 화면이 바뀌기 전에 상태 조회가 측정을 다시 시작하지 않도록 막아 둔다
                restartAt = Long.MAX_VALUE
                DeviceMessage.Calibration(true, null)
            }
            r.first == 200 -> DeviceMessage.Calibration(
                false,
                b?.optJSONObject("calibration")?.optString("error")?.takeIf { it.isNotBlank() } ?: "not_ready",
            )
            else -> DeviceMessage.Calibration(false, errorCode(r).ifBlank { "INVALID_STATE" })
        }
        incoming.tryEmit(msg)
    }

    // ======================= 카메라 미리보기 =======================

    /** 서버는 debug_mode 와 preview_stream_enabled 가 켜져 있을 때만 /preview/frame 을 준다 */
    private suspend fun enablePreview() {
        if (previewRestore != null) return
        val cur = api("GET", "/settings")?.second?.optJSONObject("settings") ?: return
        val debug = cur.optBoolean("debug_mode")
        val stream = cur.optBoolean("preview_stream_enabled")
        if (debug && stream) return
        val r = api("PUT", "/settings", JSONObject().put("debug_mode", true).put("preview_stream_enabled", true))
        if (r?.first == 200) {
            previewRestore = JSONObject().put("debug_mode", debug).put("preview_stream_enabled", stream)
        }
    }

    private suspend fun restorePreview() {
        val restore = previewRestore ?: return
        previewRestore = null
        api("PUT", "/settings", restore)
    }

    // ======================= 공부 세션 =======================

    override fun session(action: String) = launchLocked {
        val path = if (action == "start") "/monitoring/start" else "/monitoring/stop"
        val r = api("POST", path, control())
        if (r == null || r.first != 200) {
            incoming.tryEmit(DeviceMessage.Error(errorCode(r).ifBlank { "timeout" }, errorMessage(r)))
        }
    }

    override fun pause() = launchLocked { api("POST", "/monitoring/pause", control()) }

    override fun resume() = launchLocked { api("POST", "/monitoring/start", control()) }

    // ======================= 설정 =======================

    /** 앱 볼륨 0~100 → 서버 tts_volume 0~1, 음소거 → voice_feedback_enabled */
    override fun config(volume: Int, muted: Boolean) = launchLocked {
        api(
            "PUT", "/settings",
            JSONObject().put("tts_volume", volume.coerceIn(0, 100) / 100.0).put("voice_feedback_enabled", !muted),
        )
    }

    override fun testSound() = launchLocked {
        val r = api("POST", "/test-sound")
        if (r == null || r.first != 200) {
            incoming.tryEmit(DeviceMessage.Error(errorCode(r).ifBlank { "timeout" }, errorMessage(r)))
        }
    }
}
