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
| 2B | ZAP baseline, Selenium runtime, capture window, controlled SQLi, targeted ZAP | ✅ done |
| 2C | Fresh PCAP validation, Suricata offline detection | ✅ done |
| 2C-Advanced | Traffic intelligence analytics (features, clusters, anomaly scores) — supplementary | ✅ done |
| 2D | Trivy scan + Syft CycloneDX SBOM | ✅ done |
| 2E | Evidence correlation, archive, Security Gate (REPORT_ONLY / ENFORCE) | ✅ done |

Verified on the native host:

- REPORT_ONLY, build 17: RUN_ID `20261123T114855Z`, Jenkins `SUCCESS` with
  2C-Advanced and correlation image 1.2 — correlation 22/22 inside the
  container, archive 56 members, gate `PASS` with HIGH/CRITICAL=70 recorded and
  SID 1000001 at 44 events.
- ENFORCE, build 16: RUN_ID `20261123T114506Z`, Jenkins `FAILURE` at the gate
  only (`ENFORCE: HIGH/CRITICAL=70 exceeds threshold 0`); every upstream phase
  `PASS`, correlation 22/22.
- REPORT_ONLY, build 14: RUN_ID `20261123T111153Z`, first run with 2C-Advanced;
  superseded by build 17 (it predates `alerts_by_signature`).
- REPORT_ONLY, build 11: RUN_ID `20261108T144011Z`, Jenkins `SUCCESS`,
  correlation 19/19, gate `PASS` with HIGH/CRITICAL=70 recorded.
- ENFORCE, build 13: RUN_ID `20261108T144511Z`, Jenkins `FAILURE` at the gate
  as expected (`HIGH/CRITICAL=70 exceeds threshold 0`); every upstream phase
  still `PASS` and the correlation is 19/19.

## Layout

```
project2/scenario-b/
├── AGENTS.md                   # exact contract, rules, evidence layout
├── Jenkinsfile                 # pipeline 1E → 2A → 2B → 2C → 2C-Advanced → 2D → 2E
├── RELEASE-MANIFEST.json       # pinned images, tools and plugin versions
├── docker-compose.security.yaml# security-net + juice-shop + selenium + jenkins
├── jenkins/                    # image, plugins.txt, init script, job.xml
├── selenium/Dockerfile         # telecom-lab-selenium:1.0
├── capture/                    # telecom-lab-capture:1.0 (tcpdump job)
├── correlation/                # telecom-lab-correlation:1.2 (2E)
├── security/
│   ├── zap/plan.yaml           # targeted SQLi plan (Alert 40018)
│   └── ids/                    # Suricata config + rule SID 1000001
└── scripts/
    ├── up.sh                   # build and start the environment
    ├── jenkins-bootstrap.sh    # create the pipeline job
    ├── run-pipeline.sh         # trigger and follow a build
    ├── preflight.py            # phase 2A checks -> preflight.json/.md
    ├── phase2b.py              # ZAP baseline, Selenium, capture + SQLi + targeted ZAP
    ├── phase2c.py              # fresh PCAP, offline Suricata, capture summary
    ├── analytics.py            # phase 2C-Advanced: features, clusters, anomalies
    ├── phase2d.py              # Trivy scan + Syft CycloneDX SBOM
    └── phase2e.py              # correlation, evidence archive, Security Gate
```

## Run (phase 2A)

Prerequisite: Scenario A is up and its 1E gate is green (see the
[root README](../../README.md) and [docs/verification.md](../../docs/verification.md)).
After a host reboot, run
`verify-phase1.sh` first. If it reports `UE cannot reach 10.20.6.20`, replay
the restart order from the root README: `enable-n6.sh`, then `upgrade-ran.sh`,
then `scenario-a/up.sh`.

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
   screenshot. It uses the Juice Shop seeded administrator account
   (`admin@juice-sh.op`) on the deliberately vulnerable target; the cookie
   banner can cover the Angular login button, so an intercepted native click
   falls back to a synthetic element click.
3. **Controlled SQLi** `2B - capture, controlled SQLi and targeted ZAP`:
   start capture, GET `/rest/products/search?q=%27%28`, targeted ZAP Alert
   40018, stop capture. The fresh PCAP is written to the phase 2C directory
   for the network stage. Alert 40018 missing fails the stage.

Evidence: `results/scenario-b/phase2b/<RUN_ID>/` and the fresh PCAP under
`results/scenario-b/phase2c/<RUN_ID>/`.

## Phase 2C stages

1. **`2C - fresh PCAP, Suricata offline and traffic intelligence`** consumes
   the PCAP that 2B wrote into the same run directory. It never captures and
   never sits inline:
   - `tshark` proves the file parses and contains
     `/rest/products/search?q=%27%28`;
   - the SHA-256 must match the 2B `capture.json`;
   - Suricata `jasonish/suricata:8.0` runs offline with
     `security/ids/suricata.yaml` and the local rules;
   - SID `1000001` must appear in `eve.json`/`fast.log`. The rule reads
     `http.uri.raw` because Suricata normalizes `http.uri` (the encoded
     `%27%28` payload would otherwise be decoded before matching).
   - `traffic` in `phase2c.json` records packet and HTTP request counts as
     context, never as the gate.

Evidence: `results/scenario-b/phase2c/<RUN_ID>/` — `phase2c.json/.md`,
`eve.json`, `fast.log`, `stats.log`, `suricata-command.log`.

2. **`2C-Advanced - traffic intelligence analytics`** runs
   `scripts/analytics.py` on the same PCAP. Pure Python standard library plus
   `tshark`, k-means `k=3` with a fixed seed and a modified z-score against a
   learned baseline; the baseline is the cluster that matches plain content
   retrieval (no query string, no body). It writes `traffic-features.csv`
   (per request), `traffic-flows.csv` (per TCP stream), `traffic-anomaly.json`,
   `traffic-classification.json`, `analytics.json/.md`.

   Analytics is **supplementary by contract**: both JSON artifacts carry
   `supplementary: true` and `gate_impact: "none"`, and 2E only records the
   outcome in its chain. The stage exits non-zero only on a tool failure, so a
   detector that flags nothing is an observation, never a build failure. The
   rates in the report describe one controlled capture and are not detection
   accuracy.

## Phase 2D stages

1. **`2D - Trivy scan and Syft CycloneDX SBOM`** scans four explicit targets:
   - `aquasec/trivy:0.75.0 image` against
     `bkimminich/juice-shop:v20.2.0` (vulnerabilities), report
     `trivy-juice-shop.json`; **this is the only count the gate reads**;
   - `aquasec/trivy:0.75.0 fs --scanners misconfig` against
     `project2/scenario-b` (IaC), report `trivy-config.json`;
   - `aquasec/trivy:0.75.0 image --image-src docker` against this project's own
     images, `telecom-lab-django:0.1` and `telecom-lab-nginx:p2`, reports
     `trivy-telecom-lab-django.json` and `trivy-telecom-lab-nginx.json`
     (observations, `gate_impact: none`);
   - `anchore/syft:v1.52.0` produces `sbom.cdx.json` (CycloneDX) for the Juice
     Shop image.
   Trivy findings are observations. The stage fails only when a tool does not
   run or its report cannot be parsed. DAST against Django is out of scope: ZAP
   targets Juice Shop by design.

Evidence: `results/scenario-b/phase2d/<RUN_ID>/` — `phase2d.json/.md`,
`trivy-juice-shop.json`, `trivy-config.json`, `sbom.cdx.json`, logs.

## Phase 2E stages

1. **`2E - Security evidence correlation`**: `telecom-lab-correlation:1.2`
   reads phases 2A–2D read-only and writes
   `security-event-correlation.json/.md`. It links the controlled SQLi
   request, ZAP Alert 40018, the PCAP hash, Suricata SID 1000001, the Trivy
   counts, the SBOM, the traffic-intelligence summary and the Jenkins build tag
   by RUN_ID, target, request signature and artifact hashes. It never re-scans
   or invents data.
2. **`2E - Evidence archive`**: packs `phase2a..phase2e/<RUN_ID>` into
   `scenario-b-evidence.tar.gz` and records its SHA-256.
3. **`2E - Security Gate`**: a Jenkins policy decision, separate from tool
   results and findings. `SECURITY_GATE_MODE` is a build parameter:
   - `REPORT_ONLY` (default): HIGH/CRITICAL findings are archived, build
     continues;
   - `ENFORCE`: build fails when HIGH+CRITICAL exceeds
     `GATE_MAX_HIGH_CRITICAL` (0).
   A broken evidence chain or a failed positive control fails the gate in both
   modes. `gate.json/.md` records tool result, security finding and decision
   separately.

Run ENFORCE explicitly:

```bash
SECURITY_GATE_MODE=ENFORCE ./scripts/run-pipeline.sh
```

Evidence: `results/scenario-b/phase2e/<RUN_ID>/` — correlation JSON/Markdown,
evidence archive and `gate.json/.md`.

## Known limitations

- The environment now runs on a native Linux host; the earlier 32 GB VM is no
  longer the deployment target.
- ZAP is referenced as `stable` in the manifest; the archived run used 2.17.0.
- The evidence archive is created before the Security Gate, matching the
  required order, so `gate.json/.md` are delivered next to it rather than
  inside the tar.
- Traffic intelligence is a bounded demonstration: features come from one
  controlled capture, the baseline is learned from that same capture and the
  reported rates are descriptive, not detection accuracy. It is supplementary
  evidence and never changes the Security Gate.
- The base images are **tag-pinned, not digest-pinned** (`nginx:latest`,
  `python:3.12-slim`). Reproducibility debt tracked in
  `docs/architecture.md`; scheduled after every phase is verified, because
  changing a base image invalidates the current 1C/2D evidence.
