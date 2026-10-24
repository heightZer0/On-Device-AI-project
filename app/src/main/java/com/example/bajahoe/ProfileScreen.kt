package com.example.bajahoe

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun ProfileScreen(vm: AppViewModel) {
    BackHandler { vm.goHome() }
    var draft by rememberSaveable { mutableStateOf(vm.nickname) }
    val info = vm.client?.info

    Column(
        Modifier
            .fillMaxSize()
            .background(Bj.Cream)
            .safeDrawingPadding()
            .imePadding()
    ) {
        ScreenHeader(title = "프로필 편집", dark = false, onBack = vm::goHome)

        Column(
            Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(28.dp))
            Box(
                Modifier
                    .size(118.dp)
                    .shadow(14.dp, CircleShape, spotColor = Bj.Brand)
                    .clip(CircleShape)
                    .background(Color.White)
                    .padding(5.dp)
                    .clip(CircleShape)
                    .background(Bj.Mint),
            ) {
                Canvas(Modifier.fillMaxSize()) {
                    val w = size.width
                    val h = size.height
                    val c = Color(0xFF8DB8AB)
                    drawCircle(c, w * 0.16f, Offset(w / 2, h * 0.34f))
                    drawRoundRect(
                        c, Offset(w / 2 - w * 0.33f, h * 0.62f), Size(w * 0.66f, h * 0.45f),
                        CornerRadius(w * 0.33f, w * 0.33f),
                    )
                }
            }

            Spacer(Modifier.height(36.dp))
            Text("나를 어떻게 부를까요?", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Bj.Ink)
            Spacer(Modifier.height(8.dp))
            Text("입력한 정보는 이 기기에만 저장돼요.", fontSize = 13.sp, color = Bj.Muted)

            Spacer(Modifier.height(32.dp))
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it.take(12) },
                label = { Text("닉네임") },
                placeholder = { Text("닉네임을 입력해주세요") },
                singleLine = true,
                supportingText = { Text("${draft.length}/12", color = Bj.Muted) },
                shape = RoundedCornerShape(17.dp),
                colors = fieldColors(),
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(Modifier.height(24.dp))
            Column(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(18.dp))
                    .background(Color.White)
                    .border(1.dp, Bj.Line, RoundedCornerShape(18.dp))
                    .padding(start = 16.dp, top = 14.dp, bottom = 6.dp, end = 6.dp)
            ) {
                Text("연결된 기기", fontSize = 12.sp, color = Bj.Muted)
                Spacer(Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(info?.name ?: "없음", fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Bj.Ink)
                        if (info != null) Text(info.address, fontSize = 12.sp, color = Bj.Muted)
                    }
                    TextButton(onClick = vm::forgetDevice) {
                        Text(if (info == null) "기기 연결" else "연결 해제", color = Bj.Danger, fontSize = 14.sp)
                    }
                }
                Spacer(Modifier.width(1.dp))
            }
            Spacer(Modifier.height(24.dp))
        }

        Box(Modifier.padding(start = 22.dp, end = 22.dp, bottom = 16.dp, top = 8.dp)) {
            PrimaryButton(text = "저장", onClick = { vm.saveNickname(draft) })
        }
    }
}
