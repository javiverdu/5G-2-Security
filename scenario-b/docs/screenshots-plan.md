# Scenario B — Screenshot Plan (visual evidence)

Screenshots for the Scenario B report (pages 3–6). Screenshots are
*illustrations*; the graded evidence stays as text/`.pcap` under
`results/scenario-b/` and `captures/scenario-b/`.

Save PNGs in `docs/img/` with the `sb-pageN-NN-description.png` convention and
fill the index at the end. See the Scenario A plan for general tips
([`../../docs/screenshots-plan.md`](../../docs/screenshots-plan.md)).

## 0. Prepare a running, clean topology

```bash
cd scenario-b
./scripts/fetch-upstream.sh
./scripts/deploy.sh
sudo ./scripts/enable-n6.sh        # N6 + nginx + iperf3, no NAT
./scripts/verify.sh                # expect 7/7 green
./scripts/grafana-import.sh        # datasource + dashboard into Grafana
```

> If the repository is on a VirtualBox shared folder, use `grafana-import.sh`
> (file provisioning is blocked by vboxfs permissions — see
> [`observability.md`](../docs/observability.md) §6).

---

## 1. Page 3 — deployment & end-to-end

| Shot | Prepare with | Must show |
|---|---|---|
| `sb-p3-01-containers` | `cd upstream && docker compose -f sa-deploy.yaml ps` | all NFs + gNB/UE `Up` |
| `sb-p3-02-verify` | `cd .. && ./scripts/verify.sh` | **7/7 green** |
| `sb-p3-03-upf-ifaces` | `docker exec upf ip -4 addr` | `ogstun 10.45.0.1/16`, `eth0 172.22.0.8`, N6 `eth1 10.20.6.2` |
| `sb-p3-04-ue-session` | `docker exec nr_ue ip -4 addr show uesimtun0` | `10.45.0.2/32` |
| `sb-p3-05-no-nat` | `docker logs --tail 5 sb-nginx` | access log with client **`10.45.0.2`** (no NAT) |

## 2. Page 4 — traffic observation (Wireshark)

Capture first (if not already): `sudo ./scripts/capture.sh icmp` etc.

| Shot | Open in Wireshark | Must show |
|---|---|---|
| `sb-p4-01-gtp-envelope` | `captures/scenario-b/icmp/P3-upf.pcap`, filter `gtp` | `udp:gtp:ip:icmp` — the packet inside the GTP-U envelope; compare with `P1-ue.pcap` (`ip:icmp`) and `P4-upf.pcap` (`ip:icmp`) |
| `sb-p4-02-follow-http` | `tcp-http/P1-ue.pcap` → *Follow → TCP Stream* | `GET / HTTP/1.0` + `200 OK` + body |
| `sb-p4-03-icmp-fields` | expand an ICMP packet in `icmp/P1-ue.pcap` | `ip.ttl=64`, `icmp.type 8`, `seq`, `ident` |
| `sb-p4-04-counts` | terminal `cat results/scenario-b/cross-point-counts.txt` | identical counts P1…P5 |
| `sb-p4-05-hierarchy` | `cat results/scenario-b/icmp-phs-P3-upf.txt` | `eth > ip > udp > gtp > ip > icmp` |

## 3. Page 5 — performance & degradation

| Shot | Prepare with | Must show |
|---|---|---|
| `sb-p5-01-tc-delay` | `sudo ./scripts/impair.sh delay` | `netem … delay 50ms 10ms` on `uesimtun0`/`eth0` |
| `sb-p5-02-tc-rate` | `sudo ./scripts/impair.sh rate` | `netem … rate 20Mbit` |
| `sb-p5-03-iperf` | baseline vs `delay`: `docker run --rm --network container:nr_ue networkstatic/iperf3 -c 10.20.6.21 -t 5` | throughput collapse |
| `sb-p5-04-table` | `cat results/scenario-b/comparison-table.md` | comparative numbers |
| `sb-p5-05-plot` | open `results/scenario-b/plots/comparison.png` | Fig. — 6 panels |
| `sb-p5-06-retrans` | `loss/retrans.pcap`, filter `tcp.analysis.retransmission` | highlighted retransmitted frames |

## 4. Page 6 — observability

| Shot | Open | Must show |
|---|---|---|
| `sb-p6-01-prometheus-targets` | <http://127.0.0.1:9090/targets> | `up` for amf/smf/pcf/upf |
| `sb-p6-02-dashboard` | <http://127.0.0.1:3000/dashboards> → `General` → `Open5GS` | the dashboard with the NF stat green |
| `sb-p6-03-during-traffic` | same dashboard while running `docker run --rm --network container:nr_ue networkstatic/iperf3 -c 10.20.6.21 -t 10` | panels change vs baseline |

## 5. Wireshark tips

* Columns: right-click → *Apply as Column* for `ip.ttl`, `gtp.teid`,
  `tcp.flags.str`, `icmp.seq`.
* The key figure is the **same frame at P1 vs P3 vs P4** (`frame.protocols`).
* If AppArmor blocks reading a capture from the repo, copy it to `/tmp` first.

## 6. Index

| # | File | Requirement | Done |
|---|---|---|---|
| 1 | `sb-p3-01-containers.png` | components/services | ☐ |
| 2 | `sb-p3-02-verify.png` | end-to-end operational | ☐ |
| 3 | `sb-p3-03-upf-ifaces.png` | interfaces & addressing | ☐ |
| 4 | `sb-p3-04-ue-session.png` | UE PDU session | ☐ |
| 5 | `sb-p3-05-no-nat.png` | UE address preserved on N6 | ☐ |
| 6 | `sb-p4-01-gtp-envelope.png` | N3 encapsulation | ☐ |
| 7 | `sb-p4-02-follow-http.png` | HTTP request/response | ☐ |
| 8 | `sb-p4-03-icmp-fields.png` | ICMP fields/TTL | ☐ |
| 9 | `sb-p4-04-counts.png` | generated/forwarded/delivered | ☐ |
| 10 | `sb-p5-01-tc-delay.png` | impairment configuration | ☐ |
| 11 | `sb-p5-05-plot.png` | comparative plot | ☐ |
| 12 | `sb-p5-06-retrans.png` | TCP retransmissions | ☐ |
| 13 | `sb-p6-01-prometheus-targets.png` | scrape health | ☐ |
| 14 | `sb-p6-02-dashboard.png` | Grafana Open5GS | ☐ |
| 15 | `sb-p6-03-during-traffic.png` | metrics track the path | ☐ |
