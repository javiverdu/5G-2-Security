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
| 2C | Fresh PCAP validation, Suricata offline detection, traffic intelligence | 🟡 stages implemented; green run pending |
| 2D | Trivy scan + Syft CycloneDX SBOM | 🟡 stages implemented; green run pending |
| 2E | Evidence correlation, archive, Security Gate (REPORT_ONLY / ENFORCE) | 🟡 stages implemented; green run pending |

## Layout

```
project2/scenario-b/
├── AGENTS.md                   # exact contract, rules, evidence layout
├── Jenkinsfile                 # pipeline 1E → 2A → 2B → 2C → 2D → 2E
├── RELEASE-MANIFEST.json       # pinned images, tools and plugin versions
├── docker-compose.security.yaml# security-net + juice-shop + selenium + jenkins
├── jenkins/                    # image, plugins.txt, init script, job.xml
├── selenium/Dockerfile         # telecom-lab-selenium:1.0
├── capture/                    # telecom-lab-capture:1.0 (tcpdump job)
├── correlation/                # telecom-lab-correlation:1.0 (2E)
├── security/
│   ├── zap/plan.yaml           # targeted SQLi plan (Alert 40018)
│   └── ids/                    # Suricata config + rule SID 1000001
└── scripts/
    ├── up.sh                   # build and start the environment
    ├── jenkins-bootstrap.sh    # create the pipeline job
    ├── run-pipeline.sh         # trigger and follow a build
    ├── preflight.py            # phase 2A checks -> preflight.json/.md
    ├── phase2b.py              # ZAP baseline, Selenium, capture + SQLi + targeted ZAP
    ├── phase2c.py              # fresh PCAP, offline Suricata, traffic intelligence
    ├── phase2d.py              # Trivy scan + Syft CycloneDX SBOM
    └── phase2e.py              # correlation, evidence archive, Security Gate
```

## Run (phase 2A)

Prerequisite: Scenario A is up and its 1E gate is green (see the
[root README](../../README.md#run-the-environment)). After a VM reboot, run
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

## Phase 2D stages

1. **`2D - Trivy scan and Syft CycloneDX SBOM`** scans two explicit targets:
   - `aquasec/trivy:0.75.0 image` against
     `bkimminich/juice-shop:v20.2.0` (vulnerabilities), report
     `trivy-juice-shop.json`;
   - `aquasec/trivy:0.75.0 fs --scanners misconfig` against
     `project2/scenario-b` (IaC), report `trivy-config.json`;
   - `anchore/syft:v1.52.0` produces `sbom.cdx.json` (CycloneDX) for the same
     Juice Shop image.
   Trivy findings are observations. The stage fails only when a tool does not
   run or its report cannot be parsed.

Evidence: `results/scenario-b/phase2d/<RUN_ID>/` — `phase2d.json/.md`,
`trivy-juice-shop.json`, `trivy-config.json`, `sbom.cdx.json`, logs.

## Phase 2E stages

1. **`2E - Security evidence correlation`**: `telecom-lab-correlation:1.0`
   reads phases 2A–2D read-only and writes
   `security-event-correlation.json/.md`. It links the controlled SQLi
   request, ZAP Alert 40018, the PCAP hash, Suricata SID 1000001, the Trivy
   counts and the SBOM by RUN_ID, target, request signature and artifact
   hashes. It never re-scans or invents data.
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
- Traffic intelligence is limited to the bounded TShark feature summary in
  `phase2c.json`; no ML model is claimed.
