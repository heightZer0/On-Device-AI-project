package com.example.bajahoe

import android.app.Application
import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.YearMonth

enum class Screen {
    SPLASH, CONNECT, SETUP_INITIAL, SETUP_RESET, HOME, STUDY, RESULT, PROFILE, SETTINGS, CALENDAR
}

/** 학습 모드 중 화면에 보여줄 값 */
data class StudyUi(
    /** 이번 세션 집중 시간 */
    val focusSec: Int = 0,
    /** 오늘 하루 누적 집중 시간. 껐다 켜도 이어진다 */
    val todayFocusSec: Int = 0,
    val goodSec: Int = 0,
    val awaySec: Int = 0,
    val warnings: Int = 0,
    val badStreak: Int = 0,
    val state: PostureState = PostureState.UNKNOWN,
    val issues: List<PostureIssue> = emptyList(),
    val paused: Boolean = false,
    val stale: Boolean = true,
    val alert: Boolean = false,
)

/** 글씨 크기 선택지 */
enum class TextSize(val label: String, val scale: Float) {
    SMALL("작게", 0.9f),
    NORMAL("보통", 1.0f),
    LARGE("크게", 1.15f),
    XLARGE("아주 크게", 1.3f);

    companion object {
        fun from(scale: Float): TextSize = entries.minByOrNull { kotlin.math.abs(it.scale - scale) } ?: NORMAL
    }
}

class AppViewModel(app: Application) : AndroidViewModel(app) {

    companion object {
        /** 이 시간 이상 나쁜 자세가 이어지면 경고 */
        const val WARN_DELAY_SEC = 5

        /** 마지막 status 이후 이 시간이 지나면 판정 보류 */
        const val STALE_MS = 3000L

        /** 공부 중 기록을 저장소에 반영하는 간격(초). 앱이 갑자기 꺼져도 이만큼만 잃는다 */
        const val FLUSH_EVERY_SEC = 15
    }

    private val storage = Storage(app)
    val discovery = DeviceDiscovery(app)

    private var currentScreen by mutableStateOf(Screen.SPLASH)
    var screen: Screen
        get() = currentScreen
        private set(value) {
            if (currentScreen != value) AppLog.i("화면 이동 $currentScreen → $value")
            currentScreen = value
        }

    var nickname by mutableStateOf(storage.nickname)
        private set

    // ---------- 설정 ----------
    var volume by mutableStateOf(storage.volume)
        private set
    var muted by mutableStateOf(storage.muted)
        private set
    var textSize by mutableStateOf(TextSize.from(storage.textScale))
        private set
    private var volumeSendJob: Job? = null

    // ---------- 기기 연결 ----------
    var client by mutableStateOf<DeviceClient?>(null)
        private set
    var link by mutableStateOf(LinkState.DISCONNECTED)
        private set
    var connecting by mutableStateOf(false)
        private set
    var connectError by mutableStateOf<String?>(null)
        private set

    private var clientJobs: List<Job> = emptyList()

    // ---------- 자세설정 ----------
    var detect by mutableStateOf<DeviceMessage.Detect?>(null)
        private set
    var calibrating by mutableStateOf(false)
        private set
    var calibrationError by mutableStateOf<String?>(null)
        private set
    private var calibrationTimeout: Job? = null

    // ---------- 학습 모드 ----------
    var study by mutableStateOf(StudyUi())
        private set
    var lastResult by mutableStateOf<SessionRecord?>(null)
        private set
    var today by mutableStateOf(storage.today())
        private set

    private var lastStatus: DeviceMessage.Status? = null
    private var lastStatusAt = 0L
    private val issueSeconds = mutableMapOf<PostureIssue, Int>()
    private var tickJob: Job? = null
    private var sessionStartedAt = 0L

    // 아직 저장소에 반영하지 않은 증가분
    private var pendingDate: LocalDate = LocalDate.now()
    private var pendFocus = 0
    private var pendGood = 0
    private var pendAway = 0
    private var pendWarn = 0
    private var ticksSinceFlush = 0

    // ---------- 캘린더 ----------
    var calendarMonth by mutableStateOf(YearMonth.now())
        private set
    var monthStats by mutableStateOf<Map<LocalDate, DayStat>>(emptyMap())
        private set
    var selectedDate by mutableStateOf(LocalDate.now())
        private set
    var selectedSessions by mutableStateOf<List<SessionRecord>>(emptyList())
        private set

    // ================= 화면 이동 =================

    private var splashHandled = false

    fun onSplashFinished() {
        if (splashHandled) return
        splashHandled = true
        val saved = storage.savedDevice()
        when {
            saved == null -> screen = Screen.CONNECT
            saved.demo -> {
                useClient(DemoDeviceClient(viewModelScope))
                goSetup(initial = true)
            }
            saved.kind == DeviceKind.P2 -> {
                // 팀 서버는 상태 조회를 계속 반복하므로 서버가 늦게 켜져도 알아서 붙는다
                val info = DeviceInfo(
                    "p2-${saved.host}", "바자회 기기", "P2", saved.host, saved.port,
                    kind = DeviceKind.P2, token = saved.token,
                )
                useClient(makeClient(info))
                goSetup(initial = true)
            }
            else -> viewModelScope.launch {
                // 저장된 기기로 바로 연결. 정보 확인이 안 돼도 재연결을 계속 시도한다
                val info = Http.fetchInfo(saved.host, saved.port)
                    ?: DeviceInfo("unknown", "바자회 기기", "?", saved.host, saved.port)
                useClient(makeClient(info))
                goSetup(initial = true)
            }
        }
    }

    fun openConnect() {
        connectError = null
        screen = Screen.CONNECT
    }

    fun goHome() {
        client?.setMode(Protocol.MODE_IDLE)
        today = storage.today()
        screen = Screen.HOME
    }

    fun openReset() = goSetup(initial = false)

    fun openProfile() {
        screen = Screen.PROFILE
    }

    fun openSettings() {
        screen = Screen.SETTINGS
    }

    private fun goSetup(initial: Boolean) {
        detect = null
        calibrating = false
        calibrationError = null
        client?.setMode(Protocol.MODE_CALIBRATE)
        screen = if (initial) Screen.SETUP_INITIAL else Screen.SETUP_RESET
    }

    // ================= 연결 =================

    /** 연결 화면 토큰 칸에 미리 넣어 둘 값 */
    val lastToken: String get() = storage.lastToken

    private fun makeClient(info: DeviceInfo): DeviceClient =
        if (info.isP2) P2DeviceClient(info, viewModelScope) else WsDeviceClient(info, viewModelScope)

    fun connectTo(host: String, port: Int, token: String = "") {
        if (connecting) return
        val cleanHost = host.trim()
        if (cleanHost.isEmpty()) {
            connectError = "기기 IP 주소를 입력해 주세요."
            return
        }
        connecting = true
        connectError = null
        if (token.isNotBlank()) storage.lastToken = token.trim()
        viewModelScope.launch {
            val result = Http.probe(cleanHost, port, token)
            connecting = false
            when (result) {
                is Http.ProbeResult.Failed -> {
                    AppLog.w("기기 연결 실패 $cleanHost:$port ${result.message}")
                    connectError = result.message
                }
                is Http.ProbeResult.Found -> {
                    AppLog.i("기기 확인 ${result.info.kind} ${result.info.address}")
                    storage.saveDevice(result.info)
                    useClient(makeClient(result.info))
                    goSetup(initial = true)
                }
            }
        }
    }

    fun connectDemo() {
        val demo = DemoDeviceClient(viewModelScope)
        storage.saveDevice(demo.info)
        useClient(demo)
        goSetup(initial = true)
    }

    fun forgetDevice() {
        stopTicking()
        client?.close()
        clientJobs.forEach { it.cancel() }
        client = null
        link = LinkState.DISCONNECTED
        storage.forgetDevice()
        openConnect()
    }

    private fun useClient(newClient: DeviceClient) {
        client?.close()
        clientJobs.forEach { it.cancel() }
        client = newClient
        clientJobs = listOf(
            viewModelScope.launch {
                newClient.link.collect {
                    AppLog.i("기기 연결 상태: $it (${newClient.info.address})")
                    link = it
                    // 연결될 때마다 기기에 앱 설정을 알려준다
                    if (it == LinkState.CONNECTED) newClient.config(volume, muted)
                }
            },
            viewModelScope.launch { newClient.messages.collect { onMessage(it) } },
        )
        newClient.connect()
    }

    private fun onMessage(msg: DeviceMessage) {
        when (msg) {
            is DeviceMessage.Detect -> {
                detect = msg
                // 측정이 실패하면 이유를 보여 주고, 다시 측정이 시작되면 지운다
                if (msg.failReason != null) calibrationError = Protocol.calibrationReasonText(msg.failReason)
                else if (msg.progress == 0f && !calibrating) calibrationError = null
            }
            is DeviceMessage.Calibration -> onCalibration(msg)
            is DeviceMessage.Status -> {
                lastStatus = msg
                lastStatusAt = System.currentTimeMillis()
            }
            is DeviceMessage.Error -> {
                AppLog.w("기기 오류 ${msg.code}: ${msg.message}")
                if (calibrating) onCalibration(DeviceMessage.Calibration(false, msg.code))
                when (msg.code) {
                    // 토큰이 바뀌었으면 연결 화면으로 돌아가 다시 입력받는다
                    "UNAUTHORIZED", "FORBIDDEN" -> if (screen != Screen.CONNECT) {
                        stopTicking()
                        client?.close()
                        clientJobs.forEach { it.cancel() }
                        client = null
                        link = LinkState.DISCONNECTED
                        connectError = "기기 토큰이 올바르지 않아요. 토큰을 다시 입력해 주세요."
                        screen = Screen.CONNECT
                    }
                    // 기기에 기준 자세가 없으면 공부를 시작할 수 없다
                    "CALIBRATION_REQUIRED" -> if (screen == Screen.STUDY) {
                        stopTicking()
                        flushPending()
                        goSetup(initial = false)
                        calibrationError = "기기에 저장된 기준 자세가 없어요. 먼저 자세를 설정해 주세요."
                    }
                }
            }
        }
    }

    // ================= 자세설정 =================

    fun confirmCalibration() {
        val c = client ?: return
        if (calibrating) return
        calibrating = true
        calibrationError = null
        AppLog.i("기준 자세 저장 요청")
        c.calibrate()
        calibrationTimeout?.cancel()
        calibrationTimeout = viewModelScope.launch {
            delay(5000)
            if (calibrating) onCalibration(DeviceMessage.Calibration(false, "timeout"))
        }
    }

    private fun onCalibration(msg: DeviceMessage.Calibration) {
        if (!calibrating) return
        calibrating = false
        calibrationTimeout?.cancel()
        AppLog.i(if (msg.ok) "기준 자세 저장 성공" else "기준 자세 저장 실패: ${msg.reason}")
        if (msg.ok) {
            goHome()
        } else {
            calibrationError = Protocol.calibrationReasonText(msg.reason)
        }
    }

    // ================= 학습 모드 =================

    fun startStudy() {
        val c = client ?: return
        issueSeconds.clear()
        lastStatus = null
        lastStatusAt = 0L
        sessionStartedAt = System.currentTimeMillis()
        pendingDate = LocalDate.now()
        resetPending()
        // 오늘 공부 횟수 +1, 타이머는 오늘 누적 시간부터 이어서 시작
        storage.addToDay(pendingDate, sessions = 1)
        study = StudyUi(todayFocusSec = storage.day(pendingDate).focusSec)
        AppLog.i("공부 시작. 오늘 누적 ${study.todayFocusSec}초부터 이어서 측정")
        c.setMode(Protocol.MODE_MONITOR)
        c.session("start")
        screen = Screen.STUDY
        stopTicking()
        tickJob = viewModelScope.launch {
            while (true) {
                delay(1000)
                tick()
            }
        }
    }

    fun togglePause() {
        val paused = !study.paused
        if (paused) client?.pause() else client?.resume()
        study = study.copy(paused = paused, badStreak = 0, alert = false)
    }

    private fun tick() {
        rollOverIfNewDay()
        val s = study
        if (s.paused) return
        val status = lastStatus
        val stale = status == null ||
            link != LinkState.CONNECTED ||
            System.currentTimeMillis() - lastStatusAt > STALE_MS
        if (stale) {
            study = s.copy(stale = true, badStreak = 0, alert = false)
            return
        }
        study = when (status!!.state) {
            PostureState.NO_PERSON -> {
                pendAway++
                s.copy(
                    awaySec = s.awaySec + 1, badStreak = 0, alert = false,
                    state = status.state, issues = emptyList(), stale = false,
                )
            }
            PostureState.GOOD -> {
                pendFocus++
                pendGood++
                s.copy(
                    focusSec = s.focusSec + 1, todayFocusSec = s.todayFocusSec + 1,
                    goodSec = s.goodSec + 1, badStreak = 0, alert = false,
                    state = status.state, issues = emptyList(), stale = false,
                )
            }
            PostureState.BAD -> {
                pendFocus++
                status.issues.forEach { issueSeconds[it] = (issueSeconds[it] ?: 0) + 1 }
                val streak = s.badStreak + 1
                val warnDelay = client?.warnDelaySec ?: WARN_DELAY_SEC
                val newWarning = streak == warnDelay
                if (newWarning) {
                    pendWarn++
                    vibrate()
                    AppLog.i("자세 경고 ${status.issues.map { it.code }} (이번 세션 ${s.warnings + 1}회)")
                }
                s.copy(
                    focusSec = s.focusSec + 1, todayFocusSec = s.todayFocusSec + 1,
                    badStreak = streak,
                    warnings = s.warnings + if (newWarning) 1 else 0,
                    alert = streak >= warnDelay,
                    state = status.state, issues = status.issues, stale = false,
                )
            }
            PostureState.UNKNOWN -> s.copy(stale = true)
        }
        ticksSinceFlush++
        if (ticksSinceFlush >= FLUSH_EVERY_SEC) flushPending()
    }

    /** 공부 중에 자정이 지나면 어제 몫은 어제에, 이후는 새 날짜에 쌓는다 */
    private fun rollOverIfNewDay() {
        val now = LocalDate.now()
        if (now == pendingDate) return
        AppLog.i("자정이 지나 $pendingDate 기록을 저장하고 $now 기록을 시작함")
        flushPending()
        pendingDate = now
        storage.addToDay(now, sessions = 1)
        study = study.copy(todayFocusSec = storage.day(now).focusSec)
    }

    private fun flushPending() {
        storage.addToDay(pendingDate, pendFocus, pendGood, pendAway, pendWarn)
        resetPending()
    }

    private fun resetPending() {
        pendFocus = 0
        pendGood = 0
        pendAway = 0
        pendWarn = 0
        ticksSinceFlush = 0
    }

    fun stopStudy() {
        stopTicking()
        flushPending()
        client?.session("stop")
        client?.setMode(Protocol.MODE_IDLE)
        val s = study
        val record = SessionRecord(
            startedAt = sessionStartedAt,
            endedAt = System.currentTimeMillis(),
            focusSec = s.focusSec,
            goodSec = s.goodSec,
            awaySec = s.awaySec,
            warnings = s.warnings,
            topIssue = issueSeconds.maxByOrNull { it.value }?.key?.code,
        )
        AppLog.i(
            "공부 종료. 집중 ${record.focusSec}초, 자세 유지율 ${record.postureRate}%, " +
                "경고 ${record.warnings}회, 자리 비움 ${record.awaySec}초"
        )
        if (record.focusSec > 0) {
            storage.addSession(record)
        } else {
            // 실제로 공부한 시간이 없으면 횟수에서 뺀다
            storage.addToDay(pendingDate, sessions = -1)
        }
        today = storage.today()
        lastResult = record
        screen = Screen.RESULT
    }

    private fun stopTicking() {
        tickJob?.cancel()
        tickJob = null
    }

    // ================= 캘린더 =================

    fun openCalendar() {
        calendarMonth = YearMonth.now()
        refreshMonth()
        selectDate(LocalDate.now())
        screen = Screen.CALENDAR
    }

    fun prevMonth() {
        calendarMonth = calendarMonth.minusMonths(1)
        refreshMonth()
    }

    fun nextMonth() {
        calendarMonth = calendarMonth.plusMonths(1)
        refreshMonth()
    }

    fun goThisMonth() {
        calendarMonth = YearMonth.now()
        refreshMonth()
        selectDate(LocalDate.now())
    }

    fun selectDate(date: LocalDate) {
        selectedDate = date
        selectedSessions = storage.sessionsOn(date).sortedBy { it.startedAt }
    }

    fun dayStat(date: LocalDate): DayStat = monthStats[date] ?: storage.day(date)

    private fun refreshMonth() {
        monthStats = storage.month(calendarMonth)
    }

    // ================= 프로필 =================

    fun saveNickname(value: String) {
        val v = value.trim().ifEmpty { "사용자" }.take(12)
        storage.nickname = v
        nickname = v
        goHome()
    }

    // ================= 설정 =================

    fun changeVolume(value: Int) {
        val v = value.coerceIn(0, 100)
        volume = v
        storage.volume = v
        // 슬라이더를 움직이는 동안 너무 자주 보내지 않도록 잠깐 모아서 보낸다
        volumeSendJob?.cancel()
        volumeSendJob = viewModelScope.launch {
            delay(150)
            client?.config(volume, muted)
        }
    }

    fun changeMuted(value: Boolean) {
        muted = value
        storage.muted = value
        client?.config(volume, muted)
    }

    fun playTestSound() {
        client?.config(volume, muted)
        client?.testSound()
    }

    fun changeTextSize(size: TextSize) {
        textSize = size
        storage.textScale = size.scale
    }

    // ================= 기타 =================

    private fun vibrate() {
        val ctx = getApplication<Application>()
        val vibrator: Vibrator? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            (ctx.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }
        try {
            vibrator?.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 180, 120, 180), -1))
        } catch (_: Exception) {
        }
    }

    override fun onCleared() {
        if (tickJob != null) flushPending()
        stopTicking()
        client?.close()
        discovery.stop()
    }
}
