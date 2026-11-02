#!/bin/sh
# =============================================================================
# Capture entrypoint. Runs inside the target's network namespace, so the
# interface is the one the Juice Shop traffic really uses.
#
# Usage (from Jenkins):
#   docker run -d --name capture --network container:juice-shop \
#       --cap-add NET_ADMIN --cap-add NET_RAW \
#       -v <host-evidence>:/captures telecom-lab-capture:1.0 \
#       /captures/juice-shop-ci-sqli.pcapng eth0
# =============================================================================
set -eu

OUT="${1:-/captures/juice-shop-ci-sqli.pcapng}"
IFACE="${2:-eth0}"

mkdir -p "$(dirname "$OUT")"
echo "[capture] interface=$IFACE output=$OUT"
exec tcpdump -i "$IFACE" -U -s 0 -w "$OUT"
