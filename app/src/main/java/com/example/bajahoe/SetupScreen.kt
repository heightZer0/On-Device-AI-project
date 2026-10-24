package com.example.bajahoe

import androidx.activity.compose.BackHandler
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 시작 전 자세설정(initial = true)과 자세 재설정(initial = false) */
@Composable
fun SetupScreen(vm: AppViewModel, initial: Boolean) {
    // 시작 전 자세설정은 건너뛸 수 없다
    BackHandler(enabled = initial) { }
    BackHandler(enabled = !initial) { vm.goHome() }

    val client = vm.client
    val connected = vm.link == LinkState.CONNECTED
    val detect = vm.detect
    val ready = connected && detect?.ready == true

    CameraBackdrop {
        // 카메라 미리보기. 데모이거나 영상이 없으면 실루엣을 보여준다
        if (client != null && !client.info.isDemo && connected) {
            MjpegPreview(
                url = client.info.previewUrl,
                modifier = Modifier.fillMaxSize(),
                placeholder = { SilhouetteLayer() },
            )
        } else {
            SilhouetteLayer()
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .safeDrawingPadding()
    ) {
        ScreenHeader(
            title = if (initial) "시작 전 자세설정" else "자세 재설정",
            dark = true,
            onBack = if (initial) null else vm::goHome,
        )

        // 안내 배너
        Row(
            Modifier
                .padding(horizontal = 20.dp, vertical = 6.dp)
                .fillMaxWidth()
                .shadow(12.dp, RoundedCornerShape(22.dp))
                .clip(RoundedCornerShape(22.dp))
                .background(Color.White.copy(alpha = 0.94f))
                .padding(horizontal = 18.dp, vertical = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center,
        ) {
            Box(
                Modifier
                    .size(18.dp)
                    .clip(CircleShape)
                    .background(Bj.Mint),
                contentAlignment = Alignment.Center,
            ) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(Bj.Brand))
            }
            Spacer(Modifier.width(12.dp))
            Text(
                buildAnnotatedString {
                    append(if (initial) "시작하기 전에\n" else "카메라를 보고\n")
                    withStyle(SpanStyle(color = Bj.BrandDark, fontWeight = FontWeight.Bold, fontSize = 17.sp)) {
                        append("바른 자세를 설정해주세요")
                    }
                },
                fontSize = 15.sp,
                color = Bj.Ink,
                lineHeight = 23.sp,
            )
        }

        // 가이드
        Box(
            Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentAlignment = Alignment.Center,
        ) {
            AlignmentGuide(
                ready = ready,
                modifier = Modifier
                    .padding(vertical = 16.dp)
                    .width(250.dp)
                    .height(340.dp),
            )
        }

        // 인식 상태
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
        ) {
            DetectChip("얼굴", connected && detect?.face == true)
            DetectChip("어깨", connected && detect?.shoulders == true)
            DetectChip("자세 고정", connected && detect?.stable == true)
        }
        Spacer(Modifier.height(10.dp))
        Text(
            text = when {
                !connected -> "기기에 연결하는 중이에요…"
                ready -> "좋아요! 이 자세를 기준으로 저장할게요"
                else -> "얼굴과 어깨가 가이드 안에 오도록 맞춰주세요"
            },
            fontSize = 13.sp,
            color = Color.White.copy(alpha = 0.85f),
            modifier = Modifier.align(Alignment.CenterHorizontally),
        )

        vm.calibrationError?.let {
            Text(
                it,
                fontSize = 13.sp,
                color = Bj.StopDot,
                modifier = Modifier
                    .align(Alignment.CenterHorizontally)
                    .padding(top = 8.dp, start = 20.dp, end = 20.dp),
            )
        }

        Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 18.dp, bottom = 16.dp)) {
            PrimaryButton(
                text = when {
                    vm.calibrating -> "기준 자세 저장 중…"
                    initial -> "설정 완료하고 시작하기"
                    else -> "설정 완료"
                },
                onClick = vm::confirmCalibration,
                enabled = ready && !vm.calibrating,
                icon = BjIcons.Check,
            )
            if (!connected) {
                TextButton(
                    onClick = vm::openConnect,
                    modifier = Modifier.align(Alignment.CenterHorizontally),
                ) {
                    Text("다른 기기 선택하기", color = Color.White.copy(alpha = 0.85f), fontSize = 13.sp)
                }
            }
        }
    }
}

@Composable
private fun SilhouetteLayer() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        PersonSilhouette(
            Modifier
                .padding(top = 40.dp)
                .width(240.dp)
                .height(330.dp)
        )
    }
}

@Composable
private fun DetectChip(label: String, ok: Boolean) {
    Row(
        Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(if (ok) Bj.Brand.copy(alpha = 0.85f) else Color(0x5C0A1915))
            .border(1.dp, Color.White.copy(alpha = if (ok) 0.35f else 0.18f), RoundedCornerShape(999.dp))
            .padding(horizontal = 12.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (ok) {
            BjIcon(BjIcons.Check, Color.White, 14.dp)
        } else {
            Box(Modifier.size(6.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.5f)))
        }
        Spacer(Modifier.width(6.dp))
        Text(label, fontSize = 12.sp, color = Color.White, fontWeight = FontWeight.Medium)
    }
}
