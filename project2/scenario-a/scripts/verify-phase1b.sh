#!/usr/bin/env bash
# =============================================================================
# Project 2 — Phase 1B acceptance.
#
# Checks, in order:
#   1. telecom-lab-django:0.1 builds and `manage.py check` passes
#   2. scenario-b-django is healthy (Docker healthcheck)
#   3. it is attached to app-net ONLY, at 10.20.8.20
#   4. app-net is internal and matches 10.20.8.0/24
#   5. django-data exists and survives container recreation
#   6. GET /health/ returns the exact contract body
#   7. an Nginx proxy on app-net can reach Django
#
# Usage:  ./project2/scenario-a/scripts/verify-phase1b.sh
# =============================================================================
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-a
COMPOSE="$HERE/docker-compose.p2.yaml"
IMG="telecom-lab-django:0.1"
CT="scenario-b-django"
EXPECTED='{"service": "project2-django", "status": "ok", "project": "Telecommunication Security"}'
CURL_IMG="curlimages/curl:latest"

ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; ERRORS=$((ERRORS+1)); }
step() { printf '\033[1;34m----]\033[0m %s\n' "$*"; }
ERRORS=0
TMP=$(mktemp -d)
trap 'docker rm -f p2-nginx-check >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT

step "1. image build and Django system check"
if ! docker image inspect "$IMG" >/dev/null 2>&1; then
    docker compose -f "$COMPOSE" build django >/dev/null 2>&1 \
        || { echo "build failed — run docker compose -f $COMPOSE build django"; }
fi
docker image inspect "$IMG" >/dev/null 2>&1 \
    && ok "$IMG built" \
    || fail "$IMG missing"
CHECK=$(docker run --rm --entrypoint python --env-file "$HERE/env" "$IMG" manage.py check 2>&1)
if [[ $? -eq 0 ]]; then
    ok "manage.py check: $(tr -s ' \n' ' ' <<<"$CHECK" | sed 's/ *$//')"
else
    fail "manage.py check failed: $CHECK"
fi

step "2. container health"
docker compose -f "$COMPOSE" up -d --no-build >/dev/null 2>&1 || fail "compose up failed"
for _ in $(seq 1 30); do
    H=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CT" 2>/dev/null || true)
    [[ "$H" == "healthy" ]] && break
    sleep 2
done
if [[ "$H" == "healthy" ]]; then
    ok "$CT healthy"
else
    fail "$CT health='${H:-missing}' (see: docker logs $CT)"
    docker logs --tail 20 "$CT" 2>&1 | sed 's/^/       /'
fi

step "3. network attachment (app-net only)"
NETS=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$CT" 2>/dev/null | tr -s ' ' | sed 's/^ //; s/ $//')
IP=$(docker inspect -f '{{with index .NetworkSettings.Networks "app-net"}}{{.IPAddress}}{{end}}' "$CT" 2>/dev/null || true)
if [[ "$NETS" == "app-net" ]]; then
    ok "attached only to app-net"
else
    fail "networks: '${NETS:-none}' (expected only app-net)"
fi
if [[ "$IP" == "10.20.8.20" ]]; then
    ok "Django address 10.20.8.20"
else
    fail "Django address '${IP:-none}' (expected 10.20.8.20)"
fi
if docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' "$CT" 2>/dev/null | grep -q dn-net; then
    fail "Django is attached to dn-net (must never be)"
else
    ok "Django is not on dn-net"
fi

step "4. app-net definition"
INTERNAL=$(docker network inspect -f '{{.Internal}}' app-net 2>/dev/null || echo "missing")
SUBNET=$(docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' app-net 2>/dev/null || true)
[[ "$INTERNAL" == "true" ]] && ok "app-net is internal" || fail "app-net Internal='$INTERNAL' (expected true)"
[[ "$SUBNET" == "10.20.8.0/24" ]] && ok "app-net subnet 10.20.8.0/24" || fail "app-net subnet '${SUBNET:-none}'"

step "5. django-data volume survives recreation"
docker volume inspect django-data >/dev/null 2>&1 && ok "volume django-data exists" || fail "volume django-data missing"
STAMP="phase1b-$(date +%s)"
docker exec "$CT" sh -c "echo $STAMP > /app/data/persistence-check" 2>/dev/null \
    && ok "wrote a marker into /app/data" \
    || fail "cannot write to /app/data (volume permissions?)"
docker compose -f "$COMPOSE" up -d --no-build --force-recreate django >/dev/null 2>&1 || fail "recreate failed"
for _ in $(seq 1 30); do
    H=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CT" 2>/dev/null || true)
    [[ "$H" == "healthy" ]] && break
    sleep 2
done
[[ "$H" == "healthy" ]] && ok "recreated container healthy" || fail "recreated container '${H:-missing}'"
MARKER=$(docker exec "$CT" cat /app/data/persistence-check 2>/dev/null || true)
[[ "$MARKER" == "$STAMP" ]] && ok "marker survived the recreation" || fail "marker lost after recreation"
docker exec "$CT" test -s /app/data/db.sqlite3 \
    && ok "SQLite database at /app/data/db.sqlite3" \
    || fail "database file missing or empty"

step "6. /health/ response"
BODY=$(docker run --rm --network app-net "$CURL_IMG" -fsS --max-time 5 http://10.20.8.20:8000/health/ 2>/dev/null || true)
if [[ "$BODY" == "$EXPECTED" ]]; then
    ok "exact JSON body"
    printf '       %s\n' "$BODY"
else
    fail "unexpected body: ${BODY:-<none>}"
fi

step "7. Nginx on app-net can reach Django"
cat > "$TMP/nginx.conf" <<'EOF'
server {
    listen 8080;
    location /health/ {
        proxy_pass http://10.20.8.20:8000;
    }
}
EOF
docker rm -f p2-nginx-check >/dev/null 2>&1 || true
if docker run -d --rm --name p2-nginx-check --network app-net \
        -v "$TMP/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine >/dev/null 2>&1; then
    sleep 3
    THROUGH=$(docker run --rm --network app-net "$CURL_IMG" -fsS --max-time 5 \
        http://p2-nginx-check:8080/health/ 2>/dev/null || true)
    if [[ "$THROUGH" == "$EXPECTED" ]]; then
        ok "health through an Nginx proxy: 200"
    else
        fail "Nginx proxy did not return the contract body"
    fi
    docker rm -f p2-nginx-check >/dev/null 2>&1 || true
else
    fail "could not start the Nginx check container"
fi

echo
if [[ $ERRORS -eq 0 ]]; then
    ok "Phase 1B complete: Django is healthy on the isolated app-net."
else
    fail "$ERRORS check(s) failed."
    exit 1
fi
