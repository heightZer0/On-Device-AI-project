package com.example.bajahoe

import org.json.JSONObject

/** 기기가 판정한 그 순간의 자세 상태. PROTOCOL.md 3.2 참고 */
enum class PostureState {
    GOOD, BAD, NO_PERSON, UNKNOWN;

    companion object {
        fun parse(value: String?): PostureState = when (value) {
            "normal", "good" -> GOOD
            "attention", "bad" -> BAD
            "no_person" -> NO_PERSON
            "unavailable" -> UNKNOWN
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
    val address: String get() = if (isDemo) "데모 모드" else "$host:$port"
}

sealed interface DeviceMessage {
    data class Status(
        val state: PostureState,
        val score: Int,
        val issues: List<PostureIssue>,
    ) : DeviceMessage

    data class Detect(
        val ear: Boolean,
        val shoulders: Boolean,
        val stable: Boolean,
    ) : DeviceMessage {
        val ready: Boolean get() = ear && shoulders && stable
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

    fun parseApiStatus(response: JSONObject): DeviceMessage.Status {
        val posture = response.optJSONObject("posture") ?: JSONObject()
        return DeviceMessage.Status(
            state = PostureState.parse(posture.optString("state")),
            score = -1,
            issues = emptyList(),
        )
    }

    fun calibrationReasonText(reason: String?): String = when (reason) {
        "no_person" -> "사람이 보이지 않아요. 카메라 앞에 앉아 주세요."
        "face_not_found", "ear_not_detected" -> "귀가 잘 보이도록 카메라와 조명을 조정해 주세요."
        "shoulders_not_found", "shoulder_not_detected" -> "어깨가 화면에 들어오도록 카메라를 조금 멀리 두세요."
        "out_of_frame" -> "머리와 어깨가 화면 안에 들어오도록 앉아 주세요."
        "invalid_geometry" -> "카메라를 눈높이에 두고 정면을 바라봐 주세요."
        "unstable" -> "움직임이 있어요. 잠시 가만히 있어 주세요."
        "no_camera" -> "기기에서 카메라를 찾지 못했어요."
        "camera_disconnected" -> "카메라 연결이 끊겼어요. 카메라 연결을 확인해 주세요."
        "too_few_frames", "too_few_stable_frames" -> "기준 자세를 충분히 측정하지 못했어요. 카메라에 머리와 어깨가 보이는지 확인해 주세요."
        "too_much_variation" -> "자세가 안정될 때까지 잠시 가만히 있어 주세요."
        "calibration_not_started" -> "자세 측정을 먼저 시작해 주세요."
        "calibration_failed", "save_failed" -> "기준 자세를 저장하지 못했어요. 다시 시도해 주세요."
        "timeout" -> "기기 응답이 없어요. 연결 상태를 확인해 주세요."
        else -> "기준 자세를 저장하지 못했어요. 다시 시도해 주세요."
    }
}
