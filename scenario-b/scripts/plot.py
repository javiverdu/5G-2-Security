#!/usr/bin/env python3
"""Scenario B — page 5: build the comparative table and plots from summary.csv.

Input : results/scenario-b/summary.csv   (condition,metric,run,value,unit)
Output: results/scenario-b/comparison.csv
        results/scenario-b/comparison-table.md
        results/scenario-b/plots/comparison.{png,svg}
"""
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STEP = os.path.join(ROOT, "results", "scenario-b")
SUMMARY = os.path.join(STEP, "summary.csv")

CONDITIONS = ["baseline", "delay", "loss", "rate"]
METRICS = [
    "icmp_rtt_avg", "http_time_avg", "tcp_throughput",
    "udp_throughput", "udp_loss", "udp_jitter",
    "tcp_retransmissions", "tcp_retransmissions_sender",
]
UNITS = {
    "icmp_rtt_avg": "ms", "http_time_avg": "ms", "tcp_throughput": "Mbit/s",
    "udp_throughput": "Mbit/s", "udp_loss": "%", "udp_jitter": "ms",
    "tcp_retransmissions": "count", "tcp_retransmissions_sender": "count",
}
SCALE = {"tcp_throughput": 1e-6, "udp_throughput": 1e-6}  # bit/s -> Mbit/s


def load():
    if not os.path.exists(SUMMARY):
        raise SystemExit(
            f"missing {SUMMARY}\n"
            "run the measurements first:  sudo ./scripts/run-all.sh")
    values = defaultdict(lambda: defaultdict(list))
    with open(SUMMARY) as f:
        for row in csv.DictReader(f):
            try:
                values[row["condition"]][row["metric"]].append(float(row["value"]))
            except ValueError:
                continue
    return values


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def main():
    values = load()
    conds = [c for c in CONDITIONS if c in values]
    metrics = [m for m in METRICS if any(values[c][m] for c in conds)]

    os.makedirs(os.path.join(STEP, "plots"), exist_ok=True)
    with open(os.path.join(STEP, "comparison.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["condition"] + metrics)
        for c in conds:
            w.writerow([c] + [f"{mean(values[c][m]) * SCALE.get(m, 1):.4g}" for m in metrics])

    with open(os.path.join(STEP, "comparison-table.md"), "w") as f:
        f.write("# Scenario B — Comparative results (mean of the repetitions)\n\n")
        f.write("| Condition | " + " | ".join(f"{m} ({UNITS[m]})" for m in metrics) + " |\n")
        f.write("|" + "---|" * (len(metrics) + 1) + "\n")
        for c in conds:
            f.write(f"| {c} | " + " | ".join(
                f"{mean(values[c][m]) * SCALE.get(m, 1):.3f}" for m in metrics) + " |\n")

    colors = {"baseline": "#2c7fb8", "delay": "#f0a202", "loss": "#d7301f", "rate": "#238b45"}
    panels = [
        ("icmp_rtt_avg", "ICMP RTT (avg)", "ms", False),
        ("http_time_avg", "HTTP response time (avg)", "ms", False),
        ("tcp_throughput", "TCP throughput (log scale)", "Mbit/s", True),
        ("udp_throughput", "UDP throughput", "Mbit/s", False),
        ("udp_loss", "UDP loss", "%", False),
        ("udp_jitter", "UDP jitter (avg)", "ms", False),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, (metric, title, unit, logy) in zip(axes.flat, panels):
        vals = [mean(values[c][metric]) * SCALE.get(metric, 1) for c in conds]
        ax.bar(conds, vals, color=[colors.get(c, "#888") for c in conds])
        ax.set_title(f"{title}\n({unit})")
        if logy:
            ax.set_yscale("log")
            ax.set_ylim(bottom=1)
        else:
            ax.set_ylim(bottom=0)
        for i, v in enumerate(vals):
            ax.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=9)
        ax.grid(axis="y", alpha=0.3, which="both")
    fig.suptitle("Scenario B — 5G SA: baseline vs degraded network conditions", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(os.path.join(STEP, "plots", "comparison.png"), dpi=130)
    fig.savefig(os.path.join(STEP, "plots", "comparison.svg"))
    print(f"wrote {os.path.join(STEP, 'comparison-table.md')} and plots/comparison.png")


if __name__ == "__main__":
    main()
