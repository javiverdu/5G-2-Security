# Step 1 — Network Deployment and End-to-End Operation

**Date:** 2026-09-21 · **Environment:** single Linux VM (`192.168.56.104`, VirtualBox), Ubuntu with Docker 29.8.1
**Raw evidence:** [`results/step1/`](../results/step1/) · **Scripts:** [`scripts/deploy/`](../scripts/deploy/), [`scripts/teardown/`](../scripts/teardown/)

---

## 1. Topology

Hybrid Linux + Docker architecture implementing the reference chain
`UE / Client → Access Network → Core Network / Gateway → Data Network → Application Server`:

```
+----------------+  10.0.1.0/24  +------------------+  10.0.2.0/24  +-----------------+  10.0.3.0/24  +--------------------+
| ue (netns)     |===============| access (netns)   |===============| core (netns)    |===============| Linux host         |
| eth0           |  veth pair    | eth0        eth1 |  veth pair    | eth0       eth1 |  veth pair    | (Data Network      |
| 10.0.1.10/24   |               | .1          .1   |               | .2         .1   |               |  boundary)         |
| gw: 10.0.1.1   |               | ip_forward=1     |               | ip_forward=1    |               | veth-hn 10.0.3.2/24|
+----------------+               +------------------+               +-----------------+               +---------+----------+
                                                                                                                 |
                                                                                                   docker bridge "datanet"
                                                                                                   br-b4c27d9a184c
                                                                                                     10.0.4.0/24 (gw 10.0.4.1)
                                                                                                          +-------+--------+
                                                                                                          |               |
                                                                                                    nginx-app       iperf3-srv
                                                                                                    10.0.4.10:80    10.0.4.20:5201
```

Deployment is fully scripted and idempotent: `sudo ./scripts/deploy/setup.sh`
(teardown: `sudo ./scripts/teardown/cleanup.sh`).

## 2. Principal components

| Component | Implementation | Function |
|---|---|---|
| UE / client | Linux network namespace `ue` | Traffic source; default gateway toward access router |
| Access Router | Linux network namespace `access` | Forwards between UE link and core link (`ip_forward=1`) |
| Core / Gateway | Linux network namespace `core` | Forwards between access link and Data Network (`ip_forward=1`) |
| Data Network boundary | Linux host (root namespace), interface `veth-hn` | Integration boundary between namespace network and containers |
| Service network | Docker user-defined bridge `datanet` (`br-b4c27d9a184c`) | Containerized extension of the Data Network |
| Application server | Container `nginx-app` (`nginx:latest`) | HTTP service on port 80 |
| Measurement endpoint | Container `iperf3-srv` (`networkstatic/iperf3:latest`, `-s`) | iperf3 server on port 5201 TCP/UDP |

## 3. Interfaces and IP addressing

Evidence: [`01-namespaces-interfaces.txt`](../results/step1/01-namespaces-interfaces.txt)

| Node | Interface | Peer | IP address | Role |
|---|---|---|---|---|
| `ue` | `eth0` | `access:eth0` | `10.0.1.10/24` | UE/client endpoint |
| `access` | `eth0` | `ue:eth0` | `10.0.1.1/24` | Access router (UE-facing) |
| `access` | `eth1` | `core:eth0` | `10.0.2.1/24` | Access router (core-facing) |
| `core` | `eth0` | `access:eth1` | `10.0.2.2/24` | Core/gateway (access-facing) |
| `core` | `eth1` | `host:veth-hn` | `10.0.3.1/24` | Core/gateway (DN-facing) |
| host | `veth-hn` | `core:eth1` | `10.0.3.2/24` | Data Network boundary |
| host | `br-b4c27d9a184c` | — | `10.0.4.1/24` | Docker bridge gateway |
| container | `nginx-app` | — | `10.0.4.10` | HTTP server (port 80) |
| container | `iperf3-srv` | — | `10.0.4.20` | iperf3 server (port 5201) |

| Segment | Subnet | Connects |
|---|---|---|
| UE access link | `10.0.1.0/24` | `ue` ↔ `access` |
| Access–core link | `10.0.2.0/24` | `access` ↔ `core` |
| Data Network link | `10.0.3.0/24` | `core` ↔ host |
| Docker service network | `10.0.4.0/24` | host bridge ↔ containers |

> **Note (subnet relationship):** the VM's VirtualBox NAT interface (`enp0s3`) also
> uses `10.0.2.0/24`. This overlaps with the access–core link but causes no
> conflict: network namespaces have fully isolated interface and routing state,
> and no host stack ever needs to resolve `10.0.2.0/24` into the namespace side.

## 4. Routing

Evidence: [`02-routing-tables.txt`](../results/step1/02-routing-tables.txt)

| Node | Route | Next hop | Purpose |
|---|---|---|---|
| `ue` | `default` | `10.0.1.1` | All traffic via access router |
| `access` | `10.0.3.0/24` | `10.0.2.2` | Toward Data Network |
| `access` | `10.0.4.0/24` | `10.0.2.2` | Toward Docker service network |
| `core` | `10.0.1.0/24` | `10.0.2.1` | Return path toward UE |
| `core` | `10.0.4.0/24` | `10.0.3.2` | Toward Docker service network |
| host | `10.0.1.0/24` | `10.0.3.1` | Return path toward UE |
| containers | `default` | `10.0.4.1` | Automatic (Docker bridge gateway) |

IP forwarding is enabled in `access`, `core` and the host. There is **no NAT**
between the namespace side and the Docker network: the path is fully routed, so
packet captures show real end-to-end addresses (important for Step 2).

## 5. Docker network, services and listening ports

Evidence: [`03-docker-network.txt`](../results/step1/03-docker-network.txt), [`04-listening-ports.txt`](../results/step1/04-listening-ports.txt)

- Docker network `datanet`: driver `bridge`, subnet `10.0.4.0/24`, gateway `10.0.4.1`.
- `nginx-app` (`nginx:latest`) Up, `80/tcp` → listening `0.0.0.0:80` inside its netns (verified with `nsenter … ss -tlnp`).
- `iperf3-srv` (`networkstatic/iperf3:latest -s`) Up, `5201/tcp` → listening `*:5201` TCP (and UDP) inside its netns.

## 6. End-to-end verification

Evidence: [`00-verify.txt`](../results/step1/00-verify.txt), [`05-e2e-ping.txt`](../results/step1/05-e2e-ping.txt), [`06-curl-http.txt`](../results/step1/06-curl-http.txt), [`07-iperf3.txt`](../results/step1/07-iperf3.txt)

`sudo ./scripts/deploy/verify.sh` — **all checks passed**:

- Namespaces `ue`, `access`, `core` exist.
- ICMP reachability at every stage (see TTL analysis below).
- `curl http://10.0.4.10/` from `ue` → **HTTP 200**, nginx welcome page (896 bytes), total time ≈ 0.4 ms.
- `iperf3 -c 10.0.4.20` from `ue` → TCP test completed, **≈ 36 Gbit/s** (in-VM virtual path).

### TTL as path evidence

The observed ICMP reply TTL decreases exactly one unit per routing hop, which
proves the packets traverse each forwarding stage:

| Target | TTL | Interpretation |
|---|---|---|
| `10.0.1.1` (access) | 64 | Directly connected — no routing |
| `10.0.2.2` (core) | 63 | 1 routed hop (access) |
| `10.0.3.2` (host) | 62 | 2 routed hops (access, core) |
| `10.0.4.10` / `10.0.4.20` (containers) | 61 | 3 routed hops (access, core, host) |

## 7. End-to-end communication path explained

Forward path of an HTTP request from the UE to the application server:

1. **ue** sends `10.0.1.10 → 10.0.4.10:80`. Its default route delivers the packet to `access` via `eth0`.
2. **access** looks up `10.0.4.0/24 via 10.0.2.2` and forwards out `eth1` to `core`.
3. **core** looks up `10.0.4.0/24 via 10.0.3.2` and forwards out `eth1` to the host's `veth-hn`.
4. **host** routes to the connected subnet `10.0.4.0/24` on `br-b4c27d9a184c`; netfilter FORWARD is traversed and the packet is explicitly accepted by the `DOCKER-USER` rule (see §8). The bridge delivers the frame to the `nginx-app` veth.
5. **nginx** accepts the TCP connection on `0.0.0.0:80` and returns the HTTP response.

Return path: container default gateway `10.0.4.1` (host) → host route `10.0.1.0/24 via 10.0.3.1` → `core` route `10.0.1.0/24 via 10.0.2.1` → `access` (connected `10.0.1.0/24`) → `ue`. Routing is symmetric, which also keeps the (loose) `rp_filter` checks satisfied on every hop.

The observations that demonstrate the complete path is operational are therefore
not just "ping works": interfaces are up with the planned addresses on every
stage, routing entries exist and are used (TTL decrement), both services are
listening on their documented ports, an application-level HTTP 200 is returned,
and a multi-gigabit TCP stream completes through the same path.

## 8. Deployment diagnosis — Docker's hardened defaults found and fixed

The first end-to-end attempt failed only on the last segment (ue → containers),
while ue → access/core/host already worked. Multi-point packet captures
(`core:eth1`, `host:veth-hn`, `br-<id>`) showed requests arriving at the host but
never entering the bridge. Two independent layers of Docker's (v29.8.1) hardened
default forwarding policy were identified:

1. **Raw `PREROUTING` drops per container IP.** A `table ip raw` contained
   `drop` rules for `ip daddr 10.0.4.10/10.0.4.20` arriving from any interface
   except the container bridge — so packets were discarded *before* the FORWARD
   chain (all FORWARD counters stayed at 0, and `nstat` showed `IpInReceives`
   increasing without `IpForwDatagrams`). The rules kept reappearing with the
   current bridge name after every `docker network (re)create`. A binary wrapper
   on `iptables` caught the culprit: **`/usr/bin/dockerd` itself programs them**
   (`iptables --wait -t raw -A PREROUTING -d <container-ip> ! -i br-<id> -j DROP`)
   as part of Docker ≥ 28's hardening against direct routed access to container
   IPs. **Fix (root cause):** daemon option **`allow-direct-routing: true`** in
   `/etc/docker/daemon.json` + `systemctl restart docker`. Setup script applies
   it idempotently and keeps a safety-net removal of the raw table.

2. **Filter-layer drop of routed container traffic.** Docker also sets the
   `FORWARD` policy to `DROP` and adds `DROP all !br-<id> br-<id>` in the
   `DOCKER` chain, so even with (1) removed, traffic routed (not published-port
   NATed) toward the containers is discarded. **Fix (Docker's documented
   extension point):** `iptables -I DOCKER-USER -i veth-hn -d 10.0.4.0/24
   -j ACCEPT`. Counters in `08-firewall-state.txt` show this rule matching the
   full traffic of the iperf3 tests, confirming it carries the data path.

Diagnostic steps used: hop isolation by ICMP TTL → per-hop tcpdump → netfilter
counter inspection → `nstat` delta analysis → `nft monitor` + journal/process
snapshots at re-creation time → binary wrappers on `nft`/`iptables` that
identified `dockerd` as the rule origin.

Both fixes are integrated in `scripts/deploy/setup.sh` (and reversed in
`scripts/teardown/cleanup.sh`), so the deployment is reproducible from scratch.

## 9. Reproduce

```bash
sudo ./scripts/teardown/cleanup.sh   # optional: start clean
sudo ./scripts/deploy/setup.sh       # deploy namespaces, links, routes, Docker services
sudo ./scripts/deploy/verify.sh      # end-to-end verification (all checks must pass)
```
