#!/usr/bin/env python3
"""Scenario B — Phase 2E: correlate the current run's evidence.

The container mounts the evidence root read-only and the 2E run directory
writable:

    -v <host>/results/scenario-b:/evidence:ro
    -v <host>/results/scenario-b/phase2e/<RUN_ID>:/out

It links independent observations by explicit attributes (RUN_ID, target,
request signature, artifact hashes) and reports a correlation decision. It
does not re-scan, re-analyze or invent evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE_ROOT = Path(os.environ.get("EVIDENCE_ROOT", "/evidence")).resolve()
OUT_DIR = Path(os.environ.get("OUT_DIR", "/out")).resolve()
RUN_ID = os.environ.get("RUN_ID", "")
SQLI_MARK = "%27%28"
SID = 1000001

PHASES = ("phase2a", "phase2b", "phase2c", "phase2d")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def parse_epoch(value: object) -> float:
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def check(results: list[dict], name: str, ok: bool, detail: str = "") -> bool:
    results.append({
        "check": name,
        "status": "PASS" if ok else "FAIL",
        "detail": str(detail)[:2000],
    })
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def inventory(phase_root: Path) -> list[dict]:
    items = []
    for path in sorted(phase_root.rglob("*")):
        if not path.is_file():
            continue
        items.append({
            "path": str(path.relative_to(EVIDENCE_ROOT)),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        })
    return items


# ---------------------------------------------------------------------------
# correlation
# ---------------------------------------------------------------------------
def main() -> int:
    started = utc_now()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    if not RUN_ID:
        print("[2E] RUN_ID is required")
        return 2

    phase_dirs = {phase: EVIDENCE_ROOT / phase / RUN_ID for phase in PHASES}
    for phase, path in phase_dirs.items():
        check(results, f"{phase} evidence directory present", path.is_dir(),
              str(path))

    # -- load the machine-readable evidence --------------------------------
    preflight = read_json(phase_dirs["phase2a"] / "preflight.json")
    phase2b = read_json(phase_dirs["phase2b"] / "phase2b.json")
    capture = read_json(phase_dirs["phase2b"] / "capture.json")
    zap_sqli = read_json(phase_dirs["phase2b"] / "zap-sqli.json")
    selenium = read_json(phase_dirs["phase2b"] / "selenium.json")
    phase2c = read_json(phase_dirs["phase2c"] / "phase2c.json")
    phase2d = read_json(phase_dirs["phase2d"] / "phase2d.json")

    documents = {
        "preflight": preflight,
        "phase2b": phase2b,
        "capture": capture,
        "selenium": selenium,
        "phase2c": phase2c,
        "phase2d": phase2d,
    }
    for name, document in documents.items():
        check(results, f"{name} JSON present and readable", bool(document),
              f"run_id={document.get('run_id', '')}" if document else "empty")

    run_ids = {name: doc.get("run_id", "") for name, doc in documents.items() if doc}
    consistent = bool(run_ids) and all(value == RUN_ID for value in run_ids.values())
    check(results, "every component reports the current RUN_ID", consistent,
          ", ".join(f"{k}={v}" for k, v in run_ids.items()))

    decisions = {
        "preflight": preflight.get("decision", ""),
        "phase2b": phase2b.get("decision", ""),
        "capture": capture.get("decision", ""),
        "selenium": selenium.get("decision", ""),
        "phase2c": phase2c.get("decision", ""),
        "phase2d": phase2d.get("decision", ""),
    }
    check(results, "all upstream phases passed", all(d == "PASS" for d in decisions.values()),
          ", ".join(f"{k}={v or 'missing'}" for k, v in decisions.items()))

    # -- targeted ZAP Alert 40018 ------------------------------------------
    targeted = capture.get("targeted_zap", {}) or {}
    plugin_ids = [str(p) for p in targeted.get("plugin_ids", [])]
    alert_40018 = bool(targeted.get("alert_40018_detected")) or "40018" in plugin_ids
    check(results, "targeted ZAP reported Alert 40018", alert_40018,
          f"plugin ids={plugin_ids}")

    # -- Suricata SID 1000001 ----------------------------------------------
    suricata = phase2c.get("suricata", {}) or {}
    alerts = suricata.get("alerts", []) or []
    sid_hits = [a for a in alerts if str(a.get("signature_id")) == str(SID)]
    check(results, f"Suricata reported SID {SID}", bool(sid_hits),
          f"{len(sid_hits)} alert(s)")

    # -- the PCAP is the same artifact in 2B and 2C -------------------------
    pcap_2b = (capture.get("pcap", {}) or {})
    pcap_2c = (phase2c.get("pcap", {}) or {})
    same_pcap = (bool(pcap_2b.get("sha256"))
                 and pcap_2b.get("sha256") == pcap_2c.get("sha256"))
    check(results, "2B and 2C reference the same PCAP hash", same_pcap,
          f"2b={pcap_2b.get('sha256', '')}; 2c={pcap_2c.get('sha256', '')}")

    sqli_url = capture.get("sqli_url", "")
    check(results, "captured request matches the controlled SQLi signature",
          SQLI_MARK in sqli_url, sqli_url)

    # -- time window --------------------------------------------------------
    window_start = []
    window_end = []
    for name in ("preflight", "phase2b", "capture", "selenium", "phase2c", "phase2d"):
        document = documents[name]
        if document.get("started_utc"):
            window_start.append(parse_epoch(document["started_utc"]))
        if document.get("finished_utc"):
            window_end.append(parse_epoch(document["finished_utc"]))
    start_epoch = min([v for v in window_start if v] or [0.0])
    end_epoch = max([v for v in window_end if v] or [0.0])
    check(results, "component timestamps form a current run window",
          start_epoch > 0 and end_epoch > start_epoch,
          f"start={start_epoch:.0f}, end={end_epoch:.0f}, "
          f"duration={max(end_epoch - start_epoch, 0):.0f}s")

    # -- artifact inventory -------------------------------------------------
    artifacts: list[dict] = []
    for phase, path in phase_dirs.items():
        if path.is_dir():
            artifacts.extend(inventory(path))
    check(results, "security evidence set contains artifacts", len(artifacts) > 10,
          f"{len(artifacts)} file(s)")

    failed = [r for r in results if r["status"] == "FAIL"]
    decision = "PASS" if not failed else "FAIL"

    vulnerabilities = phase2d.get("vulnerabilities", {}) or {}
    sbom = phase2d.get("sbom", {}) or {}
    report = {
        "phase": "2E",
        "component": "correlation",
        "run_id": RUN_ID,
        "started_utc": started,
        "finished_utc": utc_now(),
        "decision": decision,
        "checks_total": len(results),
        "checks_failed": len(failed),
        "checks": results,
        "chain": {
            "target": "http://10.20.10.20:3000",
            "request_signature": sqli_url,
            "application_observation": {
                "tool": "OWASP ZAP",
                "alert": "40018 SQL Injection",
                "detected": alert_40018,
                "report": "phase2b/zap-sqli.json",
                "report_plugin_ids": plugin_ids,
            },
            "network_evidence": {
                "tool": "tshark + Suricata",
                "pcap": pcap_2c.get("name", ""),
                "pcap_sha256": pcap_2c.get("sha256", ""),
                "pcap_size": pcap_2c.get("size", 0),
                "sid": SID,
                "sid_alert_count": len(sid_hits),
                "report": "phase2c/eve.json",
            },
            "software_artifacts": {
                "trivy_high_or_critical": vulnerabilities.get("high_or_critical", 0),
                "sbom_components": sbom.get("components", 0),
                "sbom_format": sbom.get("bom_format", ""),
            },
        },
        "windows": {
            "start_epoch": round(start_epoch, 3),
            "end_epoch": round(end_epoch, 3),
            "duration_seconds": round(max(end_epoch - start_epoch, 0), 2),
        },
        "artifacts": artifacts,
        "decisions": decisions,
    }
    (OUT_DIR / "security-event-correlation.json").write_text(
        json.dumps(report, indent=2) + "\n")

    lines = [
        "# Scenario B — Security Event Correlation",
        "",
        f"- RUN_ID: `{RUN_ID}`",
        f"- Decision: **{decision}** ({len(failed)} failed of {len(results)})",
        f"- Window (UTC epoch): {report['windows']['start_epoch']} .. "
        f"{report['windows']['end_epoch']} "
        f"({report['windows']['duration_seconds']}s)",
        "",
        "## Evidence chain",
        "",
        "| Layer | Observation | Link |",
        "|---|---|---|",
        f"| Application | ZAP Alert 40018 detected={alert_40018} | {sqli_url} |",
        f"| Network | {pcap_2c.get('name', 'PCAP')} sha256 "
        f"`{(pcap_2c.get('sha256') or '')[:16]}…` | Suricata SID {SID} "
        f"x{len(sid_hits)} |",
        f"| Software | Trivy HIGH/CRITICAL="
        f"{vulnerabilities.get('high_or_critical', 0)} | CycloneDX components="
        f"{sbom.get('components', 0)} |",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for item in results:
        detail = item["detail"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {item['check']} | {item['status']} | {detail} |")
    lines += ["", "## Artifacts", "", "| Artifact | Bytes | SHA-256 |", "|---|---|---|"]
    for item in artifacts:
        lines.append(f"| `{item['path']}` | {item['size']} | `{item['sha256']}` |")
    lines.append("")
    (OUT_DIR / "security-event-correlation.md").write_text("\n".join(lines))

    print(f"\n[2E] correlation: {decision} — {len(failed)} failed of {len(results)}")
    return 0 if decision == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
