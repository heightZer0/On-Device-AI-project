package com.example.bajahoe

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun StudyScreen(vm: AppViewModel) {
    val s = vm.study
    var confirmStop by remember { mutableStateOf(false) }
    BackHandler { confirmStop = true }

    // 공부하는 동안 화면이 꺼지지 않게
    val view = LocalView.current
    DisposableEffect(Unit) {
        view.keepScreenOn = true
        onDispose { view.keepScreenOn = false }
    }

    val disconnected = vm.link != LinkState.CONNECTED
    val message = when {
        s.paused -> "일시정지 중이에요"
        disconnected -> "기기와 다시 연결하는 중이에요"
        s.stale -> "자세를 확인하고 있어요"
        s.state == PostureState.NO_PERSON -> "자리를 비웠어요. 돌아오면 다시 측정해요"
        s.alert -> s.issues.firstOrNull()?.advice ?: "자세를 바르게 해 주세요"
        s.state == PostureState.BAD -> "자세가 조금 흐트러졌어요"
        else -> "바른 자세를 잘 유지하고 있어요"
    }
    val accent by animateColorAsState(
        when {
            s.alert -> Bj.Danger
            s.state == PostureState.BAD && !s.paused -> Color(0xFFE0B25B)
            else -> Bj.Live
        },
        label = "accent",
    )

    CameraBackdrop {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            PersonSilhouette(
                Modifier
                    .padding(bottom = 120.dp)
                    .width(260.dp)
                    .height(380.dp)
                    .alpha(if (s.state == PostureState.NO_PERSON) 0.25f else 1f)
            )
        }
        if (s.alert) {
            Box(Modifier.fillMaxSize().background(Bj.Danger.copy(alpha = 0.18f)))
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .safeDrawingPadding(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(14.dp))
        LivePill(paused = s.paused, color = accent)

        AnimatedVisibility(
            visible = s.alert && !s.paused,
            enter = fadeIn() + slideInVertically(),
            exit = fadeOut() + slideOutVertically(),
        ) {
            Row(
                Modifier
                    .padding(horizontal = 20.dp, vertical = 14.dp)
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(20.dp))
                    .background(Color.White.copy(alpha = 0.95f))
                    .padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(
                    Modifier.size(36.dp).clip(CircleShape).background(Bj.DangerSoft),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("!", color = Bj.Danger, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                }
                Spacer(Modifier.width(12.dp))
                Column {
                    Text("자세를 바로 해주세요", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Bj.Ink)
                    Text(
                        s.issues.firstOrNull()?.advice ?: "기준 자세에서 벗어났어요",
                        fontSize = 13.sp, color = Bj.Muted,
                    )
                }
            }
        }

        Spacer(Modifier.weight(1f))

        Text("오늘 집중한 시간", fontSize = 12.sp, color = Color.White.copy(alpha = 0.7f), letterSpacing = 1.5.sp)
        Text(
            formatTime(s.todayFocusSec),
            fontSize = 46.sp,
            fontWeight = FontWeight.SemiBold,
            fontFamily = FontFamily.SansSerif,
            color = Color.White,
            letterSpacing = 1.sp,
        )
        Spacer(Modifier.height(4.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(accent))
            Spacer(Modifier.width(7.dp))
            Text(message, fontSize = 14.sp, color = Color.White.copy(alpha = 0.85f))
        }
        Spacer(Modifier.height(6.dp))
        Text(
            "이번 공부 ${formatTime(s.focusSec)}" + if (s.warnings > 0) " · 경고 ${s.warnings}회" else "",
            fontSize = 12.sp,
            color = Color.White.copy(alpha = 0.6f),
        )

        Spacer(Modifier.height(36.dp))
        Row(
            Modifier.padding(bottom = 20.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            GlassButton(
                label = if (s.paused) "계속" else "일시정지",
                onClick = vm::togglePause,
            ) {
                if (s.paused) {
                    Text("▶", color = Bj.Live, fontSize = 12.sp)
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        Box(Modifier.size(3.dp, 12.dp).background(Color.White))
                        Box(Modifier.size(3.dp, 12.dp).background(Color.White))
                    }
                }
            }
            GlassButton(label = "종료", onClick = { confirmStop = true }) {
                Box(Modifier.size(11.dp).clip(RoundedCornerShape(3.dp)).background(Bj.StopDot))
            }
        }
    }

    if (confirmStop) {
        AlertDialog(
            onDismissRequest = { confirmStop = false },
            title = { Text("공부를 마칠까요?") },
            text = { Text("이번에 ${formatMinutes(s.focusSec)}, 오늘 모두 ${formatMinutes(s.todayFocusSec)} 집중했어요. 나중에 다시 시작하면 오늘 시간에 이어서 더해져요.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmStop = false
                    vm.stopStudy()
                }) { Text("종료", color = Bj.Danger) }
            },
            dismissButton = {
                TextButton(onClick = { confirmStop = false }) { Text("계속하기", color = Bj.Brand) }
            },
            containerColor = Color.White,
        )
    }
}

@Composable
private fun LivePill(paused: Boolean, color: Color) {
    val pulse by rememberInfiniteTransition(label = "pulse").animateFloat(
        initialValue = 1f,
        targetValue = 0.4f,
        animationSpec = infiniteRepeatable(tween(900), RepeatMode.Reverse),
        label = "dot",
    )
    Row(
        Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(Color(0x6B0A1915))
            .border(1.dp, Color.White.copy(alpha = 0.18f), RoundedCornerShape(999.dp))
            .padding(horizontal = 15.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(8.dp)
                .alpha(if (paused) 1f else pulse)
                .clip(CircleShape)
                .background(if (paused) Color.White.copy(alpha = 0.5f) else color)
        )
        Spacer(Modifier.width(8.dp))
        Text(
            if (paused) "학습 모드 일시정지" else "학습 모드 작동 중",
            fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Color.White.copy(alpha = 0.92f),
        )
    }
}

@Composable
private fun GlassButton(label: String, onClick: () -> Unit, icon: @Composable () -> Unit) {
    Row(
        Modifier
            .width(132.dp)
            .height(54.dp)
            .clip(RoundedCornerShape(18.dp))
            .background(Color(0xBF182522))
            .border(1.dp, Color.White.copy(alpha = 0.35f), RoundedCornerShape(18.dp))
            .clickable(onClick = onClick),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        icon()
        Spacer(Modifier.width(9.dp))
        Text(label, fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Color.White)
    }
}
