package com.example.bajahoe

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

private val SundayColor = Color(0xFFD9695C)
private val SaturdayColor = Color(0xFF5878A5)
private val ClockFormat: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

@Composable
fun CalendarScreen(vm: AppViewModel) {
    BackHandler { vm.goHome() }
    val month = vm.calendarMonth
    val stats = vm.monthStats
    val todayDate = LocalDate.now()

    val monthFocus = stats.values.sumOf { it.focusSec }
    val studyDays = stats.values.count { it.focusSec > 0 }
    val monthGood = stats.values.sumOf { it.goodSec }

    Column(
        Modifier
            .fillMaxSize()
            .background(Bj.Cream)
            .safeDrawingPadding()
    ) {
        ScreenHeader(title = "공부 캘린더", dark = false, onBack = vm::goHome)

        Column(
            Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 18.dp)
        ) {
            // 월 이동
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp, bottom = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                CircleIconButton(BjIcons.ChevronLeft, vm::prevMonth, dark = false, description = "이전 달")
                Text(
                    "${month.year}년 ${month.monthValue}월",
                    modifier = Modifier.weight(1f),
                    textAlign = TextAlign.Center,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    color = Bj.Ink,
                )
                CircleIconButton(BjIcons.Chevron, vm::nextMonth, dark = false, description = "다음 달")
            }
            if (month != YearMonth.now()) {
                Text(
                    "이번 달로 돌아가기",
                    fontSize = 13.sp,
                    color = Bj.BrandDark,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .align(Alignment.CenterHorizontally)
                        .clip(RoundedCornerShape(999.dp))
                        .clickable(onClick = vm::goThisMonth)
                        .padding(horizontal = 12.dp, vertical = 6.dp),
                )
                Spacer(Modifier.height(8.dp))
            }

            // 이번 달 요약
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(18.dp))
                    .background(Color.White)
                    .border(1.dp, Bj.Line, RoundedCornerShape(18.dp))
                    .padding(vertical = 14.dp),
            ) {
                SummaryStat("이번 달 공부", if (monthFocus == 0) "-" else formatMinutes(monthFocus), Modifier.weight(1f))
                SummaryStat("공부한 날", "${studyDays}일", Modifier.weight(1f))
                SummaryStat(
                    "하루 평균",
                    if (studyDays == 0) "-" else formatMinutes(monthFocus / studyDays),
                    Modifier.weight(1f),
                )
                SummaryStat(
                    "자세 유지율",
                    if (monthFocus == 0) "-" else "${monthGood * 100 / monthFocus}%",
                    Modifier.weight(1f),
                )
            }

            Spacer(Modifier.height(16.dp))

            // 요일 머리글 (일요일 시작)
            val weekdays = listOf(
                DayOfWeek.SUNDAY, DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY,
                DayOfWeek.THURSDAY, DayOfWeek.FRIDAY, DayOfWeek.SATURDAY,
            )
            Row(Modifier.fillMaxWidth()) {
                weekdays.forEach { d ->
                    Text(
                        d.getDisplayName(TextStyle.SHORT, Locale.KOREAN),
                        modifier = Modifier.weight(1f),
                        textAlign = TextAlign.Center,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = when (d) {
                            DayOfWeek.SUNDAY -> SundayColor
                            DayOfWeek.SATURDAY -> SaturdayColor
                            else -> Bj.Muted
                        },
                    )
                }
            }
            Spacer(Modifier.height(6.dp))

            // 날짜 칸
            val first = month.atDay(1)
            val offset = first.dayOfWeek.value % 7 // 일요일 = 0
            val days = month.lengthOfMonth()
            val weeks = (offset + days + 6) / 7
            for (w in 0 until weeks) {
                Row(Modifier.fillMaxWidth()) {
                    for (c in 0 until 7) {
                        val dayNum = w * 7 + c - offset + 1
                        if (dayNum < 1 || dayNum > days) {
                            Spacer(Modifier.weight(1f))
                        } else {
                            val date = month.atDay(dayNum)
                            DayCell(
                                date = date,
                                stat = stats[date],
                                isToday = date == todayDate,
                                isSelected = date == vm.selectedDate,
                                isFuture = date.isAfter(todayDate),
                                onClick = { vm.selectDate(date) },
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                }
            }

            // 범례
            Spacer(Modifier.height(10.dp))
            Row(
                Modifier.align(Alignment.End),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("적음", fontSize = 11.sp, color = Bj.Muted)
                Spacer(Modifier.width(6.dp))
                listOf(30 * 60, 60 * 60, 2 * 3600, 3 * 3600).forEach { sec ->
                    Box(
                        Modifier
                            .padding(horizontal = 2.dp)
                            .size(12.dp)
                            .clip(RoundedCornerShape(3.dp))
                            .background(heatColor(sec))
                    )
                }
                Spacer(Modifier.width(6.dp))
                Text("많음", fontSize = 11.sp, color = Bj.Muted)
            }

            // 선택한 날 상세
            Spacer(Modifier.height(18.dp))
            DayDetail(vm.selectedDate, vm.dayStat(vm.selectedDate), vm.selectedSessions)
            Spacer(Modifier.height(28.dp))
        }
    }
}

/** 공부 시간이 길수록 진한 초록 */
private fun heatColor(focusSec: Int): Color = when {
    focusSec <= 0 -> Color.Transparent
    focusSec < 30 * 60 -> Color(0xFFDCEFE9)
    focusSec < 60 * 60 -> Color(0xFFA9D8C8)
    focusSec < 2 * 3600 -> Color(0xFF5FAE97)
    else -> Bj.Brand
}

private fun shortTime(sec: Int): String {
    val m = sec / 60
    return when {
        sec <= 0 -> ""
        m < 1 -> "<1분"
        m < 60 -> "${m}분"
        else -> "${m / 60}:${"%02d".format(m % 60)}"
    }
}

@Composable
private fun DayCell(
    date: LocalDate,
    stat: DayStat?,
    isToday: Boolean,
    isSelected: Boolean,
    isFuture: Boolean,
    onClick: () -> Unit,
    modifier: Modifier,
) {
    val focus = stat?.focusSec ?: 0
    val bg = heatColor(focus)
    val dark = focus >= 60 * 60
    val numberColor = when {
        dark -> Color.White
        isFuture -> Bj.Muted.copy(alpha = 0.5f)
        date.dayOfWeek == DayOfWeek.SUNDAY -> SundayColor
        date.dayOfWeek == DayOfWeek.SATURDAY -> SaturdayColor
        else -> Bj.Ink
    }
    Box(
        modifier
            .padding(2.dp)
            .aspectRatio(0.82f)
            .clip(RoundedCornerShape(12.dp))
            .background(if (bg == Color.Transparent) Color.White.copy(alpha = 0.6f) else bg)
            .border(
                width = if (isSelected) 2.dp else 1.dp,
                color = when {
                    isSelected -> Bj.BrandDark
                    isToday -> Bj.Brand.copy(alpha = 0.6f)
                    else -> Bj.Line
                },
                shape = RoundedCornerShape(12.dp),
            )
            .clickable(onClick = onClick)
            .padding(vertical = 6.dp, horizontal = 2.dp),
    ) {
        Column(
            Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            if (isToday) {
                Box(
                    Modifier
                        .size(24.dp)
                        .clip(CircleShape)
                        .background(if (dark) Color.White else Bj.Brand),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "${date.dayOfMonth}",
                        fontSize = 13.sp, fontWeight = FontWeight.Bold,
                        color = if (dark) Bj.Brand else Color.White,
                    )
                }
            } else {
                Text("${date.dayOfMonth}", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = numberColor)
            }
            Spacer(Modifier.weight(1f))
            Text(
                shortTime(focus),
                fontSize = 10.sp,
                fontWeight = FontWeight.SemiBold,
                color = if (dark) Color.White else Bj.BrandDark,
                maxLines = 1,
                overflow = TextOverflow.Clip,
            )
        }
    }
}

@Composable
private fun SummaryStat(label: String, value: String, modifier: Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Bj.Ink, maxLines = 1)
        Spacer(Modifier.height(3.dp))
        Text(label, fontSize = 11.sp, color = Bj.Muted, maxLines = 1)
    }
}

@Composable
private fun DayDetail(date: LocalDate, stat: DayStat, sessions: List<SessionRecord>) {
    val weekday = date.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.KOREAN)
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(Color.White)
            .border(1.dp, Bj.Line, RoundedCornerShape(20.dp))
            .padding(18.dp)
    ) {
        Text(
            "${date.monthValue}월 ${date.dayOfMonth}일 ($weekday)",
            fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Bj.Ink,
        )
        Spacer(Modifier.height(12.dp))
        if (stat.focusSec == 0) {
            Text(
                if (date.isAfter(LocalDate.now())) "아직 오지 않은 날이에요." else "이날은 공부 기록이 없어요.",
                fontSize = 14.sp, color = Bj.Muted,
            )
        } else {
            DayDetailBody(stat, sessions)
        }
    }
}

@Composable
private fun DayDetailBody(stat: DayStat, sessions: List<SessionRecord>) {
    Column {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DetailChip("총 공부", formatTime(stat.focusSec), Modifier.weight(1.3f))
            DetailChip("자세 유지율", "${stat.postureRate}%", Modifier.weight(1f))
            DetailChip("공부 횟수", "${stat.sessions}회", Modifier.weight(1f))
        }
        if (stat.warnings > 0 || stat.awaySec > 0) {
            Spacer(Modifier.height(10.dp))
            Text(
                "자세 경고 ${stat.warnings}회 · 자리 비움 ${formatMinutes(stat.awaySec)}",
                fontSize = 13.sp, color = Bj.Muted,
            )
        }
        if (sessions.isNotEmpty()) {
            Spacer(Modifier.height(14.dp))
            Box(Modifier.fillMaxWidth().height(1.dp).background(Bj.Line))
            Spacer(Modifier.height(10.dp))
            Text("공부 기록", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Bj.Muted)
            sessions.forEach { r ->
                val start = java.time.Instant.ofEpochMilli(r.startedAt).atZone(java.time.ZoneId.systemDefault())
                val end = java.time.Instant.ofEpochMilli(r.endedAt).atZone(java.time.ZoneId.systemDefault())
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(top = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(Bj.Brand))
                    Spacer(Modifier.width(10.dp))
                    Text(
                        "${start.format(ClockFormat)} ~ ${end.format(ClockFormat)}",
                        fontSize = 14.sp, color = Bj.Ink, modifier = Modifier.weight(1f),
                    )
                    Text(
                        "${formatMinutes(r.focusSec)} · ${r.postureRate}%",
                        fontSize = 13.sp, color = Bj.Muted,
                    )
                }
            }
        }
    }
}

@Composable
private fun DetailChip(label: String, value: String, modifier: Modifier) {
    Column(
        modifier
            .clip(RoundedCornerShape(14.dp))
            .background(Bj.MintSoft)
            .padding(vertical = 12.dp, horizontal = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(value, fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Bj.Ink, maxLines = 1)
        Spacer(Modifier.height(2.dp))
        Text(label, fontSize = 11.sp, color = Bj.Muted)
    }
}
