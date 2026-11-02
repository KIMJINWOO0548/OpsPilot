# G1 오프라인 평가 실행 명세

## 즉시 재현하는 계약 검사

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/eval_compare.py evaluation/examples/contract_v1/experiment.json
```

이 예시는 합성 원문 15개와 작성자 라벨 30개를 사용한다. 모든 보류와 정답 복사라는 입력 fixture 두 개를 채점한다. **B0/B2 검색기나 AI 알고리즘을 실행하지 않는다.** 출력의 `CONTRACT_CHECK_NOT_BENCHMARK`, `research_performance_claim_allowed=false`, missing B1/B3/B4를 유지한다. 계약 수치로 정확도·개선율·95점·산업 성능을 홍보하지 않는다.

새 파일로 결과를 보관하려면 다음 옵션을 사용한다. 기존 파일은 덮어쓰지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/eval_compare.py evaluation/examples/contract_v1/experiment.json --output evaluation/reports/contract-check.json --calibration-out evaluation/reports/dev-calibration.json
```

## 입력 계약

| 파일 | 필수 정보 |
|---|---|
| dataset manifest | schema_version=1, dataset_id, track=T2, purpose, label_review, sources, split별 path/SHA256/case_ids |
| source metadata | ID, source/revision family, split, 로컬 path/hash, source_ref/license/synthetic, tenant/team/roles, valid_from/valid_to/recorded_at |
| label JSONL | case_id, question, actor_scope, effective_at/known_as_of, source_ids/gold_evidence_ids, expected_state/permitted_action/gold_reason, annotator_id/review_status |
| prediction JSONL | case_id, action(null=abstain), evidence_ids, confidence(유한 0..1) |
| experiment manifest | schema_version, experiment_id, split, dataset path/hash/commit, code_commit, seed, target_coverage, bootstrap_iterations, spend_limit_usd, baselines |
| baseline | predictions path/hash, conditions, implementation_status(fixture/implemented), wall_seconds, usd_cost_total |
| conditions | provider, model_id/revision, temperature, prompt_sha256(null은 fixture만), retrieval_k, context_budget_tokens, hardware |

모든 상대 path는 해당 manifest 디렉터리에 갇혀야 한다. case와 source group은 따로 ID를 갖는다. 같은 사건의 반복 질문을 독립 표본으로 세지 않도록 case의 source들은 동일한 bootstrap group에 속해야 한다. 복수 source group을 연결해야 하는 사건은 상위 incident family를 미리 정의해야 한다.

## dev → holdout

1. 데이터 담당자가 출처군별로 split을 배정하고 원문·label snapshot SHA256과 ID 목록을 고정한다. 공개 benchmark의 공개 정답을 비공개 holdout이라고 부르지 않는다.
2. 실제 알고리즘 prediction을 dev에서만 만들고 같은 조건으로 채점한다. threshold는 dev에서 저장한다. 목표 도달 실패도 기록한다.
3. 최종 평가 담당자가 같은 dataset manifest와 scorer 코드에 대해 holdout prediction을 작성한다. experiment의 split=holdout, calibration={path,sha256}을 지정한다.
4. `--allow-holdout`을 명시한 최종 실행에서만 해당 label을 읽는다. 미도달/변조/NaN threshold, 다른 조건·source/scorer hash는 label 접근 전에 거부한다. 이 옵션은 OS 파일 권한이나 독립 평가자를 대체하지 않는다.
5. 실제 holdout coverage와 목표 차이를 보고한다. dev와 달라졌다고 holdout에서 threshold를 다시 선택하지 않는다. coverage가 서로 다르면 primary risk 비교를 보류한다.

## 아직 없어서 연구 완료를 막는 것

- 실제 B0 lexical/B1 hybrid/B2 temporal/B3 NLI/B4 EIE 모델 실행과 같은 retrieval/context 조건의 비교.
- 권리 확인된 외부/실자료와 독립 사람이 검토한 T2 정답 및 봉인된 최종 holdout.
- 실제 code/dataset commit을 가진 연구 실행, 모델·prompt 버전, 인덱스/검증 단계까지 포함한 실측 비용·지연.
- source group 지정의 독립 검토, 다중 근거 entailment 검증, near-duplicate 휴리스틱의 false positive/negative 검토.

현재 `.git`이 없어 code commit은 null이고, 합성 계약 출력만 가능하다. G0/G1 공식 수용과 G2 이후 연구 확대는 별도 근거가 필요하다.
