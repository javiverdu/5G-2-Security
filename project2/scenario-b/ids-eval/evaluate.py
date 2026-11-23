#!/usr/bin/env python3
"""Evaluate two intrusion-detection methods on the extracted ISCX flows.

Protocol
--------
* **Supervised, leave-one-day-out.** For every test day the model is trained
  on flows from the *other* days only, so no flow of the evaluated day (and
  none of its attack campaign) is seen during training. Training uses a
  deterministic sample: attacks from the training days plus a normal sample,
  with balanced class weights. Decision threshold 0.5.
* **Unsupervised, normal-only baseline.** Learned from the normal day
  (2010-06-16) with a modified z-score per feature; a flow is flagged when its
  largest absolute score exceeds the 99.5th percentile of the baseline. No
  label is used to fit it, only to evaluate it.

Both are scored on **every** row of the extracted CSV.

Output: eval.json (machine) and eval.md (human) with, per day and overall:
confusion matrix, precision, recall, F1, false-positive rate and accuracy.

Rows are kept as compact float arrays (23 features) so 600k flows fit in
memory without pandas or numpy.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from array import array
from datetime import datetime, timezone
from pathlib import Path

NUMERIC = [
    "duration_s", "src_bytes", "dst_bytes", "src_pkts", "dst_pkts",
    "bytes_ratio", "pkts_ratio", "avg_src_pkt", "avg_dst_pkt",
    "src_port", "dst_port", "flag_s", "flag_a", "flag_f", "flag_r",
    "proto_tcp", "proto_udp", "proto_icmp", "l2r",
]
LOG_FIELDS = {"src_bytes", "dst_bytes", "src_pkts", "dst_pkts",
              "avg_src_pkt", "avg_dst_pkt", "duration_s"}
PORT_FLAGS = (22, 25, 80, 443, 445, 5555, 6667)
TOP_APPS = 12


def read_rows(path: Path, apps: list[str]) -> tuple[list[tuple[int, int, array]], list[str]]:
    day_index: dict[str, int] = {}
    days: list[str] = []
    rows: list[tuple[int, int, array]] = []
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        col = {name: i for i, name in enumerate(header)}
        for record in reader:
            day = record[col["day"]]
            if day not in day_index:
                day_index[day] = len(days)
                days.append(day)
            vec = array("f")
            for name in NUMERIC:
                value = float(record[col[name]] or 0.0)
                if name in LOG_FIELDS:
                    value = math.log1p(max(0.0, value))
                vec.append(value)
            dst_port = int(float(record[col["dst_port"]] or 0))
            for port in PORT_FLAGS:
                vec.append(1.0 if dst_port == port else 0.0)
            app = record[col["app"]]
            for name in apps:
                vec.append(1.0 if app == name else 0.0)
            rows.append((day_index[day], int(record[col["label"]]), vec))
    return rows, days


def vocabulary(path: Path) -> list[str]:
    counts: dict[str, int] = {}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            counts[row["app"]] = counts.get(row["app"], 0) + 1
    return [app for app, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:TOP_APPS]]


def fit_scaler(vectors: list[array]) -> tuple[list[float], list[float]]:
    dim = len(vectors[0])
    means, stds = [], []
    for j in range(dim):
        column = [v[j] for v in vectors]
        means.append(statistics.fmean(column))
        stds.append(statistics.pstdev(column) or 1.0)
    return means, stds


def scale(vec: array, means: list[float], stds: list[float]) -> list[float]:
    return [(v - m) / s for v, m, s in zip(vec, means, stds)]


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def train_logreg(points: list[tuple[list[float], int]], epochs: int,
                 lr: float = 0.05, l2: float = 1e-4) -> tuple[list[float], float]:
    dim = len(points[0][0])
    weights = [0.0] * dim
    bias = 0.0
    positives = sum(1 for _, y in points if y == 1)
    negatives = len(points) - positives
    w_pos = negatives / positives if positives else 1.0
    adagrad = [1e-6] * (dim + 1)
    order = list(range(len(points)))
    rng = random.Random(7)
    for _ in range(epochs):
        rng.shuffle(order)
        for idx in order:
            x, y = points[idx]
            z = bias + sum(w * v for w, v in zip(weights, x))
            p = sigmoid(z)
            error = (p - y) * (w_pos if y == 1 else 1.0)
            for j in range(dim):
                grad = error * x[j] + l2 * weights[j]
                adagrad[j] += grad * grad
                weights[j] -= lr * grad / math.sqrt(adagrad[j])
            adagrad[dim] += error * error
            bias -= lr * error / math.sqrt(adagrad[dim])
    return weights, bias


def confusion(pred: int, label: int, cell: dict) -> None:
    if label == 1:
        cell["tp" if pred == 1 else "fn"] += 1
    else:
        cell["fp" if pred == 1 else "tn"] += 1


def metrics(cell: dict) -> dict:
    tp, fp, fn, tn = cell["tp"], cell["fp"], cell["fn"], cell["tn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "false_positive_rate": round(fpr, 4),
            "accuracy": round(accuracy, 4), "attacks": tp + fn, "normals": fp + tn}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--train-attacks", type=int, default=30000)
    parser.add_argument("--train-normals", type=int, default=30000)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    manifest = json.loads((args.run_dir / "manifest.json").read_text())
    csv_path = args.run_dir / "flows.csv"
    apps = vocabulary(csv_path)
    print(f"[eval] app vocabulary: {apps}")
    rows, days = read_rows(csv_path, apps)
    print(f"[eval] {len(rows)} rows, {len(days)} days")

    rng = random.Random(args.seed)
    attack_idx = [i for i, (_, label, _) in enumerate(rows) if label == 1]
    normal_idx = [i for i, (_, label, _) in enumerate(rows) if label == 0]
    rng.shuffle(attack_idx)
    rng.shuffle(normal_idx)
    sample_idx = attack_idx[:args.train_attacks] + normal_idx[:args.train_normals]
    sample_vectors = [rows[i][2] for i in sample_idx]
    means, stds = fit_scaler(sample_vectors)
    scaled_sample = [scale(v, means, stds) for v in sample_vectors]

    report: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": manifest.get("dataset"),
        "run_dir": str(args.run_dir),
        "flows_csv": manifest.get("csv"),
        "subset": manifest.get("by_day"),
        "features": len(rows[0][2]),
        "protocol": {
            "supervised": (f"leave-one-day-out logistic regression "
                           f"(attacks<={args.train_attacks}, normals<={args.train_normals}, "
                           f"epochs={args.epochs}), balanced class weights, threshold 0.5"),
            "unsupervised": ("modified z-score on a normal-only baseline (2010-06-16), "
                             "threshold = 99.5th percentile of baseline scores"),
        },
        "methods": {},
    }

    # ---- supervised: leave-one-day-out -----------------------------------
    per_day_sup: dict[str, dict] = {}
    total = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for test_day in days:
        points = [(x, rows[i][1]) for x, i in zip(scaled_sample, sample_idx)
                  if rows[i][0] != days.index(test_day)]
        weights, bias = train_logreg(points, epochs=args.epochs)
        cell = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for day_idx, label, vec in rows:
            if day_idx != days.index(test_day):
                continue
            x = scale(vec, means, stds)
            p = sigmoid(bias + sum(w * v for w, v in zip(weights, x)))
            confusion(1 if p >= 0.5 else 0, label, cell)
        per_day_sup[test_day] = metrics(cell)
        for key in total:
            total[key] += cell[key]
        print(f"[supervised] {test_day}: recall={cell['tp'] / max(1, cell['tp'] + cell['fn']):.3f} "
              f"fpr={cell['fp'] / max(1, cell['fp'] + cell['tn']):.4f}")
    report["methods"]["supervised_lodo"] = {"per_day": per_day_sup, "overall": metrics(total)}

    # ---- unsupervised: normal-only baseline ------------------------------
    normal_day = days.index("2010-06-16") if "2010-06-16" in days else 0
    base_vectors = [scale(vec, means, stds) for day_idx, _, vec in rows if day_idx == normal_day]
    medians = [statistics.median(col) for col in zip(*base_vectors)]
    mads = []
    for j, med in enumerate(medians):
        mads.append(statistics.median(abs(v[j] - med) for v in base_vectors) or 1e-6)

    def score(x: list[float]) -> float:
        return max(abs(0.6745 * (v - m) / s) for v, m, s in zip(x, medians, mads))

    baseline_scores = sorted(score(v) for v in base_vectors)
    threshold = baseline_scores[int(0.995 * (len(baseline_scores) - 1))]
    per_day_uns: dict[str, dict] = {}
    total_uns = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for day_idx, day in enumerate(days):
        cell = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for row_day, label, vec in rows:
            if row_day != day_idx:
                continue
            confusion(1 if score(scale(vec, means, stds)) >= threshold else 0, label, cell)
        per_day_uns[day] = metrics(cell)
        for key in total_uns:
            total_uns[key] += cell[key]
        print(f"[unsupervised] {day}: recall={cell['tp'] / max(1, cell['tp'] + cell['fn']):.3f} "
              f"fpr={cell['fp'] / max(1, cell['fp'] + cell['tn']):.4f}")
    report["methods"]["unsupervised_zscore"] = {
        "threshold": round(threshold, 4), "per_day": per_day_uns,
        "overall": metrics(total_uns),
    }

    scenarios = {}
    scenario_by_day = {d["day"]: d["scenario"] for d in manifest.get("days", [])}
    for day in days:
        scenarios[day] = dict(manifest["by_day"][day])
        scenarios[day]["scenario"] = scenario_by_day.get(day, "unknown")
        scenarios[day]["supervised"] = per_day_sup[day]
        scenarios[day]["unsupervised"] = per_day_uns[day]
    report["scenarios"] = scenarios

    (args.run_dir / "eval.json").write_text(json.dumps(report, indent=2) + "\n")
    write_markdown(report, args.run_dir / "eval.md")
    print(f"[eval] wrote eval.json and eval.md in {args.run_dir}")
    return 0


def write_markdown(report: dict, path: Path) -> None:
    sup = report["methods"]["supervised_lodo"]
    uns = report["methods"]["unsupervised_zscore"]
    lines = [
        "# ISCXIDS2012 — IDS evaluation",
        "",
        f"- Generated: `{report['generated_utc']}`",
        f"- Subset: `{report['flows_csv']['rows']}` flows, "
        f"sha256 `{report['flows_csv']['sha256'][:16]}…`",
        f"- Supervised: {report['protocol']['supervised']}",
        f"- Unsupervised: {report['protocol']['unsupervised']}",
        "",
        "## Per-day results (day = attack scenario)",
        "",
        "| Day | Scenario | Flows | Attacks | Supervised P/R/F1 | FPR | Unsupervised P/R/F1 | FPR |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for day, scen in report["scenarios"].items():
        s, u = scen["supervised"], scen["unsupervised"]
        lines.append(
            f"| {day} | {scen['scenario']} | {scen['flows']} | {scen['attacks']} | "
            f"{s['precision']:.3f}/{s['recall']:.3f}/{s['f1']:.3f} | {s['false_positive_rate']:.4f} | "
            f"{u['precision']:.3f}/{u['recall']:.3f}/{u['f1']:.3f} | {u['false_positive_rate']:.4f} |")
    lines += ["", "## Confusion matrices (all days)", "",
              "Supervised (leave-one-day-out):", "",
              "| | predicted attack | predicted normal |", "|---|---|---|",
              f"| **actual attack** | {sup['overall']['tp']} | {sup['overall']['fn']} |",
              f"| **actual normal** | {sup['overall']['fp']} | {sup['overall']['tn']} |",
              "", "Unsupervised (normal-only baseline):", "",
              "| | predicted attack | predicted normal |", "|---|---|---|",
              f"| **actual attack** | {uns['overall']['tp']} | {uns['overall']['fn']} |",
              f"| **actual normal** | {uns['overall']['fp']} | {uns['overall']['tn']} |",
              "", "## Overall", "",
              "| Method | Precision | Recall | F1 | FPR | Accuracy |", "|---|---|---|---|---|---|"]
    for name, block in (("supervised", sup["overall"]), ("unsupervised", uns["overall"])):
        lines.append(f"| {name} | {block['precision']:.3f} | {block['recall']:.3f} | "
                     f"{block['f1']:.3f} | {block['false_positive_rate']:.4f} | "
                     f"{block['accuracy']:.3f} |")
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
