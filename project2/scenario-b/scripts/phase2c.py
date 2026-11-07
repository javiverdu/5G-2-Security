#!/usr/bin/env python3
"""Scenario B — Phase 2C: fresh PCAP validation and offline IDS.

Runs inside the Jenkins container (Docker-outside-of-Docker) against the PCAP
that phase 2B wrote into the 2C run directory. It never captures traffic and
never sits inline: Suricata reads the file offline in an ephemeral container.

Environment:
  EVIDENCE_DIR        container path of the 2C run directory (required)
  EVIDENCE_HOST_DIR   host path of the same directory, for `docker -v`
  P2B_DIR             container path of the 2B run directory (cross-check)
  REPO_ROOT           container path of the checked-out repository
  P2_HOST_REPO        host path of the repository (for read-only rule mounts)
  RUN_ID               current run id (fallback: EVIDENCE_DIR.name)
  BUILD_TAG            Jenkins build id

The positive control is SID 1000001 on the controlled SQLi request. A green
result here means the rule fired, not that the target is secure.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SURICATA_IMAGE = "jasonish/suricata:8.0"
PCAP_NAME = "juice-shop-ci-sqli.pcapng"
SQLI_URI_MARK = "%27%28"
SID = "1000001"

EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", ".")).resolve()
EVIDENCE_HOST_DIR = os.environ.get("EVIDENCE_HOST_DIR", str(EVIDENCE_DIR))
REPO = Path(os.environ.get("REPO_ROOT", Path.cwd())).resolve()
HOST_REPO = os.environ.get("P2_HOST_REPO", str(REPO))
P2B_DIR = Path(os.environ.get("P2B_DIR", "")).resolve() if os.environ.get("P2B_DIR") else None
RUN_ID = os.environ.get("RUN_ID", EVIDENCE_DIR.name)
BUILD_TAG = os.environ.get("BUILD_TAG", "")

IDS = REPO / "project2/scenario-b/security/ids"


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


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    except FileNotFoundError as exc:
        return 127, str(exc)


def tail(path: Path, lines: int = 20) -> str:
    if not path.is_file():
        return ""
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


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
        "phase": "2C",
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
        f"# Scenario B — Phase 2C — {component}",
        "",
        f"- RUN_ID: `{RUN_ID}`",
        f"- Build: `{BUILD_TAG}`",
        f"- Started (UTC): {report['started_utc']}",
        f"- Finished (UTC): {report['finished_utc']}",
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

    print(f"\n[2C] {component}: {report['decision']} — "
          f"{len(failed)} failed of {len(results)}")
    return 0 if not failed else 1


def run_start_epoch() -> float:
    """Epoch of the current RUN_ID (UTC, YYYYmmddTHHMMSSZ), 0 when unknown."""
    try:
        parsed = dt.datetime.strptime(RUN_ID, "%Y%m%dT%H%M%SZ")
        return parsed.replace(tzinfo=dt.timezone.utc).timestamp()
    except ValueError:
        return 0.0


def tshark_filter(pcap: Path, display_filter: str, field: str,
                  timeout: int = 120) -> tuple[int, list[str]]:
    rc, out = run([
        "tshark", "-r", str(pcap), "-Y", display_filter,
        "-T", "fields", "-e", field,
    ], timeout=timeout)
    values = [line for line in out.splitlines() if line.strip()] if rc == 0 else []
    return rc, values


# ---------------------------------------------------------------------------
# traffic intelligence (optional context, never the gate)
# ---------------------------------------------------------------------------
def traffic_intelligence(pcap: Path) -> dict:
    rc, uris = tshark_filter(pcap, "http.request", "http.request.uri")
    _, methods = tshark_filter(pcap, "http.request", "http.request.method")
    _, hosts = tshark_filter(pcap, "http.request", "http.host")
    _, count = run(["capinfos", "-c", "-M", str(pcap)], timeout=120)
    packets = 0
    match = re.search(r"Number of packets:\s*(\d+)", count)
    if match:
        packets = int(match.group(1))
    return {
        "packets": packets,
        "http_requests": len(uris),
        "http_methods": sorted(set(methods)),
        "http_hosts": sorted(set(hosts)),
        "sample_uris": uris[:20],
        "tshark_exit": rc,
    }


def main() -> int:
    started = utc_now()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    pcap = EVIDENCE_DIR / PCAP_NAME
    suri_log = EVIDENCE_DIR / "suricata-command.log"
    eve = EVIDENCE_DIR / "eve.json"
    fast = EVIDENCE_DIR / "fast.log"
    stats = EVIDENCE_DIR / "stats.log"

    results: list[dict] = []
    evidence: dict = {
        "pcap": {"path": str(pcap), "name": pcap.name},
        "suricata": {"image": SURICATA_IMAGE, "sid": SID},
        "traffic": {},
    }

    # -- 1. the PCAP must exist and belong to this run ----------------------
    size = pcap.stat().st_size if pcap.is_file() else 0
    check(results, "2B wrote the fresh SQLi PCAP into the 2C run directory",
          size > 0, f"{pcap} ({size} bytes)")

    digest = sha256(pcap) if size else ""
    evidence["pcap"].update({"size": size, "sha256": digest,
                             "created_epoch": pcap.stat().st_mtime if size else 0})
    check(results, "PCAP is non-empty", size > 0, f"{size} bytes")

    start_epoch = run_start_epoch()
    created = pcap.stat().st_mtime if size else 0.0
    check(results, "PCAP was created during the current run",
          bool(size) and (not start_epoch or created >= start_epoch - 5),
          f"created={created:.3f}, run_start={start_epoch:.3f}")

    if P2B_DIR and (P2B_DIR / "capture.json").is_file():
        try:
            capture = json.loads((P2B_DIR / "capture.json").read_text())
            expected = capture.get("pcap", {}).get("sha256", "")
            check(results, "PCAP matches the phase 2B capture evidence",
                  bool(digest) and digest == expected,
                  f"2b={expected or 'missing'}; 2c={digest or 'missing'}")
        except (json.JSONDecodeError, OSError) as exc:
            check(results, "PCAP matches the phase 2B capture evidence", False,
                  f"cannot read capture.json: {exc}")

    # -- 2. the PCAP must parse and contain the controlled request ----------
    rc, first = tshark_filter(pcap, "frame", "frame.number") if size else (1, [])
    check(results, "tshark parses the PCAP", rc == 0 and bool(first),
          f"exit={rc}; {len(first)} packet(s)")

    rc, uris = tshark_filter(pcap, "http.request", "http.request.uri") if size else (1, [])
    search_uris = [u for u in uris if "/rest/products/search" in u]
    check(results, "HTTP request to the Juice Shop search endpoint is present",
          bool(search_uris), search_uris[:5] or "no /rest/products/search request")
    check(results, "captured request carries the controlled SQLi payload",
          any(SQLI_URI_MARK in u for u in search_uris),
          (search_uris[:5] or f"payload {SQLI_URI_MARK} not found"))

    evidence["traffic"] = traffic_intelligence(pcap) if size else {}

    # -- 3. offline Suricata over the file (never inline) -------------------
    for stale in (eve, fast, stats, suri_log):
        try:
            stale.unlink(missing_ok=True)
        except OSError as exc:
            print(f"[2C] cannot remove stale {stale.name}: {exc}")

    cmd = [
        "docker", "run", "--rm", "--name", "scenario-b-suricata",
        "-v", f"{EVIDENCE_HOST_DIR}:/evidence",
        "-v", f"{HOST_REPO}/project2/scenario-b/security/ids/suricata.yaml:"
              "/etc/suricata/suricata.yaml:ro",
        "-v", f"{HOST_REPO}/project2/scenario-b/security/ids/rules:/rules:ro",
        SURICATA_IMAGE,
        "-r", f"/evidence/{PCAP_NAME}",
        "-c", "/etc/suricata/suricata.yaml",
        "-l", "/evidence",
        "--runmode", "single",
        "-k", "none",
    ]
    suri_rc = 127
    suri_out = ""
    if size:
        run(["docker", "rm", "-f", "scenario-b-suricata"], timeout=30)
        suri_rc, suri_out = run(cmd, timeout=900)
        suri_log.write_text(f"command: {' '.join(cmd)}\nexit_code: {suri_rc}\n"
                            f"output:\n{suri_out}\n")
    evidence["suricata"].update({
        "command": cmd,
        "exit_code": suri_rc,
        "suricata_log": suri_log.name,
        "log_tail": tail(suri_log),
    })
    check(results, "offline Suricata run completed without tool error",
          size > 0 and suri_rc == 0,
          f"exit={suri_rc}; {tail(suri_log, 3)}")

    # -- 4. EVE alert for SID 1000001 (positive control) --------------------
    alerts: list[dict] = []
    parsed = False
    if eve.is_file():
        try:
            for line in eve.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event_type") == "alert":
                    alerts.append(event)
            parsed = True
        except OSError:
            parsed = False
    check(results, "Suricata wrote a parseable eve.json", parsed,
          f"{eve.name} ({eve.stat().st_size if eve.is_file() else 0} bytes)")
    check(results, f"Suricata SID {SID} alert detected (positive control)",
          any(str(a.get("alert", {}).get("signature_id")) == SID for a in alerts),
          f"alert signatures={[a.get('alert', {}).get('signature_id') for a in alerts][:10]}")

    check(results, "fast.log records the SID alert",
          fast.is_file() and SID in fast.read_text(errors="replace"),
          tail(fast, 3) or f"{fast.name} missing")
    check(results, "Suricata stats.log written",
          stats.is_file() and stats.stat().st_size > 0,
          f"{stats.name} ({stats.stat().st_size if stats.is_file() else 0} bytes)")

    evidence["suricata"].update({
        "alerts": [
            {
                "signature_id": a.get("alert", {}).get("signature_id"),
                "signature": a.get("alert", {}).get("signature"),
                "src_ip": a.get("src_ip"),
                "dest_ip": a.get("dest_ip"),
                "dest_port": a.get("dest_port"),
                "timestamp": a.get("timestamp"),
                "http_uri": a.get("http", {}).get("url"),
            }
            for a in alerts[:20]
        ],
        "alert_count": len(alerts),
    })

    return finish("phase2c", started, results, evidence)


if __name__ == "__main__":
    sys.exit(main())
