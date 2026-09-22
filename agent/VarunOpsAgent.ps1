# VarunOps PowerShell endpoint agent
# Runs as SYSTEM from Task Scheduler. No Python runtime is required.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$AgentVersion = '4.4.1-livepolicy'
$script:RestartForUpdate = $false
$PolicyPollSeconds = 10

$Base = Join-Path $env:ProgramData 'VarunOps'
$ConfigPath = Join-Path $Base 'agent.json'
$LogPath = Join-Path $Base 'agent.log'

function Write-AgentLog([string]$Message) {
  New-Item -ItemType Directory -Path $Base -Force | Out-Null
  $line = "$(Get-Date -Format o) $Message"
  Add-Content -Path $LogPath -Value $line -Encoding UTF8
  try {
    if ((Get-Item $LogPath).Length -gt 2MB) {
      Move-Item $LogPath "$LogPath.1" -Force
    }
  } catch {}
}

function Load-Config {
  if (-not (Test-Path $ConfigPath)) { throw "Missing $ConfigPath" }
  $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
  if (-not $cfg.server_url) { throw 'server_url is required' }
  $uri = [Uri]$cfg.server_url
  if ($uri.Scheme -ne 'https' -and $uri.Host -notin @('127.0.0.1','localhost')) { throw 'HTTPS is required for non-local servers' }
  return $cfg
}

function Save-Config($cfg) {
  New-Item -ItemType Directory -Path $Base -Force | Out-Null
  $cfg | ConvertTo-Json -Depth 8 | Set-Content -Path $ConfigPath -Encoding UTF8
}

function Invoke-AgentApi([string]$Path,[string]$Method='GET',$Body=$null,$ExtraHeaders=@{}) {
  $cfg = Load-Config
  $headers = @{ 'Accept'='application/json'; 'User-Agent'=('VarunOps-AgentPS/'+$AgentVersion) }
  if ($cfg.agent_id -and $cfg.agent_key) {
    $headers['X-Agent-ID'] = [string]$cfg.agent_id
    $headers['X-Agent-Key'] = [string]$cfg.agent_key
  }
  foreach ($k in $ExtraHeaders.Keys) { $headers[$k] = $ExtraHeaders[$k] }
  $params = @{ Uri = (([string]$cfg.server_url).TrimEnd('/') + $Path); Method=$Method; Headers=$headers; TimeoutSec=60; UseBasicParsing=$true }
  if ($null -ne $Body) {
    $params['ContentType']='application/json; charset=utf-8'
    $params['Body']=($Body | ConvertTo-Json -Depth 12 -Compress)
  }
  try {
    return Invoke-RestMethod @params
  } catch {
    $status=''; $responseBody=''
    try {
      if ($_.Exception.Response) {
        try { $status=[int]$_.Exception.Response.StatusCode } catch { $status=[string]$_.Exception.Response.StatusCode }
        $stream=$_.Exception.Response.GetResponseStream()
        if ($stream) {
          $reader=New-Object System.IO.StreamReader($stream)
          $responseBody=$reader.ReadToEnd()
          $reader.Dispose()
        }
      }
    } catch {}
    if($responseBody.Length -gt 1200){$responseBody=$responseBody.Substring(0,1200)}
    $message="HTTP $status from $Path"
    if($responseBody){$message += ": $responseBody"}
    throw $message
  }
}

function Get-VersionObject([string]$Value) {
  try {
    $m=[regex]::Match([string]$Value,'^(\d+)\.(\d+)\.(\d+)')
    if(-not $m.Success){ return [version]'0.0.0' }
    return [version]("{0}.{1}.{2}" -f $m.Groups[1].Value,$m.Groups[2].Value,$m.Groups[3].Value)
  } catch { return [version]'0.0.0' }
}

function Start-NewAgentAfterUpdate {
  $target=Join-Path $Base 'VarunOpsAgent.ps1'
  $restart=Join-Path $Base 'restart_after_update.ps1'
  $content=@"
Start-Sleep -Seconds 3
Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$target`"' -WindowStyle Hidden
Remove-Item -LiteralPath `$MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"@
  Set-Content -Path $restart -Value $content -Encoding UTF8
  Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$restart) -WindowStyle Hidden | Out-Null
}

function Check-SelfUpdate($manifest) {
  if($null -eq $manifest -or $null -eq $manifest.agent_update){ return $false }
  $remote=[string]$manifest.agent_update.version
  $url=[string]$manifest.agent_update.url
  $expected=([string]$manifest.agent_update.sha256).ToLowerInvariant()
  if(-not $remote -or -not $url -or $expected -notmatch '^[a-f0-9]{64}$'){ return $false }
  if((Get-VersionObject $remote) -le (Get-VersionObject $AgentVersion)){ return $false }

  $cfg=Load-Config
  if(-not $cfg.agent_id -or -not $cfg.agent_key){ return $false }
  if(-not $url.StartsWith(([string]$cfg.server_url).TrimEnd('/')+'/')) { throw 'Agent update URL is not on the configured VarunOps server.' }
  $headers=@{
    'Accept'='text/plain'
    'User-Agent'=('VarunOps-AgentPS/'+$AgentVersion)
    'X-Agent-ID'=[string]$cfg.agent_id
    'X-Agent-Key'=[string]$cfg.agent_key
  }
  $tmp=Join-Path $Base 'VarunOpsAgent.ps1.download'
  try {
    Write-AgentLog ("Agent update available: {0} -> {1}" -f $AgentVersion,$remote)
    Invoke-WebRequest -Uri $url -Headers $headers -TimeoutSec 60 -UseBasicParsing -OutFile $tmp
    $actual=(Get-FileHash -Algorithm SHA256 -LiteralPath $tmp).Hash.ToLowerInvariant()
    if($actual -ne $expected){ throw 'Agent update SHA-256 verification failed.' }
    $downloaded=Get-Content $tmp -Raw
    if($downloaded -notmatch [regex]::Escape("`$AgentVersion = '$remote'")){ throw 'Downloaded agent version does not match the authenticated manifest.' }
    $target=Join-Path $Base 'VarunOpsAgent.ps1'
    Copy-Item $target (Join-Path $Base 'VarunOpsAgent.ps1.previous') -Force -ErrorAction SilentlyContinue
    Move-Item $tmp $target -Force
    Write-AgentLog ("Agent self-update installed: {0}" -f $remote)
    Start-NewAgentAfterUpdate
    $script:RestartForUpdate=$true
    return $true
  } finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
  }
}

function Clean-HardwareValue([string]$Value) {
  $v=([string]$Value).Trim()
  if (-not $v) { return '' }
  $bad=@('default string','to be filled by o.e.m.','to be filled by oem','system serial number','none','n/a','unknown','not specified')
  if ($bad -contains $v.ToLowerInvariant()) { return '' }
  return $v
}
function Get-SerialNumber {
  try {
    $candidates=@(
      (Get-CimInstance Win32_BIOS -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty SerialNumber),
      (Get-CimInstance Win32_ComputerSystemProduct -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty IdentifyingNumber)
    )
    foreach($candidate in $candidates) { $clean=Clean-HardwareValue ([string]$candidate); if($clean){ return $clean } }
  } catch {}
  return ''
}
function Get-LocalIp {
  try {
    $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | Where-Object { $_.IPAddress -notlike '169.254*' -and $_.IPAddress -ne '127.0.0.1' } | Sort-Object InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress
    return [string]$ip
  } catch { return '' }
}

function Convert-WmiCharArray($Value) {
  try {
    $chars=@($Value | Where-Object { $_ -gt 0 } | ForEach-Object { [char][int]$_ })
    return (-join $chars).Trim()
  } catch { return '' }
}

function Get-SystemInfo {
  $cs = Get-CimInstance Win32_ComputerSystem
  $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
  $os = Get-CimInstance Win32_OperatingSystem
  $bios = Get-CimInstance Win32_BIOS | Select-Object -First 1
  $board = Get-CimInstance Win32_BaseBoard -ErrorAction SilentlyContinue | Select-Object -First 1
  $gpuRows = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue)
  $gpu = @($gpuRows | ForEach-Object { [string]$_.Name } | Where-Object { $_ })
  $ram = @(Get-CimInstance Win32_PhysicalMemory -ErrorAction SilentlyContinue | ForEach-Object {
    @{capacity_gb=[Math]::Round(([double]$_.Capacity)/1GB,2);manufacturer=[string]$_.Manufacturer;part_number=([string]$_.PartNumber).Trim();serial=([string]$_.SerialNumber).Trim();speed_mhz=[int]$_.Speed}
  })
  $disks = @(Get-CimInstance Win32_DiskDrive -ErrorAction SilentlyContinue | ForEach-Object {
    @{model=[string]$_.Model;serial=([string]$_.SerialNumber).Trim();size_gb=[Math]::Round(([double]$_.Size)/1GB,1);interface=[string]$_.InterfaceType;media_type=[string]$_.MediaType}
  })
  $net = @(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=True' -ErrorAction SilentlyContinue | ForEach-Object {
    @{description=[string]$_.Description;mac=[string]$_.MACAddress;ip_addresses=@($_.IPAddress | Select-Object -First 6)}
  })
  $monitors=@()
  try {
    $ids=@(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID -ErrorAction Stop)
    $params=@(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorBasicDisplayParams -ErrorAction SilentlyContinue)
    foreach($m in $ids) {
      $instance=[string]$m.InstanceName
      $param=$params | Where-Object { [string]$_.InstanceName -eq $instance } | Select-Object -First 1
      $widthCm=0; $heightCm=0; $diag=''
      if($param) {
        $widthCm=[int]$param.MaxHorizontalImageSize; $heightCm=[int]$param.MaxVerticalImageSize
        if($widthCm -gt 0 -and $heightCm -gt 0) { $diag=('{0:N1}' -f ([Math]::Sqrt(($widthCm*$widthCm)+($heightCm*$heightCm))/2.54)) }
      }
      $monitors += @{
        manufacturer=(Convert-WmiCharArray $m.ManufacturerName)
        model=(Convert-WmiCharArray $m.UserFriendlyName)
        serial=(Convert-WmiCharArray $m.SerialNumberID)
        mfg_week=[int]$m.WeekOfManufacture
        mfg_year=[int]$m.YearOfManufacture
        width_cm=$widthCm
        height_cm=$heightCm
        diagonal_inches=$diag
      }
    }
  } catch {}
  $mouse=@(Get-CimInstance Win32_PointingDevice -ErrorAction SilentlyContinue | ForEach-Object {
    @{name=[string]$_.Name;manufacturer=[string]$_.Manufacturer;pnp_id=[string]$_.PNPDeviceID}
  } | Select-Object -First 10)
  $keyboard=@(Get-CimInstance Win32_Keyboard -ErrorAction SilentlyContinue | ForEach-Object {
    @{name=[string]$_.Name;manufacturer=[string]$_.Manufacturer;description=[string]$_.Description;pnp_id=[string]$_.PNPDeviceID}
  } | Select-Object -First 10)
  $resolution=''
  $activeGpu=$gpuRows | Where-Object { $_.CurrentHorizontalResolution -and $_.CurrentVerticalResolution } | Select-Object -First 1
  if($activeGpu) { $resolution="$($activeGpu.CurrentHorizontalResolution) x $($activeGpu.CurrentVerticalResolution)" }
  return @{
    hostname=$env:COMPUTERNAME
    manufacturer=[string]$cs.Manufacturer
    model=[string]$cs.Model
    system_type=[string]$cs.SystemType
    processor=[string]$cpu.Name
    cpu_name=[string]$cpu.Name
    cpu_id=([string]$cpu.ProcessorId).Trim()
    cpu_manufacturer=[string]$cpu.Manufacturer
    cpu_cores=[int]$cpu.NumberOfCores
    cpu_logical_processors=[int]$cpu.NumberOfLogicalProcessors
    cpu_max_clock_mhz=[int]$cpu.MaxClockSpeed
    memory=('{0:N1} GB' -f ($cs.TotalPhysicalMemory/1GB))
    memory_total_gb=[Math]::Round(([double]$cs.TotalPhysicalMemory)/1GB,2)
    memory_modules=$ram
    physical_disks=$disks
    gpu=$gpu
    network_adapters=$net
    windows_user=[string]$cs.UserName
    domain= if ($cs.Domain) {[string]$cs.Domain} else {[string]$env:USERDOMAIN}
    os_caption=[string]$os.Caption
    os_version=[string]$os.Version
    os_build=[string]$os.BuildNumber
    os_architecture=[string]$os.OSArchitecture
    bios_version=[string]$bios.SMBIOSBIOSVersion
    bios_serial=(Clean-HardwareValue ([string]$bios.SerialNumber))
    motherboard_manufacturer= if($board){[string]$board.Manufacturer}else{''}
    motherboard_model= if($board){[string]$board.Product}else{''}
    motherboard_serial= if($board){Clean-HardwareValue ([string]$board.SerialNumber)}else{''}
    monitors=$monitors
    resolution=$resolution
    mouse_devices=$mouse
    keyboard_devices=$keyboard
    agent_version=$AgentVersion
  }
}

function Get-SystemInfoCore($FullInfo=$null) {
  if ($null -eq $FullInfo) { $FullInfo=Get-SystemInfo }
  return @{
    hostname=[string]$FullInfo.hostname
    manufacturer=[string]$FullInfo.manufacturer
    model=[string]$FullInfo.model
    processor=[string]$FullInfo.processor
    cpu_name=[string]$FullInfo.cpu_name
    cpu_id=[string]$FullInfo.cpu_id
    cpu_manufacturer=[string]$FullInfo.cpu_manufacturer
    cpu_cores=[int]$FullInfo.cpu_cores
    cpu_logical_processors=[int]$FullInfo.cpu_logical_processors
    cpu_max_clock_mhz=[int]$FullInfo.cpu_max_clock_mhz
    memory=[string]$FullInfo.memory
    memory_total_gb=[double]$FullInfo.memory_total_gb
    windows_user=[string]$FullInfo.windows_user
    domain=[string]$FullInfo.domain
    os_caption=[string]$FullInfo.os_caption
    os_version=[string]$FullInfo.os_version
    os_build=[string]$FullInfo.os_build
    os_architecture=[string]$FullInfo.os_architecture
    bios_version=[string]$FullInfo.bios_version
    bios_serial=[string]$FullInfo.bios_serial
    motherboard_manufacturer=[string]$FullInfo.motherboard_manufacturer
    motherboard_model=[string]$FullInfo.motherboard_model
    motherboard_serial=[string]$FullInfo.motherboard_serial
    resolution=[string]$FullInfo.resolution
    agent_version=$AgentVersion
  }
}

function Get-Metrics {
  $os = Get-CimInstance Win32_OperatingSystem
  $cpuLoad = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
  if ($null -eq $cpuLoad) { $cpuLoad = 0 }
  $totalMem = [double]$os.TotalVisibleMemorySize * 1KB
  $freeMem = [double]$os.FreePhysicalMemory * 1KB
  # Avoid PowerShell selecting the Int32 Math.Max overload for byte values > 2 GB.
  $usedMem = [double]($totalMem - $freeMem)
  if ($usedMem -lt 0.0) { $usedMem = 0.0 }
  $disks = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3')
  $vols = @()
  $totalDisk=0.0; $freeDisk=0.0
  foreach ($d in $disks) {
    if (-not $d.Size) { continue }
    $used = [double]$d.Size - [double]$d.FreeSpace
    $totalDisk += [double]$d.Size; $freeDisk += [double]$d.FreeSpace
    $vols += @{ mount=[string]$d.DeviceID; filesystem=[string]$d.FileSystem; percent=[Math]::Round(($used/[double]$d.Size)*100,1); used_gb=[Math]::Round($used/1GB,2); total_gb=[Math]::Round(([double]$d.Size)/1GB,2) }
  }
  $usedDisk=[double]($totalDisk-$freeDisk)
  if ($usedDisk -lt 0.0) { $usedDisk = 0.0 }
  $boot=[datetime]$os.LastBootUpTime
  $uptimeSeconds = [int64]((Get-Date)-$boot).TotalSeconds
  if ($uptimeSeconds -lt 0) { $uptimeSeconds = [int64]0 }
  return @{
    cpu_percent=[Math]::Round([double]$cpuLoad,1)
    memory_percent= if ($totalMem) {[Math]::Round(($usedMem/$totalMem)*100,1)} else {0}
    memory_used_gb=[Math]::Round($usedMem/1GB,2)
    memory_total_gb=[Math]::Round($totalMem/1GB,2)
    storage_percent= if ($totalDisk) {[Math]::Round(($usedDisk/$totalDisk)*100,1)} else {0}
    storage_used_gb=[Math]::Round($usedDisk/1GB,2)
    storage_total_gb=[Math]::Round($totalDisk/1GB,2)
    storage_volumes=$vols
    uptime_seconds=$uptimeSeconds
  }
}

function Get-SoftwareInventory {
  $paths=@(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
  )
  $seen=@{}; $out=@()
  foreach($path in $paths) {
    Get-ItemProperty $path -ErrorAction SilentlyContinue | ForEach-Object {
      $name=[string]$_.DisplayName
      if ($name) {
        $key=$name.ToLowerInvariant()+'|'+[string]$_.DisplayVersion+'|'+[string]$_.Publisher
        if (-not $seen.ContainsKey($key)) {
          $seen[$key]=$true
          $out += @{name=$name.Substring(0,[Math]::Min(180,$name.Length));version=[string]$_.DisplayVersion;publisher=[string]$_.Publisher}
        }
      }
    }
  }
  return @($out | Select-Object -First 700)
}

function Get-PowerEvents {
  $out=@()
  try {
    Get-WinEvent -FilterHashtable @{LogName='System';Id=6005,6006,6008} -MaxEvents 20 -ErrorAction Stop | ForEach-Object {
      $kind = switch ($_.Id) { 6005 {'boot'} 6006 {'shutdown'} 6008 {'unexpected_shutdown'} }
      if ($kind) { $out += @{event_type=$kind;occurred_at=$_.TimeCreated.ToUniversalTime().ToString('o');source_id=[string]$_.Id} }
    }
  } catch {}
  return $out
}

function Get-BootIso {
  try { return (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o') } catch { return '' }
}

function Find-CatalogApps($manifest,$inventory) {
  $out=@()
  foreach($app in @($manifest.apps)) {
    $names=@($app.detection_names)
    if ($names.Count -eq 0) { $names=@([string]$app.name) }
    $match=$null
    foreach($row in $inventory) {
      $low=([string]$row.name).ToLowerInvariant()
      foreach($n in $names) {
        $needle=([string]$n).ToLowerInvariant()
        if ($needle -and ($low -eq $needle -or $low.Contains($needle))) { $match=$row; break }
      }
      if ($match) { break }
    }
    if ($match) { $out += @{slug=[string]$app.slug;version=[string]$match.version;detected_name=[string]$match.name} }
  }
  return $out
}

function Set-UrlList([string]$Path,$Values) {
  if (Test-Path $Path) {
    $item=Get-Item $Path
    foreach($name in $item.Property) { if ($name -match '^\d+$') { Remove-ItemProperty -Path $Path -Name $name -ErrorAction SilentlyContinue } }
  } else { New-Item -Path $Path -Force | Out-Null }
  $i=1
  foreach($v in @($Values)) { New-ItemProperty -Path $Path -Name ([string]$i) -Value ([string]$v) -PropertyType String -Force | Out-Null; $i++ }
}

function Remove-VarunOpsBrowserBlocks {
  Get-NetFirewallRule -Group 'VarunOps Strict Browsing' -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
}

function Add-BlockedBrowserRule([string]$Path) {
  if (-not $Path -or -not (Test-Path $Path)) { return }
  $name = 'VarunOps Block ' + [IO.Path]::GetFileName($Path) + ' ' + ($Path.ToLowerInvariant().GetHashCode().ToString('x8'))
  if (-not (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $name -Group 'VarunOps Strict Browsing' -Direction Outbound -Action Block -Program $Path -Profile Any -ErrorAction SilentlyContinue | Out-Null
  }
}

function Apply-StrictBrowserLock([bool]$Enabled) {
  Remove-VarunOpsBrowserBlocks
  if (-not $Enabled) { return }
  # Free endpoint mode: managed Edge/Chrome stay available; common unmanaged browsers are denied outbound network access.
  # This is not a Secure Web Gateway and does not claim to filter every arbitrary network-capable process.
  $candidates = @(
    "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
    "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe",
    "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe",
    "${env:ProgramFiles(x86)}\BraveSoftware\Brave-Browser\Application\brave.exe",
    "$env:ProgramFiles\Vivaldi\Application\vivaldi.exe",
    "${env:ProgramFiles(x86)}\Vivaldi\Application\vivaldi.exe",
    "$env:ProgramFiles\Waterfox\waterfox.exe"
  )
  $usersRoot = "$env:SystemDrive\Users"
  if (Test-Path $usersRoot) {
    foreach($profile in Get-ChildItem $usersRoot -Directory -ErrorAction SilentlyContinue) {
      $candidates += @(
        (Join-Path $profile.FullName 'AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe'),
        (Join-Path $profile.FullName 'AppData\Local\Programs\Opera\opera.exe'),
        (Join-Path $profile.FullName 'AppData\Local\Programs\Opera GX\opera.exe'),
        (Join-Path $profile.FullName 'AppData\Local\Vivaldi\Application\vivaldi.exe'),
        (Join-Path $profile.FullName 'AppData\Local\Mozilla Firefox\firefox.exe'),
        (Join-Path $profile.FullName 'AppData\Local\Waterfox\waterfox.exe')
      )
    }
  }
  foreach($path in @($candidates | Where-Object { $_ } | Select-Object -Unique)) { Add-BlockedBrowserRule $path }
}

function Normalize-UrlPolicyRule([string]$Rule) {
  $v=[string]$Rule
  if([string]::IsNullOrWhiteSpace($v)){ return '' }
  $v=$v.Trim()
  if($v -eq '*'){ return '*' }
  if($v.StartsWith('[*.]')){ $v=$v.Substring(4) }
  elseif($v.StartsWith('*.')){ $v=$v.Substring(2) }
  if($v.EndsWith('/*')){ $v=$v.Substring(0,$v.Length-2) }
  if($v.StartsWith('https://',[System.StringComparison]::OrdinalIgnoreCase)){ $rest=$v.Substring(8); if(-not $rest.Contains('/')){$v=$rest} }
  elseif($v.StartsWith('http://',[System.StringComparison]::OrdinalIgnoreCase)){ $rest=$v.Substring(7); if(-not $rest.Contains('/')){$v=$rest} }
  return $v.Trim().TrimEnd('/')
}

function Get-UrlListValues([string]$Path) {
  if(-not (Test-Path $Path)){ return @() }
  $item=Get-ItemProperty -Path $Path -ErrorAction SilentlyContinue
  if(-not $item){ return @() }
  $rows=@()
  foreach($prop in $item.PSObject.Properties | Where-Object { $_.Name -match '^\d+$' } | Sort-Object { [int]$_.Name }) {
    $rows += [string]$prop.Value
  }
  return @($rows)
}

function Apply-NetworkPolicy($policy) {
  $bases=@('HKLM:\SOFTWARE\Policies\Microsoft\Edge','HKLM:\SOFTWARE\Policies\Google\Chrome')
  foreach($b in $bases) { Set-UrlList "$b\URLBlocklist" @(); Set-UrlList "$b\URLAllowlist" @() }
  if ($null -eq $policy) { Apply-StrictBrowserLock $false; return @{id='';revision=0;verified=$true;rules=@()} }
  $block=@($policy.blocked_sites | ForEach-Object { Normalize-UrlPolicyRule ([string]$_) } | Where-Object { $_ })
  $allow=@($policy.allowed_sites | ForEach-Object { Normalize-UrlPolicyRule ([string]$_) } | Where-Object { $_ })
  if ([string]$policy.mode -eq 'allowlist') { $block=@('*') }
  else { $allow=@() }
  $targets=@()
  if ($policy.enforce_edge) {$targets += 'HKLM:\SOFTWARE\Policies\Microsoft\Edge'}
  if ($policy.enforce_chrome) {$targets += 'HKLM:\SOFTWARE\Policies\Google\Chrome'}
  foreach($b in $targets) { Set-UrlList "$b\URLBlocklist" $block; Set-UrlList "$b\URLAllowlist" $allow }
  Apply-StrictBrowserLock ([bool]$policy.strict_browsing)
  $verified=$true
  foreach($b in $targets){
    $actual=@(Get-UrlListValues "$b\URLBlocklist")
    if(@(Compare-Object -ReferenceObject @($block) -DifferenceObject @($actual)).Count -gt 0){ $verified=$false }
  }
  Write-AgentLog ("Network policy applied: id={0} rev={1} verified={2} block=[{3}]" -f $policy.id,$policy.revision,$verified,($block -join ','))
  return @{id=[string]$policy.id;revision=[int]$policy.revision;verified=[bool]$verified;rules=@($block)}
}

function Sync-NetworkPolicyFast([bool]$Force=$false) {
  Ensure-Enrolled
  $state=Invoke-AgentApi '/api/agent/policy-state/' 'GET'
  $assignment=$state.assignment
  $policy=$state.policy
  $policyId=''; $revision=0; $enabled=$false
  if($null -ne $assignment){
    $policyId=[string]$assignment.id
    try{$revision=[int]$assignment.revision}catch{$revision=0}
    $enabled=[bool]$assignment.enabled
  }
  $token=("{0}:{1}:{2}" -f $policyId,$revision,$enabled)
  $cfg=Load-Config
  $due=$Force -or ([string]$cfg.last_policy_token -ne $token)
  if(-not $due){
    try{
      if(-not $cfg.last_policy_verify_utc){$due=$true}
      else{
        $last=[datetime]::Parse([string]$cfg.last_policy_verify_utc).ToUniversalTime()
        if(((Get-Date).ToUniversalTime()-$last).TotalSeconds -ge 60){$due=$true}
      }
    }catch{$due=$true}
  }
  if(-not $due){return $null}

  $localAck=Apply-NetworkPolicy $policy
  $body=@{
    policy_id=$policyId
    revision=$revision
    enabled=$enabled
    verified=[bool]$localAck.verified
    rules=@($localAck.rules)
  }
  $serverAck=Invoke-AgentApi '/api/agent/policy-ack/' 'POST' $body
  $cfg=Load-Config
  $cfg | Add-Member -NotePropertyName last_policy_token -NotePropertyValue $token -Force
  $cfg | Add-Member -NotePropertyName last_policy_verify_utc -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('o')) -Force
  Save-Config $cfg
  Write-AgentLog ("Policy sync ack: id={0} rev={1} enabled={2} verified={3} desired={4}" -f $policyId,$revision,$enabled,$localAck.verified,$serverAck.matches_desired)
  return $body
}

function Ensure-Enrolled {
  $cfg=Load-Config
  if ($cfg.agent_id -and $cfg.agent_key) { return }
  $body=@{name=$env:COMPUTERNAME;branch=[string]$cfg.branch;device_type=[string]$cfg.device_type;os_version=(Get-CimInstance Win32_OperatingSystem).Caption;serial_number=(Get-SerialNumber)}
  if ($cfg.pairing_code) {
    $body['code']=[string]$cfg.pairing_code
    $result=Invoke-AgentApi '/api/agent/enroll-pairing/' 'POST' $body
    $cfg.PSObject.Properties.Remove('pairing_code')
  } elseif ($cfg.enrollment_token) {
    $result=Invoke-AgentApi '/api/agent/enroll/' 'POST' $body @{ 'X-Enrollment-Token'=[string]$cfg.enrollment_token }
    $cfg.PSObject.Properties.Remove('enrollment_token')
  } else { throw 'Pairing code or enrollment token is required for first enrollment' }
  $cfg | Add-Member -NotePropertyName agent_id -NotePropertyValue ([string]$result.agent_id) -Force
  $cfg | Add-Member -NotePropertyName agent_key -NotePropertyValue ([string]$result.agent_key) -Force
  Save-Config $cfg
  Write-AgentLog "Enrolled $($result.name)"
}

function Invoke-WingetAction([string]$Action,[string]$Id,[bool]$DryRun) {
  if ($Id -notmatch '^[A-Za-z0-9._+\-]{2,120}$') { return @{ok=$false;message='Invalid Winget ID'} }
  if ($DryRun) { return @{ok=$true;message="Dry run: would $Action $Id"} }
  $winget=(Get-Command winget.exe -ErrorAction SilentlyContinue).Source
  if (-not $winget) { return @{ok=$false;message='winget.exe not found'} }
  switch($Action) {
    'install' {$args=@('install','--id',$Id,'--exact','--silent','--accept-package-agreements','--accept-source-agreements','--disable-interactivity')}
    'update' {$args=@('upgrade','--id',$Id,'--exact','--silent','--accept-package-agreements','--accept-source-agreements','--disable-interactivity')}
    'uninstall' {$args=@('uninstall','--id',$Id,'--exact','--silent','--disable-interactivity')}
    default { return @{ok=$false;message='Unsupported action'} }
  }
  $p=Start-Process -FilePath $winget -ArgumentList $args -Wait -PassThru -NoNewWindow
  return @{ok=($p.ExitCode -eq 0);message="winget exit code $($p.ExitCode)"}
}

function Invoke-DirectInstaller([string]$Action,$App,[bool]$DryRun) {
  if ($Action -eq 'uninstall') { return Invoke-WingetAction $Action ([string]$App.winget_id) $DryRun }
  $url=[string]$App.installer_url; $sha=([string]$App.installer_sha256).ToLowerInvariant(); $kind=([string]$App.installer_kind).ToLowerInvariant()
  if (-not $url.StartsWith('https://') -or $sha -notmatch '^[a-f0-9]{64}$' -or $kind -notin @('exe','msi')) { return @{ok=$false;message='Invalid direct installer metadata'} }
  if ($DryRun) { return @{ok=$true;message="Dry run: would download and verify $kind installer"} }
  $file=Join-Path $env:TEMP ("varunops-"+[Guid]::NewGuid().ToString('N')+".$kind")
  try {
    Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing -TimeoutSec 300
    $actual=(Get-FileHash -Path $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $sha) { return @{ok=$false;message='SHA-256 mismatch; installer refused'} }
    $argList=@()
    if ($Action -eq 'update') { $argList=@($App.update_args) } else { $argList=@($App.install_args) }
    if ($kind -eq 'msi') {
      $p=Start-Process -FilePath 'msiexec.exe' -ArgumentList (@('/i',$file,'/qn','/norestart')+$argList) -Wait -PassThru -NoNewWindow
    } else {
      $p=Start-Process -FilePath $file -ArgumentList $argList -Wait -PassThru -NoNewWindow
    }
    return @{ok=($p.ExitCode -in @(0,1641,3010));message="installer exit code $($p.ExitCode)"}
  } catch { return @{ok=$false;message=("Direct installer error: "+$_.Exception.Message)} }
  finally { Remove-Item $file -Force -ErrorAction SilentlyContinue }
}

function Process-Commands($manifest,[bool]$DryRun) {
  $payload=Invoke-AgentApi '/api/agent/commands/' 'GET'
  foreach($cmd in @($payload.commands)) {
    $app=@($manifest.apps | Where-Object { [string]$_.slug -eq [string]$cmd.app.slug }) | Select-Object -First 1
    $result=@{ok=$false;message='App not present in authenticated manifest'}
    if ($app) {
      if ([string]$app.source_type -in @('direct','github')) { $result=Invoke-DirectInstaller ([string]$cmd.action) $app $DryRun }
      else { $result=Invoke-WingetAction ([string]$cmd.action) ([string]$app.winget_id) $DryRun }
    }
    $ver=''; if ($result.ok -and [string]$cmd.action -ne 'uninstall') {$ver=[string]$app.latest_version}
    Invoke-AgentApi ("/api/agent/commands/"+[string]$cmd.id+"/result/") 'POST' @{status=$(if($result.ok){'succeeded'}else{'failed'});message=[string]$result.message;version=$ver} | Out-Null
  }
}

function Process-AgentTasks([bool]$DryRun) {
  $payload=Invoke-AgentApi '/api/agent/tasks/' 'GET'
  foreach($task in @($payload.tasks)) {
    $result=@{ok=$false;message='Unsupported task'}
    if ([string]$task.kind -eq 'uninstall_detected') {
      $name=[string]$task.payload.display_name
      if ($DryRun) { $result=@{ok=$true;message="Dry run: would uninstall $name"} }
      else {
        $winget=(Get-Command winget.exe -ErrorAction SilentlyContinue).Source
        if ($winget) {
          $p=Start-Process -FilePath $winget -ArgumentList @('uninstall','--name',$name,'--exact','--silent','--disable-interactivity') -Wait -PassThru -NoNewWindow
          $result=@{ok=($p.ExitCode -eq 0);message="winget exit code $($p.ExitCode)"}
        } else {$result=@{ok=$false;message='winget.exe not found'}}
      }
    }
    Invoke-AgentApi ("/api/agent/tasks/"+[string]$task.id+"/result/") 'POST' @{status=$(if($result.ok){'succeeded'}else{'failed'});message=[string]$result.message} | Out-Null
  }
}

function Agent-Cycle {
  Ensure-Enrolled
  $cfg=Load-Config
  $manifest=Invoke-AgentApi '/api/agent/manifest/' 'GET'
  if(Check-SelfUpdate $manifest) { return }
  $policyAck=Sync-NetworkPolicyFast $true

  # Phase 1: send only conservative JSON-safe core hardware + telemetry.
  # This makes onboarding resilient even if an optional WMI/peripheral field is malformed.
  $fullInfo=Get-SystemInfo
  $coreInfo=Get-SystemInfoCore $fullInfo
  if($null -ne $policyAck){
    $coreInfo['network_policy_applied_id']=$(if([bool]$policyAck.enabled){[string]$policyAck.policy_id}else{''})
    $coreInfo['network_policy_applied_revision']=[int]$policyAck.revision
    $coreInfo['network_policy_verified']=[bool]$policyAck.verified
    $coreInfo['network_policy_rules']=@($policyAck.rules)
    $coreInfo['network_policy_ack']=@{policy_id=[string]$policyAck.policy_id;revision=[int]$policyAck.revision;enabled=[bool]$policyAck.enabled;verified=[bool]$policyAck.verified}
  }
  $metrics=Get-Metrics
  $coreHeartbeat=@{
    system_info=$coreInfo
    metrics=$metrics
  }
  $ack=Invoke-AgentApi '/api/agent/heartbeat/' 'POST' $coreHeartbeat
  if(-not $ack -or -not [bool]$ack.ok) { throw 'Core heartbeat was not acknowledged by VarunOps server.' }
  if(-not [bool]$ack.system_info_received) { throw 'Server did not accept core hardware information.' }
  if(-not [bool]$ack.metrics_received) { throw 'Server did not accept device telemetry.' }
  Write-AgentLog 'Core hardware + telemetry heartbeat accepted.'

  # Phase 2: enrich the same machine with complete hardware details.
  # Failure here is non-fatal: core telemetry remains usable and the exact server body is logged.
  try {
    $extendedHeartbeat=@{
      ip_address=(Get-LocalIp)
      os_version=[string](Get-CimInstance Win32_OperatingSystem).Caption
      serial_number=(Get-SerialNumber)
      system_info=$fullInfo
      metrics=$metrics
      boot_time=(Get-BootIso)
    }
    $extendedAck=Invoke-AgentApi '/api/agent/heartbeat/' 'POST' $extendedHeartbeat
    if($extendedAck -and [bool]$extendedAck.ok) { Write-AgentLog 'Extended hardware heartbeat accepted.' }
  } catch {
    Write-AgentLog ('Extended hardware warning: '+$_.Exception.Message)
  }

  $inventoryDue=$true
  try {
    if($cfg.last_inventory_utc) {
      $last=[datetime]::Parse([string]$cfg.last_inventory_utc).ToUniversalTime()
      if(((Get-Date).ToUniversalTime()-$last).TotalSeconds -lt 900) { $inventoryDue=$false }
    }
  } catch { $inventoryDue=$true }

  # Phase 3: software and power event inventory are optional enrichment.
  # Always include the full system_info so older servers do not clear it when handling a partial heartbeat.
  if($inventoryDue) {
    try {
      $inventory=Get-SoftwareInventory
      $inventoryHeartbeat=@{
        ip_address=(Get-LocalIp)
        os_version=[string](Get-CimInstance Win32_OperatingSystem).Caption
        serial_number=(Get-SerialNumber)
        system_info=$fullInfo
        metrics=$metrics
        apps=(Find-CatalogApps $manifest $inventory)
        software_inventory=$inventory
        power_events=(Get-PowerEvents)
        boot_time=(Get-BootIso)
      }
      $inventoryAck=Invoke-AgentApi '/api/agent/heartbeat/' 'POST' $inventoryHeartbeat
      if($inventoryAck -and [bool]$inventoryAck.ok) {
        $cfg=Load-Config
        $cfg | Add-Member -NotePropertyName last_inventory_utc -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('o')) -Force
        Save-Config $cfg
        Write-AgentLog 'Software + power inventory heartbeat accepted.'
      }
    } catch {
      Write-AgentLog ('Inventory enrichment warning: '+$_.Exception.Message)
    }
  }

  $dryRun = -not [bool]$manifest.live_actions
  Process-Commands $manifest $dryRun
  Process-AgentTasks $dryRun
}

$strictOnce = $args -contains '--once-strict'
$once = ($args -contains '--once') -or $strictOnce
if($once){
  try {
    Agent-Cycle
    if($script:RestartForUpdate){ Write-AgentLog 'Current agent process exiting for self-update restart.'; exit 0 }
    if($strictOnce){ Write-Host 'VarunOps strict sync accepted.' -ForegroundColor Green }
    exit 0
  } catch {
    Write-AgentLog ("Cycle failed: "+$_.Exception.Message)
    if($strictOnce){ Write-Error ("VarunOps strict sync failed: "+$_.Exception.Message) }
    exit 2
  }
}

$nextFull=[datetime]::MinValue
do {
  try {
    $now=(Get-Date).ToUniversalTime()
    if($now -ge $nextFull){
      Agent-Cycle
      if($script:RestartForUpdate){ Write-AgentLog 'Current agent process exiting for self-update restart.'; exit 0 }
      try{$cfg=Load-Config;$seconds=[Math]::Max(30,[Math]::Min(300,[int]$cfg.poll_seconds))}catch{$seconds=60}
      $nextFull=(Get-Date).ToUniversalTime().AddSeconds($seconds)
    } else {
      Sync-NetworkPolicyFast $false | Out-Null
    }
  } catch {
    Write-AgentLog ("Fast policy/full cycle failed: "+$_.Exception.Message)
  }
  Start-Sleep -Seconds $PolicyPollSeconds
} while ($true)
exit 0
