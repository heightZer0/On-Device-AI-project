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
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

enum class LinkState { DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING }

/** 오렌지파이 기기와의 연결. 실제 기기와 데모 기기가 같은 인터페이스를 쓴다 */
abstract class DeviceClient {
    abstract val info: DeviceInfo

    protected val linkState = MutableStateFlow(LinkState.DISCONNECTED)
    val link: StateFlow<LinkState> = linkState.asStateFlow()

    protected val incoming = MutableSharedFlow<DeviceMessage>(extraBufferCapacity = 64)
    val messages: SharedFlow<DeviceMessage> = incoming.asSharedFlow()

    /** 재연결할 때 다시 보내기 위해 기억해 두는 현재 모드 */
    protected var currentMode: String = Protocol.MODE_IDLE

    abstract fun connect()
    abstract fun close()
    protected abstract fun send(json: String)

    open fun setMode(mode: String) {
        currentMode = mode
        send(Protocol.mode(mode))
    }

    open fun calibrate() = send(Protocol.calibrate())

    open fun session(action: String) = send(Protocol.session(action))

    /** 음성 안내 볼륨과 음소거 상태를 기기에 알린다 */
    open fun config(volume: Int, muted: Boolean) = send(Protocol.config(volume, muted))

    /** 기기 스피커로 확인용 안내음을 한 번 재생한다 */
    open fun testSound() = send(Protocol.testSound())

    /** 공부 일시정지와 다시 시작. 기기가 지원하지 않으면 앱에서만 처리한다 */
    open fun pause() = Unit
    open fun resume() = Unit

    /**
     * 나쁜 자세가 몇 초 이어져야 앱이 경고할지.
     * 기기가 이미 시간 조건을 걸어 판정을 보내는 경우(P2)는 작게 둔다.
     */
    open val warnDelaySec: Int get() = AppViewModel.WARN_DELAY_SEC
}

object Http {
    val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(3, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .pingInterval(5, TimeUnit.SECONDS)
            .build()
    }

    private val JSON_TYPE = "application/json; charset=utf-8".toMediaType()

    sealed interface ProbeResult {
        data class Found(val info: DeviceInfo) : ProbeResult
        data class Failed(val message: String) : ProbeResult
    }

    /**
     * 입력한 주소의 기기 종류를 확인한다.
     * 1) 팀 백엔드(P2): GET /api/v1/health 가 응답하면 토큰으로 /api/v1/status 를 호출해 인증을 확인
     * 2) WebSocket 기기: GET /api/info
     */
    suspend fun probe(host: String, port: Int, token: String): ProbeResult = withContext(Dispatchers.IO) {
        val health = call("GET", "http://$host:$port/api/v1/health", null, null)
        if (health != null && health.first == 200 && health.second?.has("camera") == true) {
            AppLog.received("200 /api/v1/health ${health.second}")
            val cleanToken = token.trim()
            // 서버 인증이 꺼져 있으면 토큰 없이도 된다
            val status = call("GET", "http://$host:$port/api/v1/status", cleanToken, null)
            return@withContext when (status?.first) {
                null -> ProbeResult.Failed("$host:$port 기기에 연결하지 못했어요.")
                401, 403 -> ProbeResult.Failed(
                    if (cleanToken.isEmpty()) "기기 토큰을 입력해 주세요. 서버를 켤 때 정한 BAJAHOE_DEVICE_TOKEN 값이에요."
                    else "토큰이 올바르지 않아요. 서버의 BAJAHOE_DEVICE_TOKEN 값과 같은지 확인해 주세요."
                )
                else -> ProbeResult.Found(
                    DeviceInfo(
                        deviceId = "p2-$host",
                        name = "바자회 기기",
                        version = "P2",
                        host = host,
                        port = port,
                        kind = DeviceKind.P2,
                        token = cleanToken,
                    )
                )
            }
        }
        fetchInfo(host, port)?.let { return@withContext ProbeResult.Found(it) }
        ProbeResult.Failed(
            "$host:$port 에서 바자회 기기를 찾지 못했어요. 같은 Wi-Fi인지, 서버가 켜져 있는지, 포트(팀 서버 기본 8000)가 맞는지 확인해 주세요."
        )
    }

    /** HTTP 요청. (응답 코드, JSON 본문) 을 돌려주고, 연결 자체가 실패하면 null */
    fun call(method: String, url: String, token: String?, body: JSONObject?): Pair<Int, JSONObject?>? = try {
        val builder = Request.Builder().url(url)
        if (!token.isNullOrBlank()) builder.header("Authorization", "Bearer $token")
        if (method == "GET") builder.get()
        else builder.method(method, (body?.toString() ?: "{}").toRequestBody(JSON_TYPE))
        client.newCall(builder.build()).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            val json = try {
                if (text.isBlank()) null else JSONObject(text)
            } catch (e: Exception) {
                null
            }
            resp.code to json
        }
    } catch (e: Exception) {
        null
    }

    /** GET /api/info 로 기기인지 확인한다. 실패하면 null */
    suspend fun fetchInfo(host: String, port: Int): DeviceInfo? = withContext(Dispatchers.IO) {
        try {
            val req = Request.Builder().url("http://$host:$port/api/info").build()
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) {
                    AppLog.w("기기 정보 조회 실패 $host:$port HTTP ${resp.code}")
                    return@use null
                }
                val body = resp.body?.string() ?: return@use null
                AppLog.received(body)
                Protocol.parseInfo(body, host, port)
            }
        } catch (e: Exception) {
            AppLog.w("기기 정보 조회 실패 $host:$port ${e.javaClass.simpleName}: ${e.message}")
            null
        }
    }
}

class WsDeviceClient(
    override val info: DeviceInfo,
    private val scope: CoroutineScope,
) : DeviceClient() {

    private var socket: WebSocket? = null
    private var closedByUser = false
    private var reconnectJob: Job? = null

    override fun connect() {
        closedByUser = false
        open()
    }

    private fun open() {
        linkState.value =
            if (linkState.value == LinkState.DISCONNECTED) LinkState.CONNECTING else LinkState.RECONNECTING
        AppLog.i("WebSocket 연결 시도 ${info.wsUrl}")
        val request = Request.Builder().url(info.wsUrl).build()
        socket = Http.client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                AppLog.i("WebSocket 연결됨 ${info.wsUrl}")
                linkState.value = LinkState.CONNECTED
                sendOn(webSocket, Protocol.hello())
                sendOn(webSocket, Protocol.mode(currentMode))
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                AppLog.received(text)
                val msg = Protocol.parse(text)
                if (msg == null) AppLog.w("해석할 수 없는 메시지: $text")
                else incoming.tryEmit(msg)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                AppLog.i("WebSocket 닫힘 code=$code reason=$reason")
                onDropped(webSocket)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                AppLog.w("WebSocket 연결 실패 ${t.javaClass.simpleName}: ${t.message}")
                onDropped(webSocket)
            }
        })
    }

    private fun onDropped(webSocket: WebSocket) {
        if (webSocket != socket) return
        socket = null
        if (closedByUser) {
            linkState.value = LinkState.DISCONNECTED
            return
        }
        linkState.value = LinkState.RECONNECTING
        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            delay(2000)
            if (!closedByUser) open()
        }
    }

    override fun send(json: String) {
        val s = socket
        if (s == null) {
            AppLog.w("연결이 없어 보내지 못함: $json")
            return
        }
        sendOn(s, json)
    }

    private fun sendOn(webSocket: WebSocket, json: String) {
        AppLog.sent(json)
        webSocket.send(json)
    }

    override fun close() {
        closedByUser = true
        reconnectJob?.cancel()
        socket?.close(1000, "bye")
        socket = null
        linkState.value = LinkState.DISCONNECTED
    }
}

/** 보드 없이 앱을 둘러볼 수 있는 가짜 기기 */
class DemoDeviceClient(private val scope: CoroutineScope) : DeviceClient() {

    override val info = DeviceInfo(
        deviceId = "demo",
        name = "데모 기기",
        version = "demo",
        host = "demo",
        port = 0,
        isDemo = true,
    )

    private var loopJob: Job? = null
    private var modeStartedAt = System.currentTimeMillis()

    // 지속 초, 상태, 원인
    private val scenario = listOf(
        Triple(15, PostureState.GOOD, emptyList<PostureIssue>()),
        Triple(10, PostureState.BAD, listOf(PostureIssue.FORWARD_HEAD)),
        Triple(8, PostureState.GOOD, emptyList<PostureIssue>()),
        Triple(8, PostureState.BAD, listOf(PostureIssue.HEAD_DOWN)),
        Triple(6, PostureState.NO_PERSON, emptyList<PostureIssue>()),
        Triple(10, PostureState.GOOD, emptyList<PostureIssue>()),
        Triple(9, PostureState.BAD, listOf(PostureIssue.SLOUCH)),
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
            Protocol.MODE_CALIBRATE -> incoming.tryEmit(
                DeviceMessage.Detect(
                    face = elapsed > 1.0,
                    shoulders = elapsed > 1.5,
                    stable = elapsed > 2.5,
                )
            )
            Protocol.MODE_MONITOR -> {
                val total = scenario.sumOf { it.first }
                var t = elapsed % total
                var step = scenario.first()
                for (s in scenario) {
                    step = s
                    if (t < s.first) break
                    t -= s.first
                }
                val score = when (step.second) {
                    PostureState.GOOD -> 90
                    PostureState.BAD -> 58
                    else -> 0
                }
                incoming.tryEmit(DeviceMessage.Status(step.second, score, step.third))
            }
        }
    }

    override fun setMode(mode: String) {
        AppLog.i("[데모] mode=$mode")
        currentMode = mode
        modeStartedAt = System.currentTimeMillis()
    }

    override fun calibrate() {
        AppLog.i("[데모] 기준 자세 저장 요청")
        scope.launch {
            delay(700)
            incoming.tryEmit(DeviceMessage.Calibration(ok = true, reason = null))
        }
    }

    override fun session(action: String) = Unit

    override fun send(json: String) = Unit

    override fun close() {
        loopJob?.cancel()
        linkState.value = LinkState.DISCONNECTED
    }
}
