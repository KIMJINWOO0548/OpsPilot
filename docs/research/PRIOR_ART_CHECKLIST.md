# G0 선행 연구 + 오픈소스 검증 체크리스트

**현재 상태:** 대상 목록은 유지한다. 2026-10-20 공개 공식 저장소의 commit SHA, 코드 LICENSE 원문 URL/SPDX, README 범위와 문서화된 명령을 `prior_art_matrix.csv`에 기록했다. 이는 코드 저장소 식별과 문서 확인이며, 데이터/가중치 권리 확인, 실행 재현, novelty 승인과는 다르다. 세부 판단과 미확인 항목은 `PRIOR_ART_REVIEW.md`, 차별 가설은 `NOVELTY_COLLISION_MATRIX.md`를 본다.

| 대상 | 검증할 위치 | 기술적 비교 질문 | 채택 후보 |
|---|---|---|---|
| [SURE-RAG](https://github.com/mouwumou/SURE-RAG) | README, code, checkpoints, LICENSE, arXiv revision | NLI/support/refute/insufficient 방식 공개 재현 범위? | B3 학습 없이 지원 가능한 일부 |
| [GraphRAG](https://github.com/microsoft/graphrag) | docs/methods, LICENSE, costs | 엔티티/관계/Global vs Local 검색의 장점과 한계 | 선택 대조군 |
| [EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench) | license, dataset/official 500, metadata subset | 정답 접근성/평가 방식/데이터 출처/라이선스? | T1 |
| [FEVER](https://github.com/awslabs/fever) | task guidelines, datasets/LICENSE | support/refute/NEI classifier 검증 적절성? | NLI sanity |
| [LongMemEval](https://github.com/xiaowu0162/LongMemEval) | eval type, temporal change case | 기업 문서와 차이·재사용 한계? | 참고/보조 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | persistence, retries/interrupt, license | resume가 side effect duplication을 만들 수 있는가? | 오케스트레이션 후보 |
| [pgvector](https://github.com/pgvector/pgvector) | compatibility/licenses | temporal filter ACL pre-index, vector search latency | DB 후보 |
| [AgentDojo](https://github.com/ethz-spylab/agentdojo-core) | attack fixture/LICENSE | 자체 보안 테스트와 직접 비교 가능한가? | T3 설계 참고 |

각 대상에 대해 `vendor, repository, commit SHA, license SPDX, model weights rights, evidence API, documented limitations, reproduce command, date verified, who verified`를 `prior_art_matrix.csv`에 작성한다. 직접 돌리지 않은 벤치 결과를 나란히 비교하면 안 됨.

## 독창성 결정 게이트
- 단순 B2(최신 유효 SOP) + 범용 NLI B3로 B4와 비슷한 성능이면 강한 차별성이 없다고 인정.
- 시간·기록 시각, 문서 우선순위, SQL 자료를 연결한 별도 효과가 확인되기 전에 새로운 알고리즘이라 주장하지 않는다.
- 데이터셋 공식 범위를 넘어서는 자체 평가셋은 독립 라벨 검토의 한계를 분명히 표시.

2026-10-20 확인자 표기는 AI-only다. 공식 GitHub API/고정 commit raw LICENSE·README, GraphRAG/EnterpriseRAG-Bench 공식 quickstart, SURE-RAG 논문 초록만 읽었다. 문서화된 명령은 확인만 했으며 실행하지 않았다. 원문 데이터, 체크포인트 다운로드·설치·API 호출은 하지 않았다. SPDX는 코드 LICENSE에만 해당하고 별도 데이터/가중치 권리를 추정하지 않는다.
