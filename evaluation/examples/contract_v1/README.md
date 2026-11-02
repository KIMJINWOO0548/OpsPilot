# 작성자 합성 계약 예시 30개 — 연구 평가 데이터 아님

5개 가상 문서군 × 6개 시점/권한/충돌 변형이다. **독립 사례 30개 또는 제삼자가 검증한 정답 30개가 아니다.** 단위·CLI 계약 점검과 사람이 검토할 라벨 예시를 위해 AI가 작성했다. 실제 제조 절차로 사용하지 않는다.

- `sources/`: 직접 작성한 원문 15개. 각 문서군 v1·소급 정정 v2·추가 충돌 지시.
- `manifest.json`: 원문 hash·split·ACL·valid/recorded time·출처. `purpose=contract_only`, `label_review=author_only`, **dev만 존재**한다. blind holdout을 만들었다고 주장하지 않는다.
- `dev.jsonl`: 질문·actor·두 시점·gold ID·상태·허용 조치·rationale·작성자. 수동 독립 검토가 필요하다.
- `abstain-control.jsonl`: 모든 요청을 보류하는 입력 fixture.
- `gold-alignment-control.jsonl`: 정답을 그대로 옮겨 쓴 입력 fixture. 모델 예측이 아니다.
- `experiment.json`: 파서의 B0/B2 슬롯에 위 두 fixture를 넣은 **배선 점검**. B0 검색기나 B2 모델을 구현/실험했다는 뜻이 아니다. B1/B3/B4는 없다.

```powershell
.\.venv\Scripts\python.exe scripts/eval_compare.py evaluation/examples/contract_v1/experiment.json
```

출력은 `CONTRACT_CHECK_NOT_BENCHMARK`다. 여기서 계산된 coverage·risk·CI는 산술/경로 검증 결과이며 포트폴리오 성능표·개선율에 넣지 않는다. `wall_seconds=0`, `usd_cost_total=0`은 추론을 실행하지 않은 입력 fixture의 표기다.

선택적으로 `--calibration-out <새 파일>`과 `--output <새 파일>`로 저장할 수 있다. 기존 파일은 덮어쓰지 않는다. holdout 평가를 하려면 다른 source family의 원문과 별도 label 파일, 독립 라벨 검토, dev에서 저장한 calibration artifact가 필요하다. 로컬 파일 접근 통제는 별도로 필요하며 이 CLI가 독립 평가자 역할을 대신하지 않는다.
