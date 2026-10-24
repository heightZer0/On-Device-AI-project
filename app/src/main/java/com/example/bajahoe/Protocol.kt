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

/** 나쁜 자세의 원인. 정면 카메라 기준 */
enum class PostureIssue(val code: String, val label: String, val advice: String) {
    HEAD_DOWN("head_down", "고개 숙임", "고개를 너무 숙이고 있어요"),
    TOO_CLOSE("too_close", "화면과 너무 가까움", "화면에 너무 가까이 다가갔어요"),
    SHOULDER_TILT("shoulder_tilt", "어깨 기울어짐", "어깨가 한쪽으로 기울었어요"),
    LEANING("leaning", "몸 기울어짐", "몸이 한쪽으로 기울었어요");

    companion object {
        fun parse(code: String?): PostureIssue? = entries.firstOrNull { it.code == code }
    }
}

data class DeviceInfo(
    val deviceId: String,
    val name: String,
    val version: String,
    val host: String,
    val port: Int,
    val isDemo: Boolean = false,
) {
    val previewUrl: String get() = "http://$host:$port/stream.mjpg"
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
    ) : DeviceMessage {
        val ready: Boolean get() = face && shoulders && stable
    }

    data class Calibration(val ok: Boolean, val reason: String?) : DeviceMessage

    data class Error(val code: String, val message: String) : DeviceMessage
}

object Protocol {
    /** NsdManager 에 넘기는 서비스 타입 */
    const val SERVICE_TYPE = "_bajahoe._tcp"
    const val DEFAULT_PORT = 8080
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
        else -> "기준 자세를 저장하지 못했어요. 다시 시도해 주세요."
    }
}
