@echo off
setlocal
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo === VarunOps Agent Diagnostic ===
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=Join-Path $env:ProgramData 'VarunOps'; $c=Join-Path $d 'agent.json'; $l=Join-Path $d 'agent.log'; Write-Host ('Folder: '+$d); Write-Host ('Config exists: '+(Test-Path $c)); if(Test-Path $c){$x=Get-Content $c -Raw|ConvertFrom-Json; Write-Host ('Server: '+$x.server_url); Write-Host ('Agent ID present: '+[bool]$x.agent_id); Write-Host ('Agent key present: '+[bool]$x.agent_key)}; try{$t=Get-ScheduledTask -TaskName 'VarunOps Agent' -ErrorAction Stop; Write-Host ('Task state: '+$t.State); $a=$t.Actions|Select-Object -First 1; Write-Host ('Task action: '+$a.Execute+' '+$a.Arguments)}catch{Write-Host ('Task error: '+$_.Exception.Message) -ForegroundColor Red}; if(Test-Path $l){Write-Host ''; Write-Host 'Last log lines:'; Get-Content $l -Tail 20}"
echo.
pause
