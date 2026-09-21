# VarunOps Security Notes

This starter is designed to reduce dangerous defaults, but **no application should be described as fully secure without deployment-specific review, patching, monitoring, backups, and testing**.

## Implemented controls

- Staff-only browser console plus a separate employee portal. Employee endpoints derive identity from the authenticated session and scope data to that user rather than accepting an employee ID from the browser.
- CSRF middleware and CSRF tokens for state-changing browser requests.
- Argon2 first in the password-hasher list.
- Per-device random agent key; only its password hash is kept in the database.
- IT bootstrap enrollment can use a separate token; employee onboarding uses a short-lived single-use pairing code generated from an authenticated employee session. An already enrolled device cannot silently re-enroll.
- Agent API keys are scoped to the machine represented by the credential.
- No endpoint accepts arbitrary shell commands. Catalog actions are limited to install/update/uninstall. The only additional remediation task is a server-recorded exact-name Winget uninstall of software that the agent itself reported as installed.
- Endpoint locally validates action type, Winget package ID syntax, and matches the command back to a separately fetched approved manifest.
- The recommended PowerShell agent uses structured `Start-Process -ArgumentList` calls and never executes arbitrary server-supplied shell text.
- Enrollment secret is deleted from the endpoint configuration after first enrollment.
- Windows installer restricts `%ProgramData%\VarunOps` to SYSTEM and local Administrators.
- Commands have queued/running/succeeded/failed/cancelled states, dispatch attempts and stale-command recovery.
- Locked policy is re-checked on the server before a command is created.
- Automatic policy queues updates only for already installed approved apps.
- Security headers include CSP, `X-Frame-Options: DENY`, nosniff, same-origin opener/referrer policy, and a restrictive Permissions-Policy.
- Production defaults enable secure cookies, HTTPS redirect and HSTS; all are configurable by environment.
- DRF throttling is enabled as an application-level backstop.
- Audit events are written server-side for command creation, policy assignment, enrollment, dispatch and results.


## Employee portal controls

- Employee users are non-staff and `/console/` redirects them to `/employee/`.
- Software request creation always uses the authenticated employee and their server-side assigned machine.
- Admin approval is required before a request can create an agent command.
- Locked machine policy is enforced again during request approval.
- Ticket reads/replies verify ownership unless the user is staff.
- Screenshot uploads are limited to 2 MB and verified with Pillow as PNG/JPEG/WebP before storage.
- New screenshot bytes are stored in PostgreSQL and are never exposed through a public media route; downloads pass through an authenticated authorization check. Legacy file-backed attachments remain readable for migration compatibility.
- Employee notifications are queried and updated only by their owner.
- Employee-facing device details deliberately omit machine policy controls and agent credentials.

## Required before production

1. Use a long random `SECRET_KEY` and `AGENT_ENROLLMENT_TOKEN`. Never commit `.env`.
2. Use HTTPS end-to-end from clients to the public reverse proxy. Keep TLS verification enabled in the agent.
3. Set exact `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`; do not use `*`.
4. Use PostgreSQL/Neon with restricted database credentials and backups.
5. Put rate limiting/WAF controls at the edge. DRF's cache-backed throttle is not a substitute for network controls.
6. Create individual admin accounts, enable MFA through your identity layer/admin access strategy, and avoid sharing passwords.
7. Rotate the enrollment token after enrollment batches. Disable lost or retired machines.
8. Code-sign the Windows agent executable before broad deployment.
9. Test inventory, Winget/direct deployment metadata and uninstall behavior on non-critical PCs before enabling **LIVE actions** for a device.
10. Run `python manage.py check --deploy` using the exact production environment.
11. Add centralized error monitoring and alerting; do not expose tracebacks to users.
12. Keep Django, DRF, Python, PostgreSQL and agent build tooling patched.
13. Perform an independent security review before using the system on sensitive or internet-exposed infrastructure.

## Deliberately not included

- Arbitrary PowerShell, CMD, remote desktop, file browser, credential dumping, or unrestricted command execution.
- A server endpoint that tells the agent to download and run an arbitrary executable.
- Disabling TLS verification.


## Endpoint compliance and browser policy controls

- Unknown software inventory is treated as untrusted data and is never converted into shell text.
- Admin "Uninstall" creates a typed `uninstall_detected` task containing only the detected display name. In LIVE mode the agent calls Winget as a structured process invocation; arbitrary shell text is not accepted.
- Per-machine software exceptions are exact-name exceptions and do not globally approve an application.
- Required/Optional/Blocked policy only references server-side AppCatalog records.
- Managed browser policy writes only structured numbered string values under Microsoft Edge / Google Chrome `URLBlocklist` and `URLAllowlist` policy keys. No registry path/value name is accepted from the browser or server payload.
- Treat VarunOps as the sole manager of those Edge/Chrome URL list entries on enrolled PCs. The agent rewrites the numbered values to the assigned policy; parallel GPO/MDM management of the same keys can conflict.
- Allowlist browser policy is not equivalent to a DNS/firewall gateway and does not claim to control every application.
- Strict allow-only executable enforcement (WDAC/AppLocker) is deliberately not auto-generated/applied because a bad policy can lock legitimate endpoints. Stage that capability separately with audit mode and signed policies.
- Device pairing requires a short-lived, single-use code that can only be generated from an authenticated employee session; the employee account must not already have an assigned managed PC.
- Telemetry is capped and retained as a rolling 48-hour high-resolution metric window.

## Software licensing policy

VarunOps does not support software cracks, activation bypasses, pirated packages or auto-crack scripts. The catalog can store non-secret legal license/activation notes. Product keys/secrets should live in a dedicated secrets/licensing system rather than plaintext catalog fields.

## Per-device catalog authorization

- Employee software visibility is derived from the authenticated employee's server-side assigned machine.
- Once a machine has explicit app-policy rows, the employee store becomes an explicit per-machine allowlist.
- Hidden/Blocked apps are rejected server-side even if a user guesses the catalog slug.
- Required apps cannot be uninstalled through employee requests, and the same policy is re-checked again when IT approves the request.
- The admin command API also re-checks Blocked/Required software policy so browser manipulation cannot bypass the configured app state.

## Direct installer controls

- Direct installers must use HTTPS.
- The catalog must contain an exact 64-character SHA-256 digest.
- The Windows agent computes SHA-256 after download and refuses execution on mismatch.
- Only EXE/MSI types and bounded argument arrays are accepted.
- Every newly paired PC starts in TEST mode; command/remediation dequeue is blocked server-side until an administrator enables LIVE actions on that specific device.
