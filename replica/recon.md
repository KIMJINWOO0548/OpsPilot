# 승인 입력 검토 — 공개 기능 참조 (2026-11-06)

범위: 기존 OpsPilot 승인함에서 초안의 주장과 두 시점을 확인하는 작은 기능 개선. Replica recon/diff를 기능 범위로 적용했으며 전체 LangChain 복제나 시각적 동일성은 목표가 아니다.

| 출처 | 관찰한 사실 | 사용 범위 |
|---|---|---|
| https://docs.langchain.com/oss/python/langchain/human-in-the-loop | 공개 문서에서 실행 전 도구 호출을 멈추고 원래 인자를 검토하여 승인·수정·거절하는 흐름 | 승인 전 입력 맥락 확인 패턴 |

REA 6.8.0 공개 브라우저 캡처는 Chromium 156.0.8078.80, exit 0, provider 소유 프로세스 정리 완료. 원문/스크린샷은 로컬 참조 전용이며 배포하지 않는다. 접근성 캡처 SHA-256: `50f6e285075da3abf3a7a5b8dcfa8129f9477ab06cbea686dea8b9f152b1b279`. 계정 사용·비공개 API·제품 코드 복사는 없다.

## 화면과 흐름

S01 공개 문서: 중단된 호출과 검토 결정 설명(관찰). 실제 로그인 제품 UI는 미관찰.
S02 OpsPilot 승인함: 작성자·조치·인용·fingerprint(기존), 주장·업무 유효 시점·관측 시점(이번 추가), 근거 검토 불가·완료 상태.
F01 작성자가 초안 생성 → 독립 승인자가 승인함 목록 선택 → 저장된 주장과 두 시점 확인 → 근거/조치 확인 → 승인 또는 거절. 제안 선택 후 추가 클릭 없이 맥락 확인.
F02 문서 권한 회수 → 상세 재조회 → review_context=null, 기존 근거 검토 불가 안내. 조회는 상태·감사·mock 원장을 쓰지 않는다.

반복 구성: 기존 review-meta 정의 목록과 KST 시간 표시. 새 디자인 시스템/라이브러리 없음.
추론: 사람이 원래 요청 맥락을 확인할 수 있으면 잘못된 시점의 승인 검토를 줄일 수 있다. 효과는 사용자 실험으로 측정하지 않았다.
데이터: 기존 저장 request_json의 claim_key/effective_at/known_as_of만 읽고, 현재 호출자 ACL과 최신 근거 검증이 성공할 때 review_context로 투영한다. actor나 원문은 추가하지 않는다.

## 구현 경계

기준 `feat/proposal-review-readiness` / `5bd503f`. 형제 `feat/temporal-decision-comparison` / `1dd520e`는 기준의 ancestor가 아니다(`git merge-base --is-ancestor` exit 1). 해당 브랜치를 병합하거나 덮어쓰지 않았다. 이번 추가는 기존 readiness의 중복 구현이 아니라 검토 입력 누락을 채운다.

수정·재개 가능한 에이전트 런타임, 실설비 실행, 도구 편집, LLM 도입은 제외. 기존 독립 승인·fingerprint·ACL·response-loss 복구 정책 유지. G0/G1 연구 및 운영 수용 완료를 의미하지 않는다. 규모 S: API 투영 1개, 기존 UI 1개, 회귀 테스트 2개.

## Phase 2 depth audit
See [critical workflow audit and acceptance plan](depth-review.md). Documentation evidence, local measurements and untested competitor behavior are distinguished.
