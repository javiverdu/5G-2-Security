#!/bin/sh
# =============================================================================
# Give the gateway a return path into the UE PDU pool.
#
# The UE has 10.45.0.x; replies must go back through the UPF at 10.20.6.2, not
# through the Docker default gateway. The UPF address is fixed by the lab
# compose file (UPF_DN_IP).
# =============================================================================
set -eu

ip route replace 10.45.0.0/16 via 10.20.6.2
echo "[nginx-init] route 10.45.0.0/16 via 10.20.6.2 installed"
