# OpsPilot-X · 근거 검증 운영 콘솔

**문서의 권한·유효 시점·충돌을 검증하고, 독립 승인 후 mock 작업을 실행하는 운영 콘솔입니다.**

SK이노베이션 AI/DT Engineer 및 대기업 AI·SW 엔지니어링 포트폴리오 프로젝트로 개발하고 있습니다. '95점 수준의 외부 검증 가능한 결과'는 개발 목표이며 현재 성취 점수가 아닙니다.

서버 계정 로그인 → 권한 있는 문서 검색 → 유효/관측 시점 판정 → 독립 승인 → mock 실행·영수증 복구를 React/TypeScript 콘솔과 FastAPI에서 수행합니다. 계정·세션·근거 ACL·초안·감사는 SQLite에 저장합니다. [설계 결정](docs/decisions/ADR-003-SECURE-CONSOLE.md), [실행·배포 안내](docs/DEPLOYMENT.md).

> **배포 준비 중인 단일 인스턴스 포트폴리오 앱**입니다. 실제 LLM, Hybrid RAG, NLI, PostgreSQL/pgvector, LangGraph, OIDC, 외부 벤치마크는 아직 없습니다. 합성 근거와 결정적 정책을 사용하며 실제 작업은 mock입니다. G0/G1 연구 수용·외부 배포 검증·95점 달성을 선언하지 않습니다. 기본 접속은 loopback으로 제한합니다.

개발 순서와 안전 경계는 [시작 안내](START_HERE.md)를 확인하세요.

## 프로젝트 구성

| 파일/폴더 | 목적 | 상태 |
|---|---|---|
| `docs/reference/Plan_v2.0.md` / `.docx` | 전체 95점 목표 계획서 원본 | 포함 |
| `docs/TASK_BOARD.md` | 단계별 의존성/작업·검증 기준 | 완성 |
| `docs/architecture/EIE_CONTRACT.md` | 시간·권한·증거 모델/결정 상태 규칙 | 첫 계약 |
| `docs/evaluation/EVAL_PROTOCOL.md` | 외부/내부 분리 평가, 누수 방지, 통계 절차 | 규격 |
| `src/opspilot_x` | FastAPI + 결정적 근거 검증 + 가상 승인·작업 | **로컬 작동** |
| `web/src/` | React/TypeScript 조사·근거 타임라인·승인함·로그인 | **API 연결 구현** |
| `src/opspilot_x/auth.py` / `evidence_store.py` | 서버 identity/session, SQL ACL·관측 시점 선필터 | **로컬 구현** |
| `Dockerfile` / `docker-compose.yml` | UI 빌드·non-root·영속 volume·healthcheck | **로컬 Linux build/run·HTTP 검증** |
| `scripts/manage_users.py` / `backup_db.py` | 계정 생성/비활성화·세션 폐기, 검증된 새 파일 백업/복원 | **임시 DB 검증** |
| `tests/` | 단위·통합·동시성 테스트 | **자동 실행** |
| `evaluation/datasets/SMOKE_ONLY_cases.jsonl` | 사전 작성한 8개 합성 스모크 케이스 | **벤치마크 아님** |
| `.github/workflows/ci.yml` | Linux CI 정적분석/스모크 테스트 | 템플릿; 실제 GitHub 실행 전 |

## Windows에서 실행

저장소를 clone하거나 ZIP을 전체 압축 해제한 뒤, 저장소 루트에서 실행합니다. Python 3.12, Node.js 24, pnpm 11이 필요합니다. PowerShell에서 `./RUN_WINDOWS.ps1` 또는 아래 명령을 사용합니다.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements-runtime.lock -e ".[dev]"
Push-Location web
pnpm install --frozen-lockfile
pnpm build
Pop-Location
.\.venv\Scripts\python.exe scripts/manage_users.py --username engineer --tenant demo --team team_a --role engineer
.\.venv\Scripts\python.exe scripts/manage_users.py --username reviewer --tenant demo --team team_a --role approver
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\smoke_demo.py
.\.venv\Scripts\python.exe -m uvicorn opspilot_x.api:app --host 127.0.0.1 --port 8000
```

Python 3.12, Node.js 24, pnpm 11을 사용합니다. 관리 CLI에서 계정별 비밀번호를 입력하고 **http://127.0.0.1:8000**에 로그인하세요. 기본 계정·공개 가입은 없습니다. engineer로 A-103을 분석해 초안을 만들고 로그아웃한 뒤 reviewer로 승인·mock 응답 유실·영수증 복구를 시연합니다. 과거 시점의 분석은 읽기 전용입니다. 자세한 설정·계정 생성·한계는 [배포 안내](docs/DEPLOYMENT.md)에 있습니다.

> PowerShell 실행 정책으로 `.ps1`이 차단되면 스크립트 대신 위 명령을 한 줄씩 실행하세요. 실제 인증 우회용으로 실행 정책을 변경할 필요가 없습니다.

## Mac / Linux

```bash
bash RUN_MAC_LINUX.sh
```

Docker 실행과 volume 내 계정 생성은 [배포 안내](docs/DEPLOYMENT.md)를 따릅니다. 호스트 공개 주소는 기본 `127.0.0.1`이며 HTTPS ingress·기업 인증·Postgres/outbox·외부 보안 검증은 후속 작업입니다. SQLite를 기업 운영 검증이 끝난 저장소라고 표현하지 않습니다.

## 검증 기록

2026-11-02 격리 사본: 제안 상세·승인·최초 실행을 현재 검토자의 문서 ACL로 재검증하도록 수정했습니다. 새 회귀3실패/5통과→8통과, 전체 Windows pytest167통과입니다. 과거10014는 이번 일반 Windows 검사에서 재현되지 않았으며 WPF·설치기·출시 수용은 별도입니다. [수정·검증과 한계](docs/safety/REVIEWER_EVIDENCE_ACL_2026-11-02.md). 원본·사용자 DB는 보존했습니다. 자체 코드의 라이선스는 아직 지정하지 않았으며 외부 모델·실제 회사 자료는 포함하지 않습니다.

2026-10-20 개발: [8종 원천 검토](docs/research/prior_art_matrix.csv), [G1 원문·분할·holdout 및 평가 CLI](docs/evaluation/EXPERIMENT_RUNBOOK.md), [30개 합성 라벨 예시](evaluation/examples/contract_v1/README.md)를 추가했습니다. 저장된 prediction을 비교하는 도구이며 실제 B0~B4 모델 실행·외부 성능 검증은 아직 없습니다.

2026-10-23 현재: Compose 서비스는 **Healthy**이고, 같은 이미지의 임시 DB에서 실제 Chrome으로 로그인→현재 근거·타임라인→작성자 승인 잠금→독립 승인→mock 응답 유실·영수증 복구를 확인했습니다. 엔지니어 권한의 충돌·과거 분석도 초안을 차단했습니다. [화면과 QA](docs/design/CONSOLE_QA.md)를 확인하세요. 검증용 계정·컨테이너는 정리했고 서비스 volume은 변경하지 않았습니다.

동일 코드의 10월 22일 Linux 검사는 **133개 통과**와 두 스모크 통과였습니다. 10월 23일 Windows 재검사는 **120 통과 / 2 실패 / 11 오류**이며 13건 모두 WinError 10014를 포함합니다. 사용자의 재부팅 완료 보고와 달리 진단 환경의 커널 부팅 시각은 10월 21일로 표시돼 재시작 범위를 확인 중입니다. Windows 소켓 원인·Desktop 종료 원인·장기 실행 안정성은 미해결입니다. Linux 통과와 Chrome 검증을 공개 배포 수용이나 Windows 오류 해결로 해석하지 않습니다.

## 검증 명령

```bash
python scripts/check_package.py
pytest -q
python scripts/smoke_demo.py
python scripts/eval_smoke.py --output evaluation/reports/local_smoke.json
python scripts/eval_compare.py evaluation/examples/contract_v1/experiment.json
```

`eval_smoke.py`는 **사용자가 작성한 합성 케이스와 규칙의 일치성**만 점검합니다. `eval_compare.py`의 제공 예시도 모든 보류/정답 복사 입력의 계약 검사입니다. 두 결과 모두 외부 정답 데이터에 대한 정확도나 연구 결과가 아닙니다.

## 지원하는 데모 시나리오

- 문서 개정 시 현재/과거 유효한 SOP 구별 (`valid_from` / `valid_to` + `recorded_at`)
- 나중에 기록된 소급 정정이 당시 판단에 누설되지 않는 시간여행 질의
- 승인된 SOP 사이의 충돌 탐지 및 작업 제안 거부
- 권한이 없는 문서의 원문/ID를 API 결과에 노출하지 않는 규칙
- 인젝션 텍스트를 명령으로 해석하지 않는 결정적 엔진
- 승인 전 실제 mock 작업 생성 차단
- 동시 승인·재실행 시 고유한 가상 작업 영수증 유지
- mock 응답 유실 후 영수증 확인으로 상태 복구

이 항목은 **제한된 합성 테스트 범위의 동작**입니다. API는 서버 세션의 role/tenant/team만 사용하고 본문의 actor는 권한을 바꾸지 못합니다. 검색 후보는 SQL에서 권한·관측 시점으로 선필터됩니다. 외부 API와 분산 트랜잭션 경계는 테스트하지 않습니다.

## 중요한 경계

- 현재 판단기는 **결정적 EIE 규칙**입니다. 문서 검색은 허용된 후보의 단순 lexical overlap입니다. LLM·임베딩·NLI·Hybrid RAG나 실제 B0~B4 실험이 구현된 것처럼 설명하지 않습니다.
- **외부 테스트 데이터는 포함하지 않습니다.** EnterpriseRAG-Bench 등은 라이선스·분할·체크섬 검증 후 사용자 명령으로만 받아야 합니다.
- G0(선행연구/라이선스)와 G1(데이터 계약/평가 분할)을 통과하지 않고 B4 성능 우위를 주장할 수 없습니다.
- 장비·정유 공정 원격 제어, 실회사 문서, 고객 정보, 실 API 자격증명은 절대로 연결하지 않습니다.

## 개발 로드맵

`G0 선행연구 잠금 → G1 평가 계약 → G2 E2E 바닥 코드 강화 → G3 EIE 알고리즘 → G4 공정 비교 실험 → G5 실행 신뢰성 → G6 UI/성능 → G7 외부 검증 → G8 제출 패키지`

현재 `G2`에는 통과 가능한 **축소 실험 스캐폴딩**이 들어 있지만, G0/G1 공식 완료·G2 최종 완료로 표시하지 않습니다. `docs/TASK_BOARD.md`의 Gate 체크리스트와 `docs/GATE_STATUS.md`를 참조하세요.

## 개발 원칙과 라이선스

평가셋 보호·기술 선택 이유·실패 원인·실측 데이터·코드 라이선스를 검토하고 설명할 수 있도록 기록합니다. 검증되지 않은 기술 독창성, 외부 수상·공헌, 목표 점수 달성을 주장하지 않습니다. 기여 시 [개발 규칙](AGENTS.md)을 참고하세요.

자체 코드의 라이선스는 아직 지정하지 않았습니다. 외부 모델·실제 회사 자료는 포함하지 않습니다.
