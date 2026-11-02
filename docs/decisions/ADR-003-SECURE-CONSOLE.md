# ADR-003: 인증된 조사·승인 콘솔을 배포 단위로 묶는다

2026-10-20. 사용자의 최신 지시는 프로그램 전체와 실제 API 연결 UI를 배포 전제로 개발하는 것이다. 이에 기존 ADR-001의 UI 후행 순서를 이번 제품 경로에 한해 확장한다. G0/G1의 연구 수용·모델 성능·외부 검증은 별도이며 완료로 승격하지 않는다.

## 제품과 구성

대상은 제조 점검 요청을 조사하는 engineer와 독립 approver다. 로그인→권한 있는 근거 검색→두 시점 판정→조치 초안→승인→mock 실행·응답 유실 복구를 한 프로그램에서 수행한다. React/TypeScript/Vite 정적 빌드를 FastAPI가 같은 origin에서 제공한다. 기존 다크 콘솔의 업무 맥락은 유지하고 조사·타임라인·승인함, 한국어 상태 요약과 감사 이력으로 구조화한다.

## 인증과 데이터 경계

- 표준 라이브러리 PBKDF2-HMAC-SHA256(600,000회 이상, 사용자별 random salt)과 서버 저장 opaque session을 쓴다. JWT를 직접 구현하지 않는다. IdP/OIDC 연결은 이번 범위가 아니다. [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)를 2026-10-20 확인했다.
- 세션 token은 고엔트로피 random이며 DB에는 hash만 저장한다. HttpOnly/SameSite cookie·CSRF token·만료·로그아웃·실패 로그인 제한을 적용한다. HTTPS용 Secure cookie를 배포 설정으로 켠다. 계정은 관리 CLI로 명시 생성하며 자동 기본 비밀번호/공개 가입/권한 선택은 없다.
- 서버 DB의 principal만 actor를 결정한다. JSON role/tenant/team 위조가 승인·검색에 영향을 주지 않아야 한다. proposal 조회·목록·감사도 같은 tenant/team·소유/approver 정책을 따른다.
- SQLite evidence table/ACL에서 권한과 known_as_of를 먼저 필터하고 허용된 record만 결정적 엔진·lexical ranking에 전달한다. 초기 seed는 합성 문서다. 이는 Postgres RLS·대규모 hybrid RAG 구현이라는 주장이 아니다.
- 승인 snapshot·업무 분리·고유 외부 작업 키·영수증 복구는 유지한다. 실제 업무 시스템 쓰기는 추가하지 않는다.

## 배포와 검증

Node build stage + Python runtime container, non-root user, 고정 의존성 목록, healthcheck·영속 volume, loopback 기본 바인딩을 준비한다. Vite dev/preview를 production server로 쓰지 않는다([Vite production build](https://vite.dev/guide/build), [static deploy](https://vite.dev/guide/static-deploy), 2026-10-20 확인).

새 React 의존성은 UI 요구에 필요한 범위로만 추가하고 lockfile로 고정한다. backend는 새 인증 패키지 없이 기존 FastAPI/SQLite/표준 라이브러리를 사용한다. 실제 공개 배포, 외부 계정 연결, 데이터/가중치 다운로드, 유료 모델 호출은 실행하지 않는다. Docker가 없으면 build 성공을 선언하지 않는다.

완료 기준은 인증·권한 실패/정상 경로, DB 검색 선필터, 승인·동시성·복구 회귀, React typecheck/build, 실제 브라우저 핵심 경로·작은 화면 검증이다. 제한된 단일 인스턴스 포트폴리오 앱이며 SSO·Postgres outbox·실제 외부 장애·부하·독립 보안 리뷰·외부 모델 평가는 여전히 별도다.
