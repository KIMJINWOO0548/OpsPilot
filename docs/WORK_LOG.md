# Dev / Research Work Log

## 2026-11-02 — Windows smoke 출력 인코딩

후속 공개 CI에서 Linux·컨테이너와 Windows 전체 pytest는 통과했으나 Windows smoke의 성공 메시지 화살표가 cp1252 stdout에서 `UnicodeEncodeError`를 냈다. 같은 cp1252 환경의 임시 DB smoke로 실패를 재현한 뒤 출력 구분자만 ASCII로 바꾸고 재검증했다. API·승인·실행·검증 조건과 시스템 인코딩 설정은 변경하지 않았다.

## 2026-11-02 — 공개 CI의 평가 예제 바이트 보존

첫 공개 CI의 Linux pytest·mock smoke·웹 빌드·컨테이너 검사는 통과했으나 평가 CLI가 `SHA256 mismatch: manifest.json`으로 실패했다. Windows matrix는 그 실패로 취소됐으며 pip 결함으로 단정하지 않는다. 기존 Windows fixture는 CRLF 바이트로 해시가 고정돼 있었지만 Git 정규화 blob은 LF였다. LF 체크아웃 export에서 같은 실패를 재현하고 `.gitattributes`로 평가 예제의 원본 바이트를 보존했다. 예제20개 파일은 줄바꿈 외 내용 변경0이며, 수정한 새 LF 체크아웃 export의 평가 CLI가 통과했다. 검증 로직·해시·라벨을 완화하거나 재작성하지 않았다. 후속 GitHub Actions 결과는 해당 커밋의 CI를 따른다.

## 2026-11-02 — 현재 검토자의 문서 ACL

원본 제품/실제 DB를 보존한 격리 사본에서 제안 상세·승인·최초 실행의 작성자 ACL 재사용을 수정했다. 새 회귀3실패/5통과→8통과, 전체 pytest159→167통과. Ruff, mock smoke, 합성8개, eval_compare 계약 예제, 필수24파일 검사 통과. 일반 Windows 검사에서 과거10014는 재현되지 않았다. 샌드박스 임시폴더/소켓 실패는 별도 기록하며 보안 설정은 바꾸지 않았다. [실행 명령·증거·제약](safety/REVIEWER_EVIDENCE_ACL_2026-11-02.md). 처음에는 Git identity 부재로 tree를 보존했고, 후속 승인으로 확인된 기존 GitHub noreply 작성자를 저장소 로컬에만 사용해 기준선/수정 커밋을 분리한다. 사용자 공개 승인은 OpsPilot GitHub 소스에 한정되며 앱 배포는 하지 않는다.

| 날짜 | 작업 | 명령 및 결과 | 한계/다음 단계 |
|---|---|---|---|
| 2026-10-19 | AI 구현 킷 생성: 결정적 EIE+FastAPI+SQLite(mock), 합성 타임라인, 승인·멱등성, 브라우저 시연 | `pytest -q`: 23 passed; `smoke_demo.py`: E2E pass; `eval_smoke.py`: 합성 8/8 (외부 평가 아님) | 실제 학습모델/Hybrid RAG/기업인증/외부평가 없음 |
| 2026-10-19 | Windows 개발 환경·수정 전 기준선 | 기본 `python` 3명령 exit 1: WindowsApps 별칭. bundled Python에는 pytest/FastAPI/설치된 프로젝트가 없어 실패. bundled Python으로 `.venv` 생성 후 `-m pip install -e '.[dev]'`. `.venv/Scripts/python.exe -m pytest -q`: 23 passed/1 warning; `scripts/eval_smoke.py`: 합성 8/8, exit 0; `scripts/smoke_demo.py`: 흐름 PASS 뒤 임시 DB 정리 WinError32, exit 1 | 새 직접 의존성 추가 없음. `.git` 없는 압축 해제 디렉터리로 code commit 미확보 |
| 2026-10-19 | G0 R00 1차 출처 검증 | EnterpriseRAG-Bench, AgentDojo, LangGraph의 공식 설명·GitHub API commit·코드 LICENSE를 [기록](research/PRIOR_ART_REVIEW.md). 원문 arXiv v3와 대조해 AgentDojo의 잘못된 학회 표기를 수정 | 데이터 다운로드·baseline 실행 없음. 데이터 이용 권리·독창성·성능은 미검증. G0 부분 검토 |
| 2026-10-19 | G1 D01 manifest 경계 강화 | `tests/test_split_integrity.py`: 최초 새 테스트 4 failed/3 passed → 구현 후 9 passed. 독립 리뷰의 앞뒤 공백 우회는 회귀 테스트 1 failed로 재현 → 거부 추가 후 10 passed. 빈 입력/비객체/필드 타입/SHA256 형식·대소문자/각 출처 키 교차/CLI 실패·성공 검증 | 기존 가짜 hash fixture를 결정적 SHA256로 변경한 이유는 새 형식 계약을 검증하기 위함. 원문 일치·근접중복·실제 데이터·독립 라벨 미검증으로 G1 부분 유지 |
| 2026-10-19 | G2 Windows SQLite 연결 누수 해결 | `tests/test_api.py -q -k database_connections_close`: 2 failed → 공유 connection에 `closing`+기존 transaction context 적용 → 2 passed. 첫 수정 후 테스트의 다른 스레드 검사 오류를 확인하고 test-only `check_same_thread=False`로 연결 보유·검사를 일관되게 함. `scripts/smoke_demo.py`: 임시 DB 정리까지 exit 0 | 테스트를 제거하거나 정책·트랜잭션 조건을 완화하지 않음. 실제 인증/외부 exactly-once 보장은 없음 |
| 2026-10-19 | 플랫폼·디자인 작업 범위와 실제 화면 점검 | [ADR-001](decisions/ADR-001-PLATFORM-AND-DESIGN.md) 작성. Product Design으로 로컬 분석→초안→승인→응답 유실→복구 6단계 캡처·검토. [결과](design/LOCAL_DEMO_AUDIT.md). Figma 연결 확인, Canva 검색은 재인증 필요로 실패 | UI 재구축·이미지 생성·외부 디자인 업로드·배포 없음. Figma Code Layers 비활성. 접근성·작은 화면은 미검증 |
| 2026-10-19 | 전체 회귀·실패 원인 기록 | UTF-8 모드 전체 검사에서 CLI subprocess의 CP949/UTF-8 디코딩 불일치로 31 passed/1 failed. CLI 테스트의 자식 프로세스와 캡처를 UTF-8로 고정 후 전체 `-m pytest -q`: **32 passed, 1 warning**; `-X utf8 -m pytest tests/test_split_integrity.py -q`: 10 passed. mock E2E·합성 8/8·`ruff check src tests scripts`·`scripts/check_package.py`·`pip check` 성공 | Starlette/HTTPX deprecation warning 1개 유지. 의존성 잠금·Docker·실제 CI·실제 모델/벤치마크는 미검증. 성능/비용/점수 미측정. [검증 산출물](../verification/windows-2026-10-19.json) |

| 2026-10-20 | 중단 작업 복구·기준선 | 이전 중단이 남긴 `tests/test_evaluation_metrics.py`에 대응 모듈이 없어 `python -m pytest -q`는 collection error 1건. 기존 `python scripts/smoke_demo.py`, `python scripts/eval_smoke.py`는 exit 0(합성 8개 일치). 중단 전 32 tests 통과 기록과 구분 | 테스트를 지우지 않고 대응 구현을 완성. 명령의 python은 PowerShell 세션 PATH 앞에 기존 .venv/Scripts를 추가해 실행 |
| 2026-10-20 | R00/R01 공식 8종 검토 | [CSV](research/prior_art_matrix.csv) 8행에 commit·고정 LICENSE 원문/SPDX·코드 범위·문서 명령·AI-only 검토자·시각 기록. 8행·SHA 형식·필수필드 로컬 assertion 통과. [collision matrix](research/NOVELTY_COLLISION_MATRIX.md)로 B2/B3/B4 가설/R1~R5 재점검 | 코드 LICENSE를 data/weights 권리로 해석하지 않음. 명령 실행·모델 호출·데이터 다운로드 없음. G0 수용 보류 |
| 2026-10-20 | P0 평가 지표 단위 | `evaluation_metrics.py`/`test_evaluation_metrics.py`: module 부재 red → **41 passed**. bool/NaN/inf·중복·동점·비적격 제안·all-abstain·cluster pairing·순서/seed·undefined replicate 검증 | risk/coverage·부분 AURC·paired percentile CI 계산 코드만 구현. 실제 알고리즘 성능 미측정. 서로 다른 coverage 구간의 부분 AURC 비교 금지 |
| 2026-10-20 | D01 원문·시간·분할 경계 | `evaluation_data.py`+신규 테스트: 부재 red → 기존 split 검사 포함 22 passed. 공용 분할 함수를 `split_integrity.py`로 이동하고 기존 CLI의 check export 유지. 이후 잘못된 snapshot·split case ID 교차 5 failed를 재현 → 검증 추가 | SHA256·source/revision family·정규화/5-token 근접중복·ACL·두 시점·label 분리·path containment 검증. dev가 holdout label을 읽지 않는 정상 경로 확인. 근접중복은 O(n²) 휴리스틱, source family 의미·인용 entailment·권리는 사람 검토 필요 |
| 2026-10-20 | P0 저장 prediction 비교 CLI | `scripts/eval_compare.py` 초기 3 failed를 확인한 뒤 구현. action/gold 근거·조건/예산·case 완전 일치·dev calibration·matched coverage·제출 비용상한·output 덮어쓰기 차단. 비용상한 누락을 실패 테스트로 재현하고 복구. CLI와 데이터 focused 28 passed 기록 | B0/B2 슬롯은 모든 보류/정답 복사 입력 fixture. 실제 검색기/LLM/NLI/Hybrid 실행 아님. B1/B3/B4 미구현을 보고서에 명시 |
| 2026-10-20 | 독립 AI 코드 리뷰와 holdout 순서 보강 | reviewer가 calibration 미도달/NaN/잘못된 threshold 및 research commit 누락보다 먼저 loader가 호출됨을 P1로 지적. **5 failed** 회귀로 재현 → 엄격 Calibration 모델과 commit/조건/scorer 검증을 loader 앞에 이동 → CLI **11 passed**. 마지막으로 고정 threshold에서 holdout coverage가 0.5로 하락한 경우 primary 비교 허용 버그를 1 failed로 재현해 수정 | 실제 독립 holdout 자료를 열지 않았고 가상 파일/spy로 검증. CLI opt-in은 로컬 파일 관리자에 대한 보안 경계나 독립 평가자 인증이 아님 |
| 2026-10-20 | D02 라벨 예시와 실행 증빙 | [라벨 기준](evaluation/LABEL_GUIDELINE.md), [runbook](evaluation/EXPERIMENT_RUNBOOK.md), [ADR-002](decisions/ADR-002-EVALUATION-CONTRACT.md), [30개 작성자 합성 dev 예시](../evaluation/examples/contract_v1/README.md), CI Windows/Linux matrix·E2E·계약 CLI 단계 추가. [최종 계약 보고서](../verification/g1-contract-final-2026-10-20.json)의 scorer hash·abstain/비교 보류 flag assertion 통과 | 5개 합성 문서군/15개 원문에서 파생된 30변형이며 독립 30사례가 아님. 실제 사람 검토 0건. GitHub CI·Docker 미실행. [외부 자산 최소 범위 제안](research/DATA_ACQUISITION_PROPOSAL.md)만 작성 |
| 2026-10-20 | 전체 최종 검증 | `python -m pytest -q`: **101 passed, 1 warning**. `python scripts/smoke_demo.py`: E2E exit 0. `python scripts/eval_smoke.py`: 합성 8/8 exit 0(benchmark 아님). `python -m ruff check src tests scripts`, `python scripts/check_package.py`, `python -m pip check`: 통과. 신규 계약 CLI exit 0 | Starlette/HTTPX deprecation warning 1개. 새 의존성·API 과금·외부 업로드·데이터 다운로드 없음. `.git` 부재로 commit/실제 PR 없음. 실제 모델·외부 성능/비용·G0/G1 통과·최종 점수는 미측정/보류 |

### 2026-10-20 위험 재평가와 다음 작업

- R1 중복: 8종 검토와 B2/B3 collision 경계를 기록했으나 실제 대조군이 없어 미해소. 효과 없으면 복잡도를 버리는 조건 유지.
- R2 범위: 한 업무 문제의 데이터/평가 경로만 확장. UI·새 ML·멀티에이전트 제품 기능은 추가하지 않음. 코딩 작업의 AI 하위 에이전트는 제품 런타임과 구별.
- R3 누수: 실행 전 source/hash/group/ID/근접중복 guard와 holdout 순서 수정. 실제 독립 출처·검토·봉인 holdout은 미확보.
- R4 보류 편법: no-proposal risk=null, coverage=0·target 미도달·누출은 별도 기록. 목표 미달/서로 다른 실제 coverage에서 primary risk 비교 보류.
- R5 부적합: T0와 T2 contract/research를 구별하고 모든 계약 출력의 성능 주장 허용값은 false. 실제 외부 데이터 평가 없음.

다음은 원천별 데이터 권리 확인과 승인할 최소 slice의 확정, 독립 라벨 검토자·holdout 확보다. 이 근거가 준비된 뒤 가장 단순한 실제 lexical B0 및 서버 유도 identity/Auth를 순차 구현한다. 현재 폴더에는 .git이 없어 계획의 PR 단위를 로컬 코드/검증 기록으로 남겼고 commit을 만든 것처럼 보고하지 않았다.

**매 PR마다 추가할 항목:** 기술 가설 / 관련 issue / 변경 이유 / 코드 파일 / 수행 테스트 / 실패 추적 / benchmark manifest / 위험 영향 / next step.

## 2026-10-20~22 · 인증된 포트폴리오 콘솔 단위

사용자의 최신 “실제 배포를 전제로 프로그램/UI 구현” 지시에 따라 ADR-003과 구현 계획을 먼저 작성했다. 기존 UI 후행 순서의 변경이며 G0/G1 연구 완료를 의미하지 않는다. `.git`이 없으므로 아래 단위는 로컬 변경·검증 단위이며 commit/PR을 만든 것이 아니다.

| 단위 | 변경 파일·실제 결과 | 실패/검증과 위험 |
|---|---|---|
| A03 인증/API | `auth.py`, `api.py`, `scripts/manage_users.py`, `tests/conftest.py`, `test_api.py`, `test_auth.py`, `smoke_demo.py`. PBKDF2 600k·salt, session hash/expiry/logout·HttpOnly/SameSite·CSRF·시도 제한, DB principal, 객체 scope·목록·감사, 계정 명시 생성 | 초기 auth 동작을 구현 전 red로 실행하지 못했고 연결 모듈 부재 ImportError만 관측했다. 이 단위를 엄격한 TDD 완료로 주장하지 않는다. 기존 actor JSON 테스트는 명시적 실제 로그인으로 전환했고 정책을 낮추지 않았다. 회귀 18개와 전체 검사로 현재 동작을 검증했다. 계정 회수/비밀번호 변경·OIDC·분산 제한 미완료 |
| 근거 저장소 | `evidence_store.py`, `test_evidence_store.py`. immutable snapshot/체크섬, SQL tenant/team/role·known cutoff 전처리, 단순 lexical overlap, 두 시점 상태·관계 표시 | 모듈 부재 red → 첫 5 tests pass. 다른 asset이 supersedes하는 오류 1 failed → 동일 asset/claim으로 제한. hidden/future 관계 ID가 응답에 노출되는 오류 1 failed → 허용/관측 동일 scope 관계만 반환. 최종 7 tests pass. ranking 감시 테스트의 완전 일치 비교를 부분 문자열 검사로 강화. BM25/외부 B0 실험은 아님 |
| 안전 리뷰 수정 | `api.py`, `test_auth.py`. 시나리오 자산 ACL, write 객체 scope 404, query 1000자 422, 저장 action 재검증 | 독립 AI 리뷰가 action만 DB 변조해 approve/execute 200·잘못된 work order를 만들 수 있음을 재현. 실패 테스트 후 승인/실행에서 EXPIRED/409·write 0으로 수정. foreign write 403/404 존재 oracle도 red → scope 검사 선적용으로 수정. DB 전체 관리자 변조 방어·비밀키 전자서명까지 구현했다고 주장하지 않음 |
| UI01 | `web/package.json`, `pnpm-lock.yaml`, `tsconfig.json`, `vite.config.ts`, `index.html`, `src/{main.tsx,styles.css,helpers.ts,helpers.test.ts,vite-env.d.ts}`. 로그인·조사·타임라인·승인함·실제 API/cookie/CSRF, 한국어 상태·접힌 JSON·로딩/오류/빈 상태 | 원 승인자 실행/복구 helper 1 failed → 조건 보강. 과거 분석에서 활성 초안 버튼을 발견해 helper 미export red → 읽기 전용 guard·설명 추가. 현재 정상 입력은 버튼 활성 유지. **4 frontend tests**, typecheck/build exit 0. API 브라우저 핵심 경로와 작은 화면 DOM 검사, [QA](design/CONSOLE_QA.md). 모바일 캡처 축척 이상·정식 접근성 검증은 한계 |
| DEP01 | `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `.gitignore`, `requirements-runtime.lock`, `RUN_WINDOWS.ps1`, `RUN_MAC_LINUX.sh`, `.github/workflows/ci.yml`, `scripts/check_package.py` | non-root·read-only root·data volume·healthcheck·loopback, UI build/Python runtime 단위. static 경로를 OPSPILOT_WEB_DIR로 분리해 noneditable 설치 대응. Compose config exit 0. Docker Desktop daemon은 unable to start로 실제 build/run 못함. CI 설정을 실제 실행으로 계산하지 않음 |
| 문서·제출 설명 | README, ADR-003·계획, DEPLOYMENT, EIE_CONTRACT, THREAT_MODEL, THIRD_PARTY_NOTES, GATE_STATUS, TASK_BOARD, SCORECARD, PORTFOLIO_DEMO, QA·화면·검증 JSON | 구현/미구현·hash vs 서명·합성 vs 외부 평가 구분. 프런트 의존성은 20일 설치했고 이후 사용자 규칙 갱신 뒤 신규 설치/외부 업로드/유료 호출/외부 데이터 다운로드/공개 배포 없음. 실제 촬영 영상 없음 |

### 실행 증거와 실패 경과

- 시작 시 전체 baseline은 100 passed / 1 setup error(WinError 10014)였다. 21일 전체 재실행은 **111 passed / 2 setup errors**. Python asyncio/socketpair 생성에서 앱 없는 최소 코드와 설치된 Python 3.12.10에서도 같은 OS 오류를 관측했다. 실패 로그는 `verification/console-pytest-2026-10-21.log`, auth 진단은 `verification/auth-retry-2026-10-21.log`, `auth-primed-2026-10-21.log`다.
- 22일 `.venv/Scripts/python.exe -m pytest -q --tb=short`를 PTY에서 실행해 **114 passed, 1 Starlette/HTTPX deprecation warning, 55.86s**, exit 0. skip·정책 우회·stdlib patch·전역 Winsock 변경 없음. 터미널 방식이 근본 해결이라는 결론은 내리지 않는다.
- `python scripts/smoke_demo.py`: 실제 로컬 계정 로그인→분석→초안→독립 승인→mock 유실→복구, exit 0. `python scripts/eval_smoke.py`: **합성 8/8**, exit 0, 외부 benchmark 아님.
- `pnpm test`: **4 passed**. `pnpm build`: `tsc --noEmit`과 Vite 빌드 exit 0, JS gzip 약 77 kB. 사용자 지연/P95나 성능 개선율은 미측정이다.
- `python -m ruff check src tests scripts`, `python -m pip check`, `python scripts/check_package.py`: 모두 exit 0, 필수 20개 누락 0. `docker compose config -q`: exit 0. daemon 조회 실패를 Compose 구문 검사의 성공과 혼동하지 않는다.
- 21일 브라우저에서 engineer 초안·승인 잠금 → reviewer 승인 → 응답 유실 → 영수증 복구/SUCCEEDED·감사 4건 확인. 22일 최신 빌드에서 로그인, A-105 충돌 차단, A-104 과거 v1/읽기 전용, A-103 현재 v2/초안 활성 재확인. 기본 uvicorn 명령도 22일 PTY에서 loopback으로 시작했다.
- [최종 코드 hash·검증 기록](../verification/console-final-2026-10-22.json), [브라우저 기록](design/CONSOLE_QA.md). 실제 외부 모델 성능·연구 독창성·채용 점수는 미측정/보류다.

### R1~R5 및 다음 우선 작업

- R1 중복: 실제 B2/B3/B4 비교가 없어 미해소다. UI와 auth 구현이 연구의 신규성 근거는 아니다.
- R2 범위: 사용자 요청에 따라 인증 콘솔·배포 경로만 확장했다. 관련 없는 ML·런타임 멀티에이전트·노드 편집기는 추가하지 않았다.
- R3 누수: DB 검색 후보와 관계 metadata에서 scope·관측 시점 누출을 차단했다. 실자료·source family 의미·독립 holdout은 미확보다.
- R4 보류 편법: 정상 A-103 조치 초안은 유지하고 충돌/과거 경계만 잠갔다. 정상 업무 coverage의 실제 외부 수치는 측정하지 않았다.
- R5 벤치 부적합: 합성 smoke·작성자 예시·local UI QA를 외부 benchmark와 구별한다. B0~B4 입력 파일은 실제 모델 실험이 아니다.

다음 순서: (1) 정상 Docker/Linux 환경에서 이미지 build/run·CI와 Windows socket 원인 재확인, (2) 계정 회수/세션 폐기·HTTPS/proxy·백업 복원·감사 보존, (3) 사용자 승인 범위가 확정된 실제 자료·독립 라벨/holdout 확보 후 동일 예산 lexical B0와 시간 비교군부터 측정, (4) 별도 mock 프로세스/outbox 장애 검증. 외부 포트 공개·실업무 write·API 과금은 실행하지 않았다.

## 2026-10-22 후속 · 계정 회수와 새 경로 복원

[ADR-004](decisions/ADR-004-ACCOUNT-RECOVERY.md)로 범위와 race/복원 경계를 먼저 확정했다. 기존 `.local` 계정의 암호·활성 상태를 변경하거나 실제 운영 DB를 교체하지 않았다. 새 패키지·외부 연결·공개 배포는 없다.

- 계정 단위: `auth.py`, `scripts/manage_users.py`, `tests/test_account_lifecycle.py`. 기능 부재 **5 failed** → disabled/session_version migration·회수 트랜잭션·발행 직전 재검증 → 5 passed. CLI action 테스트 **2 failed/1 passed** → create 호환·disable/revoke CLI. 테스트 추가 위치 오류로 1 failed/8 passed를 관측하고 해당 부정 입력 블록을 원래 테스트로 되돌렸다. 최종 **11 focused passed**: 기존 token 차단·다른 계정 보존·폐기 후 정상 새 로그인·hash 계산 도중 회수/폐기·legacy migration 반복·CLI create 호환·비밀번호 prompt 금지·API 401 경계.
- 백업 단위: `database_backup.py`, `scripts/backup_db.py`, `tests/test_database_backup.py`. 모듈 부재 red → **8 passed**. 원본 read-only SQLite backup API, integrity_check·필수 table 검증, 임시 파일 실패 cleanup, 같은/기존 목적지 거부, os.link로 overwrite 없는 게시. restore는 복원본의 저장 session을 삭제한다. 동시 쓰기 snapshot 실험·암호화·보존 정책·실운영 DB 교체는 하지 않았다.
- 배포 연결: Docker에 backup CLI를 포함하고 `check_package.py`를 24개 필수 파일로 확장했다. DEPLOYMENT·THREAT_MODEL·GATE_STATUS·TASK_BOARD·SCORECARD·README를 현재 상태에 동기화했다. 백업 이후 계정 회수/암호 변경이 snapshot 복원으로 되돌아가는 한계를 명시했다. 계정 회수/복구는 아직 OIDC/전체 수명주기·운영 재해 복구 SLA의 증거가 아니다.

### 현재 코드 검증 · 이전 114 green과 구별

1. `python -m pytest -q --tb=short` 전체: **122 passed / 2 failed / 9 errors**, 모두 테스트 루프 생성의 WinError 10014. 앱 없는 `asyncio.new_event_loop()` 반복에서도 통과·10014가 섞이는 최소 재현을 확인했다. 기본 라이브러리 패치·socket 예외 무시·skip을 추가하지 않았다.
2. artifact 저장을 포함한 마지막 전체 실행 `python -m pytest -q --tb=line --color=no --junitxml=verification/recovery-pytest-2026-10-22.xml`: **127 passed / 1 failed / 5 errors / 0 skipped**, exit 1. XML assertion으로 각 failure/error에 10014가 포함되는 것을 확인했다. [전체 로그](../verification/recovery-pytest-2026-10-22.log), [현재 검증](../verification/recovery-final-2026-10-22.json). **현재 전체 통과·작업 수용 완료로 표시하지 않는다.**
3. 신규 focused 계정 **11 passed**, backup **8 passed**, Ruff·pip check·필수 파일24개(누락0)·Compose config exit0. 합성 eval smoke **8/8** exit0(benchmark 아님). `smoke_demo.py` 최신 실행은 같은 asyncio/socketpair 오류로 exit1. 묶음 shell의 마지막 exit0을 smoke 성공으로 계산하지 않았고 [별도 실패 로그](../verification/recovery-smoke-2026-10-22.log)를 보존했다.
4. 소유하던 구 uvicorn 프로세스를 종료하고 **새 auth 코드로 기본 uvicorn 명령을 loopback에서 재시작**했다. 별도 동기 HTTP client 2개로 로그인→분석→초안→작성자 승인403→독립 승인→mock 유실→영수증 복구→재시도 동일 영수증→감사 조회→logout/replay401을 실제 서버에서 확인했다. [실제 HTTP 기록](../verification/recovery-live-http-2026-10-22.json). 이 결과가 in-process smoke/전체 pytest 실패를 대체하는 green은 아니다.

### 위험과 다음 작업

R1/R3/R4/R5 연구 제약은 그대로다. R2 범위는 계정·복구라는 배포 경계로 제한했다. 새로운 설계 문제: 복원은 권한/암호 상태도 과거 snapshot으로 되돌리므로 세션 폐기만으로 계정 회수 목록까지 복구되는 것은 아니다. 이미 시작된 요청의 강제 취소도 보장하지 않는다.

다음은 Windows socket/정상 Linux Docker 환경에서 **현재 133개 전체 재검증**과 이미지 build/run·CI다. 이 안전 게이트가 남아 있으므로 새 모델/RAG 확장으로 넘어가지 않는다. 이후 HTTPS/proxy·감사 보존·계정 암호 변경/재활성화·복원 전환 절차를 수용하고, 실제 자료 승인이 확보되면 lexical B0부터 측정한다. 현재 외부 성능/95점·기업 운영 배포 준비 완료는 보류다.

추가 호스트 진단: `wsl --status`를 UTF-16LE로 읽어 **exit50 / WSL 미설치**를 확인했다. Docker settings의 WSL engine은 true, Desktop status는 starting이다. 필수 backend 요소 누락을 [공식 문서](https://docs.docker.com/desktop/features/wsl/)와 대조했다. 설치 후보는 Microsoft `wsl --install --no-distribution`이며 관리자 권한/재부팅이 필요한 OS 변경이므로 최신 AGENTS 규칙에 따라 사용자 승인을 요청했다. 승인 대기 중에는 설치·전역 설정·재부팅을 하지 않았다. WSL 미설치가 Python10014의 원인이라는 주장은 하지 않는다.

## 2026-10-22 후속 · 승인된 WSL2 설치

사용자가 “WSL2 설치를 승인합니다 — 재부팅은 제가 진행”으로 범위를 확정했다. 최초 비관리자 실행은 exit1로 설치되지 않았고, 관리자 권한으로 `wsl --install --no-distribution`을 실행해 **exit0**을 확인했다. WSL `--version`/`--status`/`--list`를 실제 호출해 WSL 3.0.3.0, 기본 버전2, 최초 별도 배포판 없음이 확인됐다. 이후 Docker Desktop이 생성한 `docker-desktop`에서 `uname -r`이 **6.18.54.1-microsoft-standard-WSL2**를 반환했고 Running/VERSION2였다. 별도 Ubuntu 설치·자동 재부팅·공개 배포는 하지 않았다.

`docker desktop restart --timeout 60`은 init 응답 대기로 시간 초과(exit1), `docker version --format '{{json .Server}}'`은 API500(exit1)이었다. WSL 설치 성공을 컨테이너 성공으로 계산하지 않는다. 확인한 CBS/Windows Update 재부팅 대기 key는 false였다. 사용자가 예정한 재부팅 이후 WSL·Docker 응답·build/run·현재 전체133개 재검증을 이어간다. [구조화 설치 기록](../verification/wsl-install-2026-10-22.json), [현재 코드 검증](../verification/recovery-final-2026-10-22.json)에 이전 실패와 새 호스트 상태를 구분했다.

이번 단위는 호스트 설치·상태 문서만 변경했다. 앱 로직·의존성 명세·계정·기존 DB는 수정하지 않았고, 앱 테스트를 반복해 기존 127 pass/1 failure/5 errors를 지우지 않았다. R1/R3/R4/R5 연구 제약은 그대로이며 R2 범위는 컨테이너 선행조건으로 제한했다. Docker 내부 init 대기 원인은 아직 확정하지 않았고 WSL과 WinError10014의 인과관계도 미입증이다. 도구는 PowerShell/Windows Installer·Python subprocess와 문서 위치 확인용 읽기 전용 탐색 에이전트를 사용했다.

문서 갱신 후 `python scripts/check_package.py`는 필수24개 누락0(exit0), `docker compose config -q`도 exit0이었다. 두 JSON의 설치 exit0·자동 재부팅 false·기존 pytest 실패 보존 assertion을 통과했다. Compose 구문 통과를 엔진 실행으로 계산하지 않는다.

## 2026-10-22 후속 · Docker 실제 복구와 Linux 전체 검증

사용자가 실패·오류를 실제로 수정하라고 요청해 Superpowers 원인 추적·검증 흐름과 Ponytail의 최소 변경 원칙을 적용했다. 목적은 테스트 삭제/예외 무시 없이 기존 앱의 배포 실행 경로를 복구하는 것이다. 앱 정책·인증/ACL·DB 내용·의존성 명세는 바꾸지 않았다. 이전 에이전트 세션이 종료된 뒤 실제 파일 로그를 회수해 상태를 다시 확인했다.

1. 시작 검사: `.venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=verification/runtime-baseline-pytest-2026-10-22.xml` → **126 passed / 7 errors / 0 skipped**, exit1. 각 error가10014인 것을 XML assertion으로 확인했다. `smoke_demo.py`도10014로exit1, `eval_smoke.py`는합성8/8 exit0. 이전127/1/5를 최신 결과로 재사용하지 않았다.
2. 소켓 진단: 앱 없는 Python·정확한 타입의 native Winsock listen에서도IPv4 10014, 별도IPv6 비교25/25 성공. Winsock catalog는Microsoft mswsock.dll뿐, Python로드 모듈도Windows/Python뿐이었다. 자식프로세스의 `__COMPAT_LAYER` 제거 비교도실패해 호환성 변수·작은 backlog를 해결책으로 사용하지 않았다. 보안 예외/stdlib patch/skip/Winsock reset을 넣지 않았다. 메모리 압박도 관측했으나10014 원인으로 단정하지 않았다. 최하위 OS/driver 원인은 미확정이며 사용자 직접 재부팅 후 재검증을 요청했다.
3. Docker 복구: version 조회의 pipe 부재/timeout, Desktop start/stop timeout을 확인했다. Docker용 배포판만 `wsl --terminate docker-desktop`로 종료(exit0, unregister/디스크삭제 아님)하고 `docker desktop restart --timeout 60`으로 재시작(exit0)하자 **Desktop4.95.0 / Engine29.8.2**가 응답했다. 이 절차로 복구됐다는 관측이며 내부 정지 원인까지 확정한 것은 아니다. Windows 재부팅은 하지 않았다.
4. 실제 `docker compose build --progress plain` →exit0, `docker compose up --no-build -d --wait --wait-timeout 90` →exit0/Healthy. Node24·Python3.12 공식 base와 기존 lock/pyproject 의존성만 사용했다. 실제 inspect로 UID10001·read-only root·ALL cap drop·no-new-privileges·127.0.0.1:8000 바인딩을 확인했다. 현재 서비스는 기본 계정 없이 시작하며 계정 생성은 운영자 CLI 절차다. 공개포트·유료 API·외부자료·새기술을 추가하지 않았다.
5. 첫 Linux 검증은 read-only 컨테이너의 `/data` volume을 마운트하지 않아 import 때 DB 경로 오류였다. [최초 실패 로그](../verification/linux-container-initial-2026-10-22.log)를 보존하고 **검증용** `OPSPILOT_DB=/tmp/import-default.sqlite3`를 지정했다. 서비스 정책을 바꾸지 않았다. pytest9.1.1/httpx0.28.1은 pyproject dev 범위로 임시 `/tmp/verification-deps`에 설치했으며 서비스 이미지는 그대로다.
6. Linux Python3.12.15에서 전체 **133 passed / 0 failed / 0 errors / 0 skipped / dependency warning1개, 68.88s**, exit0. `smoke_demo.py` 실제 로컬 세션→분석→승인→유실→복구 exit0. 합성 `eval_smoke.py`8/8 exit0. 경고는 Starlette/HTTPX deprecation이며 새 패키지를 임의 추가해 없애지 않았다. [전체 로그](../verification/linux-container-2026-10-22.log), [XML](../verification/linux-pytest-2026-10-22.xml), [명령 exit 기록](../verification/linux-commands-2026-10-22.json).
7. 설치 이미지 자체도 `--network none`·UID10001·read-only root·임시 DB로 실행해 **실제 HTTP** 가상계정2개 로그인→분석→초안→위조actor를 보낸 작성자 승인403→독립 승인→mock 유실→receipt복구→같은receipt재시도→감사→logout후cookie재생401을 통과했다. 테스트컨테이너·임시DB는 종료 시 정리됐고 서비스 volume/기존계정은 수정하지 않았다. 별도로 실제 Compose의 health·HTML/JS/CSS200·미인증401을 확인했다. [이미지 E2E](../verification/container-image-e2e-2026-10-22.json), [서비스 HTTP/설정](../verification/container-http-2026-10-22.json). 이번 브라우저 상호작용은 도구가 없어 미실행이다.

변경 파일은 README·DEPLOYMENT·GATE_STATUS·TASK_BOARD·SCORECARD·WORK_LOG와 검증 로그/XML/JSON·재현 runner2개다. runner는 처음 `.local`에서 실행했고 자격증명 없는 동일 코드를 `verification/`으로 옮겨 재현 입력으로 보존했다. [현재 코드 hash·상태](../verification/runtime-final-2026-10-22.json)는 Windows 실패·최초 harness 실패를 삭제하지 않고 Linux 통과와 구분한다. `.git`이 없어 commit/PR은 만들지 않았다.

R1 중복·R3 실자료누수·R4 정상업무coverage·R5 외부benchmark 적합성은 여전히 연구 미해소다. R2는 기존 배포경로 복구로 제한했다. 발견한 설계/운영 문제: API module import가 기본 DB를 초기화하므로 검증프로세스도 쓰기 가능한 **별도** DB 경로가 필요하다. 이번에는 명시적 환경설정으로 격리했으며 startup/lifespan 재구조화는 하지 않았다. 다음은 사용자 재부팅 후 Windows 원인 재확인, HTTPS/proxy·감사/복원 전환 수용과 실제 GitHub CI, 승인된 실제 자료의 lexical B0 평가 순서다. 로컬 Docker 수용이 기업 운영/공개 배포·외부 성능·95점 완료를 뜻하지 않는다.

최종 확인: Ruff는 src/tests/scripts와 runner 2개까지 통과했고 필수24개 누락0·Compose 구문도 통과했다. 다만 이어진 Compose 조회에서 Docker pipe가 사라졌고 Desktop 프로세스 종료를 관측했다. 일반 `Start-Process Docker Desktop.exe -WindowStyle Hidden` 재실행 뒤 **같은 컨테이너**가 자동 Healthy로 돌아왔다. 종료 원인·장기 지속성은 미확정이며 Application crash event도 조회 범위에서 발견하지 못했다. 성공 snapshot을 계속 실행 보장으로 표현하지 않도록 읽기 전용 근거 검토의 지적을 문서/JSON에 반영했다.

브라우저 도구가 다시 노출된 뒤8000 접근을 시도했지만 시작 중 REFUSED·호스트 회복 뒤 FAILED가 나와 이번 UI 상호작용을 끝내지 못했다. HTTP 검증을 브라우저 성공으로 대체하지 않았고 우회 브라우저도 사용하지 않았다. Docker 복구 후 Windows 소켓 최소 probe를 한 번 더 실행했다: IPv4 listen60/60, socketpair55/60·10014 오류5개. [원시 진단](../verification/windows-socket-post-recovery-2026-10-22.json), [최종 상태](../verification/runtime-final-2026-10-22.json). Windows 오류 해결 판정은 계속 보류다.

## 2026-10-23 · 재부팅 보고 후 검사와 컨테이너 Chrome 검증

사용자가 재부팅 완료를 알렸다. Superpowers 원인 추적·검증, Ponytail 최소 변경, Auto Model Router의 모델 선택을 적용했다. Router가 선택한 Luna/medium 읽기 전용 진단 에이전트로 Windows 모듈/레지스트리와 XML 실패 분류를 확인했다. 앱 기능·테스트·의존성은 수정하지 않았으며 이전 Linux/빌드 입력36개 SHA256이 동일함을 assertion으로 검사했다. 코드 변경 단위가 아니므로 새 실패 테스트를 만들지 않고 필수 baseline과 실제 UI 경계를 검증했다.

1. `.venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=verification/reboot-windows-pytest-2026-10-23.xml` → **133개 중120 passed / 2 failures / 11 errors / 0 skipped**,174.76s, exit1. XML의 실패·오류13건 모두10014를 포함함을 assertion과 별도 읽기 검토로 확인했다. `scripts/smoke_demo.py`는 루프 생성10014로exit1, `scripts/eval_smoke.py`는합성8/8 exit0. [명령/exit](../verification/reboot-windows-commands-2026-10-23.json), [pytest XML](../verification/reboot-windows-pytest-2026-10-23.xml). 테스트를 제거·skip·예외 무시하지 않았다.
2. 앱 없는 socketpair probe: IPv4 **33/60 성공·27건10014**, IPv6 **60/60 성공**. [진단](../verification/reboot-socket-2026-10-23.json). Windows/Python 모듈29개에서 verifier/compat 관련 이름은 없었고 Python IFEO/SilentProcessExit key도 없었다. 시스템 FTH Enabled=1은 Python 적용 증거가 아니며 원인은 미확정이다. 커널 LastBoot가10/21로 관측돼 사용자가 수행한 재시작 범위를 질문했으나 이 기록 시점에는 답이 없다. 재부팅 완료 보고를 부정하거나 해결로 계산하지 않았고 자동 재부팅·전역 설정·Winsock reset은 실행하지 않았다.
3. Desktop/pipe가 없는 상태에서 표준 `Docker Desktop.exe`를 hidden 실행했다. 정상 시작 대기 뒤 **기존 컨테이너3f3909ddfc71**가 Healthy로 복구됐다. UID10001:10001·read-only·cap drop·no-new-privileges·127.0.0.1:8000과health200을 재확인했다. 서비스 재생성·volume/기존 계정 변경은 없었다. 이전10/22 Linux133개·두 스모크는 날짜를 유지하고 이번 새 실행으로 재사용하지 않았다.
4. CUA Chrome에서 서비스8000 로그인 화면을 확인했다. 동일 이미지의 별도 `opspilot-browser-verify-20261023` 컨테이너를 loopback18010·non-root·read-only·tmpfs DB로 띄워 테스트 전용 engineer/reviewer 계정으로 로그인→현재A-103·타임라인→초안→작성자 승인 비활성→독립 승인→mock 응답 유실→영수증 복구/실행 완료·감사4건을 확인했다. engineer로A-105 충돌과A-104 과거9/20 v1·읽기 전용의 초안 차단도 확인했다. 실제 UI는8개 경로이며 pytest 수나 외부 평가에 합산하지 않는다. [화면/QA](design/CONSOLE_QA.md).
5. 승인/복구 및 충돌/과거 확인에서 콘솔warn/error0건을 관측했다. 원래 탭의 제어 연결이 끊겨 새 Chrome 탭으로 계속했다. 날짜 fill이 React state에 반영되지 않아 AX setValue로 표시 날짜를 확인했고 fullPage screenshot 시간 초과는 viewport 캡처로 대체했다. 성공하지 않은 첫 과거 분석/캡처를 성공으로 기록하지 않았다. 테스트 컨테이너 ID를 확인한 뒤 종료·자동 제거했고 Docker 목록에서 부재를 확인했다. 서비스8000 로그인 화면은 남겼다.

변경: README·DEPLOYMENT·GATE_STATUS·TASK_BOARD·CONSOLE_QA·SCORECARD·WORK_LOG, 새 검증 JSON/XML/log와 JPEG3개. [최신 상태·hash·정리 증거](../verification/reboot-final-2026-10-23.json). `.git`이 없어 commit/PR은 없으며 공개 배포·외부 업로드·모델/데이터 다운로드·유료 호출은 하지 않았다. 실제 사용 도구는 PowerShell/Python/Docker CLI·CUA Chrome·모델 선택용 Router와 읽기 전용 하위 에이전트다.

위험 재검토: R1 중복 연구·R3 누수·R4 과도한 보류·R5 benchmark 부적합은 실원본/독립 라벨/B0~B4 실험 부재로 그대로다. R2 범위는 기존 런타임·UI 검증에 한정했다. 새로 확인한 동작 오류는 없으나 **Windows native socket 원인, 재시작 범위, Desktop 종료 원인·장기 안정성**은 미해결이다. 다음은 해당 OS 경계 해소·실제 CI/HTTPS 수용이며, G0 자산 권리/다운로드 범위·G1 독립 검토를 확보한 뒤 실제 lexical B0부터 측정한다. 외부 배포·연구 수용·95점은 계속 보류다.

마지막 정적 확인: `python scripts/check_package.py` exit0(필수24개 누락0), 보고서의 Windows 수치/exit·Linux 날짜·임시 컨테이너 제거·미배포 상태 assertion 통과, 앱 입력36개 hash 일치, 문서7개의 로컬 링크 누락0이었다. 별도 읽기 전용 검토도 같은 수치·117개 링크를 확인했다. UI/앱 코드는 바뀌지 않아 Linux 전체 테스트·frontend build를 문서 변경 뒤 반복 실행하지 않았다.

## 2026-11-02 · UI02 현재 근거 검토 상태와 승인함 동기화

공개 OpsPilot의 `caa8902`를 별도 클라우드 폴더에 복제하고 기능 브랜치에서 작업했다. DocFlowLab·원본 PC·사용자 DB는 수정하지 않았다. 개발·디자인·독립 QA·최종 코드 검토 역할을 나눴다. 기존 G0/G1은 외부자료 권리/독립 라벨이 미확보여서 연구 완료를 선언하지 않으며, 이번 단위는 이미 구현된 승인 흐름의 확인 가능한 결함으로 제한했다. 새 라이브러리·실제 쓰기 도구·실계정·외부자료·과금은 추가하지 않았다.

문제: 검토자 ACL 회수·근거 변경 시 API는 변경 요청을 거부했지만 UI가 빈 근거를 원본에서 확인하라고 안내하며 승인/최초 실행을 활성화했다. 현재 principal·저장 action/fingerprint·최신 근거를 확인하는 `evidence_reviewable`과 명시적 잠금/재조사 안내를 연결했다. 숨겨진 문서의 사유·메타데이터는 노출하지 않는다. GET으로 제안 상태를 변경하지 않으며, 원 승인자의 기존 영수증 복구를 유지한다. 오류/새로고침 뒤 목록·상세를 함께 갱신하고 조회 실패 시 이전 조작을 제거한다.

검증: 초기 pytest 미설치 후 기존 lock으로 venv를 구성했다. pnpm 기본 캐시가 쓰기 불가여서 `/tmp`의 XDG/store 경로로 설치했고 잠금 파일은 바꾸지 않았다. baseline `pytest -q`167개·두 스모크 통과. 새 API 회귀10실패/프런트1실패 → API10통과/프런트5통과. 최종 `pytest -q`169통과(기존 경고1), Ruff·`pnpm build`·`smoke_demo.py`·`eval_smoke.py`합성8/8·`eval_compare.py`계약예제·`check_package.py`필수24개·`pip check`·`git diff --check` 통과. 정답 fixture 계약/스모크는 연구 성능이 아니다.

실제 Chromium은 정상 승인 가능, 권한 회수 후 승인/최초 실행 잠금, 복구 유지,409 뒤 건수 동기화, 재조회 실패 뒤 이전 버튼 제거를 확인했다. 실행 응답과 상세 GET을 함께 유실시켜도 GET 재선택으로 복구하며 실행POST1회·작업1건을 유지했다.390px 문서 넘침과 관측 JS 예외가 없었다. 최종 문구 조정 뒤 디자인 화면을 재캡처했고 임시 서버3개는 종료했다. [증거·화면·재현 경로](design/REVIEW_READINESS_2026-11-02.md).

현재 준비 상태는 조회 순간의 안내이며 서버 변경 검증이 최종 권한이다. Windows WPF·설치기·운영 전체 안전성·G0/G1 연구 수용은 검증하지 않았다. GitHub에는 기존 승인된 connector 권한으로 기능 브랜치를 게시하고 정확한 remote revision/CI를 별도로 확인한다. main merge·release·visibility 변경은 하지 않는다.

게시 결과: 기능 브랜치 생성 API가403 `Resource not accessible by integration`으로 거부됐다. 원격 브랜치 부재·main `caa8902` 유지 확인. 허용되지 않은 쓰기를 우회/재시도하지 않았고 push·PR·새CI는 실행되지 않았다. 구현 커밋 `72978b0`과 후속 거부 기록 커밋을 로컬에 보존하고 binary patch·Git bundle·소스ZIP을 생성했다. [정확한 요청·결과](../verification/proposal-review-publication-2026-11-02.json). 기존 연동의 쓰기 접근이 해소되면 보존한 기능 브랜치를 정상 게시해야 한다.

## 2026-11-06 승인 입력 맥락 확인

- 공개 LangChain HITL의 실행 전 인자 검토 패턴을 [좁은 범위](../replica/recon.md)로 분석했다. 기존 승인함에서 누락되던 초안의 claim_key/effective_at/known_as_of를 현재 근거 권한 검증 뒤 review_context로 반환하고 KST로 표시한다.
- 독립 승인·fingerprint·기존 근거 ACL·실행/복구는 유지한다. 권한 회수 시 review_context=null이며 조회는 상태·감사·mock 원장을 쓰지 않는다.
- RED: 신규 2개 테스트 모두 review_context KeyError, exit 1(호스트 실행). 구현 후 전체 검증 및 제한은 replica/verification.md에 기록한다. 초기 sandbox TEMP 생성 오류와 TestClient 정지는 검증 성공으로 계산하지 않았다.
- 형제 temporal-decision-comparison 브랜치는 ancestor가 아니며 병합하지 않았다. 기존 proposal-review-readiness 기준을 보존했다.

최종 호스트 확인: 전체 pytest 171 passed(기존 경고 1), smoke E2E PASS, eval_smoke 합성8/8, 모두 exit 0. TypeScript noEmit exit 0. 브라우저 시각/WPF/운영 수용은 별도이며 미실행이다.
## 2026-11-02 · A05 관측 시점별 판정 변화 비교

사용자가 버그/UI뿐 아니라 프로젝트의 실제 핵심 기능 발전을 요청해 기존5bd503f를 보존한 `feat/temporal-decision-comparison`을 만들었다. 개발·디자인·독립 QA가 기존 API/실제 A-104 흐름을 각각 확인했다. 실행 사전 점검은 기존 준비 상태·mock 실행과 중복되고 설비 영향 모델이 없으며, 요청별 감사 이력도 이미 있어 새 기능으로 포장하지 않았다. Product Design get-context 브리프와 후보 검토로 고정 유효 시점·두 관측 시점의 판정 비교를 선정하고 [ADR-005](decisions/ADR-005-TEMPORAL-COMPARISON.md)에 이유·수용 조건을 먼저 기록했다. 제공된 skill context preflight 스크립트 리소스는 읽기 불가라 저장 컨텍스트를 사용한 것으로 표시하지 않았다.

구현: 비교 입력/응답 타입·순서/timezone 검증, 읽기 전용 비교 API, 상태/조치/인용 전체 metadata의 결정적 차이 계산을 추가했다. 두 조회를 같은 query_only SQLite 트랜잭션으로 묶고 각 cutoff의 SQL ACL/known 선필터를 유지한다. 타임라인에는 두 결과·인용 변화·A104 예시·현재ACL 안내와 오류/빈/로딩 상태를 연결했다. 비교 결과를 초안 생성/승인에 연결하지 않는다. 새 라이브러리·계정 권한·외부 자료·실제 명령·배포·과금은 없다.

검증: baseline169개·두 스모크·frontend5개 통과. 초기 새15개404 RED → endpoint/동일snapshot/metadata/order 포함 최종21개 GREEN. 중간 전체185개 이후 추가5개 테스트를 포함해 최종 전체190개(34.21s, 기존 Starlette/httpx 경고1)·frontend5개·TypeScript/build·Ruff·mock E2E·합성8/8·평가계약예제·필수파일24개·pip check·diff 검사 통과. 합성/fixture 결과는 연구 성능이 아니다.

독립 Chromium12개 검사에서 과거 판단과 사후 정정, 변경 없음/충돌/비인가 빈 결과, 오류/재시도·결과 초기화,390px를 확인했다. 비교 전후 제안/작업/감사 전체 행 불변과 기존 UNKNOWN 영수증 동일ID 복구·작업1건을 검증했다. 두 읽기 사이 ACL 회수는 같은 snapshot을 유지하고 다음 요청에 반영했다. 디자인 화면의 의도적503 콘솔1건과 페이지 예외0을 구별했다. 별도 코드 검토도 차단 결함 없이 비교21·기존 ACL/근거17·frontend5를 재실행했다. [화면·재현·검증 파일](design/TEMPORAL_COMPARISON_2026-11-02.md).

현재ACL 기반 합성 비교이며 과거 사용자 권한 이력·실제 설비 영향·외부 벤치마크·G0/G1 연구 수용은 아니다. Windows WPF/설치기는 미검증이다. 임시8765/18213 서버는 종료했다. GitHub create_branch403은 미해결로 이번 원격 쓰기/다른 인증/재시도/CI/배포는 전혀 시도하지 않았다. 이전 브랜치5bd503f와 복구 패키지는 보존하고 새 기능 커밋·별도 패치/번들/ZIP을 준비한다.

## 2026-11-06 phase2 temporal review integration
Preserved sibling temporal comparison and phase1 review_context/readiness through normal merge. Added exact saved-clock comparison and fresh-current-analysis handoffs. [Audit/tests/gaps](../replica/depth-review.md). Frontend6 and noEmit passed; host full-suite193 passed. No production or research gate advancement.

Phase2 host verification completed:193pytest PASS, smoke PASS, synthetic8/8, frontend6 and noEmit PASS. Broader gates unchanged; see replica/depth-review.md.

Phase2 Chromium156 verification completed: native keyboard flow,1440/390px document overflow0, no page exceptions. Synthetic API interception; backend tests separate. Evidence and remaining professional accessibility/production gaps: replica/depth-review.md.
