# Project 2 — Scenario B: DevSecOps security pipeline

Scenario B adds a reproducible security-validation layer around the verified
Scenario A system. It is **not** another 5G network: Jenkins orchestrates
security tools as ephemeral Docker jobs against a controlled, deliberately
vulnerable target (OWASP Juice Shop), while the secure Django/Nginx path stays
isolated and untouched.

```text
source/GitHub → Jenkins → Preflight → ZAP baseline → Selenium runtime
  → start fresh PCAP → controlled SQLi → targeted ZAP → stop PCAP
  → Suricata offline → traffic intelligence (optional) → Trivy → Syft
  → correlation → archive → Security Gate → final result
```

## Status

| Phase | Deliverable | Status |
|---|---|---|
| 2A | Preflight + environment acceptance (Jenkins, Juice Shop, Selenium, capture, Suricata, ZAP, Trivy/Syft, tools) | ✅ done |
| 2B | ZAP baseline, Selenium runtime, capture window, controlled SQLi, targeted ZAP | 🟡 stages implemented; green run pending |
| 2C | Fresh PCAP validation, Suricata offline detection, traffic intelligence | ⬜ pending |
| 2D | Trivy scan + Syft CycloneDX SBOM | ⬜ pending |
| 2E | Evidence correlation, archive, Security Gate (REPORT_ONLY / ENFORCE) | ⬜ pending |

## Layout

```
project2/scenario-b/
├── AGENTS.md                   # exact contract, rules, evidence layout
├── Jenkinsfile                 # pipeline (2A stages implemented so far)
├── RELEASE-MANIFEST.json       # pinned images, tools and plugin versions
├── docker-compose.security.yaml# security-net + juice-shop + selenium + jenkins
├── jenkins/                    # image, plugins.txt, init script, job.xml
├── selenium/Dockerfile         # telecom-lab-selenium:1.0
├── capture/                    # telecom-lab-capture:1.0 (tcpdump job)
├── security/
│   ├── zap/plan.yaml           # targeted SQLi plan (Alert 40018)
│   └── ids/                    # Suricata config + rule SID 1000001
└── scripts/
    ├── up.sh                   # build and start the environment
    ├── jenkins-bootstrap.sh    # create the pipeline job
    ├── run-pipeline.sh         # trigger and follow a build
    ├── preflight.py            # phase 2A checks -> preflight.json/.md
    └── phase2b.py              # ZAP baseline, Selenium, capture + SQLi + targeted ZAP
```

## Run (phase 2A)

Prerequisite: Scenario A is up and its 1E gate is green (see the
[root README](../../README.md#run-the-environment)).

```bash
cd project2/scenario-b
cp -n env.example env          # set JENKINS_ADMIN_PASSWORD
./scripts/up.sh                # build images, start services, create the job
./scripts/run-pipeline.sh      # trigger and follow the Jenkins build
```

Jenkins mounts the host repository read-only at `/lab` (for the git-ignored
`env`/`secrets`), the host `results/` at `/evidence`, and the Docker socket.
The pipeline job is checked out from GitHub, so push before triggering.

## Evidence

Phase 2A:
[`results/scenario-b/phase2a/`](../../results/scenario-b/phase2a/README.md)
— 35 checks, decision PASS.

## Phase 2B stages

The Jenkins pipeline now runs, after Preflight:

1. **ZAP baseline** `2B - ZAP baseline`: HTML, Markdown and JSON reports.
   Baseline findings are observations; only a tool error fails the stage.
2. **Selenium runtime** `2B - Selenium runtime and authentication`: Chrome
   login, JWT/session assertions, cookies, `localStorage` and an authenticated
   screenshot.
3. **Controlled SQLi** `2B - capture, controlled SQLi and targeted ZAP`:
   start capture, GET `/rest/products/search?q=%27%28`, targeted ZAP Alert
   40018, stop capture. The fresh PCAP is written to the phase 2C directory
   for the network stage. Alert 40018 missing fails the stage.

Evidence: `results/scenario-b/phase2b/<RUN_ID>/` and the fresh PCAP under
`results/scenario-b/phase2c/<RUN_ID>/`.

## Known limitations

- The VM disk (32 GB) cannot hold every Scenario B image plus the Project 1
  observability stack; Grafana/Prometheus containers were stopped to free
  space (they are still defined in the base compose files).
- ZAP is referenced as `stable` in the manifest; the archived run used 2.17.0.
- No Security Gate yet: REPORT_ONLY/ENFORCE semantics arrive in 2E.
