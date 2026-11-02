# =============================================================================
# Project 2 — Scenario B: Jenkins orchestrator (phase 2A)
# Jenkins LTS pinned as required, plus the CLI/tools the pipeline uses.
#
# Build:  docker compose -f project2/scenario-b/docker-compose.security.yaml build jenkins
# =============================================================================
FROM jenkins/jenkins:2.580.1-jdk21

USER root

# Non-interactive tshark: the pipeline only reads PCAPs, never captures.
RUN echo 'wireshark-common wireshark-common/install-setuid boolean false' \
        | debconf-set-selections \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        jq \
        python3 \
        python3-yaml \
        tshark \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# Debian's docker.io package no longer ships the client; the pipeline needs the
# CLI to launch security jobs, so install the pinned static binary.
ARG DOCKER_CLI_VERSION=29.9.2
RUN curl -fsSL \
        "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" \
    | tar -xz --strip-components=1 -C /usr/local/bin docker/docker

# Plugins required by the Jenkinsfile, pinned in plugins.txt.
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# Admin account and authorization, applied on first boot.
COPY init.groovy.d/ /usr/share/jenkins/ref/init.groovy.d/

USER jenkins
