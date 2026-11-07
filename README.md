# 5G-2-Security

**Project 2 — Telecommunication Security, DevSecOps, and Traffic Intelligence**

This repository is a **fork of Project 1** (`5G-project-RTU`, full history kept).
Only **Project 2 documentation** is maintained here. The inherited 5G Standalone
code, scripts and raw results remain as the working base, but the Project 1
reports, screenshots and PDF were removed from the working tree.

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
| B | 2B–2E | ZAP/Selenium/SQLi, PCAP + Suricata, Trivy/Syft, correlation + gate | ✅ done |

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
└── results/                  # Project 2 evidence; inherited raw results kept
```

## Run the environment

All container work runs natively on the Linux host, from the repository
checkout. The examples assume the repository is at `~/5G-2-Security`; use the
actual checkout path (for example
`~/Documentos/VSCODE/5G-2-Security`) if it differs.

```bash
cd ~/5G-2-Security

# ---------------------------------------------------------------- Scenario A
# First time only: create the git-ignored inputs.
cd scenario-b && cp -n env.example .env && cd ..

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
it also uses `10.20.6.20`. If you re-run `enable-n6.sh`, it recreates
`sb-nginx`; run `scenario-a/up.sh` again afterwards so the two gateways do not
conflict.

### Restart after a host reboot

Containers use `restart: unless-stopped`, so normally they come back by
themselves. Check first; do not redeploy if the gate is already green:

```bash
cd ~/5G-2-Security
docker ps --format 'table {{.Names}}\t{{.Status}}'
./project2/scenario-a/scripts/verify-phase1.sh
```

If that is green, the Scenario A gate is satisfied. Start the Scenario B
containers only if they are not already up, then run the pipeline.

If core, gNB or UE were recreated (for example after `scenario-b/scripts/deploy.sh`),
the N6 attachment and the UE PDU session must be rebuilt in this order:

```bash
cd ~/5G-2-Security

# A restarting scenario-b-nginx owns 10.20.6.20; free it before N6
docker rm -f sb-nginx scenario-b-nginx 2>/dev/null || true

cd scenario-b
sudo ./scripts/enable-n6.sh          # recreates upf with dn-net, no NAT
cd ..

./project2/scenario-a/scripts/upgrade-ran.sh  # UE registers after the new UPF
./project2/scenario-a/scripts/up.sh           # Django + TLS gateway
./project2/scenario-a/scripts/verify-phase1.sh
```

Order matters: `deploy.sh` starts the UPF without the `dn-net` override and
starts the UE before N6 exists. `enable-n6.sh` recreates the UPF, so the UE
must register afterwards (`upgrade-ran.sh`). Running `enable-n6.sh` after the
UE is up leaves a dead PDU session; symptom is `UE cannot reach 10.20.6.20`
or `gateway access log has no request from 10.45.0.x`.

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

### Scenario B — full pipeline (2A through 2E)

```bash
cd ~/5G-2-Security
SECURITY_GATE_MODE=REPORT_ONLY ./project2/scenario-b/scripts/run-pipeline.sh
echo $?                    # must be 0
```

`SECURITY_GATE_MODE` defaults to `REPORT_ONLY`. To demonstrate the gate
policy, run with `ENFORCE`: the build then fails at the last stage when the
Juice Shop image has HIGH/CRITICAL findings.

Expected at the end:

```text
[run] build N result: SUCCESS
[preflight] PASS — 0 failed of 35
[2B] summary: PASS — 0 failed of 23
[2C] phase2c: PASS — 0 failed of 12
[2D] phase2d: PASS — 0 failed of 10
[2E] correlation: PASS — 0 failed of 18
[2E] gate: PASS (REPORT_ONLY) — ...
```

Artifacts are written by the Jenkins build per run and phase:

| Phase | Directory | Key files |
|---|---|---|
| 2A | `results/scenario-b/phase2a/<RUN_ID>/` | `baseline-1e.txt`, `preflight.json/.md`, proof PCAP |
| 2B | `results/scenario-b/phase2b/<RUN_ID>/` | ZAP baseline HTML/MD/JSON, Selenium JSON + screenshot, `plan.yaml`, targeted `zap-sqli.json` |
| 2C | `results/scenario-b/phase2c/<RUN_ID>/` | fresh `juice-shop-ci-sqli.pcapng`, `eve.json`, `fast.log`, `stats.log`, `phase2c.json/.md` |
| 2D | `results/scenario-b/phase2d/<RUN_ID>/` | `trivy-juice-shop.json`, `trivy-config.json`, `sbom.cdx.json`, `phase2d.json/.md` |
| 2E | `results/scenario-b/phase2e/<RUN_ID>/` | `security-event-correlation.json/.md`, `scenario-b-evidence.tar.gz`, `gate.json/.md` |

The latest locally verified runs are
`phase2b/20261107T132531Z` (REPORT_ONLY, build SUCCESS) and
`phase2e/20261107T132809Z` (ENFORCE, expected gate failure). Raw evidence and
PCAPs stay out of Git.

On the host:

```bash
R=$(ls -d ~/5G-2-Security/results/scenario-b/phase2a/*/ | tail -1)
jq -r '.decision, (.checks | length)' "$R/preflight.json"
grep -c '\[FAIL\]' "$R/baseline-1e.txt" || true
```

Jenkins UI: <http://127.0.0.1:8080/job/scenario-b-security/>. Log in as
`securityadmin` with the password from `project2/scenario-b/env`.

The tracked green 2A run in this repository is
[`results/scenario-b/phase2a/20261102T230116Z/`](results/scenario-b/phase2a/20261102T230116Z/).
Later run directories contain raw evidence and PCAPs, so they stay untracked.

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

- The lab now runs natively on Linux (no VirtualBox VM). The full Project 2
  image set needs several GB; the inherited observability stack (`metrics`,
  `grafana`) is still disabled by default. Set `ENABLE_OBSERVABILITY=1` only
  if the images fit.
- After a host reboot, run `host-up.sh --with-b` (or the restart order above),
  then `verify-phase1.sh` before trusting the pipeline.
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

Clone to a **native Linux path**, never to a VirtualBox shared folder: vboxsf
breaks container mounts and permissions.

## For AI agents / new sessions

- [`AGENTS.md`](AGENTS.md) — architecture, frozen values, phase gates, evidence rules.
- [`scenario-b/AGENTS.md`](scenario-b/AGENTS.md) — inherited 5G invariants and gotchas.
- [`project2/scenario-a/AGENTS.md`](project2/scenario-a/AGENTS.md) — exact Scenario A contract.
- [`project2/scenario-b/AGENTS.md`](project2/scenario-b/AGENTS.md) — exact Scenario B contract.

Requirements source of truth:
`Project 2_Telecommunication Security, DevSecOps, and Traffic Intelligence.pdf`.
