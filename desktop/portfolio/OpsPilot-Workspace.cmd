@echo off
setlocal
set "PORTFOLIO_DIR=%~dp0"
if not exist "%PORTFOLIO_DIR%backend\python\python.exe" (
    echo OpsPilot-X could not start. Extract the full bundle before launching.
    exit /b 1
)
"%PORTFOLIO_DIR%backend\python\python.exe" -I -B -m opspilot_x.workspace %*
exit /b %ERRORLEVEL%
