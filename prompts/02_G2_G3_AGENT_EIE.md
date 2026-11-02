# Codex 게이트 작업: G2 강화 + G3 EIE

선행조건: G0/G1 필수 계약과 split tester가 통과할 것. 그전 작업도 가능하지만 성과로 발표하지 말 것.

1. API demo role spoofing 경계를 유지하며 OIDC/JWT/테넌트 서버 identity 설계(테스트 가능한 mock identity provider). 공개 배포 금지.
2. SQLite 스모크를 손상시키지 않고 PostgreSQL + pgvector의 DB schema/migrations/RLS 및 인제스터를 별도 단계로 추가.
3. B0 lexical baseline부터 구현하고, 동일 top-k/LLM 예산으로 dense/hybrid B1과 simple-temporal B2, NLI verifier B3, EIE B4 비교 인터페이스 정의.
4. EvidenceRecord에 authority, `supersedes`, `effective_at`, `known_as_of`, citations, SQL receipt/checksum 계약을 구현하고 out-of-order events·이력 수정·동일 문서 중복에 대한 테스트를 작성.
5. CLAIM→EVIDENCE link를 span/SQL 결과 검증과 연결하고 `SUPPORTED/REFUTED/CONFLICT/INSUFFICIENT/STALE/FORBIDDEN` 타입 결과를 구현. 경우별 분리 평가.
6. Ablation toggle은 실험에서만 허용하며 production path의 auth/approval invariants를 끄는 스위치는 금지.
7. E2E UI/CLI가 LLM 오류를 고유 상태와 trace로 보고하도록 연동.

완료 조건: 각 Baseline 실제 측정/단위테스트, 안전 테스트, 비용·지연 측정. 미개발 알고리즘 우위를 주장 금지.
