# Codex 게이트 작업: G0/G1

아래 작업을 테스트 가능한 PR 단위로 완료합니다.

1. AGENTS.md / 현재 테스트 실행 로그 확보.
2. docs/research/prior_art_matrix.csv 의 8개 연구/오픈소스 행마다 공식 저장소 및 라이선스·코드 기능·체크포인트·commit SHA를 검증해 채우기. 접근 불가 항목은 UNVERIFIED 유지.
3. novelty collision matrix 작성. 단순 B2/B3가 해결하는 문제와 B4에만 남는 문제를 문서로 명시.
4. evaluation/datasets 폴더에 독립적인 `source_group_id`, `document_revision_family`, `split`, `labeler` 필드를 정의하고, **같은 source family가 train/dev/holdout에 중복될 때 CI 실패**하는 `scripts/check_split_integrity.py` + pytest 작성.
5. T2 라벨 예제 30개를 제3자가 원문 대조할 수 있도록 source ref와 rationale 포함해 설계. 없는 자료는 실제 자료라고 주장하지 말 것.
6. T0 스모크를 T2 고품질 평가와 구분하는 자동 validator 만들기.
7. G0/G1 산출물/차단 위험(R1~R5)/미완료를 GATE_STATUS/WORK_LOG에 업데이트.

완료 조건: 출처 검증과 split checker를 재현 가능하게 실행. 실제 외부 benchmark 성적이나 95점 점수는 금지. 비용 발생·데이터 라이선스 위반 우려 시 사용자 승인 요청.
