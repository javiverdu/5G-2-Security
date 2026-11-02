#!/usr/bin/env bash
# =============================================================================
# Project 2 — Phase 1C acceptance: lab PKI + Nginx TLS gateway.
#
# Checks, in order:
#   1. the gateway image exists and runs the container scenario-b-nginx
#   2. it is on dn-net 10.20.6.20 and app-net 10.20.8.10, and sb-nginx is gone
#   3. the server certificate matches the contract (issuer, SAN, validity)
#   4. the CA private key is mounted into no container
#   5. HTTP from the UE returns 301 to HTTPS
#   6. HTTPS from the UE validates against the CA (no -k) and returns 200
#   7. TLS 1.2 and TLS 1.3 handshakes succeed, verified against the CA
#   8. the gateway sees the real UE address (no NAT) in its access log
#
# "From the UE" means a throwaway client sharing the network namespace of
# nr_ue, so the request enters the PDU session and uesimtun0, exactly like
# traffic originated by the UE container.
#
# Usage:  ./project2/scenario-a/scripts/verify-phase1c.sh
# =============================================================================
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-a
ROOT=$(cd "$HERE/../.." && pwd)
IMG="telecom-lab-nginx:p2"
CT="scenario-b-nginx"
CA="$ROOT/secrets/tls/ca.crt"
CRT="$ROOT/secrets/tls/server.crt"
CURL_IMG="curlimages/curl:latest"
EXPECTED='{"service": "project2-django", "status": "ok", "project": "Telecommunication Security"}'

ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; ERRORS=$((ERRORS+1)); }
step() { printf '\033[1;34m----]\033[0m %s\n' "$*"; }
ERRORS=0

# Client that shares the UE network namespace.
ue_run() {
    docker run --rm --network container:nr_ue \
        -v "$CA:/etc/telecom-lab/ca.crt:ro" "$@"
}

step "1. gateway image and container"
docker image inspect "$IMG" >/dev/null 2>&1 && ok "$IMG built" \
    || fail "$IMG missing (run ./project2/scenario-a/scripts/up.sh)"
RUNNING_IMG=$(docker inspect -f '{{.Config.Image}}' "$CT" 2>/dev/null || true)
[[ "$RUNNING_IMG" == "$IMG" ]] && ok "$CT runs $IMG" \
    || fail "$CT runs '${RUNNING_IMG:-none}' (run ./project2/scenario-a/scripts/up.sh)"

step "2. addressing and network isolation"
DN=$(docker inspect -f '{{with index .NetworkSettings.Networks "dn-net"}}{{.IPAddress}}{{end}}' "$CT" 2>/dev/null || true)
AN=$(docker inspect -f '{{with index .NetworkSettings.Networks "app-net"}}{{.IPAddress}}{{end}}' "$CT" 2>/dev/null || true)
[[ "$DN" == "10.20.6.20" ]] && ok "dn-net 10.20.6.20" || fail "dn-net address '${DN:-none}'"
[[ "$AN" == "10.20.8.10" ]] && ok "app-net 10.20.8.10" || fail "app-net address '${AN:-none}'"
if docker inspect sb-nginx >/dev/null 2>&1; then
    fail "sb-nginx still exists (it would also claim 10.20.6.20)"
else
    ok "sb-nginx removed"
fi
if docker inspect "$CT" >/dev/null 2>&1; then
    ok "$CT running"
else
    fail "$CT missing"
fi

step "3. server certificate"
if [[ -f "$CRT" ]]; then
    SUBJ=$(openssl x509 -in "$CRT" -noout -subject | sed 's/^subject=//')
    ISSUER=$(openssl x509 -in "$CRT" -noout -issuer | sed 's/^issuer=//')
    SAN=$(openssl x509 -in "$CRT" -noout -ext subjectAltName | tail -1 | sed 's/^ *//')
    END=$(openssl x509 -in "$CRT" -noout -enddate | cut -d= -f2)
    echo "       subject: $SUBJ"
    echo "       issuer : $ISSUER"
    echo "       expires: $END"
    echo "       SAN    : $SAN"
    if openssl verify -CAfile "$CA" "$CRT" >/dev/null 2>&1; then
        ok "certificate verifies against the lab CA"
    else
        fail "certificate does not verify against $CA"
    fi
    grep -q 'IP Address:10.20.6.20' <<<"$SAN" && ok "SAN contains IP 10.20.6.20" \
        || fail "SAN missing IP 10.20.6.20"
    grep -q 'DNS:telecom-lab.local' <<<"$SAN" && ok "SAN contains telecom-lab.local" \
        || fail "SAN missing telecom-lab.local"
    grep -q 'DNS:localhost' <<<"$SAN" && ok "SAN contains localhost" \
        || fail "SAN missing localhost"
else
    fail "missing $CRT (run ./project2/scenario-a/scripts/gen-pki.sh)"
fi

step "4. the CA private key is mounted into no container"
LEAK=$(for c in $(docker ps -q); do
    docker inspect -f '{{range .Mounts}}{{.Source}} {{end}}' "$c" 2>/dev/null
done | grep -c 'ca\.key' || true)
if [[ "${LEAK:-0}" -eq 0 ]]; then
    ok "no running container mounts ca.key"
else
    fail "$LEAK container mount(s) expose ca.key"
fi

step "5. HTTP from the UE redirects to HTTPS"
REDIR=$(ue_run "$CURL_IMG" -s -o /dev/null -w '%{http_code} %{redirect_url}' \
    --max-time 6 http://10.20.6.20/health/ 2>/dev/null || true)
if [[ "$REDIR" == "301 https://10.20.6.20/health/" ]]; then
    ok "301 -> $REDIR"
else
    fail "unexpected redirect: '${REDIR:-none}' (expected 301 to https://10.20.6.20/health/)"
fi

step "6. HTTPS from the UE, CA-validated, no -k"
RESP=$(ue_run "$CURL_IMG" -s --max-time 8 --cacert /etc/telecom-lab/ca.crt \
    -w '\n%{http_code}' https://10.20.6.20/health/ 2>/dev/null || true)
CODE=${RESP##*$'\n'}
BODY=${RESP%$'\n'*}
[[ "$CODE" == "200" ]] && ok "HTTPS 200 with the lab CA" || fail "HTTPS status '${CODE:-none}'"
[[ "$BODY" == "$EXPECTED" ]] && ok "exact JSON body through TLS" || fail "unexpected body through TLS: ${BODY:-<none>}"

step "7. TLS 1.2 and TLS 1.3 handshakes"
for v in "-tls1_2 TLSv1.2" "-tls1_3 TLSv1.3"; do
    FLAG=${v%% *}; WANT=${v##* }
    OUT=$(ue_run --entrypoint openssl "$IMG" s_client -connect 10.20.6.20:443 \
        -servername telecom-lab.local -CAfile /etc/telecom-lab/ca.crt "$FLAG" \
        -verify_return_error </dev/null 2>&1 || true)
    PROTO=$(grep -oE 'Protocol *: *TLSv1\.[0-9]' <<<"$OUT" | head -1 | awk '{print $NF}')
    VRC=$(grep -oE 'Verify return code: [0-9]+ \(ok\)' <<<"$OUT" | head -1)
    if [[ "$PROTO" == "$WANT" && -n "$VRC" ]]; then
        ok "$WANT handshake, certificate verified"
    else
        fail "$WANT handshake failed (protocol='${PROTO:-none}')"
    fi
done

step "8. real UE source address in the access log (no NAT)"
UEIP=$(docker exec nr_ue ip -4 -brief addr show uesimtun0 2>/dev/null | awk '{print $3}' | cut -d/ -f1)
SEEN=$(docker logs --tail 40 "$CT" 2>&1 | grep -oE '^10\.45\.[0-9]+\.[0-9]+' | sort -u | tr '\n' ' ')
if [[ -n "$SEEN" ]]; then
    ok "gateway saw ${SEEN}(UE is ${UEIP:-unknown})"
else
    fail "no 10.45.x client in the gateway access log"
fi

echo
if [[ $ERRORS -eq 0 ]]; then
    ok "Phase 1C complete: HTTP 301 -> TLS 1.2/1.3 -> Django, trusted from the UE."
else
    fail "$ERRORS check(s) failed."
    exit 1
fi
