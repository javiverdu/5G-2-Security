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
curl -fsS -b "$JAR" -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
    -H "Jenkins-Crumb: $CRUMB" -X POST "$URL/job/$JOB/build" >/dev/null

[[ "$WAIT" -eq 1 ]] || { echo "[run] queued"; exit 0; }

echo "[run] waiting for build $BEFORE"
for _ in $(seq 1 240); do
    BUILDING=$(curl -s -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
        "$URL/job/$JOB/$BEFORE/api/json" \
        | sed -n 's/.*"building":\(true\|false\).*/\1/p')
    [[ "$BUILDING" == "false" ]] && break
    sleep 5
done

RESULT=$(curl -s -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
    "$URL/job/$JOB/$BEFORE/api/json" | sed -n 's/.*"result":"\([A-Z]*\)".*/\1/p')
echo "[run] build $BEFORE result: ${RESULT:-unknown}"
curl -s -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
    "$URL/job/$JOB/$BEFORE/consoleText" | tail -60
[[ "$RESULT" == "SUCCESS" ]] || exit 1
