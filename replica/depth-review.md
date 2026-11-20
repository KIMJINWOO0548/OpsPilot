# OpsPilot temporal review workflow — 2026-11-06

## Audit and reference
Primary reference: [LangChain human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop), public documentation read 2026-11-06. It documents tool-call interruption, persisted state and approve/edit/reject/respond decisions. We studied the review-before-action pattern; no agent/model call or proprietary content was submitted. This is a framework reference, not an equal-condition hosted product benchmark.

OpsPilot remains a deterministic synthetic evidence/mock-action prototype. Before this work phase1 1d591c6 showed saved context and current ACL readiness, while sibling 1dd520e separately compared two observation times. Neither branch alone offered the combined review journey. A user manually transferring clocks risks reviewing a different instant or confusing historical support with current authorization.

## Integration and new behavior
Merge base is 5bd503f. Parent performed a normal no-commit merge of 1dd520e into phase2. Conflicts were limited to Proposal/Comparison types in main.tsx and appended WORK_LOG history. Both were retained. API auto-merge was inspected: comparison uses a query-only transaction; review_context still appears only when current evidence is reviewable. The merge itself is preservation, not newly invented functionality.

New behavior connects the two: authorized draft detail → compare exact saved effective/known instants against now; comparison → current analysis of the same asset using one shared current timestamp. Both are read-only. Fresh analysis does not create a proposal or approve it. Existing separate draft, independent approval, fingerprint, current evidence ACL and original-approver receipt recovery continue to govern mock execution. Unauthorized/missing draft context disables transfer. The helper uses the saved claim and both original clocks rather than displayed minute precision.

## Acceptance and verification
- New helper RED: missing exported handoff functions; GREEN: all 6 frontend tests. Exact saved clock transfer, revoked/missing context, fresh equal clocks and historical read-only classification tested.
- Existing temporal regressions cover correction/unchanged/ACL snapshot and read-only DB tables. New combined HTTP regression follows saved context → comparison → unchanged proposal → independent approval → lost response → same receipt recovery. Passed in the 193-test host suite; actual logs were inspected.
- TypeScript noEmit passed using existing desktop node_modules through ignored .pytest_cache/typecheck.json; no install or desktop write. No bundle/browser claim from typecheck.
- Performance/workflow acceptance: historical comparison to fresh analysis requires one explicit action rather than switching page, resetting times and submitting; this is local control-path counting, not measured human task time. Zero comparison proposal/work-order mutations, zero hidden evidence disclosures in ACL tests, single receipt after loss/retry are functional safety metrics, not latency claims. External real-agent executor comparison is NOT_RUN.
- Design/a11y acceptance: native button with 44px minimum and mobile stacked callout, explicit read-only explanation; existing KST labels and approval context retained. Native Enter and 390px/1440px layout checks passed in Chrome156; screen-reader speech and professional accessibility review remain untested. Original OpsPilot styling retained; no competitor visual assets copied.

## Remaining gaps
Production agent/tool execution, edited-action reapproval, durable distributed recovery, OIDC, ACL history, real evaluation corpus, professional accessibility and latency/load benchmarks remain out of scope. Current ACL is used for historical comparison; historical permissions are not reconstructed. Same-condition competitor benchmark NOT_RUN. Replica output is a scoped functional inventory and cannot establish competitive superiority or overall quality.

## Scoped design checks
Installed Replica contrast.py executed against `replica/design/depth-tokens.json`; all declared new text/focus pairs passed AA. See depth-contrast.json and depth-components.md. First token-shape probe returned unknown-token errors; color mapping was corrected before these recorded checks. This does not certify inherited controls or assistive-technology behavior.

## Phase2 host verification — completed
Parent host logs were read directly from phase2/verification/OpsPilot. `python -m pytest -q --basetemp=<owned tmp>`: **193 passed**, 1 existing warning, exit0,154.92s wall time. Includes the merged temporal regressions, current evidence ACL/review context and new combined saved-review→compare→approval→response-loss recovery test. `scripts/smoke_demo.py`: PASS (2.82s). `scripts/eval_smoke.py`: synthetic8/8 (0.40s), not external evaluation. Frontend6 and TypeScript noEmit exit0. No package installation.

Executed `scripts/build_browser_probe.mjs` and `scripts/check_temporal_handoff_browser.cjs` against Chrome156 with intercepted local synthetic API; see the browser verification below.

## Phase2 actual browser verification — completed

Chrome156.0.8078.80 executed the real source UI with synthetic intercepted API responses. At1440px and390px the document had0px horizontal overflow and no page exceptions. This is actual browser behavior/layout evidence, not live-backend E2E, assistive-technology certification or competitor testing. Backend behavior is covered separately by the full host suite.

Native draft-review click carried exact saved seconds/milliseconds into comparison. Enter on the current-analysis button made only `/api/v1/analysis/compare` and `/api/v1/analysis` requests; fresh clocks matched and no proposal/approval was submitted. The action measured44px at both widths. Mobile screenshot reviewed: stacked callout remained readable; citation tables retain contained horizontal scrolling. [Result](evidence/browser/result.json), [desktop](evidence/browser/temporal-handoff-1440.png), [mobile](evidence/browser/temporal-handoff-390.png).
