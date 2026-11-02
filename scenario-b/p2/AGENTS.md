# AGENTS.md — Project 2, Scenario A (phases 1A–1E)

Exact contract from the brief for the secure application path. Root
[`../../AGENTS.md`](../../AGENTS.md) and [`../AGENTS.md`](../AGENTS.md) still
apply. **Do not simplify the acceptance criteria.**

## Path

```text
UE → 5G PDU session → gNB → N3/GTP-U → UPF → N6 → Nginx 10.20.6.20
   → (TLS termination) → app-net → Django 10.20.8.20:8000
```

Direct access to `10.20.8.20:8000` is troubleshooting only; the **final**
demonstration must cross the 5G user plane.

## Images (locally built)

| Image | Base | Notes |
|---|---|---|
| `telecom-lab-nginx:p2` | `nginx:latest` + `iproute2` | TLS, proxy, HTTP→HTTPS, routes for the UE PDU path |
| `telecom-lab-django:0.1` | `python:3.12-slim` | Django **6.0.8**, Gunicorn, SQLite |
| `telecom-lab-ueransim:3.3.0-p2` | `gradiant/ueransim:3.3.0` | keeps `10.20.6.0/24 → uesimtun0` after container recreation |

Verification-only, `docker run --rm`, never part of the runtime: `curlimages/curl:latest`, `alpine`.

> ⚠️ Current scaffold builds the UE image `FROM docker_ueransim:latest` (Project
> 1). The brief names `gradiant/ueransim:3.3.0`. This is an **open decision**
> (root §8); resolve it before claiming 1A complete.

## Places and files

| Thing | Where |
|---|---|
| Django DB | `/app/data/db.sqlite3`, named volume `django-data`, must survive container recreation |
| UE CA | `/etc/telecom-lab/ca.crt` (read-only) |
| Nginx cert/key | mounted read-only |
| CA private key | host only, **mounted into no container** |
| Repo exclusions | `env`, `secrets/tls/` |

Django is configured through environment variables (secret key, debug, allowed
hosts). **Do not hardcode secrets.**

## Phase 1A — reuse and verify

- UE registers, PDU session established, `uesimtun0` exists with `10.45.0.x`.
- Route **`10.20.6.0/24 dev uesimtun0`** installed; `ip route get 10.20.6.20`
  resolves via `uesimtun0`, including **after `docker restart` of the UE**.
- UE can reach `10.20.6.20`.

> Note: the scaffold's watcher also installs `default dev uesimtun0` (a Project 1
> carry-over). The brief only requires the `/24` route. Keep the default route
> only if it is verified not to break management/DNS traffic, and document why.

## Phase 1B — Django

- Container `scenario-b-django` on **`app-net` only** (never `dn-net`).
- `GET /health/` returns exactly:

```json
{"service": "project2-django", "status": "ok", "project": "Telecommunication Security"}
```

- Docker `healthcheck` must report healthy; migrations run before creating the
  lab account; Nginx must reach Django.
- Evidence: Dockerfile, `requirements.txt`, compose service, healthcheck,
  health status, `app-net` config, `django-data` volume, `/health/` response.

## Phase 1C — Nginx + TLS

- Container `scenario-b-nginx`: `dn-net 10.20.6.20`, `app-net 10.20.8.10`.
- TLS 1.2 **and** 1.3, termination at Nginx, `X-Forwarded-Proto: https`,
  proxy to `http://10.20.8.20:8000`.
- `HTTP:80 → 301 → HTTPS:443 → 200`.
- Cert validation from the UE with `--cacert`, **never `-k`** as the final proof.
- TLS evidence: subject, issuer, validity, SAN, both handshakes, UE request.

## Phase 1D — Django security baseline

Endpoints: `/`, `/health/`, `/api/status/`, `/search/`, `/accounts/login/`,
`/accounts/logout/`, `/profile/`, `/feedback/`, `/admin/`.
Public: `/`, `/health/`, `/api/status/`, `/search/`.
Protected: `/profile/`, `/feedback/` (Django auth). Lab user: `securityadmin`.

Required behavior:

| Case | Result |
|---|---|
| Unauth `GET /profile/` | `302` → `/accounts/login/` |
| Auth `GET /profile/` | `200`, `Username: securityadmin`, `Authenticated: True` |
| Auth `POST /feedback/` + valid CSRF | `200` |
| Auth `POST /feedback/` without/invalid CSRF | `403` (keep CSRF enforced) |

Settings (exact):

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
```

Cookie evidence: session `Secure; HttpOnly; SameSite=Lax`; CSRF `Secure`.
Headers: `Strict-Transport-Security: max-age=3600`, `X-Frame-Options: DENY`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
Keep Django's security middleware enabled; record **actual** header values.

## Phase 1E — acceptance (gate into Scenario B)

From the UE, through the 5G path: `HTTP 301` → HTTPS `200` with trusted CA;
`/`, `/health/`, `/api/status/`, `/search/`; the four auth cases; the two CSRF
cases; headers and cookies above. Automate it in `verify-phase1.sh` and archive
the output. **No new application or tool in 1E.**

## Status tracking

Update the table in the root `README.md` when a phase goes green. Never mark a
phase done without its verification artifact.
