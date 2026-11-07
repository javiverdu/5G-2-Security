#!/usr/bin/env bash
# =============================================================================
# Project 2 — Scenario B: trigger the Jenkins pipeline and follow it.
#
# Usage:  ./project2/scenario-b/scripts/run-pipeline.sh [--no-wait]
# =============================================================================
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-b
JOB="scenario-b-security"
URL="http://127.0.0.1:8080"
WAIT=1
[[ "${1:-}" == "--no-wait" ]] && WAIT=0

# shellcheck disable=SC1091
set -a; . "$HERE/env"; set +a

JAR=$(mktemp)
trap 'rm -f "$JAR"' EXIT

BEFORE=$(curl -s -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
    "$URL/job/$JOB/api/json" | sed -n 's/.*"nextBuildNumber":\([0-9]*\).*/\1/p')

CRUMB=$(curl -fsS -c "$JAR" -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
    "$URL/crumbIssuer/api/json" | sed -n 's/.*"crumb":"\([^"]*\)".*/\1/p')
[[ -n "$CRUMB" ]] || { echo "[run] could not obtain a CSRF crumb"; exit 1; }

echo "[run] triggering $JOB (build $BEFORE)"
# Pass the gate mode only when the caller sets it; otherwise Jenkins uses the
# job parameter default (REPORT_ONLY).
if [[ -n "${SECURITY_GATE_MODE:-}" ]]; then
    CODE=$(curl -s -o /dev/null -w '%{http_code}' \
        -b "$JAR" -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
        -H "Jenkins-Crumb: $CRUMB" -X POST \
        --data-urlencode "SECURITY_GATE_MODE=$SECURITY_GATE_MODE" \
        "$URL/job/$JOB/buildWithParameters" || true)
    if [[ "$CODE" != "200" && "$CODE" != "201" ]]; then
        echo "[run] WARN: buildWithParameters returned $CODE; the job has not"
        echo "[run] registered the parameter yet. Falling back to /build, which"
        echo "[run] uses the Jenkinsfile default (REPORT_ONLY)."
        curl -fsS -b "$JAR" -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
            -H "Jenkins-Crumb: $CRUMB" -X POST "$URL/job/$JOB/build" >/dev/null
    fi
else
    curl -fsS -b "$JAR" -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
        -H "Jenkins-Crumb: $CRUMB" -X POST "$URL/job/$JOB/build" >/dev/null
fi

[[ "$WAIT" -eq 1 ]] || { echo "[run] queued"; exit 0; }

MAX_WAIT="${MAX_WAIT_SECONDS:-5400}"
START=$(date +%s)
LAST_REPORT=$START
echo "[run] waiting for build $BEFORE (max ${MAX_WAIT}s)"
while true; do
    BUILDING=$(curl -s -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
        "$URL/job/$JOB/$BEFORE/api/json" \
        | sed -n 's/.*"building":\(true\|false\).*/\1/p')
    [[ "$BUILDING" == "false" ]] && break
    NOW=$(date +%s)
    if (( NOW - START >= MAX_WAIT )); then
        echo "[run] wait timeout after ${MAX_WAIT}s; build may still be running"
        break
    fi
    if (( NOW - LAST_REPORT >= 60 )); then
        echo "[run] still building $BEFORE ($((NOW - START))s)"
        LAST_REPORT=$NOW
    fi
    sleep 10
done

RESULT=$(curl -s -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
    "$URL/job/$JOB/$BEFORE/api/json" | sed -n 's/.*"result":"\([A-Z]*\)".*/\1/p')
echo "[run] build $BEFORE result: ${RESULT:-unknown}"
curl -s -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
    "$URL/job/$JOB/$BEFORE/consoleText" | tail -60
[[ "$RESULT" == "SUCCESS" ]] || exit 1
