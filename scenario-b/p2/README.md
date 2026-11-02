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
| **1A** | UE image with a **persistent user-plane route**: `telecom-lab-ueransim:3.3.0-p2` | `ip route get 10.20.6.20` resolves via `uesimtun0` **and survives `docker restart nr_ue`** |
| **1B** | Django + Gunicorn + SQLite on a private `app-net` (`10.20.8.0/24`, internal) | container `healthy`; `/health/` reachable from Nginx only |
| **1C** | Lab PKI + Nginx TLS gateway on N6 (`10.20.6.20`) | from the UE: `https://…/health/` returns **200 without `-k`**; `http://` returns **301** |
| **1D** | Django security baseline (login, CSRF, secure cookies, HSTS, headers) | acceptance list green |
| **1E** | End-to-end acceptance from the UE through the 5G path | `verify-phase1.sh` all green |

Scenario B (Jenkins, ZAP, Suricata, Trivy/Syft) starts only after 1E is green.

## Directory

```
scenario-b/p2/
├── README.md                   # this plan
├── ueransim/                   # Phase 1A: Dockerfile + p2-init.sh (persistent route)
├── docker-compose.ueransim.yaml# compose override: nr_ue uses the p2 image
└── scripts/
    ├── build.sh                # build telecom-lab-ueransim:3.3.0-p2
    ├── upgrade-ue.sh           # recreate nr_ue with the p2 image + verify
    └── verify-phase1a.sh       # acceptance for phase 1A
```

Later phases add `django/`, `nginx/`, `tls/`, `docker-compose.p2.yaml` and
`verify-phase1.sh`.

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
  then hands control to the original UERANSIM init.
  It also keeps `default dev uesimtun0` (Project 1 behaviour); that part is not
  required by the brief and must be justified or dropped — see
  [`AGENTS.md`](AGENTS.md).
* The image is `telecom-lab-ueransim:3.3.0-p2`, built **on top of** the Project 1
  base (`docker_ueransim`), so the rest of the deployment is untouched.
* `nr_ue` is recreated via a compose override; nothing else changes.

## Run (phase 1A)

```bash
cd scenario-b
./scripts/fetch-upstream.sh      # if not already done (provides docker_ueransim)
./scripts/deploy.sh              # base deployment (core, gNB, UE, subscriber)
sudo ./scripts/enable-n6.sh      # N6 + apps, no NAT
./p2/scripts/build.sh            # build the p2 UE image
./p2/scripts/upgrade-ue.sh      # recreate nr_ue with it
./p2/scripts/verify-phase1a.sh   # route via uesimtun0, survives a restart
```

## Working specification

See the [root README](../../README.md#working-specification-from-the-brief--confirm-before-wiring)
for the values used while scaffolding (UE pool, N6, `app-net`, PKI, TLS policy).
If your copy of the brief differs, that table is the single place to change.
