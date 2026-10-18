#!/usr/bin/env bash
# =============================================================================
# Scenario B — milestone 6: bring up the Data Network (N6) and the application,
# and remove the UPF masquerade so the UE address survives end to end.
#
# Usage:  ./scripts/enable-n6.sh
# =============================================================================
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
UP="$HERE/upstream"
set -a; . "$HERE/.env"; set +a

[[ $EUID -eq 0 ]] || { echo "run with sudo (nsenter is needed for the iperf3 return route)"; exit 1; }
[[ -d "$UP" ]] || { echo "run scripts/fetch-upstream.sh first"; exit 1; }
cd "$UP"

echo "[n6] attaching UPF to dn and starting nginx (${NGINX_IP})"
docker compose -f sa-deploy.yaml -f "$HERE/n6/docker-compose.n6.yaml" up -d --no-build

echo "[n6] waiting for nginx"
for _ in $(seq 1 30); do
    docker exec sb-nginx true 2>/dev/null && break
    sleep 1
done

echo "[n6] removing the UPF masquerade (N6 stays un-NATed)"
# The only POSTROUTING rule inside the UPF is the internet-APN MASQUERADE added
# by tun_if.py; flush it. (fetch-upstream.sh also patches upf_init.sh so a fresh
# deploy never adds it.)
docker exec upf iptables -t nat -F POSTROUTING 2>/dev/null || true

echo "[n6] adding the iperf3 return route (its image has no 'ip'); via nsenter"
IPID=$(docker inspect -f '{{.State.Pid}}' sb-iperf3 2>/dev/null || true)
if [[ -n "$IPID" && "$IPID" != "0" ]]; then
    nsenter -t "$IPID" -n ip route add 10.45.0.0/16 via "$UPF_DN_IP" 2>/dev/null \
        || nsenter -t "$IPID" -n ip route replace 10.45.0.0/16 via "$UPF_DN_IP" 2>/dev/null || true
fi

echo "[n6] (re)asserting the UE route through the tunnel"
docker exec nr_ue ip route replace default dev uesimtun0 2>/dev/null || true
docker exec nr_ue ip route add 10.45.0.0/16 dev uesimtun0 2>/dev/null || true

echo "[n6] checking UE -> nginx"
if docker exec nr_ue ping -c 3 -W 2 "$NGINX_IP" >/dev/null 2>&1; then
    echo "[n6] OK: UE reaches nginx ${NGINX_IP}"
else
    echo "[n6] WARN: UE cannot reach nginx yet (check the UPF dn interface and routes)"
fi

echo
echo "[n6] end-to-end HTTP check from the UE (bash /dev/tcp; the UE image has no curl):"
CODE=$(timeout 10 docker exec nr_ue timeout 6 bash -c "
    exec 3<>/dev/tcp/${NGINX_IP}/80 2>/dev/null || exit 1
    printf 'GET / HTTP/1.0\r\nHost: ${NGINX_IP}\r\n\r\n' >&3
    head -n1 <&3 | tr -d '\r'
" 2>/dev/null || true)
echo "    ${CODE:-<no response>}"

echo "[n6] last nginx access lines (source address):"
docker logs --tail 8 sb-nginx 2>&1 | grep -E '10\.(45|20)\.' || docker logs --tail 3 sb-nginx 2>&1 || true

echo
echo "[n6] no-NAT check: the access log should show a 10.45.0.x client, not ${UPF_DN_IP}."

echo
echo "[n6] iperf3 throughput (client runs inside the UE network namespace):"
docker run --rm --network container:nr_ue networkstatic/iperf3:latest -c "$IPERF_IP" -t 4 2>&1 | tail -6 || true
