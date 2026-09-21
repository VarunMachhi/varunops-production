$ErrorActionPreference = "Stop"

try {
    $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $ProjectRoot

    Write-Host "" 
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " VarunOps Pro - Local Setup" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Project: $ProjectRoot"

    $required = @(
        "manage.py",
        "requirements.txt",
        "varunops\settings.py",
        "varunops\urls.py",
        "core\apps.py",
        "core\models.py",
        "core\views.py"
    )
    foreach ($item in $required) {
        if (-not (Test-Path (Join-Path $ProjectRoot $item))) {
            throw "Project extraction is incomplete. Missing '$item'. Re-extract the complete ZIP into a normal folder and run this script again."
        }
    }

    # Some Windows ZIP/extraction tools can omit zero-byte __init__.py files.
    # Repair package markers automatically instead of failing setup.
    $packageMarkers = @(
        "varunops\__init__.py",
        "core\__init__.py",
        "core\management\__init__.py",
        "core\management\commands\__init__.py",
        "core\migrations\__init__.py"
    )
    foreach ($marker in $packageMarkers) {
        $markerPath = Join-Path $ProjectRoot $marker
        $markerDir = Split-Path -Parent $markerPath
        if (-not (Test-Path $markerDir)) { New-Item -ItemType Directory -Force -Path $markerDir | Out-Null }
        if (-not (Test-Path $markerPath)) {
            Set-Content -Path $markerPath -Value '"""VarunOps Python package marker."""' -Encoding UTF8
            Write-Host "Repaired missing package marker: $marker" -ForegroundColor DarkYellow
        }
    }

    $bootstrapPython = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c "import sys; print(sys.executable)" *> $null
        if ($LASTEXITCODE -eq 0) { $bootstrapPython = "py -3" }
    }
    if (-not $bootstrapPython -and (Get-Command python -ErrorAction SilentlyContinue)) {
        $bootstrapPython = "python"
    }
    if (-not $bootstrapPython) {
        throw "Python 3 was not found. Install Python 3.12+ from python.org, enable 'Add python.exe to PATH', then run this setup again."
    }

    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "[1/7] Creating virtual environment..." -ForegroundColor Yellow
        if ($bootstrapPython -eq "py -3") { & py -3 -m venv .venv } else { & python -m venv .venv }
        if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
    } else {
        Write-Host "[1/7] Virtual environment already exists." -ForegroundColor DarkGray
    }

    $Py = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $Py)) { throw "Virtual environment Python was not created correctly." }

    Write-Host "[2/7] Installing dependencies..." -ForegroundColor Yellow
    & $Py -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $Py -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "[3/7] Created development .env." -ForegroundColor Yellow
    } else {
        Write-Host "[3/7] Existing .env preserved." -ForegroundColor DarkGray
    }

    Write-Host "[4/7] Checking project imports..." -ForegroundColor Yellow
    & $Py -c "from pathlib import Path; import sys; p=Path.cwd(); sys.path.insert(0,str(p)); import varunops, core; print('Project import OK:', p)"
    if ($LASTEXITCODE -ne 0) { throw "VarunOps Python packages could not be imported. Confirm the varunops and core folders are beside manage.py." }

    Write-Host "[5/7] Creating/updating database..." -ForegroundColor Yellow
    & $Py manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }

    Write-Host "[6/7] Loading demo workspace..." -ForegroundColor Yellow
    & $Py manage.py seed_demo
    if ($LASTEXITCODE -ne 0) { throw "Demo data setup failed." }

    Write-Host "[7/7] Running Django checks..." -ForegroundColor Yellow
    & $Py manage.py check
    if ($LASTEXITCODE -ne 0) { throw "Django system check failed." }

    Write-Host "" 
    Write-Host "SETUP COMPLETE" -ForegroundColor Green
    Write-Host "Run START_VARUNOPS.bat or run_local.bat to open VarunOps." -ForegroundColor Green
    Write-Host "Local URL: http://127.0.0.1:8000/" -ForegroundColor Cyan
    exit 0
}
catch {
    Write-Host "" 
    Write-Host "SETUP FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "" 
    Write-Host "Do not continue to runserver until this setup reports SETUP COMPLETE." -ForegroundColor Yellow
    exit 1
}
