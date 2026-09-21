@echo off
setlocal
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo.
echo =============================================
echo   VarunOps RAM64 Agent Hotfix 4.2.1
echo =============================================
echo.
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_agent.ps1"
if errorlevel 1 (
  echo.
  echo HOTFIX FAILED. Run CHECK_AGENT.bat and keep the window open.
  pause
  exit /b 1
)
echo.
echo HOTFIX SUCCESS. Refresh VarunOps Employee page in 10-20 seconds.
pause
exit /b 0
