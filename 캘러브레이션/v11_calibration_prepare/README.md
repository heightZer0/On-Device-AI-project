# V11 캘리브레이션 준비 — 아직 추론·양자화하지 않은 파일

## 지금 할 일

ZIP을 새 폴더에 풀고, 이 README와 smoke·full·tools 폴더가 있는 위치를 확인한다.
권장 위치는 `C:\LLM\v11_calibration_prepare`이다.
기존 `rkllm-team\data\config.yaml`에 덮어쓰지 않는다.
모델 파일은 기존 `rkllm-team\model`의 9개를 그대로 사용한다.

이 패키지는 마음AI 제공 이미지 `rkllm-class:1.3.0`의 check/calib 코드를 그대로 실행한다.
PowerShell에서 Docker에 필요한 폴더를 직접 연결하는 방식이며, 제공 run.sh의 폴더 연결과 같은 역할이다.
run.sh를 수정하거나 Docker 이미지를 재설치하지 않는다.

## 포함 파일

- `smoke/data/config.yaml`: 16문장 시험용 설정
- `smoke/data/queries.json`: 학습 Train에서 고른 명령별 1문장, 총 16개
- `smoke/data/reference.json`: 검수용 원문·기존 정답·Train 줄 번호 (calib.py 입력 아님)
- `full/data/config.yaml`: 500문장용 설정
- `full/data/queries.json`: Train에서 고른 500문장
- `full/data/reference.json`: 500문장 출처·정답 기록 (calib.py 입력 아님)
- `system_prompt_v11.txt`: 실제 첨부 Train에 저장된 979자 프롬프트, 수정 없음
- `selection_audit.json`: 출처 해시, 제외 기준, 16명령 분포, 알려진 제한
- `tools/preflight.py`: 프롬프트·입력 길이·토크나이저·헤더 조회, 모델 가중치 로딩 없음
- `tools/review_calibration.py`: 생성된 input/target을 검수. 잘못된 정답을 자동 교체하지 않음

`data_quant.json`은 아직 없다. 제공 calib.py를 실제 V11 모델로 실행해야 생성된다.

## 데이터 선정

사용자가 올린 train_v11.jsonl 2,776개만 발화 공급원으로 사용했다.
16개 명령에 최소 20개씩 배정하고, 남은 180개는 원본 명령 빈도에 비례 배정했다.
문자 n-gram 유사도를 이용해 대표성과 표현 다양성을 함께 반영했다.
시간 알림에는 1·5·10·14·30·60·90·120·180분의 숫자 표현을 우선 포함했다.
실제 원문만 사용하며 발화를 새로 만들거나 정답 정책을 수정하지 않았다.

보관 중인 V11 Val 302개·Eval 420개·Boundary 120개·추가 Eval 24개,
대화에서 확인한 최종 마이크 평가 발화 16개와 공백·문장부호를 제거해 비교했다.
선정 500개와 위 보관본 사이에 겹치는 원문은 없다.
외부에서 이후 변경된 평가 파일이나 모든 의미상 유사 표현까지 비중복임을 보증하는 것은 아니다.
기본/Eval/Boundary 결과를 이 Train 500개의 생성 정답 일치율로 대체하면 안 된다.

## 설정 변경과 유지 사항

| 항목 | 제공 기본값 | 준비 파일 |
|---|---|---|
| team / domain | team01 / study | bajahoe-v11 / posture (산출물 이름용) |
| system_prompt | 학습 계획 안내 | 첨부 Train의 정확한 V11 프롬프트 |
| prompt_template | chat_template | 유지 |
| calib_dtype | auto | float16 명시 |
| dtype | float32 | float16 명시 |
| calib_stop_at | 비움 | `<suda_end>` |
| calib_max_new_tokens | 64 | 유지 |
| max_context | 4096 | 1024 임시 후보, 아래 길이 검사를 통과해야 사용 |
| 양자화 설정 | w8a8 / normal / opt 1 / hybrid 0 | 유지 |
| 보드 | RK3588 / NPU 3코어 | 유지 |

`max_context=1024`는 앞서 평가에 사용한 길이를 기준으로 잡은 후보이며,
작은 컨텍스트로 불필요한 메모리 요구를 줄이려는 설정이다. 실제 입력을 잘라내지 않는다.
preflight가 전체 프롬프트 길이 + 출력 64토큰이 1024 이내인지 검사한다.
초과하면 중단한다. 그때 프롬프트를 삭제하거나 자르지 말고 길이 값을 다시 정한다.

제공 common.py의 enable_thinking=False를 그대로 쓴다.
제공 calib.py의 do_sample=False와 repetition_penalty=1.1도 바꾸지 않았다.
따라서 추론 환경·생성 인자까지 이전 swift 평가와 완전히 같다고 단정하지 않는다.
16문장 시험에서 먼저 결과를 확인한다. `<suda_end>`는 생성 후 문자열 절단 시 포함되며,
이 설정이 4개 토큰으로 구성된 마커를 단일 EOS로 바꾸거나 생성 즉시 중단시키지는 않는다.

## 1. PowerShell에서 경로 설정

압축을 푼 실제 위치가 다르면 두 번째 경로만 맞춘다.

```powershell
$v11TeamPath = "C:\LLM\rkllm-class-dist\rkllm-class-dist\rkllm-team"
$v11PrepPath = "C:\LLM\v11_calibration_prepare"
Test-Path "$v11TeamPath\model\model.safetensors"
Test-Path "$v11PrepPath\smoke\data\config.yaml"
Test-Path "$v11PrepPath\full\data\queries.json"
```

세 결과가 모두 True여야 한다. False이면 경로부터 확인한다.

## 2. 가중치를 로딩하지 않는 사전 점검

먼저 full 500개 전체 길이를 확인한다. 사용자 모델/데이터/도구는 모두 읽기 전용이다.

```powershell
docker run --rm --mount "type=bind,source=$v11TeamPath\model,target=/work/model,readonly" --mount "type=bind,source=$v11PrepPath\full\data,target=/work/data,readonly" --mount "type=bind,source=$v11PrepPath\tools,target=/work/tools,readonly" --entrypoint python3 rkllm-class:1.3.0 /work/tools/preflight.py
```

PREFLIGHT PASSED 및 출력된 실제 입력 토큰 길이를 확인한다.
오류가 있으면 calib를 실행하지 않는다. 이 점검은 모델 추론이나 RKLLM 지원 실증이 아니다.

마음AI 제공 check도 시험용 설정에 적용한다.

```powershell
docker run --rm --mount "type=bind,source=$v11TeamPath\model,target=/work/model,readonly" --mount "type=bind,source=$v11PrepPath\smoke\data,target=/work/data,readonly" rkllm-class:1.3.0 check
```

calibration 파일이 없다는 경고는 첫 실행 전에는 예상된다.
제공 check.py는 tokenizer_config.json 안의 chat_template만 조회하므로,
별도 chat_template.jinja에서 정상 로딩되는 모델에도 템플릿 없음 경고를 낼 수 있다.
이때 파일을 삭제/수정하지 말고 위 preflight의 실제 토크나이저 결과와 함께 검토한다.
`CHECK PASSED`만으로 실제 모델 로딩이나 양자화가 검증된 것은 아니다.

## 3. 소량 시험 — 앞 단계 통과 후에만

Docker Desktop을 켜고 불필요한 GPU/메모리 사용 프로그램은 종료한다.
이 단계부터 V11 가중치를 실제로 로딩하고 CUDA 추론을 수행한다.
추가 학습과 양자화는 하지 않는다. RAM/VRAM 부족 시 오류 전체를 보존하고 중단한다.
문장 수가 16개라고 해서 모델 로딩 메모리까지 작아지는 것은 아니다.
CPU 자동 폴백 경고가 나오면 그대로 장시간 실행하지 말고 GPU 상태를 다시 확인한다.

```powershell
docker run --rm --gpus all --mount "type=bind,source=$v11TeamPath\model,target=/work/model,readonly" --mount "type=bind,source=$v11PrepPath\smoke\data,target=/work/data" rkllm-class:1.3.0 calib
```

생성 결과는 `smoke\data\data_quant.json`에 남는다. 기존 팀 data 폴더는 변경되지 않는다.
같은 명령을 재실행하면 제공 코드가 이 생성 파일을 덮어쓸 수 있으므로,
이미 파일이 있으면 먼저 결과를 검토/보존하고 재실행 여부를 결정한다.

## 4. 생성 결과 검수

```powershell
docker run --rm --mount "type=bind,source=$v11PrepPath\smoke\data,target=/work/data,readonly" --mount "type=bind,source=$v11PrepPath\tools,target=/work/tools,readonly" --entrypoint python3 rkllm-class:1.3.0 /work/tools/review_calibration.py
```

16개 전체의 형식·기존 정답과의 차이를 확인한다. 빈 think 블록만 비교할 때 제거한다.
원래 target 데이터는 바꾸지 않는다. 형식 오류나 smoke 오답이 있으면 500개 실행을 보류하고 원인을 확인한다.
검수 출력과 calib 로그를 대화에 공유한 다음 다음 단계를 정한다.

## 이후 단계 — 지금 자동 실행하지 않음

소량 결과를 확인한 후 full/data에 대해 제공 calib를 실행한다.
전체 생성 결과의 잘못된 태그·명령과 대표 샘플을 검수한 뒤에만 convert로 넘어간다.
500개 문장 생성은 학습이 아니며, 이 단계만으로 .rkllm 파일이 만들어지지 않는다.
메모리 적합성·실제 RKLLM 변환·보드 추론은 아직 검증 전이다.
FP16 비교 기준은 병합/미병합 동일 조건의 522/540이고, bnb4 결과 531/540이 아니다.

## 인코딩

한글이 PowerShell에서만 깨져 보이면 아래처럼 UTF-8을 지정해 읽는다.
화면이 깨졌다는 이유로 원본 YAML이나 프롬프트를 재작성하지 않는다.

```powershell
Get-Content -LiteralPath "$v11PrepPath\smoke\data\config.yaml" -Encoding UTF8 -Raw
```

## 확인 범위

이 패키지는 데이터 출처·분포·정확한 프롬프트·YAML 문법을 검사해 준비했다.
현재 모델 가중치를 이 작업 환경에 로딩하거나 원격 PC에서 명령을 실행하지 않았다.
로컬 가중치의 정상 헤더/크기 확인은 Drive 원본과 SHA256 전체 일치를 검증한 것과 다르다.
필요하면 Drive/Colab 원본과 PC 파일 해시를 별도 비교한다.
