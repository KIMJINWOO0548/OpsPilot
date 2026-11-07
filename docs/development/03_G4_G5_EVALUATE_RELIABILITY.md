# 평가와 신뢰성 검증 · G4/G5

1. T1 official 500(별도 metadata 100 구분), T2 독립 검토 대상, T3 fault matrix를 다른 폴더와 별도 manifest로 분리.
2. 같은 case ID·모델·retrieval K·토큰·시드에서 B2↔B3↔B4 실행. Primary metric: unsupported action rate @ Coverage 70%, safe completion, risk-coverage, AURC, paired bootstrap CI.
3. 임계값은 dev split에서만 고정. holdout 결과를 기반으로 prompt/threshold를 수정하면 blind 속성을 상실했음을 기록.
4. 연구 실패/타임아웃/편향/labeler 이견/라이선스 문제를 보고서에 빠짐없이 기록.
5. 승인 원장과 remote mock 업무 서버를 분리하고 outbox/idempotency receipt 조회 구현. process kill, HTTP timeout, 429/500, concurrent replay fault harness 작성.
6. JWT/RLS/least privilege/ACL prefilter/secret redaction/attack fixtures 확인. 하나라도 위반하면 release blocker.
7. 외부 평가자가 같은 실험을 실행할 수 있는 버전 고정·단일 CLI·기대 출력 형식·실험 비용 안내 생성.

완료 조건: 결과 표/CI/하위 유형 분모·실패 사례 및 fault trace 공개. 결과가 불리하면 사실대로 기록하고 가설 폐기/개선 여부 평가.
