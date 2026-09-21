# VarunOps — Free test deployment

Free tiers can change and do not provide a lifetime/production availability guarantee.

## Suggested test stack

- Django web/API: Render Free Web Service
- PostgreSQL: Supabase Free Postgres (or another compatible PostgreSQL service)
- OTP email: Resend Free HTTPS API
- Endpoints: Windows PowerShell VarunOps Agent

## 1. PostgreSQL

Create a Supabase project and copy a PostgreSQL connection string suitable for your hosting environment. Put the complete PostgreSQL URI in Render as `DATABASE_URL`.

Do not use SQLite on Render: the free web-service filesystem is ephemeral.

## 2. Resend OTP email

Render Free blocks outbound SMTP ports, so this build uses the **Resend HTTPS API** instead of SMTP when `RESEND_API_KEY` is configured.

Create a Resend **sending-only** API key. For real employee recipients, verify a sending domain in Resend and use an address on that domain as `DEFAULT_FROM_EMAIL`.

Render environment values:

- `RESEND_API_KEY=<Resend sending API key>`
- `DEFAULT_FROM_EMAIL=VarunOps <it@your-verified-domain>`

Local/non-Render environments can still use the optional Django SMTP fallback from `.env.example`.

## 3. GitHub + Render

Push the project root (contains `manage.py` + `render.yaml`) to a **private** GitHub repository. Do not commit `.env`, `db.sqlite3`, passwords, API keys or device credentials.

Create a Render Blueprint/Web Service from the repository. `render.yaml` contains the build/start commands.

Set these required Render values:
- `DATABASE_URL`
- `ADMIN_PASSWORD`
- `ADMIN_EMAIL`
- `RESEND_API_KEY`
- `DEFAULT_FROM_EMAIL`

Render generates `SECRET_KEY` and `AGENT_ENROLLMENT_TOKEN`.

Deployment start command applies migrations, creates/updates the production admin and starts Gunicorn.

## 4. Employee onboarding

Admin > Employees > Add employee:
- username
- employee code
- first/last name
- email for OTP
- department
- branch
- job title

Copy the temporary password once and send it privately.

Employee login is restricted to onboarding until:
- PC is paired,
- first hardware + telemetry report arrives,
- email OTP is verified,
- a permanent password is set.

IT can edit the employee email/details and reissue a temporary password. IT never receives the final permanent password.

## 5. Connect Windows PC

Employee generates a pairing code, downloads PC Connector, extracts it and runs `CONNECT_THIS_PC.bat` as Administrator. Keep the PC online for the first full report (normally around a minute).

New PCs start in TEST software-execution mode. Verify the device/inventory/policies, then enable LIVE actions from Admin > Devices > Details.

## 6. Scale notes for 60+ devices

Default agent reporting is intentionally reduced:
- live telemetry ~60 sec
- software inventory ~15 min
- sampled telemetry ~15 min / 7-day retention

60 continuously reporting endpoints can generate a meaningful amount of HTTP and database traffic. Monitor Render/Supabase usage dashboards and storage. Avoid storing large ticket screenshots in the database and move to paid hosting/storage if uptime, backups or limits become important.
