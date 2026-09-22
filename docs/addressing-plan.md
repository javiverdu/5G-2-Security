# Addressing & Routing Plan

Canonical address and routing plan for Scenario A. The implemented topology
(diagram with IP addresses) is in the [README](../README.md#architecture).

## Subnet relationships

| Segment | Subnet | Connects |
|---|---|---|
| UE access link | `10.0.1.0/24` | `ue` ↔ `access` |
| Access–core link | `10.0.2.0/24` | `access` ↔ `core` |
| Data Network link | `10.0.3.0/24` | `core` ↔ host |
| Docker service network | `10.0.4.0/24` | host bridge ↔ containers |

## Interfaces and IP addressing

| Node | Interface | Peer | IP address | Role |
|---|---|---|---|---|
| `ue` | `eth0` | `access:eth0` | `10.0.1.10/24` | UE/client endpoint |
| `access` | `eth0` | `ue:eth0` | `10.0.1.1/24` | Access router (UE-facing) |
| `access` | `eth1` | `core:eth0` | `10.0.2.1/24` | Access router (core-facing) |
| `core` | `eth0` | `access:eth1` | `10.0.2.2/24` | Core/gateway (access-facing) |
| `core` | `eth1` | `host:veth-hn` | `10.0.3.1/24` | Core/gateway (Data-Network-facing) |
| host | `veth-hn` | `core:eth1` | `10.0.3.2/24` | Data Network boundary |
| host | `br-*` (datanet) | — | `10.0.4.1/24` | Docker bridge gateway |
| container | `nginx-app` | — | `10.0.4.10` | HTTP server, port 80 |
| container | `iperf3-srv` | — | `10.0.4.20` | Measurement endpoint, port 5201 TCP/UDP |

## Routing plan

| Node | Route | Next hop | Purpose |
|---|---|---|---|
| `ue` | `default` | `10.0.1.1` | All traffic via the access router |
| `access` | `10.0.3.0/24` | `10.0.2.2` | Toward the Data Network |
| `access` | `10.0.4.0/24` | `10.0.2.2` | Toward the Docker service network |
| `core` | `10.0.1.0/24` | `10.0.2.1` | Return path toward the UE |
| `core` | `10.0.4.0/24` | `10.0.3.2` | Toward the Docker service network |
| host | `10.0.1.0/24` | `10.0.3.1` | Return path toward the UE |
| containers | `default` | `10.0.4.1` | Automatic via the Docker bridge gateway |

IP forwarding is enabled in `access`, `core` and the host.

## Notes

- **No NAT** between the namespace side and the Docker network: the path is fully
  routed so captures show real end-to-end addresses.
- The VM's VirtualBox NAT interface (`enp0s3`) also uses `10.0.2.0/24`. This
  overlaps with the access–core link but causes no conflict: namespaces have
  isolated interfaces and routing tables, and the host never resolves
  `10.0.2.0/24` into the namespace side.
