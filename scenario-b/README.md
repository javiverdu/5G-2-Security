# Inherited 5G SA base (`scenario-b/`)

This subtree is the **5G Standalone transport** inherited from Project 1 and
reused by Project 2. It is not a second network and it is not a Project 1
deliverable anymore: only the code, Compose files and operational scripts are
kept. Project 1 reports and screenshots were removed from the working tree.

Read [`../AGENTS.md`](../AGENTS.md) first. The base invariants and known traps
are in [`AGENTS.md`](AGENTS.md).

## What runs here

```text
UE (UERANSIM) -> gNB (UERANSIM) -> UPF -> N6 (dn-net) -> application
                    |                |
                    N2/N3            N4
                    |                |
                  AMF/SMF -------- Open5GS core
```

| Item | Value |
|---|---|
| Core network | `172.22.0.0/24`, shared L2 for N2/N3/N4/SBI |
| UE PDU pool | `10.45.0.0/16`, gateway `10.45.0.1` |
| N6 / data network | `dn-net` `10.20.6.0/24`; UPF `.2`, app gateway `.20` |
| Subscriber | IMSI `001011234567895`, APN `internet` |
| Upstream | `herlesupreeth/docker_open5gs`, pinned commit `1f3bcf7` |

## Run the base

```bash
cd ~/5G-2-Security/scenario-b

# First time on a fresh clone only
cp env.example .env
./scripts/fetch-upstream.sh

# Every boot
./scripts/deploy.sh
sudo ./scripts/enable-n6.sh
```

`deploy.sh` starts the core, provisions the subscriber, then starts the gNB and
the UE. `enable-n6.sh` creates `dn-net`, starts the N6 test endpoint
(`sb-nginx`) and the iperf3 server, and removes the UPF masquerade.

Project 2 replaces the RAN image and the N6 endpoint afterwards:

```bash
cd ~/5G-2-Security
./project2/scenario-a/scripts/upgrade-ran.sh   # UERANSIM v3.3.0 + narrow UE route
./project2/scenario-a/scripts/up.sh            # Django + TLS gateway; removes sb-nginx
```

Do **not** run `enable-n6.sh` after `project2/scenario-a/scripts/up.sh`: it would
recreate `sb-nginx`, which conflicts with `scenario-b-nginx` on `10.20.6.20`.

## Verify the base alone

```bash
cd ~/5G-2-Security/scenario-b
./scripts/verify.sh                 # 7/7 after enable-n6.sh
docker exec nr_ue ip -4 addr show uesimtun0
docker exec nr_ue ping -c 2 10.20.6.20
```

The Project 2 acceptance gate is
[`../project2/scenario-a/scripts/verify-phase1.sh`](../project2/scenario-a/scripts/verify-phase1.sh);
it proves the whole path from the UE, not just container state.

## Notes

- Observability (`metrics`, `grafana`) is **disabled by default** in this fork:
  the 32 GB VM cannot hold the Project 2 image set plus that stack. Set
  `ENABLE_OBSERVABILITY=1` only if the images are available and disk allows.
- `dn-net` was called `scenario-b-dn` in Project 1; the subnet is unchanged.
- `.env` and `upstream/` are git-ignored. `env.example` is the tracked template.
- Raw packet captures are git-ignored; keep them out of Git.
