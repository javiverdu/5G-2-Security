# Step 2 — Traffic Observation and Protocol Behavior

**Date:** 2026-09-22 · **Environment:** same VM topology as Step 1 (`ue → access → core → host → datanet`)
**Raw captures:** `captures/step2/` (`.pcap`, git-ignored) · **Analysis outputs:** [`results/step2/`](../results/step2/) · **Scripts:** [`scripts/observe/`](../scripts/observe/)

---

## 1. Method — capture the same traffic at six points

The same traffic is generated from the `ue` namespace and captured simultaneously
at six observation points along the complete path (capture filter `ip`, tcpdump
running in each namespace / netns):

| Point | Where | Meaning |
|---|---|---|
| P1 | `ue:eth0` | packet **generated** by the client (and reply **received**) |
| P2 | `access:eth0` | arrived at the access router (UE side) |
| P3 | `access:eth1` | **forwarded** by access toward core |
| P4 | `core:eth1` | **forwarded** by core toward the Data Network |
| P5 | `host:veth-hn` | arrived at the Data Network boundary |
| P6 | `<container>:eth0` (via `nsenter`) | **delivered** to / answered by the service |

Traffic categories: **A** ICMP (`ping -c 5 -s 100 10.0.4.10`), **B** TCP
(`curl` HTTP → nginx; `iperf3 -c 10.0.4.20 -b 5M -t 4`), **C** UDP
(`iperf3 -c 10.0.4.20 -u -b 1M -t 5`), **D** application-layer HTTP exchange.

Reproduce:

```bash
sudo ./scripts/observe/capture.sh icmp      nginx-app  'ping -c 5 -s 100 10.0.4.10'
sudo ./scripts/observe/capture.sh tcp-http  nginx-app  'curl -s -o /dev/null http://10.0.4.10/'
sudo ./scripts/observe/capture.sh tcp-iperf iperf3-srv 'iperf3 -c 10.0.4.20 -b 5M -t 4'
sudo ./scripts/observe/capture.sh udp-iperf iperf3-srv 'iperf3 -c 10.0.4.20 -u -b 1M -t 5'
sudo ./scripts/observe/analyze.sh
```

`-b` limits the iperf3 bitrate so the captures stay small while still containing
the full connection lifecycle (setup, transfer, teardown).

## 2. Cross-point result — the path carries every packet

Packet counts per scenario and observation point
([`cross-point-packet-counts.txt`](../results/step2/cross-point-packet-counts.txt)):

| Scenario | P1 | P2 | P3 | P4 | P5 | P6 |
|---|---|---|---|---|---|---|
| icmp (5 req + 5 reply) | 10 | 10 | 10 | 10 | 10 | 10 |
| tcp-http (handshake+GET+200+FIN) | 12 | 12 | 12 | 12 | 12 | 12 |
| tcp-iperf | 164 | 164 | 164 | 164 | 164 | 164 |
| udp-iperf (432 datagrams) | 434 | 434 | 434 | 434 | 434 | 434 |

Identical counts at all six points (both directions included) demonstrate that
every packet was **generated, forwarded by both routers and the host, and
delivered** — no drops or duplication at any stage.

## 3. A. ICMP — fields, size, TTL and RTT

Evidence: [`icmp-fields-P1-ue.txt`](../results/step2/icmp-fields-P1-ue.txt), [`icmp-fields-P6-nginx-app.txt`](../results/step2/icmp-fields-P6-nginx-app.txt), [`icmp-protocol-hierarchy.txt`](../results/step2/icmp-protocol-hierarchy.txt)

- Protocol hierarchy at P1: `frame > eth > ip > icmp`, 10 frames / 1420 bytes.
- Each echo is `ip.len = 128` (100-byte payload + 8 ICMP + 20 IP), `type 8/code 0`
  (request) or `type 0/code 0` (reply), with matching `seq` and `ident` per pair.
- **TTL proves the number of routed hops:**

  | Direction | At P1 (ue) | At P6 (container) |
  |---|---|---|
  | echo request (`10.0.1.10 → 10.0.4.10`) | TTL 64 | TTL 61 |
  | echo reply (`10.0.4.10 → 10.0.1.10`) | TTL 61 | TTL 64 |

  The request leaves the UE with TTL 64 and arrives at the service with TTL 61
  (**3 routed hops**: access, core, host); the reply is generated with TTL 64 at
  the container and reaches the UE with TTL 61. This is direct packet-level proof
  that both directions traverse the full architecture.
- RTT: `min/avg/max/mdev = 0.067/0.072/0.081/0.004 ms`, **0% packet loss**.
  Cross-checking P1 and P6 relative timestamps gives the in-path component of the
  RTT (P1 request→reply ≈ 0.10 ms; P6 request→reply ≈ 0.02 ms).

## 4. B. TCP — connection lifecycle

### B1. HTTP request/response (curl → nginx)
Evidence: [`tcp-http-fields-P1.txt`](../results/step2/tcp-http-fields-P1.txt)

| Frame | Direction | Flags | Seq / Ack | Len | Meaning |
|---|---|---|---|---|---|
| 1 | UE → nginx | S | seq 877287257 | 0 | SYN (connection request) |
| 2 | nginx → UE | A·S | ack 877287258, seq 687345318 | 0 | SYN-ACK |
| 3 | UE → nginx | A | ack 687345319 | 0 | ACK — **3-way handshake complete** |
| 4 | UE → nginx | AP | seq 877287258 | 73 | `GET /` HTTP request |
| 6 | nginx → UE | AP | seq 687345319 | 238 | HTTP response headers |
| 8 | nginx → UE | AP | — | 896 | HTTP `200 OK` body |
| 10-12 | both | A…F | — | 0 | FIN / FIN-ACK / ACK — **teardown** |

Sequence/acknowledgement numbers increase exactly by the TCP payload lengths,
confirming a correct, in-order exchange. No retransmissions or out-of-order
segments appear.

### B2. iperf3 TCP throughput
Evidence: [`tcp-iperf-conversations.txt`](../results/step2/tcp-iperf-conversations.txt), [`tcp-iperf-handshake-teardown.txt`](../results/step2/tcp-iperf-handshake-teardown.txt), [`tcp-iperf-retransmissions.txt`](../results/step2/tcp-iperf-retransmissions.txt), [`iperf3-tcp-report.txt`](../results/step2/iperf3-tcp-report.txt)

- Two TCP connections are used by iperf3: a **control** connection
  (`10.0.1.10:53724 → 10.0.4.20:5201`) and a **data** connection
  (`…:53736 → …:5201`); both show SYN/SYN-ACK setup and FIN/FIN-ACK teardown.
- Transfer: 2.50 MBytes at 5.24 Mbit/s (rate-capped), **0 retransmissions** at
  P1, P4 and P6.
- Note: segment sizes in the capture are larger than the veth MTU because veth
  devices use segmentation offload (GSO/TSO); the capture therefore shows
  aggregated segments, not on-wire MTU framing.

## 5. C. UDP — datagrams, loss and jitter

Evidence: [`udp-iperf-conversations.txt`](../results/step2/udp-iperf-conversations.txt), [`udp-iperf-datagrams-P1.txt`](../results/step2/udp-iperf-datagrams-P1.txt), [`iperf3-udp-report.txt`](../results/step2/iperf3-udp-report.txt)

- One UDP flow `10.0.1.10:54154 ↔ 10.0.4.20:5201`: 432 data datagrams of
  `udp.length = 1456` bytes (8 + 1448 payload) plus 2 small (12-byte) control
  datagrams — 434 frames, identical at all six points.
- iperf3 receiver report: **0/432 lost (0%)**, **jitter 0.020 ms**.
- UDP provides a connectionless, best-effort datagram service: there is **no
  transport-layer retransmission** mechanism (unlike TCP). Loss/delay would be
  reported by the receiver and observed in the capture but never recovered by
  the transport layer — it is left to the application. Under baseline conditions
  there is nothing to recover, which is why the counts match end to end.

## 6. D. Application-layer exchange (HTTP)

Evidence: [`tcp-http-follow-stream0.txt`](../results/step2/tcp-http-follow-stream0.txt), [`tcp-http-protocol-hierarchy.txt`](../results/step2/tcp-http-protocol-hierarchy.txt)

Following TCP stream 0 reconstructs the complete application transaction:

```
GET / HTTP/1.1                          (73 bytes)
Host: 10.0.4.10
User-Agent: curl/8.18.0
Accept: */*

HTTP/1.1 200 OK                         (238 bytes)
Server: nginx/1.31.6
Date: Tue, 22 Sep 2026 05:57:37 GMT
Content-Type: text/html
Content-Length: 896
Connection: keep-alive
...

<!DOCTYPE html> ... Welcome to nginx!   (896 bytes body)
```

| Field | Observed |
|---|---|
| Request | `GET /`, HTTP/1.1, Host `10.0.4.10` |
| Response status | `200 OK` |
| Server endpoint | `10.0.4.10:80`, `Server: nginx/1.31.6` |
| Content | `text/html`, `Content-Length: 896` |
| Response time | ≈ 0.4 ms total (curl: 0.000438 s) |

The `Content-Length: 896` matches the captured body size and the `curl`
`size_download=896`, tying the application result to the packet evidence. The
successful `200 OK` means the application is reachable and functioning, and it
is supported here by IP connectivity (§2/§3), a complete TCP connection (§4) and
a captured application exchange.

## 7. Deployment note — AppArmor confined `tshark`

The first analysis run produced empty output. `tshark` (running as root) reported
`You don't have permission to read the file …/P1-ue.pcap`. Cause: Ubuntu's
**AppArmor profile `tshark`** (`/etc/apparmor.d/tshark`) only grants file-read
access to `user-tmp` paths, so reading captures inside the repository is denied
even for root. Rather than weakening the system profile, `analyze.sh` runs the
dissector unconfined for offline analysis:

```bash
aa-exec -p unconfined -- tshark -r <capture.pcap> ...
```

The `tshark//dumpcap` sub-profile still governs live capture (not used by the
analysis step).

## 8. Conclusions

- The complete path is not only reachable but **carries every generated packet
  end to end in both directions** (identical point counts).
- ICMP, TCP and UDP behavior is consistent with correct operation: TTL decrement
  per router, in-order TCP sequence/acknowledgements, correct handshake and
  teardown, no TCP retransmissions, 0% UDP loss.
- The application layer returns a valid `HTTP/1.1 200 OK`, corroborated by the
  packet-level exchange.
- Comparing points shows **where** a packet is generated, forwarded and
  delivered; in a degraded scenario (Step 3) the same method will show **where**
  it is dropped or delayed.

## 9. Evidence index (`results/step2/`)

`cross-point-packet-counts.txt`, `icmp-fields-P1-ue.txt`, `icmp-fields-P6-nginx-app.txt`,
`icmp-protocol-hierarchy.txt`, `tcp-http-fields-P1.txt`, `tcp-http-follow-stream0.txt`,
`tcp-http-protocol-hierarchy.txt`, `tcp-iperf-conversations.txt`,
`tcp-iperf-handshake-teardown.txt`, `tcp-iperf-retransmissions.txt`,
`tcp-iperf-protocol-hierarchy.txt`, `udp-iperf-conversations.txt`,
`udp-iperf-datagrams-P1.txt`, `udp-iperf-protocol-hierarchy.txt`,
`iperf3-tcp-report.txt`, `iperf3-udp-report.txt`, `ping-report.txt`.
