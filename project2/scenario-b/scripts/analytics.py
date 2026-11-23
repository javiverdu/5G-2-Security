#!/usr/bin/env python3
"""Scenario B — Phase 2C-Advanced: bounded traffic intelligence.

Supplementary analytics over the *current run's* PCAP. It never captures, never
scans and never decides the build: it turns the validated capture into features,
learns the "normal browsing" profile of the run, scores every HTTP request
against that profile and classifies requests into behavioural clusters. The
outputs are correlated in 2E as supporting evidence only.

Why this shape:

  * Pure Python standard library + tshark. Adding numpy/scikit-learn to the
    pinned Jenkins image would change a release-manifest component for an
    optional stage; a deterministic k-means and a robust z-score are enough for
    a bounded demonstration and stay reproducible.
  * Baseline = the behavioural cluster that matches plain content retrieval
    (no query string, no request body, GET). That is an explicit, documented
    prior, not something the attack traffic can influence.
  * Anomaly score = modified z-score (Iglewicz-Hoaglin) against the baseline
    medians, with a variance floor so that a feature that is constant in the
    baseline (for example "request body length") can still separate traffic.
  * The label used to *evaluate* the output is never used as a feature.

Exit codes: 0 when the artifacts were produced (whatever the model says), 1 only
on a tool/infrastructure failure (no PCAP, tshark unavailable). A detector that
flags nothing is an *observation* recorded in analytics.json, not a build
failure: the brief requires analytics to be supplementary evidence.

Environment:
  EVIDENCE_DIR   container path of the 2C run directory (PCAP + eve.json)
  RUN_ID         current run id (fallback: directory name)
  BUILD_TAG      Jenkins build id
  ANALYTICS_K    cluster count for k-means (default 3)
  ANALYTICS_Z    modified z-score threshold (default 3.5)
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PCAP_NAME = "juice-shop-ci-sqli.pcapng"
SID = "1000001"
SQLI_MARK = "%27%28"
ENDPOINT_UNDER_TEST = "/rest/products/search"

EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", ".")).resolve()
RUN_ID = os.environ.get("RUN_ID", EVIDENCE_DIR.name)
BUILD_TAG = os.environ.get("BUILD_TAG", "")
K = max(2, int(os.environ.get("ANALYTICS_K", "3")))
Z_THRESHOLD = float(os.environ.get("ANALYTICS_Z", "3.5"))
MAX_REQUESTS = 20000
RANDOM_SEED = 42

FEATURE_NAMES = [
    "uri_len",
    "path_depth",
    "query_len",
    "pct_count",
    "pct_ratio",
    "digit_ratio",
    "special_ratio",
    "token_count",
    "q_entropy",
    "is_post",
    "body_len",
]

REQUEST_FIELDS = [
    "frame.number",
    "frame.time_relative",
    "ip.src",
    "tcp.srcport",
    "ip.dst",
    "tcp.dstport",
    "tcp.stream",
    "http.request.method",
    "http.request.uri",
    "http.host",
    "http.content_length",
]

FRAME_FIELDS = [
    "frame.time_relative",
    "frame.len",
    "ip.src",
    "tcp.srcport",
    "ip.dst",
    "tcp.dstport",
    "tcp.stream",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    except FileNotFoundError as exc:
        return 127, str(exc)


def check(results: list[dict], name: str, ok: bool, detail: str = "") -> bool:
    results.append({
        "check": name,
        "status": "PASS" if ok else "FAIL",
        "detail": str(detail)[:2000],
    })
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def tshark_rows(pcap: Path, fields: list[str], display_filter: str | None) -> list[dict]:
    cmd = ["tshark", "-r", str(pcap), "-T", "fields",
           "-E", "separator=\t", "-E", "occurrence=f", "-E", "aggregator=,"]
    if display_filter:
        cmd += ["-Y", display_filter]
    for name in fields:
        cmd += ["-e", name]
    rc, out = run(cmd, timeout=600)
    if rc != 0:
        return []
    rows: list[dict] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        parts += [""] * (len(fields) - len(parts))
        rows.append(dict(zip(fields, parts)))
    return rows


def entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text)
    total = len(text)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def mad(values: list[float], center: float) -> float:
    return median([abs(v - center) for v in values])


# ---------------------------------------------------------------------------
# feature extraction
# ---------------------------------------------------------------------------
def request_features(uri: str, method: str, body_len: int) -> dict:
    path, _, query = uri.partition("?")
    pct = query.count("%")
    alnum = sum(ch.isalnum() for ch in query)
    special = max(len(query) - alnum - pct, 0)
    return {
        "uri_len": float(len(uri)),
        "path_depth": float(path.count("/")),
        "query_len": float(len(query)),
        "pct_count": float(pct),
        "pct_ratio": round(pct * 3 / len(query), 3) if query else 0.0,
        "digit_ratio": round(sum(ch.isdigit() for ch in query) / len(query), 3) if query else 0.0,
        "special_ratio": round(special / len(query), 3) if query else 0.0,
        "token_count": float(len([t for t in re.split(r"[&=+]", query) if t])) if query else 0.0,
        "q_entropy": round(entropy(query), 3),
        "is_post": 1.0 if method == "POST" else 0.0,
        "body_len": float(body_len),
    }


def build_requests(pcap: Path) -> list[dict]:
    rows = tshark_rows(pcap, REQUEST_FIELDS, "http.request")[:MAX_REQUESTS]
    requests: list[dict] = []
    for index, row in enumerate(rows):
        method = (row["http.request.method"] or "").upper()
        uri = row["http.request.uri"] or ""
        body = row["http.content_length"]
        body_len = int(body) if body.isdigit() else 0
        features = request_features(uri, method, body_len)
        requests.append({
            "index": index,
            "frame": int(row["frame.number"]) if row["frame.number"].isdigit() else 0,
            "time": float(row["frame.time_relative"] or 0.0),
            "src": row["ip.src"],
            "sport": row["tcp.srcport"],
            "dst": row["ip.dst"],
            "dport": row["tcp.dstport"],
            "stream": row["tcp.stream"],
            "method": method,
            "uri": uri,
            "host": row["http.host"],
            "features": features,
        })
    return requests


def build_flows(pcap: Path) -> list[dict]:
    rows = tshark_rows(pcap, FRAME_FIELDS, "tcp")
    flows: dict[str, dict] = {}
    for row in rows:
        stream = row["tcp.stream"]
        if not stream:
            continue
        try:
            when = float(row["frame.time_relative"])
            size = int(row["frame.len"])
        except ValueError:
            continue
        flow = flows.setdefault(stream, {
            "stream": stream,
            "src": row["ip.src"],
            "sport": row["tcp.srcport"],
            "dst": row["ip.dst"],
            "dport": row["tcp.dstport"],
            "packets": 0,
            "bytes": 0,
            "start": when,
            "end": when,
            "requests": 0,
            "methods": set(),
        })
        flow["packets"] += 1
        flow["bytes"] += size
        flow["start"] = min(flow["start"], when)
        flow["end"] = max(flow["end"], when)
    return list(flows.values())


# ---------------------------------------------------------------------------
# unsupervised model
# ---------------------------------------------------------------------------
def standardize(vectors: list[list[float]]) -> tuple[list[list[float]], list[float], list[float], list[int]]:
    n = len(vectors)
    d = len(vectors[0])
    means = [sum(v[j] for v in vectors) / n for j in range(d)]
    scales = []
    keep = []
    for j in range(d):
        var = sum((v[j] - means[j]) ** 2 for v in vectors) / n
        std = math.sqrt(var)
        scales.append(std)
        if std > 1e-9:
            keep.append(j)
    scaled = [[(v[j] - means[j]) / scales[j] for j in keep] for v in vectors]
    return scaled, means, scales, keep


def sqdist(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def kmeans(points: list[list[float]], k: int) -> tuple[list[int], list[list[float]], float]:
    """Deterministic k-means++ with a fixed seed (reproducible across runs)."""
    rng = random.Random(RANDOM_SEED)
    n = len(points)
    k = min(k, n)
    centroids = [list(points[rng.randrange(n)])]
    while len(centroids) < k:
        dists = [min(sqdist(p, c) for c in centroids) for p in points]
        total = sum(dists)
        if total <= 0:
            break
        target = rng.random() * total
        acc = 0.0
        chosen = n - 1
        for i, dist in enumerate(dists):
            acc += dist
            if acc >= target:
                chosen = i
                break
        centroids.append(list(points[chosen]))

    labels = [-1] * n
    inertia = 0.0
    for _ in range(300):
        changed = False
        for i, point in enumerate(points):
            best = min(range(len(centroids)), key=lambda c: sqdist(point, centroids[c]))
            if labels[i] != best:
                labels[i] = best
                changed = True
        groups: dict[int, list[list[float]]] = defaultdict(list)
        for point, label in zip(points, labels):
            groups[label].append(point)
        new_centroids = []
        for c in range(len(centroids)):
            members = groups.get(c, [])
            if members:
                new_centroids.append([sum(m[j] for m in members) / len(members)
                                      for j in range(len(members[0]))])
            else:
                far = max(range(n), key=lambda i: sqdist(points[i], centroids[c]))
                new_centroids.append(list(points[far]))
        inertia = sum(sqdist(p, centroids[labels[i]]) for i, p in enumerate(points))
        centroids = new_centroids
        if not changed:
            break
    return labels, centroids, inertia


def cluster_name(profile: dict) -> str:
    """Semantic name from the centroid profile only (never from URIs)."""
    if profile["is_post"] >= 0.5:
        return "credential_submission"
    if profile["query_len"] >= 1.0 and profile["pct_ratio"] >= 0.2:
        return "encoded_query_api"
    if profile["query_len"] >= 1.0:
        return "query_api"
    return "content_retrieval"


def softmax_confidence(distances: list[float]) -> float:
    """Relative confidence from centroid distances; not a calibrated probability."""
    if not distances:
        return 0.0
    weights = [math.exp(-d) for d in distances]
    total = sum(weights)
    return round(weights[distances.index(min(distances))] / total, 4) if total else 0.0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    started = utc_now()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    pcap = EVIDENCE_DIR / PCAP_NAME
    results: list[dict] = []

    size = pcap.stat().st_size if pcap.is_file() else 0
    check(results, "current-run PCAP is available for analysis", size > 0,
          f"{pcap} ({size} bytes)")

    requests = build_requests(pcap) if size else []
    check(results, "tshark extracted HTTP requests from the PCAP", len(requests) >= 50,
          f"{len(requests)} request(s)")

    flows = build_flows(pcap) if size else []
    by_stream: dict[str, list[dict]] = defaultdict(list)
    for request in requests:
        by_stream[request["stream"]].append(request)
    for flow in flows:
        members = by_stream.get(flow["stream"], [])
        flow["requests"] = len(members)
        flow["methods"] = sorted({m["method"] for m in members})
        duration = max(flow["end"] - flow["start"], 1e-6)
        flow["duration"] = round(flow["end"] - flow["start"], 6)
        flow["pps"] = round(flow["packets"] / duration, 3)
        flow["bps"] = round(flow["bytes"] / duration, 3)

    if len(requests) < 2:
        write_json(EVIDENCE_DIR / "analytics.json", {
            "phase": "2C-Advanced", "component": "analytics", "run_id": RUN_ID,
            "build_tag": BUILD_TAG, "started_utc": started,
            "finished_utc": utc_now(), "decision": "FAIL",
            "checks": results, "supplementary": True,
            "note": "not enough HTTP requests to model traffic",
        })
        print("[2C-Advanced] FAIL — not enough HTTP requests")
        return 1

    vectors = [[r["features"][name] for name in FEATURE_NAMES] for r in requests]
    scaled, means, scales, keep = standardize(vectors)
    kept_names = [FEATURE_NAMES[j] for j in keep]
    check(results, "at least three features carry variance", len(keep) >= 3,
          f"{len(keep)} usable feature(s): {', '.join(kept_names)}")

    labels, centroids, inertia = kmeans(scaled, K)
    cluster_sizes = Counter(labels)
    check(results, f"k-means produced {K} non-empty clusters (>=2 required)",
          len(cluster_sizes) >= min(2, len(requests)), f"sizes={dict(cluster_sizes)}")

    # Raw centroid profile per cluster (interpretable medians).
    profiles: dict[int, dict] = {}
    for cluster in sorted(cluster_sizes):
        members = [requests[i]["features"] for i, label in enumerate(labels) if label == cluster]
        profiles[cluster] = {name: round(median([m[name] for m in members]), 3)
                             for name in FEATURE_NAMES}

    names = {cluster: cluster_name(profiles[cluster]) for cluster in profiles}
    # Baseline: the plain content-retrieval cluster. Explicit prior, documented.
    baseline_candidates = [c for c, name in names.items() if name == "content_retrieval"]
    baseline_cluster = max(baseline_candidates, key=lambda c: cluster_sizes[c]) \
        if baseline_candidates else max(cluster_sizes, key=lambda c: cluster_sizes[c])
    baseline_kind = "content_retrieval" if baseline_candidates else "largest_cluster"
    baseline_members = [requests[i] for i, label in enumerate(labels) if label == baseline_cluster]
    check(results, "baseline profile learned from the run",
          len(baseline_members) >= 5,
          f"cluster={baseline_cluster} kind={baseline_kind} n={len(baseline_members)}")

    baseline_vectors = [r["features"] for r in baseline_members]
    baseline_stats = {}
    for name in FEATURE_NAMES:
        values = [v[name] for v in baseline_vectors]
        center = median(values)
        spread = 1.4826 * mad(values, center)
        baseline_stats[name] = {
            "median": round(center, 3),
            "mad": round(mad(values, center), 3),
            "scale": round(max(spread, 0.5), 3),
        }

    for i, request in enumerate(requests):
        scores = {}
        for name in FEATURE_NAMES:
            stat = baseline_stats[name]
            scores[name] = round(abs(request["features"][name] - stat["median"])
                                 / stat["scale"], 3)
        top_feature = max(scores, key=lambda name: scores[name])
        request["anomaly_score"] = round(max(scores.values()), 3)
        request["top_feature"] = top_feature
        request["feature_scores"] = scores
        request["flagged"] = request["anomaly_score"] >= Z_THRESHOLD
        request["cluster"] = names.get(labels[i], f"cluster_{labels[i]}")
        point = scaled[i]
        request["confidence"] = softmax_confidence([math.sqrt(sqdist(point, c)) for c in centroids])

    flagged = [r for r in requests if r["flagged"]]
    controlled = [r for r in requests
                  if SQLI_MARK in r["uri"] and r["method"] == "GET"]
    tested = [r for r in requests if r["uri"].startswith(ENDPOINT_UNDER_TEST)]
    credentials = [r for r in requests if r["method"] == "POST"]
    requestor = min(controlled, key=lambda r: r["time"]) if controlled else None

    def rate(group: list[dict]) -> dict:
        hits = sum(1 for r in group if r["flagged"])
        return {"requests": len(group), "flagged": hits,
                "rate": round(hits / len(group), 3) if group else 0.0}

    # -- Suricata cross-layer link (read-only, never re-run) ----------------
    sid_uris: Counter = Counter()
    sid_events = 0
    eve = EVIDENCE_DIR / "eve.json"
    if eve.is_file():
        for line in eve.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") != "alert":
                continue
            if str((event.get("alert") or {}).get("signature_id")) != SID:
                continue
            sid_events += 1
            url = (event.get("http") or {}).get("url") or ""
            if url:
                sid_uris[url] += 1
    flagged_uris = {r["uri"] for r in flagged}
    matched = sorted(uri for uri in sid_uris if uri in flagged_uris)

    # -- artifacts ----------------------------------------------------------
    features_csv = EVIDENCE_DIR / "traffic-features.csv"
    with features_csv.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["index", "frame", "time", "src", "sport", "dst", "dport",
                         "stream", "method", "host", "uri"] + FEATURE_NAMES
                        + ["cluster", "confidence", "anomaly_score", "top_feature", "flagged"])
        for r in requests:
            writer.writerow([r["index"], r["frame"], round(r["time"], 6), r["src"],
                             r["sport"], r["dst"], r["dport"], r["stream"], r["method"],
                             r["host"], r["uri"]]
                            + [r["features"][name] for name in FEATURE_NAMES]
                            + [r["cluster"], r["confidence"], r["anomaly_score"],
                               r["top_feature"], int(r["flagged"])])

    flows_csv = EVIDENCE_DIR / "traffic-flows.csv"
    with flows_csv.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["stream", "src", "sport", "dst", "dport", "packets", "bytes",
                         "start", "end", "duration", "pps", "bps", "requests", "methods"])
        for flow in sorted(flows, key=lambda f: f["start"]):
            writer.writerow([flow["stream"], flow["src"], flow["sport"], flow["dst"],
                             flow["dport"], flow["packets"], flow["bytes"],
                             round(flow["start"], 6), round(flow["end"], 6),
                             flow["duration"], flow["pps"], flow["bps"],
                             flow["requests"], ",".join(flow["methods"])])

    anomaly = {
        "phase": "2C-Advanced",
        "component": "traffic-anomaly",
        "run_id": RUN_ID,
        "build_tag": BUILD_TAG,
        "generated_utc": utc_now(),
        "supplementary": True,
        "gate_impact": "none",
        "pcap": {"name": pcap.name, "path": str(pcap), "size": size},
        "population": {"requests": len(requests), "flows": len(flows)},
        "model": {
            "name": "robust-baseline modified z-score",
            "baseline_cluster": baseline_cluster,
            "baseline_kind": baseline_kind,
            "baseline_requests": len(baseline_members),
            "threshold": Z_THRESHOLD,
            "variance_floor": 0.5,
            "features": FEATURE_NAMES,
            "baseline_stats": baseline_stats,
        },
        "result": {
            "flagged": len(flagged),
            "not_flagged": len(requests) - len(flagged),
            "flagged_rate": round(len(flagged) / len(requests), 3),
            "groups": {
                "endpoint_under_test": rate(tested),
                "credential_submission": rate(credentials),
                "controlled_payload_requests": rate(controlled),
            },
            "top_anomalies": [
                {"frame": r["frame"], "time": round(r["time"], 6), "src": r["src"],
                 "method": r["method"], "uri": r["uri"], "score": r["anomaly_score"],
                 "top_feature": r["top_feature"], "cluster": r["cluster"]}
                for r in sorted(flagged, key=lambda r: r["anomaly_score"], reverse=True)[:10]
            ],
            "controlled_request": {
                "frame": requestor["frame"] if requestor else None,
                "time": round(requestor["time"], 6) if requestor else None,
                "src": requestor["src"] if requestor else "",
                "uri": requestor["uri"] if requestor else "",
                "score": requestor["anomaly_score"] if requestor else None,
                "flagged": bool(requestor and requestor["flagged"]),
            },
            "suricata_cross_check": {
                "sid": SID,
                "sid_events": sid_events,
                "flagged_uris_seen_in_alerts": len(matched),
            },
        },
        "interpretation": (
            "Bounded demonstration on one controlled capture. The population is "
            "dominated by attack traffic, so these rates describe this run and are "
            "not detection accuracy. Analytics never replaces Suricata and never "
            "changes the Security Gate."
        ),
    }
    write_json(EVIDENCE_DIR / "traffic-anomaly.json", anomaly)

    classification = {
        "phase": "2C-Advanced",
        "component": "traffic-classification",
        "run_id": RUN_ID,
        "build_tag": BUILD_TAG,
        "generated_utc": utc_now(),
        "supplementary": True,
        "gate_impact": "none",
        "model": {
            "name": "k-means (k=%d) on standardized request features" % K,
            "seed": RANDOM_SEED,
            "inertia": round(inertia, 3),
            "features": kept_names,
            "dropped_zero_variance": [n for n in FEATURE_NAMES if n not in kept_names],
            "confidence": "softmax over centroid distances (relative, not calibrated)",
        },
        "clusters": [
            {
                "id": cluster,
                "label": names[cluster],
                "members": cluster_sizes[cluster],
                "profile": profiles[cluster],
                "is_baseline": cluster == baseline_cluster,
            }
            for cluster in sorted(cluster_sizes)
        ],
        "assignments": [
            {"frame": r["frame"], "time": round(r["time"], 6), "method": r["method"],
             "uri": r["uri"], "cluster": r["cluster"], "confidence": r["confidence"],
             "anomaly_score": r["anomaly_score"], "flagged": r["flagged"]}
            for r in requests
        ],
        "evaluation": {
            "endpoint_under_test": ENDPOINT_UNDER_TEST,
            "ground_truth_note": (
                "The endpoint and method are used only to evaluate the output; "
                "neither is a model feature."
            ),
            "endpoint_under_test_requests": len(tested),
            "credential_requests": len(credentials),
            "labels_assigned": dict(Counter(names[labels[i]] for i in range(len(requests)))),
        },
    }
    write_json(EVIDENCE_DIR / "traffic-classification.json", classification)

    for path, label in ((features_csv, "traffic-features.csv"),
                        (flows_csv, "traffic-flows.csv")):
        check(results, f"{label} written", path.is_file() and path.stat().st_size > 0,
              f"{path.stat().st_size if path.is_file() else 0} bytes")
    check(results, "traffic-anomaly.json written", True, anomaly["model"]["name"])
    check(results, "traffic-classification.json written", True,
          f"{len(cluster_sizes)} cluster(s), {len(requests)} assignment(s)")
    check(results, "analytics output is marked supplementary",
          anomaly["supplementary"] is True and classification["supplementary"] is True,
          "gate_impact=none")

    failed = [r for r in results if r["status"] == "FAIL"]
    # Supplementary contract: poor analytical quality is reported as DEGRADED,
    # never as a build failure. Only a tool failure (handled above) exits 1.
    decision = "PASS" if not failed else "DEGRADED"
    report = {
        "phase": "2C-Advanced",
        "component": "analytics",
        "run_id": RUN_ID,
        "build_tag": BUILD_TAG,
        "started_utc": started,
        "finished_utc": utc_now(),
        "decision": decision,
        "checks_total": len(results),
        "checks_failed": len(failed),
        "checks": results,
        "supplementary": True,
        "gate_impact": "none",
        "summary": {
            "requests": len(requests),
            "flows": len(flows),
            "baseline_requests": len(baseline_members),
            "flagged": len(flagged),
            "controlled_request_flagged": bool(requestor and requestor["flagged"]),
            "sid_events": sid_events,
        },
        "artifacts": ["traffic-features.csv", "traffic-flows.csv",
                      "traffic-anomaly.json", "traffic-classification.json",
                      "analytics.json", "analytics.md"],
    }
    write_json(EVIDENCE_DIR / "analytics.json", report)

    outcome = "FLAGGED" if requestor and requestor["flagged"] else "NOT FLAGGED"
    lines = [
        "# Scenario B — Phase 2C-Advanced — Traffic intelligence (supplementary)",
        "",
        f"- RUN_ID: `{RUN_ID}`",
        f"- Build: `{BUILD_TAG}`",
        f"- Decision: **{report['decision']}** ({len(failed)} failed of {len(results)})",
        "- Gate impact: **none** — analytics is supporting evidence, not a policy control",
        "",
        "## Model",
        "",
        f"- k-means k={K}, seed {RANDOM_SEED}, inertia {round(inertia, 3)}",
        f"- Baseline: cluster {baseline_cluster} (`{baseline_kind}`), "
        f"{len(baseline_members)} request(s)",
        f"- Anomaly: modified z-score vs baseline medians, threshold {Z_THRESHOLD}",
        "",
        "## Result",
        "",
        f"- Requests: {len(requests)} over {len(flows)} TCP stream(s)",
        f"- Flagged as anomalous: {len(flagged)}",
        f"- Controlled SQLi request (frame {requestor['frame'] if requestor else '-'}): "
        f"**{outcome}** with score "
        f"{requestor['anomaly_score'] if requestor else '-'}",
        f"- Endpoint under test: {rate(tested)['flagged']}/{len(tested)} flagged",
        f"- Credential submissions: {rate(credentials)['flagged']}/{len(credentials)} flagged",
        f"- Suricata SID {SID}: {sid_events} alert(s); "
        f"{len(matched)} flagged URI(s) also appear in an alert",
        "",
        "## Clusters",
        "",
        "| Cluster | Label | Members | Baseline |",
        "|---|---|---|---|",
    ]
    for cluster in sorted(cluster_sizes):
        lines.append(f"| {cluster} | `{names[cluster]}` | {cluster_sizes[cluster]} | "
                     f"{'yes' if cluster == baseline_cluster else 'no'} |")
    lines += ["", "## Checks", "", "| Check | Status | Detail |", "|---|---|---|"]
    for item in results:
        detail = item["detail"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {item['check']} | {item['status']} | {detail} |")
    lines += ["", "> Bounded demonstration on one controlled capture. Rates describe "
              "this run and are not production detection accuracy.", ""]
    (EVIDENCE_DIR / "analytics.md").write_text("\n".join(lines))

    print(f"\n[2C-Advanced] analytics: {report['decision']} — "
          f"{len(failed)} failed of {len(results)}; controlled request {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
