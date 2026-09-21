$ErrorActionPreference = "SilentlyContinue"
Stop-ScheduledTask -TaskName "VarunOps Agent"
Unregister-ScheduledTask -TaskName "VarunOps Agent" -Confirm:$false
Remove-Item (Join-Path $env:ProgramData "VarunOps") -Recurse -Force
Write-Host "VarunOps Agent removed. Delete/disable the corresponding machine record in the server admin if it should no longer be trusted."
