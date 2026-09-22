# VarunOps Agent Automatic Updates

Agent version: `4.4.1-livepolicy`

## Normal behavior

After a PC has this version (or newer) installed, no local update action is required for normal future agent releases.

1. The endpoint authenticates to `/api/agent/manifest/` with its per-device key.
2. The manifest includes the server's bundled agent version, exact SHA-256, size and authenticated download URL.
3. If the server version is newer than the installed agent, the endpoint downloads `/api/agent/update-script/` over HTTPS using its own device credentials.
4. The endpoint verifies SHA-256 before replacement.
5. The old script is backed up as `C:\ProgramData\VarunOps\VarunOpsAgent.ps1.previous`.
6. The new script replaces the active agent and a SYSTEM child process restarts it after the old process exits.
7. The new agent resumes normal policy, telemetry and command polling automatically.

## Publishing a future agent version

Update `agent/VarunOpsAgent.ps1` and increase the leading semantic version in:

```powershell
$AgentVersion = '4.4.2-description'
```

Deploy the project to Render. Connected 4.4.0+ endpoints will discover it automatically. Website policy state itself is checked by 4.4.1+ endpoints on a lightweight ~10-second control poll, while full telemetry remains on the normal slower interval.

## Existing older endpoints

Agents older than 4.4.0 do not contain the self-update code. Upgrade those endpoints once with the latest connector `UPDATE_EXISTING_AGENT.bat`. After that, future updates are automatic.

`UPDATE_EXISTING_AGENT.bat` remains available as a recovery/repair path if automatic update ever fails.


## Employee portal access
After onboarding, Employee → My PC always shows an **Agent & connector** section with the installed agent version, latest server version, auto-update state, policy sync state, and a permanent **Download latest connector** button.
