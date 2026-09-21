# Run in PowerShell on a trusted build workstation.
# Produces a single-file Windows executable in .\dist\VarunOpsAgent.exe
$ErrorActionPreference = "Stop"
python -m pip install --upgrade pyinstaller psutil
python -m PyInstaller --clean --onefile --name VarunOpsAgent --noconsole .\varunops_agent.py
Write-Host "Built .\dist\VarunOpsAgent.exe" -ForegroundColor Green
