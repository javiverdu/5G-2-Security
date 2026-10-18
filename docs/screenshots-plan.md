# Screenshot Plan — visual evidence for the final report

Screenshots to take in the **Ubuntu desktop** environment, with the command that
prepares each state. Screenshots are *illustrations*; the authoritative graded
evidence stays as text/`.pcap` under `results/` and `captures/`.

> **Scenario B (5G SA):** see
> [`../scenario-b/docs/screenshots-plan.md`](../scenario-b/docs/screenshots-plan.md).

## 0. Setup (Scenario A)

| Item | How |
|---|---|
| Multi-node terminal | `sudo ./scripts/observe/gui-workspace.sh` (tmux: host/ue/access/core) |
| Packet GUI | `sudo apt install wireshark` |
| Diagram | Mermaid preview (VS Code) or <https://mermaid.live>, export PNG |

Before every shot: font 14–16 px, fixed-size window, clean prompt, `clear`, and
make sure the command is visible together with its output.

> Wireshark cannot capture inside `ip netns`. Capture with `tcpdump` (the scripts
> do) and open the resulting `.pcap`. If AppArmor blocks reading a capture, copy
> it to `/tmp` or `$HOME`.

## 1. Step 1 — deployment & end-to-end

| Shot | Prepare with | Must show |
|---|---|---|
| `step1-00-topology` | Mermaid Fig. 1 (README §Architecture) | nodes, IPs, subnets |
| `step1-01-namespaces` | `gui-workspace.sh`; in each pane `ip -brief addr; ip route` | 3 namespaces + host, IPs/routes |
| `step1-02-docker-network` | `docker network inspect datanet`; `docker ps` | bridge, `10.0.4.0/24`, containers `Up` |
| `step1-03-listening-ports` | `results/step1/04-listening-ports.txt` | nginx `0.0.0.0:80`, iperf3 `*:5201` |
| `step1-04-verify` | `sudo ./scripts/deploy/verify.sh` | all checks `[ OK ]` |
| `step1-05-curl` | `sudo ip netns exec ue curl -v http://10.0.4.10/` | `HTTP/1.1 200 OK`, `Content-Length: 896` |
| `step1-06-ping-ttl` | `sudo ip netns exec ue ping -c2 10.0.4.10` | `ttl=61` (3 routed hops) |
| `step1-07-wireshark-icmp` | `captures/step2/icmp/P1-ue.pcap` vs `P6-nginx-app.pcap` | IP `ttl` 64→61, ICMP fields |

## 2. Step 2 — traffic observation

```bash
sudo ./scripts/observe/capture.sh icmp      nginx-app  'ping -c 5 -s 100 10.0.4.10'
sudo ./scripts/observe/capture.sh tcp-http  nginx-app  'curl -s -o /dev/null http://10.0.4.10/'
sudo ./scripts/observe/capture.sh tcp-iperf iperf3-srv 'iperf3 -c 10.0.4.20 -b 5M -t 4'
sudo ./scripts/observe/capture.sh udp-iperf iperf3-srv 'iperf3 -c 10.0.4.20 -u -b 1M -t 5'
sudo ./scripts/observe/analyze.sh
```

| Shot | Wireshark / command | Must show |
|---|---|---|
| `step2-01-protocol-hierarchy` | *Statistics → Protocol Hierarchy* | `eth > ip > icmp/tcp/udp` |
| `step2-02-conversations` | *Statistics → Conversations* | flows `:80`, `:5201` |
| `step2-03-follow-http` | *Follow → TCP Stream* | `GET /`, `200 OK`, body |
| `step2-04-handshake` | expand SYN/SYN-ACK/ACK | flags, seq, ack |
| `step2-05-icmp-fields` | expand ICMP | `ip.len=128`, `type/code`, `seq`, `ttl` |
| `step2-06-six-points` | `cat results/step2/cross-point-packet-counts.txt` | identical counts at 6 points |

## 3. Step 3 — performance & degradation

```bash
sudo ./scripts/measure/impair.sh delay      # / loss / rate / baseline
sudo ./scripts/measure/run-all.sh
python3 ./scripts/measure/plot.py
```

| Shot | Prepare with | Must show |
|---|---|---|
| `step3-01-tc-delay` | `impair.sh delay` | `netem … delay 50ms 10ms` |
| `step3-02-tc-loss` | `impair.sh loss` | `netem … loss 1%` |
| `step3-03-tc-rate` | `impair.sh rate` | `netem … rate 20Mbit` |
| `step3-04-iperf-tcp` | baseline vs degraded | throughput collapse |
| `step3-05-table` | `cat results/step3/comparison-table.md` | comparative numbers |
| `step3-06-plot` | `results/step3/plots/comparison.png` | Fig. — 6 panels |
| `step3-07-retransmissions` | `loss/retrans.pcap`, filter `tcp.analysis.retransmission` | highlighted frames |

## 4. Wireshark tips

* Columns: right-click a field → *Apply as Column* (`ip.ttl`, `tcp.flags.str`,
  `icmp.seq`, `udp.length`).
* Statistics: *Protocol Hierarchy*, *Conversations*, *I/O Graph*.
* Retransmissions: *Analyze → Expert Information* + filter
  `tcp.analysis.retransmission or tcp.analysis.fast_retransmission`.

## 5. Index

Fill this and reference each image in the report as `![...](img/<file>)`.
Naming: `stepN-NN-description.png` (Scenario A), `sb-pageN-NN-description.png`
(Scenario B).

| # | File | Requirement | Done |
|---|---|---|---|
| 1 | `step1-01-namespaces.png` | namespaces/interfaces/IPs/routes | ☐ |
| 2 | `step1-04-verify.png` | end-to-end operational | ☐ |
| 3 | `step1-05-curl.png` | application test (HTTP 200) | ☐ |
| 4 | `step2-01-protocol-hierarchy.png` | protocol hierarchy | ☐ |
| 5 | `step2-03-follow-http.png` | HTTP request/response | ☐ |
| 6 | `step2-06-six-points.png` | generated/forwarded/delivered | ☐ |
| 7 | `step3-06-plot.png` | comparative plot | ☐ |
| 8 | `step3-07-retransmissions.png` | TCP retransmissions | ☐ |
