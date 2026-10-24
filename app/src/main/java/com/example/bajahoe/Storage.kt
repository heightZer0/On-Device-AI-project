package com.example.bajahoe

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId

/** 하루 동안의 누적 기록. 같은 날 여러 번 공부하면 모두 더해진다 */
data class DayStat(
    val date: LocalDate,
    val focusSec: Int = 0,
    val goodSec: Int = 0,
    val awaySec: Int = 0,
    val warnings: Int = 0,
    val sessions: Int = 0,
) {
    /** 자세 유지율 0~100 */
    val postureRate: Int get() = if (focusSec == 0) 0 else (goodSec * 100 / focusSec)
}

/** 공부 한 번(시작~종료)의 기록 */
data class SessionRecord(
    val startedAt: Long,
    val endedAt: Long,
    val focusSec: Int,
    val goodSec: Int,
    val awaySec: Int,
    val warnings: Int,
    val topIssue: String?,
) {
    val postureRate: Int get() = if (focusSec == 0) 0 else (goodSec * 100 / focusSec)
}

fun Long.toLocalDate(): LocalDate = Instant.ofEpochMilli(this).atZone(ZoneId.systemDefault()).toLocalDate()

/** 닉네임, 설정, 기기, 공부 기록을 휴대폰 안에만 저장한다 */
class Storage(context: Context) {

    private val prefs = context.getSharedPreferences("bajahoe", Context.MODE_PRIVATE)
    private var daysCache: MutableMap<LocalDate, DayStat>? = null

    init {
        migrateOldHistory()
    }

    // ---------------- 프로필 ----------------

    var nickname: String
        get() = prefs.getString("nickname", null) ?: "사용자"
        set(value) = prefs.edit().putString("nickname", value).apply()

    // ---------------- 설정 ----------------

    /** 기기 음성 안내 볼륨 0~100 */
    var volume: Int
        get() = prefs.getInt("volume", 70)
        set(value) = prefs.edit().putInt("volume", value.coerceIn(0, 100)).apply()

    var muted: Boolean
        get() = prefs.getBoolean("muted", false)
        set(value) = prefs.edit().putBoolean("muted", value).apply()

    /** 앱 글씨 크기 배율 */
    var textScale: Float
        get() = prefs.getFloat("text_scale", 1f)
        set(value) = prefs.edit().putFloat("text_scale", value).apply()

    // ---------------- 기기 ----------------

    fun savedDevice(): Triple<String, Int, Boolean>? {
        val demo = prefs.getBoolean("device_demo", false)
        val host = prefs.getString("device_host", null)
        if (!demo && host == null) return null
        return Triple(host ?: "demo", prefs.getInt("device_port", Protocol.DEFAULT_PORT), demo)
    }

    fun saveDevice(info: DeviceInfo) {
        prefs.edit()
            .putString("device_host", info.host)
            .putInt("device_port", info.port)
            .putBoolean("device_demo", info.isDemo)
            .apply()
    }

    fun forgetDevice() {
        prefs.edit().remove("device_host").remove("device_port").remove("device_demo").apply()
    }

    // ---------------- 날짜별 기록 ----------------

    private fun days(): MutableMap<LocalDate, DayStat> {
        daysCache?.let { return it }
        val map = mutableMapOf<LocalDate, DayStat>()
        val raw = prefs.getString("days", null)
        if (raw != null) {
            try {
                val o = JSONObject(raw)
                o.keys().forEach { key ->
                    val d = o.getJSONObject(key)
                    val date = LocalDate.parse(key)
                    map[date] = DayStat(
                        date = date,
                        focusSec = d.optInt("focus"),
                        goodSec = d.optInt("good"),
                        awaySec = d.optInt("away"),
                        warnings = d.optInt("warn"),
                        sessions = d.optInt("sessions"),
                    )
                }
            } catch (_: Exception) {
            }
        }
        daysCache = map
        return map
    }

    private fun saveDays() {
        val o = JSONObject()
        days().forEach { (date, d) ->
            o.put(
                date.toString(),
                JSONObject()
                    .put("focus", d.focusSec)
                    .put("good", d.goodSec)
                    .put("away", d.awaySec)
                    .put("warn", d.warnings)
                    .put("sessions", d.sessions)
            )
        }
        prefs.edit().putString("days", o.toString()).apply()
    }

    fun day(date: LocalDate): DayStat = days()[date] ?: DayStat(date)

    fun today(): DayStat = day(LocalDate.now())

    /** 해당 달에 기록이 있는 날만 담아 돌려준다 */
    fun month(month: YearMonth): Map<LocalDate, DayStat> =
        days().filterKeys { YearMonth.from(it) == month }

    /** 그날 기록에 더한다. 공부를 껐다 켜도 같은 날이면 계속 이어서 쌓인다 */
    fun addToDay(
        date: LocalDate,
        focusSec: Int = 0,
        goodSec: Int = 0,
        awaySec: Int = 0,
        warnings: Int = 0,
        sessions: Int = 0,
    ) {
        if (focusSec == 0 && goodSec == 0 && awaySec == 0 && warnings == 0 && sessions == 0) return
        val map = days()
        val cur = map[date] ?: DayStat(date)
        map[date] = cur.copy(
            focusSec = cur.focusSec + focusSec,
            goodSec = cur.goodSec + goodSec,
            awaySec = cur.awaySec + awaySec,
            warnings = cur.warnings + warnings,
            sessions = cur.sessions + sessions,
        )
        saveDays()
    }

    // ---------------- 세션 기록 ----------------

    fun sessions(): List<SessionRecord> {
        val raw = prefs.getString("sessions", null) ?: return emptyList()
        return try {
            val arr = JSONArray(raw)
            (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                SessionRecord(
                    startedAt = o.getLong("startedAt"),
                    endedAt = o.getLong("endedAt"),
                    focusSec = o.getInt("focusSec"),
                    goodSec = o.getInt("goodSec"),
                    awaySec = o.optInt("awaySec"),
                    warnings = o.getInt("warnings"),
                    topIssue = if (o.isNull("topIssue")) null else o.optString("topIssue"),
                )
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun addSession(record: SessionRecord) {
        val list = (sessions() + record).takeLast(500)
        val arr = JSONArray()
        list.forEach { r ->
            arr.put(
                JSONObject()
                    .put("startedAt", r.startedAt)
                    .put("endedAt", r.endedAt)
                    .put("focusSec", r.focusSec)
                    .put("goodSec", r.goodSec)
                    .put("awaySec", r.awaySec)
                    .put("warnings", r.warnings)
                    .put("topIssue", r.topIssue ?: JSONObject.NULL)
            )
        }
        prefs.edit().putString("sessions", arr.toString()).apply()
    }

    /** 그날 시작했거나 끝난 세션 */
    fun sessionsOn(date: LocalDate): List<SessionRecord> =
        sessions().filter { it.startedAt.toLocalDate() == date || it.endedAt.toLocalDate() == date }

    // ---------------- 이전 버전 기록 옮기기 ----------------

    private fun migrateOldHistory() {
        val raw = prefs.getString("history", null) ?: return
        try {
            val arr = JSONArray(raw)
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                val ended = o.getLong("endedAt")
                val focus = o.getInt("focusSec")
                val away = o.optInt("awaySec")
                val record = SessionRecord(
                    startedAt = ended - (focus + away) * 1000L,
                    endedAt = ended,
                    focusSec = focus,
                    goodSec = o.getInt("goodSec"),
                    awaySec = away,
                    warnings = o.getInt("warnings"),
                    topIssue = if (o.isNull("topIssue")) null else o.optString("topIssue"),
                )
                addSession(record)
                addToDay(
                    ended.toLocalDate(), record.focusSec, record.goodSec, record.awaySec,
                    record.warnings, sessions = 1,
                )
            }
        } catch (_: Exception) {
        }
        prefs.edit().remove("history").apply()
    }
}
