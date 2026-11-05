package com.example.bajahoe

import android.util.Log

/**
 * Logcat 로그.
 * Android Studio 아래쪽 Logcat 창 검색칸에 아래처럼 입력해서 본다.
 *   tag:Bajahoe     화면 이동, 연결 상태, 자세설정, 경고 같은 주요 이벤트
 *   tag:BjMsg       기기와 주고받은 JSON 원문 (→ 보냄, ← 받음)
 */
object AppLog {
    const val TAG = "Bajahoe"
    const val TAG_MSG = "BjMsg"

    fun i(message: String) {
        Log.i(TAG, message)
    }

    fun w(message: String) {
        Log.w(TAG, message)
    }

    fun sent(json: String) {
        Log.d(TAG_MSG, "→ $json")
    }

    fun received(json: String) {
        Log.d(TAG_MSG, "← $json")
    }
}
