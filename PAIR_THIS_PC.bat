@echo off
setlocal
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo This pairing helper needs IT administrator approval because the VarunOps agent credential is protected.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
set /p CODE=Enter the 8-digit pairing code from the Employee Portal: 
if "%CODE%"=="" exit /b 1
if not exist "%ProgramData%\VarunOps\VarunOpsAgent.exe" (
  echo VarunOps Agent is not installed on this PC.
  pause
  exit /b 2
)
"%ProgramData%\VarunOps\VarunOpsAgent.exe" --pair %CODE%
pause
