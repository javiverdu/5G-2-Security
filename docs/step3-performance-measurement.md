# Step 3 — Performance Measurement and Network Degradation

**Date:** 2026-09-22 (the `delay` condition re-measured 2026-09-28) · **Environment:** same VM topology as Steps 1–2
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
| HTTP response time / connect time / availability | `curl -w '%{time_total} %{time_connect} %{http_code}'` × 10 to `http://10.0.4.10/` |
| TCP throughput | `iperf3 -c 10.0.4.20 -t 3` |
| UDP throughput / loss / jitter | `iperf3 -c 10.0.4.20 -u -b 10M -t 3` |
| TCP retransmissions | capture at `ue:eth0` during a rate-capped transfer: frames flagged by tshark (`tcp.analysis.retransmission` + `tcp.analysis.fast_retransmission`) **and** iperf3's own sender segment counter (both reported; see §9) |

Reproduce (on the VM):

```bash
sudo ./scripts/measure/run-all.sh       # baseline + delay + loss + rate
python3 ./scripts/measure/plot.py       # table + plots (needs matplotlib)
```

## 2. Comparative results (mean of the repetitions)

| Condition | ICMP RTT (ms) | HTTP time (ms) | TCP thr. (Mbit/s) | UDP thr. (Mbit/s) | UDP loss (%) | UDP jitter (ms) | TCP retrans. (tshark / iperf3) |
|---|---|---|---|---|---|---|---|
| **baseline** | 0.081 | 0.60 | 38048.6 | 10.000 | 0.026 | 0.026 | 0 / 0 |
| **delay** | 157.80 | 217.80 | 140.8 | 10.001 | 0.039 | 6.32 | 3 / 2 |
| **loss** | 0.086 | 14.63 | 4434.4 | 10.002 | 1.87 | 0.037 | 21 / 137 |
| **rate** | 14.61 | 1.70 | 18.96 | 10.001 | 0.000 | 0.104 | 0 / 0 |

Generated files: [`comparison-table.md`](../results/step3/comparison-table.md),
[`comparison.csv`](../results/step3/comparison.csv),
[`plots/comparison.png`](../results/step3/plots/comparison.png)
(and `.svg`). The plot uses a **log scale** for TCP throughput because the
baseline value is up to three orders of magnitude above the most degraded one.

## 3. Baseline (reference behaviour)

Before any impairment: ICMP RTT ≈ 0.08 ms with 0% loss, HTTP ≈ 0.6 ms, TCP
throughput ≈ 38 Gbit/s, UDP 10 Mbit/s with 0% loss and ≈ 0.03 ms jitter,
0 TCP retransmissions **in the rate-capped retransmission test**. (The unbounded
~38 Gbit/s throughput runs did report 8–9 sender retransmissions, a negligible
fraction at that volume; retransmission counting is discussed in §1.) This is
the normal, healthy state of the path (the huge TCP figure reflects the in-VM
virtual link, not a physical link — only relative comparisons are meaningful).

## 4. Condition 1 — increased delay (`delay 50ms ±10ms`)

- **ICMP RTT 0.08 ms → 157.8 ms** (runs: 130.0 / 176.8 / 166.6 ms). Each
  direction crosses one shaped access egress, so the nominal round trip is
  ≈ 2 × 50 ms = 100 ms; the measured mean is well above that, with large
  per-run dispersion (`mdev` 42–69 ms, peaks to ~300 ms). This broadening is
  consistent with **queueing / host scheduling jitter added on top of the
  configured delay**: the NetEm qdisc serialises the shaped egress, so probes can
  wait behind the backlog.
- **HTTP 0.6 ms → 217.8 ms.** A request/response needs ≈ 2 round trips (the TCP
  three-way handshake plus the request/response ≈ 2 × 100 ms), matching the
  measured ≈ 218 ms.
- **TCP throughput 38 Gbit/s → 140.8 Mbit/s mean, but highly variable**
  (21.6 / 215.5 / 185.3 Mbit/s; CV 60%, §8). Throughput ≈ window / RTT: the RTT
  rises ~2000× and the auto-tuned window recovers part of the loss, so goodput
  collapses ~270× even though no bandwidth limit is in place. The spread reflects
  how window auto-tuning interacts with a highly variable RTT.
- **UDP jitter 0.03 ms → 6.32 ms** (from the ±10 ms NetEm jitter); throughput
  stays at the sender's 10 Mbit/s and loss is negligible (mean 0.039%). Under
  jitter, out-of-order datagrams can be reported as loss by iperf3's UDP
  accounting, but in this run almost none were.
- **2–3 TCP retransmissions** (iperf3 2 / tshark 3) on the rate-capped transfer —
  far fewer than under packet loss (§5).

## 5. Condition 2 — 1% packet loss (`loss 1%`)

- **ICMP RTT unchanged (0.086 ms)** and most probes still answered; loss is
  visible as occasional drops (one probe batch reported 10% loss because two
  echoes — seq 14 and 17 — were lost out of 20).
- **TCP throughput 38 Gbit/s → 4.4 Gbit/s.** TCP interprets loss as a congestion
  signal: it reduces the congestion window and recovers via retransmissions, so
  goodput drops by ~9× even though the link has spare capacity.
- **TCP retransmissions 0 → 21 frames (tshark) / 137 segments (iperf3 sender).**
  Direct evidence that lost segments were detected and recovered by TCP. The two
  counts differ because the capture aggregates segments (GSO/TSO): a single
  captured frame can carry several TCP segments, so the frame-level count is
  lower than the segment-level count (see §1 and §9).
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
| delay | Latency (RTT ↑) + queueing | TCP goodput ↓ and unstable (window/RTT), HTTP ↑ (≈2 RTT), UDP jitter ↑ (reordering can register as loss) |
| loss | Packet drops | TCP congestion-window reduction + retransmissions, goodput ↓; HTTP tail latency; UDP loss with **no** recovery |
| rate | Bandwidth ceiling | TCP goodput clamped to the limit; queueing delay (RTT ↑) when the link is saturated; UDP unaffected below the cap |

Key takeaways: **latency**, **loss** and **bandwidth** are independent dimensions.
Loss degrades TCP in two ways (reduced window *and* retransmission delay) while
UDP merely loses data; a bandwidth ceiling harms throughput but also introduces
queueing delay; latency alone can cripple TCP goodput without any loss.

## 8. Stability of the measurements

Each metric is the mean of 3 repetitions. Min/max and the coefficient of
variation (CV = σ/μ) show how stable each result is (computed from `summary.csv`):

| Condition | Metric | mean | min | max | CV |
|---|---|---|---|---|---|
| baseline | ICMP RTT (ms) | 0.081 | 0.078 | 0.085 | 3.5% |
| baseline | TCP thr. (Mbit/s) | 38048.6 | 37715.5 | 38543.0 | 0.9% |
| delay | ICMP RTT (ms) | 157.8 | 130.0 | 176.8 | 12.7% |
| delay | TCP thr. (Mbit/s) | 140.8 | 21.6 | 215.5 | 60.5% |
| delay | UDP jitter (ms) | 6.32 | 5.77 | 7.16 | 9.5% |
| loss | TCP thr. (Mbit/s) | 4434.4 | 2837.0 | 5940.6 | 28.6% |
| loss | UDP loss (%) | 1.87 | 1.20 | 2.35 | 26.2% |
| rate | TCP thr. (Mbit/s) | 18.96 | 18.86 | 19.04 | 0.4% |
| rate | ICMP RTT (ms) | 14.61 | 6.21 | 19.36 | 40.8% |

**Interpretation.** Throughput is very stable where the condition is
deterministic: `baseline` (0.9%) and especially `rate` (0.4% — the shaper gives a
hard ceiling). Latency- and loss-driven metrics are inherently more variable:
`loss` TCP throughput varies ~29% because the congestion window re-opens
differently after each drop, and `delay` TCP throughput is the least stable
(60%) because the auto-tuned window competes with a variable RTT. `rate` ICMP RTT
varies (6–19 ms) with queue occupancy at the shaper. Where CV is large but the
absolute values are near zero (e.g. baseline UDP loss), the spread is dominated
by rounding/noise rather than a real effect.

## 9. Measurement caveats

- TCP throughput values are for the in-VM virtual path (≈38 Gbit/s baseline);
  absolute numbers are not representative of a physical network.
- Captures at `ue:eth0` show GSO/TSO-aggregated frames (many > 1500 B), so
  frame-level counts (tshark) and segment-level counts (iperf3 sender) differ;
  both are reported in §2.
- The `delay` TCP throughput and RTT are notably less stable than under the other
  conditions (CV 60% / 13%, §8); the mean should be read together with its
  min/max.
- `http_connect_avg` and `http_availability` are collected by the updated
  `measure.sh` but are not yet in the current `summary.csv` (the re-measured
  `delay` run used the previous script); re-run `run-all.sh` to populate them.
- iperf3 UDP loss under the `delay` condition includes reordering effects; it was
  negligible in the re-measured run (mean 0.039%).
- Baseline showed two lost UDP datagrams in one of three runs (0.077% in that
  run, 0.026% mean) — normal measurement noise.
- UDP throughput is sender-capped at 10 Mbit/s in every condition, so it is
  comparable across conditions; it does not probe the 20 Mbit/s ceiling.

## 10. Raw evidence

Per condition, `results/step3/<condition>/` holds the raw outputs
(`ping-run*.txt`, `http-run*.txt`, `tcp-run*.json`, `udp-run*.json`,
`retrans.pcap`, `tcp-retrans-source.txt`). The updated `measure.sh` writes
`http-run*.txt` as `time_total time_connect http_code` per line.
Aggregated files: `summary.csv`, `comparison.csv`, `comparison-table.md`,
`plots/comparison.{png,svg}` and the `tc-*.txt` impairment states.
Retransmission counts can be recomputed from the captures without re-measuring:
`sudo ./scripts/measure/recount-retrans.sh`.
