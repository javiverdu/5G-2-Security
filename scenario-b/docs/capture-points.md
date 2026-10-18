# Scenario B — Capture Points (page 4)

Five user-plane points along the 5G path. `tcpdump` runs from the host inside
each container's netns via `nsenter`, because the container images do not include
`tcpdump`.

| Point | Container | Interface | Capture filter | What it shows |
|---|---|---|---|---|
| **P1** | `nr_ue` | `uesimtun0` | `ip` | the UE's own view: src `10.45.0.2`, plain user data |
| **P2** | `nr_gnb` | core iface (detected) | `udp port 2152` | N3: the packet **inside** the GTP-U envelope |
| **P3** | `upf` | core iface (detected) | `udp port 2152` | N3 at the UPF: still encapsulated |
| **P4** | `upf` | N6 iface (detected) | `ip` | N6: **envelope removed**, IP `10.20.6.x` |
| **P5** | `sb-nginx` / `sb-iperf3` | N6 iface (detected) | `ip` | delivered to the application endpoint (nginx for ping/HTTP, iperf3 for throughput) |

> **Interfaces are detected by address, not by name.** Inside a container attached
> to more than one Docker network, `eth0`/`eth1` **are not guaranteed** to keep the
> same order across restarts. `capture.sh` finds the core interface by `172.22.0.x`
> and the N6 interface by `10.20.6.x`; hard-coding `eth0`/`eth1` silently produced
> an empty N3 capture when the order swapped.

Optional control-plane points (registration analysis):

| Point | Container | Filter | What it shows |
|---|---|---|---|
| N2 | `nr_gnb` / `amf` | `sctp port 38412` | NGAP registration (NG Setup, Initial UE Message) |
| N4 | `upf` | `udp port 8805` | PFCP session establishment from the SMF |
| SBI | any NF | `tcp port 7777` | HTTP/2 service calls (NRF, AUSF, UDM, …) |

## The teaching point: the same packet looks different at N3 and N6

* At **P1** the packet is plain IP: `10.45.0.2 → 10.20.6.20`, protocol TCP/UDP/ICMP.
* At **P2/P3** there is no `10.45.0.2 → 10.20.6.20` on the wire as such: the
  whole user packet is **inside** a GTP-U datagram (`UDP 2152`). This is the N3
  envelope.
* At **P4/P5** the UPF has removed the envelope again: plain IP
  `10.45.0.2 → 10.20.6.20` for uplink, and the reply as
  `10.20.6.20 → 10.45.0.2` on the way back.

Because there is **no NAT on N6**, the addresses are the same end to end; only
the encapsulation changes. That is the evidence that the 5G user plane is doing
its job (and not merely bridging Docker networks).

## Traffic set

| Label | Command (from the UE netns) | Protocol |
|---|---|---|
| `icmp` | `ping -c 5 -s 100 10.20.6.20` | ICMP |
| `tcp-http` | `bash /dev/tcp` GET to nginx | TCP / HTTP |
| `tcp-iperf` | `iperf3 -c 10.20.6.21 -b 5M -t 4` | TCP |
| `udp-iperf` | `iperf3 -c 10.20.6.21 -u -b 1M -t 5` | UDP |

The iperf3 client and the HTTP client run in the UE's network namespace (the
UERANSIM image has neither `iperf3` nor `curl`): the HTTP GET uses bash
`/dev/tcp`, and iperf3 runs as
`docker run --rm --network container:nr_ue networkstatic/iperf3`.

## Run

```bash
cd scenario-b
sudo ./scripts/capture.sh icmp
sudo ./scripts/capture.sh tcp-http
sudo ./scripts/capture.sh tcp-iperf
sudo ./scripts/capture.sh udp-iperf
sudo ./scripts/analyze.sh          # -> results/scenario-b/  (needs sudo: root-owned pcaps + AppArmor)
```

Output pcaps: `captures/scenario-b/<label>/P*.pcap` (git-ignored).

## What to look for in the captures

| Question | Where | Expected |
|---|---|---|
| Was the packet generated? | P1 | request present with src `10.45.0.2` |
| Was it forwarded / encapsulated? | P2, P3 | same bytes inside `UDP:2152` |
| Was it decapsulated for N6? | P4 | plain IP `10.45.0.2 ↔ 10.20.6.20` |
| Was it delivered? | P5 | the app sees the same flow |
| Did a response return? | P1, P4, P5 | reply `10.20.6.20 → 10.45.0.2` |
| Is anything dropped? | compare counts P1→P5 | identical counts = nothing dropped |

`ping`'s RTT and iperf3's retransmission/jitter reports complement the packet
evidence; they belong to page 5.
