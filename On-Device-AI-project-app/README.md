# 바자회 — 공부 자세 모니터링 앱

공부하는 동안 카메라로 자세를 확인하고, 자세가 흐트러지면 알려주는 서비스의 **안드로이드 앱**입니다.

자세 판정은 책상 위 **Orange Pi 5 Plus**와 반측면 카메라가 기기 안에서 모두 처리합니다(온디바이스).
카메라는 사용자 정면에서 한쪽으로 30~45° 돌아간 위치에 두어, 목과 등이 앞으로 굽는 정도를 잘 잡도록 했습니다.
앱은 기기와 같은 Wi-Fi로 연결해 판정 결과를 받아 보여주고, 경고와 공부 기록을 관리합니다.
카메라 영상은 자세설정 화면의 미리보기에만 쓰이고, 학습 중에는 휴대폰으로 보내지 않습니다.

```
[반측면 카메라] → [Orange Pi 5 Plus]               → [안드로이드 앱]
                 자세 추정 · 기준 자세 비교           화면 표시 · 진동 경고
                 good / bad / no_person 판정         공부 기록 · 캘린더
                          └──── 같은 Wi-Fi (WebSocket) ────┘
```

## 주요 기능

| 화면 | 내용 |
|---|---|
| 기기 연결 | 같은 Wi-Fi의 기기 자동 검색(mDNS), IP 직접 입력, 기기 없이 둘러보는 데모 모드 |
| 시작 전 자세설정 | 앱을 켤 때마다 필수. 얼굴·어깨·자세 고정이 인식돼야 완료 가능 |
| 홈 | 자세 재설정, 공부 시작, 오늘의 기록 |
| 학습 모드 | 오늘 누적 집중 시간 타이머. 나쁜 자세가 5초 이상 이어지면 경고 배너와 진동. 자리 비움 시 타이머 정지 |
| 결과 | 이번 공부·오늘 누적 시간, 자세 유지율, 경고 횟수, 가장 많이 흐트러진 자세와 팁 |
| 공부 캘린더 | 실제 달력 기준 월별 기록. 날짜별 공부 시간과 세션 목록 |
| 설정 | 기기 스피커 볼륨·음소거·테스트음, 앱 글씨 크기 |
| 프로필 | 닉네임, 연결된 기기 해제 |

같은 날 공부를 여러 번 껐다 켜도 그날 시간은 이어서 쌓이고, 자정을 넘기면 날짜별로 나눠 저장됩니다.
모든 기록은 휴대폰 안에만 저장됩니다.

## 개발 환경

- Android Studio, Kotlin, Jetpack Compose (Material 3)
- minSdk 26 (Android 8.0) / targetSdk 37
- 통신: OkHttp (WebSocket, MJPEG 미리보기)

## 실행 방법

1. Android Studio에서 이 폴더를 엽니다.
2. Gradle 동기화가 끝나면 휴대폰을 USB로 연결하고 **Run**을 누릅니다.
3. 기기가 없으면 첫 화면에서 **기기 없이 데모 모드로 둘러보기**를 누릅니다.

## 팀 서버(P2 API)에 연결하기

팀원이 만든 `p2_board_api` 서버(REST, 포트 8000)에 그대로 연결됩니다. 앱이 주소를 확인할 때 팀 서버인지 자동으로 구분합니다.

1. 보드(또는 PC)에서 토큰을 정하고 서버를 켭니다.
   ```bash
   cd p2_board_api
   BAJAHOE_DEVICE_TOKEN=원하는토큰값 python -m service.api_server.main
   ```
2. 앱 연결 화면에서 **IP 주소**, **포트 `8000`**, **기기 토큰**(위에서 정한 값)을 입력하고 연결합니다. 주변 기기 목록에 `bajahoe`가 보이면 토큰만 넣고 눌러도 됩니다.
3. 자세설정 화면에서 5초 동안 바른 자세를 유지하면 **설정 완료** 버튼이 켜집니다.

앱과 서버의 대응 관계

| 앱 동작 | 서버 API |
|---|---|
| 연결 확인 | `GET /api/v1/health`, `GET /api/v1/status` |
| 자세 상태(1초마다) | `GET /api/v1/status` → `posture.state` (normal/attention/unavailable) |
| 기준 자세 측정 | `POST /calibration/start` → `GET /calibration/preview` → `POST /calibration/confirm` |
| 카메라 미리보기 | `GET /api/v1/preview/frame` (자세설정 중에만 debug_mode·preview_stream_enabled 를 잠시 켬) |
| 공부 시작·일시정지·종료 | `POST /monitoring/start`, `/monitoring/pause`, `/monitoring/stop` |
| 볼륨·음소거 | `PUT /settings` (`tts_volume`, `voice_feedback_enabled`) |
| 테스트 음성 | `POST /test-sound` |

- 팀 서버는 자세 원인을 거북목(머리 위치) 하나로만 판정하므로 앱에도 거북목으로 표시됩니다.
- 서버가 이미 나쁜 자세 유지 시간을 걸러서 보내므로 앱은 1초 만에 경고합니다.
- 토큰이 틀리면 연결 화면으로 돌아가 다시 입력하라고 안내합니다.

## 모의 서버로 테스트하기

보드 없이 PC에서 오렌지파이 역할을 대신하는 서버입니다.

```bash
cd mock_server
pip install -r requirements.txt
python mock_server.py            # 정해진 시나리오대로 자세 상태가 바뀜
python mock_server.py --manual   # 키보드로 상태 바꾸기 (g/f/d/s/c/n/a/x/q)
```

- 휴대폰과 PC가 같은 Wi-Fi에 있으면 앱의 주변 기기 목록에 **Bajahoe-Mock**이 나타납니다.
- 목록에 없으면 PC의 IP와 포트 `8080`을 직접 입력합니다. 에뮬레이터에서는 IP에 `10.0.2.2`를 입력합니다.

## 기기 통신 규격

오렌지파이 서버가 지켜야 할 메시지 형식은 [PROTOCOL.md](PROTOCOL.md)에 정리되어 있습니다.

- HTTP `GET /api/info`, MJPEG `GET /stream.mjpg`
- WebSocket `/ws`: `mode`, `calibrate`, `detect`, `status`, `config`, `test_sound` 등
- 반측면 카메라 기준 판정 항목: 거북목, 고개 숙임, 등 굽음, 화면과 너무 가까움

## 폴더 구조

```
app/src/main/java/com/example/bajahoe/
├─ MainActivity.kt      화면 전환, 글씨 크기 적용
├─ AppViewModel.kt      앱 상태, 학습 타이머, 기록 누적
├─ Protocol.kt          메시지 형식
├─ DeviceClient.kt      WebSocket 연결, 데모 기기
├─ Discovery.kt         mDNS 기기 검색
├─ MjpegPreview.kt      카메라 미리보기
├─ Storage.kt           날짜별 기록, 설정 저장
├─ Design.kt            색상, 아이콘, 공통 컴포넌트
├─ AppLog.kt            Logcat 로그 (tag:Bajahoe 이벤트, tag:BjMsg 송수신 JSON)
└─ *Screen.kt           각 화면
mock_server/            PC용 모의 기기 서버
PROTOCOL.md             기기 ↔ 앱 통신 규격
```
