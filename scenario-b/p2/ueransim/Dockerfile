#!/bin/bash
# =============================================================================
# telecom-lab-ueransim:3.3.0-p2 — Project 2 Phase 1A
#
# Built ON TOP of the Project 1 base image (docker_ueransim) so the rest of the
# 5G SA deployment is untouched. The only change is the init wrapper: a watcher
# keeps the user-plane route installed after every (re)registration, so traffic
# toward N6 always leaves via uesimtun0 even if the UE container restarts.
#
# Base CMD: /ueransim_image_init.sh   (upstream ueransim image)
# =============================================================================
FROM docker_ueransim:latest

COPY p2-init.sh /usr/local/bin/p2-init.sh
RUN chmod +x /usr/local/bin/p2-init.sh

CMD ["/usr/local/bin/p2-init.sh"]
