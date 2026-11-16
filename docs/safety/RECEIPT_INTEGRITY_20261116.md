# Recovery receipt integrity — 2026-11-16

## Reproduction and correction
The original implementation confirmed SUCCEEDED for a receipt whose action no longer matched the approved proposal (execute and reconcile), or whose idempotency key changed (reconcile). Before correction the four new focused cases produced 3 failures and 1 pass.

Both recovery paths now validate the proposal ID, derived operation key, approved action, and a nonempty receipt ID. Execute searches by operation key or proposal ID, so a damaged key cannot cause another insert. A mismatch preserves the receipt and returns UNKNOWN_RECONCILE rather than success. This deliberately does not fabricate absence-of-side-effect evidence or unlock retry.

## Evidence
- Focused execution recovery: 26 passed, 1 Starlette deprecation warning, 97.65 seconds.
- New matrix: execute/reconcile × action/key/blank receipt × APPROVED/UNKNOWN_RECONCILE/SUCCEEDED (18 cases). APPROVED reconciliation remains 409.
- scripts/smoke_demo.py: LOCAL E2E PASS (analysis→proposal→approval→response loss→reconciliation).
- scripts/eval_smoke.py: 8/8 synthetic checks, fixture SHA256 66c9ab2f5edac23c7117649c79a43a45480c8bb383a13eca62998d4ce564dca5. Not a benchmark.
- Full regression: 220 passed, 1 Starlette deprecation warning in 199.08 seconds (exit 0).
- Test runner: sibling CaseProof_Enterprise/.venv/Scripts/python, with pytest project pythonpath. OpsPilot .venv lacks pytest; its unsuccessful launch is not counted as a test.

Independent review: no blocking findings; focused recovery suite independently rerun, 26 passed in 50.83 seconds (one deprecation warning). Full 220-case suite was run by implementation worker, not repeated by reviewer.

## Boundaries
Only owned temporary SQLite databases were mutated in fault injection. User data, main, and UI are unchanged. Tests cover this local mock transaction model, not remote service execution or production process crash recovery. A coordinated alteration of proposal and receipt is not prevented by these consistency checks. Missing approver delegation, external provider reconciliation, production auth and broader G0/G1 acceptance remain separate requirements.
