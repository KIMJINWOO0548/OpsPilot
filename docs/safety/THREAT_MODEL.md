# 위협 모델과 릴리스 조건 (2026-10-21)

## 현 구현의 명시적인 보안 결함 (회피하지 말 것)
1. **서버 계정 인증:** PBKDF2 password hash·opaque session hash·HttpOnly/SameSite cookie·CSRF·8시간 만료·logout·로그인 시도 제한·계정 비활성화·세션 폐기 CLI를 구현했다. JSON actor 대신 서버 users의 principal을 사용한다. OIDC/SSO·암호 변경/재활성화·MFA·분산 rate limit·독립 침투 검증은 없다.
2. **SQLite 데모:** 스토어와 모의 업무 API가 같은 DB/프로세스에 있음. 진정한 외부 네트워크 응답 유실과 distributed saga/outbox 테스트 없음.
3. **DB 선필터:** 신뢰된 합성 fixture를 최초 수집한 뒤 evidence/ACL table의 tenant/team/role·known_as_of를 SQL bound parameter로 필터하고 허용된 원문만 ranking/EIE에 보낸다. SQLite는 DB 사용자별 RLS가 없으므로 DB 파일 관리자에 대한 격리는 아니다. 대용량 인덱스·실원본 수집은 없다.
4. **객체 권한:** proposal 목록/상세/감사/decision/execute/reconcile은 tenant/team 및 소유자/approver 범위를 검사한다. 범위 밖 객체는 없는 객체와 같이 404다. 독립 승인·원 승인자의 실행·멱등성·복구는 정책/DB가 결정한다.
5. **시간 경계:** 사용자가 제출한 `known_as_of`를 통한 historical replay는 read-only로 제한했지만 실제 서비스 전 clock trust, DB recorded_at, source lifecycle 검증 필요.
6. **문서 인젝션 시연의 한계:** 현재 LLM이 없으므로 프롬프트 인젝션에 대한 회복력을 검증했다고 말하면 안 됨.

## 공개 사용을 위한 선행 필수 요건
- 기업 IdP/OIDC 연동 필요성·전체 계정 수명주기 확정. 서버 유도 actor·비활성화·세션 폐기는 로컬 구현이며 외부 보안 인증은 아님.
- 최소 권한 DB 계정 및 tenant-scoped SQL, 문서 ACL prefilter + 재검증
- Postgres 트랜잭션/outbox, 별도 mock remote write 서버 및 receipt endpoint, 장애 주입
- Rate-limit, audit append-only, redaction, SSRF 및 tool allowlist, 보안 리뷰
- Container/image scanning, 종속성 lockfile/라이선스 점검, `.env` 관리
- 403·404 응답에서 비인가 객체 존재 여부 유추 방지와 API 로그 비밀 제거
- 실데이터 없이도 end-to-end 안전 경계 재현한 테스트 통과

**릴리스 차단:** 외부 포트 공개, 실제 시스템 write, 권한 없는 데이터 노출, 미승인 write, 외부 부작용 중복이 발생할 수 있는 경우.

## 이번 리뷰에서 수정한 경계

- 인증된 타 조직 사용자에게 고정 시나리오 자산 ID를 반환하던 경로를 DB 허용 자산만 반환하도록 변경했다.
- 외부 조직의 쓰기 API가 403/404 차이로 초안 존재를 노출하던 경로에 객체 조회 정책을 먼저 적용했다.
- `q` 1001자가 내부 ValueError/500이 되던 입력에 API 길이 제한/422를 적용했다.
- request/fingerprint를 유지한 채 저장된 action만 바꿔 승인·실행할 수 있던 계약 위반을 재현했다. 승인/실행에서 저장 action과 재평가 조치를 비교하고 변조 시 EXPIRED/409, mock 작업 0건으로 차단한다. 이는 DB 관리자 공격 전체를 방어하는 서명 체계라는 주장이 아니다. hash는 서버 비밀키 전자서명이 아니며 DB 전체를 함께 변조할 권한에는 별도 신뢰 경계가 필요하다.

HTTPS ingress·정확한 proxy/host 설정·요청 크기 제한·비밀 로그 마스킹·일관된 DB backup/restore는 [배포 안내](../DEPLOYMENT.md)를 따른다. 인증정보는 `.local`/환경 변수에만 두고 이미지/문서에 포함하지 않는다. 감사 table은 append-only DB 권한이나 외부 불변 저장소로 강제하지 않았으며 관리자가 수정할 수 있다.

## 회수·복구 경계 (ADR-004)

비활성화와 세션 삭제는 같은 쓰기 트랜잭션이다. 로그인 해시 계산 중 회수되는 race는 세션 세대 번호를 발행 직전 재검증해 차단한다. 폐기는 기존 세션을 거부하되 정상 새 로그인은 허용하고, disable은 새 로그인도 막는다. 이미 시작된 HTTP 요청을 취소하는 보장은 없다. 모든 검증은 임시 계정/DB에서 수행했고 실제 로컬 검증 계정을 비활성화하지 않았다.

백업은 읽기 전용 원본+SQLite backup API, 무결성·필수 table 확인, 새 목적지 원자 게시를 사용한다. 복원은 기존 DB를 덮어쓰지 않고 저장 세션을 전부 제거한다. 단, 백업 이후 변경한 계정 상태·암호·감사 내용은 snapshot으로 돌아가므로 별도 회수 목록과 대조해야 한다. 복원 파일의 존재만으로 현재 권한 정책과 운영 복구 수용이 끝난 것이 아니다.
