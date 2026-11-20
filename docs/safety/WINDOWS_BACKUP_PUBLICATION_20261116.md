# Windows backup publication verification

Baseline: origin/improve/execution-recovery-20261109 at 23c22ef.
Original checkout preserved; isolated branch improve/reliability-review-20261116.

The Windows application sandbox rejected hardlink publication with WinError 5.
The fail-fast regression stopped at 51 passed / 1 failed in test_database_backup.
Windows now uses atomic rename, whose Windows contract refuses existing targets.
POSIX retains hardlink publication because POSIX rename may replace a destination.
No permission changes, replacement of an existing database, or copy-overwrite fallback.
A new regression creates a destination after validation and proves its bytes survive
and temporary files are removed when publication is refused.

Actual verification: backup and execution recovery 17 passed; synthetic API E2E
analysis -> proposal -> independent approval -> response loss -> reconciliation passed;
24 required package files present; git diff --check passed. Full regression: 201 passed / 1 failed (109.15s).
The remaining failure is test_real_runner_ready_health_and_eof_shutdown:
its first subprocess output line was not JSON. Cause not established; no complete
regression pass is claimed. Local log: reliability-test-fixed-20261116.log.
Environment: Python 3.13.16, CaseProof hash-pinned development environment, OpsPilot
src on PYTHONPATH. Editable packaging is separately blocked by setuptools interpreting
braces in the Windows sandbox temporary installation path as variable placeholders.
No external service writes or production data. No complete enterprise-readiness claim.


## Subsequent desktop diagnosis

The runner deliberately starts Python with -I, so the prior PYTHONPATH-only test
environment did not make OpsPilot importable. Normal editable installation with
existing dependencies succeeded, and an isolated `python -I` import verified the
installed package. All22 desktop-runtime tests then passed in8.47 seconds. No
production source or isolated-mode safety boundary was weakened for this result.
The subsequent elevated full run was196 passed /6 errors, all Windows10014 during
asyncio socketpair initialization (not six application assertion failures). A final
normal-runner full regression is in progress; do not report complete success yet.


## Completed normal-runner full regression

After the correct editable installation, the complete unchanged test collection
passed: 202 passed, 1 Starlette/httpx deprecation warning, 172.29 seconds, exit0.
Command: `python -m pytest -q --tb=short` using the documented Python3.13.16
environment. Local raw evidence: reliability-installed-20261116.log.
The earlier196/6 Windows initialization-error run is retained, not erased.
This is a local synthetic regression result, not cross-platform or production certification.
