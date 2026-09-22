#!/usr/bin/env bash
# =============================================================================
# Scenario A: teardown
# Removes containers, Docker network, namespaces, veth links and host routes.
# Usage:  sudo ./scripts/teardown/cleanup.sh
# =============================================================================
set -uo pipefail

log() { printf '\033[1;34m[cleanup]\033[0m %s\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)."; exit 1; }

log "Removing containers"
docker rm -f nginx-app iperf3-srv 2>/dev/null || true

log "Removing Docker network 'datanet'"
docker network rm datanet 2>/dev/null || true

log "Removing namespaces (this also removes the veth pairs inside them)"
for ns in ue access core; do
    ip netns del "$ns" 2>/dev/null || true
done

log "Removing host-side link, route and firewall rules (if still present)"
ip link del veth-hn 2>/dev/null || true
ip route del 10.0.1.0/24 via 10.0.3.1 2>/dev/null || true
iptables -D DOCKER-USER -i veth-hn -d 10.0.4.0/24 -j ACCEPT 2>/dev/null || true
# safety net: stale raw/PREROUTING drops toward our container subnet
if nft list table ip raw &>/dev/null && nft list table ip raw | grep -q '10\.0\.4\.'; then
    nft delete table ip raw 2>/dev/null || true
fi

log "Done."
