# Final Report — Structure & Traceability

**Project 1: Network Deployment, Measurement, and Observability — Scenario A: Software-Based Telecommunications Network**

This document is the **master index and structure of the final report**. It states
what each section must contain and links to the evidence already produced, so the
narrative report (e.g. `5Gproject.docx`) can be assembled directly on top of it.
Each detailed step report is the authoritative source for its section.

---

## A. Requirement coverage matrix

| Assignment requirement | Where it is covered |
|---|---|
| Topology diagram | `docs/addressing-plan.md` §Topology; `docs/step1-network-deployment.md` §1 |
| Namespace list / interface configuration / IP addressing table | `docs/step1-network-deployment.md` §3; raw: `results/step1/01-namespaces-interfaces.txt` |
| Routing table output per node | `docs/step1-network-deployment.md` §4; raw: `results/step1/02-routing-tables.txt` |
| Docker network configuration & container/service info | `docs/step1-network-deployment.md` §5; raw: `results/step1/03-docker-network.txt` |
| Service status and listening ports | `docs/step1-network-deployment.md` §5; raw: `results/step1/04-listening-ports.txt` |
| Successful `curl`/application test | `docs/step1-network-deployment.md` §6; raw: `results/step1/06-curl-http.txt` |
| Explanation of the end-to-end path | `docs/step1-network-deployment.md` §7 |
| ICMP/TCP/UDP/application packet analysis | `docs/step2-traffic-observation.md` §3–§6; raw: `results/step2/` |
| Multi-point captures (generated/forwarded/dropped/answered) | `docs/step2-traffic-observation.md` §1–§2; pcaps: `captures/step2/` |
| Baseline + ≥2 degraded conditions (`tc`/NetEm) | `docs/step3-performance-measurement.md` §1, §4–§6; raw: `results/step3/` |
| Comparative table + plot | `docs/step3-performance-measurement.md` §2; `results/step3/comparison-table.md`, `results/step3/plots/comparison.png` |
| Quantitative interpretation linking conditions to protocol behaviour | `docs/step3-performance-measurement.md` §7 |

---

## B. Report outline

### 0. Cover and metadata
Title, authors, course, date, environment summary (single Linux VM, Ubuntu,
Docker 29.8.1, VirtualBox), repository location.

### 1. Introduction
- **1.1 Objectives** — establish, observe, measure and explain an end-to-end
  software-based telecommunications path.
- **1.2 Engineering workflow** — Deploy → Verify → Observe → Measure → Diagnose → Explain.
- **1.3 Scope and assumptions** — simplified Scenario A (not a full 4G/5G core);
  no NAT by design (routed, observable addresses).

### 2. Reference architecture and topology
- **2.1 Logical chain** — `UE → Access → Core/Gateway → Data Network → Application Server`.
- **2.2 Hybrid Linux + Docker architecture** — namespaces for UE/Access/Core,
  Docker bridge for the Data Network extension.
- **2.3 Topology diagram** — `docs/addressing-plan.md` §Topology.
- **2.4 Components table** — `docs/step1-network-deployment.md` §2.
- **2.5 Addressing plan** — `docs/addressing-plan.md` (interfaces, subnets, roles).
- **2.6 Routing and forwarding plan** — `docs/addressing-plan.md` §Routing plan.

### 3. Step 1 — Network deployment and end-to-end operation
> Detailed report: [`docs/step1-network-deployment.md`](step1-network-deployment.md)

- **3.1 Deployment procedure** — `scripts/deploy/setup.sh` (idempotent).
- **3.2 Interface configuration and IP addressing** — §3 + `results/step1/01-…`.
- **3.3 Routing tables per namespace/host** — §4 + `results/step1/02-…`.
- **3.4 Docker network, containers, services** — §5 + `results/step1/03-…`.
- **3.5 Service status and listening ports** — §5 + `results/step1/04-…`.
- **3.6 End-to-end verification** — `verify.sh` (all green), `curl` HTTP 200,
  `iperf3` TCP; §6 + `results/step1/00/05/06/07-…`.
- **3.7 Path explanation with packet evidence** — TTL 64 → 63 → 62 → 61 (§7).
- **3.8 Deployment diagnosis** — Docker 29 hardened defaults; see §6 of this
  document and §8 of the step report.

### 4. Step 2 — Traffic observation and protocol behavior
> Detailed report: [`docs/step2-traffic-observation.md`](step2-traffic-observation.md)

- **4.1 Capture methodology** — six observation points P1–P6 (§1).
- **4.2 Cross-point result** — identical packet counts = generated/forwarded/
  delivered (§2).
- **4.3 ICMP** — type/code, size, TTL decrement, RTT, 0% loss (§3).
- **4.4 TCP** — handshake, HTTP request/response, teardown; iperf3 TCP (§4).
- **4.5 UDP** — datagrams, loss, jitter; no transport retransmission (§5).
- **4.6 Application layer** — HTTP transaction via follow-stream (§6).
- **4.7 Observation** — AppArmor `tshark` confinement and the `aa-exec` fix (§7).

### 5. Step 3 — Performance measurement and network degradation
> Detailed report: [`docs/step3-performance-measurement.md`](step3-performance-measurement.md)

- **5.1 Experimental conditions** — baseline, delay 50 ms±10 ms, loss 1%, rate 20 Mbit/s (§1).
- **5.2 Baseline reference values** (§3).
- **5.3 Comparative table** (reproduced in Appendix A) (§2).
- **5.4 Plot** — `results/step3/plots/comparison.png` (§2).
- **5.5 Interpretation** — latency vs loss vs bandwidth effects on TCP/UDP/HTTP (§7).
- **5.6 Caveats** — virtual-path throughput, UDP reordering counted as loss (§8).

### 6. Diagnosis summary (the **Diagnose** dimension)
Two real obstacles were found and explained with evidence; both are strong
"engineering reasoning" material for the report:
1. **Docker ≥28/29 hardened forwarding** dropped routed traffic toward container
   IPs in `raw/PREROUTING` and the `DOCKER` filter chain. Root cause proved by
   binary-wrapping `nft`/`iptables` (the caller was `dockerd`). Fix:
   `allow-direct-routing: true` + a `DOCKER-USER` accept rule.
   (`docs/step1-network-deployment.md` §8)
2. **AppArmor `tshark` profile** denied reading captures outside `user-tmp`.
   Fix: `aa-exec -p unconfined -- tshark …` for offline analysis.
   (`docs/step2-traffic-observation.md` §7)

### 7. Conclusions
- Complete path established and verified; every generated packet traverses it
  (Steps 1–2).
- Protocol behaviour under baseline and three degraded conditions quantified and
  explained (Step 3).
- The measurement method localises *where* packets are generated, forwarded,
  delayed or dropped.

### 8. Reproducibility
```bash
sudo ./scripts/deploy/setup.sh        # build the topology
sudo ./scripts/deploy/verify.sh       # end-to-end checks
sudo ./scripts/observe/capture.sh <label> <container> '<traffic cmd>'  # captures
sudo ./scripts/observe/analyze.sh     # tshark dissection -> results/step2
sudo ./scripts/measure/run-all.sh     # baseline + degraded conditions
python3 ./scripts/measure/plot.py     # comparative table + plots
sudo ./scripts/teardown/cleanup.sh    # remove everything
```

### 9. Evidence index (appendix)
See §D below and each step report's "Evidence index".

### 10. References
- Project brief: `Project 1_Network Deployment, Measurement, and Observability.pdf`.
- Tools: `iproute2`/`ip netns`, Docker Engine, Nginx, iperf3, tcpdump/tshark,
  Linux `tc` + NetEm.

---

## C. Figure and table list

| ID | Item | Source |
|---|---|---|
| Fig. 1 | Hybrid topology diagram | `docs/addressing-plan.md` |
| Fig. 2 | Step 3 comparative plots | `results/step3/plots/comparison.png` |
| Tab. 1 | Interface/IP addressing table | `docs/step1-network-deployment.md` §3 |
| Tab. 2 | Routing plan | `docs/addressing-plan.md` |
| Tab. 3 | Step 2 cross-point packet counts | `results/step2/cross-point-packet-counts.txt` |
| Tab. 4 | Step 3 comparative results | `results/step3/comparison-table.md` |
| Tab. 5 | Condition → protocol-behaviour mapping | `docs/step3-performance-measurement.md` §7 |

---

## D. Repository evidence index

```
docs/
  addressing-plan.md              topology, addressing, routing plan
  step1-network-deployment.md     deployment + verification + Docker diagnosis
  step2-traffic-observation.md    ICMP/TCP/UDP/HTTP dissection + AppArmor note
  step3-performance-measurement.md baseline + degradation study
  final-report.md                 this document (report structure)
scripts/
  deploy/    setup.sh, verify.sh
  observe/   capture.sh, analyze.sh
  measure/   impair.sh, measure.sh, run-all.sh, plot.py
  teardown/  cleanup.sh
results/
  step1/  namespaces, interfaces, routes, docker, ports, curl, iperf3, firewall
  step2/  protocol hierarchies, fields, follow-stream, conversations, counts
  step3/  per-condition raw data, summary/comparison CSV, table, plots
captures/ (git-ignored)   raw .pcap files for Steps 2–3
```

---

## E. Key numbers at a glance

**Step 2 — cross-point packet counts** (identical at P1–P6 ⇒ no drops):

| Scenario | icmp | tcp-http | tcp-iperf | udp-iperf |
|---|---|---|---|---|
| packets at each point | 10 | 12 | 164 | 434 |

**Step 3 — comparative results (means):**

| Condition | RTT (ms) | HTTP (ms) | TCP (Mbit/s) | UDP loss (%) | UDP jitter (ms) | TCP retrans. |
|---|---|---|---|---|---|---|
| baseline | 0.081 | 0.60 | 38048.6 | 0.03 | 0.03 | 0 |
| delay | 103.90 | 239.70 | 12.77 | 1.10 | 7.46 | 8 |
| loss | 0.086 | 14.63 | 4434.4 | 1.87 | 0.04 | 21 |
| rate | 14.61 | 1.70 | 18.96 | 0.00 | 0.10 | 0 |
