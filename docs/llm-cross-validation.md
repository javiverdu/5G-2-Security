# LLM-assisted cross-validation

The brief requires at least two LLM-assisted cross-validation tasks, each one
documented with model/provider, date, prompt, input evidence, the LLM
conclusion, an independently verified conclusion, and any disagreement between
the two. (Like the ISCX evaluation, this requirement comes from the course's
additional Scenario B hints, not from `brief-p2.txt`.) It also requires that
the LLM is never the authoritative detector, the correlation engine or the
gate.

This document records two tasks against the artefacts of Jenkins **build 20**
(`20261123T163741Z`, `REPORT_ONLY`, `SUCCESS`). In both, the LLM produced a
claim first and the claim was then checked against the machine-generated files;
where they disagree, the file wins and the disagreement is written down.

## How the LLM was used, and what it was not allowed to do

- **Model / provider:** Hermes Agent session using the configured model
  `modelo-grande` served by `Nienna-llm.inf.um.es` (custom provider). The
  provider does not expose a finer build string; that is recorded here instead
  of inventing one.
- **Date:** 2026-11-23.
- **Role:** read the evidence, propose an interpretation, and be wrong when the
  evidence says so. It did not produce any number that was not afterwards
  recomputed from the artefacts with `jq` / a stdlib script.
- **Not used for:** the Security Gate (`phase2e.py gate`), the IDS detections,
  the correlation chain (`correlate.py`), or any vulnerability finding. Those
  are deterministic and unchanged by this document.

---

## Task 1 — SBOM versus vulnerability-scanning evidence

**Input evidence** (`results/scenario-b/phase2d/20261123T163741Z/`):
`sbom.cdx.json` (CycloneDX 1.7, 2,677 component entries) and
`trivy-juice-shop.json` (Trivy scan of `bkimminich/juice-shop:v20.2.0`,
224 vulnerabilities, 70 HIGH/CRITICAL: 12 CRITICAL + 58 HIGH).

**Prompt summary.** "Here are the SBOM component list and the Trivy report for
the same image. Explain how the two relate, say whether every HIGH/CRITICAL
finding can be located in the SBOM, and name the packages that concentrate the
findings. State what would constitute disagreement between the two artefacts."

**LLM conclusion (before verification).** Two claims:

1. The SBOM is an inventory, not a verdict: it should contain the vulnerable
   packages, but exact versions may not line up because Trivy resolves
   vulnerabilities against its own database, so some HIGH/CRITICAL findings may
   have **no matching component** — in particular operating-system libraries,
   which an application-level SBOM usually omits.
2. The findings should concentrate in a few Node.js packages, and that
   concentration is what makes the picture actionable.

**Independent verification.**

```bash
cd ~/Documentos/VSCODE/5G-2-Security
N=20261123T163741Z
jq '[.components[] | [.name, .version]] | unique | length' \
   results/scenario-b/phase2d/$N/sbom.cdx.json            # 2632 unique pairs
jq '[.Results[].Vulnerabilities[]?] | length' \
   results/scenario-b/phase2d/$N/trivy-juice-shop.json     # 224
jq -r '[.Results[].Vulnerabilities[]? | select(.Severity=="HIGH" or .Severity=="CRITICAL")]
       | group_by(.PkgName) | map({pkg: .[0].PkgName, n: length}) | sort_by(-.n) | .[:6]' \
   results/scenario-b/phase2d/$N/trivy-juice-shop.json
```

Then the set comparison, done in Python over the two files: for each
HIGH/CRITICAL finding, look up `(PkgName, InstalledVersion)` in the SBOM
component set.

**Verified conclusion.**

- SBOM: 2,677 entries, **2,632 unique (name, version) pairs** — the extra 45
  are the same package reachable through different paths, not different
  software.
- Trivy: 224 findings, 70 HIGH/CRITICAL.
- **All 70 HIGH/CRITICAL findings match an SBOM component with the exact same
  name and version. Zero findings are absent, zero differ in version.**
- Concentration: `multer` 10, `tar` 9, `jsonwebtoken` 6, `undici` 5,
  `brace-expansion` 4, `libssl3t64` 3.
- The SBOM also contains operating-system packages (`libssl3t64` is one of the
  vulnerable ones), so the second half of claim 1 is also wrong for this image.

**Disagreement (explicit).** The LLM predicted that some HIGH/CRITICAL findings
would not be traceable to the SBOM — specifically OS libraries. The evidence
contradicts that: the SBOM is complete for this image and every finding is
locatable. What survives of the claim is only the general principle ("inventory
versus verdict"); the specific mismatch it predicted does not exist here. The
reporting consequence is the opposite of what was guessed: Trivy is not
*adding* packages the SBOM missed, it is *scoring* the packages the SBOM
already lists.

**Why this matters for the deliverable.** It turns an assumption into a checked
property: SBOM and Trivy are complementary (inventory vs. known CVEs) and, in
this build, consistent. It also scopes the claim: consistency does not mean
exploitability — nothing here says those 70 CVEs are reachable in the Juice
Shop container.

---

## Task 2 — Correlation claim: traffic intelligence versus Suricata

**Input evidence** (`results/scenario-b/phase2c/20261123T163741Z/`):
`traffic-classification.json` (135 HTTP requests scored by 2C-Advanced,
98 flagged) and `eve.json` (44 Suricata alerts on SID 1000001), plus
`security-event-correlation.json` from 2E.

**Prompt summary.** "2C-Advanced flags 98 of 135 requests; Suricata raises 44
alerts. Does the analytics output agree with the network detector? Can I say
the model detects the same attack, and that it is more sensitive?"

**LLM conclusion (before verification).** "98 flags against 44 alerts suggests
the model is roughly twice as sensitive as Suricata and catches the same
attack, possibly more of it. Treat it as supporting evidence that the attack
was detected."

**Independent verification.**

```bash
cd ~/Documentos/VSCODE/5G-2-Security
N=20261123T163741Z
jq '[.assignments[] | select(.flagged)] | length' \
   results/scenario-b/phase2c/$N/traffic-classification.json          # 98
jq -r 'select(.event_type=="alert") | .http.url' \
   results/scenario-b/phase2c/$N/eve.json | sort -u | wc -l           # 37 unique URIs
```

Then the set comparison in Python: unique URIs flagged by the model versus
unique URIs Suricata alerted on.

**Verified conclusion.**

- Requests: 135; flagged: **98** (73 %), on **45 unique URIs**.
- Suricata: **44 alert events on 37 unique URIs** — 44 is the number of events,
  not of distinct requests; several payloads repeat the same URI.
- Set comparison: **all 37 URIs Suricata alerted on are in the model's flagged
  set (100 % coverage); 8 flagged URIs were not alerted.** Zero misses in the
  other direction.
- The controlled request `/rest/products/search?q=%27%28` (frame 4, score 16.0)
  is flagged.

**Disagreement (explicit).** The "98 versus 44, so twice as sensitive" reading
is wrong twice: the two numbers count different objects (flagged *requests* vs
alert *events*), and sensitivity cannot be inferred from raw counts. What the
evidence does support is narrower and stronger: the model's flagged set
**contains every URI Suricata alerted on** (no misses relative to the rule) and
adds 8 URIs the rule ignored. Precision cannot be measured here — the capture
carries no per-request ground truth, and 73 % flagged is what a scanner sweep
looks like, not what a detector looks like.

**Why this matters for the deliverable.** It fixes the sentence the report can
defend: analytics is a *triage aid with full coverage of the rule's hits*, not
a better detector. It also justifies, with data, why 2C-Advanced is marked
`supplementary` / `gate_impact: none` and why the gate keeps depending on SID
1000001 and ZAP 40018.

---

## What the two tasks changed in the deliverable

| Claim from the LLM | Verified outcome | Where it landed |
|---|---|---|
| "Some HIGH/CRITICAL findings have no SBOM component (OS packages)" | False for build 20: 70/70 exact matches | [report.md](report.md) SBOM/Trivy row and this section |
| "The model is twice as sensitive as Suricata" | Invalid comparison; correct claim is 37/37 URI coverage plus 8 extra | report.md §8.1 properties and this section |
| "Concentration in a few packages makes it actionable" | Confirmed: 6 packages hold 37 of the 70 | report.md §10 Trivy row |

Neither LLM output feeds a decision: the gate reads `gate.json`, which is
produced by `phase2e.py` from the artefacts, and the IDS rule decision comes
from `eve.json`. If both LLM conclusions had been wrong, the build would have
been unchanged — which is the property the brief asks for.
