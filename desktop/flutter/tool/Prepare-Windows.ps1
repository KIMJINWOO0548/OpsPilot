param([Parameter(Mandatory)][string]$Flutter)
$ErrorActionPreference = 'Stop'
$flutterExecutable = (Resolve-Path -LiteralPath $Flutter).Path
$project = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $project 'windows'
Push-Location -LiteralPath $project
try {
    if (!(Test-Path -LiteralPath $runner)) {
        # Flutter's default create mode adds missing files and leaves the workbench source intact.
        $sourceBefore = (Get-FileHash -LiteralPath 'lib/main.dart').Hash
        & $flutterExecutable create --no-pub --platforms=windows --project-name opspilot_review_windows .
        if ($LASTEXITCODE) { throw 'Windows runner generation failed' }
        if ((Get-FileHash -LiteralPath 'lib/main.dart').Hash -ne $sourceBefore) {
            throw 'Runner generation unexpectedly changed the review UI source'
        }
    }
    & $flutterExecutable build windows --release
    if ($LASTEXITCODE) { throw 'Flutter Windows build failed' }
} finally { Pop-Location }
