# =============================================================================
# Project 2 — Scenario B: Selenium Grid + browser node (phase 2A)
#
# The delivered environment expects the local image name telecom-lab-selenium:1.0.
# It is a pinned Selenium standalone grid with Chrome, so one container offers
# both the grid endpoint (:4444) and a ready browser node.
#
# Build:  docker compose -f project2/scenario-b/docker-compose.security.yaml build selenium
# =============================================================================
FROM selenium/standalone-chrome:155.0-20261010

# Label only; behaviour comes from the pinned upstream image.
LABEL org.telecom-lab.image="telecom-lab-selenium" \
      org.telecom-lab.version="1.0" \
      org.telecom-lab.upstream="selenium/standalone-chrome:155.0-20261010"
