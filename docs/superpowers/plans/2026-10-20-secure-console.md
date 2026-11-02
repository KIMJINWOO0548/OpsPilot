# 인증된 배포 단위 콘솔 구현 계획

**명세:** [ADR-003](../../decisions/ADR-003-SECURE-CONSOLE.md). 사용자 지시에 따라 로컬 구현을 자율 진행한다. .git 없는 패키지이므로 worktree/commit/실제 PR은 만들었다고 보고하지 않는다.

1. 인증/API: 서버 session·사용자 관리, CSRF, principal 유도, proposal 목록/조회/감사 scope와 기존 승인·복구 API. 소유 api.py/auth.py 및 auth/API tests/smoke. 실제 계정으로 기존 policy 테스트를 전환하며 역할 입력 위조로 통과시키지 않는다.
2. UI: web/의 React/TypeScript/Vite, 로그인·조사·근거 타임라인·승인함. 실제 API와 cookie/CSRF를 사용한다. mock UI API·하드코딩 성능·프론트 권한 결론은 없다. typecheck/build 후 브라우저에서 상태·오류·반응형 확인.
3. 근거 저장소: SQLite evidence/ACL와 immutable seed, authorized query와 lexical 검색. 기존 evaluate(request, seed=...)를 재사용한다. 비인가/미래 record가 ranking/engine에 들어가지 않는 실패 테스트와 정상 경로를 확인.
4. 배포: UI multi-stage build·non-root backend·dependency locks·영속 volume·healthcheck·관리/실행 안내. 실제 인증 없이 실행하는 경로는 없앤다. Docker 도구가 없으면 미검증 기록.
5. 전체 회귀·스모크·새 인증 E2E·frontend build·브라우저 QA·코드 리뷰. WORK_LOG/GATE_STATUS/TASK_BOARD/위협 모델/포트폴리오 한계를 동기화한다.

API 공통: /api/v1/auth/login, me, logout; /analysis, /evidence; /proposals 목록/상세/decision/execute/reconcile/audit. 내부 actor는 서버 principal이다. web 빌드는 web/dist이며 backend가 /와 /assets를 제공한다. 주요 변경은 실패 테스트→구현→검증 순서로 기록한다.
