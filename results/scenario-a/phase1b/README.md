# Phase 1B — evidence

Django 6.0.8 + Gunicorn + SQLite on the isolated `app-net`, container
`scenario-b-django` at `10.20.8.20:8000`.

- Date: 2026-11-02
- Image: `telecom-lab-django:0.1` (`python:3.12-slim`)
- Volume: `django-data` mounted at `/app/data`
- Network: `app-net` `10.20.8.0/24`, `internal: true`

## Commands

```bash
cd ~/5G-2-Security
cp project2/scenario-a/env.example project2/scenario-a/env   # then set the secret
docker compose -f project2/scenario-a/docker-compose.p2.yaml up -d --build
./project2/scenario-a/scripts/verify-phase1b.sh
```

## Result

`verify-phase1b.txt` is the unedited output of the acceptance script:

- `manage.py check` — no issues;
- `scenario-b-django` reports `healthy` through the image healthcheck;
- attached **only** to `app-net`, at `10.20.8.20`; not on `dn-net`;
- `app-net` is `internal` with subnet `10.20.8.0/24`;
- `django-data` exists and a marker file plus `db.sqlite3` survive a
  `--force-recreate` of the container;
- `GET /health/` returns exactly
  `{"service": "project2-django", "status": "ok", "project": "Telecommunication Security"}`;
- requests through an Nginx proxy attached to `app-net` reach Django with
  `200`.

## Note on the Nginx check

The gateway container with TLS is phase 1C. For 1B the "Nginx can reach Django"
condition is demonstrated with a throwaway `nginx:alpine` container
(`p2-nginx-check`) that shares `app-net` and proxies `/health/` to
`10.20.8.20:8000`. It is removed by the script; it is not part of the runtime
architecture. The `Host` header is left at Nginx's default (`10.20.8.20:8000`)
because the throwaway name is not in `DJANGO_ALLOWED_HOSTS`; the real gateway
sends `10.20.6.20`/`telecom-lab.local`, which are.

## Django version

`requirements.txt` pins `Django==6.0.8` and `gunicorn==23.0.0`. Both were
confirmed present on PyPI before the build; the container reports the pinned
version via `pip show`.
