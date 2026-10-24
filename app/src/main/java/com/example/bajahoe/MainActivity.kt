package com.example.bajahoe

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.Density
import androidx.core.view.WindowCompat
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            BajahoeAppTheme {
                val vm: AppViewModel = viewModel()
                BajahoeApp(vm)
            }
        }
    }
}

@Composable
fun BajahoeApp(vm: AppViewModel) {
    val screen = vm.screen

    // 카메라 화면(어두운 배경)에서는 상태바 아이콘을 흰색으로
    val view = LocalView.current
    val darkScreen = screen == Screen.SETUP_INITIAL || screen == Screen.SETUP_RESET || screen == Screen.STUDY
    SideEffect {
        val window = (view.context as? android.app.Activity)?.window ?: return@SideEffect
        WindowCompat.getInsetsController(window, view).apply {
            isAppearanceLightStatusBars = !darkScreen
            isAppearanceLightNavigationBars = !darkScreen
        }
    }

    // 설정의 글씨 크기를 앱 전체에 적용한다 (휴대폰 시스템 글씨 크기에 곱해짐)
    val baseDensity = LocalDensity.current
    val scaledDensity = Density(baseDensity.density, baseDensity.fontScale * vm.textSize.scale)

    CompositionLocalProvider(LocalDensity provides scaledDensity) {
        Crossfade(targetState = screen, animationSpec = tween(350), label = "screen") { s ->
            Box(Modifier.fillMaxSize()) {
                when (s) {
                    Screen.SPLASH -> SplashScreen(onContinue = vm::onSplashFinished)
                    Screen.CONNECT -> ConnectScreen(vm)
                    Screen.SETUP_INITIAL -> SetupScreen(vm, initial = true)
                    Screen.SETUP_RESET -> SetupScreen(vm, initial = false)
                    Screen.HOME -> HomeScreen(vm)
                    Screen.STUDY -> StudyScreen(vm)
                    Screen.RESULT -> ResultScreen(vm)
                    Screen.PROFILE -> ProfileScreen(vm)
                    Screen.SETTINGS -> SettingsScreen(vm)
                    Screen.CALENDAR -> CalendarScreen(vm)
                }
            }
        }
    }
}
