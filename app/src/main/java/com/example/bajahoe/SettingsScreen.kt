package com.example.bajahoe

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.roundToInt

@Composable
fun SettingsScreen(vm: AppViewModel) {
    BackHandler { vm.goHome() }
    val info = vm.client?.info
    val connected = vm.link == LinkState.CONNECTED

    Column(
        Modifier
            .fillMaxSize()
            .background(Bj.Cream)
            .safeDrawingPadding()
    ) {
        ScreenHeader(title = "설정", dark = false, onBack = vm::goHome)

        Column(
            Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
        ) {
            // ---------------- 음성 안내 ----------------
            SectionTitle("음성 안내")
            SettingsCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconTile(if (vm.muted) BjIcons.SpeakerOff else BjIcons.Speaker)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("기기 스피커 볼륨", fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Bj.Ink)
                        Text("자세 경고를 소리로 알려줘요", fontSize = 12.sp, color = Bj.Muted)
                    }
                    Text(
                        if (vm.muted) "음소거" else "${vm.volume}%",
                        fontSize = 15.sp, fontWeight = FontWeight.Bold,
                        color = if (vm.muted) Bj.Muted else Bj.Brand,
                    )
                }
                Spacer(Modifier.height(6.dp))
                Slider(
                    value = vm.volume.toFloat(),
                    onValueChange = { vm.changeVolume(it.roundToInt()) },
                    valueRange = 0f..100f,
                    enabled = !vm.muted,
                    colors = SliderDefaults.colors(
                        thumbColor = Bj.Brand,
                        activeTrackColor = Bj.Brand,
                        inactiveTrackColor = Bj.Mint,
                    ),
                )
                Divider()
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("음소거", fontSize = 15.sp, color = Bj.Ink, modifier = Modifier.weight(1f))
                    Switch(
                        checked = vm.muted,
                        onCheckedChange = vm::changeMuted,
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = Color.White,
                            checkedTrackColor = Bj.Brand,
                            uncheckedThumbColor = Color.White,
                            uncheckedTrackColor = Bj.Line,
                            uncheckedBorderColor = Bj.Line,
                        ),
                    )
                }
                Divider()
                Spacer(Modifier.height(12.dp))
                val canTest = connected && !vm.muted && info?.isDemo == false
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(48.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(if (canTest) Bj.PostureCard else Bj.Line.copy(alpha = 0.5f))
                        .clickable(enabled = canTest, onClick = vm::playTestSound),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "테스트 소리 듣기",
                        fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                        color = if (canTest) Bj.BrandDark else Bj.Muted,
                    )
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    when {
                        info == null -> "기기를 연결하면 볼륨이 기기에 적용돼요."
                        info.isDemo -> "데모 모드에서는 소리가 나지 않아요. 실제 기기를 연결하면 적용돼요."
                        !connected -> "기기와 다시 연결되면 지금 설정이 자동으로 적용돼요."
                        else -> "${info.name}에 바로 적용돼요."
                    },
                    fontSize = 12.sp, color = Bj.Muted, lineHeight = 17.sp,
                )
            }

            // ---------------- 글씨 크기 ----------------
            SectionTitle("글씨 크기")
            SettingsCard {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextSize.entries.forEach { size ->
                        val selected = vm.textSize == size
                        Box(
                            Modifier
                                .weight(1f)
                                .heightIn(min = 56.dp)
                                .clip(RoundedCornerShape(14.dp))
                                .background(if (selected) Bj.Brand else Bj.MintSoft)
                                .border(
                                    1.dp,
                                    if (selected) Bj.Brand else Bj.Line,
                                    RoundedCornerShape(14.dp),
                                )
                                .clickable { vm.changeTextSize(size) }
                                .padding(vertical = 8.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(
                                    "가",
                                    fontSize = (16 * size.scale / vm.textSize.scale).sp,
                                    fontWeight = FontWeight.Bold,
                                    color = if (selected) Color.White else Bj.Ink,
                                )
                                Text(
                                    size.label,
                                    fontSize = 11.sp,
                                    color = if (selected) Color.White else Bj.Muted,
                                    textAlign = TextAlign.Center,
                                )
                            }
                        }
                    }
                }
                Spacer(Modifier.height(14.dp))
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(Bj.Cream)
                        .border(1.dp, Bj.Line, RoundedCornerShape(14.dp))
                        .padding(14.dp)
                ) {
                    Text("미리보기", fontSize = 11.sp, color = Bj.Brand, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(6.dp))
                    Text("오늘도 바른 자세로 집중해 볼까요?", fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Bj.Ink)
                    Spacer(Modifier.height(4.dp))
                    Text("작은 습관이 더 편안한 하루를 만들어요.", fontSize = 14.sp, color = Bj.Muted)
                }
                Spacer(Modifier.height(8.dp))
                Text("앱 전체 글씨에 바로 적용돼요.", fontSize = 12.sp, color = Bj.Muted)
            }

            // ---------------- 정보 ----------------
            SectionTitle("정보")
            SettingsCard {
                InfoRow("연결된 기기", info?.name ?: "없음")
                Divider()
                InfoRow("기기 주소", info?.address ?: "-")
                Divider()
                InfoRow("앱 버전", Protocol.APP_VERSION)
            }
            Spacer(Modifier.height(28.dp))
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text,
        fontSize = 13.sp,
        fontWeight = FontWeight.SemiBold,
        color = Bj.Muted,
        modifier = Modifier.padding(start = 4.dp, top = 22.dp, bottom = 8.dp),
    )
}

@Composable
private fun SettingsCard(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(Color.White)
            .border(1.dp, Bj.Line, RoundedCornerShape(20.dp))
            .padding(16.dp),
        content = content,
    )
}

@Composable
private fun IconTile(icon: androidx.compose.ui.graphics.vector.ImageVector) {
    Box(
        Modifier
            .size(40.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(Bj.PostureCard),
        contentAlignment = Alignment.Center,
    ) {
        BjIcon(icon, Bj.Brand, 22.dp)
    }
}

@Composable
private fun Divider() {
    Box(
        Modifier
            .fillMaxWidth()
            .height(1.dp)
            .background(Bj.Line)
    )
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, fontSize = 14.sp, color = Bj.Muted, modifier = Modifier.weight(1f))
        Text(value, fontSize = 14.sp, color = Bj.Ink, fontWeight = FontWeight.Medium)
    }
}
