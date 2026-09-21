@echo off
setlocal
set /p CODE=Enter the 8-digit pairing code shown in VarunOps Employee Portal: 
if "%CODE%"=="" exit /b 1
if exist "%ProgramData%\VarunOps\VarunOpsAgent.exe" (
  "%ProgramData%\VarunOps\VarunOpsAgent.exe" --pair %CODE%
) else (
  python "%~dp0varunops_agent.py" --pair %CODE%
)
pause
