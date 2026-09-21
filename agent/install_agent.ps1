param(
  [Parameter(Mandatory=$true)][string]$ServerUrl,
  [Parameter(Mandatory=$true)][string]$PairingCode,
  [string]$Branch = "",
  [ValidateSet("Desktop","Laptop","Server")][string]$DeviceType = "Desktop"
)
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Run as Administrator.'}
if(-not ($ServerUrl.StartsWith('https://') -or $ServerUrl.StartsWith('http://127.0.0.1') -or $ServerUrl.StartsWith('http://localhost'))){throw 'HTTPS is required for non-local servers.'}
if($PairingCode -notmatch '^\d{8}$'){throw 'Pairing code must be 8 digits.'}
$source=Join-Path $PSScriptRoot 'VarunOpsAgent.ps1'
if(-not (Test-Path $source)){throw "Missing $source"}
$dir=Join-Path $env:ProgramData 'VarunOps'
New-Item -ItemType Directory -Path $dir -Force | Out-Null
Copy-Item $source (Join-Path $dir 'VarunOpsAgent.ps1') -Force
@{
  server_url=$ServerUrl.TrimEnd('/'); pairing_code=$PairingCode; branch=$Branch; device_type=$DeviceType;
  poll_seconds=60
} | ConvertTo-Json | Set-Content (Join-Path $dir 'agent.json') -Encoding UTF8
icacls $dir /inheritance:r | Out-Null
icacls $dir /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' | Out-Null
$script=Join-Path $dir 'VarunOpsAgent.ps1'
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$script`""
$trigger=New-ScheduledTaskTrigger -AtStartup
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName 'VarunOps Agent' -Action $action -Trigger $trigger -Settings $settings -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $script --once
Start-ScheduledTask -TaskName 'VarunOps Agent'
Write-Host ''
Write-Host 'VarunOps agent installed and paired.' -ForegroundColor Green
Write-Host 'Software execution starts in TEST mode. IT can enable LIVE actions from the VarunOps device page after verification.' -ForegroundColor Yellow
