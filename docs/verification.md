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

Expected console output:

```text
[run] build N result: SUCCESS
[preflight] PASS — 0 failed of 35
[2B] summary: PASS — 0 failed of 23
[2C] phase2c: PASS — 0 failed of 12
[2C-Advanced] analytics: PASS — 0 failed of 10; controlled request FLAGGED
[2D] phase2d: PASS — 0 failed of 10
[2E] correlation: PASS — 0 failed of 22
[2E] gate: PASS (REPORT_ONLY) — ...
```

### Artifacts per phase

| Phase | Directory | Key files |
|---|---|---|
| 2A | `results/scenario-b/phase2a/<RUN_ID>/` | `baseline-1e.txt`, `preflight.json/.md`, proof PCAP |
| 2B | `results/scenario-b/phase2b/<RUN_ID>/` | ZAP baseline HTML/MD/JSON, Selenium JSON + screenshot, `plan.yaml`, targeted `zap-sqli.json` |
| 2C | `results/scenario-b/phase2c/<RUN_ID>/` | fresh `juice-shop-ci-sqli.pcapng`, `eve.json`, `fast.log`, `stats.log`, `phase2c.json/.md` |
| 2C-Advanced | `results/scenario-b/phase2c/<RUN_ID>/` | `traffic-features.csv`, `traffic-flows.csv`, `traffic-anomaly.json`, `traffic-classification.json`, `analytics.json/.md` |
| 2D | `results/scenario-b/phase2d/<RUN_ID>/` | `trivy-juice-shop.json`, `trivy-config.json`, `trivy-telecom-lab-django.json`, `trivy-telecom-lab-nginx.json`, `sbom.cdx.json`, `phase2d.json/.md` |
| 2E | `results/scenario-b/phase2e/<RUN_ID>/` | `security-event-correlation.json/.md`, `scenario-b-evidence.tar.gz`, `gate.json/.md` |

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

- `phase2b/20261108T144011Z` — `REPORT_ONLY`, build 11, Jenkins `SUCCESS`,
  correlation 19/19 at the time.
- `phase2e/20261108T144511Z` — `ENFORCE`, build 13, expected gate failure
  (`HIGH/CRITICAL=70 exceeds threshold 0`); all upstream phases `PASS`.
- The 2C-Advanced stage was added after those builds. Replaying the build-11
  evidence with the current scripts gives correlation 22/22 and the same gate
  decisions in both modes.

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
