package com.example.bajahoe

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun ResultScreen(vm: AppViewModel) {
    BackHandler { vm.goHome() }
    val r = vm.lastResult ?: SessionRecord(0L, System.currentTimeMillis(), 0, 0, 0, 0, null)
    val rate = r.postureRate
    val top = PostureIssue.parse(r.topIssue)
    val comment = when {
        r.focusSec < 60 -> "짧은 세션이었어요. 다음엔 조금 더 길게 집중해 봐요."
        rate >= 85 -> "아주 좋아요! 바른 자세를 잘 지켰어요."
        rate >= 60 -> "괜찮아요. 조금만 더 신경 쓰면 완벽해요."
        else -> "자세가 자주 흐트러졌어요. 중간중간 스트레칭을 해 보세요."
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(Bj.Cream)
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(36.dp))
        Text("STUDY REPORT", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Bj.Brand, letterSpacing = 1.6.sp)
        Spacer(Modifier.height(8.dp))
        Text("오늘의 집중 결과", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = Bj.Ink)

        Spacer(Modifier.height(28.dp))
        Box(Modifier.size(190.dp), contentAlignment = Alignment.Center) {
            RateRing(rate / 100f, Modifier.fillMaxSize())
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("$rate%", fontSize = 40.sp, fontWeight = FontWeight.Bold, color = Bj.Ink)
                Text("자세 유지율", fontSize = 13.sp, color = Bj.Muted)
            }
        }
        Spacer(Modifier.height(18.dp))
        Text(comment, fontSize = 15.sp, color = Bj.Ink, fontWeight = FontWeight.Medium)

        Spacer(Modifier.height(26.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            StatCard("이번 공부", formatTime(r.focusSec), Modifier.weight(1f))
            StatCard("오늘 누적", formatTime(vm.today.focusSec), Modifier.weight(1f))
        }
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            StatCard("자세 경고", "${r.warnings}회", Modifier.weight(1f))
            StatCard("자리 비움", formatMinutes(r.awaySec), Modifier.weight(1f))
        }

        if (top != null) {
            Spacer(Modifier.height(12.dp))
            Column(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(18.dp))
                    .background(Bj.DangerSoft)
                    .padding(16.dp)
            ) {
                Text("가장 많이 흐트러진 자세", fontSize = 12.sp, color = Bj.Danger, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(4.dp))
                Text(top.label, fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Bj.Ink)
                Spacer(Modifier.height(4.dp))
                Text(tipFor(top), fontSize = 13.sp, color = Bj.Muted, lineHeight = 19.sp)
            }
        }

        Spacer(Modifier.height(32.dp))
        PrimaryButton(text = "홈으로", onClick = vm::goHome)
        androidx.compose.material3.TextButton(onClick = vm::openCalendar) {
            Text("캘린더에서 보기", color = Bj.BrandDark, fontSize = 14.sp)
        }
        Spacer(Modifier.height(24.dp))
    }
}

private fun tipFor(issue: PostureIssue): String = when (issue) {
    PostureIssue.HEAD_DOWN -> "책이나 화면을 눈높이 가까이 올리면 고개를 덜 숙이게 돼요."
    PostureIssue.TOO_CLOSE -> "화면과 눈 사이는 팔 길이 정도로 두는 것이 좋아요."
    PostureIssue.SHOULDER_TILT -> "한쪽 팔꿈치로 기대지 말고 양 어깨 높이를 맞춰 보세요."
    PostureIssue.LEANING -> "의자 깊숙이 앉아 등받이에 허리를 붙여 보세요."
}

@Composable
private fun RateRing(progress: Float, modifier: Modifier) {
    Canvas(modifier) {
        val stroke = 16.dp.toPx()
        val inset = stroke / 2
        val arcSize = Size(size.width - stroke, size.height - stroke)
        drawArc(Bj.Mint, 0f, 360f, false, Offset(inset, inset), arcSize, style = Stroke(stroke))
        drawArc(
            Bj.Brand, -90f, 360f * progress.coerceIn(0f, 1f), false,
            Offset(inset, inset), arcSize,
            style = Stroke(stroke, cap = StrokeCap.Round),
        )
    }
}

@Composable
private fun StatCard(label: String, value: String, modifier: Modifier) {
    Column(
        modifier
            .clip(RoundedCornerShape(18.dp))
            .background(Color.White)
            .border(1.dp, Bj.Line, RoundedCornerShape(18.dp))
            .padding(vertical = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(value, fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Bj.Ink)
        Spacer(Modifier.height(4.dp))
        Text(label, fontSize = 12.sp, color = Bj.Muted)
    }
}
