#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  echo ""
  echo "============================================================"
  echo "VARUNOPS STARTUP FAILED"
  echo "$1"
  echo "============================================================"
  exit 1
}

trap 'code=$?; echo ""; echo "VARUNOPS STARTUP FAILED at shell line ${LINENO} (exit ${code}). Check the command output immediately above."; exit ${code}' ERR

echo "============================================================"
echo "VarunOps production startup"
echo "============================================================"
python --version

[ -n "${DATABASE_URL:-}" ] || fail "DATABASE_URL is missing. Add the PostgreSQL connection string in Render -> Environment."
[ -n "${SECRET_KEY:-}" ] || fail "SECRET_KEY is missing. Redeploy from render.yaml or add a strong generated SECRET_KEY in Render -> Environment."

echo "[env] DATABASE_URL: present"
echo "[env] SECRET_KEY: present"
echo "[env] ADMIN_USERNAME: ${ADMIN_USERNAME:-admin}"
if [ -n "${ADMIN_PASSWORD:-}" ]; then
  echo "[env] ADMIN_PASSWORD: present (value hidden)"
else
  echo "[env] ADMIN_PASSWORD: not set (allowed only if the admin already exists)"
fi

echo ""
echo "[1/4] Applying database migrations..."
python manage.py migrate --noinput

echo ""
echo "[2/4] Running Django system checks..."
python manage.py check

echo ""
echo "[3/4] Ensuring production administrator exists..."
python manage.py bootstrap_production

echo ""
echo "[4/4] Starting Gunicorn..."
exec gunicorn varunops.wsgi:application \
  --bind "0.0.0.0:${PORT:-10000}" \
  --workers 1 \
  --threads 4 \
  --timeout 90 \
  --access-logfile - \
  --error-logfile -
