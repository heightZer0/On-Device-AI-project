package com.example.bajahoe

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathBuilder
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// ======================= 색상 (Figma index.css 토큰) =======================

object Bj {
    val Ink = Color(0xFF18322E)
    val Muted = Color(0xFF6C7D79)
    val Brand = Color(0xFF2C806F)
    val BrandDark = Color(0xFF236A5C)
    val Mint = Color(0xFFDCEFE9)
    val MintSoft = Color(0xFFF0F8F5)
    val Blue = Color(0xFF5878A5)
    val Cream = Color(0xFFF9FBF8)
    val Line = Color(0xFFE5ECE8)
    val PostureCard = Color(0xFFEDF7F3)
    val FocusCard = Color(0xFFEEF2F8)
    val Guide = Color(0xFFB8F3DF)
    val Live = Color(0xFF7EE0BD)
    val Danger = Color(0xFFD9695C)
    val DangerSoft = Color(0xFFFBEDEA)
    val StopDot = Color(0xFFF1A49C)
    val CameraTop = Color(0xFF82928D)
    val CameraMid = Color(0xFF50605C)
    val CameraBottom = Color(0xFF263632)
}

@Composable
fun BajahoeAppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Bj.Brand,
            onPrimary = Color.White,
            secondary = Bj.Blue,
            background = Bj.Cream,
            surface = Color.White,
            onBackground = Bj.Ink,
            onSurface = Bj.Ink,
            error = Bj.Danger,
        ),
        content = content,
    )
}

// ======================= 아이콘 (Figma SVG 를 옮김) =======================

private fun strokeIcon(name: String, size: Float, block: PathBuilder.() -> Unit): ImageVector =
    ImageVector.Builder(
        name = name,
        defaultWidth = 24.dp,
        defaultHeight = 24.dp,
        viewportWidth = size,
        viewportHeight = size,
    ).path(
        stroke = SolidColor(Color.Black),
        strokeLineWidth = 2f,
        strokeLineCap = StrokeCap.Round,
        strokeLineJoin = StrokeJoin.Round,
        pathBuilder = block,
    ).build()

private fun PathBuilder.circle(cx: Float, cy: Float, r: Float) {
    moveTo(cx - r, cy)
    arcToRelative(r, r, 0f, true, false, r * 2, 0f)
    arcToRelative(r, r, 0f, true, false, -r * 2, 0f)
    close()
}

object BjIcons {
    val Chevron = strokeIcon("chevron", 24f) {
        moveTo(9f, 6f); lineTo(15f, 12f); lineTo(9f, 18f)
    }
    val Back = strokeIcon("back", 24f) {
        moveTo(15f, 5f); lineTo(8f, 12f); lineTo(15f, 19f)
    }
    val Check = strokeIcon("check", 24f) {
        moveTo(5f, 12.5f); lineTo(9.5f, 17f); lineTo(19f, 7.5f)
    }
    val Camera = strokeIcon("camera", 32f) {
        moveTo(10.3f, 9.5f); lineTo(12f, 6.8f); lineTo(20f, 6.8f); lineTo(21.7f, 9.5f); lineTo(25f, 9.5f)
        quadTo(28f, 9.5f, 28f, 12.5f); lineTo(28f, 22.5f); quadTo(28f, 25.5f, 25f, 25.5f)
        lineTo(7f, 25.5f); quadTo(4f, 25.5f, 4f, 22.5f); lineTo(4f, 12.5f); quadTo(4f, 9.5f, 7f, 9.5f)
        close()
        circle(16f, 17f, 5.2f)
    }
    val Focus: ImageVector = ImageVector.Builder(
        name = "focus", defaultWidth = 24.dp, defaultHeight = 24.dp,
        viewportWidth = 32f, viewportHeight = 32f,
    ).path(
        stroke = SolidColor(Color.Black), strokeLineWidth = 1.8f,
        strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round,
    ) {
        circle(16f, 16f, 11f)
        circle(16f, 16f, 6f)
    }.path(fill = SolidColor(Color.Black)) {
        moveTo(14f, 12f); lineTo(20f, 16f); lineTo(14f, 20f); close()
    }.build()
    val Device = strokeIcon("device", 32f) {
        moveTo(9f, 5f); lineTo(23f, 5f); quadTo(26f, 5f, 26f, 8f); lineTo(26f, 20f)
        quadTo(26f, 23f, 23f, 23f); lineTo(9f, 23f); quadTo(6f, 23f, 6f, 20f); lineTo(6f, 8f)
        quadTo(6f, 5f, 9f, 5f); close()
        circle(16f, 14f, 4f)
        moveTo(16f, 23f); lineTo(16f, 27f); moveTo(11f, 27f); lineTo(21f, 27f)
    }
    val Gear = strokeIcon("gear", 24f) {
        circle(12f, 12f, 3f)
        // 톱니 8개
        for (i in 0 until 8) {
            val a = Math.toRadians(i * 45.0)
            val c = kotlin.math.cos(a).toFloat()
            val sn = kotlin.math.sin(a).toFloat()
            moveTo(12f + c * 6.2f, 12f + sn * 6.2f)
            lineTo(12f + c * 8.8f, 12f + sn * 8.8f)
        }
        circle(12f, 12f, 6.2f)
    }
    val Calendar = strokeIcon("calendar", 24f) {
        moveTo(6f, 5f); lineTo(18f, 5f); quadTo(20f, 5f, 20f, 7f); lineTo(20f, 18f)
        quadTo(20f, 20f, 18f, 20f); lineTo(6f, 20f); quadTo(4f, 20f, 4f, 18f); lineTo(4f, 7f)
        quadTo(4f, 5f, 6f, 5f); close()
        moveTo(4f, 10f); lineTo(20f, 10f)
        moveTo(8.5f, 3f); lineTo(8.5f, 6.5f)
        moveTo(15.5f, 3f); lineTo(15.5f, 6.5f)
    }
    val Speaker = strokeIcon("speaker", 24f) {
        moveTo(4f, 9.5f); lineTo(7.5f, 9.5f); lineTo(12f, 5.5f); lineTo(12f, 18.5f); lineTo(7.5f, 14.5f)
        lineTo(4f, 14.5f); close()
        moveTo(15.5f, 9f); quadTo(17.5f, 12f, 15.5f, 15f)
        moveTo(18f, 6.5f); quadTo(22f, 12f, 18f, 17.5f)
    }
    val SpeakerOff = strokeIcon("speaker_off", 24f) {
        moveTo(4f, 9.5f); lineTo(7.5f, 9.5f); lineTo(12f, 5.5f); lineTo(12f, 18.5f); lineTo(7.5f, 14.5f)
        lineTo(4f, 14.5f); close()
        moveTo(16f, 9.5f); lineTo(21f, 14.5f)
        moveTo(21f, 9.5f); lineTo(16f, 14.5f)
    }
    val ChevronLeft = strokeIcon("chevron_left", 24f) {
        moveTo(15f, 6f); lineTo(9f, 12f); lineTo(15f, 18f)
    }
}

@Composable
fun BjIcon(icon: ImageVector, tint: Color, size: Dp = 22.dp, modifier: Modifier = Modifier) {
    Icon(imageVector = icon, contentDescription = null, tint = tint, modifier = modifier.size(size))
}

// ======================= 로고 =======================

/** 흰 새싹 모양 로고. Figma 의 leaf-mark */
@Composable
fun LeafMark(modifier: Modifier = Modifier, color: Color = Color.White) {
    Canvas(modifier) {
        val s = size.minDimension / 55f
        fun p(x: Float, y: Float) = Offset(x * s, y * s)
        drawLine(color, p(28f, 50f), p(29.5f, 16f), strokeWidth = 4f * s, cap = StrokeCap.Round)
        val left = androidx.compose.ui.graphics.Path().apply {
            moveTo(27f * s, 33f * s)
            quadraticTo(12f * s, 34f * s, 5f * s, 22f * s)
            quadraticTo(21f * s, 18f * s, 27f * s, 33f * s)
            close()
        }
        val right = androidx.compose.ui.graphics.Path().apply {
            moveTo(30f * s, 22f * s)
            quadraticTo(33f * s, 8f * s, 52f * s, 6f * s)
            quadraticTo(49f * s, 22f * s, 30f * s, 22f * s)
            close()
        }
        drawPath(left, color)
        drawPath(right, color)
    }
}

@Composable
fun LogoTile(size: Dp, corner: Dp, modifier: Modifier = Modifier) {
    Box(
        modifier
            .size(size)
            .clip(RoundedCornerShape(corner))
            .background(Bj.Brand),
        contentAlignment = Alignment.Center,
    ) {
        LeafMark(Modifier.size(size * 0.55f))
    }
}

// ======================= 공통 컴포넌트 =======================

@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    icon: ImageVector? = null,
    color: Color = Bj.Brand,
) {
    Row(
        modifier
            .fillMaxWidth()
            .height(58.dp)
            .shadow(if (enabled) 10.dp else 0.dp, RoundedCornerShape(19.dp), spotColor = color)
            .clip(RoundedCornerShape(19.dp))
            .background(if (enabled) color else color.copy(alpha = 0.35f))
            .clickable(enabled = enabled, onClick = onClick),
        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) {
            BjIcon(icon, Color.White, 20.dp)
            Spacer(Modifier.width(8.dp))
        }
        Text(text, color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun CircleIconButton(
    icon: ImageVector,
    onClick: () -> Unit,
    dark: Boolean,
    description: String,
) {
    Box(
        Modifier
            .size(40.dp)
            .clip(CircleShape)
            .background(if (dark) Color(0x470C1C18) else Color.White.copy(alpha = 0.8f))
            .border(1.dp, if (dark) Color.White.copy(alpha = 0.2f) else Bj.Line, CircleShape)
            .clickable(onClickLabel = description, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        BjIcon(icon, if (dark) Color.White else Bj.Ink, 22.dp)
    }
}

@Composable
fun ScreenHeader(
    title: String,
    dark: Boolean,
    onBack: (() -> Unit)?,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .height(56.dp)
            .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (onBack != null) CircleIconButton(BjIcons.Back, onBack, dark, "뒤로 가기")
        else Spacer(Modifier.size(40.dp))
        Text(
            title,
            modifier = Modifier.weight(1f),
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            color = if (dark) Color.White else Bj.Ink,
            fontSize = 16.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.size(40.dp))
    }
}

/** 기기 연결 상태 표시 */
@Composable
fun LinkChip(link: LinkState, info: DeviceInfo?, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val (label, color) = when {
        info == null -> "기기 없음" to Bj.Muted
        link == LinkState.CONNECTED -> (if (info.isDemo) "데모 연결됨" else "기기 연결됨") to Bj.Brand
        link == LinkState.DISCONNECTED -> "연결 안 됨" to Bj.Danger
        else -> "연결 중" to Color(0xFFC79A3B)
    }
    Row(
        modifier
            .clip(RoundedCornerShape(999.dp))
            .background(Color.White)
            .border(1.dp, Bj.Line, RoundedCornerShape(999.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(7.dp).clip(CircleShape).background(color))
        Spacer(Modifier.width(6.dp))
        Text(label, fontSize = 12.sp, color = Bj.Ink, fontWeight = FontWeight.Medium)
    }
}

// ======================= 카메라 화면 배경 =======================

@Composable
fun CameraBackdrop(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit = {}) {
    Box(
        modifier
            .fillMaxSize()
            .background(
                Brush.radialGradient(listOf(Bj.CameraTop, Bj.CameraMid, Bj.CameraBottom))
            )
    ) {
        content()
        // 3분할 격자
        Canvas(Modifier.fillMaxSize().alpha(0.11f)) {
            val w = size.width
            val h = size.height
            for (i in 1..2) {
                drawLine(Color.White, Offset(w * i / 3, h * 0.18f), Offset(w * i / 3, h * 0.8f), 1.5f)
                drawLine(Color.White, Offset(0f, h * (0.18f + 0.62f * i / 3)), Offset(w, h * (0.18f + 0.62f * i / 3)), 1.5f)
            }
        }
        // 위아래 어둡게
        Box(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        0f to Color(0x8006120F),
                        0.2f to Color.Transparent,
                        0.65f to Color.Transparent,
                        1f to Color(0xD106120F),
                    )
                )
        )
    }
}

/** 카메라 영상이 없을 때 보여주는 사람 실루엣 */
@Composable
fun PersonSilhouette(modifier: Modifier = Modifier, alpha: Float = 0.5f) {
    Canvas(modifier) {
        val w = size.width
        val h = size.height
        val c = Color(0xFF14221F).copy(alpha = alpha)
        // 머리
        drawOval(c, Offset(w / 2 - w * 0.19f, h * 0.13f), Size(w * 0.38f, h * 0.31f))
        // 목
        drawRect(c, Offset(w / 2 - w * 0.088f, h * 0.405f), Size(w * 0.176f, h * 0.14f))
        // 몸
        drawRoundRect(
            c,
            Offset(w / 2 - w * 0.43f, h * 0.5f),
            Size(w * 0.86f, h * 0.5f),
            CornerRadius(w * 0.4f, w * 0.4f),
        )
    }
}

/** 네 모서리 가이드와 어깨선. ready 면 민트색으로 밝아진다 */
@Composable
fun AlignmentGuide(ready: Boolean, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val w = size.width
        val h = size.height
        val corner = 34.dp.toPx()
        val stroke = 2.dp.toPx()
        val color = if (ready) Bj.Guide else Color(0xD9DDFFF5)
        val st = Stroke(width = stroke, cap = StrokeCap.Round)
        // 모서리
        fun cornerPath(x: Float, y: Float, dx: Float, dy: Float) {
            val p = androidx.compose.ui.graphics.Path().apply {
                moveTo(x, y + dy * corner)
                lineTo(x, y)
                lineTo(x + dx * corner, y)
            }
            drawPath(p, color, style = st)
        }
        cornerPath(0f, 0f, 1f, 1f)
        cornerPath(w, 0f, -1f, 1f)
        cornerPath(0f, h, 1f, -1f)
        cornerPath(w, h, -1f, -1f)
        // 어깨선
        val y = h * 0.59f
        val x1 = w * 0.1f
        val x2 = w * 0.9f
        drawLine(
            color.copy(alpha = if (ready) 0.95f else 0.6f),
            Offset(x1, y), Offset(x2, y),
            strokeWidth = 1.5.dp.toPx(),
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f)),
        )
        val dot = if (ready) Bj.Guide else Color.White.copy(alpha = 0.5f)
        drawCircle(dot.copy(alpha = 0.25f), 8.dp.toPx(), Offset(x1 + 12.dp.toPx(), y))
        drawCircle(dot.copy(alpha = 0.25f), 8.dp.toPx(), Offset(x2 - 12.dp.toPx(), y))
        drawCircle(dot, 4.dp.toPx(), Offset(x1 + 12.dp.toPx(), y))
        drawCircle(dot, 4.dp.toPx(), Offset(x2 - 12.dp.toPx(), y))
    }
}

fun formatTime(totalSec: Int): String {
    val h = totalSec / 3600
    val m = totalSec % 3600 / 60
    val s = totalSec % 60
    return "%02d:%02d:%02d".format(h, m, s)
}

fun formatMinutes(totalSec: Int): String {
    val m = totalSec / 60
    return if (m >= 60) "${m / 60}시간 ${m % 60}분" else "${m}분"
}
