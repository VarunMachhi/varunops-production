# VarunOps PowerShell endpoint agent
# Runs as SYSTEM from Task Scheduler. No Python runtime is required.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

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
  $headers = @{ 'Accept'='application/json'; 'User-Agent'='VarunOps-AgentPS/4.2' }
  if ($cfg.agent_id -and $cfg.agent_key) {
    $headers['X-Agent-ID'] = [string]$cfg.agent_id
    $headers['X-Agent-Key'] = [string]$cfg.agent_key
  }
  foreach ($k in $ExtraHeaders.Keys) { $headers[$k] = $ExtraHeaders[$k] }
  $params = @{ Uri = (([string]$cfg.server_url).TrimEnd('/') + $Path); Method=$Method; Headers=$headers; TimeoutSec=60; UseBasicParsing=$true }
  if ($null -ne $Body) {
    $params['ContentType']='application/json'
    $params['Body']=($Body | ConvertTo-Json -Depth 12 -Compress)
  }
  return Invoke-RestMethod @params
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
    agent_version='4.2-powershell'
  }
}

function Get-Metrics {
  $os = Get-CimInstance Win32_OperatingSystem
  $cpuLoad = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
  if ($null -eq $cpuLoad) { $cpuLoad = 0 }
  $totalMem = [double]$os.TotalVisibleMemorySize * 1KB
  $freeMem = [double]$os.FreePhysicalMemory * 1KB
  $usedMem = [Math]::Max(0,$totalMem-$freeMem)
  $disks = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3')
  $vols = @()
  $totalDisk=0.0; $freeDisk=0.0
  foreach ($d in $disks) {
    if (-not $d.Size) { continue }
    $used = [double]$d.Size - [double]$d.FreeSpace
    $totalDisk += [double]$d.Size; $freeDisk += [double]$d.FreeSpace
    $vols += @{ mount=[string]$d.DeviceID; filesystem=[string]$d.FileSystem; percent=[Math]::Round(($used/[double]$d.Size)*100,1); used_gb=[Math]::Round($used/1GB,2); total_gb=[Math]::Round(([double]$d.Size)/1GB,2) }
  }
  $usedDisk=$totalDisk-$freeDisk
  $boot=[datetime]$os.LastBootUpTime
  return @{
    cpu_percent=[Math]::Round([double]$cpuLoad,1)
    memory_percent= if ($totalMem) {[Math]::Round(($usedMem/$totalMem)*100,1)} else {0}
    memory_used_gb=[Math]::Round($usedMem/1GB,2)
    memory_total_gb=[Math]::Round($totalMem/1GB,2)
    storage_percent= if ($totalDisk) {[Math]::Round(($usedDisk/$totalDisk)*100,1)} else {0}
    storage_used_gb=[Math]::Round($usedDisk/1GB,2)
    storage_total_gb=[Math]::Round($totalDisk/1GB,2)
    storage_volumes=$vols
    uptime_seconds=[Math]::Max(0,[int]((Get-Date)-$boot).TotalSeconds)
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

function Apply-NetworkPolicy($policy) {
  $bases=@('HKLM:\SOFTWARE\Policies\Microsoft\Edge','HKLM:\SOFTWARE\Policies\Google\Chrome')
  foreach($b in $bases) { Set-UrlList "$b\URLBlocklist" @(); Set-UrlList "$b\URLAllowlist" @() }
  if ($null -eq $policy) { return }
  $block=@($policy.blocked_sites); $allow=@()
  if ([string]$policy.mode -eq 'allowlist') { $block=@('*'); $allow=@($policy.allowed_sites) }
  $targets=@()
  if ($policy.enforce_edge) {$targets += 'HKLM:\SOFTWARE\Policies\Microsoft\Edge'}
  if ($policy.enforce_chrome) {$targets += 'HKLM:\SOFTWARE\Policies\Google\Chrome'}
  foreach($b in $targets) { Set-UrlList "$b\URLBlocklist" $block; Set-UrlList "$b\URLAllowlist" $allow }
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
      if ([string]$app.source_type -eq 'direct') { $result=Invoke-DirectInstaller ([string]$cmd.action) $app $DryRun }
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
  Apply-NetworkPolicy $manifest.network_policy
  $heartbeat=@{
    ip_address=(Get-LocalIp)
    os_version=[string](Get-CimInstance Win32_OperatingSystem).Caption
    serial_number=(Get-SerialNumber)
    system_info=(Get-SystemInfo)
    metrics=(Get-Metrics)
    boot_time=(Get-BootIso)
    power_events=(Get-PowerEvents)
  }

  $inventoryDue=$true
  try {
    if($cfg.last_inventory_utc) {
      $last=[datetime]::Parse([string]$cfg.last_inventory_utc).ToUniversalTime()
      if(((Get-Date).ToUniversalTime()-$last).TotalSeconds -lt 900) { $inventoryDue=$false }
    }
  } catch { $inventoryDue=$true }

  if($inventoryDue) {
    $inventory=Get-SoftwareInventory
    $heartbeat['apps']=(Find-CatalogApps $manifest $inventory)
    $heartbeat['software_inventory']=$inventory
  }

  $ack=Invoke-AgentApi '/api/agent/heartbeat/' 'POST' $heartbeat
  if(-not $ack -or -not [bool]$ack.ok) { throw 'Heartbeat was not acknowledged by VarunOps server.' }
  if($inventoryDue -and -not [bool]$ack.system_info_received) { throw 'Server did not accept the full hardware inventory.' }
  if(-not [bool]$ack.metrics_received) { throw 'Server did not accept device telemetry.' }
  Write-AgentLog ("Heartbeat accepted. ready="+[string]$ack.machine_ready+" metrics="+[string]$ack.metrics_received+" inventory="+[string]$ack.system_info_received)
  if($inventoryDue) {
    $cfg=Load-Config
    $cfg | Add-Member -NotePropertyName last_inventory_utc -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('o')) -Force
    Save-Config $cfg
  }
  $dryRun = -not [bool]$manifest.live_actions
  Process-Commands $manifest $dryRun
  Process-AgentTasks $dryRun
}

$strictOnce = $args -contains '--once-strict'
$once = ($args -contains '--once') -or $strictOnce
do {
  try {
    Agent-Cycle
    if($strictOnce) { Write-Host 'VarunOps strict sync accepted.' -ForegroundColor Green }
  } catch {
    Write-AgentLog ("Cycle failed: "+$_.Exception.Message)
    if($strictOnce) {
      Write-Error ("VarunOps strict sync failed: "+$_.Exception.Message)
      exit 2
    }
  }
  if ($once) { break }
  try { $cfg=Load-Config; $seconds=[Math]::Max(30,[Math]::Min(300,[int]$cfg.poll_seconds)) } catch {$seconds=60}
  Start-Sleep -Seconds $seconds
} while ($true)
exit 0
