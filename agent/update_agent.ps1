param()
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Run as Administrator.'}
$source=Join-Path $PSScriptRoot 'VarunOpsAgent.ps1'
if(-not (Test-Path $source)){throw "Missing $source"}
$dir=Join-Path $env:ProgramData 'VarunOps'
$config=Join-Path $dir 'agent.json'
if(-not (Test-Path $config)){throw 'No existing VarunOps device registration was found. Use CONNECT_THIS_PC.bat instead.'}
Stop-ScheduledTask -TaskName 'VarunOps Agent' -ErrorAction SilentlyContinue
Copy-Item $source (Join-Path $dir 'VarunOpsAgent.ps1') -Force
try {
  $cfg=Get-Content $config -Raw | ConvertFrom-Json
  $cfg | Add-Member -NotePropertyName poll_seconds -NotePropertyValue 60 -Force
  $cfg.PSObject.Properties.Remove('last_inventory_utc')
  $cfg | ConvertTo-Json -Depth 8 | Set-Content $config -Encoding UTF8
} catch { throw "Could not update agent configuration: $($_.Exception.Message)" }
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $dir 'VarunOpsAgent.ps1') --once
Start-ScheduledTask -TaskName 'VarunOps Agent' -ErrorAction Stop
Write-Host ''
Write-Host 'VarunOps Agent updated. Keep this PC online for about a minute.' -ForegroundColor Green
