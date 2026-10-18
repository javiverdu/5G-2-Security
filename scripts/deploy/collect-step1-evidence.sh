#!/usr/bin/env bash
# =============================================================================
# Scenario A — Step 1: collect raw evidence
#
# Regenerates the raw command output for the Step 1 report into results/step1/,
# replacing the earlier summarised files with real, reproducible output.
#
# Produces:
#   00-verify.txt               pass/fail end-to-end checks (verify.sh)
#   01-namespaces-interfaces.txt  ip netns list + ip -brief addr per node
#   02-routing-tables.txt       ip route per node + ip_forward flags
#   03-docker-network.txt       docker network inspect (raw) + docker ps + IPs
#   04-listening-ports.txt      listening sockets inside each container netns
#   05-e2e-ping.txt             hop-by-hop ping with TTL evidence
#   06-curl-http.txt            HTTP GET via nginx (application test)
#   07-iperf3.txt               iperf3 TCP throughput test
#   08-firewall-state.txt       nft/iptables state + route lookup
#   09-container-inspect.txt    raw container network settings
#   10-packet-path.txt          (optional, --with-capture) packet-level path
#
# Usage:
#   sudo ./scripts/deploy/collect-step1-evidence.sh
#   sudo ./scripts/deploy/collect-step1-evidence.sh --with-capture
#
# NOTE: must run as root. `nsenter -t <pid> -n` needs CAP_SYS_ADMIN, which is why
# running it as a normal user fails with "fallo al volver a asociar al espacio de
# nombres: Operación no permitida".
# =============================================================================
set -uo pipefail

WITH_CAPTURE=0
[[ "${1:-}" == "--with-capture" ]] && WITH_CAPTURE=1

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT="$ROOT/results/step1"
CAP="$ROOT/captures/step1"
mkdir -p "$OUT"

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)."; exit 1; }

log() { printf '\033[1;34m[evidence]\033[0m %s\n' "$*"; }

# ------------------------------ preflight -----------------------------------
for ns in ue access core; do
    ip netns list | awk '{print $1}' | grep -qx "$ns" \
        || { echo "missing namespace '$ns' — run scripts/deploy/setup.sh first"; exit 1; }
done
for c in nginx-app iperf3-srv; do
    docker inspect "$c" &>/dev/null \
        || { echo "missing container '$c' — run scripts/deploy/setup.sh first"; exit 1; }
done

# --------------------------- 00. verify.sh ----------------------------------
if [[ -x "$ROOT/scripts/deploy/verify.sh" ]]; then
    log "Running scripts/deploy/verify.sh -> 00-verify.txt"
    "$ROOT/scripts/deploy/verify.sh" > "$OUT/00-verify.txt" 2>&1 || true
fi

# ---------------------- 01. namespaces + interfaces -------------------------
log "Collecting namespaces and interfaces -> 01-namespaces-interfaces.txt"
{
    echo "# date"
    date
    echo
    echo "# ip netns list"
    ip netns list
    for ns in ue access core; do
        echo
        echo "# ip -brief addr ($ns)"
        ip netns exec "$ns" ip -brief addr
    done
    echo
    echo "# host: Data Network boundary + docker bridge"
    ip -brief addr show veth-hn
    br=$(ip -o link show | awk -F': ' '/br-[0-9a-fA-F]+/{print $2; exit}')
    [[ -n "${br:-}" ]] && ip -brief addr show "$br"
} > "$OUT/01-namespaces-interfaces.txt"

# --------------------------- 02. routing ------------------------------------
log "Collecting routing tables -> 02-routing-tables.txt"
{
    for ns in ue access core; do
        echo "# ip route ($ns)"
        ip netns exec "$ns" ip route
        echo
    done
    echo "# ip route (host)"
    ip route
    echo
    echo "# ip_forward flags"
    for ns in access core; do
        printf '%s: ' "$ns"
        ip netns exec "$ns" sysctl -n net.ipv4.ip_forward
    done
    printf 'host: '
    sysctl -n net.ipv4.ip_forward
} > "$OUT/02-routing-tables.txt"

# --------------------------- 03. docker -------------------------------------
log "Collecting Docker network/services -> 03-docker-network.txt"
{
    echo "# docker network inspect datanet"
    docker network inspect datanet
    echo
    echo "# docker ps"
    docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
    echo
    echo "# container addresses"
    for c in nginx-app iperf3-srv; do
        printf '%s -> %s\n' "$c" \
            "$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$c")"
    done
} > "$OUT/03-docker-network.txt"

# ----------------------- 04. listening ports --------------------------------
log "Collecting listening ports (needs root/nsenter) -> 04-listening-ports.txt"
{
    for c in nginx-app iperf3-srv; do
        echo "# listening sockets inside $c (container netns)"
        pid=$(docker inspect -f '{{.State.Pid}}' "$c")
        nsenter -t "$pid" -n ss -tlnp 2>&1
        nsenter -t "$pid" -n ss -ulnp 2>&1
        echo
    done
} > "$OUT/04-listening-ports.txt"

# --------------------------- 05. ping ---------------------------------------
log "Collecting hop-by-hop ping -> 05-e2e-ping.txt"
{
    for t in 10.0.1.1 10.0.2.2 10.0.3.2 10.0.4.10 10.0.4.20; do
        echo "# ping -c2 $t from ue"
        ip netns exec ue ping -c2 -W2 "$t"
        echo
    done
} > "$OUT/05-e2e-ping.txt"

# --------------------------- 06. curl ---------------------------------------
log "Collecting HTTP application test -> 06-curl-http.txt"
{
    echo "# curl http://10.0.4.10/ from ue"
    ip netns exec ue curl -s http://10.0.4.10/
    echo
    echo "---"
    ip netns exec ue curl -s -o /dev/null \
        -w 'HTTP %{http_code} | connect %{time_connect}s | total %{time_total}s | size %{size_download} bytes\n' \
        http://10.0.4.10/
} > "$OUT/06-curl-http.txt"

# --------------------------- 07. iperf3 -------------------------------------
log "Collecting iperf3 TCP test -> 07-iperf3.txt"
{
    echo "# iperf3 TCP: ue -> 10.0.4.20 (5 s)"
    ip netns exec ue iperf3 -c 10.0.4.20 -t 5
} > "$OUT/07-iperf3.txt"

# --------------------------- 08. firewall -----------------------------------
log "Collecting firewall/forwarding state -> 08-firewall-state.txt"
{
    echo "# nft tables"
    nft list tables 2>/dev/null || echo "(nft unavailable)"
    echo
    echo "# iptables DOCKER-USER"
    iptables -L DOCKER-USER -v -n 2>/dev/null || echo "(iptables unavailable)"
    echo
    echo "# iptables FORWARD"
    iptables -L FORWARD -v -n 2>/dev/null || true
    echo
    echo "# host route lookup toward the service network"
    ip route get 10.0.4.10 2>/dev/null || true
} > "$OUT/08-firewall-state.txt"

# ---------------------- 09. container network settings ----------------------
log "Collecting raw container network settings -> 09-container-inspect.txt"
{
    for c in nginx-app iperf3-srv; do
        echo "# docker inspect $c (network settings)"
        docker inspect -f '{{json .NetworkSettings.Networks}}' "$c"
        echo
    done
} > "$OUT/09-container-inspect.txt"

# ---------------------- 10. optional packet path ----------------------------
if [[ $WITH_CAPTURE -eq 1 ]]; then
    if command -v tcpdump >/dev/null; then
        log "Capturing one HTTP GET at three points -> 10-packet-path.txt"
        mkdir -p "$CAP"
        pid=$(docker inspect -f '{{.State.Pid}}' nginx-app)
        ip netns exec ue     tcpdump -i eth0 -w "$CAP/e2e-http-ue.pcap"    -U -q ip &
        tcpdump -i veth-hn   -w "$CAP/e2e-http-host.pcap" -U -q ip &
        nsenter -t "$pid" -n tcpdump -i eth0 -w "$CAP/e2e-http-nginx.pcap" -U -q ip &
        sleep 1
        ip netns exec ue curl -s -o /dev/null http://10.0.4.10/
        sleep 1
        kill -INT $(jobs -p) 2>/dev/null || true
        wait 2>/dev/null || true
        {
            echo "# packet path of a single HTTP GET (curl ue -> 10.0.4.10:80)"
            for f in e2e-http-ue e2e-http-host e2e-http-nginx; do
                echo
                echo "## $f"
                echo "frames: $(tcpdump -nr "$CAP/$f.pcap" 2>/dev/null | wc -l)"
                tcpdump -nr "$CAP/$f.pcap" 2>/dev/null | head -6
            done
        } > "$OUT/10-packet-path.txt"
    else
        log "tcpdump not found; skipping --with-capture"
    fi
fi

# ------------------------------ ownership -----------------------------------
# When invoked through sudo, files are created as root; hand them back.
if [[ -n "${SUDO_USER:-}" ]]; then
    chown -R "$SUDO_USER":"$SUDO_USER" "$OUT" 2>/dev/null || true
    [[ -d "$CAP" ]] && chown -R "$SUDO_USER":"$SUDO_USER" "$CAP" 2>/dev/null || true
fi

log "Done. Files in $OUT:"
ls -1 "$OUT"
