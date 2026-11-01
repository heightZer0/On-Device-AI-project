package com.example.bajahoe

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

enum class LinkState { DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING }

/** P2 REST API와 데모 기기를 같은 화면 인터페이스로 제공한다. */
abstract class DeviceClient {
    abstract val info: DeviceInfo
    protected val linkState = MutableStateFlow(LinkState.DISCONNECTED)
    val link: StateFlow<LinkState> = linkState.asStateFlow()
    protected val incoming = MutableSharedFlow<DeviceMessage>(extraBufferCapacity = 64)
    val messages: SharedFlow<DeviceMessage> = incoming.asSharedFlow()
    protected var currentMode: String = Protocol.MODE_IDLE
    val mode: String get() = currentMode

    abstract fun connect()
    abstract fun close()
    open fun setMode(mode: String) { currentMode = mode }
    open fun calibrate() = Unit
    open fun retryCalibration() = setMode(Protocol.MODE_CALIBRATE)
    open fun session(action: String) = Unit
    open fun pauseMonitoring() = Unit
    open fun resumeMonitoring() = Unit
    open fun config(volume: Int, muted: Boolean) = Unit
    open fun testSound() = Unit
}

object Http {
    val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(3, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .writeTimeout(10, TimeUnit.SECONDS)
            .build()
    }

    /** Health is public; authenticated /status confirms both that this is P2 and that the token works. */
    suspend fun fetchInfo(host: String, port: Int, token: String): DeviceInfo? = withContext(Dispatchers.IO) {
        try {
            val base = baseUrl(host, port)
            val health = execute(Request.Builder().url("$base/api/v1/health").get().build())
            if (!health.optString("status").let { it == "ok" || it == "degraded" }) return@withContext null
            execute(Request.Builder().url("$base/api/v1/status").header("Authorization", "Bearer $token").get().build())
            DeviceInfo(
                deviceId = "bajahoe-${host.hashCode().toUInt().toString(16)}",
                name = "바자회 기기",
                version = "P2 REST",
                host = host,
                port = port,
            )
        } catch (_: Exception) {
            null
        }
    }

    internal fun baseUrl(host: String, port: Int): String {
        val authority = if (host.contains(":") && !host.startsWith("[")) "[$host]" else host
        return "http://$authority:$port"
    }

    internal suspend fun execute(request: Request): JSONObject = withContext(Dispatchers.IO) {
        client.newCall(request).execute().use { response ->
            val raw = response.body?.string().orEmpty()
            val body = try { JSONObject(raw) } catch (_: Exception) { JSONObject() }
            if (!response.isSuccessful) {
                val message = body.optJSONObject("error")?.optString("message")
                    ?.takeIf { !it.isNullOrBlank() } ?: "기기 요청에 실패했어요. (${response.code})"
                throw DeviceRequestException(message, body.optJSONObject("error")?.optString("code"))
            }
            body
        }
    }
}

private class DeviceRequestException(message: String, val errorCode: String? = null) : Exception(message)

/** P2 REST 연결. 상태는 1초 간격으로 조회하고, 네트워크 오류에는 1·2·4·10초 간격으로 재접속한다. */
class RestDeviceClient(
    override val info: DeviceInfo,
    private val token: String,
    private val scope: CoroutineScope,
) : DeviceClient() {
    private val base = Http.baseUrl(info.host, info.port)
    private val jsonType = "application/json; charset=utf-8".toMediaType()
    private var pollJob: Job? = null
    private var calibrationJob: Job? = null
    private var closed = false
    private var calibrationId: String? = null
    private var calibrationFinished = false
    private var appliedMode: String? = null
    private val modeMutex = Mutex()

    override fun connect() {
        closed = false
        linkState.value = LinkState.CONNECTING
        pollJob?.cancel()
        pollJob = scope.launch {
            var retry = 0
            while (isActive && !closed) {
                try {
                    val status = get("/api/v1/status")
                    linkState.value = LinkState.CONNECTED
                    incoming.tryEmit(Protocol.parseApiStatus(status))
                    val serverState = status.optString("system_state")
                    reconcileMode(status)
                    applyModeIfNeeded()
                    retry = 0
                    delay(1000)
                } catch (e: Exception) {
                    linkState.value = LinkState.RECONNECTING
                    val waitSec = listOf(1L, 2L, 4L, 10L)[retry.coerceAtMost(3)]
                    retry = (retry + 1).coerceAtMost(3)
                    delay(waitSec * 1000)
                }
            }
        }
    }

    override fun setMode(mode: String) {
        if (mode != currentMode && mode == Protocol.MODE_CALIBRATE) calibrationFinished = false
        currentMode = mode
        if (linkState.value == LinkState.CONNECTED) scope.launch { applyModeIfNeeded() }
    }

    private suspend fun applyModeIfNeeded() {
        modeMutex.withLock {
            val mode = currentMode
            if (appliedMode != mode) {
                when (mode) {
                    Protocol.MODE_CALIBRATE -> beginCalibration()
                    Protocol.MODE_MONITOR -> post("/api/v1/monitoring/start", controlBody())
                    else -> {
                        post("/api/v1/monitoring/stop", controlBody())
                    }
                }
                appliedMode = mode
            }
        }
    }

    private fun reconcileMode(status: JSONObject) {
        if (currentMode == Protocol.MODE_CALIBRATE && calibrationFinished) return
        val serverState = status.optString("system_state")
        val needsMode = when (currentMode) {
            Protocol.MODE_CALIBRATE -> serverState != "CALIBRATING"
            Protocol.MODE_MONITOR -> serverState != "MONITORING" && serverState != "PAUSED"
            else -> serverState == "MONITORING" || serverState == "PAUSED"
        }
        if (needsMode) {
            appliedMode = null
            if (currentMode == Protocol.MODE_CALIBRATE) calibrationId = null
        }
    }

    private suspend fun beginCalibration() {
        calibrationFinished = false
        calibrationJob?.cancel()
        val response = post("/api/v1/calibration/start", JSONObject()
            .put("duration_sec", 5)
            .put("request_id", requestId()))
        calibrationId = response.optString("calibration_id").takeIf { it.isNotBlank() }
            ?: throw DeviceRequestException("캘리브레이션을 시작하지 못했어요.")
        // Hub wraps the P1 result in `detection`; P1 itself nests sides under `detected`.
        val detection = response.optJSONObject("detection")
        val sides = detection?.optJSONObject("detected") ?: detection
        val left = sides?.optJSONObject("left")
        val right = sides?.optJSONObject("right")
        val ear = left?.optBoolean("ear") == true || right?.optBoolean("ear") == true
        val shoulder = left?.optBoolean("shoulder") == true || right?.optBoolean("shoulder") == true
        incoming.tryEmit(DeviceMessage.Detect(ear, shoulder, false))

        calibrationJob = scope.launch {
            while (isActive && !closed) {
                try {
                    val preview = get("/api/v1/calibration/preview?calibration_id=$calibrationId")
                    val state = preview.optString("state").uppercase()
                    when (state) {
                        "READY" -> {
                            incoming.tryEmit(DeviceMessage.Detect(true, true, true))
                            return@launch
                        }
                        "FAILED" -> {
                            val detail = preview.optJSONObject("preview")
                            val error = detail?.optString("error")?.takeIf { it.isNotBlank() } ?: "calibration_failed"
                            incoming.tryEmit(DeviceMessage.Error(error, Protocol.calibrationReasonText(error)))
                            return@launch
                        }
                    }
                    delay(1000)
                } catch (e: Exception) {
                    incoming.tryEmit(DeviceMessage.Error("calibration_unavailable", e.message ?: "캘리브레이션 상태를 읽지 못했어요."))
                    return@launch
                }
            }
        }
    }

    override fun calibrate() {
        val id = calibrationId ?: run {
            incoming.tryEmit(DeviceMessage.Calibration(false, "calibration_not_started"))
            return
        }
        scope.launch {
            try {
                val result = post("/api/v1/calibration/confirm", JSONObject()
                    .put("calibration_id", id).put("confirm", true).put("request_id", requestId()))
                val ok = result.optBoolean("calibrated", result.optBoolean("saved", false))
                if (ok) {
                    calibrationId = null
                    calibrationJob?.cancel()
                }
                calibrationFinished = ok
                incoming.tryEmit(DeviceMessage.Calibration(ok, if (ok) null else "calibration_failed"))
            } catch (e: Exception) {
                incoming.tryEmit(DeviceMessage.Calibration(false, (e as? DeviceRequestException)?.errorCode ?: "calibration_failed"))
            }
        }
    }

    override fun retryCalibration() {
        scope.launch {
            try {
                calibrationJob?.cancel()
                calibrationId?.let { id ->
                    post("/api/v1/calibration/confirm", JSONObject()
                        .put("calibration_id", id).put("confirm", false).put("request_id", requestId()))
                }
                calibrationId = null
                appliedMode = null
                beginCalibration()
                appliedMode = Protocol.MODE_CALIBRATE
            } catch (e: Exception) {
                emitError(e)
            }
        }
    }

    override fun pauseMonitoring() {
        scope.launch { runCatching { post("/api/v1/monitoring/pause", controlBody()) }
            .onFailure { emitError(it) } }
    }

    override fun resumeMonitoring() {
        scope.launch { runCatching { post("/api/v1/monitoring/start", controlBody()) }
            .onFailure { emitError(it) } }
    }

    override fun config(volume: Int, muted: Boolean) {
        scope.launch {
            val body = JSONObject()
                .put("tts_volume", volume.coerceIn(0, 100) / 100.0)
                .put("voice_feedback_enabled", !muted)
            runCatching { put("/api/v1/settings", body) }.onFailure { emitError(it) }
        }
    }

    override fun testSound() {
        scope.launch { runCatching { post("/api/v1/test-sound", controlBody()) }.onFailure { emitError(it) } }
    }

    private suspend fun get(path: String): JSONObject =
        Http.execute(authRequest(path).get().build())

    private suspend fun post(path: String, body: JSONObject): JSONObject =
        Http.execute(authRequest(path).post(body.toString().toRequestBody(jsonType)).build())

    private suspend fun put(path: String, body: JSONObject): JSONObject =
        Http.execute(authRequest(path).put(body.toString().toRequestBody(jsonType)).build())

    private fun authRequest(path: String): Request.Builder = Request.Builder()
        .url("$base$path")
        .header("Authorization", "Bearer $token")
        .header("Accept", "application/json")

    private fun controlBody() = JSONObject().put("source", "app").put("request_id", requestId())
    private fun requestId() = UUID.randomUUID().toString()

    private fun emitError(error: Throwable) {
        incoming.tryEmit(DeviceMessage.Error(
            (error as? DeviceRequestException)?.errorCode ?: "request_failed",
            error.message ?: "기기 요청을 처리하지 못했어요.",
        ))
    }

    override fun close() {
        closed = true
        pollJob?.cancel()
        calibrationJob?.cancel()
        linkState.value = LinkState.DISCONNECTED
    }
}

/** 보드 없이 앱 화면을 둘러볼 수 있는 시나리오 기기 */
class DemoDeviceClient(private val scope: CoroutineScope) : DeviceClient() {
    override val info = DeviceInfo("demo", "데모 기기", "demo", "demo", 0, isDemo = true)
    private var loopJob: Job? = null
    private var modeStartedAt = System.currentTimeMillis()
    private val scenario = listOf(
        Triple(15, PostureState.GOOD, emptyList<PostureIssue>()),
        Triple(10, PostureState.BAD, listOf(PostureIssue.HEAD_DOWN)),
        Triple(8, PostureState.GOOD, emptyList<PostureIssue>()),
        Triple(8, PostureState.BAD, listOf(PostureIssue.TOO_CLOSE)),
        Triple(6, PostureState.UNKNOWN, emptyList<PostureIssue>()),
        Triple(10, PostureState.GOOD, emptyList<PostureIssue>()),
    )

    override fun connect() {
        linkState.value = LinkState.CONNECTING
        loopJob?.cancel()
        loopJob = scope.launch {
            delay(500)
            linkState.value = LinkState.CONNECTED
            while (isActive) {
                delay(500)
                emitTick()
            }
        }
    }

    private fun emitTick() {
        val elapsed = (System.currentTimeMillis() - modeStartedAt) / 1000.0
        when (currentMode) {
            Protocol.MODE_CALIBRATE -> incoming.tryEmit(DeviceMessage.Detect(elapsed > 1.0, elapsed > 1.5, elapsed > 2.5))
            Protocol.MODE_MONITOR -> {
                val total = scenario.sumOf { it.first }
                var t = elapsed % total
                var step = scenario.first()
                for (s in scenario) { step = s; if (t < s.first) break; t -= s.first }
                val score = when (step.second) { PostureState.GOOD -> 90; PostureState.BAD -> 58; else -> -1 }
                incoming.tryEmit(DeviceMessage.Status(step.second, score, step.third))
            }
        }
    }

    override fun setMode(mode: String) { currentMode = mode; modeStartedAt = System.currentTimeMillis() }
    override fun retryCalibration() { setMode(Protocol.MODE_CALIBRATE) }
    override fun calibrate() { scope.launch { delay(300); incoming.tryEmit(DeviceMessage.Calibration(true, null)) } }
    override fun close() { loopJob?.cancel(); linkState.value = LinkState.DISCONNECTED }
}
