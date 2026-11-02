#!/usr/bin/env bash
# =============================================================================
# Project 2 — Phase 1D acceptance: Django security baseline.
#
# All requests run in a throwaway client that shares the UE network namespace,
# so they cross the 5G user plane to the TLS gateway (no direct app-net access).
#
# Checks:
#   1. public endpoints: /, /health/, /api/status/, /search/ (200) and /admin/
#   2. anonymous /profile/ -> 302 to /accounts/login/
#   3. login: CSRF-protected POST -> 302; session cookie Secure/HttpOnly/Lax
#   4. authenticated /profile/ -> 200 with the contract lines
#   5. CSRF cookie is Secure
#   6. /feedback/ POST with a valid token -> 200; missing/invalid -> 403
#   7. security headers: HSTS 3600, frame DENY, nosniff, referrer same-origin
#   8. /search/ escapes user input
#
# Usage:  ./project2/scenario-a/scripts/verify-phase1d.sh
# =============================================================================
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-a
ROOT=$(cd "$HERE/../.." && pwd)
CA="$ROOT/secrets/tls/ca.crt"
CURL_IMG="curlimages/curl:latest"
BASE="https://10.20.6.20"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; ERRORS=$((ERRORS+1)); }
step() { printf '\033[1;34m----]\033[0m %s\n' "$*"; }
ERRORS=0

# Credentials live in the git-ignored env file, never in this script.
set -a; . "$HERE/env"; set +a

client() {
    docker run --rm --network container:nr_ue \
        -v "$CA:/etc/telecom-lab/ca.crt:ro" \
        -v "$TMP/client.sh:/client.sh:ro" \
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

echo "PUBLIC_ROOT=$(code "$BASE/")"
echo "PUBLIC_HEALTH=$(code "$BASE/health/")"
echo "PUBLIC_API=$(code "$BASE/api/status/")"
echo "PUBLIC_SEARCH=$(code "$BASE/search/?q=TLS")"
echo "ADMIN=$(code "$BASE/admin/")"

# Anonymous profile: redirect, and where to.
echo "ANON_PROFILE=$(curl -s $C -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 8 "$BASE/profile/")"

# Login page: grab the CSRF cookie and the form token.
curl -s $C -c "$JAR" -D /tmp/login.hdr -o /tmp/login.html --max-time 8 "$BASE/accounts/login/"
echo "LOGIN_GET=$(head -n1 /tmp/login.hdr | tr -d '\r')"
grep -i '^set-cookie: csrftoken=' /tmp/login.hdr | tr -d '\r' | sed 's/^/CSRF_SET_COOKIE=/'
TOKEN=$(sed -n 's/.*name="csrfmiddlewaretoken" value="\([^"]*\)".*/\1/p' /tmp/login.html | head -1)
echo "LOGIN_CSRF_TOKEN=${TOKEN:+present}"

# Authenticate (CSRF-protected POST; Origin matches the HTTPS host).
curl -s $C -b "$JAR" -c "$JAR" -D /tmp/loginpost.hdr -o /dev/null --max-time 8 \
    -H "Origin: $BASE" \
    --data-urlencode "csrfmiddlewaretoken=$TOKEN" \
    --data-urlencode "username=$LAB_USER" \
    --data-urlencode "password=$LAB_PASS" \
    --data-urlencode "next=/profile/" \
    "$BASE/accounts/login/"
echo "LOGIN_POST=$(head -n1 /tmp/loginpost.hdr | tr -d '\r')"
grep -i '^set-cookie: sessionid=' /tmp/loginpost.hdr | tr -d '\r' | sed 's/^/SESSION_SET_COOKIE=/'

# Authenticated profile.
curl -s $C -b "$JAR" -o /tmp/profile.html -w 'PROFILE=%{http_code}\n' --max-time 8 "$BASE/profile/"
grep -o 'Username: [A-Za-z0-9_.-]*' /tmp/profile.html | sed 's/^/PROFILE_LINE=/'
grep -o 'Authenticated: True' /tmp/profile.html | sed 's/^/PROFILE_LINE=/'

# Feedback form: token, valid POST, then the two CSRF negative cases.
curl -s $C -b "$JAR" -o /tmp/feedback.html -w 'FEEDBACK_GET=%{http_code}\n' --max-time 8 "$BASE/feedback/"
FTOKEN=$(sed -n 's/.*name="csrfmiddlewaretoken" value="\([^"]*\)".*/\1/p' /tmp/feedback.html | head -1)
echo "FEEDBACK_CSRF_TOKEN=${FTOKEN:+present}"
curl -s $C -b "$JAR" -o /dev/null -w 'FEEDBACK_OK=%{http_code}\n' --max-time 8 \
    -H "Origin: $BASE" --data-urlencode "csrfmiddlewaretoken=$FTOKEN" \
    --data-urlencode "message=phase 1d acceptance" "$BASE/feedback/"
curl -s $C -b "$JAR" -o /dev/null -w 'FEEDBACK_MISSING_CSRF=%{http_code}\n' --max-time 8 \
    -H "Origin: $BASE" --data-urlencode "message=no token" "$BASE/feedback/"
curl -s $C -b "$JAR" -o /dev/null -w 'FEEDBACK_INVALID_CSRF=%{http_code}\n' --max-time 8 \
    -H "Origin: $BASE" --data-urlencode "csrfmiddlewaretoken=invalid" \
    --data-urlencode "message=bad token" "$BASE/feedback/"

# Security headers on an HTTPS response.
curl -s $C -b "$JAR" -D /tmp/headers.txt -o /dev/null --max-time 8 "$BASE/health/" 
grep -iE '^(strict-transport-security|x-frame-options|x-content-type-options|referrer-policy):' \
    /tmp/headers.txt | tr -d '\r' | sed 's/^/HEADER=/'

# Reflected input must be escaped.
curl -s $C -G --data-urlencode 'q=<script>alert(1)</script>' -o /tmp/search.html --max-time 8 "$BASE/search/"
if grep -q '&lt;script&gt;' /tmp/search.html && ! grep -q '<script>alert(1)</script>' /tmp/search.html; then
    echo "SEARCH_ESCAPED=yes"
else
    echo "SEARCH_ESCAPED=no"
fi
CLIENT

OUT="$TMP/out.txt"
client > "$OUT" 2>&1 || true

get() { sed -n "s/^$1=//p" "$OUT" | head -1; }

step "1. public endpoints"
for pair in "PUBLIC_ROOT:/" "PUBLIC_HEALTH:/health/" "PUBLIC_API:/api/status/" "PUBLIC_SEARCH:/search/"; do
    key=${pair%%:*}; path=${pair#*:}
    v=$(get "$key")
    [[ "$v" == "200" ]] && ok "$path -> 200" || fail "$path -> '${v:-none}'"
done
[[ "$(get ADMIN)" == "302" ]] && ok "/admin/ -> 302 (login)" || fail "/admin/ -> '$(get ADMIN)'"

step "2. anonymous /profile/"
ANON=$(get ANON_PROFILE)
[[ "$ANON" == 302*"/accounts/login/"* ]] && ok "$ANON" || fail "anonymous redirect: '${ANON:-none}'"

step "3. login and session cookie"
[[ "$(get LOGIN_GET)" == *"200"* ]] && ok "login page 200" || fail "login page: $(get LOGIN_GET)"
[[ "$(get LOGIN_POST)" == *"302"* ]] && ok "login POST 302" || fail "login POST: $(get LOGIN_POST)"
SESSION_COOKIE=$(sed -n 's/^SESSION_SET_COOKIE=//p' "$OUT")
[[ "$SESSION_COOKIE" == *"sessionid="* ]] && ok "session cookie set" || fail "no session cookie"
for attr in "Secure" "HttpOnly" "SameSite=Lax"; do
    [[ "$SESSION_COOKIE" == *"$attr"* ]] && ok "session cookie has $attr" || fail "session cookie lacks $attr"
done

step "4. authenticated /profile/"
[[ "$(get PROFILE)" == "200" ]] && ok "profile 200" || fail "profile: '$(get PROFILE)'"
grep -q '^PROFILE_LINE=Username: securityadmin$' "$OUT" && ok "Username: securityadmin" \
    || fail "missing 'Username: securityadmin'"
grep -q '^PROFILE_LINE=Authenticated: True$' "$OUT" && ok "Authenticated: True" \
    || fail "missing 'Authenticated: True'"

step "5. CSRF cookie"
CSRF_COOKIE=$(sed -n 's/^CSRF_SET_COOKIE=//p' "$OUT")
[[ "$CSRF_COOKIE" == *"csrftoken="* ]] && ok "csrftoken set" || fail "no csrftoken cookie"
[[ "$CSRF_COOKIE" == *"Secure"* ]] && ok "csrftoken has Secure" || fail "csrftoken lacks Secure"

step "6. /feedback/ CSRF behaviour"
[[ "$(get FEEDBACK_GET)" == "200" ]] && ok "feedback GET 200" || fail "feedback GET: '$(get FEEDBACK_GET)'"
[[ "$(get FEEDBACK_OK)" == "200" ]] && ok "valid CSRF POST -> 200" || fail "valid POST: '$(get FEEDBACK_OK)'"
[[ "$(get FEEDBACK_MISSING_CSRF)" == "403" ]] && ok "missing CSRF -> 403" \
    || fail "missing CSRF: '$(get FEEDBACK_MISSING_CSRF)'"
[[ "$(get FEEDBACK_INVALID_CSRF)" == "403" ]] && ok "invalid CSRF -> 403" \
    || fail "invalid CSRF: '$(get FEEDBACK_INVALID_CSRF)'"

step "7. security headers"
headers=$(sed -n 's/^HEADER=//p' "$OUT")
has() { grep -qi "^$1" <<<"$headers"; }
has "strict-transport-security: max-age=3600" && ok "HSTS max-age=3600" || fail "HSTS header: $(grep -i strict <<<"$headers")"
has "x-frame-options: DENY" && ok "X-Frame-Options: DENY" || fail "X-Frame-Options missing"
has "x-content-type-options: nosniff" && ok "X-Content-Type-Options: nosniff" || fail "nosniff missing"
has "referrer-policy: same-origin" && ok "Referrer-Policy: same-origin" || fail "referrer policy missing"

step "8. /search/ escaping"
[[ "$(get SEARCH_ESCAPED)" == "yes" ]] && ok "reflected input escaped" \
    || fail "search output is not escaped"

echo
if [[ $ERRORS -eq 0 ]]; then
    ok "Phase 1D complete: authentication, authorization, CSRF and headers enforced."
else
    fail "$ERRORS check(s) failed."
    echo "--- client output ---"
    sed 's/^/       /' "$OUT"
    exit 1
fi
