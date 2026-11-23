#!/usr/bin/env python3
"""Summarise a Suricata run over an ISCXIDS2012 day capture.

The flow-level evaluation in evaluate.py answers "how well does the detector
separate labelled flows". This script answers the other half: what a signature
IDS does with the *packets* of an independent capture, without rules written
for it.

Input: eve.json produced by Suricata (see the command in
docs/ids-benchmark.md) and the day's XML, used only as ground truth for the
attack sources and the attack window.

Output: summary.json + summary.md with alerts by signature, severity and
source, and the overlap between the alerting sources and the labelled attack
sources. No alert is treated as a finding without that overlap being shown.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FIELD = re.compile(r"<([A-Za-z0-9]+)>(.*?)</\1>", re.S)
OPEN = re.compile(r"^<(Testbed[A-Za-z0-9\-]+)>$")
DOS_HINT = re.compile(r"dos|flood|brute|scan|ddos", re.I)


def xml_attacks(path: Path) -> dict:
    sources: Counter = Counter()
    windows: list[str] = []
    inside = False
    buf: list[str] = []
    total = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not inside:
                if OPEN.match(stripped):
                    inside = True
                continue
            if stripped.startswith("</Testbed"):
                fields = dict(FIELD.findall("\n".join(buf)))
                buf = []
                inside = False
                if (fields.get("Tag") or "").lower() == "attack":
                    total += 1
                    sources[fields.get("source") or "?"] += 1
                    if fields.get("startDateTime"):
                        windows.append(fields["startDateTime"])
                continue
            buf.append(stripped)
    return {
        "attack_flows": total,
        "attack_sources": sources.most_common(10),
        "window_start": min(windows) if windows else "",
        "window_end": max(windows) if windows else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eve", required=True, type=Path)
    parser.add_argument("--xml", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--ruleset", default="ET Open (suricata-update snapshot)")
    parser.add_argument("--window-start", default="",
                        help="UTC timestamp prefix of the flood window, e.g. 2010-06-14T20:30")
    parser.add_argument("--window-end", default="",
                        help="UTC timestamp prefix of the flood window end")
    args = parser.parse_args()

    by_signature: Counter = Counter()
    by_severity: Counter = Counter()
    by_src: Counter = Counter()
    dos_by_src: Counter = Counter()
    dos_by_signature: Counter = Counter()
    in_window = 0
    dos_in_window = 0
    first = last = ""
    total = 0
    dos_like = 0
    flow_events = 0
    with args.eve.open(errors="replace") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") == "flow":
                flow_events += 1
                continue
            alert = event.get("alert")
            if not alert:
                continue
            total += 1
            msg = alert.get("signature") or ""
            sig = f"{alert.get('signature_id')} {msg}"
            by_signature[sig] += 1
            by_severity[alert.get("severity", "?")] += 1
            by_src[event.get("src_ip", "?")] += 1
            stamp = event.get("timestamp", "")
            first = min(first, stamp) if first else stamp
            last = max(last, stamp) if last else stamp
            if args.window_start and args.window_start <= stamp <= args.window_end:
                in_window += 1
            if DOS_HINT.search(msg):
                dos_like += 1
                dos_by_src[event.get("src_ip", "?")] += 1
                dos_by_signature[sig] += 1
                if args.window_start and args.window_start <= stamp <= args.window_end:
                    dos_in_window += 1

    truth = xml_attacks(args.xml)
    attack_sources = {src for src, _ in truth["attack_sources"]}
    overlap = sorted(attack_sources & set(dos_by_src))

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eve": str(args.eve),
        "eve_bytes": args.eve.stat().st_size,
        "ruleset": args.ruleset,
        "alerts_total": total,
        "alerts_matching_dos_flood_brute_scan": dos_like,
        "flow_events": flow_events,
        "flood_window": {"start": args.window_start, "end": args.window_end,
                         "alerts": in_window, "dos_like_alerts": dos_in_window},
        "alert_window": {"first": first, "last": last},
        "by_severity": dict(by_severity),
        "top_signatures": by_signature.most_common(15),
        "top_alert_sources": by_src.most_common(10),
        "dos_like_by_signature": dos_by_signature.most_common(10),
        "dos_like_by_source": dos_by_src.most_common(10),
        "ground_truth": truth,
        "attack_sources_with_dos_like_alerts": overlap,
        "attack_sources_without_dos_like_alerts": sorted(attack_sources - set(dos_by_src)),
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    lines = [
        "# Signature IDS on the ISCX 14 June capture",
        "",
        f"- Suricata run: `{args.eve}` ({args.eve.stat().st_size / 1e6:.1f} MB of eve.json)",
        f"- Ruleset: {args.ruleset}",
        f"- Alerts: **{total}** total, of which **{dos_like}** carry a DoS/flood/brute/scan signature",
        f"- Flood window {args.window_start or '-'} .. {args.window_end or '-'}: "
        f"{in_window} alerts, of which **{dos_in_window}** DoS-flavoured",
        f"- Alert window: {first or 'none'} .. {last or 'none'}",
        f"- Ground truth (XML): {truth['attack_flows']} attack flows from "
        f"{len(attack_sources)} sources, window {truth['window_start']} .. {truth['window_end']}",
        f"- Attack sources with a DoS-flavoured alert: **{len(overlap)} of {len(attack_sources)}**",
        "",
        "## Top signatures",
        "",
        "| SID and message | alerts |",
        "|---|---|",
    ]
    lines += [f"| `{sig}` | {count} |" for sig, count in by_signature.most_common(10)]
    lines += ["", "## DoS-flavoured signatures", "", "| SID and message | alerts |", "|---|---|"]
    lines += [f"| `{sig}` | {count} |" for sig, count in dos_by_signature.most_common(10)] or ["| (none) | 0 |"]
    lines += ["", "## Top alert sources", "", "| source | alerts |", "|---|---|"]
    lines += [f"| `{src}` | {count} |" for src, count in by_src.most_common(10)]
    lines += ["", "## Labelled attack sources (XML)", "", "| source | attack flows |", "|---|---|"]
    lines += [f"| `{src}` | {count} |" for src, count in truth["attack_sources"]]
    (args.out_dir / "summary.md").write_text("\n".join(lines) + "\n")

    print(f"[pcap] alerts={total} dos_like={dos_like} window_alerts={in_window} "
          f"window_dos={dos_in_window} sources={len(attack_sources)} dos_sources={len(overlap)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
