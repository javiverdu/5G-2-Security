# 5G-project-RTU

**Project 1: Network Deployment, Measurement, and Observability — Scenario A (Linux network namespaces) and Scenario B (5G Standalone)**

A university project that examines the deployment and operation of software-based
telecommunications networks from the perspective of a network engineer. The goal is to
establish an operational end-to-end path, observe how traffic behaves across the
system, quantify service performance under controlled conditions, and explain normal
operation and degradation with packet-, system- and application-level evidence.

- **Scenario A** — a hybrid Linux + Docker network (`UE → access → core → Data
  Network`) built with `ip netns` and veth pairs; see [Architecture](#architecture--scenario-a).
- **Scenario B** — a 5G Standalone network (`UE → gNB → UPF → N6 → application`)
  built with Open5GS + UERANSIM; see [Scenario B](#scenario-b-5g-standalone).

> **Workflow:** Deploy → Verify → Observe → Measure → Diagnose → Explain

---

## Contents

- [Architecture (Scenario A)](#architecture--scenario-a)
- [Scenario B (5G Standalone)](#scenario-b-5g-standalone)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Quickstart](#quickstart)
- [Project Status & Activity Log](#project-status--activity-log)
- [Documentation](#documentation)

---

## Architecture — Scenario A

> Scenario B (5G Standalone) is described in
> [Scenario B](#scenario-b-5g-standalone) below and in
> [`scenario-b/README.md`](scenario-b/README.md).

Scenario A is a **hybrid Linux + Docker** network running on a single Linux VM.
Linux network namespaces implement the UE, the access router and the core/gateway;
a Docker user-defined bridge extends the Data Network toward containerised services.
The path is **fully routed (no NAT)** so that captures show real end-to-end addresses.

```mermaid
flowchart LR
    subgraph NS["Linux network namespaces (veth pairs)"]
        direction LR
        UE["ue<br/>10.0.1.10/24<br/>gw 10.0.1.1"]
        ACC["access · router<br/>eth0 10.0.1.1/24<br/>eth1 10.0.2.1/24"]
        CORE["core · gateway<br/>eth0 10.0.2.2/24<br/>eth1 10.0.3.1/24"]
        HOST["host · Data Network boundary<br/>veth-hn 10.0.3.2/24"]
    end

    subgraph DK["Docker bridge datanet - 10.0.4.0/24 (gw 10.0.4.1)"]
        direction LR
        NGINX["nginx-app<br/>10.0.4.10:80/tcp"]
        IPERF["iperf3-srv<br/>10.0.4.20:5201/tcp+udp"]
    end

    UE   -- "10.0.1.0/24" --> ACC
    ACC  -- "10.0.2.0/24" --> CORE
    CORE -- "10.0.3.0/24" --> HOST
    HOST -- "routed, no NAT" --> DK

    classDef ns fill:#dbeafe,stroke:#2563eb,color:#111;
    classDef dk fill:#ffedd5,stroke:#ea580c,color:#111;
    class UE,ACC,CORE,HOST ns;
    class NGINX,IPERF dk;
```

**Routing in one line:** `ue` defaults to the access router; `access` and `core`
forward the `10.0.4.0/24` service network onward; the host routes the return path
`10.0.1.0/24` back through core. IP forwarding is enabled in `access`, `core` and the
host. Full addressing and routing tables are in
[`docs/addressing-plan.md`](docs/addressing-plan.md).

## Technology Stack

### Scenario A (Linux + Docker)

| Category | Technology | Purpose |
|---|---|---|
| Network isolation | Linux network namespaces (`ip netns`) | UE, access router, core/gateway |
| Virtual links | veth pairs | Point-to-point links between namespaces |
| Containerisation | Docker + user-defined bridge | Data Network extension and service hosting |
| Application service | Nginx (official image) | HTTP server on `10.0.4.10:80` |
| Measurement endpoint | `networkstatic/iperf3` | TCP/UDP throughput endpoint on `10.0.4.20:5201` |
| Traffic generation | `ping`, `curl`, `iperf3` | ICMP, HTTP and TCP/UDP tests |
| Capture & analysis | `tcpdump`, `tshark` | Multi-point packet evidence |
| Impairment | Linux `tc` + NetEm | Controlled delay, loss and bandwidth limits |
| Routing & addressing | `iproute2` (`ip`) | Interfaces, routes, forwarding |
| Plotting | Python 3 + `matplotlib` | Comparative tables and plots |

### Scenario B (5G SA)

| Category | Technology | Purpose |
|---|---|---|
| 5G core | Open5GS | AMF, SMF, UPF, NRF, AUSF, UDM, UDR, PCF, BSF, NSSF, SCP |
| UE / gNB | UERANSIM | simulated 5G UE and gNodeB |
| Orchestration | Docker Compose | single-VM 5G SA deployment |
| Data Network (N6) | `nginx` + `networkstatic/iperf3` | application + throughput endpoint, routed without NAT |
| Observability | Prometheus + Grafana | NF metrics on `:9091` and dashboards |

## Repository Structure

```
5G-project-RTU/
├── README.md
├── docs/                     # plans, step reports, capture/screenshots plans, final report, img/
├── scenario-b/               # Scenario B: 5G SA (Open5GS + UERANSIM)
│   ├── README.md
│   ├── .env
│   ├── docs/                 # addressing, capture-points, observation, performance,
│   │                         # observability, step-log, final-report
│   ├── grafana/              # Grafana provisioning (datasource + dashboard)
│   ├── n6/                   # N6 Compose override (nginx + iperf3, no NAT)
│   └── scripts/              # fetch-upstream, deploy, verify, enable-n6, capture,
│                             # capture-control, analyze, impair, measure, run-all,
│                             # recount-retrans, metrics-check, grafana-import, plot, cleanup
├── scripts/                  # Scenario A
│   ├── deploy/               # setup.sh, verify.sh, collect-step1-evidence.sh
│   ├── observe/              # capture.sh, analyze.sh, gui-workspace.sh   (Step 2)
│   ├── measure/              # impair.sh, measure.sh, run-all.sh, recount-retrans.sh, plot.py (Step 3)
│   └── teardown/             # cleanup.sh
├── captures/                 # raw .pcap files (git-ignored): step2/ (A), scenario-b/ (B)
└── results/                  # step1..step3 (A), scenario-b (B)
```

## Prerequisites

- Linux VM (Ubuntu) with root/sudo access.
- `iproute2` (provides `ip` and `tc` with NetEm).
- Docker Engine (user-defined bridge networks and containers).
- `iperf3`, `tcpdump`, `tshark`, `curl`, `ping`; optional `python3` + `matplotlib`.

```bash
sudo apt update
sudo apt install -y iproute2 iputils-ping iperf3 tcpdump tshark curl python3 python3-pip python3-matplotlib
# Docker Engine: https://docs.docker.com/engine/install/
```

## Quickstart

```bash
git clone <repository-url> && cd 5G-project-RTU

sudo ./scripts/deploy/setup.sh       # build namespaces, veths, routes, Docker services
sudo ./scripts/deploy/verify.sh      # end-to-end checks (ICMP, HTTP, iperf3)
sudo ./scripts/deploy/collect-step1-evidence.sh   # regenerate raw Step 1 evidence

sudo ./scripts/measure/run-all.sh    # baseline + degraded measurement set
python3 ./scripts/measure/plot.py    # comparative table + plots

sudo ./scripts/teardown/cleanup.sh   # remove namespaces, links and containers
```

## Scenario B (5G Standalone)

Scenario B builds the reference 5G architecture on the same Ubuntu VM with Docker
Compose: **UE (UERANSIM) → gNB → UPF → N6 → application**, with Open5GS as the
core. The path is routed with **no NAT** on N6, so the UE session address
(`10.45.0.x`) is visible end to end.

- Plan & run order: [`scenario-b/README.md`](scenario-b/README.md) ·
  addressing: [`scenario-b/docs/addressing-plan.md`](scenario-b/docs/addressing-plan.md)
- Page 3 — deployment & end-to-end (7/7 checks): [`scenario-b/docs/final-report.md`](scenario-b/docs/final-report.md)
- Page 4 — packet observation (GTP-U on N3 vs plain IP on N6): [`scenario-b/docs/traffic-observation.md`](scenario-b/docs/traffic-observation.md)
- Page 5 — performance & degradation (NetEm): [`scenario-b/docs/performance-measurement.md`](scenario-b/docs/performance-measurement.md)
- Page 6 — observability (Prometheus + Grafana): [`scenario-b/docs/observability.md`](scenario-b/docs/observability.md)
- Runbook & troubleshooting: [`scenario-b/docs/step-log.md`](scenario-b/docs/step-log.md)

## Project Status & Activity Log

| Scenario | Step / Page | Description | Status | Evidence |
|---|---|---|---|---|
| A | 0 | Repository scaffold, addressing plan, deploy/verify/teardown scripts | ✅ Done | `docs/addressing-plan.md`, `scripts/` |
| A | 1 | Network deployment and end-to-end operation | ✅ Done | `docs/step1-network-deployment.md`, `results/step1/` |
| A | 2 | Traffic observation and protocol behavior | ✅ Done | `docs/step2-traffic-observation.md`, `results/step2/`, `captures/step2/` |
| A | 3 | Performance measurement and network degradation | ✅ Done | `docs/step3-performance-measurement.md`, `results/step3/` |
| B | 3 | 5G SA deployment and end-to-end operation (7/7 checks) | ✅ Done | `scenario-b/docs/final-report.md` §4, `results/scenario-b/` |
| B | 4 | Traffic observation — GTP-U envelope on N3 vs plain IP on N6 | ✅ Done | `scenario-b/docs/traffic-observation.md`, `captures/scenario-b/` |
| B | 5 | Performance measurement and degradation (delay/loss/rate) | ✅ Done | `scenario-b/docs/performance-measurement.md`, `results/scenario-b/` |
| B | 6 | Observability (Prometheus + Grafana) | ✅ Done | `scenario-b/docs/observability.md`, `docs/img/sb-p6-*` |

| Date | Activity | Outcome |
|---|---|---|
| 2026-09-21 | Repository scaffold and addressing plan (10.0.1–10.0.4.0/24 scheme) | `docs/addressing-plan.md` |
| 2026-09-21 | Deploy / verify / teardown scripts | `scripts/deploy/`, `scripts/teardown/` |
| 2026-09-21 | **Step 1** — topology deployed on the lab VM; Docker 29 hardened forwarding diagnosed and fixed (`allow-direct-routing` + `DOCKER-USER`); path verified (HTTP 200, iperf3 ≈ 36 Gbit/s) | `docs/step1-network-deployment.md`, `results/step1/` |
| 2026-09-22 | **Step 2** — six-point captures (ICMP/TCP/UDP/HTTP) and tshark dissection; AppArmor `tshark` confinement worked around with `aa-exec` | `docs/step2-traffic-observation.md`, `results/step2/`, `captures/step2/` |
| 2026-09-22 | **Step 3** — baseline + delay/loss/rate conditions with NetEm; comparative table and plots | `docs/step3-performance-measurement.md`, `results/step3/` |
| 2026-10-12 | **Scenario B page 3** — Open5GS + UERANSIM deployed; registration, PDU session and UE route; N6 (nginx + iperf3) routed without NAT; all 7 checks green | `scenario-b/`, `results/scenario-b/` |
| 2026-10-13 | **Scenario B page 4** — five-point captures showing the GTP-U envelope on N3 vs the plain IP flow on N6; tshark analysis | `scenario-b/docs/traffic-observation.md`, `captures/scenario-b/` |
| 2026-10-18 | **Scenario B pages 5–6** — NetEm conditions (delay/loss/rate), comparative table/plot; Grafana dashboard imported; screenshots | `scenario-b/docs/performance-measurement.md`, `observability.md`, `docs/img/sb-*` |

## Documentation

| Document | Contents |
|---|---|
| [`docs/addressing-plan.md`](docs/addressing-plan.md) | Subnet relationships, interface/IP addressing, routing plan |
| [`docs/step1-network-deployment.md`](docs/step1-network-deployment.md) | Deployment, end-to-end verification, path analysis, Docker diagnosis |
| [`docs/step2-traffic-observation.md`](docs/step2-traffic-observation.md) | ICMP/TCP/UDP/HTTP packet-level observation across six capture points |
| [`docs/step3-performance-measurement.md`](docs/step3-performance-measurement.md) | Baseline and degraded-condition performance study |
| [`docs/final-report.md`](docs/final-report.md) | Final report (Scenarios A & B), requirement coverage and evidence index |
| [`docs/screenshots-plan.md`](docs/screenshots-plan.md) | Screenshot checklist for the final report (`docs/img/`) |
| [`docs/capture-points.md`](docs/capture-points.md) | Scenario A packet-capture points |
| [`scenario-b/README.md`](scenario-b/README.md) | Scenario B (5G SA) planning, roles, interfaces and run order |
| [`scenario-b/docs/final-report.md`](scenario-b/docs/final-report.md) | Scenario B (5G SA) consolidated report (pages 3–6) |
| [`scenario-b/docs/step-log.md`](scenario-b/docs/step-log.md) | Scenario B runbook & troubleshooting |
| [`scenario-b/docs/screenshots-plan.md`](scenario-b/docs/screenshots-plan.md) | Scenario B (5G SA) screenshot checklist |
