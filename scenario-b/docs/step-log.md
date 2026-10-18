# Scenario B — Deployment log & troubleshooting

This is the reproducible runbook for the Scenario B deployment plus the record of
every obstacle found and how it was fixed. It exists so the same problems are not
re-diagnosed later (page 4–6) and so the report can explain the *diagnose* step.

## 1. Workflow (order matters)

```bash
cd scenario-b
./scripts/fetch-upstream.sh     # clone pinned upstream + pull/tag images + .env + patch UPF NAT
./scripts/deploy.sh             # core -> gNB -> wait N2 -> UE -> wait PDU -> route
./scripts/verify.sh             # checks 1-5 green; 6-7 SKIP (N6 not wired yet)
sudo ./scripts/enable-n6.sh     # N6 network + nginx + iperf3, no NAT, return routes
./scripts/verify.sh             # checks 1-7 green
sudo ./scripts/capture.sh icmp    # page 4 captures
sudo ./scripts/capture.sh tcp-http
sudo ./scripts/capture.sh tcp-iperf
sudo ./scripts/capture.sh udp-iperf
sudo ./scripts/analyze.sh       # page 4 dissections -> results/scenario-b/
```

## 2. Why N6 "was not working"

N6 is **not** part of the upstream core: Open5GS alone gives the UE a working PDU
session (checks 1–5) but there is no Data Network and no application. Three
different problems were mistaken for "N6 is down":

1. **N6 was never wired.** The base deployment has no `10.20.6.0/24` network, no
   `10.20.6.2` on the UPF and no application. Until `enable-n6.sh` runs, a packet
   the UE sends to `10.20.6.20` enters the GTP-U tunnel, reaches the UPF, has no
   route and is silently dropped — so any `curl` just hangs. `enable-n6.sh` adds
   the `dn` network, the UPF's second interface, `sb-nginx`/`sb-iperf3`, removes
   the UPF masquerade (no NAT) and installs the return routes.

2. **The HTTP check itself was broken.** The UERANSIM UE image has **no `curl`**,
   so `docker exec nr_ue curl ...` failed. It was replaced by a `GET` over bash
   `/dev/tcp` — but that early version had **no timeout**, so when N6 was not
   wired the TCP connect blocked forever. That looked exactly like "N6 hangs".
   Fixed with `timeout` inside and outside the exec.

3. **The verify result was flaky, not the network.** Several checks used
   `command | grep -q ...`. `grep -q` exits on the first match, `command` gets
   SIGPIPE and, with `set -o pipefail`, the whole pipeline returns failure even
   though the text matched. This made checks 2 and 3 *flip* between runs
   (registration FAIL / PDU OK, then the reverse). Fixed by capturing the output
   first and grepping the captured text (`grep -q ... <<<"$(...)"`).

Net effect: N6 was fine once wired; the failures were a missing network, a missing
HTTP client + missing timeout, and a shell pitfall.

## 3. Other obstacles found and fixed

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | `uesimtun0` had `10.45.0.x` but `ping 10.45.0.1` failed | UERANSIM creates the TUN but does not install the session route; traffic left via `eth0` | `deploy.sh` waits for the session and runs `ip route replace default dev uesimtun0` |
| 2 | `enable-n6.sh` failed: container name `/nginx-app` already in use | Scenario A's `nginx-app` still exists on the same VM | renamed Scenario B containers to `sb-nginx` / `sb-iperf3` |
| 3 | `docker exec nr_ue curl` → "curl: executable file not found" | UERANSIM image has no HTTP client | use bash `/dev/tcp` for HTTP; run iperf3 via `docker run --network container:nr_ue` |
| 4 | iperf3 return route could not be added in-container | `networkstatic/iperf3` image has no `ip` binary | add the route from the host with `nsenter -t <pid> -n ip route add` |
| 5 | `capture.sh tcp-iperf` / `udp-iperf` gave P5 = 1 / 0 frames | P5 always captured on `sb-nginx`, but iperf3 talks to `sb-iperf3` | P5 target chosen per label (nginx for ping/HTTP, iperf3 for throughput) |
| 6 | `verify.sh` step 7 hung when N6 was down | iperf3 connect blocked (packets dropped in the tunnel, no RST) | gate on container `running` + ICMP reachability, plus `timeout` and `--connect-timeout` |
| 7 | `MongoServerError E11000 duplicate key` during deploy | subscriber already exists; `deploy.sh` re-adds it | harmless; kept as a WARN (idempotent) |
| 8 | `analyze.sh` produced empty files ("You don't have permission to read the file …") | captures are root-owned and Ubuntu's AppArmor `tshark` profile only allows reading `user-tmp` | run `analyze.sh` with **sudo**; it runs `tshark` unconfined via `aa-exec -p unconfined` |
| 9 | `plot.py` said "missing summary.csv" right after `run-all.sh` | `run-all`/`measure` wrote to `scenario-b/results/`, while `plot`/`analyze` read `results/` at the repo root | all scripts now write/read the repo-root `results/scenario-b/` |
| 10 | TCP retransmissions counted as 0 although iperf3 reported 75–175 | `aa-exec … sh -c "tshark …"` re-applies the `tshark` AppArmor profile on the `sh`→`tshark` exec (unlike calling `tshark` directly) | call `tshark` directly through `aa-exec`; `recount-retrans.sh` recomputes from existing pcaps |
| 11 | Grafana shows no datasource and no dashboard; log says `open /etc/grafana/provisioning/dashboards: permission denied` | the repo lives on a VirtualBox shared folder (vboxsf) and Grafana runs as uid 472, which cannot read the bind-mounted provisioning files | import via the Grafana API (`grafana-import.sh`); it stores the datasource + dashboard in Grafana's DB, independent of the shared folder |

## 4. Verified state (page 3)

`verify.sh` checks, all green after `enable-n6.sh`:

1. containers up
2. N2 — gNB NG Setup with the AMF
3. registration + PDU session (UE logs)
4. user plane — `uesimtun0` = `10.45.0.2/32`
5. user-plane route + tunnel gateway (`ping 10.45.0.1`)
6. application over N6 — HTTP 200 and nginx logs the **UE source `10.45.0.2`** (no NAT)
7. throughput endpoint — iperf3 UE → `10.20.6.21`

## 5. Useful one-liners

```bash
# real log strings used by the checks
docker logs nr_gnb 2>&1 | grep -iE 'ng[ -]?setup'
docker logs nr_ue  2>&1 | grep -iE 'registration|pdu session'

# prove no-NAT on N6
docker logs --tail 5 sb-nginx        # expect a 10.45.0.x client

# UPF interfaces (ogstun = UE pool, eth1 = N6)
docker exec upf ip -4 addr
```
