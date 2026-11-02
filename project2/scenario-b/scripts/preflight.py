#!/usr/bin/env python3
"""Scenario B — Phase 2A Preflight.

Runs inside the Jenkins container (Docker-outside-of-Docker). Produces
``preflight.json`` and ``preflight.md`` in the current run's evidence directory
and exits non-zero when any hard check fails.

Nothing here starts the security tests: it only proves the environment can run
them and that the Scenario A 1E baseline is still green.

Environment:
  EVIDENCE_DIR        container path of this run's directory (required)
  EVIDENCE_HOST_DIR   host path of the same directory, for `docker -v`
  P2_HOST_REPO        host path of the repository (for read-only mounts)
  REPO_ROOT           container path of the checked-out repository
  BUILD_TAG            Jenkins build id
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

JUICE = "http://10.20.10.20:3000"
SELENIUM = "http://10.20.10.30:4444"
JENKINS = "http://10.20.10.40:8080"

EVIDENCE_DIR = Path(os.environ["EVIDENCE_DIR"]).resolve()
EVIDENCE_HOST_DIR = os.environ.get("EVIDENCE_HOST_DIR", str(EVIDENCE_DIR))
REPO = Path(os.environ.get("REPO_ROOT", Path.cwd())).resolve()
HOST_REPO = os.environ.get("P2_HOST_REPO", str(REPO))

results: list[dict] = []
versions: dict = {}


def record(name: str, ok: bool, detail: str = "", hard: bool = True) -> bool:
    results.append(
        {
            "check": name,
            "status": "PASS" if ok else ("FAIL" if hard else "WARN"),
            "detail": detail.strip()[:2000],
            "hard": hard,
        }
    )
    print(f"[{'PASS' if ok else ('FAIL' if hard else 'WARN')}] {name}: {detail}")
    return ok


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired as exc:
        return 124, f"timeout after {timeout}s: {exc}"
    except FileNotFoundError as exc:
        return 127, str(exc)


def http(url: str, method: str = "GET", body: dict | None = None,
         timeout: int = 10) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - reported as a failed check
        return 0, str(exc)


def docker_image_tag(ref: str) -> bool:
    rc, _ = run(["docker", "image", "inspect", ref], timeout=30)
    return rc == 0


def ensure_image(ref: str, timeout: int = 900) -> bool:
    if docker_image_tag(ref):
        return True
    print(f"[pull] {ref}")
    rc, out = run(["docker", "pull", ref], timeout=timeout)
    if rc != 0:
        print(out[-800:])
    return rc == 0


def plugin_versions() -> dict[str, str]:
    base = Path("/var/jenkins_home/plugins")
    found: dict[str, str] = {}
    if not base.is_dir():
        return found
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        manifest = entry / "META-INF" / "MANIFEST.MF"
        if not manifest.is_file():
            continue
        text = manifest.read_text(errors="replace").replace("\r\n", "\n")
        # Manifest continuation lines start with a space.
        text = re.sub(r"\n ", "", text)
        short = re.search(r"^Short-Name:\s*(.+)$", text, re.M)
        version = re.search(r"^Implementation-Version:\s*(.+)$", text, re.M)
        if short and version:
            found[short.group(1).strip()] = version.group(1).strip()
    return found


def main() -> int:
    started = datetime.now(timezone.utc)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    # -- 1. evidence hygiene -------------------------------------------------
    # The 1E stage writes its log here before Preflight runs; it is the only
    # allowed entry at this point.
    allowed = {"baseline-1e.txt"}
    existing = [p.name for p in EVIDENCE_DIR.iterdir() if p.name not in allowed] \
        if EVIDENCE_DIR.exists() else []
    record("evidence directory is run-specific and free of stale artifacts",
           not existing, f"{EVIDENCE_DIR} (unexpected: {existing or 'none'})")

    # -- 2. Jenkins execution environment ------------------------------------
    record("Jenkins build id present", bool(os.environ.get("BUILD_TAG")),
           os.environ.get("BUILD_TAG", ""))
    probe = EVIDENCE_DIR / ".write-probe"
    try:
        probe.write_text("ok")
        probe.unlink()
        writable = True
    except OSError as exc:
        writable = False
        print(exc)
    record("evidence directory writable", writable, str(EVIDENCE_DIR))

    plugins = plugin_versions()
    versions["jenkins_plugins"] = plugins
    manifest_path = REPO / "project2/scenario-b/RELEASE-MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    expected_plugins = manifest.get("jenkins_plugins", {})
    missing = [p for p in expected_plugins if p not in plugins]
    mismatched = [
        f"{p}: manifest {expected_plugins[p]}, installed {plugins.get(p)}"
        for p in expected_plugins
        if p in plugins and plugins[p] != expected_plugins[p]
    ]
    record("required Jenkins plugins installed",
           not missing, ", ".join(missing) or f"{len(plugins)} plugins present")
    record("plugin versions match the Release Manifest",
           not mismatched, "; ".join(mismatched) or "all pinned versions match")

    # -- 3. container runtime ------------------------------------------------
    rc, out = run(["docker", "version", "--format", "{{.Server.Version}}"])
    versions["docker_server"] = out if rc == 0 else "unreachable"
    record("Docker reachable from Jenkins", rc == 0, out or "docker version failed")

    rc, out = run(["docker", "network", "inspect", "-f", "{{.Name}}", "security-net"])
    record("security-net exists", rc == 0 and out == "security-net", out)
    rc, out = run(["docker", "network", "inspect", "-f", "{{.Name}}", "dn-net"])
    record("Scenario A dn-net present", rc == 0, out or "dn-net missing")

    rc, out = run(["docker", "run", "--rm", "--network", "security-net",
                   "alpine:3.22", "getent", "hosts", "juice-shop"], timeout=60)
    record("container DNS resolves juice-shop on security-net", rc == 0, out)

    # -- 4. Juice Shop -------------------------------------------------------
    code, body = http(f"{JUICE}/rest/admin/application-version")
    try:
        juice_version = json.loads(body).get("version", "")
    except json.JSONDecodeError:
        juice_version = ""
    versions["juice_shop"] = juice_version
    record("Juice Shop reachable", code == 200, f"HTTP {code}")
    record("target is the controlled Juice Shop v20.2.0",
           juice_version == "20.2.0",
           f"reported version {juice_version or 'unknown'}")

    # -- 5. Selenium ---------------------------------------------------------
    code, body = http(f"{SELENIUM}/wd/hub/status", timeout=15)
    ready = False
    try:
        ready = bool(json.loads(body)["value"].get("ready"))
    except (json.JSONDecodeError, KeyError):
        pass
    record("Selenium Grid reachable and ready", code == 200 and ready,
           f"HTTP {code}, ready={ready}")

    session = http(
        f"{SELENIUM}/wd/hub/session",
        "POST",
        {"capabilities": {"alwaysMatch": {
            "browserName": "chrome",
            "goog:chromeOptions": {"args": ["--headless=new", "--no-sandbox",
                                            "--disable-dev-shm-usage"]},
        }}},
        timeout=90,
    )
    sid = ""
    try:
        sid = json.loads(session[1])["value"]["sessionId"]
    except (json.JSONDecodeError, KeyError):
        pass
    record("a browser session can be created", bool(sid),
           f"session {sid or 'not created'}")
    if sid:
        http(f"{SELENIUM}/wd/hub/session/{sid}", "DELETE", timeout=30)

    # -- 6. ZAP readiness ----------------------------------------------------
    zap = "ghcr.io/zaproxy/zaproxy:stable"
    have_zap = ensure_image(zap)
    record("ZAP image available", have_zap, zap)
    if have_zap:
        rc, out = run(["docker", "run", "--rm", "--entrypoint", "zap.sh", zap,
                       "-version"], timeout=180)
        versions["zap"] = out.splitlines()[-1] if out else ""
        record("ZAP executable reports a version", rc == 0 and "ZAP" in out,
               out.splitlines()[-1] if out else "no output")
    plan = REPO / "project2/scenario-b/security/zap/plan.yaml"
    record("targeted ZAP plan.yaml present", plan.is_file(), str(plan))
    if plan.is_file():
        import yaml  # provided by python3-yaml in the Jenkins image
        try:
            doc = yaml.safe_load(plan.read_text())
            jobs = [j.get("type") for j in doc.get("jobs", [])]
            record("plan.yaml is valid YAML with requestor and activeScan jobs",
                   "requestor" in jobs and "activeScan" in jobs, f"jobs={jobs}")
        except Exception as exc:  # noqa: BLE001
            record("plan.yaml parses", False, str(exc))

    # -- 7. capture readiness ------------------------------------------------
    capture = "telecom-lab-capture:1.0"
    record("capture image available", docker_image_tag(capture), capture)
    pcap = EVIDENCE_DIR / "preflight-capture.pcapng"
    if docker_image_tag(capture):
        run(["docker", "rm", "-f", "preflight-capture"], timeout=30)
        rc, out = run([
            "docker", "run", "-d", "--name", "preflight-capture",
            "--network", "container:juice-shop",
            "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW",
            "-v", f"{EVIDENCE_HOST_DIR}:/captures",
            capture, "/captures/preflight-capture.pcapng", "eth0",
        ], timeout=60)
        time.sleep(2)
        http(f"{JUICE}/rest/products/search?q=apple", timeout=10)
        time.sleep(2)
        run(["docker", "stop", "preflight-capture"], timeout=30)
        run(["docker", "rm", "-f", "preflight-capture"], timeout=30)
        time.sleep(1)
        size = pcap.stat().st_size if pcap.exists() else 0
        record("capture container wrote a non-empty PCAP", size > 0, f"{size} bytes")
        if size > 0:
            rc, out = run(["tshark", "-r", str(pcap), "-Y",
                           "http.request", "-T", "fields", "-e",
                           "http.request.uri"], timeout=60)
            versions["tshark"] = run(["tshark", "--version"])[1].splitlines()[0]
            record("capture point observed the Juice Shop HTTP request",
                   rc == 0 and "/rest/products/search" in out,
                   out[:400])

    # -- 8. Suricata readiness ----------------------------------------------
    suri = "jasonish/suricata:8.0"
    have_suri = ensure_image(suri)
    record("Suricata image available", have_suri, suri)
    ids = REPO / "project2/scenario-b/security/ids"
    rules = ids / "rules/scenario-b-local.rules"
    cfg = ids / "suricata.yaml"
    record("Suricata configuration present", cfg.is_file(), str(cfg))
    record("local rule file present", rules.is_file(), str(rules))
    if rules.is_file():
        record("SID 1000001 defined in the local rules",
               "sid:1000001" in rules.read_text(), "sid:1000001")
    if have_suri and cfg.is_file() and rules.is_file():
        rc, out = run([
            "docker", "run", "--rm",
            "-v", f"{HOST_REPO}/project2/scenario-b/security/ids:/etc/suricata:ro",
            "-v", f"{HOST_REPO}/project2/scenario-b/security/ids/rules:/rules:ro",
            suri, "-T", "-c", "/etc/suricata/suricata.yaml", "-v",
        ], timeout=180)
        loaded = re.search(r"(\d+) rules successfully loaded", out)
        record("Suricata accepts the configuration (suricata -T)", rc == 0,
               out.splitlines()[-3:] if out else "no output")
        record("SID 1000001 is loaded by the active rule set",
               bool(loaded) and int(loaded.group(1)) >= 1,
               loaded.group(0) if loaded else "rule count not reported")

    # -- 9. analysis tools ---------------------------------------------------
    for tool, cmd in {"jq": ["jq", "--version"], "tshark": ["tshark", "--version"],
                      "python3": ["python3", "--version"]}.items():
        rc, out = run(cmd)
        versions[tool] = out.splitlines()[0] if out else ""
        record(f"{tool} available", rc == 0, versions[tool])

    scripts = [
        REPO / "project2/scenario-a/scripts/verify-phase1.sh",
        REPO / "project2/scenario-b/scripts/preflight.py",
    ]
    record("required scripts present and executable",
           all(p.is_file() and os.access(p, os.X_OK) for p in scripts),
           ", ".join(p.name for p in scripts))

    # -- 10. software-security tooling --------------------------------------
    trivy, syft = "aquasec/trivy:0.75.0", "anchore/syft:v1.52.0"
    for ref in (trivy, syft):
        record(f"{ref} available", ensure_image(ref), ref)
    if docker_image_tag(trivy):
        rc, out = run(["docker", "run", "--rm", trivy, "--version"], timeout=120)
        versions["trivy"] = out.splitlines()[0] if out else ""
        record("Trivy reports a version", rc == 0, versions["trivy"])
        rc, out = run([
            "docker", "run", "--rm", "-v", "scenario-b-trivy-cache:/root/.cache/trivy",
            trivy, "image", "--download-db-only", "--quiet",
        ], timeout=900)
        record("Trivy vulnerability database available", rc == 0,
               out[-400:] if rc else "database ready")
    if docker_image_tag(syft):
        rc, out = run(["docker", "run", "--rm", syft, "version"], timeout=120)
        versions["syft"] = out.splitlines()[0] if out else ""
        record("Syft reports a version", rc == 0, versions["syft"])

    # -- 11. record versions -------------------------------------------------
    _, docker_cli = run(["docker", "--version"])
    versions["docker_cli"] = docker_cli
    versions["images"] = {}
    for ref in ("bkimminich/juice-shop:v20.2.0", "telecom-lab-selenium:1.0",
                "telecom-lab-jenkins:2.580.1-jdk21", "telecom-lab-capture:1.0",
                zap, suri, trivy, syft):
        rc, out = run(["docker", "image", "inspect", "-f", "{{.Id}}", ref], timeout=30)
        versions["images"][ref] = out if rc == 0 else "missing"

    finished = datetime.now(timezone.utc)
    failed = [r for r in results if r["status"] == "FAIL"]
    report = {
        "phase": "2A",
        "run_id": EVIDENCE_DIR.name,
        "build_tag": os.environ.get("BUILD_TAG", ""),
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": finished.isoformat(timespec="seconds"),
        "decision": "PASS" if not failed else "FAIL",
        "checks_total": len(results),
        "checks_failed": len(failed),
        "versions": versions,
        "checks": results,
    }
    (EVIDENCE_DIR / "preflight.json").write_text(json.dumps(report, indent=2))

    lines = [
        "# Scenario B — Phase 2A Preflight",
        "",
        f"- RUN_ID: `{report['run_id']}`",
        f"- Build: `{report['build_tag']}`",
        f"- Started (UTC): {report['started_utc']}",
        f"- Finished (UTC): {report['finished_utc']}",
        f"- Decision: **{report['decision']}** ({report['checks_failed']} failed "
        f"of {report['checks_total']})",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for r in results:
        detail = r["detail"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r['check']} | {r['status']} | {detail} |")
    lines += ["", "## Versions", "", "```json",
              json.dumps(versions, indent=2, sort_keys=True), "```", ""]
    (EVIDENCE_DIR / "preflight.md").write_text("\n".join(lines))

    print(f"\n[preflight] {report['decision']} — {len(failed)} failed of {len(results)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
