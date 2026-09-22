#!/usr/bin/env bash
# =============================================================================
# Scenario A: Software-Based Telecommunications Network
# Deploys: ue / access / core namespaces + veth links + Docker Data Network
#
# Path: ue -> access -> core -> host (veth-hn) -> docker bridge "datanet"
#                                                       |-> nginx-app  (10.0.4.10)
#                                                       |-> iperf3-srv (10.0.4.20)
#
# Addressing:  ue<->access 10.0.1.0/24 | access<->core 10.0.2.0/24
#              core<->host 10.0.3.0/24 | docker bridge 10.0.4.0/24
#
# Usage:  sudo ./scripts/deploy/setup.sh
# =============================================================================
set -euo pipefail

# ------------------------------ Config --------------------------------------
DN_NET_NAME="datanet"
DN_SUBNET="10.0.4.0/24"
DN_GW="10.0.4.1"
NGINX_IP="10.0.4.10"
IPERF_IP="10.0.4.20"
DAEMON_JSON="/etc/docker/daemon.json"

log() { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root (sudo)."

# ----------------- 0. Docker daemon prerequisite ----------------------------
# Modern Docker (>= 28) hardens its defaults: it drops routed (non-published)
# traffic toward container IPs in raw/PREROUTING and sets FORWARD policy DROP.
# "allow-direct-routing" disables the raw/PREROUTING drops so the Data Network
# can reach its containers in routed mode (no NAT, observable end-to-end path).
if ! grep -qs '"allow-direct-routing"[[:space:]]*:[[:space:]]*true' "$DAEMON_JSON"; then
    log "Enabling Docker daemon 'allow-direct-routing' in $DAEMON_JSON"
    if [[ -s $DAEMON_JSON ]] && command -v python3 >/dev/null; then
        python3 - "$DAEMON_JSON" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["allow-direct-routing"] = True
json.dump(d, open(p, "w"), indent=2)
PY
    elif [[ -s $DAEMON_JSON ]]; then
        cp "$DAEMON_JSON" "$DAEMON_JSON.bak-$(date +%s)"
        echo '{ "allow-direct-routing": true }' > "$DAEMON_JSON"
    else
        echo '{ "allow-direct-routing": true }' > "$DAEMON_JSON"
    fi
    log "Restarting docker daemon to apply the change"
    systemctl restart docker
    sleep 2
fi

# --------------------------- 1. Namespaces ----------------------------------
log "Creating network namespaces: ue, access, core (idempotent)"
for ns in ue access core; do
    if ip netns list | awk '{print $1}' | grep -qx "$ns"; then
        log "namespace $ns already exists"
    else
        ip netns add "$ns"
    fi
    ip netns exec "$ns" ip link set lo up
done

# --------------------------- 2. veth pairs ----------------------------------
# ue <-> access
if ! ip netns exec ue ip link show eth0 &>/dev/null; then
    log "Creating veth pair: ue:eth0 <-> access:eth0 (10.0.1.0/24)"
    ip link add v-ue  type veth peer name v-ac1
    ip link set v-ue  netns ue
    ip link set v-ac1 netns access
    ip netns exec ue     ip link set v-ue  name eth0
    ip netns exec access ip link set v-ac1 name eth0
else
    log "veth ue<->access already present"
fi

# access <-> core
if ! ip netns exec access ip link show eth1 &>/dev/null; then
    log "Creating veth pair: access:eth1 <-> core:eth0 (10.0.2.0/24)"
    ip link add v-ac2 type veth peer name v-co1
    ip link set v-ac2 netns access
    ip link set v-co1 netns core
    ip netns exec access ip link set v-ac2 name eth1
    ip netns exec core   ip link set v-co1 name eth0
else
    log "veth access<->core already present"
fi

# core <-> host (Data Network boundary)
if ! ip netns exec core ip link show eth1 &>/dev/null; then
    log "Creating veth pair: core:eth1 <-> host:veth-hn (10.0.3.0/24)"
    ip link add v-co2 type veth peer name veth-hn
    ip link set v-co2 netns core
    ip netns exec core ip link set v-co2 name eth1
    # veth-hn stays in the root namespace
else
    log "veth core<->host already present"
fi

# --------------------------- 3. Addressing ----------------------------------
log "Assigning IP addresses"
ip netns exec ue     ip addr add 10.0.1.10/24 dev eth0
ip netns exec access ip addr add 10.0.1.1/24  dev eth0
ip netns exec access ip addr add 10.0.2.1/24  dev eth1
ip netns exec core   ip addr add 10.0.2.2/24  dev eth0
ip netns exec core   ip addr add 10.0.3.1/24  dev eth1
ip addr add 10.0.3.2/24 dev veth-hn

log "Bringing interfaces up"
ip netns exec ue     ip link set eth0 up
ip netns exec access ip link set eth0 up
ip netns exec access ip link set eth1 up
ip netns exec core   ip link set eth0 up
ip netns exec core   ip link set eth1 up
ip link set veth-hn up

# --------------------------- 4. Forwarding ----------------------------------
log "Enabling IP forwarding in access, core and host"
ip netns exec access sysctl -qw net.ipv4.ip_forward=1
ip netns exec core   sysctl -qw net.ipv4.ip_forward=1
sysctl -qw net.ipv4.ip_forward=1

# --------------------------- 5. Routing -------------------------------------
log "Installing routes"
# UE: everything via the access router
ip netns exec ue ip route add default via 10.0.1.1
# Access router: Data Network and Docker service network via core
ip netns exec access ip route add 10.0.3.0/24 via 10.0.2.2
ip netns exec access ip route add 10.0.4.0/24 via 10.0.2.2
# Core: return path toward UE via access; Docker service network via host
ip netns exec core ip route add 10.0.1.0/24 via 10.0.2.1
ip netns exec core ip route add 10.0.4.0/24 via 10.0.3.2
# Host: return path toward UE via core
ip route add 10.0.1.0/24 via 10.0.3.1

# ---------------------- 6. Docker Data Network ------------------------------
if ! docker network inspect "$DN_NET_NAME" &>/dev/null; then
    log "Creating Docker bridge network '$DN_NET_NAME' ($DN_SUBNET, gw $DN_GW)"
    docker network create --subnet="$DN_SUBNET" --gateway="$DN_GW" "$DN_NET_NAME" >/dev/null
else
    log "Docker network '$DN_NET_NAME' already exists"
fi

# ------------------------- 7. Services --------------------------------------
if ! docker ps -a --format '{{.Names}}' | grep -qx nginx-app; then
    log "Starting nginx-app ($NGINX_IP:80)"
    docker run -d --name nginx-app --network "$DN_NET_NAME" --ip "$NGINX_IP" \
        --restart unless-stopped nginx:latest >/dev/null
else
    log "Container nginx-app already exists"
fi

if ! docker ps -a --format '{{.Names}}' | grep -qx iperf3-srv; then
    log "Starting iperf3-srv ($IPERF_IP:5201)"
    docker run -d --name iperf3-srv --network "$DN_NET_NAME" --ip "$IPERF_IP" \
        --restart unless-stopped networkstatic/iperf3:latest -s >/dev/null
else
    log "Container iperf3-srv already exists"
fi

# --------------------- 8. Host firewall fixes -------------------------------
# (a) Docker's filter DOCKER chain drops routed traffic toward the bridge
#     ("DROP !br-<id> br-<id>" + FORWARD policy DROP). Allow forwarding from
#     the Data Network boundary into datanet via Docker's DOCKER-USER chain.
log "Allowing routed traffic veth-hn -> $DN_SUBNET in DOCKER-USER"
if iptables -L DOCKER-USER &>/dev/null; then
    iptables -C DOCKER-USER -i veth-hn -d "$DN_SUBNET" -j ACCEPT 2>/dev/null || \
        iptables -I DOCKER-USER -i veth-hn -d "$DN_SUBNET" -j ACCEPT
fi

# (b) Safety net: if raw/PREROUTING drops toward container IPs still exist
#     (e.g. daemon.json was reverted), remove them as a last resort.
if nft list table ip raw &>/dev/null && nft list table ip raw | grep -q '10\.0\.4\.'; then
    log "Removing stale raw/PREROUTING drops (nft table ip raw)"
    nft delete table ip raw
fi

# ------------------------------ Summary --------------------------------------
log "Deployment finished. Namespace and route summary:"
echo
ip netns list
echo
for ns in ue access core; do
    echo "--- $ns ---"
    ip netns exec "$ns" ip -brief addr
    ip netns exec "$ns" ip route
    echo
done
echo "--- host (relevant) ---"
ip -brief addr show veth-hn
ip route show 10.0.1.0/24
echo
docker ps --filter network="$DN_NET_NAME" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
echo
log "Next: verify with  sudo ./scripts/deploy/verify.sh"
