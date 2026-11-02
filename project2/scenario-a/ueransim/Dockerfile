# =============================================================================
# telecom-lab-ueransim:3.3.0-p2 — Project 2, Scenario A, phase 1A
#
# Self-contained build of UERANSIM v3.3.0 (the version the brief specifies)
# plus the route watcher. It replaces the Project 1 image as the base for both
# nr_gnb and nr_ue, so the whole RAN runs the same pinned version.
#
# Project 1 used docker_ueransim:latest, which upstream builds from
# UERANSIM v3.2.6. Version drift is a compliance problem, so the tag is pinned
# here instead of inheriting whatever the prebuilt image contains.
#
# Build:  ./scripts/build.sh
# =============================================================================
FROM ubuntu:jammy AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        make \
        g++ \
        libsctp-dev \
        lksctp-tools \
        git \
        ca-certificates \
        libssl-dev \
        cmake && \
    rm -rf /var/lib/apt/lists/*

ARG UERANSIM_TAG=v3.3.0
RUN git clone --depth 1 --branch "${UERANSIM_TAG}" \
        https://github.com/aligungr/UERANSIM /UERANSIM && \
    make -C /UERANSIM -j"$(nproc)"

# --- runtime -----------------------------------------------------------------
FROM ubuntu:jammy

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        libsctp-dev \
        lksctp-tools \
        iproute2 \
        iptables \
        netbase \
        ifupdown \
        net-tools \
        iputils-ping \
        curl \
        ca-certificates && \
    apt-get autoremove -y && apt-get autoclean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /UERANSIM/build /UERANSIM/build
COPY --from=builder /UERANSIM/config /UERANSIM/config

COPY ueransim_image_init.sh /ueransim_image_init.sh
COPY p2-init.sh /usr/local/bin/p2-init.sh
RUN chmod +x /usr/local/bin/p2-init.sh /ueransim_image_init.sh

WORKDIR /UERANSIM/build
CMD ["/usr/local/bin/p2-init.sh"]
