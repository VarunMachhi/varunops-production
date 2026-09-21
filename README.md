# IMPORTANT — FIXSYNC build

If an already-connected PC remains on “Finishing first PC scan”, download a fresh connector from the employee portal and run **UPDATE_EXISTING_AGENT.bat as Administrator**. This build migrates legacy EXE scheduled tasks to PowerShell Agent 4.2 and only reports SUCCESS after the cloud server accepts fresh hardware + telemetry.

# VarunOps Pro — Employee Onboarding + 60 Device Build

VarunOps is a Django + Windows PowerShell-agent endpoint-management prototype for company PCs.

## Employee onboarding

1. IT creates employee with username, IT-managed email, employee code/department/branch/title.
2. VarunOps shows a strong temporary password **once**. IT gives it privately to the employee.
3. Employee signs in. Normal portal navigation remains locked during onboarding.
4. Employee generates a single-use 8-digit pairing code and downloads the PC Connector.
5. On the company Windows PC, run `CONNECT_THIS_PC.bat` as Administrator and enter the code.
6. The agent enrolls with a unique device credential and sends its first full hardware + live-usage report.
7. Only after the first real report is received, Employee can request a 6-digit OTP sent to the email stored by IT.
8. Employee verifies OTP and creates a permanent password. The password is hashed by Django and **is never visible to IT**.
9. Dashboard unlocks.

Admin sees onboarding/password **status** and timestamps (temporary password issued, email verified, permanent password changed), never the permanent password.

## Automatic device inventory

The Windows agent attempts to collect:
- hostname, IP, MAC/network adapters, signed-in Windows user
- Windows edition/version/build/architecture
- system manufacturer/model/type and usable system serial
- CPU name, Processor ID, manufacturer, cores, logical processors, max clock
- motherboard manufacturer/model/serial, BIOS version/serial
- RAM total and individual RAM module capacity/manufacturer/part/serial/speed
- physical disks model/serial/size/interface/media type
- GPU
- monitor manufacturer/model/serial, size, resolution and EDID manufacture week/year when Windows exposes it
- mouse and keyboard name/manufacturer/PNP ID when Windows exposes it
- CPU/RAM/storage usage, volumes, uptime
- installed software inventory and Windows power events

Hardware firmware/drivers do not reliably expose every peripheral value. VarunOps therefore provides manual asset fields for Asset Tag/PIN, vendor, purchase date, desk/location, monitor overrides, mouse/keyboard serial/model, UPS details and notes.

Admin > Devices includes **Export asset CSV** compatible with the asset-register fields used for this build.

## 60+ employee/device optimization

- endpoint heartbeat/live metrics: about **60 seconds**
- installed-software inventory: about **15 minutes**
- latest telemetry is overwritten on the Machine row (no new DB row every minute)
- sampled metric history: one snapshot about every **15 minutes**, rolling **7 days**
- detected software uses update-or-create rather than append-only history

This substantially reduces free-database writes compared with 15-second full inventory polling.

## Software control

Per PC an app can be Required / Optional / Blocked. Employee only sees apps allowed for that PC. Employee requests install/update/uninstall; IT approval creates a typed endpoint command. Unknown installed software creates a device warning; IT can allow that exact name on that PC or queue a removal attempt.

App sources are either:
- Winget package ID (recommended), or
- trusted HTTPS EXE/MSI + exact SHA-256 + bounded silent arguments.

Cracks, activation bypasses and arbitrary remote PowerShell/CMD are intentionally unsupported.

## Website restriction

Per-PC policies write managed Edge/Chrome URL allow/block policy. For true every-app/every-browser filtering, add a DNS/Secure Web Gateway; browser policy alone is not a full network firewall.

## Local start

Extract and run `START_VARUNOPS.bat`.

## Cloud deployment

Read `DEPLOY_FREE.md`. The build supports any PostgreSQL `DATABASE_URL`. For a free test deployment with many continuously-reporting endpoints, Supabase Free PostgreSQL is a practical option; Render hosts Django and Resend HTTPS API sends OTP email (Render Free blocks outbound SMTP ports).

Free tiers are not lifetime guarantees and should not be treated as a production SLA.
