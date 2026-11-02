# 검토자 문서 권한 수정 — 2026-11-02

Rule: FASTAPI-AUTHZ-001. 심각도: High. 제안 상세·승인·최초 실행에서 저장된 작성자 대신 현재 인증된 사용자의 문서 ACL로 근거를 조회하도록 수정했다. 원래 요청과 fingerprint, 독립 승인·기존 영수증 복구는 유지한다.

## 실제 재현

가짜 SOP와 임시 계정/DB에서 제안 생성 후 approver의 문서 ACL을 회수했다. 수정 전에는 근거 목록이 비어도 제안 상세에 evidence ID·출처·locator·checksum이 반환됐고 승인·최초 실행도 HTTP 200이었다. 새 회귀 8개 중 이 세 사례가 실패하고 나머지5개는 통과했다. 실제 회사 문서·사용자 계정·외부 작업에 연결하지 않았다.

`api.py`의 proposal detail, decision, execute에서 현재 principal을 SQL ACL 선필터와 최신 시점 평가에 일관되게 적용한다. 원래 저장 요청은 fingerprint 검증에 유지한다. 권한이 없으면 인용을 비우고 승인·최초 실행은 기존 일반화된 HTTP409/EXPIRED로 차단한다. 오류에 원문·민감 인용 정보를 넣지 않는다.

삭제·권한 회수·유효기간 만료를 승인 전/승인 후 최초 실행 전에 각각 검사했다. 작성자 승인 금지, 정상 독립 승인, mock 응답 유실, ACL 회수 후 기존 영수증 복구·동일 영수증 재시도 및 write1건을 유지했다.

## 실제 검증

기존 Python3.12.14 가상환경/의존성을 재사용하고 `PYTHONPATH`, `OPSPILOT_DB`, pytest 임시 경로를 격리 사본/새 테스트 DB로 지정했다. 설치·전역 설정·실제 사용자 DB 변경은 없다.

| 검사 | 결과 |
|---|---|
| 수정 전 기존 전체 pytest | 159 passed, deprecation warning1 |
| 새 회귀 수정 전 | 3 failed / 5 passed |
| 새 회귀 수정 후 | 8 passed, warning1 |
| 수정 후 전체 pytest | 167 passed, warning1 |
| Ruff src/tests/scripts | 통과 |
| mock 승인·응답 유실·복구 smoke | 수정 전/후 통과 |
| 합성 eval smoke | 8/8, 외부 benchmark 아님 |
| 제공 eval_compare 계약 예제 | 통과, 모델 성능 아님 |
| check_package | 필수24파일 누락0 |
| 독립 읽기 코드 검토 | 해당 범위 추가 중요 결함 없음 |

실행 로그/XML은 업로드 제외한 `.local/acl-validation/`, 공유 가능한 요약/변경 파일 해시는 `verification/reviewer-evidence-acl-2026-11-02.json`에 있다. 경고는 기존 Starlette TestClient/httpx deprecation이며 의존성은 바꾸지 않았다.

## Windows 및 보존 범위

초기 샌드박스 검사는 pytest 기본 임시 폴더 생성 실패(71pass/88setup errors)였고, 사본 안의 임시 경로로 바꾼 실행은 소켓 단계에서 진행되지 않아 중단했다. 독립 Python probe도 앱 import 없이 socketpair/asyncio 연결 timeout을 관측했다. 일반 Windows 실행으로 위 검사를 완료했으며 과거 WinError10014는 이번 호스트 검사에서 재현되지 않았다. OS·보안 설정 변경·소켓 예외 무시 패치는 넣지 않았다.

전체 검사에는 기존 desktop runtime의 ready/health/EOF 시험이 포함되나 `-I` child는 기존 가상환경에 설치된 원본 package를 사용한다. 해당 Desktop 코드는 사본과 같고 수정하지 않았다. 변경한 ACL API는 사본을 직접 import하는 회귀/전체 pytest/smoke로 검사했다. WPF UI·설치기·출시 패키지 수용은 새로 검사하지 않았다.

원본 제품 폴더는 보존하고 독립 사본만 수정했다. 검증 당시 Git 작성자 설정이 없어 우선 `refs/codex/source-baseline`의 tree `739c31d8366eddc40c39e745c270085d082ce3ef`로 소스를 보존했다. 이후 기존 사용자 소유 프로젝트에서 확인된 GitHub noreply 작성자를 저장소 로컬에만 설정해 기준선과 ACL 수정을 별도 커밋으로 보존한다. 신원을 만들거나 전역 설정을 바꾸지 않았다. GitHub 공개 게시 승인은 OpsPilot 소스에만 적용되며 Store·웹 배포 승인이 아니다. 이 수정은 연구 게이트 수용·운영 안전 전체·95점 달성을 뜻하지 않는다.
