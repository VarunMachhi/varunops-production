@echo off
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo VarunOps has not been set up yet.
  echo Running setup first...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_local.ps1"
  if errorlevel 1 (
    echo.
    echo Setup failed. Read the error above.
    pause
    exit /b 1
  )
)

if not exist "%~dp0varunops\settings.py" (
  echo ERROR: varunops\settings.py is missing. Re-extract the complete ZIP.
  pause
  exit /b 1
)

REM Self-heal Python package markers if a Windows extractor omitted them.
if not exist "%~dp0varunops\__init__.py" >"%~dp0varunops\__init__.py" echo """VarunOps Python package marker."""
if not exist "%~dp0core\__init__.py" >"%~dp0core\__init__.py" echo """VarunOps Python package marker."""
if not exist "%~dp0core\management\__init__.py" >"%~dp0core\management\__init__.py" echo """VarunOps Python package marker."""
if not exist "%~dp0core\management\commands\__init__.py" >"%~dp0core\management\commands\__init__.py" echo """VarunOps Python package marker."""
if not exist "%~dp0core\migrations\__init__.py" >"%~dp0core\migrations\__init__.py" echo """VarunOps Python package marker."""

"%PY%" -c "import sys; from pathlib import Path; sys.path.insert(0,str(Path.cwd())); import varunops, core" || (
  echo ERROR: The VarunOps project package cannot be imported.
  pause
  exit /b 1
)

echo.
echo Checking database updates...
"%PY%" manage.py migrate --noinput
if errorlevel 1 (
  echo.
  echo ERROR: Database migration failed. Run REPAIR_VARUNOPS.bat and read the error.
  pause
  exit /b 1
)

"%PY%" manage.py check
if errorlevel 1 (
  echo.
  echo ERROR: Django system check failed. Run REPAIR_VARUNOPS.bat.
  pause
  exit /b 1
)

REM Catch schema/API serialization problems before opening the browser.
"%PY%" manage.py verify_workspace
if errorlevel 1 (
  echo.
  echo ERROR: Workspace verification failed. Run REPAIR_VARUNOPS.bat for details.
  pause
  exit /b 1
)

echo.
echo VarunOps is starting at http://127.0.0.1:8000/
echo Keep this window OPEN while using the site.
echo Press Ctrl+C to stop the server.
echo.
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000/console/'"
"%PY%" manage.py runserver 127.0.0.1:8000
set "CODE=%ERRORLEVEL%"
echo.
if not "%CODE%"=="0" echo VarunOps stopped with error code %CODE%.
pause
exit /b %CODE%
