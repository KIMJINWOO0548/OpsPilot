$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv')) { py -3 -m venv .venv }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) { throw 'Install Node.js 24 and pnpm 11, then run again.' }
& $python -m pip install -c requirements-runtime.lock -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Push-Location web
try {
    & pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'Console dependency installation failed.' }
    & pnpm build
    if ($LASTEXITCODE -ne 0) { throw 'Console build failed.' }
} finally { Pop-Location }
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $python scripts\smoke_demo.py
if ($LASTEXITCODE -ne 0) { throw 'Mock E2E failed.' }
Write-Host 'Provision engineer and independent approver accounts with scripts/manage_users.py. See docs/DEPLOYMENT.md.'
Write-Host 'Open http://127.0.0.1:8000 in your browser. Ctrl+C stops server.'
& $python -m uvicorn opspilot_x.api:app --host 127.0.0.1 --port 8000
