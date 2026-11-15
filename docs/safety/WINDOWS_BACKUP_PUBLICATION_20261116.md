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
24 required package files present; git diff --check passed. Full regression pending.
Environment: Python 3.13.16, CaseProof hash-pinned development environment, OpsPilot
src on PYTHONPATH. Editable packaging is separately blocked by setuptools interpreting
braces in the Windows sandbox temporary installation path as variable placeholders.
No external service writes or production data. No complete enterprise-readiness claim.
