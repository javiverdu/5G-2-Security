# Scenario A — Screenshot Plan (ultra-fast step-by-step)

Save every screenshot in **`docs/img/`** with the exact filename in the first
column. Most outputs and `.pcap` files **already exist** in `results/` and
`captures/step2/`, so you can take almost all screenshots in a few minutes
without re-running the long benchmarks.

> **Scenario B (5G SA):** see
> [`../scenario-b/docs/screenshots-plan.md`](../scenario-b/docs/screenshots-plan.md)
> (already captured in `docs/img/sb-*`).

---

## 0. One-time preparation (run from repository root)

```bash
cd /media/sf_5G_project/5G-project-RTU   # or ~/5G-project-RTU on the VM
sudo ./scripts/deploy/setup.sh           # bring up Scenario A namespaces + containers
```

If Wireshark gives *Permission denied* when opening a `.pcap` from the shared
folder, copy the captures to `/tmp` once and open them from there:

```bash
cp -r captures/step2 /tmp/step2-caps
cp -r results/step3  /tmp/step3-res
```

---

## 1. Step 1 — Deployment & End-to-End (`docs/img/step1-*.png`)

| Target file (`docs/img/...`) | Exact command to run / file to open | What to do & what must be visible |
|---|---|---|
| `step1-01-namespaces.png` | `cat results/step1/01-namespaces-interfaces.txt && cat results/step1/02-routing-tables.txt` | Terminal shot showing `ue`, `access`, `core` namespaces, their IPs (`10.0.1.0/24`..`10.0.3.0/24`), `veth-hn`, and routing tables. |
| `step1-02-docker-network.png` | `cat results/step1/03-docker-network.txt` | Terminal shot showing `datanet` (`10.0.4.0/24`, gw `10.0.4.1`) and `nginx-app` (`10.0.4.10`) + `iperf3-srv` (`10.0.4.20`) `Up`. |
| `step1-03-listening-ports.png` | `cat results/step1/04-listening-ports.txt` | Terminal shot showing `LISTEN` on `0.0.0.0:80` (`nginx`) and `*:5201` (`iperf3`). |
| `step1-04-verify.png` | `sudo ./scripts/deploy/verify.sh` *(or `cat results/step1/00-verify.txt`)* | Terminal shot with all checks `[ OK ]` and `All checks passed — end-to-end path is operational.` |
| `step1-05-curl.png` | `sudo ip netns exec ue curl -i http://10.0.4.10/` *(or `cat results/step1/06-curl-http.txt`)* | Terminal shot showing `HTTP/1.1 200 OK`, `Welcome to nginx!`, and `896 bytes`. |
| `step1-06-ping-ttl.png` | `cat results/step1/05-e2e-ping.txt` | Terminal shot showing `ttl=64` (`10.0.1.1`), `ttl=63` (`10.0.2.2`), `ttl=62` (`10.0.3.2`), and `ttl=61` (`10.0.4.10`). |

---

## 2. Step 2 — Traffic Observation (`docs/img/step2-*.png`)

All `.pcap` files are already in `captures/step2/` (or `/tmp/step2-caps/` if copied).

| Target file (`docs/img/...`) | Exact command / file to open in Wireshark | What to do in UI / terminal & what must be visible |
|---|---|---|
| `step2-01-protocol-hierarchy.png` | `wireshark captures/step2/udp-iperf/P1-ue.pcap &` *(or `cat results/step2/udp-iperf-protocol-hierarchy.txt`)* | In Wireshark: top menu **Statistics → Protocol Hierarchy**. Must show `frame > eth > ip > udp > iperf3 > data` (434 UDP frames + 29 TCP control frames). |
| `step2-02-conversations.png` | `wireshark captures/step2/tcp-iperf/P1-ue.pcap &` *(or `cat results/step2/tcp-iperf-conversations.txt`)* | In Wireshark: **Statistics → Conversations → TCP tab**. Must show the 2 TCP flows between `10.0.1.10` and `10.0.4.20:5201` (control + data). |
| `step2-03-follow-http.png` | `wireshark captures/step2/tcp-http/P1-ue.pcap &` | Right-click packet 4 (`GET /`) → **Follow → TCP Stream**. Must show red request (`GET / HTTP/1.1`, `Host: 10.0.4.10`) and blue response (`HTTP/1.1 200 OK`, HTML body). |
| `step2-04-handshake.png` | Same window (`captures/step2/tcp-http/P1-ue.pcap`, close Follow modal) | Put filter `tcp.port == 80`. Select frame 1–3 (`[SYN]`, `[SYN, ACK]`, `[ACK]`) and expand **Transmission Control Protocol** in the middle pane showing `Seq`, `Ack`, and `Flags`. |
| `step2-05-icmp-fields.png` | `wireshark captures/step2/icmp/P1-ue.pcap &` *(or `cat results/step2/icmp-fields-P1-ue.txt results/step2/icmp-fields-P6-nginx-app.txt`)* | In Wireshark: select frame 1 (Echo request `10.0.1.10 → 10.0.4.10`, `ttl=64`, `length=128`) and frame 2 (Echo reply `ttl=61`), expanding **Internet Protocol Version 4** and **Internet Control Message Protocol**. |
| `step2-06-six-points.png` | `cat results/step2/cross-point-packet-counts.txt` | Terminal shot showing the exact same packet counts across `P1-ue`, `P2-access-e0`, `P3-access-e1`, `P4-core-e1`, `P5-host-hn`, and `P6-*` (10, 12, 164, 434). |

---

## 3. Step 3 — Performance & Degradation (`docs/img/step3-*.png`)

| Target file (`docs/img/...`) | Exact command / file to open | What to do & what must be visible |
|---|---|---|
| `step3-01-tc-impairments.png` | `cat results/step3/tc-delay.txt results/step3/tc-loss.txt results/step3/tc-rate.txt results/step3/tc-final-clean.txt` | Single terminal shot showing all three NetEm configurations (`delay 50ms 10ms`, `loss 1%`, `rate 20Mbit`) on `access:eth0` & `access:eth1`, plus the final clean `noqueue` state. |
| `step3-02-iperf-tcp.png` | `cat results/step1/07-iperf3.txt && cat results/step3/delay/tcp-retrans-source.txt && cat results/step3/loss/tcp-retrans-source.txt` | Terminal shot comparing baseline throughput (~38 Gbit/s, 0 retr) vs degraded runs with retransmissions (`Retr` column). |
| `step3-03-table.png` | `cat results/step3/comparison-table.md` | Terminal shot showing the Markdown comparative table across `baseline`, `delay`, `loss`, and `rate`. |
| `step3-04-plot.png` | `cp results/step3/plots/comparison.png docs/img/step3-04-plot.png` *(or open with `xdg-open results/step3/plots/comparison.png`)* | You can copy the generated plot directly into `docs/img/step3-04-plot.png`! Shows the 6 comparative bar charts. |
| `step3-05-retransmissions.png` | `wireshark results/step3/loss/retrans.pcap &` | Put display filter `tcp.analysis.retransmission or tcp.analysis.fast_retransmission` and press Enter. Must show the black/red `[TCP Retransmission]` / `[TCP Fast Retransmission]` frames from `10.0.1.10` to `10.0.4.20`. |

---

## 4. Checklist Index (`docs/img/`)

| # | File in `docs/img/` | Step | Done |
|---|---|---|---|
| 1 | `step1-01-namespaces.png` | Step 1 — Namespaces, interfaces & routes | ✅ |
| 2 | `step1-02-docker-network.png` | Step 1 — Docker `datanet` & containers | ✅ |
| 3 | `step1-03-listening-ports.png` | Step 1 — Listening sockets (`:80`, `:5201`) | ✅ |
| 4 | `step1-04-verify.png` | Step 1 — End-to-end `verify.sh` pass | ✅ |
| 5 | `step1-05-curl.png` | Step 1 — HTTP 200 application test | ✅ |
| 6 | `step1-06-ping-ttl.png` | Step 1 — Hop-by-hop TTL decrement (64→61) | ✅ |
| 7 | `step2-01-protocol-hierarchy.png` | Step 2 — Protocol hierarchy | ✅ |
| 8 | `step2-02-conversations.png` | Step 2 — TCP conversations | ✅ |
| 9 | `step2-03-follow-http.png` | Step 2 — Follow HTTP stream | ✅ |
| 10 | `step2-04-handshake.png` | Step 2 — TCP 3-way handshake fields | ✅ |
| 11 | `step2-05-icmp-fields.png` | Step 2 — ICMP header & TTL fields | ✅ |
| 12 | `step2-06-six-points.png` | Step 2 — 6-point packet count table | ✅ |
| 13 | `step3-01-tc-impairments.png` | Step 3 — NetEm `tc` states (delay/loss/rate) | ✅ |
| 14 | `step3-02-iperf-tcp.png` | Step 3 — TCP throughput & retransmissions | ✅ |
| 15 | `step3-03-table.png` | Step 3 — Comparative results table | ✅ |
| 16 | `step3-04-plot.png` | Step 3 — 6-panel comparative plot | ✅ |
| 17 | `step3-05-retransmissions.png` | Step 3 — Wireshark TCP retransmissions | ✅ |
