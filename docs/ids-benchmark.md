# ISCXIDS2012 — independent IDS evaluation

The brief asks for an IDS evaluation on a dataset that is **independent of the
live lab**: a documented subset with normal traffic and at least two intrusion
scenarios, volume and labels identified, a detection method applied to it, and
precision / recall / F1 / false-positive rate reported per attack category —
not a single accuracy number. This document is that evaluation. The scripts
are `project2/scenario-b/ids-eval/{extract,evaluate}.py`; the evidence of the
run quoted here is `results/ids-eval/20261123T170555Z/`.

## 1. Dataset and subset

Source: ISCXIDS2012, `labeled_flows_xml/` release, 12 XML files (3.1 GB) with
one flow record per line-group and a binary `Tag` (`Normal` / `Attack`).
The supplied files are not always well-formed XML (a raw control byte inside a
payload breaks a strict parser at `TestbedThuJun17-1Flows.xml`), so
`extract.py` streams records by their own tags and reads fields with a regex.

The attack **scenario is a property of the day**, not of the flow: the release
labels every flow binary. Days and scenarios follow the published description
(UNB CIC, *Intrusion detection evaluation dataset*), and the extractor checks
that the flows and attacks it reads match the published per-day totals:

| Day | Scenario | Files | Flows read | Attacks | Published (flows/attacks) | Match |
|---|---|---|---|---|---|---|
| 2010-06-12 | SSH brute force | 1 | 133,193 | 2,086 | 133,193 / 2,086 | yes |
| 2010-06-13 | Infiltration from inside | 1 | 275,528 | 20,358 | 275,528 / 20,358 | yes |
| 2010-06-14 | HTTP denial of service | 1 | 171,380 | 3,776 | 171,380 / 3,776 | yes |
| 2010-06-15 | DDoS via IRC botnet | 3 | 571,698 | 37,460 | 571,698 / 37,460 | yes |
| 2010-06-16 | Normal activity | 3 | 522,263 | 11 | 522,263 / 11 | yes |
| **Total** | **5 days, 4 scenarios** | **9** | **1,674,062** | **63,691** | — | — |

Flow-level SHA-256 of each source file is in `manifest.json`. The subset
**excludes 2010-06-17** (a second SSH brute-force day) on purpose: keeping it
out makes the SSH scenario an *unseen attack type* at evaluation time, which
is the harder and more informative setting. Section 6 states what that choice
costs.

Sampling: every attack flow of the selected days is kept (63,691) and normal
flows are reservoir-sampled to 60,000 per day (seed 42), giving **603,691
flows, 70.6 MB** (`flows.csv`, sha256 `230d9654092b3228…`). 10.55 % of the
subset is attack traffic; in the raw 2.07 M flows of the five days it is
3.33 %, and on the normal day it is 11/522,263 (0.002 %).

Features (23 + one-hot app): duration, bytes and packets per direction,
bytes/packets ratio, mean packet size per direction, source and destination
port, TCP flag counts (`S/A/F/R`), protocol one-hot, direction, seven
well-known destination ports, top-12 application names. Byte, packet and
duration columns are `log1p` transformed, then standardized. Payloads are not
used: the XML keeps them, but a flow-level detector that needs payload bytes
would not survive TLS.

## 2. Methods

**Supervised — leave-one-day-out.** For each test day the model is trained on
the flows of the *other* days only (attacks from the training days plus a
normal sample, at most 30,000 each, 8 epochs), so neither the evaluated day nor
its attack campaign is seen in training. Logistic regression with balanced
class weights, decision threshold 0.5, implemented in plain Python (no numpy,
no scikit-learn: the CI image has neither and the pipeline must stay
dependency-free). This is a deliberate baseline: if it generalizes, the task is
not hard; if it does not, the failure mode is visible.

**Unsupervised — normal-only baseline.** A modified z-score per feature
(`0.6745·(x−median)/MAD`) is learned on the normal day; a flow is flagged when
its largest absolute score exceeds the 99.5th percentile of the baseline
scores. No label is used to fit it. This mirrors what 2C-Advanced does on the
lab PCAP, so the two results are comparable.

Both are scored on **every** row of the subset, not on the training sample.

## 3. Results per scenario

| Day | Scenario | Supervised P / R / F1 | FPR | Unsupervised P / R / F1 | FPR |
|---|---|---|---|---|---|
| 06-12 | SSH brute force | 0.327 / **0.301** / 0.314 | 2.15 % | 0.000 / 0.000 / 0.000 | 1.83 % |
| 06-13 | Infiltration | 0.965 / **0.949** / 0.957 | 1.18 % | 0.159 / 0.018 / 0.032 | 3.18 % |
| 06-14 | HTTP DoS | 0.726 / **0.842** / 0.779 | 2.00 % | 0.055 / 0.020 / 0.030 | 2.21 % |
| 06-15 | DDoS (IRC botnet) | 0.774 / **0.998** / 0.872 | 6.07 % | 0.003 / 0.000 / 0.001 | 2.42 % |
| 06-16 | Normal day | 0.007 / 1.000 / 0.013 | 0.91 % | 0.000 / 0.000 / 0.000 | 0.71 % |

Overall, all 603,691 flows:

| Method | TP | FN | FP | TN | Precision | Recall | F1 | FPR | Accuracy |
|---|---|---|---|---|---|---|---|---|---|
| Supervised LODO | 60,543 | 3,148 | 15,761 | 524,239 | 0.793 | 0.951 | 0.865 | 2.92 % | 96.9 % |
| Unsupervised z-score | 451 | 63,240 | 9,977 | 530,023 | 0.043 | 0.007 | 0.012 | 1.85 % | 87.9 % |

Confusion matrices are in `eval.json` and rendered in `eval.md` of the run
directory.

## 4. What was detected, what was missed

- **DDoS via IRC botnet — detected (0.998 recall).** Bot-driven floods have a
  distinctive volume/packet shape: many flows, one direction, small mean packet
  size, high packet counts. The model finds them even without the day in
  training.
- **Infiltration — detected (0.949)**, with the best precision of the run
  (0.965). The multi-stage campaign keeps a recognisable signature because its
  scanning, reverse shell and C&C flows differ from the day's normal profile.
- **HTTP DoS — partially detected (0.842 recall, 0.726 precision).** The flood
  flows are caught, but they sit close to heavy normal HTTP traffic, so a
  quarter of what it flags as attack is normal.
- **SSH brute force — mostly missed (0.301 recall).** Trained on floods and
  infiltration, the model has no example of a low-volume credential attack: a
  short TCP conversation against port 22 looks like a normal interactive
  session to a volume-shaped model. This is the clearest statement of the point
  the brief asks for: *an IDS is only as good as the attack types it has seen*.
- **Normal traffic** is classified correctly 97.1 % of the time overall (99.1 %
  on the normal day), but there precision collapses to 0.007: with 11 attacks
  in 522,263 flows, almost everything flagged is a false positive. Accuracy
  would hide this; precision does not.
- **The unsupervised baseline detects almost nothing** (0.7 % recall). Its
  strongest features are marginal distributions, and attack flows overlap
  normal ones feature by feature; only a multivariate model separates them.
  This is the empirical argument for keeping 2C-Advanced *supplementary* and
  the deterministic rule in charge of the gate.

## 5. Class imbalance and dataset limitations

- Attacks are 3.33 % of the raw subset (10.55 % after capping normals). At the
  normal day it is 0.002 %. Precision, not accuracy, is the number that matters
  at that ratio, and a single global threshold cannot serve both a 37,460-attack
  day and an 11-attack day.
- **Labels are binary.** The release does not say which flow is DDoS and which
  is scan; scenarios are day-level, so "per-category" here means per-day, and a
  day can contain more than one attack type (06-13 mixes scanning, reverse
  shell and C&C; 06-14 mixes SMB exploit and HTTP flood).
- **Flow-level only.** No payload, no TLS metadata, no application context;
  encrypted C&C, low-and-slow credentials and in-protocol attacks are outside
  what these features can see.
- **One dataset, one testbed, 2010 traffic.** The testbed is a 21-host Windows
  network from 2010; the attack mix, the tooling and the background traffic do
  not represent a 5G core or a modern container platform.
- **Day as a unit** means an attack campaign can share hosts with normal
  traffic; leave-one-day-out avoids leakage by day, but not the correlation
  between flows of the same campaign.
- **Selection cost.** Excluding 06-17 keeps SSH unseen; including it would
  raise SSH recall and lower the apparent difficulty. The subset is declared,
  not tuned: it is the first five days with two SSH days, one deliberately held
  out.
- **Sampling.** 60,000 normals per day is a sample; the metrics are computed on
  the sample, not on the 1.67 M flows read. The attack class is complete.

## 6. Benchmark versus real telecommunications security

A 96.9 % accuracy here would be a trap. In an operator network:

- traffic is dominated by a handful of applications and protocols, and the
  normal class shifts with the hour, the subscriber and the slice;
- attacks relevant to 5G (signalling abuse, GTP-U injection, subscriber
  impersonation, N4/PFCP manipulation) are **not in this dataset at all** —
  ISCX is an enterprise IT testbed;
- a detector that fires 15,761 false positives out of 540,000 normal flows
  would drown a SOC; 2.9 % FPR at line rate is thousands of alerts per minute;
- per-attack recall, not aggregate F1, is what tells you whether a new campaign
  will be seen at all.

That is why the lab pipeline does not put a statistical model in charge: the
gate is decided by deterministic evidence (ZAP alert 40018, Suricata SID
1000001, Trivy counts), the traffic-intelligence stage is marked
`supplementary` with `gate_impact: none`, and this evaluation is reported as a
bounded benchmark of the *method*, not as a claim about the 5G core.

## 7. Reproduce

```bash
cd ~/Documentos/VSCODE/5G-2-Security
D="$HOME/Escritorio/ISCXIDS2012 dataset/labeled_flows_xml"
R=$(date -u +%Y%m%dT%H%M%SZ)
/usr/bin/python3 project2/scenario-b/ids-eval/extract.py --dataset-dir "$D" \
    --out-dir results/ids-eval/$R --cap 60000
/usr/bin/python3 project2/scenario-b/ids-eval/evaluate.py --run-dir results/ids-eval/$R
jq '.scenarios | to_entries[] | {day: .key, scenario: .value.scenario,
     recall: .value.supervised.recall}' results/ids-eval/$R/eval.json
```

The dataset is not in Git (3.1 GB, academic licence). `manifest.json` pins each
source file by SHA-256, so a different copy cannot pass unnoticed.
