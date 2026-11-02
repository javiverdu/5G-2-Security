# =============================================================================
# Project 2 — Scenario A, phase 1C
# Nginx TLS gateway: nginx:latest + iproute2 (route back into the UE PDU pool).
#
# Build:  docker compose -f project2/scenario-a/docker-compose.p2.yaml build nginx
# =============================================================================
FROM nginx:latest

RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Runs before nginx starts (official entrypoint hook), every time the container
# is created. Without this route, replies to 10.45.0.x would leave via the
# Docker gateway and the UE would never see them.
COPY 10-add-ue-route.sh /docker-entrypoint.d/10-add-ue-route.sh
RUN chmod +x /docker-entrypoint.d/10-add-ue-route.sh

COPY conf.d/default.conf /etc/nginx/conf.d/default.conf
