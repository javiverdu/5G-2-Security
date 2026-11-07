#!/usr/bin/env python3
"""Scenario B — Phase 2E: correlation, evidence archive and Security Gate.

Subcommands (the Jenkinsfile calls them in this order):

  correlate   run telecom-lab-correlation:1.0 over the current evidence set
  archive     pack phase2a..phase2e/<RUN_ID> into a single tar.gz with hash
  gate        apply REPORT_ONLY or ENFORCE and write gate.json/.md

Environment:
  EVIDENCE_DIR        container path of the 2E run directory (required)
  EVIDENCE_HOST_DIR   host path of the same directory, for `docker -v`
  EVIDENCE_ROOT       container path of results/scenario-b (default /evidence/scenario-b)
  EVIDENCE_HOST_ROOT  host path of the same directory, for `docker -v`
  REPO_ROOT           container path of the checked-out repository
  RUN_ID               current run id
  BUILD_TAG            Jenkins build id
  SECURITY_GATE_MODE   REPORT_ONLY (default) or ENFORCE
  GATE_MAX_HIGH_CRITICAL  tolerated HIGH+CRITICAL count (default 0)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

CORRELATION_IMAGE = "telecom-lab-correlation:1.0"

EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", ".")).resolve()
EVIDENCE_HOST_DIR = os.environ.get("EVIDENCE_HOST_DIR", str(EVIDENCE_DIR))
EVIDENCE_ROOT = Path(os.environ.get("EVIDENCE_ROOT", "/evidence/scenario-b")).resolve()
EVIDENCE_HOST_ROOT = Path(
    os.environ.get("EVIDENCE_HOST_ROOT",
                   str(EVIDENCE_ROOT))).resolve()
REPO = Path(os.environ.get("REPO_ROOT", Path.cwd())).resolve()
RUN_ID = os.environ.get("RUN_ID", EVIDENCE_DIR.name)
BUILD_TAG = os.environ.get("BUILD_TAG", "")
GATE_MODE = os.environ.get("SECURITY_GATE_MODE", "REPORT_ONLY").upper()
GATE_MAX_HIGH_CRITICAL = int(os.environ.get("GATE_MAX_HIGH_CRITICAL", "0"))

PHASES = ("phase2a", "phase2b", "phase2c", "phase2d", "phase2e")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(cmd: list[str], timeout: int = 900) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    except FileNotFoundError as exc:
        return 127, str(exc)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def check(results: list[dict], name: str, ok: bool, detail: str = "") -> bool:
    results.append({
        "check": name,
        "status": "PASS" if ok else "FAIL",
        "detail": str(detail)[:2000],
    })
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def finish(component: str, started: str, results: list[dict],
           extra: dict | None = None) -> int:
    failed = [r for r in results if r["status"] == "FAIL"]
    report = {
        "phase": "2E",
        "component": component,
        "run_id": RUN_ID,
        "build_tag": BUILD_TAG,
        "started_utc": started,
        "finished_utc": utc_now(),
        "decision": "PASS" if not failed else "FAIL",
        "checks_total": len(results),
        "checks_failed": len(failed),
        "checks": results,
    }
    if extra:
        report.update(extra)
    write_json(EVIDENCE_DIR / f"{component}.json", report)

    lines = [
        f"# Scenario B — Phase 2E — {component}",
        "",
        f"- RUN_ID: `{RUN_ID}`",
        f"- Build: `{BUILD_TAG}`",
        f"- Decision: **{report['decision']}** "
        f"({report['checks_failed']} failed of {report['checks_total']})",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for item in results:
        detail = item["detail"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {item['check']} | {item['status']} | {detail} |")
    lines.append("")
    (EVIDENCE_DIR / f"{component}.md").write_text("\n".join(lines))

    print(f"\n[2E] {component}: {report['decision']} — "
          f"{len(failed)} failed of {len(results)}")
    return 0 if not failed else 1


# ---------------------------------------------------------------------------
# correlate
# ---------------------------------------------------------------------------
def image_present(name: str) -> bool:
    rc, _ = run(["docker", "image", "inspect", name], timeout=60)
    return rc == 0


def correlate() -> int:
    started = utc_now()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    evidence: dict = {"image": CORRELATION_IMAGE}

    if not image_present(CORRELATION_IMAGE):
        build_dir = REPO / "project2/scenario-b/correlation"
        rc, out = run(["docker", "build", "-t", CORRELATION_IMAGE,
                       str(build_dir)], timeout=900)
        check(results, "correlation image built", rc == 0,
              out.splitlines()[-1] if out else "")
    check(results, "correlation image available", image_present(CORRELATION_IMAGE),
          CORRELATION_IMAGE)

    cmd = [
        "docker", "run", "--rm", "--name", "scenario-b-correlation",
        "-e", f"RUN_ID={RUN_ID}",
        "-e", "EVIDENCE_ROOT=/evidence",
        "-e", "OUT_DIR=/out",
        "-v", f"{EVIDENCE_HOST_ROOT}:/evidence:ro",
        "-v", f"{EVIDENCE_HOST_DIR}:/out",
        CORRELATION_IMAGE,
    ]
    rc, out = run(cmd, timeout=900)
    log = EVIDENCE_DIR / "correlation.log"
    log.write_text(f"command: {' '.join(cmd)}\nexit_code: {rc}\noutput:\n{out}\n")
    evidence.update({"command": cmd, "exit_code": rc, "log": log.name})
    check(results, "correlation container completed", rc == 0,
          f"exit={rc}; {out.splitlines()[-1] if out else ''}")

    report_path = EVIDENCE_DIR / "security-event-correlation.json"
    report = read_json(report_path)
    check(results, "security-event-correlation.json present and readable",
          bool(report),
          f"{report_path.name} ({report_path.stat().st_size if report_path.is_file() else 0} bytes)")
    check(results, "correlation decision is PASS",
          report.get("decision") == "PASS",
          f"failed={report.get('checks_failed', '?')} of "
          f"{report.get('checks_total', '?')}")
    check(results, "correlation report describes this run",
          report.get("run_id") == RUN_ID, f"run_id={report.get('run_id', '')}")

    evidence["correlation"] = {
        "report": report_path.name,
        "sha256": sha256(report_path) if report_path.is_file() else "",
        "decision": report.get("decision", ""),
        "checks_total": report.get("checks_total", 0),
        "checks_failed": report.get("checks_failed", 0),
        "chain": report.get("chain", {}),
    }
    return finish("correlate", started, results, evidence)


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------
def archive() -> int:
    started = utc_now()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    archive_path = EVIDENCE_DIR / "scenario-b-evidence.tar.gz"
    archive_path.unlink(missing_ok=True)

    results: list[dict] = []
    members: list[str] = []
    with tarfile.open(archive_path, "w:gz") as tar:
        for phase in PHASES:
            phase_dir = EVIDENCE_ROOT / phase / RUN_ID
            if not phase_dir.is_dir():
                check(results, f"{phase} directory archived", False, str(phase_dir))
                continue
            added = 0
            for path in sorted(phase_dir.rglob("*")):
                if not path.is_file():
                    continue
                if path == archive_path:
                    continue
                arcname = Path(phase) / RUN_ID / path.relative_to(phase_dir)
                tar.add(path, arcname=str(arcname))
                members.append(str(arcname))
                added += 1
            check(results, f"{phase} directory archived", added > 0,
                  f"{added} file(s)")

    size = archive_path.stat().st_size if archive_path.is_file() else 0
    check(results, "evidence archive is non-empty", size > 0, f"{size} bytes")
    digest = sha256(archive_path) if size else ""
    with tarfile.open(archive_path, "r:gz") as tar:
        names = tar.getnames()
    check(results, "archive is readable and matches the member list",
          len(names) == len(members),
          f"{len(names)} member(s)")

    evidence = {
        "archive": archive_path.name,
        "size": size,
        "sha256": digest,
        "root": str(EVIDENCE_ROOT),
        "members": len(members),
        "phases": list(PHASES),
    }
    return finish("archive", started, results, evidence)


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------
def gate() -> int:
    started = utc_now()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    correlation = read_json(EVIDENCE_DIR / "security-event-correlation.json")
    phase2d = read_json(EVIDENCE_ROOT / "phase2d" / RUN_ID / "phase2d.json")
    phase2c = read_json(EVIDENCE_ROOT / "phase2c" / RUN_ID / "phase2c.json")
    capture = read_json(EVIDENCE_ROOT / "phase2b" / RUN_ID / "capture.json")

    results: list[dict] = []
    mode = GATE_MODE if GATE_MODE in {"REPORT_ONLY", "ENFORCE"} else "REPORT_ONLY"
    check(results, "Security Gate mode is valid", GATE_MODE in {"REPORT_ONLY", "ENFORCE"},
          f"requested={GATE_MODE or 'empty'}, effective={mode}")

    # Process integrity first: a broken evidence chain is never a security pass.
    check(results, "correlation evidence is complete and consistent",
          correlation.get("decision") == "PASS",
          f"decision={correlation.get('decision', 'missing')}")
    targeted = capture.get("targeted_zap", {}) or {}
    check(results, "ZAP Alert 40018 positive control is PASS",
          bool(targeted.get("alert_40018_detected")),
          f"plugin ids={targeted.get('plugin_ids', [])}")
    sid_hits = [a for a in (phase2c.get("suricata", {}) or {}).get("alerts", [])
                if str(a.get("signature_id")) == "1000001"]
    check(results, "Suricata SID 1000001 positive control is PASS",
          bool(sid_hits), f"{len(sid_hits)} alert(s)")
    check(results, "Trivy scan completed and reported",
          phase2d.get("decision") == "PASS",
          f"decision={phase2d.get('decision', 'missing')}")

    vulnerabilities = phase2d.get("vulnerabilities", {}) or {}
    high_or_critical = int(vulnerabilities.get("high_or_critical", 0))
    by_severity = vulnerabilities.get("by_severity", {}) or {}
    violated = high_or_critical > GATE_MAX_HIGH_CRITICAL

    if not all(r["status"] == "PASS" for r in results):
        gate_decision = "FAIL"
        build_result = "fail"
        reason = "evidence chain incomplete; gate cannot produce a security decision"
    elif mode == "ENFORCE" and violated:
        gate_decision = "FAIL"
        build_result = "fail"
        reason = (f"ENFORCE: HIGH/CRITICAL={high_or_critical} exceeds "
                  f"threshold {GATE_MAX_HIGH_CRITICAL}")
    else:
        gate_decision = "PASS"
        build_result = "continue"
        if violated:
            reason = (f"REPORT_ONLY: HIGH/CRITICAL={high_or_critical} recorded; "
                      f"threshold {GATE_MAX_HIGH_CRITICAL} not enforced")
        else:
            reason = (f"HIGH/CRITICAL={high_or_critical} within threshold "
                      f"{GATE_MAX_HIGH_CRITICAL}")

    report = {
        "phase": "2E",
        "component": "gate",
        "run_id": RUN_ID,
        "build_tag": BUILD_TAG,
        "started_utc": started,
        "finished_utc": utc_now(),
        "mode": mode,
        "decision": gate_decision,
        "build_result": build_result,
        "reason": reason,
        "tool_result": {
            "correlation": correlation.get("decision", "missing"),
            "trivy": phase2d.get("decision", "missing"),
            "suricata": phase2c.get("decision", "missing"),
            "zap_targeted": capture.get("decision", "missing"),
        },
        "security_finding": {
            "target": "bkimminich/juice-shop:v20.2.0",
            "high_or_critical": high_or_critical,
            "by_severity": by_severity,
            "threshold": GATE_MAX_HIGH_CRITICAL,
            "condition_violated": violated,
        },
        "positive_controls": {
            "zap_alert_40018": bool(targeted.get("alert_40018_detected")),
            "suricata_sid_1000001": bool(sid_hits),
        },
        "checks_total": len(results),
        "checks_failed": sum(1 for r in results if r["status"] == "FAIL"),
        "checks": results,
    }
    write_json(EVIDENCE_DIR / "gate.json", report)

    lines = [
        "# Scenario B — Security Gate",
        "",
        f"- RUN_ID: `{RUN_ID}`",
        f"- Mode: **{mode}**",
        f"- Tool result: correlation={report['tool_result']['correlation']}, "
        f"trivy={report['tool_result']['trivy']}",
        f"- Security finding: HIGH/CRITICAL={high_or_critical} "
        f"(threshold {GATE_MAX_HIGH_CRITICAL})",
        f"- Gate decision: **{gate_decision}** — {reason}",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for item in results:
        detail = item["detail"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {item['check']} | {item['status']} | {detail} |")
    lines.append("")
    (EVIDENCE_DIR / "gate.md").write_text("\n".join(lines))

    print(f"\n[2E] gate: {gate_decision} ({mode}) — {reason}")
    return 0 if gate_decision == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Scenario B phase 2E")
    parser.add_argument("command", choices=["correlate", "archive", "gate"])
    args = parser.parse_args()
    return {
        "correlate": correlate,
        "archive": archive,
        "gate": gate,
    }[args.command]()


if __name__ == "__main__":
    sys.exit(main())
