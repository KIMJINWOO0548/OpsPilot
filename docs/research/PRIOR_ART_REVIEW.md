# G0 R00 선행연구 1차 재검토

**조회일:** 2026-10-19 (KST)  
**범위:** 공식 논문/저장소/공식 문서의 공개 설명, GitHub `main` 현재 커밋 및 저장소의 LICENSE 파일 확인. 저장소나 벤치마크 데이터는 내려받거나 실행하지 않았다. 이 기록은 G0/R00 완료, 재현 완료, 독창성 승인 또는 성능 우위를 뜻하지 않는다.

## 비교 대상

| 원천 및 확인 기준 | 공개 설명과 범위 | 라이선스 | OpsPilot-X와의 관계 및 미검증 |
|---|---|---|---|
| [EnterpriseRAG-Bench 공식 저장소](https://github.com/onyx-dot-app/EnterpriseRAG-Bench/tree/d36685e273713975ee20299bbf1ab64165575b3c), 확인 커밋 `d36685e273713975ee20299bbf1ab64165575b3c` (GitHub API commit time: 2026-05-07 17:57:22 UTC). [README](https://github.com/onyx-dot-app/EnterpriseRAG-Bench/blob/d36685e273713975ee20299bbf1ab64165575b3c/README.md), [quickstart](https://github.com/onyx-dot-app/EnterpriseRAG-Bench/blob/d36685e273713975ee20299bbf1ab64165575b3c/quickstart.md), [LICENSE 원문](https://github.com/onyx-dot-app/EnterpriseRAG-Bench/blob/d36685e273713975ee20299bbf1ab64165575b3c/LICENSE). | README는 약 50만 건의 기업 문서와 500개 질문, 10개 유형을 설명한다. 500문항에는 충돌 정보 20, 정보 없음 20, 고수준 질문 10개(단일 정답 문서 없음)가 포함된다. 생성형 Redwood Inference 기업 코퍼스와 RAG 검색·응답 평가가 중심이다. | 코드 저장소 LICENSE 식별자: **MIT License / SPDX: MIT**. 이 식별은 저장소 코드의 LICENSE를 가리킨다. 데이터셋 각 자산(문서, `questions.jsonl`, ZIP/slice)의 별도 이용 허락은 **미검증**이다. 데이터 자산 권리 범위를 묻는 [공식 이슈 #17](https://github.com/onyx-dot-app/EnterpriseRAG-Bench/issues/17)은 2026-10-09 닫혔지만 공개 본문에는 질문만 있고 댓글은 0개여서 답변 근거로 볼 수 없다. | 겹침: 문서 간 상충과 정보 없음 질문은 conflict/abstain 평가 설계에 참고 가능하다. 차이: 공개 설명은 bitemporal `effective_at`/`known_as_of`, 승인 여부, ACL 선검색, 승인 후 action gate 검증을 목표로 한 벤치마크가 아니다. 공개 설명만으로 해당 필드/라벨의 실제 커버리지를 확정할 수 없어 **미검증**이다. 500 질문은 우리 합성 8개 스모크와 규모·범위가 다르고, 그 8개는 성능 결과가 아니다. 데이터 권리 확인 전 다운로드·사용하지 않는다. |
| [AgentDojo 논문](https://arxiv.org/abs/2406.13352) 및 [공식 코드 저장소](https://github.com/ethz-spylab/agentdojo/tree/089ed468cf3ed0322acc66b0211f26d9d90dbf60), 확인 커밋 `089ed468cf3ed0322acc66b0211f26d9d90dbf60` (GitHub API commit time: 2026-06-02 00:59:58 UTC). [README](https://github.com/ethz-spylab/agentdojo/blob/089ed468cf3ed0322acc66b0211f26d9d90dbf60/README.md), [LICENSE 원문](https://github.com/ethz-spylab/agentdojo/blob/089ed468cf3ed0322acc66b0211f26d9d90dbf60/LICENSE). | arXiv v3 (2024-11-24) 논문은 도구 결과 안에 숨은 prompt injection을 통해 에이전트의 유틸리티와 보안을 평가한다. 최초 범위는 97개 사용자 작업과 629개 보안 테스트 사례다. 이메일, 은행, 여행 등 모의 도구 환경의 공격/방어 평가다. | 코드 저장소 LICENSE 식별자: **MIT License / SPDX: MIT**. 태스크 fixture 및 그 외 배포 자산의 독립 데이터 라이선스/모델 가중치 권리는 별도 확인되지 않아 **미검증**으로 둔다. 논문 자체 이용 조건도 이 코드 LICENSE로 추정하지 않는다. | 겹침: 외부 문서/도구 출력은 신뢰하지 않고, 악성 지시가 있어도 action 경계를 지켜야 한다는 위협 모델 및 안전 테스트 관점. 차이: 핵심 범위는 prompt-injection 강건성이지 bitemporal evidence, 문서 revision conflict, 당시 알 수 있던 사실의 재생이 아니다. 97/629는 우리 8개 합성 스모크와 모집단·측정 대상이 달라 직접 점수 비교에 사용할 수 없다. |
| [LangGraph 공식 문서: Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api) 및 [공식 저장소](https://github.com/langchain-ai/langgraph/tree/7b23a1084683c58a4c20f4e1290968536cc34e85), 확인 커밋 `7b23a1084683c58a4c20f4e1290968536cc34e85` (GitHub API commit time: 2026-10-19 04:45:42 UTC). [Python package LICENSE 원문](https://github.com/langchain-ai/langgraph/blob/7b23a1084683c58a4c20f4e1290968536cc34e85/libs/langgraph/LICENSE). | 공식 문서는 checkpointer의 pause/resume/replay와 side effect를 task 경계에 두는 법을 설명한다. 중단 중 완료되지 않은 task는 재실행될 수 있으므로 idempotency key 또는 기존 결과 확인을 권고한다. 이는 workflow 실행 재개 의미론이다. | `libs/langgraph` LICENSE 식별자: **MIT License / SPDX: MIT**. 확인한 코드 LICENSE는 문서 라이선스나 별도 provider integration/외부 패키지 권리 전체를 자동 확정하지 않는다. | 겹침: 승인 전후 실행, 재시도, 응답 유실을 다룰 때 replay와 idempotency 설계를 참고할 수 있다. 차이: 오케스트레이션 checkpointer가 도메인 권한 판정, bitemporal 원장, 증거 충돌 정책, 외부 시스템 exactly-once를 대신 보장하지 않는다. 문서의 idempotency 권고는 OpsPilot-X의 mock 외부 작업 키·receipt reconciliation 필요성을 없애지 않는다. |

## 가설과 범위에 대한 현재 판단

- **중복 위험(R1): 높음/해소 안 됨.** 시간 필터 + 범용 NLI/sufficiency(B2/B3)를 먼저 강한 대조군으로 세워야 한다. 이번 세 출처만으로 claim/evidence conflict 분류 또는 action-aware gate의 신규성을 승인할 수 없다. `effective_at`과 `known_as_of`를 분리한 증거 이력 및 policy gate가 대조군 대비 독립적으로 더하는 효과가 핵심 검증 대상이다.
- **범위(R2):** 단일 도메인·최소 수직 경로로 제한한다. G0/G1이 잠기기 전 새 모델·DB·retrieval/agent 프레임워크 추가 결정은 하지 않는다.
- **누수(R3):** 외부 문서에 공개된 질문은 사전학습 혼입 가능성이 있으므로 비공개 holdout으로 취급하지 않는다. T2에서는 같은 문서/source family가 train/dev/holdout에 섞이지 않도록 group split과 유사문서 검사, 독립 라벨 검토가 필요하다.
- **abstain 편법(R4):** 정보 없음 항목만으로 무응답 편법을 막을 수 없다. 성능은 동일 coverage의 risk와 정상 요청 completion을 함께 측정해야 한다.
- **벤치 부적합(R5):** EnterpriseRAG-Bench는 RAG 질의응답 범위이며 action authorization/실행 안전성까지 검증한다고 볼 수 없다. AgentDojo는 prompt-injection 안전성에 초점을 두므로 시간·revision 정확도를 검증하는 벤치로 대체할 수 없다. T1/T2/T3를 분리하고 숫자를 직접 비교하지 않는다.

## 기술 범위 메모

현재 시작점은 **Python + FastAPI + SQLite + 결정적 규칙**으로 유지한다. **React/TypeScript는 G6 예정**으로 기록한다. LangGraph는 replay/idempotency 경계를 연구할 비교 참고 대상이며 도입 결정은 아니다. 이 메모는 새 기술 선택이나 ADR 결정을 만들지 않는다.

## 재검증 한계와 후속

확인한 것은 공개 설명, 저장소 `main`의 API 반환 commit SHA, 해당 LICENSE 파일 텍스트 및 접근 가능한 공식 문서다. 데이터셋/저장소 다운로드, 실행·설치, baseline 재현, dataset hash, 모델/가중치 사용권, 동일 조건 성능 검증은 하지 않았다. 특히 EnterpriseRAG-Bench와 AgentDojo의 데이터 자산 권리는 각 코드 LICENSE와 별개로 **미검증/접근 제한** 상태다. 링크와 SHA는 출처 식별 근거일 뿐 라이선스 승인이나 재현 증거가 아니다.

**후속 R00 작업:** 데이터 이용 허락의 자산 범위와 배포 조건을 원문으로 확인하고, B2/B3/B4 경계 및 T1/T2/T3 데이터 적합성·누수 규칙을 기록한다. 그 검토와 G0 담당자의 승인 전에는 G0 완료, 외부 점수 비교, 95점 주장을 하지 않는다.

## 2026-10-20 원천 재확인 (AI-only, 문서 읽기)

아래 SHA는 각 공식 GitHub API가 반환한 기본 브랜치 tip이며, 같은 커밋의 원문 LICENSE는 CSV의 `license_text_url`(commit 고정 raw URL)로 연결했다. GitHub API가 `NOASSERTION`을 반환한 SURE-RAG와 pgvector는 원문 LICENSE 표제/본문으로 각각 Apache-2.0, PostgreSQL License를 식별했다. 코드는 LICENSE 전문을 내려받아 실행한 것이 아니라 원격 raw 응답으로 읽었다. 버전은 확인 기준 시각만 고정할 뿐, 라이선스가 데이터·가중치·외부 서비스까지 허용한다고 뜻하지 않는다.

| 원천 | 확인한 공개 코드/문서 범위 | 코드 라이선스와 재현 제한 | 충돌/차별성 의미 |
|---|---|---|---|
| [SURE-RAG](https://github.com/mouwumou/SURE-RAG/tree/fa9ec380d32eb9092512a8d00f906828b036b0fb), [논문 v2](https://arxiv.org/abs/2605.03534) | 질문·후보 답변·검색 증거에 대해 claim/evidence의 support/refute/insufficient와 집합 수준 sufficiency를 평가하고 answer/abstain/retrieve-more로 라우팅한다. README demo 명령 확인. | Apache-2.0 코드. 모델 가중치/데이터 별도 권리 미확인. 데모 명령 확인, 미실행. 논문 초록만 읽음. | B3와 직접 중첩되는 가장 강한 선행 방법이다. B4의 독자 기여는 sufficiency 점수 자체가 아니라 유효/기록 시각 재생과 근거 충돌·정책상 허용 조치의 독립 효과로 좁혀야 한다. |
| [GraphRAG](https://github.com/microsoft/graphrag/tree/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f), [공식 문서](https://microsoft.github.io/graphrag/) | 그래프 기반 RAG로 질의응답용 targeted context를 구성한다. README는 연구 프로젝트이며 현재 유지보수 중심이라고 밝힌다. | MIT 코드. 코퍼스/모델 권리 미확인. 이번에 확인한 공식 문서 발췌에서는 재현 명령을 확정하지 못해 명령 미검증, 미실행. | 그래프 구성/검색 대조군 후보이나 temporal ledger나 action policy의 증거는 아니다. 선택 시 인덱싱 비용·동일 검색 조건을 별도 통제해야 한다. |
| [EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench/tree/d36685e273713975ee20299bbf1ab64165575b3c), [공식 quickstart](https://github.com/onyx-dot-app/EnterpriseRAG-Bench/blob/d36685e273713975ee20299bbf1ab64165575b3c/quickstart.md) | 기업 문서 RAG 질문응답 평가/데이터 생성. quickstart에는 답변 평가 명령과 데이터 다운로드 경로가 문서화됨. | MIT는 저장소 코드 범위. 50만 문서/질문/배포 데이터의 자산별 이용·재배포 권리는 이 확인에서 확정하지 못함. 평가 명령 확인, 미실행. | 문서 충돌/정보부족 QA에 참고되나 승인·권한·실행 후 복구를 검증한다고 볼 수 없다. 공식 데이터 권리 문의가 해결된 것으로 간주하지 않으며 T1 사용 전 자산별 허락이 필요하다. |
| [FEVER](https://github.com/awslabs/fever/tree/3d04722cf16b42b9974ed5ffdd007b03ed954e24) | 185,441개 Wikipedia 기반 claim에 SUPPORTS/REFUTES/NOT ENOUGH INFO 라벨을 둔 claim verification 데이터·baseline 저장소. README의 submodule 명령 확인. | Apache-2.0 코드. Wikipedia/데이터 권리 및 가중치 미확인. clone/submodule 명령은 기록만 했고 clone·실행하지 않음. | B3의 claim 상태 sanity 대조에 적합할 수 있으나 기업 문서 revision/time-travel/action gate 평가를 대체하지 못한다. 공개/사전학습 누수 주의. |
| [LongMemEval](https://github.com/xiaowu0162/LongMemEval/tree/9e0b455f4ef0e2ab8f2e582289761153549043fc) | 장기 대화 기억 질의 평가. README에 데이터 다운로드, 환경 설정과 evaluation 실행 절차가 있음. | MIT 코드. 대화 데이터 및 모델 가중치의 별도 권리 미확인. API 키/모델/데이터가 필요한 절차라 실행하지 않음. | 시간에 따른 사실 변경 문제는 인접하지만 대화 기억과 기업 증거의 출처·ACL·조치 권한은 다르다. 점수 비교 불가. |
| [LangGraph](https://github.com/langchain-ai/langgraph/tree/a24fc97778fca67cfac4cd3fc63e508ee1d29f59) | 상태형 agent 오케스트레이션 패키지. 이전 공식 문서 재검토의 pause/resume/replay와 재실행 시 idempotency 경계를 참고한다. | MIT 코드. 외부 모델/provider 권리는 별도. `pip install` 문서 명령만 확인, 설치·재현하지 않음. | checkpoint는 실행 흐름 재개이지 도메인 승인, bitemporal 증거, 외부 시스템 exactly-once 보증이 아니다. 기존 중복 방지·reconciliation 불변조건 유지. |
| [pgvector](https://github.com/pgvector/pgvector/tree/f37c13f68b57d2c3472b2214fbcff699d6d34876) | Postgres에서 exact/approximate vector search, HNSW/IVFFlat 및 거리 함수를 제공. | PostgreSQL License. 설치/빌드 명령은 확인만 함. 호환성/성능 미측정. | 인덱스/검색 기반 기술이지 ACL 선검사나 temporal semantics가 아니다. 인가 검사를 후보 생성 전 수행해야 한다. |
| [AgentDojo-core](https://github.com/ethz-spylab/agentdojo-core/tree/23bf925979d051443f2e780ab19bff80f2066d6d) | prompt injection 공격/방어를 agent 도구 환경에서 평가하는 core 코드. README benchmark 명령은 모델 선택을 요구한다. | MIT 코드. 별도 fixture/data 및 모델 권리 미확인. 설치/호출 명령 미실행; API 호출 없음. | 악성 근거와 action boundary 위협에는 인접하나 시간·문서 revision claim conflict 실험의 대체재가 아니다. |

이번 확인은 2026-10-20 KST의 공개 GitHub API/고정 raw README·LICENSE와 SURE-RAG 논문 초록 및 위 공식 문서에 한정된다. 데이터나 weights를 내려받거나 저장소를 clone하지 않았고, 설치·명령 실행·유료 API 호출·baseline/benchmark 재현도 하지 않았다. 따라서 데이터/weights의 이용권, 실제 재현성, 성능/비용, 동일 조건 우열은 미검증이다. Matrix의 `REFERENCE_ONLY`는 비교 후보라는 뜻이며 제품 채택 또는 G0 통과가 아니다.
