#!/usr/bin/env python3
"""Scenario B — Phase 2B: application security testing.

Runs inside the Jenkins container (Docker-outside-of-Docker) and writes the
phase 2B evidence into ``EVIDENCE_DIR``.

Subcommands (the Jenkinsfile calls them in this order):

  zap-baseline    OWASP ZAP baseline against Juice Shop: HTML, Markdown, JSON
  selenium        Chrome session through Selenium Grid: login, session,
                  cookies, localStorage and an authenticated screenshot
  capture-sqli    START CAPTURE -> controlled SQLi -> targeted ZAP -> STOP
                  CAPTURE, then verify the fresh PCAP and Alert 40018
  summarize       combine the three component results into phase2b.json/.md

Environment:
  EVIDENCE_DIR        container path of the 2B run directory (required)
  EVIDENCE_HOST_DIR   host path of the same directory, for `docker -v`
  PCAP_DIR             container path of the 2C run directory (capture-sqli)
  PCAP_HOST_DIR        host path of the same directory (capture-sqli)
  REPO_ROOT           container path of the checked-out repository
  P2_HOST_REPO        host path of the repository (unused here, kept for parity)
  RUN_ID               current run id (fallback: EVIDENCE_DIR.name)
  BUILD_TAG            Jenkins build id

The positive controls are deliberate:
  * ZAP Alert 40018 detected -> PASS for the targeted test.
  * The capture window is armed before the SQLi traffic is generated.
Nothing here decides whether the target is secure; that is the 2E gate.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

JUICE = "http://10.20.10.20:3000"
SELENIUM = "http://10.20.10.30:4444"
ZAP_IMAGE = "ghcr.io/zaproxy/zaproxy:stable"
CAPTURE_IMAGE = "telecom-lab-capture:1.0"
NETWORK = "security-net"

JUICE_USER = "admin@juice-sh.op"
JUICE_PASSWORD = "admin123"
SQLI_PATH = "/rest/products/search?q=%27%28"

EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", ".")).resolve()
EVIDENCE_HOST_DIR = os.environ.get("EVIDENCE_HOST_DIR", str(EVIDENCE_DIR))
REPO = Path(os.environ.get("REPO_ROOT", Path.cwd())).resolve()
HOST_REPO = os.environ.get("P2_HOST_REPO", str(REPO))
RUN_ID = os.environ.get("RUN_ID", EVIDENCE_DIR.name)
BUILD_TAG = os.environ.get("BUILD_TAG", "")


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


def run_logged(cmd: list[str], log_path: Path, timeout: int,
               container_name: str | None = None) -> tuple[int, str, str]:
    """Run a foreground Docker job, redirecting its output to a log file.

    Returns (exit_code, started_utc, finished_utc). On timeout the named
    container is removed so a retry does not collide with it.
    """
    started = utc_now()
    rc = 124
    with log_path.open("w") as log:
        try:
            p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                               timeout=timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = 124
            if container_name:
                run(["docker", "rm", "-f", container_name], timeout=30)
    return rc, started, utc_now()


def tail(path: Path, lines: int = 20) -> str:
    if not path.is_file():
        return ""
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def docker_rm(name: str) -> None:
    run(["docker", "rm", "-f", name], timeout=30)


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
        "phase": "2B",
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
        f"# Scenario B — Phase 2B — {component}",
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

    print(f"\n[2B] {component}: {report['decision']} — "
          f"{len(failed)} failed of {len(results)}")
    return 0 if not failed else 1


# ---------------------------------------------------------------------------
# ZAP baseline (2B.1)
# ---------------------------------------------------------------------------
def count_alerts(obj: object) -> int:
    """Count alert records in the different ZAP JSON layouts."""
    count = 0
    if isinstance(obj, dict):
        keys = {k.lower() for k in obj}
        if "pluginid" in keys and ("alert" in keys or "name" in keys):
            return 1
        for value in obj.values():
            count += count_alerts(value)
    elif isinstance(obj, list):
        for value in obj:
            count += count_alerts(value)
    return count


def zap_baseline() -> int:
    started = utc_now()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    html = EVIDENCE_DIR / "zap-baseline.html"
    # Keep the ZAP Markdown report separate from the component summary
    # written later as zap-baseline.md.
    markdown = EVIDENCE_DIR / "zap-baseline-report.md"
    report = EVIDENCE_DIR / "zap-baseline-report.json"
    log = EVIDENCE_DIR / "zap-baseline.log"
    for path in (html, markdown, report, log):
        path.unlink(missing_ok=True)

    docker_rm("scenario-b-zap-baseline")
    cmd = [
        "docker", "run", "--rm", "--name", "scenario-b-zap-baseline",
        "--network", NETWORK,
        "-v", f"{EVIDENCE_HOST_DIR}:/zap/wrk:rw",
        ZAP_IMAGE, "zap-baseline.py",
        "-t", JUICE,
        # zap-baseline.py resolves these names relative to /zap/wrk; an
        # absolute path is prefixed again and the report is never written.
        "-r", "zap-baseline.html",
        "-w", "zap-baseline-report.md",
        "-J", "zap-baseline-report.json",
        "-I",
    ]
    rc, command_started, command_finished = run_logged(
        cmd, log, timeout=1800, container_name="scenario-b-zap-baseline")

    results: list[dict] = []
    # zap-baseline.py: 0 = success, 1 = FAIL alert, 2 = WARN only,
    # 3 = any other failure. Findings are observations, not gate failures,
    # so 0/1/2 pass; only 3 (or a timeout) is a tool error.
    check(results, "ZAP baseline command completed without tool error",
          rc in (0, 1, 2), f"exit={rc}; findings are not a build failure")
    for label, path in (("HTML", html), ("Markdown", markdown),
                        ("JSON", report)):
        size = path.stat().st_size if path.is_file() else 0
        check(results, f"ZAP baseline {label} report is non-empty",
              size > 0, f"{path.name} ({size} bytes)")

    alert_count = 0
    parsed = False
    if report.is_file():
        try:
            alert_count = count_alerts(json.loads(report.read_text()))
            parsed = True
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[2B] baseline JSON parse error: {exc}")
    check(results, "ZAP baseline JSON report parses", parsed,
          f"{alert_count} alert record(s)")

    extra = {
        "target": JUICE,
        "command": cmd,
        "command_started_utc": command_started,
        "command_finished_utc": command_finished,
        "exit_code": rc,
        "log_tail": tail(log),
        "reports": {
            "html": html.name,
            "markdown": markdown.name,
            "json": report.name,
        },
        "alert_records": alert_count,
    }
    return finish("zap-baseline", started, results, extra)


# ---------------------------------------------------------------------------
# Selenium runtime + authentication (2B.2)
# ---------------------------------------------------------------------------
class WebDriverError(RuntimeError):
    pass


class WebDriver:
    def __init__(self, base: str = SELENIUM) -> None:
        self.base = base.rstrip("/") + "/wd/hub"
        self.session_id = ""
        self.capabilities: dict = {}

    def _request(self, method: str, path: str, payload: dict | None = None,
                 timeout: int = 60) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.base + path, data=data,
                                         method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise WebDriverError(
                f"{method} {path} HTTP {exc.code}: {body[:500]}") from exc
        except Exception as exc:  # noqa: BLE001 - reported as a failed check
            raise WebDriverError(f"{method} {path}: {exc}") from exc
        try:
            return json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise WebDriverError(f"{method} {path}: invalid JSON: {body[:300]}") from exc

    def _create_session(self) -> None:
        response = self._request("POST", "/session", {
            "capabilities": {"alwaysMatch": {
                "browserName": "chrome",
                "goog:chromeOptions": {"args": [
                    "--headless",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1366,900",
                ]},
            }},
        }, timeout=120)
        value = response.get("value", response)
        self.session_id = value.get("sessionId") or response.get("sessionId", "")
        self.capabilities = value.get("capabilities", {}) or {}
        if not self.session_id:
            raise WebDriverError(f"session not created: {response}")

    def start(self) -> None:
        try:
            self._create_session()
        except WebDriverError as exc:
            # Selenium 4 serves both /wd/hub and / depending on the image.
            if "HTTP 404" in str(exc) and self.base.endswith("/wd/hub"):
                self.base = self.base[: -len("/wd/hub")]
                self._create_session()
            else:
                raise

    def _path(self, suffix: str) -> str:
        return f"/session/{self.session_id}{suffix}"

    def navigate(self, url: str) -> None:
        self._request("POST", self._path("/url"), {"url": url}, timeout=90)

    def current_url(self) -> str:
        return str(self._request("GET", self._path("/url")).get("value", ""))

    def find(self, css: str) -> str:
        value = self._request("POST", self._path("/element"), {
            "using": "css selector", "value": css,
        }, timeout=30).get("value", {})
        element = (value.get("element-6066-11e4-a52e-4f735466cecf")
                   or value.get("ELEMENT"))
        if not element:
            raise WebDriverError(f"element not found: {css}")
        return element

    def wait_find(self, css: str, timeout: int = 60) -> str:
        deadline = time.time() + timeout
        last = ""
        while time.time() < deadline:
            try:
                return self.find(css)
            except WebDriverError as exc:
                last = str(exc)
                time.sleep(0.5)
        raise WebDriverError(f"element not visible after {timeout}s: {css} ({last})")

    def clear(self, element: str) -> None:
        self._request("POST", self._path(f"/element/{element}/clear"), {})

    def send_keys(self, element: str, text: str) -> None:
        self._request("POST", self._path(f"/element/{element}/value"),
                      {"text": text})

    def click(self, element: str) -> None:
        try:
            self._request("POST", self._path(f"/element/{element}/click"), {})
        except WebDriverError as exc:
            # Juice Shop overlays (cookie/ welcome banners) can cover the
            # Angular button even after it is rendered. A synthetic click on
            # the element itself bypasses hit-testing and still runs the
            # framework handler; only fall back for interception errors.
            text = str(exc)
            if "click intercepted" not in text and "not clickable" not in text:
                raise
            print(f"[2B] native click intercepted, using element click: {text[:200]}")
            self.execute(
                "const e = arguments[0];"
                "e.scrollIntoView({block: 'center', inline: 'center'});"
                "e.click(); return true;",
                [{"element-6066-11e4-a52e-4f735466cecf": element}])

    def execute(self, script: str, args: list | None = None) -> object:
        return self._request("POST", self._path("/execute/sync"), {
            "script": script, "args": args or [],
        }).get("value")

    def cookies(self) -> list[dict]:
        return list(self._request("GET", self._path("/cookie")).get("value", []))

    def screenshot(self) -> bytes:
        value = self._request("GET", self._path("/screenshot"), timeout=60).get("value", "")
        if not value:
            return b""
        return base64.b64decode(value)

    def quit(self) -> None:
        if not self.session_id:
            return
        try:
            self._request("DELETE", self._path(""), timeout=30)
        except WebDriverError:
            pass
        self.session_id = ""


def jwt_payload(token: str) -> dict:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(part).decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:  # noqa: BLE001 - malformed token is reported by checks
        return {}


def selenium_runtime() -> int:
    started = utc_now()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    screenshot_path = EVIDENCE_DIR / "selenium-authenticated.png"
    log = EVIDENCE_DIR / "selenium.log"

    results: list[dict] = []
    evidence: dict = {
        "target": JUICE,
        "grid": SELENIUM,
        "credentials": {"user": JUICE_USER},
        "cookies": [],
        "local_storage": {},
        "authenticated_url": "",
        "authenticated_route": "",
        "screenshot": screenshot_path.name,
        "session": {},
    }

    driver = WebDriver()
    failure = ""
    try:
        driver.start()
        evidence["session"] = {
            "id": driver.session_id,
            "browserName": driver.capabilities.get("browserName", ""),
            "browserVersion": driver.capabilities.get("browserVersion", ""),
            "platformName": driver.capabilities.get("platformName", ""),
        }
        check(results, "Selenium browser session created",
              bool(driver.session_id), driver.session_id)

        driver.navigate(f"{JUICE}/#/login")
        email = driver.wait_find("input#email", timeout=90)
        password = driver.wait_find("input#password", timeout=30)
        check(results, "Juice Shop login page rendered", True,
              "input#email and input#password found")

        dismissed = driver.execute(
            "const b = [...document.querySelectorAll('button')]"
            ".find(x => /me want it/i.test(x.textContent || ''));"
            "if (b) { b.click(); return true; } return false;")
        if dismissed:
            print("[2B] dismissed the cookie banner")
            time.sleep(1)

        driver.clear(email)
        driver.send_keys(email, JUICE_USER)
        driver.clear(password)
        driver.send_keys(password, JUICE_PASSWORD)
        login = driver.wait_find("button#loginButton", timeout=30)
        driver.click(login)
        check(results, "login form submitted", True, JUICE_USER)

        deadline = time.time() + 90
        token = ""
        while time.time() < deadline:
            token = str(driver.execute(
                "return window.localStorage.getItem('token') || '';") or "")
            if token:
                break
            time.sleep(1)

        payload = jwt_payload(token)
        email_in_token = str(
            payload.get("email")
            or (payload.get("data") or {}).get("email")
            or ""
        )
        user_id = (
            (payload.get("data") or {}).get("id")
            or payload.get("id")
            or payload.get("userId")
        )
        check(results, "authentication accepted (JWT token present)",
              bool(token), f"token length {len(token)}")
        check(results, "JWT identifies the controlled lab account",
              email_in_token == JUICE_USER,
              f"email={email_in_token or 'missing'}")

        # The Angular router may update the route just after the token appears.
        route = str(driver.execute("return location.hash || '';") or "")
        current = driver.current_url()
        deadline = time.time() + 30
        while time.time() < deadline:
            route = str(driver.execute("return location.hash || '';") or "")
            current = driver.current_url()
            if "/login" not in current and "#/login" not in route:
                break
            time.sleep(1)
        check(results, "authenticated browser left the login route",
              "/login" not in current and "#/login" not in route,
              f"url={current}, route={route or 'empty'}")

        cookies = driver.cookies()
        cookie_evidence = []
        for cookie in cookies:
            cookie_evidence.append({
                "name": cookie.get("name", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", ""),
                "secure": cookie.get("secure", False),
                "httpOnly": cookie.get("httpOnly", False),
                "sameSite": cookie.get("sameSite", ""),
                "value_length": len(str(cookie.get("value", ""))),
            })
        evidence["cookies"] = cookie_evidence
        evidence["document_cookie_length"] = len(str(
            driver.execute("return document.cookie || '';") or ""))
        check(results, "browser cookie state captured", True,
              f"{len(cookies)} cookie(s), document.cookie length "
              f"{evidence['document_cookie_length']}")

        keys = driver.execute("return Object.keys(localStorage);") or []
        keys = [str(k) for k in keys]
        evidence["local_storage"] = {
            "keys": keys,
            "token_present": bool(token),
            "token_payload": {
                "email": email_in_token,
                "userId": user_id,
            },
        }
        check(results, "browser storage contains the authentication token",
              "token" in keys, f"keys={keys}")

        # Move to the account page for an authenticated screenshot.
        try:
            driver.navigate(f"{JUICE}/#/account")
            time.sleep(2)
        except WebDriverError as exc:
            print(f"[2B] account navigation warning: {exc}")
        evidence["authenticated_url"] = driver.current_url()
        evidence["authenticated_route"] = str(
            driver.execute("return location.hash || '';") or "")

        png = driver.screenshot()
        if png:
            screenshot_path.write_bytes(png)
        size = screenshot_path.stat().st_size if screenshot_path.is_file() else 0
        check(results, "authenticated screenshot saved", size > 1000,
              f"{screenshot_path.name} ({size} bytes)")

    except Exception as exc:  # noqa: BLE001 - always emit JSON evidence
        failure = str(exc)
        print(f"[2B] Selenium failure: {failure}")
        check(results, "Selenium runtime completed", False, failure)
        if driver.session_id:
            try:
                png = driver.screenshot()
                if png:
                    screenshot_path.write_bytes(png)
            except Exception:  # noqa: BLE001
                pass
    finally:
        driver.quit()

    evidence["error"] = failure
    return finish("selenium", started, results, evidence)


# ---------------------------------------------------------------------------
# Fresh capture + controlled SQLi + targeted ZAP (2B.3)
# ---------------------------------------------------------------------------
def plugin_ids(obj: object) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in {"pluginid", "plugin_id"}:
                found.add(str(value))
            else:
                found |= plugin_ids(value)
    elif isinstance(obj, list):
        for value in obj:
            found |= plugin_ids(value)
    return found


def alert_names(obj: object) -> list[str]:
    names: list[str] = []
    if isinstance(obj, dict):
        if "alert" in obj and isinstance(obj["alert"], str):
            names.append(obj["alert"])
        for value in obj.values():
            names.extend(alert_names(value))
    elif isinstance(obj, list):
        for value in obj:
            names.extend(alert_names(value))
    return names


def capture_sqli() -> int:
    started = utc_now()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    pcap_dir = Path(os.environ.get("PCAP_DIR", str(EVIDENCE_DIR))).resolve()
    pcap_host_dir = os.environ.get("PCAP_HOST_DIR", str(pcap_dir))
    pcap_dir.mkdir(parents=True, exist_ok=True)
    pcap = pcap_dir / "juice-shop-ci-sqli.pcapng"
    pcap.unlink(missing_ok=True)

    plan_src = REPO / "project2/scenario-b/security/zap/plan.yaml"
    plan_copy = EVIDENCE_DIR / "plan.yaml"
    shutil.copy2(plan_src, plan_copy)

    capture_log = EVIDENCE_DIR / "capture.log"
    sqli_headers = EVIDENCE_DIR / "sqli-headers.txt"
    sqli_body = EVIDENCE_DIR / "sqli-response.txt"
    sqli_request = EVIDENCE_DIR / "sqli-request.txt"
    zap_log = EVIDENCE_DIR / "zap-sqli.log"
    zap_report = EVIDENCE_DIR / "zap-sqli.json"

    results: list[dict] = []
    evidence: dict = {
        "target": JUICE,
        "sqli_url": JUICE + SQLI_PATH,
        "plan": plan_copy.name,
        "pcap": str(pcap),
        "capture_window": {},
        "sqli": {},
        "targeted_zap": {},
    }

    docker_rm("scenario-b-capture")
    capture_cmd = [
        "docker", "run", "-d", "--name", "scenario-b-capture",
        "--network", "container:juice-shop",
        "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW",
        "-v", f"{pcap_host_dir}:/captures",
        CAPTURE_IMAGE, "/captures/juice-shop-ci-sqli.pcapng", "eth0",
    ]
    window_start_epoch = time.time()
    rc, out = run(capture_cmd, timeout=60)
    check(results, "capture container started", rc == 0, out or "docker run failed")
    time.sleep(2)
    running_rc, running = run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "scenario-b-capture"],
        timeout=30)
    check(results, "capture window is armed before SQLi traffic",
          running_rc == 0 and running.strip() == "true",
          f"running={running.strip() or 'unknown'}")

    sqli_rc = 1
    sqli_status = ""
    zap_rc = 124
    try:
        # Controlled network positive control, generated while capture is active.
        sqli_url = JUICE + SQLI_PATH
        sqli_rc, sqli_out = run([
            "curl", "-sS", "-o", str(sqli_body), "-D", str(sqli_headers),
            "-w", "%{http_code} %{size_download} %{time_total}",
            sqli_url,
        ], timeout=60)
        sqli_status = sqli_out.split()[0] if sqli_out else ""
        sqli_request.write_text(
            f"timestamp_utc: {utc_now()}\n"
            f"method: GET\n"
            f"url: {sqli_url}\n"
            f"curl_exit: {sqli_rc}\n"
            f"http_code size_download time_total: {sqli_out}\n"
        )
        check(results, "controlled SQLi request completed", sqli_rc == 0,
              f"HTTP {sqli_status or 'none'}, curl exit {sqli_rc}")

        # Targeted ZAP test: spider -> requestor -> activeScan 40018.
        docker_rm("scenario-b-zap-sqli")
        zap_cmd = [
            "docker", "run", "--rm", "--name", "scenario-b-zap-sqli",
            "--network", NETWORK,
            "-v", f"{EVIDENCE_HOST_DIR}:/zap/wrk:rw",
            ZAP_IMAGE, "zap.sh", "-cmd", "-autorun", "/zap/wrk/plan.yaml",
        ]
        zap_rc, zap_started, zap_finished = run_logged(
            zap_cmd, zap_log, timeout=1800, container_name="scenario-b-zap-sqli")
        evidence["targeted_zap"] = {
            "command": zap_cmd,
            "exit_code": zap_rc,
            "started_utc": zap_started,
            "finished_utc": zap_finished,
            "log_tail": tail(zap_log),
        }
        check(results, "targeted ZAP command completed",
              zap_rc in (0, 1), f"exit={zap_rc}")

        ids: set[str] = set()
        names: list[str] = []
        parsed = False
        if zap_report.is_file():
            try:
                document = json.loads(zap_report.read_text())
                ids = plugin_ids(document)
                names = alert_names(document)
                parsed = True
            except (json.JSONDecodeError, OSError) as exc:
                print(f"[2B] targeted ZAP JSON parse error: {exc}")
        check(results, "targeted ZAP JSON report parses", parsed,
              f"{zap_report.name} ({zap_report.stat().st_size if zap_report.is_file() else 0} bytes)")
        detected = "40018" in ids or any("sql injection" in n.lower()
                                         for n in names)
        check(results, "ZAP Alert 40018 (SQL Injection) detected", detected,
              f"plugin ids={sorted(ids)}; alerts={names[:5]}")
        evidence["targeted_zap"].update({
            "report": zap_report.name,
            "plugin_ids": sorted(ids),
            "alert_names": names[:20],
            "alert_40018_detected": detected,
        })
    finally:
        # Stop the capture only after the complete controlled activity.
        run(["docker", "stop", "-t", "15", "scenario-b-capture"], timeout=60)
        run(["docker", "rm", "-f", "scenario-b-capture"], timeout=30)
        window_end_epoch = time.time()

    capture_log.write_text(
        f"started_utc: {started}\n"
        f"window_start_epoch: {window_start_epoch:.3f}\n"
        f"window_end_epoch: {window_end_epoch:.3f}\n"
        f"pcap: {pcap}\n"
    )

    size = pcap.stat().st_size if pcap.is_file() else 0
    check(results, "fresh SQLi PCAP created", size > 0,
          f"{pcap.name} ({size} bytes)")
    check(results, "capture window covers the controlled activity",
          window_end_epoch > window_start_epoch,
          f"{window_end_epoch - window_start_epoch:.2f}s")

    created_epoch = pcap.stat().st_mtime if pcap.is_file() else 0.0
    check(results, "PCAP creation time falls inside the current window",
          bool(size) and (window_start_epoch - 5) <= created_epoch
          <= (window_end_epoch + 5),
          f"created={created_epoch:.3f}, window={window_start_epoch:.3f}..{window_end_epoch:.3f}")

    evidence["capture_window"] = {
        "started_utc": started,
        "window_start_epoch": round(window_start_epoch, 3),
        "window_end_epoch": round(window_end_epoch, 3),
        "duration_seconds": round(window_end_epoch - window_start_epoch, 2),
    }
    evidence["sqli"] = {
        "curl_exit": sqli_rc,
        "http_code": sqli_status,
        "headers": sqli_headers.name,
        "body": sqli_body.name,
        "request": sqli_request.name,
    }
    evidence["pcap"] = {
        "path": str(pcap),
        "name": pcap.name,
        "size": size,
        "sha256": sha256(pcap) if size else "",
        "created_epoch": round(created_epoch, 3),
    }
    return finish("capture", started, results, evidence)


# ---------------------------------------------------------------------------
# summary (2B.4)
# ---------------------------------------------------------------------------
def summarize() -> int:
    components = ["zap-baseline", "selenium", "capture"]
    loaded = []
    missing = []
    for name in components:
        path = EVIDENCE_DIR / f"{name}.json"
        if path.is_file():
            try:
                loaded.append(json.loads(path.read_text()))
            except json.JSONDecodeError:
                missing.append(f"{name}.json invalid")
        else:
            missing.append(f"{name}.json missing")

    failed = [c for c in loaded if c.get("decision") != "PASS"]
    decision = "PASS" if not missing and not failed else "FAIL"
    total = sum(c.get("checks_total", 0) for c in loaded)
    failed_checks = sum(c.get("checks_failed", 0) for c in loaded)
    summary = {
        "phase": "2B",
        "run_id": RUN_ID,
        "build_tag": BUILD_TAG,
        "finished_utc": utc_now(),
        "decision": decision,
        "checks_total": total,
        "checks_failed": failed_checks,
        "components": [
            {
                "component": c.get("component", ""),
                "decision": c.get("decision", ""),
                "checks_total": c.get("checks_total", 0),
                "checks_failed": c.get("checks_failed", 0),
            }
            for c in loaded
        ],
        "missing": missing,
    }
    write_json(EVIDENCE_DIR / "phase2b.json", summary)

    lines = [
        "# Scenario B — Phase 2B summary",
        "",
        f"- RUN_ID: `{RUN_ID}`",
        f"- Build: `{BUILD_TAG}`",
        f"- Decision: **{decision}** ({failed_checks} failed of {total})",
        "",
        "| Component | Decision | Checks | Failed |",
        "|---|---|---|---|",
    ]
    for c in summary["components"]:
        lines.append(f"| {c['component']} | {c['decision']} | "
                     f"{c['checks_total']} | {c['checks_failed']} |")
    if missing:
        lines += ["", "## Missing", ""] + [f"- {m}" for m in missing]
    lines.append("")
    (EVIDENCE_DIR / "phase2b.md").write_text("\n".join(lines))

    print(f"\n[2B] summary: {decision} — {failed_checks} failed of {total}")
    return 0 if decision == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Scenario B phase 2B")
    parser.add_argument("command",
                        choices=["zap-baseline", "selenium", "capture-sqli",
                                 "summarize"])
    args = parser.parse_args()
    return {
        "zap-baseline": zap_baseline,
        "selenium": selenium_runtime,
        "capture-sqli": capture_sqli,
        "summarize": summarize,
    }[args.command]()


if __name__ == "__main__":
    sys.exit(main())
