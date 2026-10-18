# Scenario B — Addressing & Interfaces Plan

Canonical addressing for the 5G Standalone deployment. Values are fixed here so
the page-4 captures and the page-5 measurements do not need a topology rewrite.

## 1. Subnets

| Segment | Subnet | Purpose |
|---|---|---|
| 5G core network | `172.22.0.0/24` | N2, N3, N4 and SBI between NFs and the gNB |
| UE PDU pool | `10.45.0.0/16` | addresses handed to the UE (`uesimtun0`), gateway `10.45.0.1` |
| Data Network (N6) | `10.20.6.0/24` | applications: nginx `.20`, iperf3 `.21` |

## 2. Core and RAN addresses (`172.22.0.0/24`)

| Node | Address | Role |
|---|---|---|
| mongo | `172.22.0.2` | subscriber database (disk for UDR) |
| nrf | `172.22.0.12` | service registry (directory) |
| scp | `172.22.0.35` | service communication proxy |
| ausf | `172.22.0.11` | authentication |
| udm | `172.22.0.13` | subscription management |
| udr | `172.22.0.14` | subscription repository |
| pcf | `172.22.0.27` | policy |
| bsf | `172.22.0.29` | binding support |
| nssf | `172.22.0.28` | slice selection |
| smf | `172.22.0.7` | session management |
| upf | `172.22.0.8` | user-plane forwarder |
| amf | `172.22.0.10` | registration/mobility |
| webui | `172.22.0.26` | subscriber provisioning UI/CLI |
| nr-gnb | `172.22.0.23` | gNB (N2 + N3 endpoints) |
| nr-ue | `172.22.0.24` | UE container management address |

## 3. Interfaces and ports

| Interface | Endpoints | Transport | Purpose |
|---|---|---|---|
| Simulated radio | UE ↔ gNB | UERANSIM RLS, UDP `4997` | pretend air interface |
| N2 | nr-gnb → amf | NGAP over SCTP `38412` | registration/session signalling |
| N3 | nr-gnb ↔ upf | GTP-U over UDP `2152` | user data inside tunnels |
| N4 | smf ↔ upf | PFCP over UDP `8805` | "open the path for this UE" |
| SBI | NF ↔ NF | HTTP/2 `7777` | control-plane service mesh |
| N6 | upf ↔ apps | IPv4 (no NAT, intended) | user data, envelope removed |
| Management (webui) | host → webui | TCP `9999` | subscriber provisioning |
| Metrics/Grafana | host | TCP `9090` / `3000` | later observability |

## 4. Data Network (N6) and UE session

| Node | Address | Notes |
|---|---|---|
| upf (dn interface) | `10.20.6.2` | second interface, `dn` network |
| nginx | `10.20.6.20` | HTTP `80/tcp` |
| iperf3 | `10.20.6.21` | `5201/tcp+udp` |
| UE `uesimtun0` | `10.45.0.x` | assigned by the SMF at PDU session setup |

**Return path (no NAT):** application containers need a route
`10.45.0.0/16 via 10.20.6.2` (the UPF), so replies to the UE go back through the
UPF and into the tunnel. This is what makes the UE's real address visible on N6.

## 5. Subscriber

| Field | Value |
|---|---|
| IMSI | `001011234567895` |
| K | `8baf473f2f8fd09487cccbd7097c6862` |
| OP (SIM) | `11111111111111111111111111111111` |
| OPc (database) | `8E27B6AF0E692E750F32667A3B14605D` |
| AMF field | `8000` |
| APN | `internet` |
| Slice SST | `1` |

## 6. Notes

- **No NAT on N6 (intended).** The upstream UPF masquerades the `internet` APN;
  milestone 6 disables it so captures show `10.45.0.x` end to end.
- **Shared L2 for N2/N3/N4/SBI.** They live on `172.22.0.0/24`, as in the
  upstream base. They are still distinguishable by port (`38412`, `2152`,
  `8805`, `7777`); a future iteration may split them into separate networks for
  cleaner capture points.
- **`uesimtun0`** is the UERANSIM UE interface name; scripts and captures must
  use that exact name.
