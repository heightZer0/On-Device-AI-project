# P2 보드 API · 세션 저장 · 허브 · P4 명령 처리기 (P0 v10.3)

## 실행
```bash
pip install -r requirements.txt
python -m pytest tests -q                                   # P1/P3/P4 없이 mock 으로 44개 테스트
BAJAHOE_DEVICE_TOKEN=<토큰> python -m service.api_server.main   # 실제 P1(posture.engine)·OpenAI 호환 LLM 서버 필요
```
인증이 켜져 있는데 토큰이 없으면 서버가 시작되지 않는다(fail closed). 인증 끄기는 `config/api.yaml`의 `auth.enabled=false`이며 **실사용자 배포 전 반드시 활성화**.

## 구조
- `command/` P4 엄격 파서·스키마 검증·상태 전제 확인·실행기
- `service/api_server/` FastAPI 앱·오류 형식·인증·요청 제한 · `service/session_service/` 로컬 JSON 파일 저장·시간 누적
- `service/hub/` 상태 머신·이벤트→음성·설정 전파·서비스 핸들·`/command` 처리 · `config/` api.yaml, phrases.yaml
- `tests/api/fakes.py` P1/P3/P4 mock

## 앱 연동용 API 계약

- 인증된 `GET /api/v1/status`는 자세 상태와 활성 세션 요약을 돌려준다.
- `POST /api/v1/monitoring/stop` 응답의 `session_summary`에는 종료 세션 요약이 포함된다.
- `GET /api/v1/session/calendar?month=YYYY-MM&timezone=Asia/Seoul`는 `totals`, 날짜별 `days`, 세션별 `sessions`를 돌려준다.
- 화면용 세션 필드는 `focus_sec`(정상+주의 시간), `good_sec`, `attention_sec`, `unavailable_sec`, `posture_rate`, `top_issue`다. `unavailable_sec`는 부재/가림/화면 밖을 서로 구분하지 못한 측정 불가 시간이다.
- 위는 P2가 제공하는 계약이다. 모바일 앱의 연동은 앱 담당자가 별도로 반영해야 한다.

## 웹캠 → API 확인 (앱 없이)

서버를 켠 뒤 브라우저에서 `http://127.0.0.1:8000/preview`를 연다. 기기 토큰을 입력하고 **미리보기 시작**을 누르면 카메라 영상이 표시된다. 같은 페이지의 **기준 자세 측정** 버튼은 캘리브레이션을 시작하고 진행률과 결과를 보여준다. READY 상태에서 기준값을 저장한 뒤 **자세 분석 시작**을 누르면 `/status`의 자세 상태, 머리 상대 위치 변화량(ΔH), 신뢰도, 사유, 세션 누적값과 원문 JSON이 갱신된다. 프레임은 메모리에서 JPEG로 변환해 브라우저에 보내며 저장하지 않는다. 종료할 때 **분석 종료**, **미리보기 종료**를 눌러 원래 설정을 복구한다.

브라우저 없이 API만 확인하려면 `tools/webcam_api_check.ps1`을 사용할 수 있다. 스크립트가 P2 캘리브레이션 API와 `/status`를 호출하고 종료 세션 요약을 보여준다.

## ⚠ 가정 목록 (팀 확인 필요)
1. `/session/history`는 `{items,total,limit,next_cursor}`이며 세션 객체에는 기본 누적 필드와 화면용 파생 필드가 포함된다. 캘린더 응답은 `month, timezone, totals, days, sessions`다.
2. 인증 헤더는 `Authorization: Bearer <device_token>`로 가정(D-04). 페어링 API는 만들지 않았다(`pairing_enabled=false` 기본이라 생략).
3. `/command` 검증 실패는 V6 오류 코드와 HTTP status를 사용한다. 재질문은 성공 응답 `result.awaiting`으로 `body_part|intent|time`을 반환한다.
4. P4 인터페이스: `command.process_p2(raw, utterance, services)`. 명령은 V6 16개 허용 목록과 전체 일치해야 하며 알림 명령은 `minutes="N"`만 받는다. 실제 시간은 STT 원문에서 백엔드가 파싱한다.
5. 재질문 후속 처리: part 재질문은 모호/무관 발화에 1회 재질문 후 해제하고 일반(LLM) 흐름으로 넘긴다. `part_words.yaml` 단어 목록은 초안.
6. 재질문 상태는 프로세스 메모리에 세션별 저장하며 30초 TTL, 한 번 재질문 후 실패하면 `CLARIFICATION_TIMEOUT`으로 끝낸다. 오디오 데이터는 저장하지 않는다.
7. AI 요청 감사 로그는 `ai_log_enabled: true`일 때만 `ai_log_path` JSONL에 기록한다. 기본값은 꺼짐이며 이 모드는 STT 원문과 LLM 출력을 기록한다.
7. 엔진 `confirm_calibration()`이 `{"saved": false}`를 반환하면 재측정(상태 CALIBRATING 유지)으로 해석. 엔진의 `cancel_calibration`, `set_debug_label`은 선택 기능.
8. `posture_sensitivity→T_forward` 매핑은 실험으로 정해야 하므로 현재 판정에는 적용하지 않는다.
9. 캐시되는 `request_id` 응답은 **성공 응답만**. 휴식 알림 교체 정책은 `break_alarm_replace`(기본 true), 알림 문구·`command_failed`·`break_cancelled` 문구는 PLACEHOLDER(기획 확정 필요).
10. 비정상 종료 세션은 폐기하지 않고 마지막 체크포인트 시각으로 마감한다(⚑정책 TBD).
11. **미구현/하드웨어 필요**: RKLLM native binding은 보드와 일치하는 헤더·런타임을 받은 뒤 작성해야 한다. OpenAI 호환 endpoint 어댑터는 설정 가능. `/pairing/*`는 미구현. 로컬 미리보기는 디버그 설정에서만 사용할 수 있다.

P4 명령 계약·모델 교체 요건·보드 없는 확인 절차는 [COMMAND_SCHEMA.md](COMMAND_SCHEMA.md)를 참고한다.
