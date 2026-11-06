# Gate 상태표 (2026-10-23 갱신)

> 이 표에서 `작동`은 로컬 제한 범위에만 적용됩니다. 95점 달성 증거가 아닙니다.

**2026-11-02 클라우드 후속:** 현재 권한·근거로 초안을 검토할 수 있는지를 API/승인함에 연결했다. 승인·최초 실행 잠금과 영수증 복구 유지, 실패 후 목록/상세 동기화를 Linux169개·frontend5개와 실제 Chromium에서 확인했다. [화면·검증](design/REVIEW_READINESS_2026-11-02.md). Windows WPF/설치기·G0/G1 연구 수용은 이번에 검증하지 않았다. 아래 과거 수치의 날짜를 유지한다.

**2026-11-02 격리 사본:** A04/OP02의 검토자 문서 ACL 결함을 재현·수정했다. 새8개/전체167개 Windows pytest, Ruff·mock E2E·합성8개·평가 계약 예제·필수파일 검사 통과. 과거10014는 일반 Windows 검사에서 재현되지 않았고 샌드박스 소켓 제한과 구별한다. WPF/설치기·출시·GitHub CI·연구 게이트는 미검증이다. [증거/한계](safety/REVIEWER_EVIDENCE_ACL_2026-11-02.md). 아래 표와 이전 기록은10월23일 이력이다.

| Gate | 상태 | 확인 가능한 결과 | 부족한 것 |
|---|---|---|---|
| G0 선행연구 | 부분 검토 | [8종 고정 commit·코드 LICENSE·재현 범위](research/prior_art_matrix.csv), [B2/B3/B4 가설 경계](research/NOVELTY_COLLISION_MATRIX.md) | 데이터/가중치 자산 이용 권리, 실제 baseline 재현, 독창성 가설의 실험 검증 |
| G1 평가 계약 | **실행 코드 보강 / 연구 수용 미완료** | 원문·라벨 SHA256, source/revision family·case ID split 검증, 근접중복·시점·ACL, dev/holdout 라벨 분리, [30개 작성자 합성 예시](../evaluation/examples/contract_v1/README.md), [평가 CLI](evaluation/EXPERIMENT_RUNBOOK.md) | 실자료, 독립 검토자와 검토된 30 사례, 실제 봉인 holdout, 실제 B0/B1/B2 실행 |
| G2 로컬 E2E | **Linux 전체 통과 / Windows 환경 오류 잔존** | 10/22 Linux133 tests·두 스모크, 서버 계정/session·CSRF·회수, DB principal, SQL ACL/관측 선필터, 설치 이미지 HTTP와10/23 Chrome의 mock 승인·유실·복구 | Windows120 pass/2 failures/11 errors 해소·재검증, OIDC/SSO·암호 변경, 실제 LLM, Postgres 전환 |
| G3 EIE 연구 | 미착수 | 결정적 임시 time/conflict filter 코어 | B2/B3/B4 공정 대조, NLI 결합, claim/evidence span alignment |
| G4 실험 | 연구 미착수 / 집계 도구 준비 | 저장 prediction용 risk/coverage·부분 AURC·source-cluster paired CI와 dev calibration 구현; 실제 모델 비교 없음 | T1/T2/T3 실자료, B0~B4 동일 조건 실행, ablation, 독립 검토, 실측 비용/지연 |
| G5 안정성 | 부분 구현 | 계정 hash/session/CSRF·시도 제한·회수 race 방어, scope 404·actor 위조 차단, 저장 action 변조 차단, mock 멱등성·응답 유실, 검증된 새 파일 백업/복원·세션 폐기 | OIDC, RLS, Postgres outbox, 별도 프로세스 crash/restart, 감사 불변 저장소·암호 변경/재활성화, 침투 테스트 |
| G6 제품화 | **로컬 컨테이너·Chrome 검증 / 외부 배포 미완료** | 로그인·조사·타임라인·승인함, [화면/QA](design/CONSOLE_QA.md), TypeScript/build·실제 non-root/read-only/loopback·Healthy·설치 이미지 HTTP/Chrome 검사 | GitHub CI 실실행, HTTPS/proxy, 접근성 정식 검사, 추적·운영 관측, 부하 테스트 |
| G7 외부 검증 | 미착수 | 없음 | 외부 재실행, 독립 평가, 실제 OSS 기여/대회 |
| G8 포트폴리오 | 부분 구성 | 실행 README·배포 안내·ADR·실패 사례·브라우저 캡처·자동 검증 기록 | 실제 외부 실험, 독립 검토, 기술 보고서·3분 영상·최종 제출본 |

- 성과는 실제 테스트 로그·공개 산출물로 검증한다.
- 편의상 순서가 앞서 구현된 축소 데모가 있다고 해서 선행 게이트가 통과된 것으로 표시하지 않는다.
- 사용자 승인 없는 유료 서비스·데이터 수집·실서비스 연결은 금지한다.
- 이번 검증은 Windows 11 / Python 3.12.14 로컬 환경이다. G2 작동과 합성 8개 일치 검사는 G0/G1 통과나 연구 성능이 아니다. [검증 기록](../verification/windows-2026-10-19.json), [플랫폼 결정](decisions/ADR-001-PLATFORM-AND-DESIGN.md) 참조.
- 2026-10-20 추가: [ADR-002](decisions/ADR-002-EVALUATION-CONTRACT.md)에 따라 G1 검사·평가를 연결했다. [계약 CLI 기록](../verification/g1-contract-final-2026-10-20.json)은 모든 보류/정답 복사 입력의 배선 검증이며 성능표로 사용할 수 없다. `.git` 부재로 code commit은 미확보이고 CI 설정 추가를 실제 GitHub 실행으로 간주하지 않는다.
- 계정 회수 직후 Windows 실행은133개 중127 passed/1 failed/5 errors였고, 후속 Windows baseline은126 passed/7 errors였다. 모두10014가 포함된 루프 생성 오류다. [이전 Windows 기록](../verification/recovery-final-2026-10-22.json)과 아래의 새 Linux 결과를 구별한다. focused 계정11개·backup8개와 실제 HTTP mock E2E는 통과했다. Windows in-process smoke는 실패했으며 Windows 오류 해결로 표시하지 않는다.
- 프런트 helper 4개·typecheck/build는 직전 UI 단위에서 통과했고 이후 UI 변경은 없다. 합성 8개·Ruff·pip/package 검사(24개 파일)와 Compose 구문 검사는 통과했다. 검사 수를 연구 성능·외부 검증·게이트 점수로 환산하지 않는다.
- 사용자의 배포 지향 UI 요구를 [ADR-003](decisions/ADR-003-SECURE-CONSOLE.md)에 반영했다. 이 순서 확장은 G0/G1 수용을 대체하지 않는다. 최초 daemon 실패 뒤 실제 이미지 build/run 검증까지 진행했으며 공개 배포는 하지 않았다.
- WSL 설치 직후에는 Docker 재시작 시간 초과/API500이었다. 이후 `wsl --terminate docker-desktop` → Desktop 재시작으로 엔진29.8.2 응답·이미지 build·Compose Healthy를 확인했다. 현재 Linux 전체 **133 passed / 0 skipped**, 두 스모크와 설치 이미지의 실제 HTTP mock E2E 통과다. Windows는 새 baseline **126 passed / 7 errors**(모두10014)로 재부팅 후 검증이 남는다. [현재 검증](../verification/runtime-final-2026-10-22.json), [설치 당시 기록](../verification/wsl-install-2026-10-22.json). GitHub CI·외부 배포·G0/G1 연구 수용은 완료하지 않았다.
- 최종 확인 중 Desktop 종료/pipe 소실을 추가 관측했다. 앱 재실행 뒤 같은 컨테이너 Healthy를 다시 확인했으나 종료 원인·장기 지속성은 미확정이다. 브라우저 연결 오류로 이번 화면 상호작용은 차단됐다. Docker 복구 뒤 Windows socketpair probe도55/60 성공·5건10014로 미해결임을 재확인했다.
- **10월 23일 최신 검사:** 사용자 재부팅 완료 보고 후 Windows133개는120 pass/2 failures/11 errors, smoke exit1, 합성 eval8/8 exit0이었다. 13건 모두10014를 포함한다. 커널 LastBoot는10월21일로 남아 재시작 범위 확인 중이며 원인 해결로 표시하지 않는다. 표준 Desktop 실행 뒤 동일 서비스 Healthy를 확인했고, 같은 이미지·임시 DB의 실제 Chrome에서 정상 승인/복구·충돌/과거 초안 차단을 검증했다. 테스트 컨테이너는 제거했다. [최신 기록](../verification/reboot-final-2026-10-23.json). 이전 브라우저 차단은 이 Chrome 경로에서 해소됐으며 장기 안정성·연구 수용·공개 배포는 계속 미완료다.

2026-11-06: 승인함의 저장 주장·유효/관측 시점 표시를 추가했다. 현재 근거 검토가 가능한 호출자에게만 읽기 투영한다. [참조 범위](../replica/recon.md), 검증은 replica/verification.md. G0/G1 연구·운영 수용 게이트는 이번 변경으로 완료되지 않는다.
