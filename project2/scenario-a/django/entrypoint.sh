#!/usr/bin/env bash
# =============================================================================
# scenario-b-django entrypoint: initialise the database, then serve.
#
# Migrations run before anything else, so the schema is ready before the lab
# account is created (phase 1D) and before the first request arrives.
# =============================================================================
set -euo pipefail

cd /app

python manage.py migrate --noinput

# The account is created only after the schema exists, and only once: an
# existing account keeps its password.
python manage.py ensure_lab_user

exec gunicorn telecom_lab.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --access-logfile - \
    --error-logfile -
