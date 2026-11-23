@echo off
setlocal
set "PORTFOLIO_DIR=%~dp0"
if not exist "%PORTFOLIO_DIR%backend\python\python.exe" (
    echo OpsPilot-X could not start. Extract the full bundle before launching.
    pause
    exit /b 1
)
"%PORTFOLIO_DIR%backend\python\python.exe" -I -B "%PORTFOLIO_DIR%launch_opspilot.py" %*
if errorlevel 1 (
    if "%~1"=="" pause
    exit /b 1
)
exit /b 0
