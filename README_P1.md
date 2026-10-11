# P1. 자세 분석 · 캘리브레이션 (측면 귀·어깨 H 판정)

명세서 v10의 P1 파트 구현이다. 학습된 분류 모델 없이 **MediaPipe Pose 좌표 + 개인 기준 캘리브레이션 + 임계값 규칙**으로 판정한다.
결과는 "추정 지표"이며 의학적 진단이 아니다.

## 현재 상태 (정직하게)

| 항목 | 상태 |
| --- | --- |
| 판정·캘리브레이션·이벤트 로직 | 합성 데이터 단위 테스트 43개 통과 (카메라 불필요) |
| 실제 웹캠(PC) | 캘리브레이션 → 주의 → 복귀 이벤트까지 1회 동작 확인. **정확도는 미측정** |
| Orange Pi 5 Plus (aarch64) | **미확인** (mediapipe 설치 가능 여부부터 확인 필요) |
| 임계값 전부 | **임시 placeholder** — 0단계 실험(P7 E1~E6)으로 확정 전에는 확정값으로 쓰거나 발표하지 말 것 |
| TTS/API 연결 | 이 파트에는 없음 (P2가 이벤트를 받아 연결) |

## 설치 · 실행 · 테스트

```bash
pip install -r requirements-posture.txt
python -m pytest tests/posture -q                 # 카메라 없이 가능
python run_posture_demo.py --camera 1             # 카메라 번호: 노트북 내장 0, 외부 웹캠 보통 1
python run_posture_demo.py --camera 1 --log exp_p1.csv --subject p1 --note face_right_fixed   # (개발용) H·ΔH·S 로그
python tools/h_logger.py --list-cameras           # 카메라 번호 확인 / 좌표 로거(0단계 실험)
```

데모 키: `c` 기준 자세 수집 시작 · `y` 미리보기 확인 후 저장 · `p` 일시정지/재개 · `d` 디버그(S) 표시 · `ESC` 종료.
기준 자세는 **스스로 편안하다고 느끼는 자세**이며 자세의 정답이 아니다. 카메라는 **정확한 측면**에서 머리~명치가 보이게 둔다
(정면에 가까우면 `H_base`가 비정상적으로 크게 나올 수 있다).

## 폴더 구조

```text
config/posture.yaml              설정 키 (한 곳에서만 정의, 전부 placeholder)
posture/
  engine.py                      PostureEngine — P2 가 호출하는 단일 진입점
  analyzer/analyzer.py           H/ΔH 계산, 측정 불가 판정, 상태 머신, 이벤트 (카메라 의존 없음)
  calibration/calibration.py     기준값 계산(중앙값)·저장·로드
  pose_estimation/               웹캠+MediaPipe → RawFrame (mediapipe_source.py), 프레임 타입 (frame.py)
  rules/config.py                설정 로더
tools/h_logger.py                0단계 실험용 귀·어깨 좌표 로거 (P7)
tests/posture/                   단위 테스트
run_posture_demo.py              동작 확인 데모
```

## P2 연동 방법

```python
from posture.engine import PostureEngine

engine = PostureEngine()                       # config/posture.yaml, data/calibration.json 자동 로드
engine.on_event(lambda ev: print(ev))          # {"type","ts","delta"} — 처리 스레드에서 호출되니 콜백은 짧게
engine.run_in_background()                     # 처리 스레드 시작

engine.start(); engine.pause(); engine.resume(); engine.stop()   # 멱등. 최종 status("stopped|running|paused") 반환
engine.get_state()                             # PostureState (C6)
engine.get_calibration()                       # 없으면 None → P2 가 monitoring/start 에서 NOT_CALIBRATED 처리
engine.get_camera_status()                     # ready | error | unavailable  (P2 /status 의 camera)
engine.set_debug(True)                         # True 일 때만 get_state() 에 debug.shoulder_screen_shift 포함
engine.close()
```

캘리브레이션 (P2 `/calibration/start` → `/preview` → `/confirm` 에 대응):

| 호출 | 반환 |
| --- | --- |
| `begin_calibration()` | `{"phase":"collecting","camera":..., "detected":{"left":{"ear","shoulder"},"right":{...},"any":bool}}` |
| `preview_calibration()` | `{"phase":"collecting","progress":0~1}` / `{"phase":"ready","summary":{H_base,L_ref_fixed,side,d,spread_iqr,n_good,n_all,...}}` / `{"phase":"failed","error":"too_few_frames\|too_few_stable_frames\|too_much_variation\|..."}` |
| `confirm_calibration()` | `{"ok":true,"calibration":{...}}` 또는 `{"ok":false,"error":"not_ready\|save_failed"}` |

저장 후 `side`·`d`·`L_ref_fixed`·`H_base`는 다음 재캘리브레이션 전까지 바뀌지 않는다 (자동 갱신 없음).

### 이벤트

| type | 발생 조건 |
| --- | --- |
| `attention_started` | ΔH > T_forward 가 T_hold_sec 이상 지속되어 주의 진입 시 1회, 주의가 이어지면 alert_interval_sec 마다 재발생 |
| `recovered` | 주의에서 ΔH ≤ T_release 로 돌아올 때 1회 (측정 불가가 T_reset_sec 를 넘긴 뒤에는 내지 않음) |
| `unavailable_prolonged` | 측정 불가가 unavailable_prolonged_sec 이상 이어질 때 구간당 1회 |
| `recalibration_suggested` | 측정 불가(T_reset_sec 초과)가 recalib_window_sec 안에 recalib_suggest_count 번 반복될 때. **안내만**, 자동 재캘리브레이션 없음 |

측정 불가 중에는 `attention_started`가 나오지 않는다. `ΔH`가 음수(뒤로 이동)여도 주의가 되지 않는다(부호 있는 비교).
`state`는 `normal | attention | unavailable`만 노출한다 (내부 observing은 normal로 보임).

## 설정 키 (`config/posture.yaml`)

| 키 | 의미 | 상태 |
| --- | --- | --- |
| `T_vis`, `N_low_vis`, `frame_margin` | 신뢰도 기준 / 연속 프레임 / 화면 마진 | TBD(0단계) |
| `T_forward`, `T_hold_sec` | 전방 임계값 / 주의 지속 시간 | TBD(E6) |
| `T_reset_sec`, `K_recover`, `alert_interval_sec` | 타이머 초기화 / 재개 프레임 / 재알림 간격 | TBD(E6) |
| `calib_duration_sec` | 수집 시간 | 초기 제안 5~10초 |
| `T_release` | 주의 해제 임계값 (히스테리시스). null 이면 T_forward 와 같음 | **가정**, TBD |
| `smooth_window`, `max_dt_sec`, `calib_min_frames`, `calib_min_stable_ratio` | 노이즈 완화·안전장치 | **가정**, TBD |
| `calib_max_spread` | 캘리브레이션 변동 폭(IQR) 상한. null 이면 거부 없이 로그만 | TBD(E5) |
| `unavailable_prolonged_sec`, `recalib_suggest_count`, `recalib_window_sec` | 이벤트 기준 | **가정**, TBD |

## 저장되는 것 / 안 되는 것 (명세 C2-8)

- 저장: `data/calibration.json` — 숫자 6개(`H_base`, `x_shoulder_base`, `L_ref_fixed`, `side`, `d`, `created_at`). **개인 기준값이므로 팀원끼리 공유하지 않는다** (각자 캘리브레이션).
- 저장 안 함: 영상, 프레임별 좌표, 음성.
- 개발용 CSV(`--log`, `tools/h_logger.py`)는 실험용이다. **실험이 끝나면 삭제**한다. `--log` 는 H·ΔH·S·상태만, `h_logger.py` 는 픽셀 좌표를 기록한다. 둘 다 `.gitignore` 로 커밋을 막아 두었다.

## 이 구현에서 임시로 정한 가정 (CP0에서 팀 확인 필요)

1. 사람이 검출되지 않으면 사유를 `ear_not_detected`로 표시한다 (명세에 이 경우의 매핑 없음).
2. 측정 불가가 `T_reset_sec`를 넘기면 주의 구간이 끝난 것으로 보고 `recovered`를 내지 않는다.
3. `duration_sec`는 "현재 상태가 유지된 시간"이다.
4. 노이즈 완화는 `smooth_window` 프레임 이동 중앙값이다.
5. `d`는 코 x와 귀 x 비교로 판별한다 (명세도 0단계 검증 대상으로 둔 방법).
6. `side`는 캘리브레이션 중 귀·어깨 visibility 평균이 높은 쪽이다.
7. 주의 해제에 히스테리시스(`T_release`)를 둔다. 해제 조건은 명세상 TBD다.
8. 캘리브레이션 저장 위치는 임시로 JSON 파일이다 (P2 SQLite `calibration` 테이블과 합치는 방법은 미정).

## 아직 없는 것

- `occluded`(가림) 판정 — 판별 방법이 명세에 TBD
- "기준 대비 변화가 한 방향으로 장시간 지속"에 따른 재캘리브레이션 안내
- FPS·감지율·측정 불가 비율 요약 스크립트 (P1-12) — `tools/h_logger.py` CSV 는 있으나 요약 도구 없음
- 보드(aarch64) 실행 검증, 실험으로 정한 임계값
- S 지표 검증(E4) — S 는 로그 전용이며 판정·일반 화면에 쓰지 않는다

## 자주 나는 문제

- 카메라가 안 열림 / 노트북 캠이 열림 → `python tools/h_logger.py --list-cameras` 로 번호 확인 후 `--camera N`
- `module 'mediapipe' has no attribute 'solutions'` → mediapipe 버전 문제. `pip install "mediapipe<0.10.15"` 등으로 맞추거나 팀원이 쓰는 버전과 통일
- `누락된 설정 키: ['T_release']` → `config/posture.yaml` 이 이전 버전이다. 새 파일로 교체
- 주의/정상이 자꾸 오간다 → T_forward 근처에서 흔들리는 것. 임계값은 실험으로 정해야 한다
