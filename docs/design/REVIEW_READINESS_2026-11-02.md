# 현재 근거 검토 상태 · 2026-11-02

검토자 문서 ACL 회수·삭제·만료 또는 저장 조치 변경 뒤 서버는 승인/최초 실행을 거부하지만, 기존 콘솔은 비어 있는 근거에 “요청 원본에서 확인”을 안내하며 버튼을 활성화했다. 원본에도 숨겨진 근거가 없으므로 사용자가 승인 가능 상태로 오해할 수 있었다.

## 변경

- 제안 상세의 `evidence_reviewable`은 현재 principal로 조회한 근거, 저장 조치·fingerprint, 현재 시점 재평가를 확인한다. GET은 제안을 만료시키거나 작업을 만들지 않는다. 숨김·삭제·변경의 세부 사유나 비인가 문서 메타데이터는 구분해서 반환하지 않는다.
- 콘솔은 명시적인 `true`일 때만 승인·거절·최초 실행을 허용한다. 검토 불가 안내, 정확한 빈 상태, 현재 자산을 유지하는 재조사 경로를 제공한다. 상단 `APPROVED` 건수는 “승인 완료”로 표시한다.
- 영수증 복구는 현재 근거가 없어도 원 승인자에게 계속 허용한다. 이미 실행한 mock 작업을 다시 만들지 않는다.
- 목록/상세 새로고침 및 변경 요청 성공·실패 뒤 두 화면을 함께 갱신한다. 상세 조회 실패 시 이전 요청의 조작을 제거하며, 목록의 요청을 다시 선택해 GET으로 복구할 수 있다. 최초 변경 오류는 후속 조회 오류에 가려지지 않는다.

준비 상태는 조회 시점의 안내다. 이후 권한·근거 변경은 서버의 실제 변경 요청에서 다시 검증하며, 화면의 활성 버튼이 최종 승인을 보증하지 않는다.

## 검증과 화면

Linux Python 3.12.14 / Node 24.19.0 / pnpm 11.25.0에서 기존 전체 167개 → 변경 후 **169개 통과**, API 회귀 **10 실패 → 10 통과**, 프런트 **1 실패 → 5 통과**를 확인했다. 기존 권한 음성 테스트는 근거 검토 가능 값을 `true`로 주어 권한 조건 자체를 계속 검증한다. Ruff·TypeScript/build·mock E2E·패키지24개·pip check와 평가 계약 예제도 통과했다. 합성 스모크8/8은 연구 성능 수치가 아니다.

개발·디자인·독립 QA·최종 읽기 전용 코드 검토를 나눠 수행했다. 실제 FastAPI·임시 SQLite·Chromium에서 다음을 확인했다.

| 경로 | 관측 결과 | 화면 |
|---|---|---|
| 수정 전 ACL 회수 | 인용 없음에도 승인 버튼 활성, 원본 확인 안내 | [수정 전](review-readiness-2026-11-02/before-unavailable-desktop.png) |
| 수정 후 ACL 회수 | 검토 불가 안내·승인/거절 잠금, 비인가 근거 미표시 | [수정 후](review-readiness-2026-11-02/after-unavailable-desktop.png) |
| 승인 후 ACL 회수 | 최초 실행 버튼 두 개 잠금 | 실제 브라우저 assertion |
| 응답 유실 후 ACL 회수 | 복구 버튼 활성 → SUCCEEDED, work order 1건 | [복구 가능](review-readiness-2026-11-02/after-recovery-available-desktop.png) |
| 조회 이후 근거 회수 | 변경 요청409 뒤 상세·목록·대기 건수 동기화 | 독립 QA assertion |
| 실행 응답과 상세 조회 모두 유실 | 이전 실행 버튼 제거 → 요청 재선택 GET으로 SUCCEEDED 복구, 실행POST1회·작업1건 | 독립 QA transport 주입 |
| 모바일390px | 문서 clientWidth/scrollWidth 모두390, 상세·경고·버튼 표시. 표 내부 스크롤 유지 | [모바일](review-readiness-2026-11-02/after-unavailable-mobile.png) |

[명령·소스 hash](../../verification/proposal-review-local-2026-11-02.json), [pytest XML](../../verification/proposal-review-pytest-2026-11-02.xml), [독립 QA](../../verification/proposal-review-qa-2026-11-02.json), [최종 화면 검사](../../verification/proposal-review-design-2026-11-02.json)를 보존했다. 화면 검증의 콘솔 오류·페이지 예외는0건이다. QA 행동 검사는 마지막 문구 조정 전이며 최종 디자인 검사는 조정 후 빌드를 사용했다. 모바일 도구 인자 오류는 검증 스크립트에서 수정하고 다시 캡처했으며 제품 결함으로 집계하지 않았다.

재현은 `tests/test_proposal_evidence_acl.py`와 `web/src/helpers.test.ts`를 실행한다. UI에서는 임시 engineer/approver 계정으로 초안을 만든 뒤 테스트 DB의 해당 문서 approver ACL을 제거하고, 승인함에서 상태 조회를 수행한다. 정상 자료·실계정·기존 사용자 DB를 변경하지 않는다. 테스트 서버3개는 모두 종료했다.

Windows WPF·설치기 실행, 화면 리더·대비 계측, 외부 배포와 실제 원격 장애는 이번 범위에서 검증하지 않았다. 기존 Starlette/httpx deprecation 경고1개가 남아 있다. G0/G1 연구 수용·95점 달성·운영 안전성 전체를 선언하지 않는다.

## 원격 게시 상태

로컬 구현 커밋은 `72978b04d71b807f32411abed5c5b7b77e94e4cb`다. 기존 GitHub connector로 `feat/proposal-review-readiness` 브랜치를 생성하는 요청이403 `Resource not accessible by integration`으로 거부됐다. 읽기 전용 재확인에서 해당 브랜치는 없고 main은 `caa8902afee209ad2b59aab883b49d114c3a586c`다. 우회·재시도·새 자격증명 생성은 하지 않았다. 새 변경의 push/PR/원격CI는 미실행이며 GitHub 연동 쓰기 접근 확인이 남은 차단이다. [게시 거부 기록](../../verification/proposal-review-publication-2026-11-02.json). 로컬 커밋·전체 binary patch·Git bundle·소스 ZIP으로 변경을 보존한다.
