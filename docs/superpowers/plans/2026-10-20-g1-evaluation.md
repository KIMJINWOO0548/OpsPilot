# G1 평가 계약 구현 계획

> 사용자 지시대로 무료 로컬 작업을 즉시 실행한다. `.git` 없는 패키지에서 작업하므로 PR/commit/worktree는 만들 수 없으며, 각 단위의 테스트·변경을 WORK_LOG에 기록한다.

**목표:** 데이터와 예측 파일을 검증한 뒤 재현 가능한 지표를 계산하고, 연구 미실행과 coverage 부족을 명시한다.
**명세:** [ADR-002](../../decisions/ADR-002-EVALUATION-CONTRACT.md), [평가 프로토콜](../../evaluation/EVAL_PROTOCOL.md).
**기술:** 기존 Python 3.12/Pydantic, 표준 라이브러리. 새 의존성 없음.

## 단위와 인터페이스

1. G0: 공식 8종의 metadata·LICENSE·재현 범위를 `docs/research/`에 기록한다. 미확인은 그대로 남긴다. 코드/데이터 이용 권리를 구별한다.
2. 지표: `Outcome`과 `summarize`, `risk_coverage_curve`, `calibrate_threshold`, `paired_bootstrap`을 추가한다. 중단된 기존 테스트의 red를 확인하고 구현한다. source cluster를 동일하게 재표집하고 undefined risk 표본을 숨기지 않는다.
3. 데이터: `load_dataset(manifest, split='dev', allow_holdout=False)`가 source metadata·분할·원문을 확인하고 선택 split 라벨만 읽는다. `score_predictions(dataset, rows)`는 case ID 완전 일치·조치·gold 근거·권한·시점으로 `Outcome`을 만든다.
4. CLI: `eval_compare.py`에서 dev 설정 고정→같은 split의 예측 비교→JSON 보고. holdout 재보정/T0/서로 다른 예산/예측 누락을 거부한다. 30개 합성 계약 예시와 라벨 기준을 제공하되 연구 수치로 쓰지 않는다.
5. focused 검증 이후 전체 pytest·E2E·합성 smoke·Ruff를 실행하고 새 모듈 독립 리뷰를 반영한다. GATE_STATUS/TASK_BOARD/WORK_LOG를 갱신한다.

## 검토할 실패 경계

- manifest 안의 경로가 workspace 밖·심볼릭 링크 밖으로 빠지는 경우: 읽기 전에 거부.
- SHA256은 맞지만 텍스트의 공백/대소문자만 달라 split이 분리된 경우: 교차 중복 거부.
- dev를 읽는데 holdout label 파일이 손상된 경우: dev는 label을 열지 않되 전체 source metadata 분할은 검사.
- action은 맞지만 비인가·미래·틀린 인용을 섞은 경우: 정답 처리 금지, 누출 별도 계수.
- confidence 동률·모든 abstain·제안 없는 bootstrap resample: 임의 tie 분해·위험 0·표본 삭제 금지.

각 코드 단위는 테스트 먼저 작성하고 실제 실패를 확인한 뒤 구현한다. 수정한 테스트가 있으면 이유를 기록한다. 실제 모델·외부 데이터·독립 사람 검토가 없으면 G0/G1 최종 완료를 선언하지 않는다.
