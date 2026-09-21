# VarunOps Pro — Real Deploy Build

VarunOps is a Django + Windows-agent endpoint-management prototype for company PCs.

## Start locally

On Windows, extract the complete ZIP and double-click:

`START_VARUNOPS.bat`

First setup creates the virtual environment, installs requirements, runs migrations, seeds local demo data, checks Django, starts the server, and opens `http://127.0.0.1:8000/`.

Local demo accounts:
- Admin: `admin` / `ChangeThisImmediately!234`
- Employee: `varun` / `EmployeeDemo!234`

Change these before real use. The demo employee starts **unpaired** so you can test the real PC pairing flow.

## Clean navigation

### Admin
Overview → Devices → Employees → Software → Requests → Policies → Support → Activity

### Employee
Home → My PC → Software → Support → Notifications → Profile

## Employee + PC workflow

1. Admin creates an employee account.
2. Employee signs in and completes Profile.
3. Employee opens My PC and generates a single-use 8-digit pairing code.
4. Employee downloads the PC Connector ZIP.
5. On that Windows PC, extract it and run `CONNECT_THIS_PC.bat` as Administrator.
6. The installed SYSTEM agent sends hardware, software inventory, CPU/RAM/storage telemetry, IP/Windows data, last-seen, and power events.
7. The employee can only see their assigned PC and software IT has allowed for that PC.

## Software policies per PC

IT can mark each catalog app:
- **Required** — must be installed; Enforce mode queues installation if missing.
- **Optional** — visible in that employee's company Software page; employee can request install/update/uninstall.
- **Blocked** — cannot be requested; Enforce mode can remove a blocked catalog app.

Once a PC has explicit app-policy rows, its Employee Software page becomes an explicit per-PC allowlist.

## Unauthorized software

The agent inventories Windows installed software. Items that are not:
- an approved catalog app,
- a per-PC exception, or
- a conservative Windows/runtime baseline

are reported as unapproved software. IT receives an alert and can:
- **Allow on this PC** (creates a per-PC exception), or
- **Uninstall** (queues a validated endpoint removal task).

VarunOps reports that software was **detected on a device**. Inventory data alone cannot reliably prove which human installed it.

## Software Store — real installer source

VarunOps does not pretend an EXE appears by itself. Every app has a deployment source.

### Winget (recommended)
Set a Winget package ID, e.g. `Google.Chrome`. The Windows agent uses the exact package ID for supported actions.

### Direct HTTPS EXE/MSI
Set:
- trusted HTTPS installer URL,
- EXE/MSI type,
- exact SHA-256 checksum,
- silent install/update arguments,
- detection names.

The agent downloads to a temporary file and verifies SHA-256 before execution. A mismatch is refused.

Direct uninstall currently requires a Winget ID. Arbitrary remote CMD/PowerShell and crack/license-bypass scripts are intentionally unsupported.

## Safe test → live workflow

A newly paired PC starts in **TEST** mode. Inventory, telemetry and browser policy still report/apply, but software/endpoint removal commands stay queued on the server.

After verifying the correct PC/policies:
Admin → Devices → Details → **Enable LIVE actions**.

Only then can queued install/update/uninstall/removal actions be dispatched to that endpoint.

## Website restrictions

Network policies can be assigned per PC:
- **Allowlist** — block all URLs in managed browser policy then allow selected patterns.
- **Blocklist** — allow normal browsing but block selected patterns.

Current agent writes managed policies for Microsoft Edge and Google Chrome. This is browser policy, not a fake claim of all-app network filtering. For every browser/application, add a DNS/Secure Web Gateway later.

## Telemetry

The agent polls about every 15 seconds and sends:
- CPU %
- RAM used/total/%
- storage used/total/% and volumes
- uptime
- machine/OS/CPU/model/serial/IP
- signed-in Windows user when available
- installed software
- startup/shutdown/unexpected-shutdown events

The server stores the latest metrics directly on the device plus historical samples approximately every 5 minutes, with a short rolling metrics history to protect a small free database.

## Support

Employees can open IT tickets and reply with optional PNG/JPEG/WebP screenshots (max 2 MB). New screenshots are stored as authenticated database blobs, not public media URLs, so they survive stateless web-service restarts when PostgreSQL is used.

## Production deployment

Read `DEPLOY_FREE.md` for Render + Neon deployment.

Recommended real-test stack:
- Render Free Web Service
- Neon Free PostgreSQL
- Windows PowerShell agent

Free hosting is not guaranteed forever and Render Free is not an always-on production SLA. Use it to prove the workflow; move to paid infrastructure if company downtime matters.

## Key files

- `START_VARUNOPS.bat` — one-click local start
- `setup_local.ps1` — first-run setup
- `render.yaml` — Render deployment definition
- `DEPLOY_FREE.md` — step-by-step cloud deployment
- `SECURITY.md` — security design and limitations
- `agent/VarunOpsAgent.ps1` — endpoint agent
- `agent/install_agent.ps1` — SYSTEM scheduled-task installer

## Verification performed in this package

- Python source compilation checks
- JavaScript syntax checks
- archive integrity check
- route/template/static-file consistency checks
- scans for dangerous shortcuts such as `csrf_exempt`, `eval`, `exec`, `os.system`, and executable `shell=True`

A full Django runtime integration test could not be executed in the build container because its network cannot download PyPI dependencies. The Windows launcher installs those dependencies on the target PC before migrations/startup.
