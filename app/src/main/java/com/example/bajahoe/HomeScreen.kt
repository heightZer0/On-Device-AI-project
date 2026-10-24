package com.example.bajahoe

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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Calendar

@Composable
fun HomeScreen(vm: AppViewModel) {
    val greeting = remember {
        when (Calendar.getInstance().get(Calendar.HOUR_OF_DAY)) {
            in 5..10 -> "GOOD MORNING"
            in 11..16 -> "GOOD AFTERNOON"
            in 17..21 -> "GOOD EVENING"
            else -> "LATE NIGHT STUDY"
        }
    }
    val today = vm.today
    val todayFocus = today.focusSec
    val todayRate = if (todayFocus == 0) null else today.postureRate

    Column(
        Modifier
            .fillMaxSize()
            .background(Bj.Cream)
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp)
    ) {
        // 상단
        Row(
            Modifier
                .fillMaxWidth()
                .height(62.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            LogoTile(size = 30.dp, corner = 10.dp)
            Spacer(Modifier.width(8.dp))
            Text("바자회", fontSize = 19.sp, fontWeight = FontWeight.Bold, color = Bj.Ink, letterSpacing = (-1).sp)
            Spacer(Modifier.weight(1f))
            LinkChip(vm.link, vm.client?.info, onClick = vm::openSettings)
            Spacer(Modifier.width(6.dp))
            Box(
                Modifier
                    .size(36.dp)
                    .clip(CircleShape)
                    .clickable(onClickLabel = "설정", onClick = vm::openSettings),
                contentAlignment = Alignment.Center,
            ) {
                BjIcon(BjIcons.Gear, Bj.Muted, 22.dp)
            }
            Spacer(Modifier.width(4.dp))
            Box(
                Modifier
                    .size(36.dp)
                    .clip(CircleShape)
                    .background(Bj.Mint)
                    .clickable(onClickLabel = "프로필 편집", onClick = vm::openProfile),
                contentAlignment = Alignment.Center,
            ) {
                Text(vm.nickname.take(1), fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Bj.BrandDark)
            }
        }

        // 인사
        Spacer(Modifier.height(22.dp))
        Text(greeting, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Bj.Brand, letterSpacing = 1.6.sp)
        Spacer(Modifier.height(10.dp))
        Text(
            "${vm.nickname}님, 오늘도\n바른 자세로 집중해 볼까요?",
            fontSize = 28.sp,
            lineHeight = 38.sp,
            fontWeight = FontWeight.Bold,
            color = Bj.Ink,
            letterSpacing = (-1.2).sp,
        )
        Spacer(Modifier.height(10.dp))
        Text("작은 습관이 더 편안한 하루를 만들어요.", fontSize = 14.sp, color = Bj.Muted)

        // 주요 기능
        Spacer(Modifier.height(28.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(13.dp)) {
            ActionCard(
                title = "자세 재설정",
                caption = "기준 자세를\n다시 맞춰보세요",
                icon = BjIcons.Camera,
                iconTint = Bj.Brand,
                background = Bj.PostureCard,
                onClick = vm::openReset,
                modifier = Modifier.weight(1f),
            )
            ActionCard(
                title = "공부 시작",
                caption = "집중 세션을\n바로 시작해요",
                icon = BjIcons.Focus,
                iconTint = Bj.Blue,
                background = Bj.FocusCard,
                onClick = vm::startStudy,
                modifier = Modifier.weight(1f),
            )
        }

        // 오늘 기록 → 캘린더
        Spacer(Modifier.height(16.dp))
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(18.dp))
                .background(Color.White)
                .border(1.dp, Bj.Line, RoundedCornerShape(18.dp))
                .clickable(onClickLabel = "공부 캘린더 열기", onClick = vm::openCalendar)
                .padding(top = 14.dp, bottom = 16.dp),
        ) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(start = 16.dp, end = 12.dp, bottom = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                BjIcon(BjIcons.Calendar, Bj.Brand, 18.dp)
                Spacer(Modifier.width(6.dp))
                Text("오늘의 기록", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Bj.Ink)
                Spacer(Modifier.weight(1f))
                Text("캘린더 보기", fontSize = 12.sp, color = Bj.BrandDark, fontWeight = FontWeight.SemiBold)
                BjIcon(BjIcons.Chevron, Bj.BrandDark, 16.dp)
            }
            Row(Modifier.fillMaxWidth()) {
                TodayStat("오늘 집중", if (todayFocus == 0) "-" else formatMinutes(todayFocus), Modifier.weight(1f))
                Box(Modifier.width(1.dp).height(36.dp).background(Bj.Line).align(Alignment.CenterVertically))
                TodayStat("자세 유지율", todayRate?.let { "$it%" } ?: "-", Modifier.weight(1f))
                Box(Modifier.width(1.dp).height(36.dp).background(Bj.Line).align(Alignment.CenterVertically))
                TodayStat("공부 횟수", "${today.sessions}회", Modifier.weight(1f))
            }
        }

        // 팁
        Spacer(Modifier.height(12.dp))
        Row(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(18.dp))
                .background(Color.White.copy(alpha = 0.55f))
                .border(1.dp, Bj.Line, RoundedCornerShape(18.dp))
                .padding(15.dp),
        ) {
            LogoTile(size = 30.dp, corner = 9.dp)
            Spacer(Modifier.width(12.dp))
            Column {
                Text("오늘의 바른 팁", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Bj.Ink)
                Spacer(Modifier.height(3.dp))
                Text(
                    "어깨에 힘을 빼고 화면은 눈높이에 맞춰주세요.",
                    fontSize = 12.sp, color = Bj.Muted, lineHeight = 18.sp,
                )
            }
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun ActionCard(
    title: String,
    caption: String,
    icon: ImageVector,
    iconTint: Color,
    background: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier
            .heightIn(min = 190.dp)
            .shadow(8.dp, RoundedCornerShape(24.dp), ambientColor = Color(0x121F4C42), spotColor = Color(0x261F4C42))
            .clip(RoundedCornerShape(24.dp))
            .background(background)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 20.dp),
    ) {
        BjIcon(
            BjIcons.Chevron, Color(0xFF8BA19B), 20.dp,
            Modifier.align(Alignment.TopEnd),
        )
        Column(
            Modifier.align(Alignment.Center),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(
                Modifier
                    .size(58.dp)
                    .clip(RoundedCornerShape(19.dp))
                    .background(Color.White),
                contentAlignment = Alignment.Center,
            ) {
                BjIcon(icon, iconTint, 30.dp)
            }
            Spacer(Modifier.height(15.dp))
            Text(title, fontSize = 19.sp, fontWeight = FontWeight.Bold, color = Bj.Ink, letterSpacing = (-0.8).sp)
            Spacer(Modifier.height(6.dp))
            Text(caption, fontSize = 12.sp, color = Bj.Muted, textAlign = TextAlign.Center, lineHeight = 17.sp)
        }
    }
}

@Composable
private fun TodayStat(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontSize = 17.sp, fontWeight = FontWeight.Bold, color = Bj.Ink)
        Spacer(Modifier.height(3.dp))
        Text(label, fontSize = 12.sp, color = Bj.Muted)
    }
}
