# VarunOps — Free deployment for real testing

> Free tiers are useful for testing and small hobby deployments. No vendor can guarantee that a free tier will exist forever or remain always-on.

## Recommended current stack

- **Web app:** Render Free Web Service
- **Persistent database:** Neon Free PostgreSQL
- **Ticket screenshots:** stored as small authenticated blobs in PostgreSQL, so they survive Render restarts
- **Windows endpoints:** VarunOps PowerShell agent installed from the Employee Portal

Do **not** use Render Free Postgres for persistent VarunOps data. Its free database has a limited lifetime. Use Neon through `DATABASE_URL`.

## 1. Put this project on GitHub

Create a private repository and upload the project root (the folder containing `manage.py` and `render.yaml`). Never commit `.env`, `db.sqlite3`, agent credentials, or real passwords.

## 2. Create Neon PostgreSQL

1. Create a Neon account/project.
2. Copy the PostgreSQL connection string from Neon.
3. Prefer the pooled connection string when Neon offers it.
4. Keep `sslmode=require` in the connection string.

Example only:

`postgresql://USER:PASSWORD@HOST/DB?sslmode=require`

## 3. Create Render Web Service

Use **New > Blueprint** (or Web Service) and connect the GitHub repository. `render.yaml` already contains the build/start commands.

Add these environment values in Render:

- `DATABASE_URL` = Neon connection string
- `ADMIN_PASSWORD` = unique 14+ character password
- `ADMIN_EMAIL` = your email

Render generates `SECRET_KEY` and `AGENT_ENROLLMENT_TOKEN`. `RENDER_EXTERNAL_HOSTNAME` is used automatically by Django for host/CSRF configuration.

Deploy. The start command runs migrations, creates the admin when needed, and launches Gunicorn.

## 4. First real login

Open:

`https://YOUR-SERVICE.onrender.com/login/`

Username defaults to `admin`. Use the `ADMIN_PASSWORD` you configured.

## 5. Add employee and PC

1. Admin > **Employees** > Add employee.
2. Give the employee their temporary credentials privately.
3. Employee signs in > completes **Profile**.
4. Employee opens **My PC** > **Generate code**.
5. Employee downloads **PC Connector**.
6. On that Windows PC: extract ZIP > run `CONNECT_THIS_PC.bat` as Administrator > enter pairing code.
7. Within the next polling cycles, Admin > **Devices** shows hardware, software, CPU/RAM/storage, last-seen, and power events.

## 6. Test before enabling changes

Every new PC starts with software execution **TEST** mode.

First confirm:
- correct employee-PC pairing
- accurate inventory
- correct approved software list
- correct website policy
- no false unauthorized-software alerts

Then Admin > **Devices** > **Details** > **Enable LIVE actions**.

## 7. Software Store — where does the installer come from?

### Preferred: Winget

Admin > Software > Add software:
- Source: Winget
- Winget ID: e.g. vendor/package identifier
- Detection name(s)
- version/license notes

The endpoint asks Winget to install/update/uninstall that exact package.

### Direct EXE/MSI

Use only a vendor/company-controlled HTTPS URL.

Required fields:
- HTTPS installer URL
- EXE or MSI
- exact SHA-256 checksum
- silent install/update arguments
- detection name(s)

The agent downloads the file, computes SHA-256, and refuses to execute if it does not match.

Do not put cracks, license bypass scripts, or pirated installers into VarunOps.

## 8. Software policy

Per PC, set catalog apps as:
- **Required** — must exist; Enforce mode queues an install when missing
- **Optional** — appears in that employee's company store; employee can request it
- **Blocked** — cannot be requested and Enforce mode removes a catalog-installed blocked app

If a PC has any explicit app policies, employee Software becomes a strict per-PC allowlist.

Unknown software is detected from Windows inventory and creates an Admin warning. Admin can allow that name as a per-PC exception or queue an uninstall attempt. Detection alone cannot reliably prove which human installed it.

## 9. Website policies

Create Allowlist or Blocklist policies and assign them per PC.

Current enforcement uses managed policy keys for Microsoft Edge and Google Chrome. This does not claim to block every possible browser/application. For true all-app internet filtering use a DNS/Secure Web Gateway in addition to VarunOps.

## 10. Free-tier limitations

- Render Free Web Services may sleep when idle and have no production SLA.
- Agent traffic may keep a service active during working hours.
- Neon Free has usage/storage limits.
- Free-plan terms and limits can change in the future.

For a clinic/company production rollout where downtime matters, move the web service/database to paid tiers after testing.


### Render generated secrets
`render.yaml` uses `generateValue: true` for `SECRET_KEY` and `AGENT_ENROLLMENT_TOKEN`. Render generates a random Base64-encoded 256-bit value (typically 44 characters), which this build accepts as a strong production secret. Do not replace it with a short human password.
