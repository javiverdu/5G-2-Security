# AGENTS.md — Project 2, Scenario B (2A–2E)

Scenario B is a **security-engineering extension** of the verified Scenario A
baseline, not a second 5G network. Security tools are CI jobs, never network
functions or packet-forwarding nodes.

Root [`../../AGENTS.md`](../../AGENTS.md) and
[`../scenario-a/AGENTS.md`](../scenario-a/AGENTS.md) still apply.
**Do not simplify the acceptance criteria or reorder the gate.**

## Path

```text
source/GitHub → Jenkins → Preflight → ZAP baseline → Selenium runtime
  → start fresh PCAP → controlled SQLi → targeted ZAP → stop PCAP
  → Suricata offline → traffic intelligence (optional) → Trivy → Syft
  → evidence correlation → archive → Security Gate → final result
```

The order is a contract. Later stages may only consume earlier artifacts.

## Addresses and names (fixed)

| Thing | Value |
|---|---|
| Security network | `security-net` `10.20.10.0/24` |
| Juice Shop | `10.20.10.20:3000`, image `bkimminich/juice-shop:v20.2.0` |
| Selenium Grid | `10.20.10.30:4444`, image `telecom-lab-selenium:1.0` |
| Jenkins | `10.20.10.40:8080`, container `scenario-b-jenkins`, image `telecom-lab-jenkins:2.580.1-jdk21` |
| ZAP | `ghcr.io/zaproxy/zaproxy:stable`, ephemeral |
| Capture | `telecom-lab-capture:1.0`, ephemeral, shares the target netns |
| Suricata | `jasonish/suricata:8.0`, ephemeral, offline PCAP |
| Trivy | `aquasec/trivy:0.75.0`, ephemeral |
| Syft | `anchore/syft:v1.52.0`, ephemeral |
| Correlation | `telecom-lab-correlation:1.0`, ephemeral |

Juice Shop is the **positive control**: it is deliberately vulnerable and is
isolated from the Scenario A Django/Nginx path (never on `dn-net`).

## Hard rules

1. **Gate order is fixed.** 1E → 2A → 2B → 2C → 2D → 2E → archive → gate.
2. **Evidence is never invented.** Every assertion comes from a file the tool
   produced or a command that can be rerun; record the command with the result.
3. **Positive controls:** ZAP Alert 40018 detected and Suricata SID 1000001
   detected are **PASS**. A green pipeline does not mean the target is secure.
4. **Separate the layers:** tool exit status, security finding, and gate
   decision are reported separately. `REPORT_ONLY` never fails the build;
   `ENFORCE` fails only on the configured condition.
5. **Fresh capture window:** START CAPTURE → controlled SQLi → targeted test →
   STOP CAPTURE. Never capture after generating the traffic.
6. **Current-run evidence only.** Each run gets a `RUN_ID` and its own
   directory; old artifacts must not satisfy a check.
7. **Pin every external version** in `RELEASE-MANIFEST.json`; Preflight compares
   actual versions with it.
8. **Secrets stay out of Git:** `project2/scenario-b/env` and
   `project2/scenario-a/env`, `secrets/tls/`.
9. **Nothing runs from the VirtualBox shared folder.**

## Evidence layout

```text
results/scenario-b/phase2a/<RUN_ID>/   preflight.json, preflight.md
results/scenario-b/phase2b/<RUN_ID>/   ZAP, Selenium, plan, screenshot
results/scenario-b/phase2c/<RUN_ID>/   PCAP, eve.json, fast.log, stats.log
results/scenario-b/phase2d/<RUN_ID>/   trivy, sbom.cdx.json
results/scenario-b/phase2e/<RUN_ID>/   correlation.json/.md, archive, gate
```
