# Defender-friendly connector changes

- Removed `agent/install_agent.ps1` and `agent/update_agent.ps1` from deploy/source files.
- Employee connector now generates transparent elevated BAT bootstrap/update files.
- Removed the hidden PowerShell helper process from agent self-update.
- VarunOps does not require a Microsoft Defender exclusion or global Defender disable.
- If Defender detects the connector, review the exact detection in Windows Security > Protection history and submit the file to Microsoft as a suspected false positive before considering any exclusion.

Version: 4.4.4-defenderfriendly
