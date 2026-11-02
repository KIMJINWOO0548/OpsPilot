# 작업 명세 · AI가 수행할 순서 및 완료 기준

**분류:** ✅ 코드/테스트 존재(스코프 제한), ◐ 부분, ⬜ 미구현. 각 칸은 실제 테스트 로그 후에만 변경.

| ID | Gate | 작업 | 의존성 | 현재 상태 | Done 정의 |
|---|---|---|---|---|---|
| A05 | G2/G6 | 관측 시점별 판정 변화 비교 | A03,E01 | ✅ 합성 로컬 기능 | 같은 유효 시점·두 known cutoff의 상태/조치/허용 인용 차이, 같은 읽기DB snapshot·ACL·작업/감사 불변. 새21·Linux190·Chromium12검사. [수용](design/TEMPORAL_COMPARISON_2026-11-02.md) |
| UI02 | G2/G6 | 현재 근거 검토 상태와 승인함 동기화 | A04,UI01 | ✅ 합성 로컬 범위 | 근거 검토 불가 시 승인·최초 실행 잠금, 복구 유지, 실패 후 상세/목록 동기화. Linux169·frontend5·Chromium 검사. [근거](design/REVIEW_READINESS_2026-11-02.md) |
| A04 | G2/G5 | 현재 검토자 문서 ACL 재검증 | A03 | ✅ 격리 사본 | 인용·승인·최초 실행 결함3개 RED→GREEN. 삭제·시점 만료·독립 승인·영수증 복구 포함 새8개/전체167개 통과. [기록](safety/REVIEWER_EVIDENCE_ACL_2026-11-02.md) |
| R00 | G0 | 연구/코드/라이선스 비교표 재검증 | 없음 | ◐ | 8종 공식 commit·코드 LICENSE·범위 기록; 데이터/weights 권리·명령 실행/재현 미확인 |
| R01 | G0 | 독창성 가설/실패 조건 사전 등록 | R00 | ◐ | collision matrix와 R1~R5·단순화 조건 기록; 실제 B2/B3 대조로 novelty 검증은 미완료 |
| D01 | G1 | 데이터 사양+출처+split manifest | R01 | ◐ | 평가 실행에 원문 hash·group/ID split·근접중복·holdout guard 연결; 30개 합성 예시만 있고 독립 정답/실자료 미확보 |
| D02 | G1 | 보안·시간·정답 label guideline | D01 | ◐ | 8개 edge case·2인 검토/조정 기준 문서화; 실제 독립 검토자·검토 결과 미확보 |
| E01 | G2 | 실행 가능한 EIE 타입/temporal 룰 | D01 | ✅ | `pytest tests/test_eie.py` 통과. 단 baseline 스캐폴딩임 |
| A01 | G2 | 로컬 API+합성 데이터+브라우저 | E01 | ✅ | `/health`, `/analysis`, `/proposals`, 승인, mock 실행 E2E |
| A02 | G2 | 로컬 mock 승인·receipt·중복 방지 | A01 | ✅ | 20 동시 호출 1 unique receipt, 응답 유실 복구 유지; 정상·권한 거부 시 DB 연결 종료 검증 |
| A03 | G2 | API 실제 identity/Auth 추가 | A01 | ◐ Linux 검증 | 서버 계정·PBKDF2·opaque session/CSRF·expiry/logout·시도 제한, JSON actor 무효·scope 404, 비활성화·세션 회수/로그인 race·legacy migration. Linux 전체133개·설치 이미지 HTTP 통과. Windows 소켓·OIDC·암호 변경은 후속 |
| DB01 | G3 | Postgres bitemporal+immutable evidence ledger | D01,E01 | ⬜ | migration, RLS, 시점 경계/역행/수정/체크섬, UTC 테스트 |
| DB02 | G3 | SQL view/read tools + source capture | DB01 | ⬜ | 고정 SQL allowlist, per-tenant 접속, injection/timeout 검증 |
| RAG01 | G3 | BM25/lexical baseline B0 + retrieval API | D01 | ◐ | SQLite ACL/known 선필터 + 단순 lexical overlap API 구현. 합성 문서만 사용, B0 검색 품질/지연·외부 성능 미측정 |
| RAG02 | G3 | Dense/hybrid B1, temporal B2 | RAG01,DB01 | ⬜ | 같은 토큰/문서/top-k 예산, Recall/latency/cost 기록 |
| E02 | G3 | Claim/NLI 충분성 B3 | RAG02 | ⬜ | span 정답, SUPPORT/REFUTE/NEI, 비용·실패 유형 분석 |
| E03 | G3 | B4 EIE evidence/action policy | E02,DB01 | ⬜ | B3 vs B4 paired 결과, ablation, score calibration |
| EV01 | G4 | T1 공식 외부 벤치 재현 | RAG02 | ⬜ | 라이선스/commit/hardware/공식 500 평가와 metadata 별도 |
| EV02 | G4 | T2 dev/holdout + 독립 검토 | D02,E03 | ⬜ | 300 목표, source-group split, blind review, 누수 검사 |
| EV03 | G4 | bootstrap/risk-coverage/cost | EV02 | ◐ | G1 준비 도구로 집계·dev calibration·paired cluster CI만 구현; primary KPI/실제 비용·알고리즘 효과 미측정 |
| OP01 | G5 | Outbox/remote mock 분리 | DB01,A03 | ⬜ | 다른 프로세스 장애/재시작·응답유실/receipt reconciliation |
| OP02 | G5 | Fault injection, ACL, audit/secret masking | OP01 | ◐ | 로컬 auth·ACL·actor 위조·저장 action tamper·scope oracle 회귀. 외부 장애 matrix·감사 불변 저장·로그 마스킹 검증은 미완료 |
| UI01 | G6 | React/TS Investigation & Timeline & Approval | A03,E03 | ◐ 제품 경로 | 로그인·3화면·실제 승인/복구·충돌/과거 차단을10/23 컨테이너 Chrome에서 확인. 기존 helper4개/build·모바일 폭 검사. 연구 E03·정식 접근성·3분 영상 미완료 |
| DEP01 | G6 | 같은 origin UI/API 배포 패키지 | A03,UI01 | ◐ 로컬 수용 | Docker 엔진 복구·이미지 build/run Healthy·UI 자산200·비인증401·non-root/read-only/loopback 실제 검사, Linux133 tests·설치 이미지 mock HTTP 통과. GitHub CI·HTTPS/외부 배포 미검증 |
| DEP02 | G5 | 일관된 SQLite 백업·새 경로 복원 | A03 | ◐ 운영 수용 전 | 읽기 전용 backup API·integrity/table 확인·overwrite 거부·복원 세션 폐기 8 tests 통과. 암호화·보존·운영 장애/동시 쓰기 실험 미완료 |
| PERF01 | G6 | 단계별 부하·P95·토큰/비용 | OP02,EV03 | ⬜ | 1k→10k→50k docs 단계별 결과, 운영 안전성 근거 |
| EXT01 | G7 | 제삼자 독립 재실행 | EV03,OP02 | ⬜ | reviewer artifacts/실행환경/의견/수정 이력 |
| PORT01 | G8 | 기술 보고서, 3분 데모, 질의 대비 | EXT01 | ⬜ | 공개 코드, G0~G7 검증 + 한계 보고 + 직무 매핑 |

### 작업 단위 PR 템플릿
```
ID: RAG02
가설: 외부 데이터에서 Hybrid RAG가 B0를 개선할 수 있는가?
수정: ...
실패 테스트: ...
성공 테스트/실험 명령: ...
환경/버전/비용: ...
대조군 결과: 미측정 / 실측 링크
보안·라이선스 확인: ...
새로운 한계와 실패 사례: ...
ADR 및 WORK_LOG 업데이트: ...
```

### 다음 에이전트가 바로 해야 할 3건
1. `R00/D01` [자산별 권리·최소 slice 제안](research/DATA_ACQUISITION_PROPOSAL.md)의 정확한 원천/버전/사용 범위를 확인한다. 다운로드·유료 호출은 실행 전 사용자 승인 범위를 특정한다.
2. `D02` [30개 작성자 합성 예시](../evaluation/examples/contract_v1/README.md)에 대한 독립 검토자 2인·이견 조정·실제 봉인 holdout을 확보한다. [CLI](evaluation/EXPERIMENT_RUNBOOK.md) 통과만으로 G1 수용을 선언하지 않는다.
3. `DEP01/A03/OP02`: Docker build/run·10/22 Linux133개와10/23 Chrome 검증은 완료했다. 재부팅 완료 보고 후에도 Windows120 pass/2 failures/11 errors(10014), 커널 LastBoot10/21로 관측됐다. 재시작 범위와 OS 소켓 원인을 확인한 뒤 동일 probe→전체 pytest→smoke로 검증한다. 이어 HTTPS/proxy·감사 보존·계정 수명주기·복원 전환을 검증하고, GitHub CI는 실제 실행 증거를 별도로 확보한다. 사용자 자료 승인이 확보되면 `RAG01`의 실제 lexical B0부터 고정 예산에서 측정한다. 저장 prediction B0/B2는 입력 fixture이며 외부 공개는 별도 릴리스 검토 후다.

2026-10-19: Python API 유지·G6 React/TypeScript 방향은 [ADR-001](decisions/ADR-001-PLATFORM-AND-DESIGN.md)에 기록했다. 전체 32 tests, mock E2E 및 합성 스모크·Ruff·패키지 필수 파일 검사가 통과했다. G0/G1은 부분 상태를 유지한다.

2026-10-20: G1 데이터·저장 prediction 평가의 실행 경로와 CI의 Windows/Linux 계약 검사 단계를 추가했다. 실제 GitHub Actions·외부 데이터·B0~B4 실행 실험은 하지 않았다. G0/G1 연구 수용은 계속 미완료다.

2026-10-22: [ADR-003](decisions/ADR-003-SECURE-CONSOLE.md)에 따라 사용자가 요청한 인증 콘솔을 구현했다. 전체 114 tests·frontend 4 tests/build·mock E2E 통과. [검증 기록](../verification/console-final-2026-10-22.json), [QA](design/CONSOLE_QA.md), [배포 안내](DEPLOYMENT.md) 참조. Windows의 간헐적 socket 오류와 Docker daemon 시작 실패는 해결된 것으로 표시하지 않는다.

2026-10-22 계정 회수 직후: [ADR-004](decisions/ADR-004-ACCOUNT-RECOVERY.md) 계정 회수·복원을 구현했다. 계정11·backup8 tests 및 실제 HTTP mock E2E 통과. 당시 Windows 전체는127 pass/1 failure/5 errors(10014)였다. [당시 검증](../verification/recovery-final-2026-10-22.json). 이전114 green을 후속 코드의 결과로 재사용하지 않는다.

2026-10-22 런타임 복구: Docker 시작 오류를 WSL 배포판 정지·Desktop 재시작으로 복구했다. 실제 build/up·Healthy·non-root/read-only/loopback 확인, Linux **133 passed / 0 skipped**, 두 스모크·설치 이미지의 실제 HTTP mock E2E 통과. Windows 새 baseline은126 pass/7 errors로 별도 보존했다. [현재 상태](../verification/runtime-final-2026-10-22.json). 앱 정책/테스트를 약화하거나 소켓 오류를 숨기는 패치는 하지 않았다.

추가 남은 항목: Desktop이 다시 종료돼 앱 재실행으로 동일 컨테이너가 복구됐다. 장기 지속성/종료 원인·브라우저 연결 오류를 운영 수용 전에 확인한다. Windows socketpair는 복구 후 재검사도55/60 성공으로 오류가 남아 사용자 재부팅 뒤 확인해야 한다.

2026-10-23 후속: 브라우저 연결은 Chrome에서 복구해 같은 이미지의 임시 DB로 로그인·현재 분석·타임라인·작성자 승인 잠금·독립 승인·mock 유실/복구·엔지니어의 충돌/과거 차단을 확인했다. 임시 컨테이너를 제거하고 서비스8000 로그인 화면을 열었다. Windows 새 실패와 재부팅 시각 불일치는 [최신 기록](../verification/reboot-final-2026-10-23.json)에 보존했다. 앱·테스트·의존성 코드는 변경하지 않았으며 앞선 Linux/빌드 결과와 입력 hash가 동일하다. G0/G1·95점·공개 배포 수용은 보류다.
