# 선행기술 충돌 및 B4 차별 가설

**상태: 미입증 가설, 독창성 승인 아님 (2026-10-20 KST).** 문헌/저장소 범위 요약은 [PRIOR_ART_REVIEW.md](PRIOR_ART_REVIEW.md), 고정 commit·코드 라이선스·문서화된 명령은 [prior_art_matrix.csv](prior_art_matrix.csv)에 있다. 어떠한 baseline이나 benchmark도 이번 작업에서 실행하지 않았다.

| 구성 | 하는 일 | 알려진 충돌/한계 | 이번 프로젝트에서 검증할 것 |
|---|---|---|---|
| B2: B1 + 단순 valid-time 최신 문서 필터 | 업무상 현재 유효한 개정 문서만 반영 | 나중에 시스템이 알게 된 정정과 과거 질의 시점을 구별하지 못할 수 있음. 정렬된 단일 최신 버전을 전제하면 동시 유효 충돌/우선순위도 놓칠 수 있음. | 같은 질문·검색 결과에서 effective-time 필터와 `known_as_of`를 분리한 과거 재생의 차이를 짝 비교한다. |
| B3: B2 + 범용 NLI/sufficiency (SURE-RAG 포함) | claim과 검색 문맥의 support/refute/insufficient 판단, 답변 보류/추가검색 | SURE-RAG의 sufficiency routing은 강한 선행 중첩이다. 일반 NLI는 시간 provenance, 권한, 실제 조치 정책을 그 자체로 보증하지 않는다. | 같은 evidence와 모델 조건에서 NLI/sufficiency만으로 해결되는 오류를 분리한다. B4가 이를 반복 구현하면 기능을 삭제한다. |
| B4: B3 + EIE | bitemporal provenance, claim-evidence conflict, policy/action-aware gate를 결합 | 조합이 신규 알고리즘이라는 증거 없음. 규칙/상태/추가 조회 비용만 늘고 성능이 같거나 나쁠 수 있음. | 시간 정정·상충과 허용/금지 조치가 결합된 사례에서 unsupported action risk를 줄이면서 정상 완료율을 보존하는지 검증한다. |

## 공정 비교 조건

비교는 같은 데이터/문서 split, actor 권한, 질문, 검색 후보군·검색기·top-k, LLM과 모델 버전, prompt, temperature/seed(가능한 경우), context/token budget, 허용 도구, coverage operating point에서 짝지어야 한다. B4가 추가하는 구조화 조회/검증 단계와 토큰·지연·API 비용은 모두 포함해 기록한다. 대조군별 서로 다른 검색 결과나 context budget을 쓰면 그 효과와 B4 효과를 분리할 수 없다. 실제 대조군을 구현하고 같은 설정으로 실행하기 전에는 우열·숫자·비용을 주장하지 않는다.

주요 결과는 같은 coverage에서 unsupported action risk와 정상 허용 업무의 safe completion을 함께 보고한다. 무조건 보류로 위험률을 낮추는 방법은 completion/coverage 하락으로 드러나야 한다. 시간 오류, 충돌 판정, 권한 위반, 잘못된 조치 제안은 유형별 분모와 사례 근거를 남긴다. 모델 판정만으로 gold를 확정하지 않는다.

## R1–R5와 중단 조건

- **R1 선행연구 중복:** B3/SURE-RAG가 필요한 sufficiency 기능을 이미 제공한다. B4는 `effective_at`과 `known_as_of`를 분리한 증거 재생 및 실행 정책 경계에서만 독립 효과를 주장할 수 있다. 일반 claim/NLI 분류 개선만 보이면 B4 차별성은 미입증이다.
- **R2 범위:** 단일 업무 흐름/도메인에 한정한다. 비교 실험 전에 새 모델·DB·그래프·agent 프레임워크를 추가하지 않는다.
- **R3 누수:** train/dev/holdout은 source family와 document revision family로 분리한다. 공개 benchmark 질문은 pretraining 오염 가능성을 고려해 비공개 holdout이라고 부르지 않는다. split 교차 발견 시 실험을 무효화한다.
- **R4 보류 편법:** risk는 동일 coverage에서 비교하며 safe task completion도 함께 공개한다. 위험 감소가 업무 완료율 급락에서만 나오면 실패다.
- **R5 벤치 부적합:** EnterpriseRAG-Bench는 enterprise RAG QA, FEVER는 Wikipedia claim verification, LongMemEval은 대화 기억, AgentDojo는 prompt injection, pgvector/LangGraph/GraphRAG는 각각 검색/오케스트레이션/그래프 기반 기술이다. 이들의 공개 점수는 B4 action safety나 bitemporal 성능으로 환산하거나 직접 비교하지 않는다. T1/T2/T3는 별도 보고한다.

**단순화 규칙:** 동일 조건에서 B4가 B2/B3보다 unsupported action risk를 낮추지 못하거나, 개선이 coverage·safe completion 저하 또는 비용 증가만으로 설명되거나, paired 불확실성이 개선을 뒷받침하지 못하면 B4 고유 복잡도(기록시각/충돌/게이트 중 효과 없는 부분)를 제거하거나 가장 단순한 우승 대조군으로 되돌아간다. 효과가 아직 측정되지 않았으므로 현재는 단순화 결론도 채택 결론도 내리지 않는다.

## 권리 확인 및 최소 평가 slice

저장소 코드 LICENSE는 각 데이터셋/문서/질문/가중치/호스팅 서비스 권리를 대신하지 않는다. EnterpriseRAG-Bench, FEVER, LongMemEval, AgentDojo의 데이터 자산 권리와 SURE-RAG 또는 평가 모델 weights 권리는 이 문서 작업에서 확인되지 않았다. 이용 전 필요한 결정은 자산별로 다음을 포함한다: (1) 연구/내부 평가 사용 권리, (2) 로컬 저장·파생 slice·정답/인용문 보관 허용 여부, (3) 재배포·공개 저장소·서비스 호스팅 조건, (4) 출처별 attribution 및 삭제 요구, (5) weights 다운로드/추론 권리 또는 유료 API 사용 비용 상한.

권리가 확인된 후 승인 범위 안에서만 첫 slice를 만든다: 출처 1종에서 최대 30개 사례, 원문은 필요한 평가 담당자만 접근, 각 사례에 공식 source ref·원문 위치·해시·rationale·labeler 기록, train/dev/holdout source-family 분리, 공개 데이터는 holdout 보호 주장 금지. 권리가 모호하면 데이터 대신 합성 사례를 사용하고 실제 출처라고 주장하지 않는다. 현재 승인된 자산은 특정되지 않았으며, 모델/API 비용은 미측정이므로 모델을 고르거나 호출하지 않았다.
