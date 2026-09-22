param()
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Run as Administrator.'}

$source=Join-Path $PSScriptRoot 'VarunOpsAgent.ps1'
if(-not (Test-Path $source)){throw "Missing $source"}
$dir=Join-Path $env:ProgramData 'VarunOps'
$config=Join-Path $dir 'agent.json'
$target=Join-Path $dir 'VarunOpsAgent.ps1'
$log=Join-Path $dir 'agent.log'
if(-not (Test-Path $config)){throw 'No existing VarunOps device registration was found. Use CONNECT_THIS_PC.bat instead.'}

Write-Host ''
Write-Host 'VarunOps Agent 4.3.1 - Web Policy Repair / Upgrade' -ForegroundColor Cyan
Write-Host '------------------------------------' -ForegroundColor Cyan

try {
  $cfg=Get-Content $config -Raw | ConvertFrom-Json
} catch { throw "Existing agent.json is invalid: $($_.Exception.Message)" }
if(-not $cfg.server_url){throw 'Existing registration has no server_url. Re-pair this PC from the employee portal.'}
if(-not $cfg.agent_id -or -not $cfg.agent_key){throw 'Existing registration has no per-device agent key. Re-pair this PC from the employee portal.'}

# Keep a recovery copy of the currently registered credentials/config.
Copy-Item $config (Join-Path $dir 'agent.json.before-4.3.1.bak') -Force

# Stop/remove legacy scheduled task. Older VarunOps builds may still point at VarunOpsAgent.exe.
Stop-ScheduledTask -TaskName 'VarunOps Agent' -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'VarunOps Agent' -Confirm:$false -ErrorAction SilentlyContinue

Copy-Item $source $target -Force
$cfg | Add-Member -NotePropertyName poll_seconds -NotePropertyValue 60 -Force
$cfg.PSObject.Properties.Remove('last_inventory_utc')
$cfg.PSObject.Properties.Remove('dry_run')
$cfg | ConvertTo-Json -Depth 8 | Set-Content $config -Encoding UTF8

# Restrict the agent directory to SYSTEM and local administrators.
icacls $dir /inheritance:r | Out-Null
icacls $dir /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' | Out-Null

# Re-register task explicitly to the current PowerShell agent. This replaces legacy EXE task actions.
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$target`""
$trigger=New-ScheduledTaskTrigger -AtStartup
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName 'VarunOps Agent' -Action $action -Trigger $trigger -Settings $settings -User 'SYSTEM' -RunLevel Highest -Force | Out-Null

Write-Host '[1/3] Agent 4.3.1 files upgraded.' -ForegroundColor Green
Write-Host '[2/3] Sending strict full inventory + telemetry sync...' -ForegroundColor Yellow

& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $target --once-strict
if($LASTEXITCODE -ne 0){
  Write-Host ''
  Write-Host 'FIRST SYNC FAILED.' -ForegroundColor Red
  if(Test-Path $log){
    Write-Host 'Last agent log lines:' -ForegroundColor Yellow
    Get-Content $log -Tail 12 | ForEach-Object { Write-Host $_ }
  }
  throw "VarunOps server did not accept a fresh agent sync. See $log"
}

Start-ScheduledTask -TaskName 'VarunOps Agent' -ErrorAction Stop
Start-Sleep -Seconds 2
$task=Get-ScheduledTask -TaskName 'VarunOps Agent' -ErrorAction Stop
$actionText=($task.Actions | Select-Object -First 1).Execute + ' ' + ($task.Actions | Select-Object -First 1).Arguments
if($actionText -notmatch 'VarunOpsAgent\.ps1'){throw 'Scheduled task repair did not point to the new PowerShell agent.'}

Write-Host '[3/3] Background agent task started.' -ForegroundColor Green
Write-Host ''
Write-Host 'SUCCESS: Agent 4.3.1 synced and web-policy support is active.' -ForegroundColor Green
Write-Host 'Refresh the employee My PC page in 10-20 seconds.' -ForegroundColor Green
Write-Host "Log: $log" -ForegroundColor DarkGray
