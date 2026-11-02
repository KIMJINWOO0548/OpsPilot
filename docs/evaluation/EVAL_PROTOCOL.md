# 평가 프로토콜 v1 · 실험 결과 없음

## A. 반드시 분리할 트랙
- **T0 smoke**: 현재 `SMOKE_ONLY_cases.jsonl` 8개. 작성자와 평가자가 같고, 합성 데이터이며 결정적 규칙으로 생성한 결과. **정확도·일반화·95점 근거 아님**.
- **T1 external enterprise retrieval**: EnterpriseRAG-Bench 공식 질문 500개. README의 500, 추가 metadata 100 등은 **각기 다른 평가 집합**임을 명시. 직접 최신 라이선스/커밋/정답 접근권한 확인 전 사용 금지.
- **T2 task-specific evidence**: 300 사례 목표(dev 120, 최종 holdout 180): temporal 60, revision conflict 70, retrospective knowledge 60, SQL/document cross-check 50, no-evidence/ACL 60. 실제/합성 출처 비율 기재, 출처별 group split, 주제별 독립 검토 필수. 개발 중 홀드아웃 라벨을 읽거나 알고리즘을 튜닝하면 무효.
- **T3 agent/runtime**: 승인/작업/중복/응답유실/프로세스 재시작/권한/공격 등 100+ 시나리오 및 별도 fault matrix. 자체 검증을 AgentDojo 리더보드 수치라고 포장하지 말 것.

## B. 사전 등록 4가설
1. H1: B4가 B2/B3 대비 근거 없는 조치율 상대 30% 이상 감소 목표.
2. H2: Coverage 70% 고정에서 risk 감소, 또는 동일 risk에서 Coverage 상승; 정상 업무 safe completion이 대조군 대비 5%p 초과 하락하지 않을 것.
3. H3: 결과 대비 지연/토큰/금전 비용 평가; P95 응답시간 증가 35% 이내는 도전 목표이지 검증된 제한이 아님.
4. H4: 정해진 권한/승인/중복 실행 테스트에서 누출/미승인/동일 요청 외부 write 중복 0.

## C. 지표의 엄격한 정의
- **Coverage** = action-eligible 질문 중 실제 action proposal을 생성한 수 / action-eligible 질문 수. 비적격 질문의 제안은 coverage에 더하지 않고 위험률에는 오류로 포함한다. 전체 proposal rate도 따로 보고한다. 판단 보류를 모두 선택하면 Coverage 0, 제안이 없을 때 risk는 0이 아닌 null이다.
- **Unsupported Action Rate @ matched coverage** = 제안된 작업 중 `(gold permitted action 아님 OR gold evidence로 지지되지 않음)` 수 / 제안된 작업 수. 다른 coverage끼리 raw risk 직접 비교 금지.
- **Risk–Coverage 곡선** = confidence threshold를 sweep하며 각 coverage에서 error fraction. confidence를 평가셋 결과에 사후 맞추면 안 됨. Calibration dev split에서 threshold 결정 → holdout에 고정 적용.
- **Safe Task Completion** = gold action이 존재하는 질문 중 올바른 요청 초안을 만든 비율.
- **Abstain leakage** = 금지된 조치에 답변하지 않음이 아니라, 별도로 금지된 근거를 외부에 노출하지 않았는지를 측정.
- **AURC** = coverage를 x축으로 한 risk curve 면적(적분법/threshold grid 공개). 현재 도구는 confidence 동점을 묶고 오른쪽 계단 적분으로 `aurc_partial`과 최대 도달 coverage를 함께 보고한다. 서로 다른 coverage 구간의 부분 면적을 직접 우열 비교하지 않는다.
- **Paired CI** = 동일 질문 쌍 B3↔B4의 bootstrap 95% CI. source family cluster가 독립 단위면 cluster bootstrap. n=300에서 작은 효과는 불확실할 수 있음.

## D. 강한 대조군/Baseline 구현 순서
- B0: lexical + template (측정)
- B1: Hybrid RAG same LLM / topK / context budget
- B2: B1 + temporal filter / latest authoritative doc (가장 중요한 저가 경쟁군)
- B3: B2 + NLI/sufficiency verification
- B4: B3 + bitemporal claim-evidence and action policy
- Ablation: B4 minus `recorded_at`; minus `supersedes`; minus SQL cross-check; minus conflict handling; minus action gate.
- SURE-RAG/GraphRAG 논문 공개 점수와 직접 숫자 비교 금지. 동일 실행 환경에서 재현 가능한 것만 비교.

## E. 누수 방지 프로세스
1. 문서/문서군/개정 계열·incident source별 `group_id` 지정. 질문 텍스트 단순 랜덤 분할 금지.
2. source SHA256, 문서 version, URL/다운로드 날짜, 사용 허가 기록. 중복·근접중복 감지.
3. label guideline 공개. 적어도 T2의 20%는 독립 2인 블라인드 검토하고 이견/일치도 기록. 검토자 없으면 미달이라고 표기.
4. dev에만 접근하여 rerank/threshold 튜닝. holdout 데이터 라벨은 봉인하여 최종 측정 전 열지 않음.
5. 주기적 실험 결과를 잘 얻었다고 threshold를 계속 바꾸지 않음. 변경 시 `experiments/manifest.json` 등록.
6. LLM judge는 보조 판정만; deterministic gold/원문 대조, 사람 검토로 교차 확인.

## F. 실험 매니페스트 템플릿
```json
{
  "experiment_id": "EXPERIMENT_NOT_YET_RUN",
  "code_commit": null,
  "dataset_name": null,
  "dataset_commit": null,
  "source_sha256": null,
  "case_ids_sha256": null,
  "split": "dev|holdout",
  "model_id_and_revision": null,
  "embedding_id_and_revision": null,
  "retrieval_k": null,
  "temperature": null,
  "prompt_sha256": null,
  "hardware": null,
  "usd_cost_total": null,
  "wall_seconds": null,
  "hypothesis": "H1|H2|H3|H4"
}
```

**실험 보류/중단 조건:** 스모크 T0만 있는 경우 / data source-family cross-contamination / 판단 보류로 coverage 붕괴 / 실험 설정 누락 / 남의 논문 점수 직접 비교.

## G. D01 분할 검사기 입력 계약 (2026-10-19)

`scripts/check_split_integrity.py`는 T2의 JSONL manifest 한 파일을 검사한다. 각 행은 객체이며 아래 필드가 필요하다.

| 필드 | 계약 |
|---|---|
| `case_id` | 비어 있지 않고 앞뒤 공백이 없는 문자열. manifest 전체에서 고유 |
| `split` | `train`, `dev`, `holdout` 중 하나 |
| `source_group_id` | 비어 있지 않고 앞뒤 공백이 없는 문자열. 동일 출처군은 한 split에만 배치 |
| `document_revision_family` | 같은 문서의 개정 계열 식별자. 동일한 문자열 규칙, 한 split에만 배치 |
| `source_hash` | 원문 바이트의 SHA256을 표현한 64자리 16진수. 비교할 때 대소문자를 구별하지 않으며 한 split에만 배치 |

빈 manifest, 비객체 행, 잘못된 필드, 중복 case ID, 세 출처 키 각각의 split 교차는 실패한다. 식별자 앞뒤 공백은 자동 수정하지 않고 거부한다. 빈 줄은 무시하며 잘못된 JSON은 파일명과 실제 줄 번호를 출력한다. 파일 접근·디코딩 실패도 PASS 없이 오류로 종료한다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_split_integrity.py -q
.\.venv\Scripts\python.exe scripts/check_split_integrity.py <T2_manifest.jsonl>
```

이 검사는 제출된 metadata의 일관성만 확인한다. 원문과 해시 일치, 출처군 식별의 정확성, 근접 중복, 데이터 라이선스, 정해진 표본 수·분할 비율, 독립 라벨 검토, holdout 봉인은 검증하지 않는다. 합성 T0 스모크 파일을 이 검사에 통과시키려고 평가 데이터로 재분류하지 않는다. D01/G1은 계속 부분 구현이다.

## H. G1 실행 경로 (2026-10-20)

G절은 독립 metadata checker의 범위다. 추가된 `evaluation_data.load_dataset`은 아래 검증을 평가 실행 전에 수행한다.

- T2 dataset manifest와 `contract_only`/`research` 구분, 원문 SHA256, 문서군·개정군·동일 hash split 교차.
- manifest 디렉터리 밖의 경로와 심볼릭 링크 탈출 거부. UTF-8 원문 NFKC/casefold/공백 정규화 및 5-token shingle Jaccard >=0.8의 split 교차를 거부한다. 규칙은 사전 고정된 휴리스틱이며 누수 완전 검출을 보증하지 않는다. 현재는 pairwise라 대규모 색인 전환이 필요하다.
- 각 split은 서로 다른 label 파일·SHA256·case ID 목록을 갖는다. metadata에서 모든 split의 case ID 교차를 검사하고 선택한 split label의 실제 ID 목록을 대조한다. dev에서는 holdout label 파일을 읽지 않는다.
- timestamp timezone·반열림 interval, SUPPORTED/CONFLICT gold 근거의 ACL·관측 시점·유효 시점, action/status 일관성을 검증한다. 합성 정답의 의미와 원문 entailment를 자동 인증하지 않는다.
- prediction은 전체 case ID가 정확히 일치해야 한다. action 일치뿐 아니라 완전한 gold 근거 집합·허용된 현재 인용이 필요하다. abstain에 비인가 인용이 있어도 누출 건수를 별도 계수한다.

`eval_compare.py`는 같은 모델·버전·provider·temperature·prompt hash·retrieval K·context budget·hardware 조건의 저장된 prediction을 비교한다. 제출 cost와 spend limit을 검증하고, code/dataset commit과 실제 scorer 파일 SHA256을 기록한다. cost/latency 입력은 제출값이며 이 도구가 모델을 실행하거나 과금 내역을 검증하지 않는다.

dev calibration은 confidence만 사용하며 목표 이상의 최소 실제 coverage를 고른다. 동점을 나눠 정확히 70%인 것처럼 꾸미지 않고 overrun을 기록한다. holdout에서는 모든 baseline의 유효한 dev threshold·dataset/scorer/조건 hash를 **label loader 호출 전에** 검사하고 재보정하지 않는다. holdout coverage가 목표에 미달하거나 실제 coverage가 서로 다르면 primary risk 비교를 보류한다.

paired bootstrap은 source group을 독립 cluster로 복원 추출하며 같은 질문 쌍을 유지한다. 방향은 right-left, 기본 1,000회/seed 고정/percentile 95% CI다. 독립 group이 2개 미만이거나 risk가 정의되지 않는 resample이 하나라도 있으면 CI를 null로 두고 표본 수를 보고한다. CI만으로 독립 검토·충분한 표본 수·통계적 타당성을 선언하지 않는다.

[실행 명세](EXPERIMENT_RUNBOOK.md), [라벨 기준](LABEL_GUIDELINE.md), [합성 계약 예시](../../evaluation/examples/contract_v1/README.md) 참조. 지금은 B0/B2 슬롯의 입력 fixture만 있으며 실제 B0/B1/B2/B3/B4 모델 비교·개선율은 미측정이다.
