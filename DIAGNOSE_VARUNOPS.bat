@echo off
setlocal
cd /d "%~dp0"
echo === VarunOps Diagnostic ===
echo Folder: %CD%
echo.
if exist manage.py (echo [OK] manage.py) else (echo [MISSING] manage.py)
if exist varunops\settings.py (echo [OK] varunops\settings.py) else (echo [MISSING] varunops\settings.py)
if exist varunops\__init__.py (echo [OK] varunops package marker) else (echo [MISSING] varunops package marker - START_VARUNOPS will repair it)
if exist core\__init__.py (echo [OK] core package marker) else (echo [MISSING] core package marker - START_VARUNOPS will repair it)
if exist core\apps.py (echo [OK] core\apps.py) else (echo [MISSING] core\apps.py)
if exist core\migrations\0002_employee_portal.py (echo [OK] employee portal migration) else (echo [MISSING] employee portal migration)
if exist templates\core\employee.html (echo [OK] employee portal template) else (echo [MISSING] employee portal template)
if exist static\core\js\employee.js (echo [OK] employee portal JavaScript) else (echo [MISSING] employee portal JavaScript)
if exist .venv\Scripts\python.exe (echo [OK] virtual environment) else (echo [MISSING] virtual environment - run setup_local.ps1)
echo.
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -c "import os,sys; from pathlib import Path; print('Python:',sys.version); print('CWD:',os.getcwd()); sys.path.insert(0,str(Path.cwd())); import varunops,core; print('Import: OK')"
  echo Import command exit code: %ERRORLEVEL%
)
echo.
pause
