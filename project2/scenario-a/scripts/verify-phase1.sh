#!/usr/bin/env bash
# =============================================================================
# Project 2 — Phase 1E: end-to-end acceptance from the UE through 5G.
#
# This is the gate into Scenario B. Every HTTP request leaves the UE network
# namespace, crosses the PDU session (uesimtun0), the UPF, dn-net, the TLS
# gateway, and reaches Django over app-net. Nothing uses app-net directly and
# no request uses -k.
#
# Covers:
#   1. UE data path: uesimtun0 10.45.x, route via uesimtun0, N6 reachability
#   2. certificate chain and TLS 1.2 / 1.3 handshakes
#   3. HTTP 301 -> HTTPS 200, with a trusted certificate
#   4. public endpoints and the exact /health/ body
#   5. authentication: anonymous redirect, login, profile identity
#   6. CSRF: protected POST 200, missing/invalid token 403
#   7. cookie attributes and security headers
#   8. the gateway sees the real UE address (no NAT)
#
# Usage:  ./project2/scenario-a/scripts/verify-phase1.sh
# =============================================================================
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-a
ROOT=$(cd "$HERE/../.." && pwd)
SECRETS="$ROOT/secrets/tls"
# Inside Jenkins the checkout has no git-ignored secrets, but the host repo is
# mounted read-only at /lab.
if [[ ! -f "$SECRETS/ca.crt" && -d /lab/secrets/tls ]]; then
    SECRETS=/lab/secrets/tls
fi
# Paths passed to `docker run -v` must be host paths, even when this script runs
# inside Jenkins (Docker-outside-of-Docker). P2_HOST_REPO points at the host copy
# of the repository when the script runs in a container.
HOST_SECRETS="${P2_HOST_REPO:-$ROOT}/secrets/tls"
CA="$SECRETS/ca.crt"
CRT="$SECRETS/server.crt"
IMG="telecom-lab-nginx:p2"
CT="scenario-b-nginx"
RUN_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CURL_IMG="curlimages/curl:latest"
BASE="https://10.20.6.20"
EXPECTED='{"service": "project2-django", "status": "ok", "project": "Telecommunication Security"}'
# The temporary client script is mounted into `docker run`, so its path must be
# a HOST path. When this runs inside Jenkins (Docker-outside-of-Docker), use the
# run-specific evidence directory, which is mounted at a known host path.
if [[ -n "${EVIDENCE_DIR:-}" && -n "${EVIDENCE_HOST_DIR:-}" ]]; then
    TMP="$EVIDENCE_DIR/.verify-tmp.$$"
    TMP_HOST="$EVIDENCE_HOST_DIR/.verify-tmp.$$"
    mkdir -p "$TMP"
else
    TMP=$(mktemp -d)
    TMP_HOST="$TMP"
fi
trap 'rm -rf "$TMP"' EXIT

ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; ERRORS=$((ERRORS+1)); }
step() { printf '\033[1;34m----]\033[0m %s\n' "$*"; }
ERRORS=0

ENV_FILE="${P2_ENV_FILE:-$HERE/env}"
set -a; . "$ENV_FILE"; set +a

client() {
    docker run --rm --network container:nr_ue \
        -v "$HOST_SECRETS/ca.crt:/etc/telecom-lab/ca.crt:ro" \
        -v "$TMP_HOST/client.sh:/client.sh:ro" \
        -e LAB_USER="${LAB_ADMIN_USER:-securityadmin}" \
        -e LAB_PASS="${LAB_ADMIN_PASSWORD:-}" \
        -e BASE="$BASE" \
        --entrypoint sh "$CURL_IMG" /client.sh
}

cat > "$TMP/client.sh" <<'CLIENT'
set -u
C="--cacert /etc/telecom-lab/ca.crt"
JAR=/tmp/jar; rm -f "$JAR"
code() { curl -s $C -o /dev/null -w '%{http_code}' --max-time 8 "$@"; }

echo "HTTP_ROOT=$(code http://10.20.6.20/)"
echo "HTTP_HEALTH=$(code http://10.20.6.20/health/)"
echo "REDIRECT_ROOT=$(curl -s $C -o /dev/null -w '%{redirect_url}' --max-time 8 http://10.20.6.20/)"
echo "REDIRECT_HEALTH=$(curl -s $C -o /dev/null -w '%{redirect_url}' --max-time 8 http://10.20.6.20/health/)"
echo "HTTPS_ROOT=$(code "$BASE/")"
echo "HTTPS_HEALTH=$(code "$BASE/health/")"
echo "HTTPS_API=$(code "$BASE/api/status/")"
echo "HTTPS_SEARCH=$(code "$BASE/search/?q=TLS")"
echo "HTTPS_ADMIN=$(code "$BASE/admin/")"
echo "HEALTH_BODY=$(curl -s $C --max-time 8 "$BASE/health/")"
echo "API_BODY=$(curl -s $C --max-time 8 "$BASE/api/status/")"

echo "ANON_PROFILE=$(curl -s $C -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 8 "$BASE/profile/")"

curl -s $C -c "$JAR" -D /tmp/l1 -o /tmp/login.html --max-time 8 "$BASE/accounts/login/"
echo "LOGIN_GET=$(head -n1 /tmp/l1 | tr -d '\r')"
grep -i '^set-cookie: csrftoken=' /tmp/l1 | tr -d '\r' | sed 's/^/CSRF_SET_COOKIE=/'
T=$(sed -n 's/.*name="csrfmiddlewaretoken" value="\([^"]*\)".*/\1/p' /tmp/login.html | head -1)
echo "LOGIN_CSRF_TOKEN=${T:+present}"

curl -s $C -b "$JAR" -c "$JAR" -D /tmp/l2 -o /dev/null --max-time 8 \
    -H "Origin: $BASE" --data-urlencode "csrfmiddlewaretoken=$T" \
    --data-urlencode "username=$LAB_USER" --data-urlencode "password=$LAB_PASS" \
    --data-urlencode "next=/profile/" "$BASE/accounts/login/"
echo "LOGIN_POST=$(head -n1 /tmp/l2 | tr -d '\r')"
grep -i '^set-cookie: sessionid=' /tmp/l2 | tr -d '\r' | sed 's/^/SESSION_SET_COOKIE=/'

curl -s $C -b "$JAR" -o /tmp/profile.html -w 'PROFILE=%{http_code}\n' --max-time 8 "$BASE/profile/"
grep -o 'Username: [A-Za-z0-9_.-]*' /tmp/profile.html | sed 's/^/PROFILE_LINE=/'
grep -o 'Authenticated: True' /tmp/profile.html | sed 's/^/PROFILE_LINE=/'

curl -s $C -b "$JAR" -o /tmp/feedback.html -w 'FEEDBACK_GET=%{http_code}\n' --max-time 8 "$BASE/feedback/"
F=$(sed -n 's/.*name="csrfmiddlewaretoken" value="\([^"]*\)".*/\1/p' /tmp/feedback.html | head -1)
echo "FEEDBACK_CSRF_TOKEN=${F:+present}"
curl -s $C -b "$JAR" -o /dev/null -w 'FEEDBACK_OK=%{http_code}\n' --max-time 8 \
    -H "Origin: $BASE" --data-urlencode "csrfmiddlewaretoken=$F" \
    --data-urlencode "message=phase 1e acceptance" "$BASE/feedback/"
curl -s $C -b "$JAR" -o /dev/null -w 'FEEDBACK_MISSING_CSRF=%{http_code}\n' --max-time 8 \
    -H "Origin: $BASE" --data-urlencode "message=no token" "$BASE/feedback/"
curl -s $C -b "$JAR" -o /dev/null -w 'FEEDBACK_INVALID_CSRF=%{http_code}\n' --max-time 8 \
    -H "Origin: $BASE" --data-urlencode "csrfmiddlewaretoken=invalid" \
    --data-urlencode "message=bad token" "$BASE/feedback/"

curl -s $C -b "$JAR" -D /tmp/headers.txt -o /dev/null --max-time 8 "$BASE/health/"
grep -iE '^(strict-transport-security|x-frame-options|x-content-type-options|referrer-policy):' \
    /tmp/headers.txt | tr -d '\r' | sed 's/^/HEADER=/'

curl -s $C -G --data-urlencode 'q=<script>alert(1)</script>' -o /tmp/search.html --max-time 8 "$BASE/search/"
if grep -q '&lt;script&gt;' /tmp/search.html && ! grep -q '<script>alert(1)</script>' /tmp/search.html; then
    echo "SEARCH_ESCAPED=yes"
else
    echo "SEARCH_ESCAPED=no"
fi
CLIENT

step "1. UE data path"
UADDR=$(docker exec nr_ue ip -4 -brief addr show uesimtun0 2>/dev/null | awk '{print $3}')
[[ "$UADDR" == 10.45.* ]] && ok "uesimtun0 = $UADDR" || fail "uesimtun0: '${UADDR:-none}'"
[[ "$(docker inspect -f '{{.Config.Image}}' nr_ue 2>/dev/null)" == "telecom-lab-ueransim:3.3.0-p2" ]] \
    && ok "nr_ue runs UERANSIM v3.3.0 image" || fail "nr_ue image mismatch"
if grep -q uesimtun0 <<<"$(docker exec nr_ue ip route get 10.20.6.20 2>/dev/null)"; then
    ok "10.20.6.20 resolves via uesimtun0"
else
    fail "10.20.6.20 does not resolve via uesimtun0"
fi
docker exec nr_ue ping -c 1 -W 2 10.20.6.20 >/dev/null 2>&1 \
    && ok "UE reaches the gateway on N6" || fail "UE cannot reach 10.20.6.20"

step "2. certificate and TLS handshakes"
[[ "$(docker inspect -f '{{.Config.Image}}' "$CT" 2>/dev/null)" == "$IMG" ]] \
    && ok "$CT runs $IMG" || fail "$CT image mismatch"
if openssl verify -CAfile "$CA" "$CRT" >/dev/null 2>&1; then
    ok "server certificate verifies against the lab CA"
else
    fail "server certificate does not verify"
fi
for v in "-tls1_2 TLSv1.2" "-tls1_3 TLSv1.3"; do
    FLAG=${v%% *}; WANT=${v##* }
    OUT=$(docker run --rm --network container:nr_ue \
        -v "$HOST_SECRETS/ca.crt:/etc/telecom-lab/ca.crt:ro" --entrypoint openssl "$IMG" \
        s_client -connect 10.20.6.20:443 -servername telecom-lab.local \
        -CAfile /etc/telecom-lab/ca.crt "$FLAG" -verify_return_error </dev/null 2>&1 || true)
    PROTO=$(grep -oE 'Protocol *: *TLSv1\.[0-9]' <<<"$OUT" | head -1 | awk '{print $NF}')
    VRC=$(grep -oE 'Verify return code: [0-9]+ \(ok\)' <<<"$OUT" | head -1)
    [[ "$PROTO" == "$WANT" && -n "$VRC" ]] && ok "$WANT handshake, certificate verified" \
        || fail "$WANT handshake failed (protocol='${PROTO:-none}')"
done

step "3. HTTP 301 -> HTTPS 200 (trusted, no -k)"
OUT="$TMP/out.txt"; client > "$OUT" 2>&1 || true
get() { sed -n "s/^$1=//p" "$OUT" | head -1; }
[[ "$(get HTTP_ROOT)" == "301" ]] && ok "HTTP / -> 301" || fail "HTTP / -> '$(get HTTP_ROOT)'"
[[ "$(get REDIRECT_ROOT)" == "https://10.20.6.20/" ]] && ok "Location: $(get REDIRECT_ROOT)" \
    || fail "redirect target: '$(get REDIRECT_ROOT)'"
[[ "$(get HTTP_HEALTH)" == "301" ]] && ok "HTTP /health/ -> 301" || fail "HTTP /health/ -> '$(get HTTP_HEALTH)'"
[[ "$(get HTTPS_ROOT)" == "200" ]] && ok "HTTPS / -> 200" || fail "HTTPS / -> '$(get HTTPS_ROOT)'"
[[ "$(get HTTPS_HEALTH)" == "200" ]] && ok "HTTPS /health/ -> 200" || fail "HTTPS /health/ -> '$(get HTTPS_HEALTH)'"
[[ "$(get HEALTH_BODY)" == "$EXPECTED" ]] && ok "exact /health/ body" || fail "body: '$(get HEALTH_BODY)'"

step "4. public endpoints"
[[ "$(get HTTPS_API)" == "200" ]] && ok "/api/status/ -> 200" || fail "/api/status/ -> '$(get HTTPS_API)'"
[[ "$(get HTTPS_SEARCH)" == "200" ]] && ok "/search/ -> 200" || fail "/search/ -> '$(get HTTPS_SEARCH)'"
[[ "$(get HTTPS_ADMIN)" == "302" ]] && ok "/admin/ -> 302 (login)" || fail "/admin/ -> '$(get HTTPS_ADMIN)'"
grep -q '"authenticated": false' <<<"$(get API_BODY)" && ok "api reports unauthenticated caller" \
    || fail "api body: '$(get API_BODY)'"

step "5. authentication"
ANON=$(get ANON_PROFILE)
[[ "$ANON" == 302*"/accounts/login/"* ]] && ok "anonymous /profile/ -> 302" || fail "anon: '${ANON:-none}'"
[[ "$(get LOGIN_GET)" == *"200"* ]] && ok "login page 200" || fail "login page: '$(get LOGIN_GET)'"
[[ "$(get LOGIN_POST)" == *"302"* ]] && ok "authenticated login -> 302" || fail "login -> '$(get LOGIN_POST)'"
[[ "$(get PROFILE)" == "200" ]] && ok "authenticated /profile/ -> 200" || fail "profile -> '$(get PROFILE)'"
grep -q '^PROFILE_LINE=Username: securityadmin$' "$OUT" && ok "Username: securityadmin" \
    || fail "missing Username line"
grep -q '^PROFILE_LINE=Authenticated: True$' "$OUT" && ok "Authenticated: True" || fail "missing Authenticated line"

step "6. CSRF protection"
[[ "$(get FEEDBACK_GET)" == "200" ]] && ok "feedback form 200" || fail "feedback GET: '$(get FEEDBACK_GET)'"
[[ "$(get FEEDBACK_OK)" == "200" ]] && ok "valid CSRF POST -> 200" || fail "valid POST: '$(get FEEDBACK_OK)'"
[[ "$(get FEEDBACK_MISSING_CSRF)" == "403" ]] && ok "missing CSRF -> 403" || fail "missing: '$(get FEEDBACK_MISSING_CSRF)'"
[[ "$(get FEEDBACK_INVALID_CSRF)" == "403" ]] && ok "invalid CSRF -> 403" || fail "invalid: '$(get FEEDBACK_INVALID_CSRF)'"

step "7. cookies and headers"
SESSION_COOKIE=$(sed -n 's/^SESSION_SET_COOKIE=//p' "$OUT")
CSRF_COOKIE=$(sed -n 's/^CSRF_SET_COOKIE=//p' "$OUT")
for attr in "Secure" "HttpOnly" "SameSite=Lax"; do
    [[ "$SESSION_COOKIE" == *"$attr"* ]] && ok "session cookie has $attr" || fail "session cookie lacks $attr"
done
[[ "$CSRF_COOKIE" == *"Secure"* ]] && ok "CSRF cookie has Secure" || fail "CSRF cookie lacks Secure"
headers=$(sed -n 's/^HEADER=//p' "$OUT")
has() { grep -qi "^$1" <<<"$headers"; }
has "strict-transport-security: max-age=3600" && ok "HSTS max-age=3600" || fail "HSTS missing"
has "x-frame-options: DENY" && ok "X-Frame-Options: DENY" || fail "X-Frame-Options missing"
has "x-content-type-options: nosniff" && ok "X-Content-Type-Options: nosniff" || fail "nosniff missing"
has "referrer-policy: same-origin" && ok "Referrer-Policy: same-origin" || fail "referrer policy missing"
[[ "$(get SEARCH_ESCAPED)" == "yes" ]] && ok "search input escaped" || fail "search input not escaped"

step "8. real UE address at the gateway (no NAT)"
UEIP=$(docker exec nr_ue ip -4 -brief addr show uesimtun0 2>/dev/null | awk '{print $3}' | cut -d/ -f1)
# Only this run's log lines count, and allow the container log to flush. A
# fixed --tail window is racy when the previous run's requests sit next to it.
FOUND=0
for _ in $(seq 1 5); do
    if docker logs --since "$RUN_START" "$CT" 2>&1 | grep -q "^${UEIP} "; then
        FOUND=1
        break
    fi
    sleep 1
done
if [[ "$FOUND" -eq 1 ]]; then
    ok "gateway access log shows $UEIP"
else
    fail "gateway access log has no request from ${UEIP:-unknown} since $RUN_START"
fi

echo
if [[ $ERRORS -eq 0 ]]; then
    ok "Phase 1E complete: the 5G user-plane path serves the secured application."
else
    fail "$ERRORS check(s) failed."
    echo "--- client output ---"
    sed 's/^/       /' "$OUT"
    exit 1
fi
