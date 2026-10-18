# Scenario B — Traffic Observation (page 4)

Packet-level analysis of the 5G end-to-end path built on page 3. Captures are
taken at five points with `tcpdump` run from the host inside each container's
netns (`nsenter`), and dissected with `tshark` (`scripts/analyze.sh`).

Raw evidence: `results/scenario-b/` · Captures: `captures/scenario-b/` ·
How to capture: [`capture-points.md`](capture-points.md).

---

## 1. Capture points

| Point | Container | Interface | Filter | Plain / tunneled |
|---|---|---|---|---|
| P1 | `nr_ue` | `uesimtun0` (TUN) | `ip` | plain user data (`10.45.0.2`) |
| P2 | `nr_gnb` | `eth0` (N3) | `udp port 2152` | inside the GTP-U envelope |
| P3 | `upf` | `eth0` (N3) | `udp port 2152` | inside the GTP-U envelope |
| P4 | `upf` | N6 iface (`eth1`) | `ip` | decapsulated |
| P5 | `sb-nginx` / `sb-iperf3` | `eth0` (N6) | `ip` | delivered to the app |

## 2. The GTP-U envelope (the central observation)

`frame.protocols` of the first frame, decoded at each point:

| Point | ICMP | TCP / HTTP |
|---|---|---|
| P1 (UE) | `raw:ip:icmp:data` | `raw:ip:tcp` |
| P2 (gNB, N3) | `eth:ethertype:ip:udp:**gtp**:ip:icmp:data` | `eth:ethertype:ip:udp:**gtp**:ip:tcp` |
| P3 (UPF, N3) | `eth:ethertype:ip:udp:**gtp**:ip:icmp:data` | `eth:ethertype:ip:udp:**gtp**:ip:tcp` |
| P4 (UPF, N6) | `eth:ethertype:ip:icmp:data` | `eth:ethertype:ip:tcp` |
| P5 (app) | `eth:ethertype:ip:icmp:data` | `eth:ethertype:ip:tcp` |

Two facts stand out:

* On **N3** the user packet is inside **GTP-U over UDP/2152** — there is no bare
  `10.45.0.2 → 10.20.6.x` packet on the wire there.
* On **N6** the UPF has removed the envelope and the plain IP flow reappears.
* At **P1** the link layer is `raw`, not `eth`, because `uesimtun0` is a **TUN**
  device (no Ethernet header).

Protocol hierarchy at P3 for the ICMP capture:
`eth > ip > udp > gtp > ip > icmp` (10 frames).

## 3. Cross-point counts — nothing is dropped

| Scenario | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| icmp | 10 | 10 | 10 | 10 | 10 |
| tcp-http | 13 | 13 | 13 | 13 | 13 |
| tcp-iperf | 3178 | 3178 | 3178 | 3178 | 3178 |
| udp-iperf | 497 | 497 | 497 | 497 | 497 |

At P2/P3 the count uses the GTP-U carrier (`udp port 2152`); at P1/P4/P5 the
flow filter (`icmp`, `tcp.port==80`, `tcp.port==5201`, `udp.port==5201`). In
`udp-iperf` the 497 IP frames are 466 UDP data/control frames plus the 31 frames
of iperf3's **TCP control** connection (also carried in the tunnel).

Identical counts at every point prove the packet was **generated, encapsulated,
forwarded, decapsulated and delivered**, with no loss.

## 4. ICMP — size, TTL, sequence

Evidence: `icmp-fields-P1-ue.txt`, `icmp-fields-P5-nginx.txt`.

* `10.45.0.2 → 10.20.6.20` (request) and `10.20.6.20 → 10.45.0.2` (reply),
  `ip.len = 128` (100-byte payload + 8 ICMP + 20 IP), `type 8/0`, `seq 1..5`,
  `ident 9620`.
* **TTL**: request 64 at the UE → **63** at nginx; reply 64 at nginx → **63** at
  the UE. Exactly **one routed hop** (the UPF): unlike Scenario A's three IP
  hops, in the 5G user plane the gNB is not an IP router for the inner packet;
  only the UPF routes it.

## 5. TCP — HTTP request/response (curl-equivalent)

Evidence: `tcp-http-fields-P1.txt`, `tcp-http-follow-stream0.txt`.

| Frame | Direction | Flags | seq / ack | Len | Meaning |
|---|---|---|---|---|---|
| 1 | UE → nginx | S | — | 0 | SYN |
| 2 | nginx → UE | A·S | — | 0 | SYN-ACK |
| 3 | UE → nginx | A | — | 0 | ACK — handshake complete |
| 6 | UE → nginx | AP | — | 20 | `GET / HTTP/1.0` |
| 8 | nginx → UE | AP | — | 233 | HTTP response headers |
| 10 | nginx → UE | AP·F | — | 896 | HTTP `200 OK` body |
| 12–13 | both | F | — | 0 | FIN / teardown |

Followed stream: `GET / HTTP/1.0`, `Host: 10.20.6.20`, response
`HTTP/1.1 200 OK`, `Server: nginx/1.31.6`, `Content-Length: 896`.

## 6. TCP — iperf3 throughput

Evidence: `tcp-iperf-conversations.txt`, `tcp-iperf-retransmissions.txt`.

* Two connections on port 5201: control (`:40076`, 32 frames) and data
  (`:40084`, 3146 frames) — 3178 frames total, identical at all points.
* **0 retransmissions** at P1, P4 and P5.

## 7. UDP — iperf3 datagrams

Evidence: `udp-iperf-conversations.txt`, `udp-iperf-datagrams-P1.txt`.

* One flow `10.45.0.2:49868 ↔ 10.20.6.21:5201`: 466 frames (465 up, 1 down
  control), no loss, jitter 0.168 ms in the iperf3 report.

## 8. Conclusions

* The five-point method shows **where** a packet is generated (P1),
  **encapsulated** (P2/P3), **decapsulated** (P4) and **delivered** (P5).
* The same IP addresses appear at P1, P4 and P5 → the path is **routed, no NAT**;
  only the GTP-U encapsulation changes on N3.
* A `ping` between two N6 containers would prove nothing about 5G; the evidence
  above does, because it starts **inside the UE** and crosses the 5G user plane.

## 9. Evidence index (`results/scenario-b/`)

`cross-point-counts.txt`, `gtp-encapsulation-proof.txt`,
`<label>-phs-<point>.txt`, `icmp-fields-P1-ue.txt`, `icmp-fields-P5-nginx.txt`,
`tcp-http-fields-P1.txt`, `tcp-http-follow-stream0.txt`,
`tcp-iperf-conversations.txt`, `tcp-iperf-retransmissions.txt`,
`udp-iperf-conversations.txt`, `udp-iperf-datagrams-P1.txt`.
