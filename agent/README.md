# VarunOps Windows Agent

Recommended deployment is from the Employee Portal:

1. Employee signs in and opens **My PC**.
2. Click **Generate code**.
3. Click **Download PC Connector**.
4. Extract the ZIP on that company Windows PC.
5. Run `CONNECT_THIS_PC.bat` as Administrator and enter the 8-digit code.

The connector installs `VarunOpsAgent.ps1` under `C:\ProgramData\VarunOps`, locks the directory ACL to SYSTEM/Administrators, and creates a SYSTEM scheduled task.

Software actions start in **TEST** mode. IT must intentionally enable **LIVE actions** from Admin > Devices > Details after checking that inventory and policies are correct.

Supported deployment sources:
- Winget package ID.
- Direct HTTPS EXE/MSI with exact SHA-256 and argument arrays.

The agent never accepts arbitrary remote PowerShell/CMD text from the server.


## Defender-friendly bootstrap
The deploy source no longer contains `install_agent.ps1` or `update_agent.ps1`. The authenticated employee connector endpoint generates transparent BAT bootstrap/update files at download time.
