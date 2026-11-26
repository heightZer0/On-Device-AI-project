package com.example.bajahoe

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import okhttp3.Request
import java.io.ByteArrayOutputStream

/**
 * 기기 카메라 영상을 화면에 그린다. 자세설정 화면에서만 사용한다.
 * - WebSocket 기기: /stream.mjpg 연속 스트림
 * - 팀 서버(P2, [snapshot] = true): /api/v1/preview/frame 사진을 토큰과 함께 계속 받아 온다
 * 첫 프레임이 오기 전이나 영상이 없으면 [placeholder] 를 보여준다.
 */
@Composable
fun MjpegPreview(
    url: String,
    modifier: Modifier = Modifier,
    token: String = "",
    snapshot: Boolean = false,
    placeholder: @Composable () -> Unit = {},
) {
    var frame by remember(url) { mutableStateOf<ImageBitmap?>(null) }

    LaunchedEffect(url, token, snapshot) {
        withContext(Dispatchers.IO) {
            while (isActive) {
                try {
                    if (snapshot) {
                        val bmp = readSnapshot(url, token)
                        if (bmp != null) frame = bmp.asImageBitmap()
                        delay(if (bmp != null) 200 else 1000)
                        continue
                    }
                    readMjpeg(url) { bmp -> frame = bmp.asImageBitmap() }
                } catch (_: Exception) {
                }
                delay(1000)
            }
        }
    }

    val current = frame
    if (current != null) {
        Image(
            bitmap = current,
            contentDescription = "카메라 미리보기",
            contentScale = ContentScale.Crop,
            modifier = modifier,
        )
    } else {
        placeholder()
    }
}

/** JPEG 한 장. 미리보기가 꺼져 있으면(404) null */
private fun readSnapshot(url: String, token: String): Bitmap? {
    val req = Request.Builder().url(url)
    if (token.isNotBlank()) req.header("Authorization", "Bearer $token")
    Http.client.newCall(req.build()).execute().use { resp ->
        if (!resp.isSuccessful) return null
        val bytes = resp.body?.bytes() ?: return null
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }
}

private suspend fun readMjpeg(url: String, onFrame: (Bitmap) -> Unit) {
    val call = Http.client.newCall(Request.Builder().url(url).build())
    val job = currentCoroutineContext()[Job]
    val handle = job?.invokeOnCompletion { call.cancel() }
    try {
        call.execute().use { resp ->
            if (!resp.isSuccessful) return
            val input = resp.body?.byteStream() ?: return
            val buf = ByteArray(16 * 1024)
            val frameBuf = ByteArrayOutputStream(64 * 1024)
            var inFrame = false
            var prev = -1
            while (currentCoroutineContext().isActive) {
                val n = input.read(buf)
                if (n < 0) break
                for (i in 0 until n) {
                    val b = buf[i].toInt() and 0xFF
                    if (!inFrame) {
                        if (prev == 0xFF && b == 0xD8) {
                            inFrame = true
                            frameBuf.reset()
                            frameBuf.write(0xFF)
                            frameBuf.write(0xD8)
                        }
                    } else {
                        frameBuf.write(b)
                        if (prev == 0xFF && b == 0xD9) {
                            inFrame = false
                            val bytes = frameBuf.toByteArray()
                            BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.let(onFrame)
                        }
                    }
                    prev = b
                }
            }
        }
    } finally {
        handle?.dispose()
    }
}
