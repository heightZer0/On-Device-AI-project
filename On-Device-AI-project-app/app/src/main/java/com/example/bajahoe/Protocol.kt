package com.example.bajahoe

import org.json.JSONArray
import org.json.JSONObject

/** 기기가 판정한 그 순간의 자세 상태. PROTOCOL.md 3.2 참고 */
enum class PostureState {
    GOOD, BAD, NO_PERSON, UNKNOWN;

    companion object {
        fun parse(value: String?): PostureState = when (value) {
            "good" -> GOOD
            "bad" -> BAD
            "no_person" -> NO_PERSON
            else -> UNKNOWN
        }
    }
}

/** 나쁜 자세의 원인. 반측면 카메라 기준 (PROTOCOL.md 4장) */
enum class PostureIssue(val code: String, val label: String, val advice: String) {
    FORWARD_HEAD("forward_head", "거북목", "목이 앞으로 나와 있어요"),
    HEAD_DOWN("head_down", "고개 숙임", "고개를 너무 숙이고 있어요"),
    SLOUCH("slouch", "등 굽음", "등이 구부정하게 굽었어요"),
    TOO_CLOSE("too_close", "화면과 너무 가까움", "화면에 너무 가까이 다가갔어요");

    companion object {
        fun parse(code: String?): PostureIssue? = entries.firstOrNull { it.code == code }
    }
}

/** 기기 서버 종류. P2 는 팀 백엔드(p2_board_api, REST + 토큰), WS 는 PROTOCOL.md 의 WebSocket 방식 */
enum class DeviceKind { P2, WS }

data class DeviceInfo(
    val deviceId: String,
    val name: String,
    val version: String,
    val host: String,
    val port: Int,
    val isDemo: Boolean = false,
    val kind: DeviceKind = DeviceKind.WS,
    /** P2 API 인증 토큰 (Authorization: Bearer) */
    val token: String = "",
) {
    val isP2: Boolean get() = kind == DeviceKind.P2
    /** P2 는 JPEG 한 장씩, WS 는 MJPEG 스트림 */
    val previewUrl: String get() =
        if (isP2) "http://$host:$port/api/v1/preview/frame" else "http://$host:$port/stream.mjpg"
    val wsUrl: String get() = "ws://$host:$port/ws"
    val address: String get() = if (isDemo) "데모 모드" else "$host:$port"
}

sealed interface DeviceMessage {
    data class Status(
        val state: PostureState,
        val score: Int,
        val issues: List<PostureIssue>,
    ) : DeviceMessage

    data class Detect(
        val face: Boolean,
        val shoulders: Boolean,
        val stable: Boolean,
        /** P2 기준 자세 측정 진행률 0~1. 진행률이 없는 기기는 -1 */
        val progress: Float = -1f,
        /** P2 기준 자세 측정 실패 사유. 실패하면 기기가 자동으로 다시 측정한다 */
        val failReason: String? = null,
    ) : DeviceMessage {
        val ready: Boolean get() = face && shoulders && stable
    }

    data class Calibration(val ok: Boolean, val reason: String?) : DeviceMessage

    data class Error(val code: String, val message: String) : DeviceMessage
}

object Protocol {
    /** NsdManager 에 넘기는 서비스 타입 */
    const val SERVICE_TYPE = "_bajahoe._tcp"
    const val DEFAULT_PORT = 8000
    const val APP_VERSION = "1.0"

    const val MODE_IDLE = "idle"
    const val MODE_CALIBRATE = "calibrate"
    const val MODE_MONITOR = "monitor"

    fun parse(text: String): DeviceMessage? = try {
        val o = JSONObject(text)
        when (o.optString("type")) {
            "status" -> DeviceMessage.Status(
                state = PostureState.parse(o.optString("state")),
                score = o.optInt("score", -1),
                issues = parseIssues(o.optJSONArray("issues")),
            )
            "detect" -> DeviceMessage.Detect(
                face = o.optBoolean("face"),
                shoulders = o.optBoolean("shoulders"),
                stable = o.optBoolean("stable"),
            )
            "calibration" -> DeviceMessage.Calibration(
                ok = o.optBoolean("ok"),
                reason = if (o.has("reason")) o.optString("reason") else null,
            )
            "error" -> DeviceMessage.Error(o.optString("code"), o.optString("message"))
            else -> null
        }
    } catch (e: Exception) {
        null
    }

    private fun parseIssues(arr: JSONArray?): List<PostureIssue> {
        if (arr == null) return emptyList()
        return (0 until arr.length()).mapNotNull { PostureIssue.parse(arr.optString(it)) }
    }

    fun parseInfo(text: String, host: String, port: Int): DeviceInfo? = try {
        val o = JSONObject(text)
        DeviceInfo(
            deviceId = o.optString("device_id", "unknown"),
            name = o.optString("name", "바자회 기기"),
            version = o.optString("version", "?"),
            host = host,
            port = port,
        )
    } catch (e: Exception) {
        null
    }

    fun hello(): String = JSONObject()
        .put("type", "hello").put("app_version", APP_VERSION).put("client", "android").toString()

    fun mode(mode: String): String = JSONObject().put("type", "mode").put("mode", mode).toString()

    fun calibrate(): String = JSONObject().put("type", "calibrate").toString()

    fun session(action: String): String =
        JSONObject().put("type", "session").put("action", action).toString()

    fun config(volume: Int, muted: Boolean): String = JSONObject()
        .put("type", "config")
        .put("volume", volume)
        .put("muted", muted)
        .put("warn_delay_sec", AppViewModel.WARN_DELAY_SEC)
        .toString()

    fun testSound(): String = JSONObject().put("type", "test_sound").toString()

    fun calibrationReasonText(reason: String?): String = when (reason) {
        "no_person" -> "사람이 보이지 않아요. 카메라 앞에 앉아 주세요."
        "face_not_found" -> "얼굴이 잘 보이지 않아요. 조명을 밝게 해 주세요."
        "shoulders_not_found" -> "어깨가 화면에 들어오도록 카메라를 조금 멀리 두세요."
        "unstable" -> "움직임이 있어요. 잠시 가만히 있어 주세요."
        "no_camera" -> "기기에서 카메라를 찾지 못했어요."
        "timeout" -> "기기 응답이 없어요. 연결 상태를 확인해 주세요."
        // P2 (팀 백엔드) 캘리브레이션 실패 사유
        "too_few_frames" -> "카메라에 머리와 어깨가 충분히 잡히지 않았어요. 다시 측정할게요."
        "too_few_stable_frames", "too_much_variation" -> "측정 중에 움직임이 있었어요. 5초 동안 가만히 있어 주세요."
        "invalid_reference_length", "direction_unknown" -> "카메라 쪽 귀와 어깨가 잘 보이도록 카메라 각도를 맞춰 주세요."
        "not_ready" -> "아직 측정이 끝나지 않았어요. 잠시만 기다려 주세요."
        "save_failed" -> "기기에 기준 자세를 저장하지 못했어요."
        "CAMERA_NOT_READY", "CAMERA_UNAVAILABLE", "camera_disconnected" -> "기기 카메라를 사용할 수 없어요. 카메라 연결을 확인해 주세요."
        "INVALID_STATE" -> "기기가 다른 작업 중이에요. 잠시 후 다시 시도해 주세요."
        else -> "기준 자세를 저장하지 못했어요. 다시 시도해 주세요."
    }
}
