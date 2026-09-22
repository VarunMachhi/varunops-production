@echo off
setlocal
echo ========================================
echo   VarunOps Web Policy Diagnostic
echo ========================================
echo.
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ErrorActionPreference='SilentlyContinue';" ^
 "$cfg=Get-Content 'C:\ProgramData\VarunOps\agent.json' -Raw|ConvertFrom-Json; Write-Host ('Server: '+$cfg.server_url);" ^
 "$agent='C:\ProgramData\VarunOps\VarunOpsAgent.ps1'; if(Test-Path $agent){$v=Select-String -Path $agent -Pattern 'agent_version=' | Select-Object -First 1; Write-Host ('Agent: '+$v.Line.Trim())};" ^
 "foreach($b in @('HKLM:\SOFTWARE\Policies\Google\Chrome','HKLM:\SOFTWARE\Policies\Microsoft\Edge')){Write-Host '';Write-Host $b -ForegroundColor Cyan; foreach($l in @('URLBlocklist','URLAllowlist')){$p=Join-Path $b $l;Write-Host ('  '+$l+':'); if(Test-Path $p){$x=Get-ItemProperty $p; $x.PSObject.Properties|Where-Object Name -match '^\d+$'|Sort-Object {[int]$_.Name}|ForEach-Object {Write-Host ('    '+$_.Name+' = '+$_.Value)}}else{Write-Host '    (none)'}}};" ^
 "Write-Host ''; Write-Host 'Firewall rules:' -ForegroundColor Cyan; Get-NetFirewallRule -Group 'VarunOps Strict Browsing'|Select-Object DisplayName,Enabled,Action|Format-Table -AutoSize"
echo.
echo In Chrome also open: chrome://policy
echo In Edge also open: edge://policy
echo Look for URLBlocklist and URLAllowlist.
pause
