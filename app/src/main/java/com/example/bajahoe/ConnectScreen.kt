package com.example.bajahoe

import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Android 17(API 37)부터 같은 Wi-Fi 기기에 접근하려면 필요한 권한 */
private const val LOCAL_NETWORK_PERMISSION = "android.permission.ACCESS_LOCAL_NETWORK"

@Composable
fun ConnectScreen(vm: AppViewModel) {
    var permissionAsked by remember { mutableStateOf(false) }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { permissionAsked = true }

    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= 37) permissionLauncher.launch(LOCAL_NETWORK_PERMISSION)
        else permissionAsked = true
    }

    DisposableEffect(permissionAsked) {
        if (permissionAsked) vm.discovery.start()
        onDispose { vm.discovery.stop() }
    }

    val found by vm.discovery.found.collectAsState()
    val searching by vm.discovery.searching.collectAsState()
    var host by rememberSaveable { mutableStateOf("") }
    var port by rememberSaveable { mutableStateOf(Protocol.DEFAULT_PORT.toString()) }

    Box(
        Modifier
            .fillMaxSize()
            .background(Bj.Cream)
            .safeDrawingPadding()
            .imePadding()
    ) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 22.dp)
        ) {
            Spacer(Modifier.height(36.dp))
            LogoTile(size = 52.dp, corner = 16.dp)
            Spacer(Modifier.height(22.dp))
            Text("기기를 연결해 주세요", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Bj.Ink, letterSpacing = (-1).sp)
            Spacer(Modifier.height(8.dp))
            Text(
                "바자회 기기와 휴대폰이 같은 Wi-Fi에 연결되어 있어야 해요.",
                fontSize = 14.sp, color = Bj.Muted, lineHeight = 21.sp,
            )

            Spacer(Modifier.height(30.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("주변 기기", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Bj.Ink)
                Spacer(Modifier.width(8.dp))
                if (searching) CircularProgressIndicator(Modifier.size(14.dp), color = Bj.Brand, strokeWidth = 2.dp)
            }
            Spacer(Modifier.height(10.dp))
            if (found.isEmpty()) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(18.dp))
                        .background(Color.White)
                        .border(1.dp, Bj.Line, RoundedCornerShape(18.dp))
                        .padding(18.dp)
                ) {
                    Text(
                        if (searching) "기기를 찾고 있어요…" else "찾은 기기가 없어요. 아래에 IP를 직접 입력해 보세요.",
                        fontSize = 13.sp, color = Bj.Muted,
                    )
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    found.forEach { d ->
                        DeviceRow(d) { vm.connectTo(d.host, d.port) }
                    }
                }
            }

            Spacer(Modifier.height(28.dp))
            Text("직접 입력", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Bj.Ink)
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    value = host,
                    onValueChange = { host = it.trim() },
                    label = { Text("IP 주소") },
                    placeholder = { Text("192.168.0.20") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    shape = RoundedCornerShape(16.dp),
                    colors = fieldColors(),
                    modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    value = port,
                    onValueChange = { v -> port = v.filter { it.isDigit() }.take(5) },
                    label = { Text("포트") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    shape = RoundedCornerShape(16.dp),
                    colors = fieldColors(),
                    modifier = Modifier.width(96.dp),
                )
            }
            Text(
                "에뮬레이터에서 PC의 모의 서버에 연결할 때는 10.0.2.2 를 입력하세요.",
                fontSize = 12.sp, color = Bj.Muted, modifier = Modifier.padding(top = 8.dp),
            )

            vm.connectError?.let {
                Spacer(Modifier.height(14.dp))
                Box(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(Bj.DangerSoft)
                        .padding(14.dp)
                ) {
                    Text(it, fontSize = 13.sp, color = Bj.Danger, lineHeight = 19.sp)
                }
            }

            Spacer(Modifier.height(20.dp))
            PrimaryButton(
                text = if (vm.connecting) "연결하는 중…" else "연결하기",
                onClick = { vm.connectTo(host, port.toIntOrNull() ?: Protocol.DEFAULT_PORT) },
                enabled = !vm.connecting && host.isNotBlank(),
            )
            Spacer(Modifier.height(8.dp))
            TextButton(
                onClick = vm::connectDemo,
                modifier = Modifier.align(Alignment.CenterHorizontally),
            ) {
                Text("기기 없이 데모 모드로 둘러보기", color = Bj.BrandDark, fontSize = 14.sp)
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun DeviceRow(device: FoundDevice, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(Bj.PostureCard)
            .border(1.dp, Bj.Brand.copy(alpha = 0.1f), RoundedCornerShape(18.dp))
            .clickable(onClick = onClick)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(44.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(Color.White),
            contentAlignment = Alignment.Center,
        ) {
            BjIcon(BjIcons.Device, Bj.Brand, 24.dp)
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(device.serviceName, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Bj.Ink)
            Text("${device.host}:${device.port}", fontSize = 12.sp, color = Bj.Muted)
        }
        BjIcon(BjIcons.Chevron, Color(0xFF8BA19B), 20.dp)
    }
}

@Composable
fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = Bj.Brand,
    unfocusedBorderColor = Bj.Line,
    focusedLabelColor = Bj.Brand,
    cursorColor = Bj.Brand,
    focusedContainerColor = Color.White,
    unfocusedContainerColor = Color.White,
)
