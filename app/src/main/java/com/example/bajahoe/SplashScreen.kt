package com.example.bajahoe

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

@Composable
fun SplashScreen(onContinue: () -> Unit) {
    LaunchedEffect(Unit) {
        delay(3500)
        onContinue()
    }
    val float by rememberInfiniteTransition(label = "float").animateFloat(
        initialValue = 0f,
        targetValue = -6f,
        animationSpec = infiniteRepeatable(tween(1500), RepeatMode.Reverse),
        label = "logo",
    )

    Box(
        Modifier
            .fillMaxSize()
            .background(Bj.MintSoft)
            .background(
                Brush.radialGradient(
                    listOf(Color.White.copy(alpha = 0.95f), Color.Transparent),
                    radius = 700f,
                )
            )
            .clickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                onClick = onContinue,
            )
            .safeDrawingPadding(),
    ) {
        Column(
            Modifier.align(Alignment.Center),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            LogoTile(
                size = 104.dp,
                corner = 32.dp,
                modifier = Modifier
                    .graphicsLayer { translationY = float * density }
                    .shadow(18.dp, RoundedCornerShape(32.dp), spotColor = Bj.Brand),
            )
            Spacer(Modifier.height(26.dp))
            Text("바자회", fontSize = 34.sp, fontWeight = FontWeight.Bold, color = Bj.Ink, letterSpacing = (-2).sp)
            Spacer(Modifier.height(10.dp))
            Text("작은 습관이 더 나은 결과를", fontSize = 13.sp, color = Bj.Muted, letterSpacing = 0.8.sp)
        }
        Row(
            Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 40.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center,
        ) {
            Text("시작하기", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Bj.BrandDark)
            BjIcon(BjIcons.Chevron, Bj.BrandDark, 16.dp)
        }
    }
}
