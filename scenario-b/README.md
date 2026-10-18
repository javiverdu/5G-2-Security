# Scenario B — 5G Standalone end-to-end path

This is the **planning for page 3** of the brief: build the reference 5G
architecture on a single Ubuntu VM with Docker Compose, and leave the complete
UE → gNB → UPF → N6 → application path operational.

It is a *plan + scaffold*, not the finished deployment. The deployment runs on
the Ubuntu lab VM, not on the development machine.

> Read this first if 5G names are unfamiliar: the whole thing is the same idea
> as Scenario A, only the boxes get their real 5G names.

---

## 1. The idea in plain words

Scenario A was a row of rooms:

```text
laptop (ue) → access router → core router → data network → nginx
```

Scenario B is the same row, with 5G names:

```text
phone (UE) → antenna (gNB) → core forwarder (UPF) → internet (N6) → nginx
```

Nothing is a real radio or a real operator. Everything is a container on one VM:

| Role in the diagram | What actually runs | Why it exists |
|---|---|---|
| UE | **UERANSIM** (`nr-ue`) | Pretends to be the phone. Gets a real IP on `uesimtun0`. |
| gNB | **UERANSIM** (`nr-gnb`) | Pretends to be the antenna. Talks to the core for the phone. |
| AMF | Open5GS | Receptionist: takes the phone's registration |
| AUSF, UDM, UDR | Open5GS | Check the subscriber exists (UDR uses MongoDB as disk) |
| NRF | Open5GS | Phone book: "where is the AMF?" |
| SMF | Open5GS | Creates the data session and tells the UPF to open the path |
| UPF | Open5GS | The **only** box that forwards user data |
| PCF, BSF, NSSF, SCP | Open5GS | Support functions; needed by the session setup |
| WebUI | Open5GS | GUI/CLI to create the subscriber |
| Application | `nginx:latest` | HTTP server on N6 |
| Measurement | `networkstatic/iperf3` | Throughput endpoint on N6 |

## 2. Two paths, not one

* **Signalling (control plane):** the paperwork. "I want to register", "you are
  who you say", "here is your IP". No web page travels here.
  gNB --N2--> AMF, and AMF/SMF <--SBI--> the other control functions,
  SMF --N4--> UPF.
* **User data (user plane):** the real packet (ping, curl, iperf3).
  UE --(simulated radio)--> gNB --N3/GTP-U--> UPF --N6--> nginx.

**If the paperwork does not complete, the data path does not exist.** A running
container proves nothing; `docker ps` only says the program is on.

## 3. Interfaces

| Link | Between | Addresses | What travels |
|---|---|---|---|
| Radio (simulated) | UE ↔ gNB | inside the UE/gNB containers | UERANSIM RLS (UDP 4997) |
| **N2** | gNB ↔ AMF | `172.22.0.23` ↔ `172.22.0.10` | NGAP over SCTP `38412` |
| **N3** | gNB ↔ UPF | `172.22.0.23` ↔ `172.22.0.8` | GTP-U over UDP `2152` |
| **N4** | SMF ↔ UPF | `172.22.0.7` ↔ `172.22.0.8` | PFCP over UDP `8805` |
| SBI | control functions | `172.22.0.x` | HTTP/2 `7777` |
| **N6** | UPF ↔ Data Network | `10.20.6.2` ↔ `.20`/`.21` | plain IPv4 |
| UE session | UE ↔ UPF (tunnel) | `10.45.0.x` ↔ `10.45.0.1` | user data inside the tunnel |

The N3 "envelope": on N3 the HTTP packet does not travel naked; it is inside a
GTP-U packet. On N6 the UPF removes the envelope and nginx sees a normal IP.
That is why the same request looks different in N3 and N6 — that is the design,
not a fault.

## 4. Addressing plan (final — do not change later)

| Segment | Subnet | Nodes |
|---|---|---|
| UE PDU pool | `10.45.0.0/16` | UE `uesimtun0` `10.45.0.x`, gateway `10.45.0.1` |
| N6 / Data Network | `10.20.6.0/24` | UPF `.2`, nginx `.20`, iperf3 `.21` |
| 5G core network | `172.22.0.0/24` | all Open5GS NFs + gNB (see `docs/addressing-plan.md`) |

Subscriber parameters (must match **exactly** in UE, gNB and the database):

| Parameter | Value |
|---|---|
| MCC / MNC | `001` / `01` |
| TAC | `1` |
| IMSI | `001011234567895` |
| K | `8baf473f2f8fd09487cccbd7097c6862` |
| OP (type OP) | `11111111111111111111111111111111` |
| OPc (stored in DB) | `8E27B6AF0E692E750F32667A3B14605D` |
| APN | `internet` |

> The most common failure is K/OP/OPc not matching between the UE and the
> database. `OP` is what the SIM holds; `OPc` is derived from K+OP and is what
> Open5GS stores. Mixing them is the usual cause of registration failure.

## 5. Base implementation

We do not write an Open5GS stack from scratch. The scaffold pins a maintained
public Compose and layers our parameters on top:

* Upstream: [`herlesupreeth/docker_open5gs`](https://github.com/herlesupreeth/docker_open5gs),
  pinned to a commit by `scripts/fetch-upstream.sh`.
* Images are pulled prebuilt from GHCR (`docker_open5gs`, `docker_ueransim`,
  `docker_metrics`) — **no local build required**.
* Our `.env` overrides the upstream parameters (PLMN, IMSI, UE pool).
* The upstream clone lives in `scenario-b/upstream/` and is **git-ignored**.

## 6. Milestones and exit criteria

| # | Milestone | Exits when |
|---|---|---|
| 1 | Docker Compose on the VM | `docker compose version` works |
| 2 | Images + config retrieved | `scripts/fetch-upstream.sh` finishes |
| 3 | Core up | `docker compose -f sa-deploy.yaml ps` shows NFs `Up`, NRF lists them |
| 4 | Registration | gNB logs `NG Setup procedure is successful`; UE logs registration accept |
| 5 | PDU session | `uesimtun0` has a `10.45.0.x` address |
| 6 | App through the 5G path | from the UE, `curl http://10.20.6.20/` → `200 OK` |
| 7 | Document | diagram, function table, interface table, IPs, `docker network inspect`, listening ports, the three test commands |

**First test to look at:** milestone 4/5, *from the UE container*:

```bash
docker exec nr_ue ip -4 -brief addr show uesimtun0   # expect 10.45.0.x
docker exec nr_ue ping -c 3 10.45.0.1                # expect replies
```

If `uesimtun0` has an address and the ping works, the 5G data path exists. Then
and only then does the application test make sense.

> A `ping` between two containers on the Data Network does **not** count: they
> are already in the same room. The brief says so explicitly.

## 7. Run order (on the Ubuntu VM)

```bash
cd scenario-b
./scripts/fetch-upstream.sh      # clone pinned upstream + pull/tag images + apply .env
./scripts/deploy.sh              # core, then gNB, wait N2, UE, wait PDU, install route
./scripts/verify.sh              # checks 1-5 green; 6-7 SKIP (N6 not wired yet)
sudo ./scripts/enable-n6.sh      # milestone 6: N6 + nginx + iperf3, no NAT (needs sudo)
./scripts/verify.sh              # checks 1-7 green
sudo ./scripts/capture.sh icmp   # page 4: multi-point captures
sudo ./scripts/capture.sh tcp-http
sudo ./scripts/capture.sh tcp-iperf
sudo ./scripts/capture.sh udp-iperf
sudo ./scripts/analyze.sh        # page 4: dissections -> results/scenario-b/
sudo ./scripts/run-all.sh        # page 5: baseline + delay + loss + rate
python3 ./scripts/plot.py        # page 5: comparative table + plot
./scripts/cleanup.sh             # tear everything down
```

Every obstacle hit while getting this working, and the fix for each, is recorded
in [`docs/step-log.md`](docs/step-log.md) — including the three distinct reasons
N6 appeared to be broken.

## 8. Milestone 6 (N6 + application) — implemented

The upstream core NATs the UE traffic out of the UPF, which hides the UE IP on
N6. We want N6 **without NAT** so the UE address is visible. This is implemented
by:

* [`n6/docker-compose.n6.yaml`](n6/docker-compose.n6.yaml) — a Compose
  **override** that adds the `dn` network (`10.20.6.0/24`), attaches the UPF to
  it at `10.20.6.2`, runs `nginx:alpine` at `10.20.6.20` and
  `networkstatic/iperf3` at `10.20.6.21`, and gives nginx a return route
  `10.45.0.0/16 via 10.20.6.2`.
* [`scripts/enable-n6.sh`](scripts/enable-n6.sh) — brings the override up,
  **flushes the UPF masquerade** (`iptables -t nat -F POSTROUTING` inside the
  UPF, the only NAT rule there), and adds the iperf3 return route from the host
  with `nsenter` (the iperf3 image has no `ip`). Needs `sudo`.
* `fetch-upstream.sh` also patches `upf_init.sh` so a fresh deploy never adds
  that masquerade in the first place.

With no NAT, `sb-nginx` logs the real UE address `10.45.0.x`; `verify.sh`
check 6 asserts both the HTTP 200 and that the source address is the UE.

The iperf3 **client** runs in the UE's network namespace, because the UERANSIM
image has no iperf3:

```bash
docker run --rm --network container:nr_ue networkstatic/iperf3:latest -c 10.20.6.21 -t 5
```

`verify.sh` check 7 runs exactly that and reports the receiver throughput.

The alternative to the container return route (if an image lacks `ip`) is a host
route `10.45.0.0/16 via 10.20.6.2`, but that pulls the host into the forwarding
path (and Docker's `FORWARD` policy), so the in-container route is preferred.

## 9. Risks to decide before writing the Compose override

| Risk | Why it matters |
|---|---|
| Subscriber mismatch (K/OP/OPc, IMSI, PLMN) | Registration never leaves Authentication |
| UPF NAT | Hides the UE IP on N6 |
| RAM | Full Open5GS + UERANSIM + Prometheus/Grafana wants ~8 GB |
| Kernel modules | The UPF TUN needs `NET_ADMIN`; some hosts need `tun`/`gtp` |
| `uesimtun0` name | Test scripts must use the real UERANSIM interface name |

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `uesimtun0` has a `10.45.x` address but `ping 10.45.0.1` fails | UERANSIM creates the TUN but does not install the session route, so user traffic leaves via `eth0` | `docker exec nr_ue ip route replace default dev uesimtun0` (already done by `deploy.sh`) |
| Registration stuck in Authentication | K / OP / OPc or PLMN mismatch between UE, gNB and database | make the three match (see §4) |
| No NG Setup in `nr_gnb` logs | N2 (SCTP `38412`) not reaching the AMF | check `nr_gnb` / `amf` logs and the core network |
| `upf` has no `ogstun` address | TUN creation failed (permissions/module) | check `upf` logs and the `NET_ADMIN`/privileged flags |

## 11. Page coverage

| Page | Topic | Where |
|---|---|---|
| 3 | deployment & end-to-end | §6, [`final-report.md`](docs/final-report.md) §4 |
| 4 | traffic observation | §12, [`traffic-observation.md`](docs/traffic-observation.md) |
| 5 | performance & degradation | §13, [`performance-measurement.md`](docs/performance-measurement.md) |
| 6 | observability | §15, [`observability.md`](docs/observability.md) |

Not covered (optional depth beyond the brief): message-level dissection of
NGAP/PFCP/SBI and a step-by-step registration trace.

## 12. Page 4 — capture points (started)

The multi-point capture is implemented in
[`scripts/capture.sh`](scripts/capture.sh) (tcpdump from the host inside each
container's netns, via `nsenter`) and the dissection in
[`scripts/analyze.sh`](scripts/analyze.sh) (tshark). Points: P1 UE, P2 gNB (N3),
P3 UPF (N3), P4 UPF (N6), P5 application (nginx or iperf3). Documented in
[`docs/capture-points.md`](docs/capture-points.md); run log in
[`docs/step-log.md`](docs/step-log.md).

```bash
cd scenario-b
sudo ./scripts/capture.sh icmp
sudo ./scripts/capture.sh tcp-http
sudo ./scripts/capture.sh tcp-iperf
sudo ./scripts/capture.sh udp-iperf
sudo ./scripts/analyze.sh     # -> results/scenario-b/  (needs sudo: root-owned pcaps + AppArmor)
```

The key lesson for the report: at P2/P3 the user packet is inside the **GTP-U
envelope** (`UDP 2152`); at P4/P5 the envelope is gone and the plain
`10.45.0.2 ↔ 10.20.6.20` IP flow appears — with the same addresses throughout
(no NAT). Full write-up: [`docs/traffic-observation.md`](docs/traffic-observation.md).

## 13. Page 5 — performance & degradation

Impairments use `tc` + NetEm on the **user-plane endpoints only** (uplink on
`nr_ue:uesimtun0`, downlink on the app `eth0`), so N2/N4/SBI are untouched.
Metrics are taken from the UE: ICMP RTT/loss, HTTP response time, TCP
throughput, UDP throughput/loss/jitter and TCP retransmissions.

```bash
cd scenario-b
sudo ./scripts/impair.sh delay      # or loss / rate / baseline / show
sudo ./scripts/measure.sh delay
sudo ./scripts/run-all.sh           # baseline + delay + loss + rate -> summary.csv
python3 ./scripts/plot.py           # comparison-table.md + plots/comparison.png
sudo ./scripts/impair.sh baseline   # leave the path clean
```

Conditions: `delay 50ms ±10ms`, `loss 1%`, `rate 20mbit`. Full write-up and
interpretation: [`docs/performance-measurement.md`](docs/performance-measurement.md).

## 14. Consolidated report

Pages 3–5 are summarised in [`docs/final-report.md`](docs/final-report.md)
(architecture, interfaces, verification, packet observation, performance and the
diagnosis of every obstacle).

## 15. Page 6 — observability

Prometheus (`metrics`, :9090) and Grafana (`grafana`, :3000, `open5gs`/`open5gs`)
are part of the Compose. Check the stack and see the 5G path live:

```bash
cd scenario-b
./scripts/metrics-check.sh
./scripts/grafana-import.sh   # import datasource + dashboard via API
```

Details: [`docs/observability.md`](docs/observability.md). File-based provisioning
(`scenario-b/grafana/`) only works off a native path; on a VirtualBox shared
folder use the API import (`grafana-import.sh`).
