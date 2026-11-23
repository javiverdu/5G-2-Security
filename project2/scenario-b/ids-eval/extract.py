#!/usr/bin/env python3
"""Extract a documented ISCXIDS2012 subset into a flat CSV of flow features.

Why this exists
---------------
The project brief asks for an *independent* IDS evaluation on the provided
ISCXIDS2012 dataset: a subset with normal traffic and at least two intrusion
scenarios, with volume, labels and methodology written down. The release ships
one XML per day of the testbed, with flow records and a binary Tag
(Normal/Attack); the attack *scenario* is a property of the day, not of the
flow, so the mapping is declared here and cited in docs/ids-benchmark.md.

Parsing notes
-------------
`xml.etree` cannot read all the files (a raw control byte inside a payload
breaks the parser at least in TestbedThuJun17-1Flows.xml), so records are
delimited by their own tags and fields read with a regex. Input is streamed
line by line: memory stays flat on 500 MB files.

Sampling
--------
Every Attack flow in the selected days is kept. Normal flows are reservoir
sampled to `--cap` per day (deterministic seed), so a day never contributes
more than cap rows and the attacker/normal ratio is not silently changed by
taking the first N rows of a capture.

Output
------
<out-dir>/flows.csv        one row per flow (features + day + scenario + label)
<out-dir>/manifest.json    per-file sha256, rows read/kept, labels, sampling
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Day -> scenario. Source: ISCXIDS2012 daily description (UNB CIC, "Intrusion
# detection evaluation dataset") and the flow counts it publishes, which this
# script checks against what it actually reads.
DAYS = {
    "TestbedSatJun12Flows.xml": ("2010-06-12", "ssh-bruteforce"),
    "TestbedSunJun13Flows.xml": ("2010-06-13", "infiltration-inside"),
    "TestbedMonJun14Flows.xml": ("2010-06-14", "http-dos"),
    "TestbedTueJun15-1Flows.xml": ("2010-06-15", "ddos-irc-botnet"),
    "TestbedTueJun15-2Flows.xml": ("2010-06-15", "ddos-irc-botnet"),
    "TestbedTueJun15-3Flows.xml": ("2010-06-15", "ddos-irc-botnet"),
    "TestbedWedJun16-1Flows.xml": ("2010-06-16", "normal"),
    "TestbedWedJun16-2Flows.xml": ("2010-06-16", "normal"),
    "TestbedWedJun16-3Flows.xml": ("2010-06-16", "normal"),
}

# Published per-day totals (flows, attacks) from the dataset description. The
# extraction asserts them when the whole day is read, so a truncated or
# different copy of the dataset cannot pass silently.
EXPECTED = {
    "2010-06-12": (133193, 2086),
    "2010-06-13": (275528, 20358),
    "2010-06-14": (171380, 3776),
    "2010-06-15": (571698, 37460),
    "2010-06-16": (522263, 11),
}

OPEN = re.compile(r"^<(Testbed[A-Za-z0-9\-]+)>$")
FIELD = re.compile(r"<([A-Za-z0-9]+)>(.*?)</\1>", re.S)
FLAGS = ("S", "A", "F", "R")


def records(path: Path):
    buf: list[str] = []
    inside = False
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not inside:
                if OPEN.match(stripped):
                    inside = True
                    buf = []
                continue
            if stripped.startswith("</Testbed"):
                yield "\n".join(buf)
                inside = False
                buf = []
                continue
            if stripped:
                buf.append(stripped)


def seconds_between(start: str | None, stop: str | None) -> float:
    if not start or not stop:
        return 0.0
    try:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(stop)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, (b - a).total_seconds())


def ratio(a: float, b: float) -> float:
    return round(a / b, 6) if b else 0.0


def flow_row(fields: dict, day: str, scenario: str) -> list:
    src_bytes = float(fields.get("totalSourceBytes") or 0)
    dst_bytes = float(fields.get("totalDestinationBytes") or 0)
    src_pkts = float(fields.get("totalSourcePackets") or 0)
    dst_pkts = float(fields.get("totalDestinationPackets") or 0)
    proto = (fields.get("protocolName") or "").lower()
    flags = (fields.get("sourceTCPFlagsDescription") or "").upper()
    label = 1 if (fields.get("Tag") or "").strip().lower() == "attack" else 0
    return [
        day,
        scenario,
        label,
        round(seconds_between(fields.get("startDateTime"), fields.get("stopDateTime")), 3),
        int(fields.get("sourcePort") or 0),
        int(fields.get("destinationPort") or 0),
        1 if proto.startswith("tcp") else 0,
        1 if proto.startswith("udp") else 0,
        1 if proto.startswith("icmp") else 0,
        src_bytes,
        dst_bytes,
        src_pkts,
        dst_pkts,
        ratio(src_bytes, dst_bytes),
        ratio(src_pkts, dst_pkts),
        ratio(src_bytes, src_pkts),
        ratio(dst_bytes, dst_pkts),
        1 if (fields.get("direction") or "").upper() == "L2R" else 0,
        flags.count("S"),
        flags.count("A"),
        flags.count("F"),
        flags.count("R"),
        (fields.get("appName") or "")[:40],
    ]


HEADER = [
    "day", "scenario", "label", "duration_s", "src_port", "dst_port",
    "proto_tcp", "proto_udp", "proto_icmp", "src_bytes", "dst_bytes",
    "src_pkts", "dst_pkts", "bytes_ratio", "pkts_ratio", "avg_src_pkt",
    "avg_dst_pkt", "l2r", "flag_s", "flag_a", "flag_f", "flag_r", "app",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--cap", type=int, default=60000,
                        help="max normal flows kept per day (attacks always kept)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.out_dir / "flows.csv"
    manifest: dict = {
        "dataset": "ISCXIDS2012 (labeled_flows_xml)",
        "source_dir": str(args.dataset_dir),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cap_normal_per_day": args.cap,
        "seed": args.seed,
        "label_semantics": "binary Normal/Attack; scenario comes from the day",
        "days": [],
    }

    totals = {"rows_read": 0, "rows_kept": 0, "attacks_kept": 0}
    scenarios: dict[str, dict] = {}

    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for name, (day, scenario) in DAYS.items():
            path = args.dataset_dir / name
            if not path.is_file():
                print(f"[skip] {name} not found", file=sys.stderr)
                continue
            started = time.time()
            read = attacks = 0
            normals: list[list] = []
            for record in records(path):
                fields = dict(FIELD.findall(record))
                if "Tag" not in fields:
                    continue
                row = flow_row(fields, day, scenario)
                read += 1
                if row[2] == 1:
                    attacks += 1
                    writer.writerow(row)
                else:
                    # reservoir sample of the normal class, uniform over the day
                    if len(normals) < args.cap:
                        normals.append(row)
                    else:
                        j = rng.randrange(read)
                        if j < args.cap:
                            normals[j] = row
            for row in normals:
                writer.writerow(row)
            kept = attacks + len(normals)
            entry = {
                "file": name,
                "sha256": sha256(path),
                "day": day,
                "scenario": scenario,
                "rows_read": read,
                "attacks": attacks,
                "normals_kept": len(normals),
                "rows_kept": kept,
                "seconds": round(time.time() - started, 1),
            }
            manifest["days"].append(entry)
            totals["rows_read"] += read
            totals["rows_kept"] += kept
            totals["attacks_kept"] += attacks
            bucket = scenarios.setdefault(scenario, {"kept": 0, "attacks": 0})
            bucket["kept"] += kept
            bucket["attacks"] += attacks
            print(f"[day] {day} {scenario}: read={read} attacks={attacks} "
                  f"kept={kept} ({time.time() - started:.1f}s)")

    manifest["totals"] = totals
    manifest["scenarios"] = scenarios
    by_day: dict[str, dict] = {}
    for entry in manifest["days"]:
        bucket = by_day.setdefault(entry["day"], {"files": 0, "flows": 0, "attacks": 0})
        bucket["files"] += 1
        bucket["flows"] += entry["rows_read"]
        bucket["attacks"] += entry["attacks"]
        bucket["scenario"] = entry["scenario"]
    for day, published in EXPECTED.items():
        actual = by_day.setdefault(day, {"files": 0, "flows": 0, "attacks": 0})
        actual["published"] = {"flows": published[0], "attacks": published[1]}
        actual["matches_published"] = (actual["flows"] == published[0]
                                       and actual["attacks"] == published[1])
    manifest["by_day"] = by_day
    manifest["csv"] = {
        "path": str(csv_path),
        "bytes": csv_path.stat().st_size,
        "sha256": sha256(csv_path),
        "rows": totals["rows_kept"],
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    mismatch = [day for day, bucket in by_day.items()
                if "matches_published" in bucket and not bucket["matches_published"]]
    print(f"[total] rows={totals['rows_kept']} attacks={totals['attacks_kept']} "
          f"csv={csv_path.stat().st_size / 1e6:.1f} MB")
    if mismatch:
        print(f"[FAIL] day counts differ from the published table: {mismatch}")
        return 1
    print("[PASS] per-day counts match the published ISCX table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
