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
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
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
}

object Http {
    val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(3, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .pingInterval(5, TimeUnit.SECONDS)
            .build()
    }

    /** GET /api/info 로 기기인지 확인한다. 실패하면 null */
    suspend fun fetchInfo(host: String, port: Int): DeviceInfo? = withContext(Dispatchers.IO) {
        try {
            val req = Request.Builder().url("http://$host:$port/api/info").build()
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return@use null
                val body = resp.body?.string() ?: return@use null
                Protocol.parseInfo(body, host, port)
            }
        } catch (e: Exception) {
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
        val request = Request.Builder().url(info.wsUrl).build()
        socket = Http.client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                linkState.value = LinkState.CONNECTED
                webSocket.send(Protocol.hello())
                webSocket.send(Protocol.mode(currentMode))
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                Protocol.parse(text)?.let { incoming.tryEmit(it) }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                onDropped(webSocket)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
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
        socket?.send(json)
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
        Triple(10, PostureState.BAD, listOf(PostureIssue.HEAD_DOWN)),
        Triple(8, PostureState.GOOD, emptyList<PostureIssue>()),
        Triple(8, PostureState.BAD, listOf(PostureIssue.TOO_CLOSE)),
        Triple(6, PostureState.NO_PERSON, emptyList<PostureIssue>()),
        Triple(10, PostureState.GOOD, emptyList<PostureIssue>()),
        Triple(9, PostureState.BAD, listOf(PostureIssue.SHOULDER_TILT)),
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
        currentMode = mode
        modeStartedAt = System.currentTimeMillis()
    }

    override fun calibrate() {
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
