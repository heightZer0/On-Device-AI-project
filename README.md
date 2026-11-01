# 바자회 자세 코칭 — 백엔드 통합 작업

P1 자세 분석, P2 REST 서버·세션 저장, P3 음성 파이프라인, P4 명령 검증을 연결하는 개발 작업본입니다. 

## 프로젝트 구성

| 경로 | 역할 |
|---|---|
| `desk_pacemaker_p1_v1/` | 웹캠 프레임에서 귀·어깨 상대 위치를 분석하고 캘리브레이션 기준을 계산 |
| `p2_board_api/` | FastAPI, 인증, 캘리브레이션·모니터링·세션 API, JSON 저장, P4 명령 처리 |
| `P3_TTS/` | 별도 음성 서비스 복사본 |
| `p2_board_api/service/voice_agent/` | P2와 연결되는 VAD/STT/TTS 서비스 |
| `On-Device-AI-project-app/` | Android 앱.

## 개발 환경 준비

Windows PowerShell과 Python 3.11을 기준으로 합니다. 프로젝트를 받은 뒤 P2 폴더에서 가상환경을 만들고 의존성을 설치합니다.

```powershell
cd C:\path\to\mobilesystem\p2_board_api
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

P2 `requirements.txt`는 P1 코드가 쓰는 MediaPipe `mp.solutions.pose` API 버전을 고정합니다. 현재 P1 카메라 분석에 필요한 OpenCV는 이 MediaPipe 설치가 제공하는 `opencv-contrib-python`을 사용합니다. 별도 설치 파일의 `opencv-python`을 같은 가상환경에 추가로 설치하면 OpenCV/NumPy 의존성 경고가 발생할 수 있습니다.

실제 환경에서 STT/TTS도 실행하려면 별도 터미널에서 다음 의존성을 설치하고 P3 서비스를 시작합니다. 음성 모델 파일은 팀에서 받은 뒤 `service/voice_agent/config.yaml`의 경로에 배치해야 합니다.

```powershell
cd C:\path\to\mobilesystem\p2_board_api
.\.venv\Scripts\Activate.ps1
python -m pip install -r service/voice_agent/requirements.txt
$env:BAJAHOE_DEVICE_TOKEN = "로컬에서_정한_토큰"
python -m service.voice_agent.main
```

LLM 명령 실행에는 `config/api.yaml`의 `llm_url`과 `llm_model`에 맞는 OpenAI 호환 서버가 필요합니다. STT/TTS/LLM 서비스가 없으면 `/health`에 `degraded`와 해당 모듈 오류가 표시될 수 있습니다. 이는 웹캠 자세 분석과 별개입니다.

## P2 서버 시작

서버는 기본 `0.0.0.0:8000`에서 실행하며 보호된 요청에는 Bearer 토큰을 요구합니다. 서버는 한 번에 하나만 실행하세요. `WinError 10048` 또는 “address already in use”가 나오면 기존 P2 서버를 실행한 터미널에서 `Ctrl+C`를 누른 뒤 다시 시작합니다.

```powershell
cd C:\path\to\mobilesystem\p2_board_api
.\.venv\Scripts\Activate.ps1
$env:BAJAHOE_DEVICE_TOKEN = "로컬에서_정한_토큰"
python -m service.api_server.main
```

토큰은 PowerShell 세션 환경변수로 설정하고 저장소에 커밋하지 마세요. `GET /api/v1/health`는 인증 없이, 그 외 API는 `Authorization: Bearer <token>` 헤더로 호출합니다.

## 웹캠 미리보기와 캘리브레이션

서버를 실행한 PC의 브라우저에서 [http://127.0.0.1:8000/preview](http://127.0.0.1:8000/preview)를 엽니다.

1. P2 토큰을 입력하고 **미리보기 시작**을 누릅니다.
2. 카메라를 눈높이에 두고 머리와 어깨가 프레임에 들어오도록 위치를 맞춥니다.
3. **기준 자세 측정**을 누르고 편안한 정면 자세를 유지합니다.
4. 상태가 `READY`가 되면 **기준 저장**을 누릅니다. 실패하면 사유와 유효 프레임 정보를 확인하고 위치·조명을 조정해 다시 시도합니다.
5. **자세 분석 시작**을 누른 뒤 기준보다 머리를 앞으로 이동한 자세를 유지합니다. 페이지에 `/status`의 자세 상태, ΔH, 랜드마크 신뢰도, 측정 사유, 세션 값을 표시하고 원문 JSON도 제공합니다.
6. 종료할 때 **분석 종료**와 **미리보기 종료**를 누릅니다. 미리보기 시작 시 켠 디버그/스트림 설정은 종료 시 원래 설정으로 복구됩니다.

P1은 사진 한 장을 저장하는 방식이 아니라 캘리브레이션 중 수집한 안정 프레임들로 기준값을 계산합니다. 현재 P1의 `T_hold_sec`는 5초, `T_forward`는 0.20이며 실험 전 임시 설정입니다. 판정은 머리 상대 위치 기반이므로 의학적 거북목 진단을 의미하지 않습니다.

미리보기 프레임은 메모리에서 JPEG로 변환되어 인증된 `GET /api/v1/preview/frame` 응답으로 전달됩니다. 서버는 영상을 파일로 저장하지 않습니다. 미리보기 페이지(`/preview`)는 사용자가 기기 토큰을 입력하는 로컬 개발용 화면입니다.

## 주요 API

| 요청 | 용도 |
|---|---|
| `GET /api/v1/status` | P1 자세 상태와 모니터링/세션 상태 |
| `GET /api/v1/posture/current` | 현재 자세 판정 |
| `POST /api/v1/calibration/start` | 기준 자세 프레임 수집 시작 |
| `GET /api/v1/calibration/preview?calibration_id=...` | 진행률, READY/FAILED와 실패 사유 |
| `POST /api/v1/calibration/confirm` | 기준값 저장 또는 캘리브레이션 취소 |
| `POST /api/v1/monitoring/start` | 모니터링/세션 시작 |
| `POST /api/v1/monitoring/pause` | 모니터링 일시정지 |
| `POST /api/v1/monitoring/stop` | 종료 세션 요약 반환 |
| `GET /api/v1/session/current` | 현재 세션 누적값 |
| `GET /api/v1/session/history` | 종료된 세션 페이지 조회 |
| `GET /api/v1/session/calendar?month=YYYY-MM&timezone=Asia/Seoul` | 월별 날짜·세션 합계 |
| `GET /api/v1/preview/frame` | 디버그 미리보기 JPEG 프레임 |
| `POST /api/v1/command` | P4 명령 검증 및 허용 동작 실행 |

세션 요약에는 `focus_sec`, `good_sec`, `attention_sec`, `unavailable_sec`, `warning_count`, `posture_rate`, `top_issue` 등의 값이 포함됩니다. 측정 불가 시간은 사람 부재, 가림, 화면 밖 상태를 구별하지 않습니다.

브라우저 화면 대신 PowerShell에서 기본 웹캠 API 절차만 확인하려면 `p2_board_api/tools/webcam_api_check.ps1`을 사용합니다.


## 로컬 데이터와 Git

P2 설정·캘리브레이션 기준·세션 데이터는 `p2_board_api/data/store/`에 저장됩니다. 이 데이터와 가상환경, 음성 모델, 로그, 실험 CSV는 루트 `.gitignore`에서 제외합니다. 팀 공유에는 코드·설정 템플릿·문서를 사용하고 개인 토큰, 캘리브레이션 결과, 사용자 세션 기록은 커밋하지 마세요.

## 확인 현황과 남은 작업

- 백엔드 Python 문법과 미리보기 페이지 JavaScript 문법 확인 완료.
- 실제 웹캠 캘리브레이션은 일부 프레임이 감지됐지만, 낮은 visibility/유효 프레임 비율로 `too_few_stable_frames`가 발생한 실행이 있었습니다. 카메라 위치와 조명을 맞춘 뒤 브라우저 페이지에서 다시 확인해야 합니다.
- 기준을 저장하고 거북목 형태로 자세를 바꾼 뒤 `normal`→`attention` 상태 변화가 발생하는 실제 측정은 아직 팀에서 확인해야 합니다.
- 보드/RKLLM 네이티브 런타임과 모바일 앱 연동은 이 작업환경에서 검증하지 않았습니다.
