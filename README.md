# 5G-2-Security

**Project 2 — Telecommunication Security, DevSecOps, and Traffic Intelligence**

This repository is a **fork of Project 1** (`5G-project-RTU`, full history kept).
Only **Project 2 documentation** is maintained here. The inherited 5G Standalone
code, scripts and raw results remain as the working base, but the Project 1
reports, screenshots and PDF were removed from the working tree.

> **Workflow:** Reuse → Secure → Model → Test → Detect → Automate → Analyze → Defend.

## Scenarios

* **Scenario A — secure application delivery over 5G.** Reuse the 5G SA path and
  add a **Django application** behind an **Nginx TLS reverse proxy**: a public
  Data Network (N6) and a **private application network**, lab PKI, HTTP→HTTPS
  redirection, and a security baseline (login, CSRF, secure cookies, HSTS).
* **Scenario B — DevSecOps security-testing pipeline.** Jenkins + Selenium +
  OWASP ZAP + Suricata + Trivy/Syft against a Juice Shop target, packet capture,
  event correlation, a bounded traffic-intelligence stage and a security gate.

How the pieces connect and why: [docs/architecture.md](docs/architecture.md).
Checks, expected output and evidence: [docs/verification.md](docs/verification.md).
Technical report: [docs/report.md](docs/report.md).
Independent IDS evaluation on ISCXIDS2012: [docs/ids-benchmark.md](docs/ids-benchmark.md).
LLM-assisted cross-validation: [docs/llm-cross-validation.md](docs/llm-cross-validation.md).
Presentation script and Q&A: [docs/presentation-guide.md](docs/presentation-guide.md).

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
| B | 2C-Advanced | Traffic intelligence analytics (features, clusters, anomaly scores) — supplementary | ✅ done |
| B | 2C-Eval | Independent IDS evaluation on ISCXIDS2012 (offline, per-scenario metrics) | ✅ done |
| B | 2E-LLM | Two LLM-assisted cross-validation tasks, verified against the artefacts | ✅ done |

## Structure

```
5G-2-Security/
├── README.md                 # this file: what it is, how to run it, how to restart
├── AGENTS.md                 # design invariants that survive compaction
├── host-up.sh                # day-to-day entry point: start the lab in order
├── host-down.sh              # stop the lab (--all also removes networks/volume)
├── docs/
│   ├── report.md             # technical report: design, results, limits
│   ├── architecture.md       # diagrams, design decisions, phase map
│   ├── verification.md       # per-phase checks, expected output, evidence
│   ├── ids-benchmark.md      # independent IDS evaluation on ISCXIDS2012
│   ├── llm-cross-validation.md  # the two LLM cross-validation tasks
│   ├── presentation-guide.md # 12-minute script, numbers, Q&A
│   ├── brief-p2.txt          # Project 2 brief as text, for agents/tools
│   └── (Project 1 reports removed)
├── scenario-b/               # inherited 5G SA base (code + runbook)
├── project2/
│   ├── scenario-a/           # secure application delivery (1A–1E)
│   └── scenario-b/           # security CI/CD pipeline (2A–2E)
│       └── ids-eval/         # ISCXIDS2012 extractor and evaluator
├── scripts/                  # inherited Project 1 tooling (reference)
└── results/                  # Project 2 evidence; inherited raw results kept
```

## Run — first clone (one time only)

All container work runs natively on the Linux host, from the repository
checkout. The examples assume `~/5G-2-Security`; use your actual path (for
example `~/Documentos/VSCODE/5G-2-Security`).

Requirements: `docker` (user in the `docker` group), `git`, `curl`, `jq`,
`tshark`, `openssl`, and `sudo` for the N6 step.

```bash
cd ~/5G-2-Security

# 1. Git-ignored inputs. The secrets are yours: edit them before starting.
cp -n scenario-b/env.example scenario-b/.env
cp -n project2/scenario-a/env.example project2/scenario-a/env       # DJANGO_SECRET_KEY, LAB_ADMIN_PASSWORD
cp -n project2/scenario-b/env.example project2/scenario-b/env       # JENKINS_ADMIN_PASSWORD

# 2. Base 5G: pinned Open5GS + UERANSIM clone, prebuilt images, upstream/.env.
#    Run it after step 1: it copies scenario-b/.env over upstream/.env.
./scenario-b/scripts/fetch-upstream.sh

# 3. Project 2 images and lab PKI (creates secrets/tls/, once only).
./project2/scenario-a/scripts/build.sh        # telecom-lab-ueransim:3.3.0-p2
./project2/scenario-a/scripts/gen-pki.sh      # Root CA + server cert (SAN 10.20.6.20)

# 4. Scenario B images, built once. `host-up.sh --with-b` starts them with
#    --no-build, so they must exist before the first run.
./project2/scenario-b/scripts/up.sh

# 5. Everything up, in the required order, and the 1E gate at the end.
./host-up.sh --with-b
```

If you change `scenario-b/.env` later, re-run `fetch-upstream.sh`: it is the
step that copies your values into `upstream/.env`.

## Run — normal use (day to day)

```bash
cd ~/5G-2-Security

./host-up.sh              # Scenario A: core, N6, RAN, Django/TLS + verify
./host-up.sh --with-b     # same, plus Scenario B and the Jenkins job
./host-down.sh            # stop everything, keep networks and volumes
./host-down.sh --all      # also remove networks and the Jenkins volume
```

`host-up.sh` is a thin wrapper around the phase scripts, in the order the
architecture requires: `deploy.sh` → `enable-n6.sh` (sudo) →
`upgrade-ran.sh` → `up.sh` → `verify-phase1.sh`, plus, with `--with-b`,
`docker compose up -d --no-build` and `jenkins-bootstrap.sh`.

It does **not** build images, generate the PKI or create the `env` files: that
is first-clone work, and the wrapper stops with the exact command to run if any
of it is missing. `host-down.sh` never touches `results/` or `secrets/tls/`.

| Script | What it does | When |
|---|---|---|
| `host-up.sh [--with-b]` | Start the stack in order, then the 1E gate | Every start |
| `host-down.sh [--all]` | Stop Scenario B, Scenario A and the 5G core; `--all` also removes networks and the Jenkins volume | Every stop |
| `scenario-b/scripts/fetch-upstream.sh` | Pinned Open5GS/UERANSIM clone + prebuilt image tags | First clone |
| `scenario-b/scripts/deploy.sh` | Core, gNB, UE and the subscriber | Every start (called by the wrapper) |
| `scenario-b/scripts/enable-n6.sh` | Recreates the UPF with `dn-net`, no NAT; recreates `sb-nginx` | Every start, with `sudo` |
| `project2/scenario-a/scripts/build.sh` | Builds `telecom-lab-ueransim:3.3.0-p2` | First clone / RAN image change |
| `project2/scenario-a/scripts/gen-pki.sh` | Root CA + server certificate (`--force` to replace) | Once, or after rotating the PKI |
| `project2/scenario-a/scripts/up.sh` | Django + Nginx TLS gateway; removes `sb-nginx` (same IP) | Every start |
| `project2/scenario-b/scripts/up.sh` | Builds and starts Juice Shop, Selenium, Jenkins; creates the job | First clone / Scenario B image change |
| `project2/scenario-b/scripts/run-pipeline.sh` | Triggers the Jenkins pipeline and follows the build | Every test run |

## Restart after a host reboot

Containers use `restart: unless-stopped`, so normally they come back by
themselves. Check first; do not redeploy if the gate is already green:

```bash
cd ~/5G-2-Security
docker ps --format 'table {{.Names}}\t{{.Status}}'
./project2/scenario-a/scripts/verify-phase1.sh
```

If the core containers show `Exited`, or the gate fails, rebuild in this order
(this is exactly what `./host-up.sh` does, including freeing `10.20.6.20`):

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

Order matters: `enable-n6.sh` recreates the UPF, so the UE must register
afterwards. Doing it the other way leaves a dead PDU session; the symptoms are
`UE cannot reach 10.20.6.20` or `gateway access log has no request from
10.45.0.x`.

Scenario B is independent of that order: start it only if it is not already up
(`docker compose -f project2/scenario-b/docker-compose.security.yaml up -d
--no-build`), then run the pipeline.

## Environment notes

- The lab runs natively on Linux (no VirtualBox VM). The full Project 2 image
  set needs several GB; the inherited observability stack (`metrics`, `grafana`)
  is disabled by default. Set `ENABLE_OBSERVABILITY=1` only if the images fit.
- After a host reboot, run `host-up.sh --with-b` (or the order above), then
  `verify-phase1.sh` before trusting the pipeline.
- Jenkins needs the host `docker` group GID to use `/var/run/docker.sock`. The
  compose file reads `DOCKER_GID` and defaults to `956`:
  `DOCKER_GID=$(getent group docker | cut -d: -f3) docker compose ...` when the
  host uses a different GID.
- `env`, `secrets/tls/`, `*.pcap` and `*.pcapng` are git-ignored and must never
  be committed. The CA private key is mounted into no container.
- The brief is readable by tools at [`docs/brief-p2.txt`](docs/brief-p2.txt).


## For AI agents / new sessions

- [`AGENTS.md`](AGENTS.md) — architecture, frozen values, phase gates, evidence rules.
- [`docs/report.md`](docs/report.md) — technical report: design, results, limitations.
- [`docs/architecture.md`](docs/architecture.md) — diagrams, design decisions, phase map.
- [`docs/verification.md`](docs/verification.md) — per-phase checks and evidence.
- [`scenario-b/AGENTS.md`](scenario-b/AGENTS.md) — inherited 5G invariants and gotchas.
- [`project2/scenario-a/AGENTS.md`](project2/scenario-a/AGENTS.md) — exact Scenario A contract.
- [`project2/scenario-b/AGENTS.md`](project2/scenario-b/AGENTS.md) — exact Scenario B contract.

Requirements source of truth:
`Project 2_Telecommunication Security, DevSecOps, and Traffic Intelligence.pdf`.
