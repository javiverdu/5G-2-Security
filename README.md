# 5G-2-Security

**Project 2 — Telecommunication Security, DevSecOps, and Traffic Intelligence**

This repository is a **fork of Project 1** (`5G-project-RTU`, full history kept).
Only **Project 2 documentation** is maintained here. The inherited 5G Standalone
code remains, but the Project 1 reports, screenshots and PDF were removed from
the working tree.

> **Workflow:** Secure the app path → test it → automate the testing → observe and correlate.

## Scenarios

* **Scenario A — secure application delivery over 5G.** Reuse the 5G SA path and
  add a **Django application** behind an **Nginx TLS reverse proxy**: a public
  Data Network (N6) and a **private application network**, lab PKI, HTTP→HTTPS
  redirection, and a security baseline (login, CSRF, secure cookies, HSTS).
* **Scenario B — DevSecOps security-testing pipeline.** Jenkins + Selenium +
  OWASP ZAP + Suricata + Trivy/Syft against a Juice Shop target, packet capture,
  event correlation and a security gate.

## Status

| Scenario | Phase | Description | Status |
|---|---|---|---|
| A | 1A | 5G SA base + **persistent UE route** (survives container restart) | ✅ done |
| A | 1B | Django + Gunicorn + SQLite on a private `app-net`, `/health/` | ✅ done |
| A | 1C | Lab PKI + Nginx TLS gateway (`80 → 301 → 443`) | ✅ done |
| A | 1D | Django security baseline (login, CSRF, cookies, HSTS, headers) | ✅ done |
| A | 1E | End-to-end acceptance from the UE through the 5G path | ✅ done |
| B | 2A | Preflight + environment acceptance (Jenkins, Juice Shop, Selenium, capture, Suricata, Trivy/Syft) | ✅ done |
| B | 2B–2E | ZAP/Selenium/SQLi, PCAP + Suricata, Trivy/Syft, correlation + gate | ⬜ pending |

## Structure

```
5G-2-Security/
├── README.md                 # this file: overview, run and verification
├── AGENTS.md                 # design invariants that survive compaction
├── docs/
│   ├── brief-p2.txt          # Project 2 brief as text, for agents/tools
│   └── (Project 1 reports removed)
├── scenario-b/               # inherited 5G SA base (code + runbook)
├── project2/
│   ├── scenario-a/           # secure application delivery (1A–1E)
│   └── scenario-b/           # security CI/CD pipeline (2A–2E)
├── scripts/                  # inherited Project 1 tooling (reference)
└── results/                  # Project 2 evidence
```

## Run the environment

All container work runs on the **Ubuntu VM `UWUNTU`**, not on the host and not
on the VirtualBox shared folder. From the host:

```bash
VBoxManage startvm UWUNTU --type gui        # or start it from the VirtualBox GUI
ssh uwuntu
```

Inside the VM:

```bash
cd ~/5G-2-Security

# ---------------------------------------------------------------- Scenario A
# First time only: create the git-ignored inputs.
cd scenario-b && cp env.example .env && cd ..

# 1. Base 5G core, gNB, UE and subscriber
cd scenario-b
./scripts/fetch-upstream.sh                  # first clone only
./scripts/deploy.sh
sudo ./scripts/enable-n6.sh                  # N6 + no NAT; asks for sudo
cd ..

# 2. Project 2 RAN and application layer
./project2/scenario-a/scripts/build.sh       # first clone only
./project2/scenario-a/scripts/upgrade-ran.sh # UERANSIM v3.3.0 + narrow route
cp -n project2/scenario-a/env.example project2/scenario-a/env
# edit project2/scenario-a/env: DJANGO_SECRET_KEY, LAB_ADMIN_PASSWORD
./project2/scenario-a/scripts/gen-pki.sh     # once; creates secrets/tls/
./project2/scenario-a/scripts/up.sh          # Django + TLS gateway

# ---------------------------------------------------------------- Scenario B
cp -n project2/scenario-b/env.example project2/scenario-b/env
# edit project2/scenario-b/env: JENKINS_ADMIN_PASSWORD
./project2/scenario-b/scripts/up.sh          # build, start, create the job
```

`upgrade-ran.sh` is required after every `deploy.sh`: the inherited deploy uses
the Project 1 UERANSIM image and a default route; Project 2 replaces it with
UERANSIM v3.3.0 and the narrow `10.20.6.0/24 dev uesimtun0` route.

`scenario-a/up.sh` removes the inherited N6 test container `sb-nginx` because
it also uses `10.20.6.20`. Do not run `enable-n6.sh` again after that, or it
will recreate the conflicting container.

## Verify the steps

### Scenario A — end-to-end gate (1E)

```bash
cd ~/5G-2-Security
./project2/scenario-a/scripts/verify-phase1.sh
echo $?                    # must be 0
```

Expected: every line is `[ OK ]`, no `[FAIL]`, and the summary reports
`0 check(s) failed`. The script drives real requests from the UE network
namespace: `uesimtun0`, `10.20.6.20` via `uesimtun0`, TLS with `--cacert`
(never `-k`), HTTP 301 → HTTPS 200, login, CSRF 200/403, cookies, headers and
the real `10.45.0.x` address in the gateway log.

Quick intermediate checks:

```bash
docker exec nr_ue ip -4 addr show uesimtun0       # 10.45.0.x/16
docker exec nr_ue ip route get 10.20.6.20         # dev uesimtun0
docker ps --format '{{.Names}} {{.Status}}'       # nr_gnb, nr_ue, scenario-b-nginx, scenario-b-django
```

### Scenario B — preflight (2A) through Jenkins

```bash
cd ~/5G-2-Security
./project2/scenario-b/scripts/run-pipeline.sh
echo $?                    # must be 0
```

Expected at the end:

```text
[run] build N result: SUCCESS
[preflight] PASS — 0 failed of 35
```

Artifacts are written by the Jenkins build to
`results/scenario-b/phase2a/<RUN_ID>/`:

| File | Check |
|---|---|
| `baseline-1e.txt` | Scenario A gate output; must contain no `FAIL` |
| `preflight.json` | `jq -r '.decision'` = `PASS`; 35 checks |
| `preflight.md` | human-readable table with the same decision |
| `preflight-capture.pcapng` | non-empty proof capture |

On the VM:

```bash
R=$(ls -d ~/5G-2-Security/results/scenario-b/phase2a/*/ | tail -1)
jq -r '.decision, (.checks | length)' "$R/preflight.json"
grep -c '\[FAIL\]' "$R/baseline-1e.txt" || true
```

Jenkins UI: <http://127.0.0.1:8080/job/scenario-b-security/>. Log in as
`securityadmin` with the password from `project2/scenario-b/env`.

The archived green run used in this repository is
[`results/scenario-b/phase2a/20261102T230116Z/`](results/scenario-b/phase2a/20261102T230116Z/).

## Working specification

| Item | Value |
|---|---|
| UE PDU pool | `10.45.0.0/16` (`uesimtun0`) |
| N6 / data network | `dn-net` `10.20.6.0/24`; `scenario-b-nginx` at `10.20.6.20` |
| Private application network | `app-net` `10.20.8.0/24` (internal); `scenario-b-django` at `10.20.8.20:8000`; Nginx `10.20.8.10` |
| Security test network | `security-net` `10.20.10.0/24`; Juice Shop `.20:3000`, Selenium `.30:4444`, Jenkins `.40:8080` |
| Lab PKI | local root CA; server cert with `SAN = IP:10.20.6.20` |
| TLS policy | TLS 1.2/1.3, `HTTP:80 → 301 → HTTPS:443` |
| UE image (Project 2) | `telecom-lab-ueransim:3.3.0-p2` |

## Environment notes

- VM: 10 GB RAM, 32 GB disk, 4 GB swap. The full Project 2 image set leaves
  little free space; the inherited observability stack (`metrics`, `grafana`)
  is disabled by default. Set `ENABLE_OBSERVABILITY=1` only if the images fit.
- The host has frozen the guest under memory pressure. Recovery: hard poweroff,
  boot, then the run sequence above.
- `env`, `secrets/tls/`, `*.pcap` and `*.pcapng` are git-ignored and must never
  be committed. The CA private key is mounted into no container.
- The brief is readable by tools at [`docs/brief-p2.txt`](docs/brief-p2.txt).

## Repository

Project 2: [`javiverdu/5G-2-Security`](https://github.com/javiverdu/5G-2-Security).
Forked from [`javiverdu/5G-project-RTU`](https://github.com/javiverdu/5G-project-RTU)
(Project 1 history retained).

```bash
git clone https://github.com/javiverdu/5G-2-Security.git ~/5G-2-Security
```

Clone to a **native VM path**, not the VirtualBox shared folder: vboxsf breaks
container mounts and permissions.

## For AI agents / new sessions

- [`AGENTS.md`](AGENTS.md) — architecture, frozen values, phase gates, evidence rules.
- [`scenario-b/AGENTS.md`](scenario-b/AGENTS.md) — inherited 5G invariants and gotchas.
- [`project2/scenario-a/AGENTS.md`](project2/scenario-a/AGENTS.md) — exact Scenario A contract.
- [`project2/scenario-b/AGENTS.md`](project2/scenario-b/AGENTS.md) — exact Scenario B contract.

Requirements source of truth:
`Project 2_Telecommunication Security, DevSecOps, and Traffic Intelligence.pdf`.
