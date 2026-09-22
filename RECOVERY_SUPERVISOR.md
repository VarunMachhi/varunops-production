# VarunOps 4.5.0 Recovery Supervisor

This build separates endpoint supervision from the PowerShell management agent.

## Why
A powered-on Windows PC can still appear offline when the VarunOps agent process has exited. Website policy changes cannot reach that endpoint until a local management process is running.

## New supervision
- `VarunOpsWatchdog.exe` runs as SYSTEM.
- It starts `C:\ProgramData\VarunOps\VarunOpsAgent.ps1` and waits for it.
- If the agent exits after an error or self-update, the watchdog restarts it after a short delay.
- Task Scheduler launches the watchdog at startup and also checks it every minute.
- A global watchdog mutex prevents duplicate supervisors.

## Existing broken endpoint
If the endpoint is already Agent Offline, the server cannot repair it remotely because no endpoint process is listening. Download the newest connector and run `RECOVER_VARUNOPS.bat` once as Administrator on that PC. Device identity and agent key are preserved.

After recovery, future agent exits/updates are automatically supervised.
