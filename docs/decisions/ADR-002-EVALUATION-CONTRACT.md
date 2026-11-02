# ADR-002: G1의 원문 검증과 평가 계산을 모델 실행보다 먼저 연결

- 날짜: 2026-10-20 (Asia/Seoul)
- 상태: 로컬 구현 범위 채택. G0/G1 연구 통과 판정 아님.
- 명세: 사용자 지시 3·5·6·7 및 `EVAL_PROTOCOL.md`.

G1의 기존 분할 검사는 사용자가 제출한 metadata만 비교한다. 원문을 바꿔도 hash가 맞는지 확인하지 않고, 합성 스모크를 T2로 잘못 사용하는 실행 경로도 막지 못한다. 전체 보류의 risk가 정의되지 않는 경우와 coverage 저하를 숨길 가능성도 있다.

## 결정

- 표준 라이브러리와 기존 Pydantic/분할 검사기를 재사용한다. `evaluation_data.py`가 manifest·원문 바이트 SHA256·정규화/5-token shingle 교차 중복·시간·라벨을 검사한다. 상대 경로는 manifest 디렉터리 내부만 허용한다.
- T0는 연구 비교에서 거부한다. T2도 `contract_only`/`research`를 구별한다. 전자는 작성자 합성 fixture이며 모든 출력에 성능 검증 아님을 표시한다. 후자는 외부 출처/허가와 독립 라벨 검토 기록이 필요하지만 자동 검사가 사람 검토의 진실성을 인증하지는 않는다.
- source metadata는 전체 split을 검사한다. label 파일은 train/dev/holdout으로 분리하고 dev 실행은 holdout label 파일을 읽지 않는다. holdout은 명시적 최종 평가 옵션과 dev에서 고정한 설정 없이는 열지 않는다. 이는 실수 방지 장치이며 로컬 파일 관리자 권한에 대한 보안 경계가 아니다.
- `evaluation_metrics.py`는 gold scorer의 결과를 받아 coverage, safe completion, unsupported action rate, 부분 AURC, paired source-cluster bootstrap CI를 계산한다. 무제안 risk와 AURC는 null로 표시한다. 임계값은 dev confidence만으로 고정하고 confidence tie는 통째로 처리한다.
- `eval_compare.py`는 외부 모델을 호출하지 않는다. 고정된 prediction 파일과 실행 metadata를 검증·채점하며 동일 case 집합/모델·prompt·top-k·context budget 등을 확인한다. B0~B4 이름만 붙여 B1 Hybrid RAG나 B3 NLI가 구현됐다고 주장하지 않는다.
- 정상 합성 예시와 오류 입력으로 importer/scorer/CLI를 검증한다. 30개 예시도 독립 평가 데이터가 아니라 **작성자 검토 후보**다. labeler·출처·rationale를 명시하고 실제 검토는 미완료로 둔다.

## 채택하지 않은 대안

- 지금 모델/임베딩/통계 패키지 추가: 평가 계약이 없는 상태에서 비용과 변수만 증가한다.
- 기존 T0 8개 결과를 비교 연구 수치로 확장: 작성자가 규칙과 정답을 함께 만든 편향을 해소하지 못한다.
- 단일 JSON 파일에 holdout 정답 포함: dev 실행과 label 접근 분리가 불가능하다.

## 완료 기준과 위험

실패 테스트→최소 구현→focused tests→전체 회귀 및 WORK_LOG 기록. 해시 변조·split 교차·근접중복·경로 탈출·T0 승격·미승인 holdout 접근을 거부하고 정상 dev 입력을 읽어야 한다. 임계값/지표는 정답 변경으로 유리하게 맞추지 않는다. source-group 식별의 의미, near-duplicate false positive, 라벨 품질, coverage 모집단 정의는 독립 사람이 검토해야 한다. 데이터셋·유료 호출·외부 업로드는 실행하지 않는다.
