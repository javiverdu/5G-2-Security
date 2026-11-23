# ISCXIDS2012 — IDS evaluation

- Generated: `2026-11-23T17:08:17+00:00`
- Subset: `603691` flows, sha256 `230d9654092b3228…`
- Supervised: leave-one-day-out logistic regression (attacks<=30000, normals<=30000, epochs=8), balanced class weights, threshold 0.5
- Unsupervised: modified z-score on a normal-only baseline (2010-06-16), threshold = 99.5th percentile of baseline scores

## Per-day results (day = attack scenario)

| Day | Scenario | Flows | Attacks | Supervised P/R/F1 | FPR | Unsupervised P/R/F1 | FPR |
|---|---|---|---|---|---|---|---|
| 2010-06-12 | ssh-bruteforce | 133193 | 2086 | 0.327/0.301/0.314 | 0.0215 | 0.000/0.000/0.000 | 0.0183 |
| 2010-06-13 | infiltration-inside | 275528 | 20358 | 0.965/0.949/0.957 | 0.0118 | 0.159/0.018/0.032 | 0.0318 |
| 2010-06-14 | http-dos | 171380 | 3776 | 0.726/0.842/0.779 | 0.0200 | 0.055/0.020/0.030 | 0.0221 |
| 2010-06-15 | ddos-irc-botnet | 571698 | 37460 | 0.774/0.998/0.872 | 0.0607 | 0.003/0.000/0.001 | 0.0242 |
| 2010-06-16 | normal | 522263 | 11 | 0.007/1.000/0.013 | 0.0091 | 0.000/0.000/0.000 | 0.0071 |

## Confusion matrices (all days)

Supervised (leave-one-day-out):

| | predicted attack | predicted normal |
|---|---|---|
| **actual attack** | 60543 | 3148 |
| **actual normal** | 15761 | 524239 |

Unsupervised (normal-only baseline):

| | predicted attack | predicted normal |
|---|---|---|
| **actual attack** | 451 | 63240 |
| **actual normal** | 9977 | 530023 |

## Overall

| Method | Precision | Recall | F1 | FPR | Accuracy |
|---|---|---|---|---|---|
| supervised | 0.793 | 0.951 | 0.865 | 0.0292 | 0.969 |
| unsupervised | 0.043 | 0.007 | 0.012 | 0.0185 | 0.879 |
