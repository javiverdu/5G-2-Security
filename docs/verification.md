# Verification and evidence

How each phase is proved, what the output should look like, and where the
evidence lands. Architecture and phase rationale: [architecture.md](architecture.md).
Start commands: [README](../README.md).

## How to read a result

Three things are always reported separately, and none stands for another:

| Layer | Question | Example |
|---|---|---|
| Tool result | Did the tool run? | `phase2c.json` decision `PASS`, exit code 0 |
| Security finding | What did it observe? | ZAP Alert 40018, Suricata SID 1000001, 70 HIGH/CRITICAL in Trivy |
| Gate decision | What does policy say? | `gate.json` `PASS` in `REPORT_ONLY`, `FAIL` in `ENFORCE` |

A green pipeline means the mechanism worked and the policy allowed the build.
It never means the target is secure: Juice Shop is vulnerable **on purpose**.

Evidence traps worth remembering (they are also in `AGENTS.md`):

- `docker ps` is not packet evidence: use captures or real requests.
- Ping is not full validation: registration, TLS, TCP/UDP and the GTP-U path
  matter.
- The container IP is management; the UE address is `10.45.0.x` on `uesimtun0`.
- N4/PFCP is control plane, not application traffic.
- Reaching N6 is not the 5G user plane: traffic must originate **inside the UE**
  and the server must log `10.45.0.x`.
- `curl -k` is for troubleshooting only. Final validation uses `--cacert`.
- Evidence must belong to the **current** `RUN_ID`; an old PCAP must never
  satisfy a check.

## Scenario A — per-phase verifiers

Each script exits non-zero on the first failed check and prints `[ OK ]` /
`[FAIL]` lines with the observed value.

| Script | Phase | What it checks |
|---|---|---|
| `project2/scenario-a/scripts/verify-phase1a.sh` | 1A | p2 image and UERANSIM version, gNB/UE running it, PDU session (`uesimtun0` = `10.45.x`), traffic resolves via `uesimtun0`, the route **survives a container restart**, N6 reachability (optional) |
| `verify-phase1b.sh` | 1B | Django image builds and `manage.py check`, container healthy, attached to `app-net` **only** at `10.20.8.20`, `app-net` internal, `django-data` survives recreation, `/health/` exact body, Nginx proxy on `app-net` reaches Django |
| `verify-phase1c.sh` | 1C | Gateway image/container, `dn-net 10.20.6.20` + `app-net 10.20.8.10`, `sb-nginx` gone, certificate issuer/SAN/validity, CA key in no container, HTTP 301 → HTTPS 200, TLS 1.2 and 1.3, real UE address in the access log |
| `verify-phase1d.sh` | 1D | Public endpoints 200, anonymous `/profile/` → 302, login POST with CSRF → 302, session cookie `Secure`/`HttpOnly`/`Lax`, authenticated `/profile/` → 200, CSRF cookie `Secure`, `/feedback/` POST 200 with token and 403 without |
| `verify-phase1.sh` | 1E | The whole path from the UE network namespace: data path, certificate chain, TLS 1.2/1.3, 301→200, public endpoints, login, CSRF, cookies, headers and the real `10.45.0.x` in the gateway log |

### End-to-end gate (1E)

```bash
cd ~/5G-2-Security
./project2/scenario-a/scripts/verify-phase1.sh
echo $?                    # must be 0
```

Expected: every line `[ OK ]`, and the last line
`[ OK ] Phase 1E complete: the 5G user-plane path serves the secured application.`
with exit code 0. The string `N check(s) failed` only appears when something
fails: on success the script prints the completion line instead. The same
pattern holds for `verify-phase1a.sh` … `verify-phase1d.sh`.

Quick intermediate checks while debugging:

```bash
docker exec nr_ue ip -4 addr show uesimtun0       # 10.45.0.x/16
docker exec nr_ue ip route get 10.20.6.20         # dev uesimtun0
docker ps --format '{{.Names}} {{.Status}}'       # nr_gnb, nr_ue, scenario-b-nginx, scenario-b-django
```

If `verify-phase1.sh` fails with `UE cannot reach 10.20.6.20` or
`gateway access log has no request from 10.45.0.x`, the PDU session is dead:
re-run the start order (`enable-n6.sh` recreates the UPF, so the UE must
register afterwards).

## Scenario B — full pipeline (2A through 2E)

```bash
cd ~/5G-2-Security
SECURITY_GATE_MODE=REPORT_ONLY ./project2/scenario-b/scripts/run-pipeline.sh
echo $?                    # must be 0
```

`SECURITY_GATE_MODE` defaults to `REPORT_ONLY`. To demonstrate the policy, run
with `ENFORCE`: the build then fails at the last stage because the Juice Shop
image has HIGH/CRITICAL findings. That failure is the expected result.

Preflight only makes sense **inside the Jenkins container**: it reads
`/var/jenkins_home/plugins`. Run outside it, the two plugin checks now fail with
`/var/jenkins_home/plugins not found — Preflight must run inside the Jenkins
container` instead of reporting every plugin as missing, and the version
comparison refuses to pass on an empty plugin set.

Expected console output (build 20, run `20261123T163741Z`):

```text
[run] build 20 result: SUCCESS
[preflight] PASS — 0 failed of 35
[2B] summary: PASS — 0 failed of 23
[2C] phase2c: PASS — 0 failed of 12
[2C-Advanced] analytics: PASS — 0 failed of 10; controlled request FLAGGED
[2D] phase2d: PASS — 0 failed of 14
[2E] correlate: PASS — 0 failed of 6
[2E] archive: PASS — 0 failed of 7
[2E] gate: PASS (REPORT_ONLY) — REPORT_ONLY: HIGH/CRITICAL=70 recorded; threshold 0 not enforced
```

Three counts need reading with their level in mind:

- **2E correlate: 6 or 7.** The wrapper checks the image exists, holds the
  current `correlate.py`, runs, and validates its output. "correlation image
  built" only runs when the image is missing or stale, so 6 on a normal build
  and 7 when it had to rebuild. The correlation itself runs inside
  `telecom-lab-correlation:1.0` and reports its own `0 failed of 22` — that
  appears as the detail of "container completed" and in
  `security-event-correlation.json`, never as a separate stage summary.
- **2D went from 10 to 14** when the two images built by this project were
  added as explicit scan targets (`own_images`, `gate_impact: "none"`).
- **SID 1000001: 44 events, 20 stored.** `phase2c.json` keeps a 20-alert
  sample plus `alerts_by_signature` counts; the gate and the correlation read
  the counts and print both when they differ.

The correlation image keeps the tag the brief fixes (`telecom-lab-correlation:1.0`).
Which code it contains is not assumed: 2E hashes `/app/correlate.py` inside the
image, compares it with the repository file, rebuilds if they differ, and fails
the stage if the hash still does not match. `correlate.json` records both the
`source_sha256` and the `image_id`.

### Artifacts per phase

| Phase | Directory | Key files |
|---|---|---|
| 2A | `results/scenario-b/phase2a/<RUN_ID>/` | `baseline-1e.txt`, `preflight.json/.md`, proof PCAP |
| 2B | `results/scenario-b/phase2b/<RUN_ID>/` | ZAP baseline HTML/MD/JSON, Selenium JSON + screenshot, `plan.yaml`, targeted `zap-sqli.json` |
| 2C | `results/scenario-b/phase2c/<RUN_ID>/` | fresh `juice-shop-ci-sqli.pcapng`, `eve.json`, `fast.log`, `stats.log`, `phase2c.json/.md` |
| 2C-Advanced | `results/scenario-b/phase2c/<RUN_ID>/` | `traffic-features.csv`, `traffic-flows.csv`, `traffic-anomaly.json`, `traffic-classification.json`, `analytics.json/.md` |
| 2D | `results/scenario-b/phase2d/<RUN_ID>/` | `trivy-juice-shop.json`, `trivy-config.json`, `trivy-telecom-lab-django.json`, `trivy-telecom-lab-nginx.json`, `sbom.cdx.json`, `phase2d.json/.md` |
| 2E | `results/scenario-b/phase2e/<RUN_ID>/` | `security-event-correlation.json/.md`, `scenario-b-evidence.tar.gz`, `gate.json/.md` |

### What each stage actually checks

Counts are those printed by build 20; every check name, status and observed
value is stored in the phase JSON, so nothing in this table is asserted without
a machine-readable counterpart.

| Stage | Checks | Named examples | File |
|---|---|---|---|
| 1E acceptance | 38 (+ completion line) | PDU session, route via `uesimtun0`, TLS 1.2/1.3 with `--cacert`, 301→200, login, CSRF 200/403, `Secure`/`HttpOnly` cookies, real `10.45.0.x` in the gateway log | `baseline-1e.txt` |
| 2A preflight | 35 | fresh evidence dir, 62 pinned plugins match the manifest, `security-net`/`dn-net`, target is the controlled Juice Shop, Selenium Grid ready, ZAP/Suricata/Trivy/Syft versions, SID 1000001 loaded (`suricata -T`), required scripts present (including `analytics.py`) | `preflight.json` |
| 2B ZAP baseline | 5 | target reachable, scan completed, report parses, alert records written; each alert keeps `instances[]` with `uri`, `param`, `attack`, `evidence` (empty `attack` here: baseline is passive) | `zap-baseline-report.json` |
| 2B Selenium | 9 | login accepted, JWT present (717 chars) and identifies the lab account, 3 cookies, token in browser storage, authenticated route 200, screenshot | `selenium.json` |
| 2B capture + SQLi | 9 | capture running before the request, request in window, PCAP hash matches, alert 40018 detected by targeted scan | `capture.json` |
| 2C Suricata | 12 | PCAP belongs to this run (hash + creation time), tshark parses it, controlled payload present, offline run exit 0, `eve.json`/`fast.log`/`stats.log`, SID 1000001 alert (44 events, 20 stored) | `phase2c.json` |
| 2C-Advanced analytics | 10 | ≥3 features with variance, 3 non-empty clusters, baseline learned, 4 artifacts written, marked `supplementary` | `analytics.json` |
| 2D Trivy + SBOM | 14 | image scan exit 0 and parses, severity counts, filesystem misconfig scan, both own images scanned, SBOM is CycloneDX with components | `phase2d.json` |
| 2E correlate (wrapper) | 6–7 | image available, image holds the current `correlate.py` (sha256), built only if missing or stale, container exit 0, JSON readable, decision PASS, JSON carries this `RUN_ID` | `correlate.json` |
| 2E correlation (inside) | 22 | every component reports the same `RUN_ID` and build tag, 2B and 2C share one PCAP hash, both positive controls fire, timestamps form one 133 s window | `security-event-correlation.json` |
| 2E archive | 7 | five phase directories archived, tarball non-empty (1,674,670 bytes), readable and matching its 56 members | `archive.json` |
| 2E gate | 5 | mode valid, correlation complete, ZAP 40018 fired, SID 1000001 fired, Trivy reported; then policy decides | `gate.json` |

A green stage means those checks passed. It does not mean the check list is
exhaustive: what each stage does **not** prove is in
[report.md §8](report.md#8-what-each-phase-proves--and-what-it-does-not).

### What 2D scans (four explicit targets)

| Target | Command | Feeds the gate? |
|---|---|---|
| `bkimminich/juice-shop:v20.2.0` | `trivy image` | **Yes** — `vulnerabilities.high_or_critical` in `phase2d.json` is this count |
| `project2/scenario-b` | `trivy fs --scanners misconfig` | No, observation |
| `telecom-lab-django:0.1` | `trivy image --image-src docker` | No, observation |
| `telecom-lab-nginx:p2` | `trivy image --image-src docker` | No, observation |

The last two are this project's own artefacts: scanning only the deliberately
vulnerable target would leave the images we build unexamined. Their reports sit
next to the others and are listed in `phase2d.json` under `own_images`, with
`gate_impact: "none"`.

DAST against the Django application is **out of scope**: ZAP targets Juice Shop
by design, and scanning the secure app through the 5G path would change the
scenario. It is declared as a limitation, not silently skipped.

### Reading the evidence on the host

```bash
R=$(ls -d ~/5G-2-Security/results/scenario-b/phase2a/*/ | tail -1)
jq -r '.decision, (.checks | length)' "$R/preflight.json"
grep -c '\[FAIL\]' "$R/baseline-1e.txt" || true

# the two positive controls, side by side
jq '.decisions, .chain.application_observation, .chain.network_evidence' \
  "$(ls -d ~/5G-2-Security/results/scenario-b/phase2e/*/ | tail -1)/security-event-correlation.json"
```

Jenkins UI: <http://127.0.0.1:8080/job/scenario-b-security/>. Log in as
`securityadmin` with the password from `project2/scenario-b/env`.

## Latest verified runs

- `20261123T163741Z` — `REPORT_ONLY`, build 20, Jenkins `SUCCESS`. Current
  reference: 2A–2E with 2C-Advanced, correlation 22/22 inside the container,
  6 wrapper checks, archive 56 members / 1,674,670 bytes, gate `PASS` with
  `HIGH/CRITICAL=70` recorded and SID 1000001 at 44 events. Correlation image
  `telecom-lab-correlation:1.0`, `correlate.py` sha256 `b44a1205…`. The tables
  above and [report.md §10](report.md#10-results-what-was-measured) quote it.
- `20261123T164016Z` — `ENFORCE`, build 21, Jenkins `FAILURE` **at the gate**
  as expected (`ENFORCE: HIGH/CRITICAL=70 exceeds threshold 0`), same upstream
  evidence and same 22/22 correlation: the policy, not the evidence, changed.
- `20261123T114855Z` / `20261123T114506Z` — builds 17 and 16, older reference
  and `ENFORCE` runs made before the correlation tag returned to the brief's
  `1.0` and before the image-content check existed.
- `20261123T111153Z` — build 14, first run with 2C-Advanced; superseded twice
  (it predates `alerts_by_signature`).
- `20261123T113911Z` — build 15, `FAILURE` in 2B: the Selenium click was
  swallowed by an overlay and the stage printed "login form submitted" anyway.
  Fix in `phase2b.py`: verify the typed values, wait for the token and fall
  back to `requestSubmit()`. Kept here because a flaky stage that fails loudly
  is better documented than hidden.
- `phase2b/20261108T144011Z` — `REPORT_ONLY`, build 11, Jenkins `SUCCESS`,
  correlation 19/19 at the time (the 2C-Advanced stage did not exist yet).
- `phase2e/20261108T144511Z` — `ENFORCE`, build 13, expected gate failure
  (`HIGH/CRITICAL=70 exceeds threshold 0`); all upstream phases `PASS`.

Raw evidence and PCAPs stay out of Git. The tracked green 2A run in this
repository is
[`results/scenario-b/phase2a/20261102T230116Z/`](../results/scenario-b/phase2a/20261102T230116Z/).

## What analytics adds, and what it must never do

`analytics.py` (2C-Advanced) extracts request and flow features from the same
PCAP, learns a "normal browsing" baseline from the run's content-retrieval
cluster, scores every request with a modified z-score and classifies it into
behavioural clusters. It is **supplementary**:

- both JSON artifacts carry `supplementary: true` and `gate_impact: "none"`;
- the stage exits non-zero only on a tool failure, and reports `DEGRADED`
  instead of `FAIL` when the model is weak;
- correlation records the outcome but tolerates its absence
  (`optional stage not run`), so it can never open or close the gate.

Its rates describe one controlled capture dominated by attack traffic. They are
not detection accuracy, and the model is not a replacement for Suricata.
