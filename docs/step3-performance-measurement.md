# Step 3 — Performance Measurement and Network Degradation

**Date:** 2026-09-22 · **Environment:** same VM topology as Steps 1–2
**Raw data:** [`results/step3/`](../results/step3/) (per-condition folders + `summary.csv`) · **Plots:** [`results/step3/plots/`](../results/step3/plots/) · **Scripts:** [`scripts/measure/`](../scripts/measure/)

---

## 1. Experimental design

A fixed measurement set is run first under **baseline** (no impairment) and then
under each degraded condition. Impairments are applied with Linux `tc` + **NetEm**
on **both egress interfaces of the access router** (`eth0` = downlink toward the
UE, `eth1` = uplink toward the core), so both directions of the
UE ↔ Data Network path are affected. After the experiment the network is left
clean.

| Condition | `tc` NetEm configuration | Applied to |
|---|---|---|
| `baseline` | none (qdisc `noqueue`) | — |
| `delay` | `netem delay 50ms 10ms` | `access:eth0`, `access:eth1` |
| `loss` | `netem loss 1%` | `access:eth0`, `access:eth1` |
| `rate` | `netem rate 20mbit` | `access:eth0`, `access:eth1` |

Exact commands and resulting qdisc state are captured in
[`tc-*.txt`](../results/step3/) (e.g. `qdisc netem 8006: root refcnt 3 limit 1000 rate 20Mbit`).

Per condition the following are measured (3 repetitions each, from the UE):

| Metric | Tool |
|---|---|
| ICMP RTT + loss | `ping -c 20 -i 0.2 10.0.4.10` |
| HTTP response time | `curl -w '%{time_total}'` × 10 to `http://10.0.4.10/` |
| TCP throughput | `iperf3 -c 10.0.4.20 -t 3` |
| UDP throughput / loss / jitter | `iperf3 -c 10.0.4.20 -u -b 10M -t 3` |
| TCP retransmissions | capture at `ue:eth0` during a rate-capped transfer, counted with tshark |

Reproduce (on the VM):

```bash
sudo ./scripts/measure/run-all.sh       # baseline + delay + loss + rate
python3 ./scripts/measure/plot.py       # table + plots (needs matplotlib)
```

## 2. Comparative results (mean of the repetitions)

| Condition | ICMP RTT (ms) | HTTP time (ms) | TCP thr. (Mbit/s) | UDP thr. (Mbit/s) | UDP loss (%) | UDP jitter (ms) | TCP retrans. |
|---|---|---|---|---|---|---|---|
| **baseline** | 0.081 | 0.60 | 38048.6 | 10.000 | 0.026 | 0.026 | 0 |
| **delay** | 103.90 | 239.70 | 12.77 | 9.999 | 1.10 | 7.46 | 8 |
| **loss** | 0.086 | 14.63 | 4434.4 | 10.002 | 1.87 | 0.037 | 21 |
| **rate** | 14.61 | 1.70 | 18.96 | 10.001 | 0.000 | 0.104 | 0 |

Generated files: [`comparison-table.md`](../results/step3/comparison-table.md),
[`comparison.csv`](../results/step3/comparison.csv),
[`plots/comparison.png`](../results/step3/plots/comparison.png)
(and `.svg`). The plot uses a **log scale** for TCP throughput because the
baseline value is three orders of magnitude above the degraded ones.

## 3. Baseline (reference behaviour)

Before any impairment: ICMP RTT ≈ 0.08 ms with 0% loss, HTTP ≈ 0.6 ms, TCP
throughput ≈ 38 Gbit/s, UDP 10 Mbit/s with 0% loss and ≈ 0.03 ms jitter,
0 TCP retransmissions. This is the normal, healthy state of the path (the huge
TCP figure reflects the in-VM virtual link, not a physical link — only relative
comparisons are meaningful).

## 4. Condition 1 — increased delay (`delay 50ms ±10ms`)

- **ICMP RTT 0.08 ms → 103.9 ms.** Each direction crosses one shaped access
  egress interface, so the round trip gains ≈ 2 × 50 ms, plus jitter.
- **HTTP 0.6 ms → 239.7 ms.** A request/response needs ≈ 2 round trips: the TCP
  three-way handshake (1 RTT) plus the request/response (1 RTT) ≈ 2 × 100 ms,
  matching the measured ≈ 240 ms.
- **TCP throughput 38 Gbit/s → 12.8 Mbit/s.** Latency-bound: for a given TCP
  window, throughput ≈ window / RTT. Increasing the RTT by >1000× while the
  window stays bounded collapses goodput, even though no bandwidth limit exists.
- **UDP jitter 0.03 ms → 7.46 ms** (from the ±10 ms NetEm jitter); throughput
  stays at the sender's 10 Mbit/s. The apparent 1.1% "loss" is largely
  **reordering**: with delay jitter, datagrams can arrive out of order and
  iperf3's UDP accounting treats out-of-window ones as lost.
- **8 TCP retransmissions** appear on the (rate-capped) transfer capture as
  delayed acknowledgements/timeouts accumulate.

## 5. Condition 2 — 1% packet loss (`loss 1%`)

- **ICMP RTT unchanged (0.086 ms)** and most probes still answered; loss is
  visible as occasional drops (one probe batch reported 10% loss because a
  single echo was lost out of 20).
- **TCP throughput 38 Gbit/s → 4.4 Gbit/s.** TCP interprets loss as a congestion
  signal: it reduces the congestion window and recovers via retransmissions, so
  goodput drops by ~9× even though the link has spare capacity.
- **TCP retransmissions 0 → 21.** Direct packet-level evidence that lost
  segments were detected and recovered by TCP.
- **HTTP 0.6 ms → 14.6 ms average,** with a tail of 41.7 ms in one run: when a
  handshake or data segment is lost, the request waits for the retransmission.
- **UDP loss 1.1–2.4% (mean 1.87%),** consistent with the configured 1% (plus
  reordering/rounding effects); UDP does **not** recover it — nothing is
  retransmitted, the datagrams are simply gone.
- No change to jitter: loss and delay are independent NetEm properties.

## 6. Condition 3 — 20 Mbit/s bandwidth limit (`rate 20mbit`)

- **TCP throughput 38 Gbit/s → 19.0 Mbit/s**, i.e. capped exactly at the token
  bucket's limit (slightly below 20 Mbit/s because of per-packet/ACK overhead and
  the shaper's granularity).
- **ICMP RTT 0.08 ms → 14.6 ms** (6–19 ms across runs). This is **bufferbloat /
  queueing delay**: while TCP saturates the shaped link, packets queue in the
  NetEm token bucket, so even small ICMP probes wait behind the backlog.
- **UDP unaffected (10 Mbit/s, 0% loss)** because the sender is capped below the
  limit (`-b 10M < 20 Mbit/s`); this shows the limit only bites when demand
  exceeds it.
- **0 retransmissions** — the condition adds delay/queueing, not loss.

## 7. Why the changes occur — linking conditions to protocol behaviour

| Condition | Primary effect | Affected protocol behaviour |
|---|---|---|
| delay | Latency (RTT ↑) | TCP throughput ↓ (window/RTT), HTTP ↑ (≈2 RTT), UDP jitter ↑ / apparent loss via reordering |
| loss | Packet drops | TCP congestion-window reduction + retransmissions, goodput ↓; HTTP tail latency; UDP loss with **no** recovery |
| rate | Bandwidth ceiling | TCP goodput clamped to the limit; queueing delay (RTT ↑) when the link is saturated; UDP unaffected below the cap |

Key takeaways: **latency**, **loss** and **bandwidth** are independent dimensions.
Loss degrades TCP in two ways (reduced window *and* retransmission delay) while
UDP merely loses data; a bandwidth ceiling harms throughput but also introduces
queueing delay; latency alone can cripple TCP goodput without any loss.

## 8. Measurement caveats

- TCP throughput values are for the in-VM virtual path (≈38 Gbit/s baseline);
  absolute numbers are not representative of a physical network.
- iperf3 UDP loss under the `delay` condition includes reordering effects.
- Baseline showed one lost UDP datagram in one of three runs (0.026% mean) —
  normal measurement noise.
- UDP throughput is sender-capped at 10 Mbit/s in every condition, so it is
  comparable across conditions; it does not probe the 20 Mbit/s ceiling.

## 9. Raw evidence

Per condition, `results/step3/<condition>/` holds the raw outputs
(`ping-run*.txt`, `http-run*.txt`, `tcp-run*.json`, `udp-run*.json`,
`retrans.pcap`, `tcp-retrans-source.txt`). Aggregated files:
`summary.csv`, `comparison.csv`, `comparison-table.md`, `plots/comparison.{png,svg}`
and the `tc-*.txt` impairment states.
