# AGENTS.md — scenario-b/ (inherited 5G SA base)

This subtree is the **Project 1 5G Standalone deployment**, reused verbatim as
the transport for Project 2. It works; treat it as **production-like
infrastructure**, not as scratch space.

Read the root [`../AGENTS.md`](../AGENTS.md) first.

## Invariants

| Item | Value |
|---|---|
| Core network | `172.22.0.0/24` (N2, N3, N4, SBI share L2, distinguished by port) |
| UE PDU pool | `10.45.0.0/16`, gateway `10.45.0.1` |
| Data network | `dn-net` `10.20.6.0/24`; upf `.2`, nginx `.20`, iperf3 `.21` |
| Upstream | `herlesupreeth/docker_open5gs`, pinned commit `1f3bcf7` |
| Images | prebuilt GHCR (`docker_open5gs`, `docker_ueransim`, `docker_metrics`) — **no local build** |
| Subscriber | IMSI `001011234567895`, K `8baf473f2f8fd09487cccbd7097c6862`, OPc `8E27B6AF0E692E750F32667A3B14605D`, APN `internet` |
| UE interface | `uesimtun0` (exact name; scripts depend on it) |

- **No NAT on N6** (intentional): the UE address `10.45.0.x` must be visible at
  the application. Never re-enable UPF masquerade.
- Ports identify planes: N2 `38412/sctp`, N3 `2152/udp`, N4 `8805/udp`, SBI `7777/tcp`.
- The upstream clone lives in `upstream/` and is **git-ignored**. Reproduce it
  with `scripts/fetch-upstream.sh`; never edit it by hand.

## Run order

```bash
./scripts/fetch-upstream.sh
./scripts/deploy.sh
./scripts/verify.sh              # 1-5 green
sudo ./scripts/enable-n6.sh
./scripts/verify.sh              # 1-7 green
```

Captures: `sudo ./scripts/capture.sh <icmp|tcp-http|tcp-iperf|udp-iperf>`,
`sudo ./scripts/capture-control.sh` (N2/N4 during registration),
`sudo ./scripts/analyze.sh` → `results/scenario-b/`.

## Operational gotchas (already solved — do not regress)

1. **Interface names are unstable.** `eth0`/`eth1` can swap between runs. Detect
   an interface **by its address** (`172.22.0.x` core, `10.20.6.x` dn), never by
   name. `capture.sh` and `capture-control.sh` already do this.
2. **The UE route is installed by the host in Project 1.** UERANSIM creates
   `uesimtun0` but no route, so traffic silently leaves via `eth0`. Project 1
   fixes it from `deploy.sh`; Project 2 moves the responsibility into the UE
   image (`p2/`). Keep both consistent while both exist.
3. **N6 needs return paths.** App containers need `10.45.0.0/16 via 10.20.6.2`;
   the iperf3 image has no `ip`, so `enable-n6.sh` uses `nsenter` from the host.
4. **vboxsf breaks containers.** On the VirtualBox shared folder, Grafana cannot
   read mounted provisioning (uid 472). Use `scripts/grafana-import.sh` (API)
   when running from the share, or run from a native VM path.
5. **Grafana/Prometheus.** Grafana `:3000` (`open5gs`/`open5gs`), datasource
   `Open5Gs` (uid `PA240B69645956401`); Prometheus `:9090`. The 4G jobs `mme`,
   `pcrf`, `hss` stay **DOWN by design** — they are 4G-only and not applicable
   to 5G SA. Do not "fix" them.
6. **Captures are root-owned.** `analyze.sh` needs `sudo`; `.pcap`/`.pcapng` are
   git-ignored and delivered separately.

## Expected capture counts (regression signal)

At all five points: **10 ICMP, 13 HTTP, 3178 TCP-iperf, 497 UDP-iperf** frames.
GTP-U proof: P1 `raw:ip:icmp:data`; P2/P3 `eth:ip:udp:gtp:ip:icmp:data`;
P4/P5 `eth:ip:icmp:data`. Counts that differ mean the topology or NAT changed.

## Where Project 2 work goes

**Do not modify this base to implement Scenario A.** Add Project 2 files under
`project2/scenario-a/` (own `AGENTS.md`) and reference the base by the names
above. The only intentional base changes are the ones the brief requires: the UE
image, the `scenario-b-nginx` replacement, the `dn` network being named
`dn-net`, and the added Docker networks.

Once phase 1C is up, the Project 1 N6 test container `sb-nginx` is superseded by
`scenario-b-nginx`; both use `10.20.6.20` and must never run together.
`project2/scenario-a/scripts/up.sh` removes `sb-nginx` before starting the
gateway. Do not re-run `scripts/enable-n6.sh` afterwards — it would try to
create `sb-nginx` again.
