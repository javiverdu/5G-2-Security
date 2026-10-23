#!/bin/bash
# =============================================================================
# p2-init.sh — init wrapper for telecom-lab-ueransim:3.3.0-p2 (Phase 1A)
#
# Starts a route watcher and then hands control to the original UERANSIM init.
#
# Why: UERANSIM creates uesimtun0 at PDU-session setup but does NOT install any
# route for it, so traffic toward N6 would leave via the management interface
# (eth0) and be dropped. Project 1 fixed this from the host (deploy.sh), which
# is lost whenever the UE container restarts. Project 2 makes the route a
# property of the UE image.
# =============================================================================
set -uo pipefail

# --- route watcher: runs for the whole life of the container ----------------
(
    while true; do
        if ip link show uesimtun0 >/dev/null 2>&1; then
            # user plane: everything except the management subnet goes via the
            # 5G session (the connected 172.22.0.0/24 route is kept by the kernel)
            ip route replace default dev uesimtun0 2>/dev/null || true
            ip route replace 10.45.0.0/16 dev uesimtun0 2>/dev/null || true
        fi
        sleep 5
    done
) &

# --- original UERANSIM init (registration, TUN creation, interactive shell) --
exec /ueransim_image_init.sh "$@"
