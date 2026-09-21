@echo off
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
echo ========================================
echo  VarunOps Repair / Database Upgrade
echo ========================================
echo.
if not exist "%PY%" (
  echo Virtual environment missing. Running full setup...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_local.ps1"
  if errorlevel 1 goto :failed
)

echo [1/5] Project package check
"%PY%" -c "import sys; from pathlib import Path; sys.path.insert(0,str(Path.cwd())); import varunops, core; print('Project imports OK')" || goto :failed

echo [2/5] Migration status
"%PY%" manage.py showmigrations core || goto :failed

echo [3/5] Applying all pending migrations
"%PY%" manage.py migrate --noinput || goto :failed

echo [4/5] Django system check
"%PY%" manage.py check || goto :failed

echo [5/5] Verifying dashboard queries and serializers
"%PY%" manage.py verify_workspace || goto :failed

echo.
echo REPAIR COMPLETE - your existing data was preserved.
echo Now run START_VARUNOPS.bat
pause
exit /b 0

:failed
echo.
echo REPAIR FAILED. Copy the error shown above if you need help.
pause
exit /b 1
