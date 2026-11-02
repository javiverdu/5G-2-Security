#!/usr/bin/env bash
# =============================================================================
# Project 2 — Scenario B: create the Jenkins pipeline job.
#
# Idempotent: waits for Jenkins, then creates `scenario-b-security` from
# jenkins/job.xml if it does not exist. Admin credentials come from ./env.
#
# Usage:  ./project2/scenario-b/scripts/jenkins-bootstrap.sh
# =============================================================================
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-b
JOB="scenario-b-security"
URL="http://127.0.0.1:8080"

# shellcheck disable=SC1091
set -a; . "$HERE/env"; set +a

echo "[bootstrap] waiting for Jenkins"
for _ in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$URL/login" || true)
    [[ "$code" == "200" ]] && break
    sleep 3
done
[[ "${code:-}" == "200" ]] || { echo "[bootstrap] Jenkins did not come up"; exit 1; }

if curl -s -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
        -o /dev/null -w '%{http_code}' "$URL/job/$JOB/api/json" | grep -q '^200$'; then
    echo "[bootstrap] job $JOB already exists"
    exit 0
fi

echo "[bootstrap] creating job $JOB"
# Jenkins binds the CSRF crumb to the HTTP session, so both calls share a
# cookie jar (an API token would be the alternative).
JAR=$(mktemp)
trap 'rm -f "$JAR"' EXIT
CRUMB=$(curl -fsS -c "$JAR" -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
    "$URL/crumbIssuer/api/json" | sed -n 's/.*"crumb":"\([^"]*\)".*/\1/p')
[[ -n "$CRUMB" ]] || { echo "[bootstrap] could not obtain a CSRF crumb"; exit 1; }
curl -fsS -b "$JAR" -u "$JENKINS_ADMIN_ID:$JENKINS_ADMIN_PASSWORD" \
    -H "Jenkins-Crumb: $CRUMB" \
    -H "Content-Type: application/xml" \
    --data-binary "@$HERE/jenkins/job.xml" \
    "$URL/createItem?name=$JOB"
echo "[bootstrap] created; run: $URL/job/$JOB/"
