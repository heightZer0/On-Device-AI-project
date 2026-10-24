# 바자회 기기 ↔ 앱 통신 규격 v1

오렌지파이(이하 기기)와 안드로이드 앱(이하 앱)이 주고받는 메시지 규격이다.
기기는 자세 판정까지 모두 스스로 처리하고, 앱에는 **판정 결과만** 보낸다.
카메라 영상은 자세설정 화면에서 미리보기가 필요할 때만 MJPEG로 제공한다.

## 1. 연결 개요

| 항목 | 값 |
|---|---|
| 네트워크 | 기기와 휴대폰이 같은 Wi-Fi에 접속 |
| 기본 포트 | `8080` (HTTP와 WebSocket을 같은 포트로 제공) |
| 기기 찾기 | mDNS / DNS-SD 서비스 타입 `_bajahoe._tcp` |
| 메시지 형식 | UTF-8 JSON, WebSocket 텍스트 프레임 |

mDNS 광고 예시 (Python `zeroconf`):

```
서비스 이름: Bajahoe-1A2B._bajahoe._tcp.local.
포트: 8080
TXT: name=바자회 기기, ver=1
```

mDNS가 안 되는 환경을 위해 앱에서 IP를 직접 입력할 수도 있다.

## 2. HTTP

### `GET /api/info`

앱이 연결 전에 기기가 맞는지 확인할 때 호출한다. 3초 안에 응답해야 한다.

```json
{
  "device_id": "opi5p-1a2b",
  "name": "바자회 기기",
  "version": "1.0.0",
  "camera": "front"
}
```

### `GET /stream.mjpg`

`multipart/x-mixed-replace; boundary=frame` 형식의 MJPEG 스트림.
앱은 **자세설정 화면에서만** 이 주소를 연다. 권장: 640×480, 10fps, JPEG 품질 70.
학습 모드 중에는 앱이 이 주소를 열지 않는다.

## 3. WebSocket `ws://<기기 IP>:8080/ws`

동시에 하나의 앱만 연결된다고 가정한다. 새 연결이 오면 이전 연결은 닫아도 된다.
앱은 연결이 끊기면 2초 간격으로 다시 연결한다.

### 3.1 앱 → 기기

| type | 필드 | 설명 |
|---|---|---|
| `hello` | `app_version`, `client` | 연결 직후 1회 전송 |
| `mode` | `mode`: `idle` \| `calibrate` \| `monitor` | 기기 동작 모드 변경. 재연결 시 마지막 모드를 다시 보냄 |
| `calibrate` | 없음 | 지금 자세를 기준 자세로 저장 |
| `session` | `action`: `start` \| `stop` | 공부 세션 시작과 종료 알림 (기기 쪽 기록용, 선택) |
| `config` | `volume`, `muted`, `warn_delay_sec` | 앱 설정 전달. 연결될 때마다, 그리고 설정을 바꿀 때마다 보냄 |
| `test_sound` | 없음 | 스피커로 확인용 안내음을 한 번 재생 |

```json
{"type": "mode", "mode": "calibrate"}
{"type": "calibrate"}
{"type": "session", "action": "start"}
```

#### `config` 상세

```json
{"type": "config", "volume": 70, "muted": false, "warn_delay_sec": 5}
```

- `volume`: 0~100. 기기 스피커의 음성 안내 볼륨
- `muted`: `true`면 음성 안내를 내지 않음 (볼륨 값은 유지)
- `warn_delay_sec`: 앱이 경고를 띄우는 기준 시간. 기기가 음성 경고를 낼 때 같은 기준을 쓰면 앱 화면과 소리가 맞음
- 볼륨의 기준은 **앱**이다. 기기는 받은 값을 그대로 적용하고, 재부팅 후에도 쓸 수 있게 파일에 저장해 둔다
- 적용 예시: `amixer -c <카드번호> sset <컨트롤이름> 70%` (컨트롤 이름은 `amixer scontrols`로 확인), 또는 재생 코드에서 볼륨 배율 적용
- 슬라이더를 움직이는 동안 0.15초 간격으로 여러 번 올 수 있다

### 3.2 기기 → 앱

#### `detect` — `calibrate` 모드에서 초당 2회 이상

자세설정 화면의 인식 표시와 완료 버튼 활성화에 쓴다.

```json
{"type": "detect", "face": true, "shoulders": true, "stable": false}
```

- `face`: 얼굴(코, 양 눈)이 인식됨
- `shoulders`: 양 어깨가 인식됨
- `stable`: 최근 1.5초 동안 관절 위치 변화가 작음

세 값이 모두 `true`일 때만 앱의 "설정 완료" 버튼이 켜진다.

#### `calibration` — `calibrate` 요청에 대한 응답

```json
{"type": "calibration", "ok": true}
{"type": "calibration", "ok": false, "reason": "shoulders_not_found"}
```

`reason`: `no_person` | `face_not_found` | `shoulders_not_found` | `unstable` | `no_camera`
앱은 5초 안에 응답이 없으면 실패로 처리한다.

#### `status` — `monitor` 모드에서 초당 2회 권장 (최소 1회)

```json
{
  "type": "status",
  "ts": 1791459728014,
  "state": "bad",
  "score": 62,
  "issues": ["head_down"],
  "metrics": {"shoulder_tilt_deg": 3.1, "head_drop": 0.18, "distance_ratio": 1.05}
}
```

| 필드 | 설명 |
|---|---|
| `state` | `good` 바른 자세 · `bad` 기준 이탈 · `no_person` 사람 없음 |
| `score` | 0~100 자세 점수 (선택, 표시용) |
| `issues` | `bad`일 때 원인 코드 목록 |
| `metrics` | 디버깅용 수치 (선택) |

`state`는 **그 순간의 판정**만 보낸다. "5초 이상 나쁜 자세면 경고" 같은 시간 조건은 앱이 처리한다.
앱은 마지막 `status`를 받은 지 3초가 지나면 연결 상태를 확인 중으로 표시한다.

#### `error`

```json
{"type": "error", "code": "camera_unavailable", "message": "카메라를 열 수 없음"}
```

## 4. 원인 코드 `issues` — 정면 카메라 기준

기준 자세 저장 시 아래 값을 함께 저장하고, 현재 값과 비교한다.
임계값은 시작값이며 실제 테스트로 조정한다.

| 코드 | 의미 | 판정 방법 (제안) |
|---|---|---|
| `head_down` | 고개 숙임, 거북목 | (어깨 중심 y − 코 y) ÷ 어깨 너비가 기준 대비 25% 이상 감소 |
| `too_close` | 화면에 너무 가까움 | 어깨 너비(또는 양 눈 거리)가 기준 대비 20% 이상 증가 |
| `shoulder_tilt` | 어깨 기울어짐 | 양 어깨를 잇는 선의 기울기가 기준 대비 8° 이상 차이 |
| `leaning` | 몸이 옆으로 기울어짐 | 어깨 중심 x가 기준 대비 어깨 너비의 25% 이상 이동 |

여러 프레임에 걸쳐 평균(예: 최근 5프레임 이동 평균)을 낸 뒤 판정하면 깜빡임이 줄어든다.

## 5. 시나리오 예시

```
앱 실행 → mDNS로 기기 발견 → GET /api/info → WS 연결 → hello
자세설정 화면: mode=calibrate, /stream.mjpg 열기, detect 수신
설정 완료:     calibrate → calibration(ok) → mode=idle
공부 시작:     mode=monitor, session start → status 수신
공부 종료:     session stop → mode=idle
```

## 6. 테스트용 모의 서버

`mock_server/mock_server.py`가 이 규격대로 동작한다. 보드 없이 PC에서 앱을 테스트할 때 쓴다.
