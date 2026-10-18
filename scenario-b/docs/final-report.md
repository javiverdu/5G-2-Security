# Scenario B — Final Report: 5G Standalone (Open5GS + UERANSIM)

Consolidated report for pages 3–5 of the brief. Detailed sources:
[`README.md`](../README.md) · [`addressing-plan.md`](addressing-plan.md) ·
[`traffic-observation.md`](traffic-observation.md) ·
[`performance-measurement.md`](performance-measurement.md) ·
[`step-log.md`](step-log.md). Raw evidence: `results/scenario-b/`,
`captures/scenario-b/`.

---

## 1. Objective and scope

Build the reference 5G architecture on a single Ubuntu VM with Docker Compose,
establish an **end-to-end path from the UE to an application server**, document
the components, interfaces, addresses, subnets, routes, ports and services, and
observe/measure the path. Scope: a simplified 5G Standalone core (no radio
hardware, no full operator functionality), fully routed on the N6 side.

## 2. Reference architecture and implementation

| Reference role | Implementation | Notes |
|---|---|---|
| UE | UERANSIM `nr-ue` | gets `10.45.0.2` on `uesimtun0` |
| gNB | UERANSIM `nr-gnb` | N2 + N3 endpoints |
| AMF, SMF, UPF, NRF, AUSF, UDM, UDR, PCF, BSF, NSSF, SCP | Open5GS | UPF is the only user-plane forwarder |
| subscriber DB | MongoDB | provisioned via `webui` |
| Data Network (N6) | Docker network `dn` `10.20.6.0/24` | nginx `.20`, iperf3 `.21` |
| Observability | metrics + Grafana | present; dashboard is page 6 |

Two planes run in parallel: **control** (registration/session: N2, N4, SBI) and
**user** (the actual packet: radio → N3/GTP-U → UPF → N6 → app). If the control
plane does not complete, the user plane does not exist.

## 3. Interfaces and addressing (summary)

| Segment | Subnet | Nodes |
|---|---|---|
| 5G core | `172.22.0.0/24` | all NFs + gNB (see `addressing-plan.md`) |
| UE PDU pool | `10.45.0.0/16` | UE `10.45.0.x`, gateway `10.45.0.1` |
| N6 / Data Network | `10.20.6.0/24` | UPF `.2`, nginx `.20`, iperf3 `.21` |

| Interface | Endpoints | Transport |
|---|---|---|
| N2 | gNB → AMF | NGAP / SCTP `38412` |
| N3 | gNB ↔ UPF | GTP-U / UDP `2152` |
| N4 | SMF ↔ UPF | PFCP / UDP `8805` |
| SBI | NF ↔ NF | HTTP/2 `7777` |
| N6 | UPF ↔ apps | IPv4, **no NAT** |

Subscriber: IMSI `001011234567895`, K `8baf…`, OP `1111…`, OPc `8E27…`, APN
`internet`, slice SST 1.

## 4. Page 3 — deployment and end-to-end operation

Procedure: `fetch-upstream.sh` → `deploy.sh` → `verify.sh` → `enable-n6.sh` →
`verify.sh`. All steps are scripted and reproducible (`step-log.md` §1).

`verify.sh` (all green):

| # | Check | Evidence |
|---|---|---|
| 1 | containers up | mongo, nrf, amf, smf, upf, ausf, udm, udr, pcf, nr_gnb, nr_ue |
| 2 | N2 — `NG Setup procedure is successful` | `nr_gnb` log |
| 3 | registration + PDU session | `nr_ue` log |
| 4 | `uesimtun0 = 10.45.0.2/32` | UE interface |
| 5 | UE → `10.45.0.1` through the tunnel | ping |
| 6 | HTTP 200 over N6, **nginx logs the UE `10.45.0.2`** (no NAT) | `sb-nginx` log |
| 7 | iperf3 throughput UE → `10.20.6.21` | iperf3 report |

## 5. Page 4 — traffic observation

Five capture points: P1 UE (`uesimtun0`), P2 gNB (N3), P3 UPF (N3), P4 UPF (N6),
P5 application. The central observation is the **GTP-U envelope**:

| Point | `frame.protocols` (ICMP) |
|---|---|
| P1 | `raw:ip:icmp:data` |
| P2 / P3 | `eth:ip:udp:gtp:ip:icmp:data` |
| P4 / P5 | `eth:ip:icmp:data` |

* Identical frame counts at all five points (10 / 13 / 3178 / 497) → generated,
  encapsulated, forwarded, decapsulated and delivered with no loss.
* ICMP: `10.45.0.2 ↔ 10.20.6.20`, `ip.len 128`, `type 8/0`, TTL 64→63 (one routed
  hop, the UPF).
* TCP/HTTP: handshake, `GET /`, `200 OK`, `Content-Length 896`.
* TCP iperf3: two connections, 0 retransmissions; UDP iperf3: 466 frames, 0 loss.
* The same addresses appear at P1, P4 and P5 → routed, **no NAT**.

Full detail: [`traffic-observation.md`](traffic-observation.md).

## 6. Page 5 — performance and degradation

Conditions applied to the user-plane endpoints (uplink at the UE, downlink at the
apps), so N2/N4/SBI are untouched.

| Condition | ICMP RTT (ms) | HTTP (ms) | TCP (Mbit/s) | UDP loss (%) | UDP jitter (ms) |
|---|---|---|---|---|---|
| baseline | 0.735 | 3.07 | 391.7 | 0.000 | 0.106 |
| delay | 108.65 | 337.8 | 71.8 | 0.132 | 7.405 |
| loss | 0.752 | 9.63 | 281.4 | 1.150 | 0.098 |
| rate | 1.786 | 3.17 | 17.95 | 0.000 | 0.345 |

* **delay** — latency only: RTT ≈ 2 × 50 ms, HTTP ≈ 2 RTT, TCP collapses
  (window/RTT). Shows latency alone cripples TCP with no loss.
* **loss** — drops: TCP window reduction + 175 retransmissions; UDP loses ~1%
  and never recovers.
* **rate** — ceiling: TCP clamped to ~18 Mbit/s; queueing raises RTT slightly;
  UDP unaffected below the cap.

Full interpretation and the retransmission counting caveat:
[`performance-measurement.md`](performance-measurement.md).

## 7. Page 6 — observability

Prometheus (`metrics`, host port 9090) and Grafana (`grafana`, port 3000,
`open5gs`/`open5gs`) are part of the Compose. The Open5GS NFs expose metrics on
`:9091`, Prometheus scrapes them, and Grafana shows the provisioned `Open5GS`
dashboard. `scripts/metrics-check.sh` reports container status, Prometheus target
health (AMF/SMF/PCF/UPF **up**; MME/PCRF/HSS are 4G-only and stay down) and the
Open5GS metric names. Because the repository runs from a **VirtualBox shared
folder**, Grafana's file provisioning is unreadable by its uid-472 user, so the
datasource and dashboard are imported over the API instead
(`scripts/grafana-import.sh`). Details: [`observability.md`](observability.md).

## 8. Diagnosis — obstacles found (and fixed)

Recorded in full in [`step-log.md`](step-log.md). Highlights: UERANSIM does not
install the session route; container-name collision with Scenario A; the UE image
has no HTTP/iperf3 client; the iperf3 image has no `ip`; `grep -q` + `pipefail`
(SIGPIPE) made checks flaky; AppArmor confined `tshark` (twice: analyze and
recount); and inconsistent output paths between scripts. None of these were
network faults — they were tooling/permissions issues the method exposed.

## 9. Conclusions

* The complete 5G path UE → gNB → UPF → N6 → application is operational and
  demonstrated at packet level, with the UE address preserved end to end (no NAT).
* The five-point method localises where a packet is generated, encapsulated,
  decapsulated and delivered; the N3/N6 contrast is the key evidence.
* Baseline and three degraded conditions are quantified and explained by the
  interaction between latency, loss and bandwidth limits and TCP/UDP behaviour.
* Diagnosis was a first-class part of the work: the failures above were found,
  explained and fixed, not worked around blindly.

## 10. Evidence index

```
scenario-b/docs/   README, addressing-plan, capture-points, traffic-observation,
                   performance-measurement, observability, step-log, final-report (this)
scenario-b/scripts/ fetch-upstream, deploy, verify, enable-n6, capture,
                    capture-control, analyze, impair, measure, run-all,
                    recount-retrans, metrics-check, grafana-import, plot, cleanup
results/scenario-b/ summary.csv, comparison.{csv,md}, plots/, tc-*.txt,
                    <condition>/*, page-4 dissections
captures/scenario-b/ P*.pcap (git-ignored)
```

## 11. Reproducibility

```bash
cd scenario-b
./scripts/fetch-upstream.sh
./scripts/deploy.sh
./scripts/verify.sh
sudo ./scripts/enable-n6.sh
./scripts/verify.sh
sudo ./scripts/capture.sh icmp && sudo ./scripts/capture.sh tcp-http
sudo ./scripts/capture.sh tcp-iperf && sudo ./scripts/capture.sh udp-iperf
sudo ./scripts/analyze.sh
sudo ./scripts/run-all.sh && python3 ./scripts/plot.py
./scripts/metrics-check.sh
./scripts/cleanup.sh
```
