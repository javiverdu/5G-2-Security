# Scenario A — IP Addressing & Topology Plan

## Topology

```
+----------------+  10.0.1.0/24  +------------------+  10.0.2.0/24  +-----------------+  10.0.3.0/24  +--------------------+
| ue (netns)     |===============| access (netns)   |===============| core (netns)    |===============| Linux host         |
| eth0           |  veth pair    | eth0        eth1 |  veth pair    | eth0       eth1 |  veth pair    | (Data Network      |
| 10.0.1.10/24   |               | .1          .1   |               | .2         .1   |               |  boundary)         |
| gw: 10.0.1.1   |               | ip_forward=1     |               | ip_forward=1    |               | veth-hn 10.0.3.2/24|
+----------------+               +------------------+               +-----------------+               +---------+----------+
                                                                                                                 |
                                                                                                   docker bridge "datanet"
                                                                                                     10.0.4.0/24 (gw 10.0.4.1)
                                                                                                          +-------+--------+
                                                                                                          |               |
                                                                                                    nginx-app       iperf3-srv
                                                                                                    10.0.4.10:80    10.0.4.20:5201
```

Logical chain: `UE / Client → Access Network → Core Network / Gateway → Data Network → Application Server`

## Interface and addressing table

| Namespace / node | Interface | Peer | IP address | Role |
|---|---|---|---|---|
| `ue` | `eth0` | `access:eth0` | `10.0.1.10/24` | UE/client endpoint |
| `access` | `eth0` | `ue:eth0` | `10.0.1.1/24` | Access router (UE-facing) |
| `access` | `eth1` | `core:eth0` | `10.0.2.1/24` | Access router (core-facing) |
| `core` | `eth0` | `access:eth1` | `10.0.2.2/24` | Core/gateway (access-facing) |
| `core` | `eth1` | `host:veth-hn` | `10.0.3.1/24` | Core/gateway (Data-Network-facing) |
| host (root) | `veth-hn` | `core:eth1` | `10.0.3.2/24` | Data Network boundary |
| host (root) | `br-*` (datanet) | — | `10.0.4.1/24` | Docker bridge gateway |
| container | `nginx-app` | — | `10.0.4.10` | HTTP application server (port 80) |
| container | `iperf3-srv` | — | `10.0.4.20` | Measurement endpoint (port 5201 TCP/UDP) |

## Link / subnet relationships

| Segment | Subnet | Connects |
|---|---|---|
| UE access link | `10.0.1.0/24` | `ue` ↔ `access` |
| Access–core link | `10.0.2.0/24` | `access` ↔ `core` |
| Data Network link | `10.0.3.0/24` | `core` ↔ host |
| Docker service network | `10.0.4.0/24` | host bridge ↔ containers |

## Routing plan

| Node | Route | Next hop |
|---|---|---|
| `ue` | `default` | `10.0.1.1` (access) |
| `access` | `10.0.3.0/24` | `10.0.2.2` (core) |
| `access` | `10.0.4.0/24` | `10.0.2.2` (core) |
| `core` | `10.0.1.0/24` | `10.0.2.1` (access) — return path toward UE |
| `core` | `10.0.4.0/24` | `10.0.3.2` (host) |
| host | `10.0.1.0/24` | `10.0.3.1` (core) — return path toward UE |
| containers | `default` | `10.0.4.1` (host bridge) |

IP forwarding is enabled in `access`, `core`, and the host. NAT between the
namespace side and the Docker network is **disabled on purpose** (routed, not
NATed) so that packet captures show real end-to-end addresses.
