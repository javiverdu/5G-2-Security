# Phase 2A — Preflight and environment acceptance

Jenkins-orchestrated preflight for Scenario B. Run `20261102T230116Z`,
Jenkins build `jenkins-scenario-b-security-3`, decision **PASS** (35 checks,
0 failed).

- Date: 2026-11-02 (UTC)
- Environment: `security-net` `10.20.10.0/24`
  - Juice Shop `10.20.10.20:3000` (`bkimminich/juice-shop:v20.2.0`)
  - Selenium `10.20.10.30:4444` (`telecom-lab-selenium:1.0`, Selenium 155.0)
  - Jenkins `10.20.10.40:8080` (`telecom-lab-jenkins:2.580.1-jdk21`)

## Files

| File | Content |
|---|---|
| `20261102T230116Z/baseline-1e.txt` | Scenario A `verify-phase1.sh` output, run as stage 1E before Preflight |
| `20261102T230116Z/preflight.json` | machine-readable checks, versions and decision |
| `20261102T230116Z/preflight.md` | human-readable equivalent |
| `20261102T230116Z/preflight-capture.pcapng` | 2 KB proof capture (git-ignored; reproducible) |

## What Preflight proved

- Jenkins build id present, evidence directory run-specific and writable.
- All 62 installed plugins present; the required plugin versions match
  `RELEASE-MANIFEST.json` (git, docker-workflow, credentials-binding,
  timestamper, htmlpublisher, workflow-aggregator + dependencies).
- Docker 29.9.2 reachable through `/var/run/docker.sock`.
- `security-net` exists and `dn-net` is still present; container DNS resolves
  `juice-shop` on `security-net`.
- Juice Shop answers `200` and reports version `20.2.0` (controlled target).
- Selenium reports `ready=true` and a Chrome session was created and deleted.
- ZAP 2.17.0 starts; `security/zap/plan.yaml` parses with `spider`,
  `requestor`, `activeScan` and `report` jobs.
- Capture image wrote a non-empty PCAP while sharing Juice Shop's netns;
  `tshark` read an HTTP request from it.
- Suricata 8.0 accepts the configuration (`suricata -T`) and loads 1 rule;
  SID 1000001 is present in the local rule set.
- `jq`, `tshark` 4.4.19, `python3` available; required scripts executable.
- Trivy 0.75.0 and Syft v1.52.0 available; Trivy vulnerability database
  downloaded.
- Versions and image IDs recorded in `preflight.json`.

## Run commands

```bash
cd project2/scenario-b
cp env.example env          # then set the Jenkins admin password
./scripts/up.sh             # build images, start services, create the job
./scripts/run-pipeline.sh   # trigger and follow the Jenkins build
```

## Environment constraints (recorded, not hidden)

- The host VM has a 32 GB disk. The full Scenario B image set (ZAP 3.75 GB,
  Selenium 3.28 GB, Open5GS 2.21 GB, Jenkins, Trivy + DB) does not fit together
  with the Project 1 observability stack. The `grafana` and `metrics`
  containers/images were stopped and removed to make room; the Project 1
  compose files still define them, so a later `deploy.sh` would pull them
  again. This does not affect any Scenario A or B acceptance check.
- Two earlier pipeline attempts (builds 1 and 2) failed on environment bugs:
  a missing capture image, a `detail` type error in Preflight, a missing ZAP
  version line, a read-only Suricata config mount, and a transient Docker DNS
  failure while pulling Trivy. The fixes are in `d85d4eb..` history; only the
  green run is archived here.
