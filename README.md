# 5G-project-RTU

**Project 1: Network Deployment, Measurement, and Observability**
**Scenario A: Software-Based Telecommunications Network**

A university project that examines the deployment and operation of a software-based telecommunications network from the perspective of a network engineer. The objective is to establish an operational end-to-end communication path, determine how traffic and network functions behave across the system, quantify service performance under controlled conditions, and use packet-level, system-level, and application-level evidence to explain normal operation, degradation, and failure.

The project follows the engineering workflow:

> **Deploy → Verify → Observe → Measure → Diagnose → Explain**

---

## Table of Contents

- [Overview](#overview)
- [Project Status & Traceability](#project-status--traceability)
- [Reference Architecture](#reference-architecture)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Step 1 — Network Deployment and End-to-End Operation](#step-1--network-deployment-and-end-to-end-operation)
- [Step 2 — Traffic Observation and Protocol Behavior](#step-2--traffic-observation-and-protocol-behavior)
- [Step 3 — Performance Measurement and Network Degradation](#step-3--performance-measurement-and-network-degradation)
- [Metrics](#metrics)
- [Documentation and Evidence](#documentation-and-evidence)

---

## Overview

Scenario A represents a simplified, software-based telecommunications environment in which each functional stage of the communication path is explicitly observable and measurable. The objective is **not** to reproduce a complete 4G/5G network, but to establish a technically meaningful end-to-end telecommunications environment in which it is possible to:

- Investigate how packets move through multiple functional network stages.
- Determine how network conditions affect service behavior.
- Build the practical foundation of network deployment, measurement, and observability for the remainder of the course.

The baseline implementation runs on a **single Linux virtual machine**:

- **Linux network namespaces** represent the principal network entities (UE, Access Router, Core/Gateway). Namespaces provide isolated network interfaces, routing tables, sockets, and other network state.
- **Virtual Ethernet (veth) pairs** interconnect the namespaces, providing virtual point-to-point links.
- **Docker containers** provide the application server (Nginx) and a network performance measurement endpoint (iperf3).
- A **Docker user-defined bridge network** acts as a controlled containerized extension of the Data Network.
- The **Linux host** provides the integration boundary between the namespace-based network and the containerized services.

This **Hybrid Linux + Docker** architecture preserves the original communication path while introducing a realistic software-deployment mechanism: Linux network infrastructure + containerized network/application functions — without hiding the underlying Linux networking concepts.

## Project Status & Traceability

Overall progress of the project steps and where the supporting evidence lives.

| Step | Description | Status | Evidence |
|---|---|---|---|
| 0 | Repository scaffold, addressing plan, deploy/verify/teardown scripts | ✅ Done | `docs/addressing-plan.md`, `scripts/` |
| 1 | Network deployment and end-to-end operation | ✅ Done | `docs/step1-network-deployment.md`, `results/step1/` |
| 2 | Traffic observation and protocol behavior | ✅ Done | `docs/step2-traffic-observation.md`, `results/step2/`, `captures/step2/` |
| 3 | Performance measurement and network degradation | ✅ Done | `docs/step3-performance-measurement.md`, `results/step3/` |

### Activity log

| Date | Activity | Outcome / Evidence |
|---|---|---|
| 2026-09-21 | Repository scaffold created (`docs/`, `scripts/`, `captures/`, `results/`) | Done |
| 2026-09-21 | IP addressing & topology plan defined (10.0.1–10.0.4.0/24 scheme, per reference diagram) | `docs/addressing-plan.md` |
| 2026-09-21 | Deploy / verify / teardown scripts written | `scripts/deploy/`, `scripts/teardown/` |
| 2026-09-21 | Step 1: topology deployed on the lab VM (`192.168.56.104`); Docker 29 hardened defaults diagnosed and fixed (`allow-direct-routing` in daemon.json + DOCKER-USER accept rule); end-to-end path verified (HTTP 200, iperf3 ≈ 36 Gbit/s) | `docs/step1-network-deployment.md`, `results/step1/` |
| 2026-09-22 | Step 2: multi-point captures (P1–P6) for ICMP, TCP/HTTP, iperf3 TCP and UDP; tshark dissection (protocol hierarchy, flags/seq/ack, follow-stream, conversations, retransmissions); AppArmor tshark confinement diagnosed and worked around (`aa-exec -p unconfined`) | `docs/step2-traffic-observation.md`, `results/step2/`, `captures/step2/` |
| 2026-09-22 | Step 3: baseline + 3 degraded conditions (delay 50ms±10ms, loss 1%, rate 20 Mbit/s) with NetEm on both access egress interfaces; full metric set ×3; comparative table + plot; quantitative interpretation | `docs/step3-performance-measurement.md`, `results/step3/` |

> Log rule: every working session appends a dated row with the activity performed and a link to the produced evidence.

## Reference Architecture

```
UE / Client  →  Access Network  →  Core Network / Gateway  →  Data Network  →  Application Server
```

Baseline topology (hybrid Linux namespaces + Docker):

```
+--------+   veth   +----------+   veth   +-----------+      +------------------+
|   ue   |==========|  access  |==========|   core    |======|   Data Network   |
| (netns)|          |  (netns) |          |  (netns)  |      |  (host + Docker  |
+--------+          +----------+          +-----------+      |   bridge net)    |
                                                             +------------------+
                                                                      |
                                                        +-------------------------+
                                                        |  Nginx app server       |
                                                        |  iperf3 server (Docker) |
                                                        +-------------------------+
```

- Each namespace holds its own interfaces, IP addressing, and routing table.
- veth pairs provide the point-to-point links between consecutive stages.
- The Docker bridge network extends the Data Network toward the containerized services.

## Technology Stack

| Category | Technology | Purpose |
|---|---|---|
| Network isolation | Linux network namespaces (`ip netns`) | UE, Access Router, Core/Gateway functions |
| Virtual links | veth pairs | Point-to-point links between namespaces |
| Containerization | Docker + user-defined bridge network | Data Network extension and service hosting |
| Application service | Nginx (Docker Official Image) | HTTP application server |
| Traffic generation / benchmarking | `networkstatic/iperf3` (amd64 & arm64), `iperf3` CLI, `ping`, `curl` | TCP/UDP throughput tests, ICMP probes, HTTP requests |
| Packet capture & analysis | `tcpdump`, `tshark`, Wireshark | Packet-level evidence at multiple points of the path |
| Traffic control / impairment | Linux `tc` with NetEm | Controlled delay, packet loss, and bandwidth limitation |
| Routing & addressing | `iproute2` (`ip addr`, `ip route`, `ip link`) | Interface and routing configuration |
| Analysis & plotting (optional) | Python 3 (`pandas`, `matplotlib`) | Measurement post-processing, comparative tables and plots |

## Repository Structure

Planned layout (evolves as the project advances):

```
5G-project-RTU/
├── README.md
├── docs/                    # Reports, topology diagrams, analysis Road
├── scripts/                 # Deployment, measurement and teardown scripts
│   ├── deploy/              # Namespace + veth + Docker topology setup
│   ├── observe/             # Multi-point capture and tshark analysis (Step 2)
│   ├── measure/             # Baseline and impairment measurement runs
│   └── teardown/            # Cleanup of namespaces, links and containers
├── captures/                # Packet captures (.pcap / .pcapng)
├── results/                 # Raw measurement output, tables, plots
└── docker/                  # Docker Compose / network definitions (if used)
```

## Prerequisites

- A Linux virtual machine (e.g., Ubuntu Server/Desktop) with root or sudo access.
- `iproute2` (provides `ip`, `tc` with NetEm support).
- Docker Engine with permission to create user-defined bridge networks and run containers.
- `iperf3`, `tcpdump`, `tshark`/Wireshark, `curl`, `ping` (`iputils-ping`).
- Optional: Python 3 with `pandas` and `matplotlib` for results analysis.

Typical installation on Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y iproute2 iputils-ping iperf3 tcpdump tshark curl python3 python3-pip
# Docker Engine: follow https://docs.docker.com/engine/install/
```

## Getting Started

```bash
# Clone the repository
git clone <repository-url>
cd 5G-project-RTU

# Deploy the full topology
sudo ./scripts/deploy/setup.sh

# Verify end-to-end connectivity
sudo ./scripts/deploy/verify.sh

# (Planned) Run baseline measurements
./scripts/measure/baseline.sh

# Remove all namespaces, links and containers
sudo ./scripts/teardown/cleanup.sh
```

## Step 1 — Network Deployment and End-to-End Operation

Establish the network environment and demonstrate successful end-to-end communication between the UE/client and the application server.

**Tasks:**

- Create four network namespaces (`ue`, `access`, `core`, `app`, …) using `ip netns`.
- Interconnect them with three veth pairs.
- Assign IP addressing and configure routing across every stage.
- Deploy the Nginx application server and the iperf3 endpoint in Docker, attached to a user-defined bridge network.
- Verify the complete path with application-level tests (e.g., `curl` from the `ue` namespace to the Nginx service).

**Evidence to document:**

- Topology diagram and namespace list.
- Interface configuration and IP addressing table.
- Routing table output per namespace/host.
- Docker network configuration and container/service information.
- Service status and listening-port information.
- Successful `curl` (or equivalent) application test, with command output/screenshots.
- A short explanation of the end-to-end communication path.

> The objective is not merely a successful `ping`: interfaces, routes, services, and application endpoints must all be correctly configured, and traffic must traverse the complete communication path.

## Step 2 — Traffic Observation and Protocol Behavior

Analyze representative **ICMP, TCP, UDP, and application traffic** at the packet level over the established path.

**For each traffic type, identify:**

- Source/destination addresses, protocol and protocol hierarchy.
- Transport protocol, source/destination ports (where applicable).
- Packet sequence and selected timing information.
- Relevant flags, sequence numbers, acknowledgements, and other protocol fields.
- Evidence of successful or unsuccessful communication.

**Required traffic categories:**

| Category | Tooling | Focus |
|---|---|---|
| A. ICMP | `ping` + capture | Packet size, observed RTT, packet loss (if any) |
| B. TCP | HTTP → Nginx (TCP connection, HTTP request/response) or iperf3 TCP | Connection establishment, data transfer, teardown |
| C. UDP | iperf3 or another controlled UDP source | Datagram flow, loss, jitter |
| D. Application | HTTP transaction capture | Application-layer exchange |

**Capture tooling:** `tcpdump`, `tshark`, and/or Wireshark. Comparing captures at different locations (UE, access, core, data network) helps determine whether a packet was generated, forwarded, dropped, answered, or lost on the return path.

## Step 3 — Performance Measurement and Network Degradation

Establish a quantitative performance baseline and repeat the experiment under **at least two controlled degraded network conditions**, using Linux `tc` with the NetEm mechanism.

**Experimental conditions (examples):**

1. Baseline — no artificial impairment.
2. Increased delay (e.g., NetEm delay).
3. 1% packet loss.
4. 20 Mbps bandwidth limit.
5. Combinations of the above.

**Procedure:**

1. Document the normal operating condition **before** introducing any impairment: ICMP RTT, TCP throughput, UDP throughput, UDP loss/jitter, HTTP response time, and TCP retransmissions.
2. Repeat measurements sufficiently to confirm the results are reasonably stable.
3. Apply the impairment with `tc qdisc ... netem` and repeat the full measurement set.
4. Compare conditions quantitatively and explain **why** the changes occurred, linking network conditions to observed protocol behavior.

**Evidence to document:**

- Experimental topology and list of experimental conditions.
- Commands/configuration used to impose each impairment.
- Raw measurement output and original packet captures where appropriate.
- At least one comparative table and at least one suitable plot.
- Quantitative comparison, interpretation of results, and explanation linking network conditions to protocol behavior.

## Metrics

| Metric | Tool |
|---|---|
| RTT | `ping` |
| TCP throughput | iperf3 |
| UDP throughput, loss, jitter | iperf3 |
| TCP retransmission count | `tcpdump`/`tshark` analysis |
| Application (HTTP) response time | `curl -w`, Wireshark |
| Connection establishment time | capture analysis / `curl -w` |
| Service availability | repeated application requests |

## Documentation and Evidence

All diagrams, tables, raw outputs, captures, and plots are maintained in the `docs/`, `captures/`, and `results/` directories. The final report must connect quantitative results with packet-level and system-level evidence, following the **Deploy → Verify → Observe → Measure → Diagnose → Explain** workflow.

The structure and traceability index of the final report — with the requirement
coverage matrix, outline, figure/table list and key results — is in
[`docs/final-report.md`](docs/final-report.md).
