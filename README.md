# 바자회 — 온디바이스 공부 자세 코칭

공부하는 동안 카메라로 자세를 확인하고, 거북목 자세가 이어지면 **앱 경고와 기기 음성으로 알려 주는** 서비스입니다.
자세 분석, 음성 인식, 음성 명령 해석(LLM), 음성 합성이 모두 책상 위 **Orange Pi 5 Plus 안에서** 처리됩니다. 인터넷이 없어도 동작합니다.

이 저장소(브랜치 `app`)는 그중 **안드로이드 앱**입니다. 보드 쪽 서버는 팀 저장소 `develop` 브랜치에 있습니다.

- 앱은 **P2 서버 하나에만** 연결합니다. LLM과 음성은 P2가 부릅니다.
- 카메라 영상은 자세설정 화면과 공부 화면의 미리보기에만 쓰이고, 저장하지 않습니다.
- 공부 기록은 휴대폰 안에만 저장됩니다.
## 👀 Members

<table width="50%" align="center">
    <tr>
        <td align="center"><img src="https://avatars.githubusercontent.com/u/프로필이미지링크" /></td>
        <td align="center"><img src="https://avatars.githubusercontent.com/u/65843682?v=4" /></td>
        <td align="center"><img src="https://avatars.githubusercontent.com/u/프로필이미지링크"></td>
        <td align="center"><img src="https://avatars.githubusercontent.com/u/프로필이미지링크"></td>
        <td align="center"><img src="https://avatars.githubusercontent.com/u/프로필이미지링크"></td>
    </tr>
    <tr>
        <td align="center"><b><a href="https://github.com/heightZer0">고도영</a></b></td>
        <td align="center"><b><a href="https://github.com/EldaKo">고현아</a></b></td>
        <td align="center"><b><a href="https://github.com/아이디넣기">김동현</a></b></td>
        <td align="center"><b><a href="https://github.com/ㅇㅇㄷ">이승민</a></b></td>
        <td align="center"><b><a href="https://github.com/ㅇㅇㄷ">이재혁</a></b></td>
    </tr>
    <tr>
        <td align="center"><b>팀장</b></td>
        <td align="center"><b>앱 개발, API 연결</b></td>
        <td align="center"><b>김동현</b></td>
        <td align="center"><b>이승민</b></td>
        <td align="center"><b>이재혁</b></td>
    </tr>
</table>

---

## 주요 기능

| 화면 | 내용 |
|---|---|
| 기기 연결 | 같은 Wi-Fi의 기기 자동 검색(mDNS), IP·포트·토큰 직접 입력, 기기 없이 둘러보는 데모 모드 |
| 자세설정 | 카메라 미리보기를 보며 5초 동안 기준 자세 측정. 진행률 표시, 실패 시 이유 안내 후 자동 재측정 |
| 홈 | 자세 재설정, 공부 시작, 오늘의 기록 |
| 공부 | 오늘 누적 집중 시간 타이머, 배경에 내 모습. 거북목이 이어지면 경고 배너 + 진동 + 기기 음성 경고 |
| 결과 | 이번 공부·오늘 누적 시간, 자세 유지율, 경고 횟수, 가장 많이 흐트러진 자세와 팁 |
| 캘린더 | 월별 공부 기록, 날짜별 시간과 세션 목록 |
| 설정 | 기기 스피커 볼륨·음소거·테스트 음성, 앱 글씨 크기 |
| 프로필 | 닉네임, 연결된 기기 해제 |

### 음성 명령과 앱 연동

마이크에 말하면 기기가 음성으로 대답하고, 측정 상태가 바뀌면 **앱 화면도 따라갑니다.** 호출어는 없습니다.

| 말하기 예시 | 기기 | 앱 |
|---|---|---|
| "공부 시작할게" (홈·결과·캘린더·설정 화면에서) | 측정 시작 | 공부 화면으로 자동 이동 |
| "잠깐 멈춰줘" / "다시 시작해 줘" | 일시정지 / 재개 | 일시정지 표시 / 해제 |
| "측정 중지해 줘" | 측정 종료, 기록 저장 | 결과 화면으로 이동 |
| "내 자세 괜찮아?" | 현재 자세를 음성으로 안내 | — |
| "목 스트레칭 알려줘" | 스트레칭 안내 | — |
| "몸이 좀 뻐근해" | "어느 부위를 풀어 드릴까요?" 재질문 (30초 안에 대답) | — |
| "30분 뒤에 쉬라고 알려줘" | 휴식 알림 설정 | — |

LLM은 학습한 16가지 명령만 다루며, 범위 밖 요청("날씨 어때?")은 지원하지 않는다고 안내합니다.

## 개발 환경

- Android Studio, Kotlin, Jetpack Compose (Material 3)
- minSdk 26 (Android 8.0) / targetSdk 37
- 통신: OkHttp (REST, 카메라 미리보기)

## 앱 실행

1. Android Studio에서 이 폴더를 엽니다.
2. Gradle 동기화가 끝나면 휴대폰을 USB로 연결하고 **Run**을 누릅니다.
3. 휴대폰을 기기와 **같은 Wi-Fi**에 연결하고(모바일 데이터 끄기), 연결 화면에 기기 IP, 포트 `8000`, 기기 토큰을 입력합니다.
4. 기기가 없으면 **기기 없이 데모 모드로 둘러보기**를 누릅니다.

APK 만들기: **Build → Generate App Bundles or APKs → Generate APKs** → `app/build/outputs/apk/debug/app-debug.apk`

## 보드(Orange Pi 5 Plus) 실행

보드 서버 코드는 팀 저장소 `develop` 브랜치에 있습니다. 서버 3개가 부팅 시 자동으로 **LLM → 음성 → P2** 순서로 켜지도록 `systemd`에 등록해 사용합니다.

| 서비스 | 포트 | 실행 내용 |
|---|---|---|
| `bajahoe-llm` | 8080 | `rkllm-board/rkllm/server/fastapi_server.py` + 양자화 모델(`.rkllm`, `--max-context 1024`) |
| `bajahoe-voice` | 8081 | `start_voice.py` (팀 음성 서버 + 44.1kHz 스테레오 재생) + `voice_test.yaml` |
| `bajahoe-p2` | 8000 | `python -m service.api_server.main` |

자주 쓰는 명령:

```bash
systemctl is-active bajahoe-llm bajahoe-voice bajahoe-p2        # 상태 확인
sudo systemctl restart bajahoe-llm bajahoe-voice bajahoe-p2     # 코드·설정 수정 후 다시 켜기
journalctl -u bajahoe-voice -n 30 --no-pager                   # 로그 확인
curl -s 127.0.0.1:8000/api/v1/health                           # camera·pose·llm·stt·tts 상태
sudo poweroff                                                  # 끄기 (파란 LED가 꺼진 뒤 전원 분리)
```

### 보드 설정 메모

| 항목 | 설정 |
|---|---|
| 기기 토큰 | 음성 서버, P2 서버, 앱이 모두 같은 값이어야 함 |
| 카메라 | `desk_pacemaker_p1_v1/config/posture.yaml`의 `camera_index`, `camera_width`·`camera_height`·`camera_fps_limit`(필수) |
| 스피커 | USB 오디오(`output_device: "USB Audio Device"`), 44.1kHz로 변환해 재생 |
| 마이크 | `input_device`. 본체 헤드셋 잭은 `test_record.sh headset` 실행 후 `sudo alsactl store`로 설정 저장 |
| 에코 방지 | 스피커가 말한 뒤 `post_play_mute_ms`(500ms) 동안 마이크 입력 무시 |
| 인식 로그 | `voice_test.yaml`에 `diagnostics: {enabled: true, log_stt_text: true}` (테스트용) |

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 앱이 연결되지 않음 | 휴대폰과 보드가 같은 Wi-Fi인지, IP가 바뀌지 않았는지(공유기에서 IP 고정 권장), 토큰이 같은지 |
| 자세설정 화면에 영상이 없음 | `health`의 `camera`, `/dev/v4l/by-id/`의 웹캠 번호와 `camera_index` |
| P2가 `activating`만 반복 | `journalctl -u bajahoe-p2` — `posture.yaml` 필수 키 누락이나 `git pull` 충돌 표시(`<<<<<<<`) |
| 음성 서버가 `activating`만 반복 | `journalctl -u bajahoe-voice` — `start_voice.py` 경로, `PYTHONPATH`, `make_player` 함수 모양 |
| 기기 소리가 안 나거나 지직거림 | `speaker-test -D plughw:Device,0 -t wav -c 2 -l 1`로 스피커 경로부터 확인, 볼륨 60~80% |
| 음성 명령에 403 | 음성 서버·P2·앱 토큰 불일치 |
| 응답이 느림 | `journalctl -u bajahoe-voice \| grep voice_timing`으로 단계별 시간 확인, `fix_freq_rk3588.sh`로 NPU 속도 고정 |

## 폴더 구조

```
app/src/main/java/com/example/bajahoe/
├─ MainActivity.kt      화면 전환, 글씨 크기 적용
├─ AppViewModel.kt      앱 상태, 공부 타이머, 기록 누적, 기기 상태 연동
├─ Protocol.kt          기기 메시지 형식, 오류 안내 문구
├─ DeviceClient.kt      기기 연결 공통부, 주소 확인(P2/구버전 자동 구분), 데모 기기
├─ P2DeviceClient.kt    팀 서버(P2 REST API) 연결: 상태 조회, 기준 자세, 미리보기, 측정 제어
├─ Discovery.kt         mDNS 기기 검색 (_bajahoe._tcp)
├─ MjpegPreview.kt      카메라 미리보기 (P2: JPEG 반복 요청)
├─ Storage.kt           날짜별 기록, 설정, 연결 기기·토큰 저장
├─ Design.kt            색상, 아이콘, 공통 컴포넌트
├─ AppLog.kt            Logcat 로그 (tag: Bajahoe)
└─ *Screen.kt           각 화면
mock_server/            PC용 모의 기기 서버 (구버전 WebSocket 규격)
PROTOCOL.md             구버전 WebSocket 통신 규격
```

## 앱 ↔ P2 서버 API

| 앱 동작 | 서버 API |
|---|---|
| 연결 확인 | `GET /api/v1/health`, `GET /api/v1/status` |
| 자세 상태 (1초마다) | `GET /api/v1/status` → `posture.state` (normal / attention / unavailable), `system_state` |
| 기준 자세 측정 | `POST /calibration/start` → `GET /calibration/preview` → `POST /calibration/confirm` |
| 카메라 미리보기 | `PUT /settings`로 미리보기 켜기 → `GET /api/v1/preview/frame` |
| 공부 시작·일시정지·종료 | `POST /monitoring/start`, `/monitoring/pause`, `/monitoring/stop` |
| 볼륨·음소거 | `PUT /settings` (`tts_volume`, `voice_feedback_enabled`) |
| 테스트 음성 | `POST /test-sound` |

모든 요청은 `Authorization: Bearer <기기 토큰>` 헤더를 사용합니다(`/health` 제외).

자세 판정은 머리 상대 위치(거북목) 기준의 추정이며, 의학적 진단이 아닙니다.
 
