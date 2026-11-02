# =============================================================================
# Project 2 — Scenario B: packet capture job (phase 2A)
#
# The container is started on demand by Jenkins with
#   --network container:juice-shop --cap-add NET_ADMIN --cap-add NET_RAW
# so tcpdump sees the target's own eth0 and cannot miss the traffic.
#
# Build:  docker compose -f project2/scenario-b/docker-compose.security.yaml build capture
# =============================================================================
FROM alpine:3.22

RUN apk add --no-cache tcpdump

COPY capture.sh /usr/local/bin/capture.sh
RUN chmod +x /usr/local/bin/capture.sh

ENTRYPOINT ["/usr/local/bin/capture.sh"]
