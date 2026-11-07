# Project 2 — Scenario A: secure application delivery over 5G

Scenario A reuses the 5G Standalone path from Project 1
(`UE → gNB → UPF → N6 → application`) and turns it into a **secure application
delivery path**: a Django application on a private network behind an Nginx **TLS
reverse proxy**, with the lab PKI and HTTP→HTTPS redirection.

Everything is built **on top of** the inherited `scenario-b/` deployment; the
base runbook is [`scenario-b/README.md`](../../scenario-b/README.md).

---

## Phases (each depends on the previous)

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **1A** | RAN image pinned to **UERANSIM v3.3.0** with a **persistent user-plane route**: `telecom-lab-ueransim:3.3.0-p2` | `ip route get 10.20.6.20` resolves via `uesimtun0` **and survives `docker restart nr_ue`** |
| **1B** | Django + Gunicorn + SQLite on a private `app-net` (`10.20.8.0/24`, internal) | container `healthy`; `/health/` reachable from Nginx only |
| **1C** | Lab PKI + Nginx TLS gateway on N6 (`10.20.6.20`) | from the UE: `https://…/health/` returns **200 without `-k`**; `http://` returns **301** |
| **1D** | Django security baseline (login, CSRF, secure cookies, HSTS, headers) | acceptance list green |
| **1E** | End-to-end acceptance from the UE through the 5G path | `verify-phase1.sh` all green |

Scenario B (Jenkins, ZAP, Suricata, Trivy/Syft) starts only after 1E is green.

## Status

- **1A — done** (2026-11-02). Evidence:
  [`results/scenario-a/phase1a/`](../../results/scenario-a/phase1a/README.md).
  UERANSIM v3.3.0 image running on gNB and UE; `10.20.6.20` resolves via
  `uesimtun0` and keeps doing so after `docker restart nr_ue`.
- **1B — done** (2026-11-02). Evidence:
  [`results/scenario-a/phase1b/`](../../results/scenario-a/phase1b/README.md).
  `scenario-b-django` healthy on the internal `app-net` only, `/health/` exact,
  `django-data` survives recreation.
- **1C — done** (2026-11-02). Evidence:
  [`results/scenario-a/phase1c/`](../../results/scenario-a/phase1c/README.md).
  `scenario-b-nginx` on `dn-net 10.20.6.20` + `app-net 10.20.8.10`; HTTP 301 →
  HTTPS 200 with the lab CA from the UE, TLS 1.2 and 1.3 verified.
- **1D — done** (2026-11-02). Evidence:
  [`results/scenario-a/phase1d/`](../../results/scenario-a/phase1d/README.md).
  Public/protected endpoints, `securityadmin` login, CSRF 200/403, Secure
  cookies, HSTS 3600 and the four headers.
- **1E — done** (2026-11-02). Evidence:
  [`results/scenario-a/phase1e/`](../../results/scenario-a/phase1e/README.md).
  `verify-phase1.sh` green end to end from the UE: 301 → TLS 200, auth, CSRF,
  cookies, headers, real `10.45.0.x` client at the gateway.

Scenario A is complete; Scenario B may start.

## Directory

```
project2/scenario-a/
├── README.md                   # this plan
├── AGENTS.md                   # exact Scenario A contract
├── ueransim/                   # Phase 1A: UERANSIM v3.3.0 Dockerfile + p2-init.sh
├── docker-compose.ueransim.yaml# compose override: nr_gnb and nr_ue use the p2 image
├── django/                     # Django 6.0.8: app, templates, Gunicorn, SQLite
├── nginx/                      # Phase 1C: gateway image, TLS config, return route
├── pki/                        # Phase 1C: OpenSSL configs (CA + server SAN)
├── docker-compose.p2.yaml      # django + nginx, app-net (internal) + dn-net
├── env.example                 # template of the git-ignored ./env (secrets)
└── scripts/
    ├── build.sh                # build telecom-lab-ueransim:3.3.0-p2
    ├── upgrade-ran.sh          # recreate nr_gnb then nr_ue with the p2 image
    ├── verify-phase1a.sh       # acceptance for phase 1A
    ├── verify-phase1b.sh       # acceptance for phase 1B
    ├── gen-pki.sh              # create secrets/tls/ (CA + server certificate)
    ├── up.sh                   # start django + scenario-b-nginx
    ├── verify-phase1c.sh       # acceptance for phase 1C
    ├── verify-phase1d.sh       # acceptance for phase 1D
    └── verify-phase1.sh        # end-to-end acceptance (phase 1E, gate to B)
```

Scenario A ends with `verify-phase1.sh`; Scenario B starts after it is green.

## Phase 1A — what and why

In Project 1 the user-plane route (`default dev uesimtun0`) was installed **from
the host** after each registration (`deploy.sh`). If the UE container restarts,
UERANSIM recreates `uesimtun0` **without** the route, and every packet toward N6
silently leaves via the management interface.

Project 2 needs the route to be a property of the **UE image**, not of a host
script:

* `ueransim/p2-init.sh` starts a small watcher that, whenever `uesimtun0` exists,
  keeps the route the brief requires — **`10.20.6.0/24 dev uesimtun0`** — installed,
  so N6 traffic enters the PDU tunnel instead of the Docker `ran-net` path, and
  then hands control to the original UERANSIM init. The Project 1 `default` route
  is **not** installed: the brief asks for the narrow N6 route, and a default
  route would push management/DNS traffic into the tunnel.
* The image is `telecom-lab-ueransim:3.3.0-p2`, built **from source** at UERANSIM
  tag `v3.3.0`, so the running RAN matches the version the brief specifies.
  The Project 1 image (`herlesupreeth/docker_ueransim:latest`) is built from
  `v3.2.6`; using it would leave the deployment one release behind. The gNB and
  the UE both run the pinned image, so they cannot drift apart.
  The brief names `gradiant/ueransim:3.3.0`; that environment is not deployed in
  the lab, so the substitution is recorded in the report (see `AGENTS.md`).
* `nr_gnb` and `nr_ue` are recreated via a compose override; nothing else
  changes.

## Phase 1B — what and why

The application never touches N6. `scenario-b-django` is attached **only** to
`app-net` (`10.20.8.0/24`, `internal: true`), so it has no route to the data
network or the internet; the only path in will be the gateway in phase 1C.

* `django/` — Django 6.0.8 project (`telecom_lab`), Gunicorn, SQLite at
  `/app/data/db.sqlite3`. Everything environment-specific (secret key, debug,
  allowed hosts) comes from the environment; `env` is git-ignored and
  `env.example` documents the keys.
* The image runs as a non-root user. `/app/data` is created with that ownership
  so the named volume inherits it and SQLite stays writable.
* `entrypoint.sh` runs `manage.py migrate --noinput` before Gunicorn, which
  satisfies the "migrations before the lab account" order for phase 1D.
* A Docker `HEALTHCHECK` probes `http://127.0.0.1:8000/health/`, so the
  container reports `healthy` without an external tool.
* `verify-phase1b.sh` proves isolation, health, volume persistence, the exact
  `/health/` body, and that an Nginx proxy on `app-net` reaches Django.

## Phase 1C — what and why

* **PKI.** `scripts/gen-pki.sh` creates a 4096-bit root CA and a 2048-bit
  server key in `secrets/tls/` (git-ignored). The server certificate carries the
  SAN the UE validates — `IP:10.20.6.20`, `DNS:telecom-lab.local`,
  `DNS:localhost` — and is signed by the lab CA. The CA key stays on the host
  and is mounted into **no** container; only `server.crt`/`server.key` reach the
  gateway, and only `ca.crt` reaches the verification client.
* **Gateway.** `telecom-lab-nginx:p2` extends `nginx:latest` with `iproute2` and
  a `/docker-entrypoint.d` hook that installs `10.45.0.0/16 via 10.20.6.2` on
  every start, so replies to the UE return through the UPF (Project 1 did this
  by hand). Nginx terminates TLS 1.2/1.3, redirects `:80` with `301`, and
  proxies to `http://10.20.8.20:8000` with `X-Forwarded-Proto: https`.
* **Addressing.** `dn-net 10.20.6.20` + `app-net 10.20.8.10`. Django stays
  attached only to `app-net`.
* **Superseded container.** `sb-nginx` (Project 1's N6 test endpoint) also uses
  `10.20.6.20`; `up.sh` removes it before starting the gateway. Do not run
  `scenario-b/scripts/enable-n6.sh` after this phase — it would recreate it.
* **UE-side proof.** The UE image has no TLS client, so acceptance runs `curl`
  and `openssl s_client` in a throwaway container that shares `nr_ue`'s network
  namespace, with `ca.crt` at `/etc/telecom-lab/ca.crt` and `--cacert`/`-CAfile`.
  Traffic therefore exits through `uesimtun0`; `-k` is never used.

## Phase 1D — what and why

* **Endpoints.** Public `/`, `/health/`, `/api/status/`, `/search/`; protected
  `/profile/`, `/feedback/` via `@login_required`; Django's `admin/` and
  `accounts/` URL sets. `/search/` echoes the query through templates, so
  autoescaping is observable (and is a useful negative test later).
* **Account.** `manage.py ensure_lab_user` runs after `migrate` in the entrypoint
  and creates `securityadmin` from `LAB_ADMIN_USER`/`LAB_ADMIN_PASSWORD`
  (git-ignored `env`). It never resets an existing password.
* **Cookies and proxy.** `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
  `HttpOnly`, `SameSite=Lax`; `SECURE_PROXY_SSL_HEADER` makes Django trust
  `X-Forwarded-Proto: https` from the gateway, which is also what enables HSTS.
* **Baseline.** `SECURE_HSTS_SECONDS = 3600` with subdomains/preload off,
  `X_FRAME_OPTIONS = DENY`, `SECURE_CONTENT_TYPE_NOSNIFF`,
  `SECURE_REFERRER_POLICY = same-origin`; the security middleware stays first
  in `MIDDLEWARE`.
* **CSRF stays enforced.** The acceptance script performs a real token flow
  (cookie + form token + `Origin`) and then proves that a missing or invalid
  token returns `403`. Nothing is exempted.

## Run — full sequence

```bash
# 1A — base network, UE route
cd scenario-b
cp env.example .env                 # once; git-ignored
./scripts/fetch-upstream.sh         # once: pinned upstream clone
./scripts/deploy.sh                 # core, gNB, UE, subscriber
sudo ./scripts/enable-n6.sh         # N6 (dn-net) + iperf3, no NAT
cd ../project2/scenario-a
./scripts/build.sh                  # UERANSIM v3.3.0 + route watcher
./scripts/upgrade-ran.sh            # nr_gnb and nr_ue use the pinned image
./scripts/verify-phase1a.sh

# 1B — Django on app-net
cp env.example env                  # then replace the secrets
docker compose -f docker-compose.p2.yaml up -d --build
./scripts/verify-phase1b.sh

# 1C — PKI and TLS gateway
./scripts/gen-pki.sh                # once; --force replaces the whole PKI
./scripts/up.sh                     # django + scenario-b-nginx
./scripts/verify-phase1c.sh

# 1D — security baseline (already deployed by 1C; rebuild if code changed)
docker compose -f docker-compose.p2.yaml up -d --build django
./scripts/verify-phase1d.sh

# 1E — gate into Scenario B
./scripts/verify-phase1.sh
```

If you re-run `scenario-b/scripts/deploy.sh`, replay the N6 and RAN steps in
this order before trusting 1E:

```bash
cd ~/5G-2-Security
docker rm -f sb-nginx scenario-b-nginx 2>/dev/null || true
cd scenario-b && sudo ./scripts/enable-n6.sh && cd ..
./project2/scenario-a/scripts/upgrade-ran.sh
./project2/scenario-a/scripts/up.sh
./project2/scenario-a/scripts/verify-phase1.sh
```

`enable-n6.sh` recreates the UPF. A UE that registered before that recreation
keeps a dead PDU session: N6 checks fail until `upgrade-ran.sh` registers it
again. A running `scenario-b-nginx` also holds `10.20.6.20`, so remove it
before `enable-n6.sh` starts `sb-nginx`.

## Phase 1E — what and why

One script, no new application code and no new runtime image. It reuses the
verification-only `curlimages/curl` and the gateway image for `openssl`, both
`docker run --rm`, and drives the complete contract from the UE network
namespace:

* data path (`uesimtun0`, route, N6 reachability);
* certificate chain and TLS 1.2 / 1.3 handshakes;
* `HTTP 301 → HTTPS 200` with the lab CA (never `-k`);
* the four public endpoints and the exact `/health/` body;
* the four authentication cases, the two CSRF outcomes, cookie attributes,
  security headers and input escaping;
* the real `10.45.0.x` client address in the gateway log (proof that the flow
  crossed the 5G user plane, not a direct connection).

## Working specification

See the [root README](../../README.md#working-specification-from-the-brief--confirm-before-wiring)
for the values used while scaffolding (UE pool, N6, `app-net`, PKI, TLS policy).
If your copy of the brief differs, that table is the single place to change.
