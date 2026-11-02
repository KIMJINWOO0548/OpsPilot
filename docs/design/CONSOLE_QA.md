# 인증 콘솔 QA 기록 · 2026-10-21~23

설계는 [ADR-003](../decisions/ADR-003-SECURE-CONSOLE.md), 실행은 [DEPLOYMENT](../DEPLOYMENT.md)를 따른다. 기존 업무 흐름의 정보 밀도를 유지하면서 로그인·조사·두 시점 이력·승인함으로 나눴다. 시스템 폰트와 CSS를 사용하며 외부 이미지·폰트를 업로드/다운로드하지 않았다. 실제 화면 검증은 CUA 브라우저 도구로 수행했다. Figma 업로드나 외부 사용자 테스트를 했다는 뜻은 아니다.

| 확인 경로 | 관측 결과 | 근거 |
|---|---|---|
| 로그인 | 관리 CLI로 만든 로컬 검증 계정으로 로그인, 서버 principal 표시 | [로그인](console-2026-10-22/login.png) |
| A-103 현재 분석 | SUPPORTED, 센서 진단 우선, SOP-A103-v2와 checksum 표시 | 실제 브라우저 AX 상태·API 응답 확인 |
| 근거 타임라인 | v1 대체됨, v2 현재 유효, valid 구간과 recorded 시점 분리 | [타임라인](console-2026-10-21/timeline.png) |
| 작성자 승인 금지 | engineer의 승인/거절 버튼 비활성 | 브라우저 상태·API 권한 테스트 |
| 독립 승인 | 로그아웃 후 reviewer 로그인, 초안 hash/근거를 확인하고 승인 | 브라우저에서 APPROVED 관측 |
| 유실·복구 | mock 유실 → UNKNOWN_RECONCILE → 영수증 복구 → SUCCEEDED, 감사 4건 | [복구 완료](console-2026-10-21/approval-recovered.png) |
| A-105 모순 | CONFLICT, 조치 없음, 초안 버튼 비활성 | [충돌 차단](console-2026-10-22/conflict-blocked.png) |
| A-104 과거 | 유효/관측 9월 20일에 manual_inspection, v1만 인용. 과거 초안 비활성·읽기 전용 안내, 현재 A-103에서는 버튼 활성 | [과거 읽기 전용](console-2026-10-22/historical-read-only.png), [정상 현재 분석](console-2026-10-22/investigation.png) |
| 작은 화면 | 390px override 요청 시 실제 DOM clientWidth/scrollWidth 모두 375, 본문·모바일 메뉴 표시 | [캡처](console-2026-10-21/mobile-approval.png). 캡처 축척이 비정상이라 시각 QA 근거는 제한적 |

브라우저에서 날짜 입력을 Playwright fill로 조작할 때 값이 React state에 반영되지 않은 도구 동작을 관측했다. AX setValue로 입력 후 표시된 날짜를 확인하고 분석했으며, 결과에 2026-09-20 두 시점과 v1이 표시됐다. 값이 바뀌지 않은 첫 분석을 과거 재현 성공으로 계산하지 않았다.

## 발견·수정한 UI 경계

- 과거 SUPPORTED 결과에서도 초안 버튼이 활성화됐다. 서버는 이미 1시간 이내 현시점만 초안 작성 가능하도록 차단했으나 UI 안내가 맞지 않았다. `freshForProposal`의 실패 테스트(미export) 후 현재/과거/미래/잘못된 날짜 경계를 구현하고 읽기 전용 문구·비활성 버튼을 적용했다. 시계 차이가 있을 수 있으므로 서버 검증이 최종 권한이다.
- 실행·복구 버튼을 모든 approver에게 보여주던 조건을 원 승인자 일치로 제한했다. helper 회귀 1 failed → green을 확인했다. API의 거부 정책도 유지한다.
- 자산 자동완성은 서버의 ACL-filtered 자산 목록을 사용하고 로그아웃하면 지운다. 검색어 길이와 asset 길이를 제한한다. 실제 문서 언어에 맞는 검색 예시를 표시한다.
- EXPIRED 안내와 응답 유실·복구·근거 변경 감사 코드를 한국어로 표시한다. raw JSON은 접힌 상세에서만 본다.

## 검증 범위와 남은 것

label 연결, 버튼 상태, live 상태·오류 표시, 메뉴 이동, 실제 로그인·API·복구 경로, 작은 화면의 가로 넘침을 확인했다. 화면 리더·색 대비 계측·브라우저별 자동 E2E·완전한 모바일 시각 검사·외부 사용자 검토는 하지 않았다. 복구는 같은 SQLite 원장의 mock이며 실제 원격 시스템 장애 검증이 아니다. 첫 screenshot fullPage 호출은 실패했고 기본 viewport 캡처로 기록했다.

## 2026-10-23 · 컨테이너 이미지의 실제 Chrome 확인

CUA Chrome extension으로 서비스8000의 로그인 화면을 렌더링했다. 인증 후 업무 경로는 동일 이미지의 임시 컨테이너18010에서 검증했다. non-root/read-only·tmpfs DB·loopback 바인딩을 사용했고, 기존 서비스 volume/계정은 변경하지 않았다. 아래는 자동 단위 테스트 수에 합산하지 않는 실제 UI 관측이다.

| 확인 경로 | 관측 결과 | 근거 |
|---|---|---|
| engineer 로그인·A-103 현재·타임라인 | 서버 principal, 센서 진단 우선, v1 대체/v2 현재, 초안 활성 | Chrome AX 상태 |
| 작성자 승인 잠금·독립 승인 | 작성자 승인 비활성, reviewer 로그인 후 승인 | Chrome 버튼 상태와 승인 결과 |
| mock 응답 유실·복구 | 영수증 확인 필요 → 실행 완료, 감사4건 | [실행 완료 화면](console-2026-10-23/chrome-recovered.jpg) |
| engineer A-105 모순 | 근거 충돌·조치 없음·초안 비활성 | [충돌 화면](console-2026-10-23/chrome-conflict.jpg) |
| engineer A-104 과거 | 두 시점9/20 12:00, 수동 점검·v1만 인용·과거 읽기 전용·초안 비활성 | [과거 화면](console-2026-10-23/chrome-historical.jpg) |

승인·복구 후 콘솔 warn/error는0건이었고, 별도 탭의 충돌/과거 확인에서도 [캡처한 콘솔](../../verification/chrome-console-2026-10-23.json)은 빈 배열이었다. 기존 탭의 제어 연결이 끊겨 새 Chrome 탭에서 나머지를 확인했다. Playwright date fill이 state에 반영되지 않은 첫 분석은 과거 성공으로 계산하지 않았고, AX setValue로 표시 날짜를 확인한 뒤 실행했다. fullPage 캡처는 시간 초과돼 viewport 캡처를 저장했다.

검증 후 임시 컨테이너·DB는 제거했고 실제 서비스8000 로그인 화면을 열어 두었다. [검증 조건·현재 상태](../../verification/reboot-final-2026-10-23.json). 이번에는 모바일·화면 리더·브라우저 자동회귀를 재검증하지 않았다. Windows 전체 테스트 실패는 별도 미해결이며 Chrome 성공이 이를 대체하지 않는다.
