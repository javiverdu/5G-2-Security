# Scenario B — Performance Measurement & Network Degradation (page 5)

Quantitative baseline of the 5G path and three controlled degraded conditions,
measured from the UE. Raw data: `results/scenario-b/` (`summary.csv`,
`<condition>/`, `tc-*.txt`). Plots: `results/scenario-b/plots/comparison.png`.

---

## 1. Experimental design

Impairments use `tc` + **NetEm** and are applied to the **user-plane endpoints
only**, so the control plane (N2/N4/SBI) is never affected:

| Direction | Where | Interface |
|---|---|---|
| uplink | `nr_ue` | `uesimtun0` (the 5G session) |
| downlink | `sb-nginx`, `sb-iperf3` | `eth0` (N6) |

`tc` runs from the host inside each container netns via `nsenter`
(`scripts/impair.sh`); the container images are not assumed to ship iproute2.

| Condition | NetEm |
|---|---|
| `baseline` | none |
| `delay` | `delay 50ms 10ms` |
| `loss` | `loss 1%` |
| `rate` | `rate 20mbit` |

Per condition (3 repetitions, from the UE): ICMP RTT/loss, HTTP response time,
TCP throughput, UDP throughput/loss/jitter, and TCP retransmissions (rate-capped
transfer captured at `uesimtun0`).

## 2. Comparative results (mean)

| Condition | ICMP RTT (ms) | HTTP (ms) | TCP (Mbit/s) | UDP (Mbit/s) | UDP loss (%) | UDP jitter (ms) | TCP retrans. (frame / segment) |
|---|---|---|---|---|---|---|---|
| **baseline** | 0.735 | 3.07 | 391.7 | 10.001 | 0.000 | 0.106 | 6 / 6 |
| **delay** | 108.65 | 337.8 | 71.8 | 10.000 | 0.132 | 7.405 | 710 / 75 |
| **loss** | 0.752 | 9.63 | 281.4 | 10.000 | 1.150 | 0.098 | 30 / 175 |
| **rate** | 1.786 | 3.17 | 17.95 | 10.001 | 0.000 | 0.345 | 69 / 69 |

Generated: `results/scenario-b/comparison-table.md`, `comparison.csv`,
`plots/comparison.png` (log scale for TCP throughput).

## 3. Baseline (normal operation)

ICMP RTT ≈ 0.7 ms, HTTP ≈ 3 ms, TCP ≈ 392 Mbit/s, UDP 10 Mbit/s with 0% loss and
≈ 0.1 ms jitter, and ~6 TCP retransmissions on the rate-capped transfer. This is
the healthy 5G path. (TCP is ~hundreds of Mbit/s, not the Gbit/s of Scenario A,
because the flow crosses the radio simulator, the GTP-U tunnel and a TUN, and the
iperf3 client runs in a sidecar container sharing the UE netns.)

## 4. Condition 1 — delay (`50ms ±10ms`)

* **ICMP RTT 0.7 → 108.7 ms.** Each direction is delayed 50 ms (uplink at the UE,
  downlink at the app) → ≈ 2 × 50 ms, plus jitter.
* **HTTP 3 → 337.8 ms.** A request/response needs ≈ 2 RTT plus connection setup.
* **TCP 392 → 71.8 Mbit/s** (CV 41%). Latency-bound: goodput ≈ window / RTT; the
  RTT rises ~150× and the auto-tuned window cannot compensate.
* **UDP jitter 0.1 → 7.4 ms** (the ±10 ms NetEm jitter); throughput stays at the
  sender's 10 Mbit/s. The small "loss" (0.13%) is mostly reordering, which
  iperf3's UDP accounting can register as loss.
* Retransmissions: iperf3 reports 75.

## 5. Condition 2 — 1% packet loss (`loss 1%`)

* **ICMP RTT unchanged (0.75 ms)**; loss shows as occasional drops.
* **TCP 392 → 281 Mbit/s** (CV 5%). TCP treats loss as congestion: window
  reduction + retransmissions, so goodput drops even with spare capacity.
* **TCP retransmissions 0 → 175** (iperf3). Direct evidence of detection and
  recovery.
* **HTTP 3 → 9.6 ms average with a tail of 23 ms**: a lost handshake/data segment
  makes the request wait for the retransmission.
* **UDP loss 1.15%** ≈ the configured 1%; UDP does **not** recover it.
* Jitter unchanged — loss and delay are independent NetEm properties.

## 6. Condition 3 — 20 Mbit/s limit (`rate 20mbit`)

* **TCP 392 → 17.95 Mbit/s** (CV 2.6%), clamped to the token bucket (slightly
  under 20 due to per-packet/ACK overhead).
* **ICMP RTT 0.7 → 1.79 ms** (CV 37%): bufferbloat — small probes queue behind
  the shaped backlog.
* **UDP unaffected** (10 Mbit/s, 0% loss) because the sender (`-b 10M`) is below
  the limit; the ceiling only bites when demand exceeds it.
* 69 retransmissions, consistent between both counters — the condition adds
  queueing, not loss.

## 7. Why the changes occur

| Condition | Primary effect | Protocol behaviour |
|---|---|---|
| delay | Latency (RTT ↑) | TCP goodput ↓ (window/RTT), HTTP ↑ (≈2 RTT), UDP jitter ↑ |
| loss | Drops | TCP window ↓ + retransmissions, goodput ↓; HTTP tail; UDP loss with **no** recovery |
| rate | Bandwidth ceiling | TCP clamped to the limit; queueing delay (RTT ↑) when saturated; UDP unaffected below the cap |

Latency, loss and bandwidth are independent dimensions. Loss degrades TCP two
ways (smaller window *and* retransmission delay) while UDP merely loses data; a
rate ceiling harms throughput and adds queueing delay; latency alone cripples TCP
goodput with no loss at all.

## 8. Stability

| Condition | Metric | mean | min | max | CV |
|---|---|---|---|---|---|
| baseline | TCP (Mbit/s) | 391.7 | 367.8 | 430.1 | 7.0% |
| delay | ICMP RTT (ms) | 108.65 | 106.1 | 111.7 | 2.1% |
| delay | TCP (Mbit/s) | 71.8 | 33.9 | 104.8 | 40.6% |
| loss | TCP (Mbit/s) | 281.4 | 261.2 | 297.9 | 5.4% |
| loss | HTTP (ms) | 9.63 | 2.8 | 23.1 | 98.9% |
| rate | TCP (Mbit/s) | 17.95 | 17.36 | 18.49 | 2.6% |

Throughput is very stable where the condition is deterministic (`rate` 2.6%,
`baseline` 7%). `delay` TCP is the least stable (41%) because the auto-tuned
window competes with a variable RTT; `loss` HTTP is spiky (98.9%) because the
tail depends on whether a segment was lost. Where CV is high but the absolute
value is near zero (e.g. UDP loss at baseline), the spread is noise, not signal.

## 9. TCP retransmission counting — a caveat

Two counters are reported:

* **frame** — frames flagged by tshark (`tcp.analysis.retransmission` +
  `fast_retransmission`) in the `uesimtun0` capture;
* **segment** — iperf3's own sender retransmit counter (the kernel's view).

They **agree exactly** for `baseline` (6/6) and `rate` (69/69), but diverge for
`delay` (710 vs 75) and `loss` (30 vs 175). The reason is that the two measure
different things: tshark flags *captured frames* (affected by GSO aggregation and,
under jitter, by apparent out-of-order), whereas iperf3 counts *TCP segments*
retransmitted by the sender. For the report, the **segment** count (endpoint's
own view) is the primary metric; the frame count is a packet-level cross-check.

## 10. Raw evidence

`results/scenario-b/`: `summary.csv`, `comparison.csv`, `comparison-table.md`,
`plots/comparison.{png,svg}`, `tc-{baseline,delay,loss,rate,final-clean}.txt`, and
per condition `<condition>/{ping-run*,http-run*,tcp-run*.json,udp-run*.json,retrans.pcap,tcp-retrans-source.txt}`.
