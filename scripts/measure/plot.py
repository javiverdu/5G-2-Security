#!/usr/bin/env python3
"""Scenario A — Step 3: build the comparative table and plots from summary.csv.

Input : results/step3/summary.csv   (condition,metric,run,value,unit)
Output: results/step3/comparison.csv
        results/step3/comparison-table.md
        results/step3/plots/comparison.{png,svg}
"""
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STEP3 = os.path.join(ROOT, "results", "step3")
SUMMARY = os.path.join(STEP3, "summary.csv")

CONDITIONS = ["baseline", "delay", "loss", "rate"]
METRICS = [
    "icmp_rtt_avg", "http_time_avg", "tcp_throughput",
    "udp_throughput", "udp_loss", "udp_jitter",
    "tcp_retransmissions", "tcp_retransmissions_sender",
    "http_connect_avg", "http_availability",
]
UNITS = {
    "icmp_rtt_avg": "ms", "http_time_avg": "s", "tcp_throughput": "Mbit/s",
    "udp_throughput": "Mbit/s", "udp_loss": "%", "udp_jitter": "ms",
    "tcp_retransmissions": "count", "tcp_retransmissions_sender": "count",
    "http_connect_avg": "s", "http_availability": "%",
}
SCALE = {"tcp_throughput": 1e-6, "udp_throughput": 1e-6}  # bit/s -> Mbit/s


def load():
    values = defaultdict(lambda: defaultdict(list))
    with open(SUMMARY) as f:
        for row in csv.DictReader(f):
            cond, metric = row["condition"], row["metric"]
            try:
                v = float(row["value"])
            except ValueError:
                continue
            values[cond][metric].append(v)
    return values


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def main():
    values = load()
    conds = [c for c in CONDITIONS if c in values]
    # Only emit metrics that actually have data, so optional/new metrics do not
    # appear as spurious zeros in the generated table.
    metrics = [m for m in METRICS if any(values[c][m] for c in conds)]

    # --- aggregated CSV
    os.makedirs(os.path.join(STEP3, "plots"), exist_ok=True)
    agg_csv = os.path.join(STEP3, "comparison.csv")
    with open(agg_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["condition"] + metrics)
        for c in conds:
            w.writerow([c] + [f"{mean(values[c][m]) * SCALE.get(m, 1):.4g}" for m in metrics])

    # --- markdown table
    md = os.path.join(STEP3, "comparison-table.md")
    with open(md, "w") as f:
        f.write("# Step 3 — Comparative results (mean of the repetitions)\n\n")
        f.write("| Condition | " + " | ".join(
            f"{m} ({UNITS[m]})" for m in metrics) + " |\n")
        f.write("|" + "---|" * (len(metrics) + 1) + "\n")
        for c in conds:
            cells = []
            for m in metrics:
                v = mean(values[c][m]) * SCALE.get(m, 1)
                cells.append(f"{v:.3f}")
            f.write(f"| {c} | " + " | ".join(cells) + " |\n")

    # --- plots
    colors = {"baseline": "#2c7fb8", "delay": "#f0a202", "loss": "#d7301f", "rate": "#238b45"}
    # (metric, title, unit, multiplier for display, log-scale?)
    panels = [
        ("icmp_rtt_avg", "ICMP RTT (avg)", "ms", None, False),
        ("http_time_avg", "HTTP response time (avg)", "ms", 1000.0, False),
        ("tcp_throughput", "TCP throughput (log scale)", "Mbit/s", None, True),
        ("udp_throughput", "UDP throughput", "Mbit/s", None, False),
        ("udp_loss", "UDP loss", "%", None, False),
        ("udp_jitter", "UDP jitter (avg)", "ms", None, False),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, (metric, title, unit, mult, logy) in zip(axes.flat, panels):
        vals = [mean(values[c][metric]) * SCALE.get(metric, 1) * (mult or 1) for c in conds]
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
    fig.suptitle("Scenario A — Step 3: baseline vs degraded network conditions", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    png = os.path.join(STEP3, "plots", "comparison.png")
    fig.savefig(png, dpi=130)
    fig.savefig(os.path.join(STEP3, "plots", "comparison.svg"))
    print(f"wrote {agg_csv}\n      {md}\n      {png} (+ .svg)")


if __name__ == "__main__":
    main()
