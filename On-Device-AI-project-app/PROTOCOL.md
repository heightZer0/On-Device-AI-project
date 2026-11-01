# Android ↔ P2 REST 연결

## 연결 정보

- Base URL: `http://<board-ip>:8000/api/v1`
- Android는 `Authorization: Bearer <device_token>`을 보호된 P2 요청마다 보냅니다. `/health` 조회만 토큰이 필요하지 않습니다.
- mDNS 서비스 타입은 `_bajahoe._tcp`이며 P2가 광고하는 포트(기본 `8000`)를 사용합니다.
- 요청/응답은 UTF-8 JSON입니다. 앱은 1초 간격으로 `/status`를 조회하고 네트워크 오류 후 재연결 간격을 늘립니다.
- 앱에는 MJPEG/WebSocket 요청이 없습니다. 영상과 프레임 좌표는 보드에서 유지됩니다.

## 사용하는 엔드포인트

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | `/health` | P2 서버 확인(인증 제외) |
| GET | `/status` | 자세·모니터링 상태 폴링 |
| POST | `/calibration/start` | `{ "duration_sec": 5, "request_id": "…" }` |
| GET | `/calibration/preview?calibration_id=…` | 수집 상태·진행도 조회 |
| POST | `/calibration/confirm` | `{ "calibration_id": "…", "confirm": true, "request_id": "…" }` |
| POST | `/monitoring/start` | 공부 세션 시작 또는 일시정지 세션 재개 |
| POST | `/monitoring/pause` | 세션 유지하며 일시정지 |
| POST | `/monitoring/stop` | 세션 종료 |
| PUT | `/settings` | `{ "tts_volume": 0.7, "voice_feedback_enabled": true }` |
| POST | `/test-sound` | 기기 음성 테스트 |

모니터링 제어 요청에는 `{ "source": "app", "request_id": "<UUID>" }`를 보냅니다. 동일 request ID 재전송은 중복 실행을 막습니다.

## 상태 표시

`GET /status.posture.state` 값은 다음처럼 앱에 연결됩니다.

| P2 값 | 앱 표시 데이터 |
|---|---|
| `normal` | 정상 |
| `attention` | 주의, 앱 진동 |
| `unavailable` | 자세 측정 불가 |

P1/P2가 자세 주의 지속시간과 경고 음성을 처리합니다. 앱은 `attention` 상태가 도착했을 때 한 번 진동하며, 별도의 자세 분류·상세 원인 판정은 하지 않습니다.

캘리브레이션은 시작 응답의 `calibration_id`를 사용해 `state`가 `READY` 또는 `FAILED`가 될 때까지 preview를 조회합니다. `READY` 이후 앱의 확인 버튼이 `/calibration/confirm`을 보냅니다. 실패하면 현재 캘리브레이션을 취소하고 다시 시작합니다.
