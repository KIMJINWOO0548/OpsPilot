# Evidence Integrity Engine — 계약 v0.1 (G3에서 강화)

## 1. 입력
- `Actor`: 서버 DB의 인증된 principal에서 생성한다. API JSON actor는 권한에 사용하지 않는다. 로컬 계정/세션 구현은 IdP/OIDC·기업 보안 인증을 의미하지 않는다.
- `AnalyzeRequest`: `asset_id`, `claim_key`, `effective_at`, `known_as_of`, `actor`.
- `EvidenceRecord`: `tenant`, `team`, `readable_roles`, `source_id`, `version`, `checksum`, `valid_from`, `valid_to`, `recorded_at`, `supersedes`, `authority`, `locator`, `claim_key`, `value`.
- 모든 시간은 타임존 포함 ISO 8601; 유효기간은 `[valid_from, valid_to)` 반열림 구간.

## 2. 권한·정보 흐름
1. 서버 계정·만료되지 않은 opaque session을 확인한다. 변경 요청에는 CSRF를 검사한다.
2. `tenant`, `team`, `role` 조건을 **retriever query 전** 적용; 접근 불가 레코드를 랭킹하거나 LLM 입력으로 전달하면 실패.
3. API는 SQLite evidence/ACL의 bound SQL로 scope·관측 시점을 선필터한 후보를 EIE에 전달한다. 코어는 전달된 seed를 재검증하고 단위 smoke의 기본값은 합성 fixture다. PostgreSQL RLS·SQL agent·LLM은 미구현이다.
4. authorized + known(recorded_at <= known_as_of) + valid(effective_at 포함) 원칙.
5. 이미 알고 있는 유효 후보만 대상으로 같은 asset/claim의 supersedes 관계를 해소한다. 검색 응답의 관계 ID도 접근 가능하고 관측된 동일 asset/claim에 한정한다. ACL 불가·미래 자료의 존재 여부를 결과에 누설하지 않는다.
6. 같은 scope/시간에서 승인 SOP가 여러 다른 행동을 주장하고 우열 관계가 없으면 `CONFLICT`.
7. 유효 SOP 없이 과거 레코드만 존재하면 `STALE`; 조회 근거 자체가 없으면 `INSUFFICIENT`.
8. `SUPPORTED`는 **해당 테스트 범위에서 규칙상 초안 작성 가능**임을 의미할 뿐 물리적 안전성/실무적 정확성을 보증하지 않는다.

## 3. 출력
- `SUPPORTED`: `recommended_action` 값과 이용한 `citations` 연결.
- `CONFLICT`: 행동 없음, 충돌 근거 식별.
- `INSUFFICIENT` / `STALE`: 행동 없음, 비인가/숨김 ID와 원문이 노출되지 않음.
- 확장 예정: `REFUTED`, `FORBIDDEN`, `HUMAN_REVIEW`, `RETRIEVE_MORE`(최대 2회), claim-level `support/refute/insufficient`.
- 값의 출처와 모델-추론 근거를 구별; 텍스트가 citation의 존재를 보증하지 못함.

## 4. 승인 계약 / API
- `POST /api/v1/analysis`: 읽기 전용 보고.
- `POST /api/v1/proposals`: SUPPORTED + 인증된 engineer + 1시간 내 현시점 요청일 때만 초안, hash 계산.
- `POST /api/v1/proposals/{id}/decision`: 인증된 독립 approver, request hash·저장 action 일치 확인, 서버가 evidence 최신본 재검증.
- `POST /api/v1/proposals/{id}/execute`: 결정 승인 후에만 SQLite mock write. `idempotency_key` 유일 제약.
- `POST /api/v1/proposals/{id}/reconcile`: 실제 모의 원장 receipt 조회 후 UNKNOWN 해소.
- 실제 외부 API를 보낸 뒤 응답을 잃는 **분산 시스템 복구까지** 재현했다고 주장하면 안 됨. 현재 write/approval가 같은 SQLite DB에 있으므로 별도 서비스 경계가 없다.

## 5. SC-01~10 예상 행동 (현 구현/미구현 구별)
| 시나리오 | 기대 | G2 상태 |
|---|---|---|
| SC01 현재 A-103 | sensor_diagnostic_first | 구현/테스트 |
| SC02 과거 9월 20일 A-103 | replace_filter | 구현/테스트 |
| SC03 사후 정정 A-104 | 9월 당시/10월 알게 된 진실 분리 | 구현/테스트 |
| SC04 A-105 SOP 충돌 | CONFLICT, 실행하지 않음 | 구현/테스트 |
| SC05 SECRET-1 권한 차단 | 존재/원문 노출 금지 | **demo persona 조건으로만** 구현 |
| SC06 A-106 문서 인젝션 | 문서 본문을 명령으로 실행하지 않음 | 규칙 엔진에서만 테스트 |
| SC07 응답 유실 | mock UNKNOWN → receipt → SUCCEEDED | 로컬 모의 구현 |
| SC08 승인 후 원본 변경 | hash 재검증, EXPIRED | 기본 코드 구현/추가 변이 테스트 필요 |
| SC09 train/holdout 누수 | CI 차단 | source/revision/hash·case ID·근접중복 검사와 CI 단계 구현; 실제 독립 holdout·GitHub 실행 미확인 |
| SC10 고비용 알고리즘 | 성능·비용 tradeoff 보고 | 미구현 |

## 6. 실험용 대조군 (실제 개발 구현 이후)
- B0 lexical + deterministic template
- B1 Hybrid RAG 같은 LLM·top-k·prompt budget
- B2 B1 + 단순 time filter / 최신 문서 규칙
- B3 B2 + 공개 NLI/sufficiency 판정 (라이선스/재현성 확인)
- B4 B3 + proposed EIE claim-aware bitemporal decision gate
- **G2 현재 엔진은 B4의 성능을 증명한 코드가 아니다.** 정형 구조의 단순 정책 시연이다.

## 7. 데이터 무결성 확대 목표
- fixture는 실제 SHA256 텍스트 체크섬을 계산·검증함.
- 생산 수집 파이프라인에는 append-only version, transaction-time history, 문서 파서 추적, source permissions, invalidation event, immutable approval snapshot 포함.
- 복잡한 과거소급 개정 사례에서는 interval intersection, supersedes DAG cyclic detection, authority tie handling, missing history 검증 필요.
- Unicode/단위 변환·timezone 경계·clock skew 테스트 추가.
