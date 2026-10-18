# Project 1 — Final Report: Network Deployment, Measurement, and Observability

**Scenario A** — Software-Based Telecommunications Network (Linux network namespaces)
· **Scenario B** — 5G Standalone (Open5GS + UERANSIM)

This is the consolidated report. Detailed sources: the Scenario A step reports
([`step1`](step1-network-deployment.md), [`step2`](step2-traffic-observation.md),
[`step3`](step3-performance-measurement.md)) and the Scenario B reports
([`../scenario-b/docs/`](../scenario-b/docs/)). Raw evidence: `results/`,
`captures/` (`.pcap`, ship separately).

---

## 1. Introduction and scope

The project establishes an operational end-to-end path, observes how traffic
behaves, quantifies performance under controlled degradation, and explains normal
operation and failures with packet-, system- and application-level evidence, for
two reference networks. Workflow: **Deploy → Verify → Observe → Measure →
Diagnose → Explain**.

## 2. Environment

Single Ubuntu VM. Scenario A uses Linux network namespaces + Docker bridge;
Scenario B uses Docker Compose (Open5GS 5G SA core + UERANSIM). Tools: `iproute2`,
Docker, `tcpdump`/`tshark` (Wireshark), `iperf3`, `tc`/NetEm, Python + matplotlib.

---

## 3. Scenario A — Linux + Docker

### 3.1 Architecture

`ue → access → core → host → Docker Data Network` over four subnets
(`10.0.1–10.0.4.0/24`), fully routed, **no NAT**. The `app` role is realised with
the host root namespace + Docker bridge (see
[step1 §1](step1-network-deployment.md#role-mapping--why-three-namespaces-plus-docker)).
Fig. 1 (topology) is in [README §Architecture](../README.md#architecture--scenario-a);
addressing in [`addressing-plan.md`](addressing-plan.md).

### 3.2 Deployment and end-to-end operation (Step 1)

Built by `scripts/deploy/setup.sh`; verified by `verify.sh` (all checks green):
namespaces, hop-by-hop ICMP, container reachability, **HTTP 200** from nginx and
iperf3 throughput (≈ 38 Gbit/s on the virtual link). TTL decreases exactly one
per routed hop (64 → 63 → 62 → 61) proving each router forwards; routing is
symmetric so `rp_filter` passes. A real obstacle was diagnosed: Docker ≥ 28/29
hardened forwarding dropped routed traffic to container IPs; fixed with
`allow-direct-routing` + a `DOCKER-USER` accept rule
([step1 §5](step1-network-deployment.md)). Details: [`step1-network-deployment.md`](step1-network-deployment.md).

### 3.3 Traffic observation (Step 2)

Six capture points (P1 `ue:eth0` … P6 container) with identical packet counts in
every scenario (ICMP 10, TCP-HTTP 12, TCP-iperf 164, UDP-iperf 434/463),
demonstrating generated → forwarded → delivered. ICMP TTL 64→61 (3 hops). TCP
shows handshake, `GET /` and `200 OK`; UDP 432 datagrams, 0 % loss. IP addresses
stay end-to-end while MAC and TTL change hop by hop (no NAT). Details:
[`step2-traffic-observation.md`](step2-traffic-observation.md); capture points:
[`capture-points.md`](capture-points.md).

### 3.4 Performance and degradation (Step 3)

NetEm on both access egress interfaces. Comparative results (mean of 3 runs):

| Condition | ICMP RTT (ms) | HTTP (ms) | TCP (Mbit/s) | UDP loss (%) | UDP jitter (ms) |
|---|---|---|---|---|---|
| baseline | 0.081 | 0.60 | 38048.6 | 0.026 | 0.026 |
| delay | 157.80 | 217.80 | 140.8 | 0.039 | 6.32 |
| loss | 0.086 | 14.63 | 4434.4 | 1.87 | 0.037 |
| rate | 14.61 | 1.70 | 18.96 | 0.000 | 0.104 |

Latency cripples TCP goodput with no loss; loss reduces the window and forces
retransmissions while UDP merely loses data; the rate ceiling clamps TCP and adds
queueing delay. Plot: `results/step3/plots/comparison.png`. Details:
[`step3-performance-measurement.md`](step3-performance-measurement.md).

---

## 4. Scenario B — 5G Standalone

### 4.1 Architecture

`UE (UERANSIM) → gNB → N3/GTP-U → UPF → N6 → application`, with Open5GS as the
core; control plane `gNB →N2→ AMF`, `SMF →N4→ UPF`, SBI between NFs. N6 is routed
with **no NAT**. Addressing: UE pool `10.45.0.0/16`, N6 `10.20.6.0/24`, core
`172.22.0.0/24` ([`../scenario-b/docs/addressing-plan.md`](../scenario-b/docs/addressing-plan.md)).

### 4.2 Deployment and end-to-end operation (page 3)

`fetch-upstream → deploy → verify → enable-n6 → verify`; all 7 checks green:
containers up; N2 NG Setup; registration + PDU session; `uesimtun0 = 10.45.0.2`;
tunnel gateway reachable; **HTTP 200 over N6 with nginx logging the UE address
`10.45.0.2`** (no NAT); iperf3 throughput. Details:
[`../scenario-b/docs/final-report.md`](../scenario-b/docs/final-report.md).

### 4.3 Traffic observation (page 4)

Five points (P1 UE, P2 gNB-N3, P3 UPF-N3, P4 UPF-N6, P5 app). The key evidence: on
N3 the user packet travels inside the **GTP-U envelope** (`udp/2152`), and on N6 it
reappears decapsulated with the same addresses:

| Point | `frame.protocols` (ICMP) |
|---|---|
| P1 | `raw:ip:icmp:data` |
| P2 / P3 | `eth:ip:udp:gtp:ip:icmp:data` |
| P4 / P5 | `eth:ip:icmp:data` |

Counts are identical at all points. The **control plane is captured too**: N2
(NGAP/SCTP 38412) shows the whole registration (`Registration request`,
`Authentication`, `Security mode`, `InitialContextSetup`, `PDUSessionResourceSetup`)
and N4 (PFCP/UDP 8805) the `Session Establishment`/`Modification`. Details:
[`../scenario-b/docs/traffic-observation.md`](../scenario-b/docs/traffic-observation.md).

### 4.4 Performance and degradation (page 5)

NetEm on the user-plane endpoints; results (mean of 3 runs):

| Condition | ICMP RTT (ms) | HTTP (ms) | TCP (Mbit/s) | UDP loss (%) | UDP jitter (ms) |
|---|---|---|---|---|---|
| baseline | 0.735 | 3.07 | 391.7 | 0.000 | 0.106 |
| delay | 108.65 | 337.8 | 71.8 | 0.132 | 7.405 |
| loss | 0.752 | 9.63 | 281.4 | 1.150 | 0.098 |
| rate | 1.786 | 3.17 | 17.95 | 0.000 | 0.345 |

Same qualitative behaviour as Scenario A. Plot:
`results/scenario-b/plots/comparison.png`. Details:
[`../scenario-b/docs/performance-measurement.md`](../scenario-b/docs/performance-measurement.md).

### 4.5 Observability (page 6)

Prometheus scrapes the Open5GS NFs (`:9091`); Grafana shows an Open5GS dashboard
(imported over the API because the repository runs from a VirtualBox shared
folder — see the field note). The 4G jobs (`mme`/`pcrf`/`hss`) appear `DOWN` and
are **not used** in 5G SA. Details:
[`../scenario-b/docs/observability.md`](../scenario-b/docs/observability.md).

---

### 4.6 Avoiding the brief's attention traps

| Trap | How we comply |
|---|---|
| container state ≠ packet evidence | we present **pcaps**, not `docker compose ps`: N3 (GTP-U) and N6 (plain IP) at four points, and **N2/N4 captured at packet level** (`capture-control.sh`). |
| N4/PFCP is not application traffic | N4 is captured separately as control signalling. |
| GTP-U wraps the inner IP packet | the same frame is `udp:gtp:ip:<proto>` on N3 and plain `ip:<proto>` on N6. |
| Docker IP ≠ UE PDU-session IP | the UE IP is `10.45.0.2` (`uesimtun0`), not the Docker IP `172.22.0.24`. |
| a ping is not sufficient | we add HTTP 200, TCP/UDP iperf3, registration and the GTP-U path. |
| N6 reachability ≠ 5G user-plane proof | traffic starts **inside the UE netns** and nginx logs client `10.45.0.2`. |

Details: [`../scenario-b/docs/traffic-observation.md`](../scenario-b/docs/traffic-observation.md) §10.

---

## 5. Diagnosis — obstacles found and fixed

* **Scenario A:** Docker ≥ 28 hardened forwarding dropped routed container
  traffic (`allow-direct-routing` + `DOCKER-USER`); AppArmor confined `tshark`.
* **Scenario B:** UERANSIM does not install the PDU-session route; container-name
  collisions with Scenario A; the UE image lacks `curl`/`iperf3`; the iperf3 image
  lacks `ip`; `grep -q` + `pipefail` (SIGPIPE) made checks flaky; AppArmor confined
  `tshark`; Grafana provisioning unreadable from a vboxsf shared folder; container
  interface names (`eth0`/`eth1`) swap, so captures must detect them by address.

Each was diagnosed from evidence and fixed; the full log is in
[`../scenario-b/docs/step-log.md`](../scenario-b/docs/step-log.md).

## 6. Conclusions

Both reference networks were deployed and verified end to end with packet-level
evidence, and their performance was quantified under controlled degradation. The
multi-point method localises where a packet is generated, encapsulated, forwarded,
decapsulated or dropped; latency, loss and bandwidth limits degrade TCP and UDP in
distinct, explainable ways.

## 7. Figures, tables and screenshots

| ID | Item | Source |
|---|---|---|
| Fig. A1 | Scenario A topology | `README.md` (Mermaid) |
| Fig. A2 | Scenario A comparative plot | `results/step3/plots/comparison.png` |
| Fig. B1 | Scenario B comparative plot | `results/scenario-b/plots/comparison.png` |
| Fig. B2 | Scenario B screenshots (pages 3–6) | `docs/img/sb-*` |
| Fig. A3 | Scenario A screenshots | `docs/img/step*` (to capture) |

## 8. Evidence index

```
docs/                addressing-plan, step1/2/3, capture-points, screenshots-plan,
                     final-report (this)
scenario-b/docs/     README, addressing-plan, capture-points, traffic-observation,
                     performance-measurement, observability, step-log, final-report
scripts/ (A)         deploy/, observe/, measure/, teardown/
scenario-b/scripts/  fetch-upstream, deploy, verify, enable-n6, capture,
                     capture-control, analyze, impair, measure, run-all,
                     recount-retrans, metrics-check, grafana-import, plot, cleanup
results/             step1/, step2/, step3/, scenario-b/
captures/            step2/, scenario-b/   (git-ignored; ship separately)
docs/img/            sb-p3-* … sb-p6-*  (Scenario B screenshots)
```

## 9. Reproducibility

* Scenario A: [`README §Quickstart`](../README.md#quickstart).
* Scenario B: [`../scenario-b/README.md`](../scenario-b/README.md) §7.
