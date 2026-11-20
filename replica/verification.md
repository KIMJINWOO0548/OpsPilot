# 검증 기록 — 2026-11-06

호스트 전체 회귀 171 passed, exit 0. scoped parity 점수는 전체 제품 수용 판정이 아니다.

- 변경 전 Node helper tests: `node --test web/src/helpers.test.ts`, 5 passed, exit 0.
- 변경 전 `python scripts/eval_smoke.py --output .pytest_cache/eval-baseline.json`: 8/8, exit 0. 동일 작성 fixture에 대한 합성 일치이며 benchmark 아님.
- 신규 RED(호스트): `python -m pytest -q --basetemp=.pytest_cache/host-red-1106 tests/test_proposal_evidence_acl.py -k review_context`, 2 failed / 10 deselected, exit 1; 누락된 review_context의 KeyError.
- 기존 desktop TypeScript 의존성을 읽기 전용 재사용한 tsc --noEmit: exit 0. ignored .pytest_cache/typecheck.json의 절대 paths와 CSS 선언으로 검사했으며 설치/원본 의존성 변경은 없다. 최초 --baseUrl 시도는 TS7 제거 옵션으로 실패했고 paths로 수정했다. bundle build나 실제 브라우저 검증을 대신하지 않는다.
- 설치된 Replica parity.py를 features.csv에 실행: exit 0, 선택한 2개 기능만 점수화. 초기 상대 경로 오입력은 exit 2; 절대 경로 수정 뒤 성공.
- sandbox pytest는 기본 TEMP 디렉터리 생성 오류 후 명시 basetemp 재시도에서 TestClient 정지. 같은 원인으로 smoke 실행도 중단했다. 호스트에 동일 테스트를 위임했으며 sandbox 중단은 통과로 계산하지 않는다.
- 패키지/도구 설치, 전역 설정 변경, 실설비 write, 외부 모델 호출, 배포 없음. G0/G1 연구, 운영 수용, WPF/설치기/실제 브라우저 검증은 별도다.

## 최종 호스트 실행

coordinator가 기존 desktop 가상환경으로 실행한 원본 로그와 summary.json을 직접 확인했다.

| 명령 | 결과 |
|---|---|
| python -m pytest -q --basetemp=<owned verification/OpsPilot/tmp/pytest-full> | 171 passed, 1 기존 Starlette deprecation warning, 174.08초, exit 0 |
| python scripts/smoke_demo.py | analysis → proposal → approval → response loss → reconciliation PASS, exit 0 |
| python scripts/eval_smoke.py --output <owned verification/OpsPilot/eval.json> | 합성 8/8, exit 0 |

원본 실행 기록은 task workspace의 verification/OpsPilot/0-validation.log, 1-validation.log, 2-validation.log 및 summary.json이다. 본 저장소는 테스트용 DB·세션·영수증을 배포하지 않는다. 현재 전체 suite는 신규 2개 권한/읽기 회귀를 포함한다. Python suite와 TypeScript 검사는 통과했지만 이번 로컬 화면의 실제 브라우저 시각 검토와 production/외부 연구 검증은 미실행이다.

## Phase 2
See [depth review](depth-review.md) for new RED/GREEN, own-only measurement, merge preservation and explicitly remaining external checks. Prior phase1 results do not validate phase2.

## Phase2 host verification — completed
Parent host logs were read directly from phase2/verification/OpsPilot. `python -m pytest -q --basetemp=<owned tmp>`: **193 passed**, 1 existing warning, exit0,154.92s wall time. Includes the merged temporal regressions, current evidence ACL/review context and new combined saved-review→compare→approval→response-loss recovery test. `scripts/smoke_demo.py`: PASS (2.82s). `scripts/eval_smoke.py`: synthetic8/8 (0.40s), not external evaluation. Frontend6 and TypeScript noEmit exit0. No package installation.

Executed `scripts/build_browser_probe.mjs` and `scripts/check_temporal_handoff_browser.cjs` against Chrome156 with intercepted local synthetic API; see the browser verification below.

## Phase2 actual browser verification — completed

Chrome156.0.8078.80 executed the real source UI with synthetic intercepted API responses. At1440px and390px the document had0px horizontal overflow and no page exceptions. This is actual browser behavior/layout evidence, not live-backend E2E, assistive-technology certification or competitor testing. Backend behavior is covered separately by the full host suite.

Native draft-review click carried exact saved seconds/milliseconds into comparison. Enter on the current-analysis button made only `/api/v1/analysis/compare` and `/api/v1/analysis` requests; fresh clocks matched and no proposal/approval was submitted. The action measured44px at both widths. Mobile screenshot reviewed: stacked callout remained readable; citation tables retain contained horizontal scrolling. [Result](evidence/browser/result.json), [desktop](evidence/browser/temporal-handoff-1440.png), [mobile](evidence/browser/temporal-handoff-390.png).
