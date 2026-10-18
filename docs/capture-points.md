# Scenario A — Capture Points (packet observation)

How the multi-point captures of Scenario A are taken and what each point shows.
Full analysis: [`step2-traffic-observation.md`](step2-traffic-observation.md).
Raw dissections: `results/step2/`; `.pcap` files: `captures/step2/`.

`tcpdump` runs inside each Linux namespace and on the host-side veth; the tooling
is [`scripts/observe/capture.sh`](../scripts/observe/capture.sh) (capture) and
[`scripts/observe/analyze.sh`](../scripts/observe/analyze.sh) (tshark).

## 1. The six points

| Point | Where | Interface | Meaning |
|---|---|---|---|
| **P1** | `ue` | `eth0` | packet **generated** by the client (and reply received) |
| **P2** | `access` | `eth0` | arrived at the access router (UE side) |
| **P3** | `access` | `eth1` | **forwarded** by access toward core |
| **P4** | `core` | `eth1` | **forwarded** by core toward the Data Network |
| **P5** | host | `veth-hn` | arrived at the Data Network boundary |
| **P6** | the target container | `eth0` (via `nsenter`) | **delivered to / answered by** the service |

Capture filter is `ip` at every point; the per-traffic flow filter is applied
during analysis (`icmp`, `tcp.port==80`, `tcp.port==5201`, `udp.port==5201`).

## 2. What the captures prove

* **Generated → forwarded → delivered**: identical packet counts at all six
  points (see `results/step2/cross-point-packet-counts.txt`).
* **Routing**: the ICMP reply TTL decreases by exactly one per hop
  (64 → 63 → 62 → 61 for access, core, host), the packet-level proof that each
  router forwards.
* **L2 vs L3** (summary in [step2 §2.1](step2-traffic-observation.md#21-ip-addresses-stay-end-to-end--only-l2-and-ttl-change)): the **IP addresses never change**
  (`10.0.1.10 ↔ 10.0.4.10`, no NAT); the **Ethernet MAC** changes at each hop and
  the **TTL** decrements.
* **Protocol fields**: HTTP handshake + `GET /` + `200 OK`; TCP seq/ack; UDP
  datagram lengths.

> Contrast with Scenario B: there the user packet is **encapsulated in GTP-U**
> between the gNB and the UPF (see
> [`../scenario-b/docs/capture-points.md`](../scenario-b/docs/capture-points.md)).

## 3. Run

```bash
sudo ./scripts/observe/capture.sh icmp      nginx-app  'ping -c 5 -s 100 10.0.4.10'
sudo ./scripts/observe/capture.sh tcp-http  nginx-app  'curl -s -o /dev/null http://10.0.4.10/'
sudo ./scripts/observe/capture.sh tcp-iperf iperf3-srv 'iperf3 -c 10.0.4.20 -b 5M -t 4'
sudo ./scripts/observe/capture.sh udp-iperf iperf3-srv 'iperf3 -c 10.0.4.20 -u -b 1M -t 5'
sudo ./scripts/observe/analyze.sh
```

Output: `captures/step2/<label>/P1-ue.pcap … P6-<container>.pcap`
(`captures/` is git-ignored) and dissections in `results/step2/`.

## 4. What to look for, per question

| Question | Points | Expected |
|---|---|---|
| Was the packet generated? | P1 | request present with src `10.0.1.10` |
| Was it forwarded? | P3, P4 | same packet, TTL decreased |
| Was it delivered? | P6 | the container sees the same flow |
| Did a response return? | P1, P5, P6 | reply `10.0.4.x → 10.0.1.10` |
| Anything dropped? | compare P1…P6 | identical counts = nothing dropped |

Timing (RTT), throughput, loss and jitter are the Step 3 measurements
([`step3-performance-measurement.md`](step3-performance-measurement.md)).
