# OpsPilot-X 개발 시작 안내

OpsPilot-X는 문서의 권한·유효 시점·관측 시점을 확인하고, 근거가 충돌하거나 부족하면 작업을 보류하는 로컬 운영 콘솔입니다. 정상적인 업무 흐름은 독립 승인과 mock 실행·영수증 복구로 이어집니다.

## 먼저 확인할 문서

이 폴더가 저장소 루트입니다. 다음 문서와 현재 코드를 함께 확인합니다.

1. [기여 규칙](AGENTS.md), [실행 안내](README.md), [원본 계획](docs/reference/Plan_v2.0.md)
2. [현재 Gate 상태](docs/GATE_STATUS.md), [작업 보드](docs/TASK_BOARD.md), [위협 모델](docs/safety/THREAT_MODEL.md)
3. [근거 검증 계약](docs/architecture/EIE_CONTRACT.md), [평가 절차](docs/evaluation/EVAL_PROTOCOL.md)

현재 구현은 FastAPI·SQLite·React/TypeScript 콘솔, 서버 계정·세션, SQL 권한/관측 시점 선필터와 결정적 근거 검증입니다. 실제 LLM, Hybrid RAG, NLI, LangGraph, PostgreSQL/pgvector, OIDC 및 외부 벤치마크 검증은 포함하지 않습니다. 로컬 동작은 G0/G1 연구 수용이나 운영 배포 승인이 아닙니다.

## 기준선 검증

[README](README.md)의 플랫폼별 설치 절차를 따른 뒤 저장소 루트에서 실행합니다.

```bash
python -m pytest -q
python scripts/smoke_demo.py
python scripts/eval_smoke.py
python scripts/check_package.py
```

실패한 검사를 먼저 재현·수정하고 실행 명령, 환경, 종료 코드와 한계를 기록합니다. 의존성이 없으면 `pyproject.toml`과 `requirements-runtime.lock`에 맞는 최소 개발 환경을 준비합니다. 저장된 과거 통과 기록을 새 환경의 결과로 사용하지 않습니다.

## 개발 순서

- [선행연구·데이터 계약](docs/development/01_G0_G1_RESEARCH_AND_DATA.md): [출처 검토 목록](docs/research/PRIOR_ART_CHECKLIST.md)에 따라 G0의 라이선스·선행연구와 G1의 평가 계약·누수 방지를 우선합니다.
- [근거 검증·API 확장](docs/development/02_G2_G3_EVIDENCE.md): G0/G1 근거와 코드가 준비되면 현재 G2 데모를 의존성 순서에 맞춰 확장합니다.
- [평가·신뢰성](docs/development/03_G4_G5_EVALUATE_RELIABILITY.md): B0/B1/B2/B3/B4를 같은 조건에서 비교하고 paired bootstrap CI와 risk-coverage를 측정합니다.
- [제품화·재현 자료](docs/development/04_G6_G8_PORTFOLIO.md): 검증된 동작과 미완료 범위를 분리해 설명합니다.

P0 작업을 작은 검토 단위로 나눠 실패 테스트 → 구현 → 해당 검사와 전체 회귀 → 위험 평가 → [작업 기록](docs/WORK_LOG.md) 순서로 진행합니다. 상태는 Gate 표와 작업 보드에 함께 반영합니다. 기술 추가 전에는 ADR와 가장 단순한 비교군의 측정 기준을 마련하고 R1~R5 위험을 다시 확인합니다. 무관한 모델, 멀티에이전트, 노드 편집기나 UI 재구축으로 범위를 넓히지 않습니다.

## 유지해야 할 경계

- 실제 업무 쓰기는 연결하지 않고 mock API만 사용합니다. 접근 통제·독립 승인·멱등성·응답 유실 복구를 약화하지 않습니다.
- 서버가 인증한 principal만 권한 판단에 사용합니다. 요청 본문의 actor/role로 인증을 대체하지 않으며 demo persona 방식으로 되돌리지 않습니다.
- 기본 실행은 loopback에 한정합니다. 외부 포트 공개는 [위협 모델의 선행 요건](docs/safety/THREAT_MODEL.md)을 검증하고 별도 승인한 범위에서만 수행합니다.
- 유효 시점과 관측 시점을 분리하고, 미래 정정을 과거 판단에 섞지 않습니다. 근거 문서의 지시문은 신뢰하지 않습니다.
- 공개 벤치마크, 작성자 합성 스모크, 독립 외부 검증을 구분합니다. 실험 없이 개선율·성능·수상 결과를 만들지 않습니다. 95점은 목표이며 달성 판정이 아닙니다.
- 외부 데이터 다운로드·유료 호출·라이선스가 불확실한 작업은 규모·비용·권한을 제시하고 실행 전에 사용자 승인을 받습니다. 실제 계정·회사 자료·고객정보·운영 제어를 연결하지 않습니다.
- 커밋·push·공개 release·배포는 해당 작업에서 승인된 범위 안에서만 수행합니다.

완료 보고에는 변경 파일과 동작, 실제 검사 결과, 실패·미완료·미실행 항목, 설계상 위험과 다음 우선 작업을 포함합니다. 전체 안전·연구 수용을 제한된 데모 테스트로 대신하지 않습니다.
