# Phase 1A — evidence

Acceptance run for the persistent user-plane route
(`10.20.6.0/24 dev uesimtun0`, installed by the UE image and preserved across
`docker restart nr_ue`).

- Date: 2026-11-02
- VM: Ubuntu 25.04, 10 GB RAM, 32 GB disk, `~/5G-2-Security` (native disk)
- Base: Project 1 deployment from `scenario-b/scripts/deploy.sh`
- Image: `telecom-lab-ueransim:3.3.0-p2` (UERANSIM v3.3.0 built from source)

## Commands

```bash
cd ~/5G-2-Security/scenario-b
./scripts/deploy.sh

# N6 (equivalent to enable-n6.sh; see the note below)
cd upstream
docker compose -f sa-deploy.yaml -f ../n6/docker-compose.n6.yaml up -d --no-build
docker exec upf iptables -t nat -F POSTROUTING

cd ~/5G-2-Security
./project2/scenario-a/scripts/build.sh
./project2/scenario-a/scripts/upgrade-ran.sh
./project2/scenario-a/scripts/verify-phase1a.sh
```

## Result

`verify-phase1a.txt` is the unedited output of the acceptance script:

- image reports `UERANSIM v3.3.0`;
- `nr_gnb` and `nr_ue` both run `telecom-lab-ueransim:3.3.0-p2`;
- `uesimtun0 = 10.45.0.4/16` after registration;
- `ip route get 10.20.6.20` resolves via `uesimtun0`;
- the same check passes **after `docker restart nr_ue`**, with no host-side
  route command in between;
- the UE reaches `10.20.6.20` over the PDU session.

## Note on N6

`scenario-b/scripts/enable-n6.sh` requires root for one step: it enters the
iperf3 container with `nsenter` to add its return route (the image has no `ip`).
The VM has no passwordless sudo, so that command was replaced by an equivalent
one-shot container with `NET_ADMIN` sharing the iperf3 network namespace:

```bash
docker run --rm --network container:sb-iperf3 --cap-add NET_ADMIN \
    --entrypoint ip telecom-lab-ueransim:3.3.0-p2 \
    route replace 10.45.0.0/16 via 10.20.6.2
```

Everything else in the N6 bring-up is byte-for-byte the inherited runbook. The
`10.20.6.20` endpoint used here is the Project 1 `nginx:alpine` test container;
Scenario A replaces it with `scenario-b-nginx` in phase 1C. It only answers the
reachability check in this phase.
