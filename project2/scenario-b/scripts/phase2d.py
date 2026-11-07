#!/usr/bin/env python3
"""Scenario B — Phase 2D: vulnerability scan and CycloneDX SBOM.

Runs inside the Jenkins container (Docker-outside-of-Docker). Trivy and Syft
are ephemeral jobs; findings are observations, never the gate decision (2E).

Targets (recorded with every result):
  * image  bkimminich/juice-shop:v20.2.0  -> vulnerabilities
  * files  project2/scenario-b             -> misconfiguration (IaC)

Environment:
  EVIDENCE_DIR        container path of the 2D run directory (required)
  EVIDENCE_HOST_DIR   host path of the same directory, for `docker -v`
  REPO_ROOT           container path of the checked-out repository
  P2_HOST_REPO        host path of the repository (for the read-only mount)
  RUN_ID               current run id
  BUILD_TAG            Jenkins build id
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TRIVY_IMAGE = "aquasec/trivy:0.75.0"
SYFT_IMAGE = "anchore/syft:v1.52.0"
TARGET_IMAGE = "bkimminich/juice-shop:v20.2.0"
TRIVY_CACHE = "scenario-b-trivy-cache"

EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", ".")).resolve()
EVIDENCE_HOST_DIR = os.environ.get("EVIDENCE_HOST_DIR", str(EVIDENCE_DIR))
REPO = Path(os.environ.get("REPO_ROOT", Path.cwd())).resolve()
HOST_REPO = os.environ.get("P2_HOST_REPO", str(REPO))
RUN_ID = os.environ.get("RUN_ID", EVIDENCE_DIR.name)
BUILD_TAG = os.environ.get("BUILD_TAG", "")

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]


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
        "phase": "2D",
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
        f"# Scenario B — Phase 2D — {component}",
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

    print(f"\n[2D] {component}: {report['decision']} — "
          f"{len(failed)} failed of {len(results)}")
    return 0 if not failed else 1


def count_severities(document: dict) -> dict[str, int]:
    counts = {severity: 0 for severity in SEVERITIES}
    for result in document.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            severity = str(vuln.get("Severity", "UNKNOWN")).upper()
            counts[severity] = counts.get(severity, 0) + 1
    return counts


def count_misconfigurations(document: dict) -> dict[str, int]:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for result in document.get("Results") or []:
        for item in result.get("Misconfigurations") or []:
            severity = str(item.get("Severity", "UNKNOWN")).upper()
            if severity in counts:
                counts[severity] += 1
    return counts


def main() -> int:
    started = utc_now()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    trivy_json = EVIDENCE_DIR / "trivy-juice-shop.json"
    trivy_log = EVIDENCE_DIR / "trivy.log"
    config_json = EVIDENCE_DIR / "trivy-config.json"
    config_log = EVIDENCE_DIR / "trivy-config.log"
    sbom = EVIDENCE_DIR / "sbom.cdx.json"
    sbom_log = EVIDENCE_DIR / "syft.log"
    for path in (trivy_json, trivy_log, config_json, config_log, sbom, sbom_log):
        path.unlink(missing_ok=True)

    results: list[dict] = []
    evidence: dict = {
        "targets": {"image": TARGET_IMAGE,
                    "filesystem": "project2/scenario-b"},
        "trivy": {"image": TRIVY_IMAGE, "version": ""},
        "syft": {"image": SYFT_IMAGE},
        "vulnerabilities": {},
        "misconfigurations": {},
        "sbom": {},
    }

    # -- 1. Trivy image vulnerability scan ----------------------------------
    cmd = [
        "docker", "run", "--rm", "--name", "scenario-b-trivy",
        "-v", f"{TRIVY_CACHE}:/root/.cache/trivy",
        "-v", f"{EVIDENCE_HOST_DIR}:/out",
        TRIVY_IMAGE, "image",
        "--scanners", "vuln",
        "--severity", ",".join(SEVERITIES),
        "--format", "json",
        "--output", "/out/trivy-juice-shop.json",
        TARGET_IMAGE,
    ]
    trivy_rc, trivy_out = run(cmd, timeout=1800)
    trivy_log.write_text(f"command: {' '.join(cmd)}\nexit_code: {trivy_rc}\n"
                         f"output:\n{trivy_out}\n")
    evidence["trivy"].update({"command": cmd, "exit_code": trivy_rc,
                              "log": trivy_log.name})
    check(results, "Trivy image scan completed without tool error",
          trivy_rc == 0, f"exit={trivy_rc}; {tail(trivy_log, 3)}")

    trivy_doc: dict = {}
    parsed = False
    if trivy_json.is_file():
        try:
            trivy_doc = json.loads(trivy_json.read_text())
            parsed = True
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[2D] Trivy JSON parse error: {exc}")
    check(results, "Trivy JSON report parses", parsed,
          f"{trivy_json.name} ({trivy_json.stat().st_size if trivy_json.is_file() else 0} bytes)")

    counts = count_severities(trivy_doc)
    has_results = bool(trivy_doc.get("Results"))
    check(results, "Trivy report contains scanned results", has_results,
          f"{len(trivy_doc.get('Results') or [])} result set(s)")
    total = sum(counts.values())
    check(results, "Trivy severity counts recorded", parsed,
          ", ".join(f"{k}={counts.get(k, 0)}" for k in SEVERITIES))
    evidence["vulnerabilities"] = {
        "total": total,
        "by_severity": counts,
        "high_or_critical": counts.get("HIGH", 0) + counts.get("CRITICAL", 0),
    }
    evidence["trivy"].update({
        "report": trivy_json.name,
        "report_sha256": sha256(trivy_json) if trivy_json.is_file() else "",
        "data_source": (trivy_doc.get("Metadata") or {}).get("RepoTags"),
    })

    # -- 2. Trivy filesystem/IaC scan ---------------------------------------
    cmd = [
        "docker", "run", "--rm", "--name", "scenario-b-trivy-config",
        "-v", f"{TRIVY_CACHE}:/root/.cache/trivy",
        "-v", f"{HOST_REPO}/project2/scenario-b:/src:ro",
        "-v", f"{EVIDENCE_HOST_DIR}:/out",
        TRIVY_IMAGE, "fs",
        "--scanners", "misconfig",
        "--format", "json",
        "--output", "/out/trivy-config.json",
        "/src",
    ]
    cfg_rc, cfg_out = run(cmd, timeout=1800)
    config_log.write_text(f"command: {' '.join(cmd)}\nexit_code: {cfg_rc}\n"
                          f"output:\n{cfg_out}\n")
    evidence["trivy"]["config_exit_code"] = cfg_rc
    check(results, "Trivy filesystem scan completed without tool error",
          cfg_rc == 0, f"exit={cfg_rc}; {tail(config_log, 3)}")
    config_doc: dict = {}
    cfg_parsed = False
    if config_json.is_file():
        try:
            config_doc = json.loads(config_json.read_text())
            cfg_parsed = True
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[2D] Trivy config JSON parse error: {exc}")
    check(results, "Trivy filesystem JSON report parses", cfg_parsed,
          f"{config_json.name} ({config_json.stat().st_size if config_json.is_file() else 0} bytes)")
    misconfigs = count_misconfigurations(config_doc)
    evidence["misconfigurations"] = {
        "total": sum(misconfigs.values()),
        "by_severity": misconfigs,
        "report": config_json.name,
    }

    # -- 3. Syft CycloneDX SBOM --------------------------------------------
    cmd = [
        "docker", "run", "--rm", "--name", "scenario-b-syft",
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        "-v", f"{EVIDENCE_HOST_DIR}:/out",
        SYFT_IMAGE, f"docker:{TARGET_IMAGE}",
        "-o", "cyclonedx-json=/out/sbom.cdx.json",
    ]
    syft_rc, syft_out = run(cmd, timeout=1800)
    sbom_log.write_text(f"command: {' '.join(cmd)}\nexit_code: {syft_rc}\n"
                        f"output:\n{syft_out}\n")
    evidence["syft"].update({"command": cmd, "exit_code": syft_rc,
                             "log": sbom_log.name})
    check(results, "Syft SBOM generation completed without tool error",
          syft_rc == 0, f"exit={syft_rc}; {tail(sbom_log, 3)}")

    sbom_doc: dict = {}
    sbom_parsed = False
    if sbom.is_file():
        try:
            sbom_doc = json.loads(sbom.read_text())
            sbom_parsed = True
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[2D] SBOM JSON parse error: {exc}")
    check(results, "CycloneDX SBOM parses", sbom_parsed,
          f"{sbom.name} ({sbom.stat().st_size if sbom.is_file() else 0} bytes)")
    components = sbom_doc.get("components") or []
    metadata_component = sbom_doc.get("metadata", {}).get("component", {}) or {}
    check(results, "SBOM is CycloneDX and lists components",
          sbom_doc.get("bomFormat") == "CycloneDX" and bool(components),
          f"bomFormat={sbom_doc.get('bomFormat')}, spec={sbom_doc.get('specVersion')}, "
          f"components={len(components)}")
    check(results, "SBOM describes the scanned Juice Shop image",
          "juice" in str(metadata_component.get("name", "")).lower()
          or any("juice" in str(c.get("name", "")).lower() for c in components[:200]),
          f"metadata.component={metadata_component.get('name', '')}")
    evidence["sbom"] = {
        "report": sbom.name,
        "report_sha256": sha256(sbom) if sbom.is_file() else "",
        "bom_format": sbom_doc.get("bomFormat", ""),
        "spec_version": sbom_doc.get("specVersion", ""),
        "components": len(components),
        "metadata_component": metadata_component.get("name", ""),
    }

    return finish("phase2d", started, results, evidence)


if __name__ == "__main__":
    sys.exit(main())
