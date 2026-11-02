# Project 2 — Scenario A: secure application delivery over 5G

Scenario A reuses the 5G Standalone path from Project 1
(`UE → gNB → UPF → N6 → application`) and turns it into a **secure application
delivery path**: a Django application on a private network behind an Nginx **TLS
reverse proxy**, with the lab PKI and HTTP→HTTPS redirection.

Everything is built **on top of** the inherited `scenario-b/` deployment; the base
runbook (`scenario-b/README.md` §7) is unchanged.

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
- 1C–1E: pending.

## Directory

```
project2/scenario-a/
├── README.md                   # this plan
├── AGENTS.md                   # exact Scenario A contract
├── ueransim/                   # Phase 1A: UERANSIM v3.3.0 Dockerfile + p2-init.sh
├── docker-compose.ueransim.yaml# compose override: nr_gnb and nr_ue use the p2 image
├── django/                     # Phase 1B: Django 6.0.8 + Gunicorn + SQLite
├── docker-compose.p2.yaml      # Phase 1B: django-data volume, app-net (internal)
├── env.example                 # template of the git-ignored ./env (secret key)
└── scripts/
    ├── build.sh                # build telecom-lab-ueransim:3.3.0-p2
    ├── upgrade-ran.sh          # recreate nr_gnb then nr_ue with the p2 image
    ├── verify-phase1a.sh       # acceptance for phase 1A
    └── verify-phase1b.sh       # acceptance for phase 1B
```

Later phases add `nginx/`, `pki/` and the gateway service in
`docker-compose.p2.yaml`.

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

## Run (phase 1B)

```bash
cd project2/scenario-a
cp env.example env                  # then replace DJANGO_SECRET_KEY
docker compose -f docker-compose.p2.yaml up -d --build
./scripts/verify-phase1b.sh
```

## Run (phase 1A)

```bash
cd scenario-b
./scripts/fetch-upstream.sh        # if not already done (provides docker_ueransim)
./scripts/deploy.sh                # base deployment (core, gNB, UE, subscriber)
sudo ./scripts/enable-n6.sh        # N6 + apps, no NAT
cd ../project2/scenario-a
./scripts/build.sh                 # build UERANSIM v3.3.0 + route watcher
./scripts/upgrade-ran.sh           # recreate nr_gnb and nr_ue with that image
./scripts/verify-phase1a.sh        # route via uesimtun0, survives a restart
```

## Working specification

See the [root README](../../README.md#working-specification-from-the-brief--confirm-before-wiring)
for the values used while scaffolding (UE pool, N6, `app-net`, PKI, TLS policy).
If your copy of the brief differs, that table is the single place to change.
