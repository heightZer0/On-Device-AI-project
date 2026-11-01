# 바자회 Android 앱

팀원이 만든 Jetpack Compose 화면과 휴대폰 내 공부 기록을 유지하고, 기기 연결을 P2 REST API에 맞춘 앱입니다.

## 연결

- API 기본 주소: `http://<보드 IP>:8000/api/v1`
- 같은 Wi-Fi에서 mDNS `_bajahoe._tcp`로 검색하거나 IP와 포트를 직접 입력합니다.
- 연결 화면에서 보드의 `BAJAHOE_DEVICE_TOKEN` 값을 입력합니다. 앱은 IP·포트와 토큰으로 `/api/v1/status`를 확인합니다.
- 인증 토큰은 앱 전용 `bajahoe_auth` 저장소에 보관하고 Android 클라우드/기기 이전 백업에서 제외합니다.
- 캘리브레이션 중에도 자세 영상은 휴대폰으로 보내지 않습니다. 앱은 측정 진행/완료 상태만 표시합니다.

## 앱과 보드 동작

| 앱 화면 동작 | P2 REST |
|---|---|
| 연결 확인·상태 갱신 | `GET /api/v1/health`, `GET /api/v1/status` |
| 기준 자세 설정 | `POST /api/v1/calibration/start`, `GET /api/v1/calibration/preview`, `POST /api/v1/calibration/confirm` |
| 공부 시작·종료 | `POST /api/v1/monitoring/start`, `POST /api/v1/monitoring/stop` |
| 공부 일시정지·재개 | `POST /api/v1/monitoring/pause`, `POST /api/v1/monitoring/start` |
| 음성 볼륨·음소거 | `PUT /api/v1/settings` (`tts_volume`, `voice_feedback_enabled`) |
| 테스트 음성 | `POST /api/v1/test-sound` |

보드의 `normal`은 앱의 정상 상태, `attention`은 주의 상태, `unavailable`은 측정 불가로 표시합니다. 앱은 P1이 이미 적용한 주의 지속시간을 다시 기다리지 않고 `attention` 수신 시 진동합니다. P2의 LLM/P4 명령 실행은 이 앱 연결과 별도입니다.

## 실행

Android Studio에서 이 폴더를 열고 Gradle 동기화 후 기기나 에뮬레이터에서 앱을 실행합니다. **기기 없이 데모 모드로 둘러보기**를 선택하면 화면 시나리오를 볼 수 있습니다.

실제 보드 API에 연결하려면 먼저 보드에서 P2와 P3 서버를 실행하고, 앱의 포트는 P2의 API 포트 `8000`을 사용합니다. Android 에뮬레이터에서 개발 PC의 서버로 연결할 때는 IP `10.0.2.2`를 사용합니다.
