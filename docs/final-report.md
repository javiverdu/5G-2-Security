# Final Report — Skeleton & Evidence Index

**Project 1 — Scenario A: Software-Based Telecommunications Network**

This is the working skeleton of the final report. Each section below states what to
write and links the exact evidence to draw from; the step reports are the detailed
sources, so their content is not repeated here.

## 1. Requirement coverage

| Assignment requirement | Where it is covered |
|---|---|
| Topology diagram (with IPs) | [README §Architecture](../README.md#architecture) |
| Namespace list, interfaces, IP addressing | [addressing-plan.md](addressing-plan.md); raw: `results/step1/01-…` |
| Routing tables per node | [addressing-plan.md](addressing-plan.md); raw: `results/step1/02-…` |
| Docker network & container/service info | `docs/step1-network-deployment.md` §2; raw: `results/step1/03-…` |
| Service status & listening ports | `docs/step1-network-deployment.md` §2; raw: `results/step1/04-…` |
| Successful `curl`/application test | `docs/step1-network-deployment.md` §3; raw: `results/step1/06-…` |
| End-to-end path explanation | `docs/step1-network-deployment.md` §4 |
| ICMP/TCP/UDP/application analysis | [step2-traffic-observation.md](step2-traffic-observation.md); raw: `results/step2/` |
| Multi-point captures | [step2-traffic-observation.md](step2-traffic-observation.md) §1–2; pcaps: `captures/step2/` |
| Baseline + ≥2 degraded conditions | [step3-performance-measurement.md](step3-performance-measurement.md); raw: `results/step3/` |
| Comparative table + plot | `results/step3/comparison-table.md`, `results/step3/plots/comparison.png` |
| Interpretation linking conditions to behaviour | [step3-performance-measurement.md](step3-performance-measurement.md) §7 |

## 2. Report sections

**0. Cover** — title, authors, course, date, environment (single Ubuntu VM, Docker 29.8.1).

**1. Introduction** — objectives; the Deploy → Verify → Observe → Measure → Diagnose →
Explain workflow; scope (simplified Scenario A, not a full 4G/5G core; routed, not NATed).

**2. Architecture and topology** — logical chain
`UE → Access → Core/Gateway → Data Network → Application Server`; hybrid Linux + Docker
design. Include **Fig. 1** (topology, README) and the addressing/routing tables
([addressing-plan.md](addressing-plan.md)).

**3. Step 1 — Deployment and end-to-end operation** — deployment procedure, as-built
state, verification results, path analysis with TTL evidence, and the Docker 29
forwarding diagnosis. Source: [step1-network-deployment.md](step1-network-deployment.md).

**4. Step 2 — Traffic observation** — six-point capture method, cross-point packet
counts, and ICMP / TCP / UDP / HTTP dissections. Source:
[step2-traffic-observation.md](step2-traffic-observation.md).

**5. Step 3 — Performance and degradation** — conditions, comparative results
(**Tab. 4**), plot (**Fig. 2**) and interpretation. Source:
[step3-performance-measurement.md](step3-performance-measurement.md).

**6. Diagnosis** — the two obstacles found and explained with evidence (this is the
*Diagnose* dimension of the workflow):
- Docker ≥ 28/29 hardened forwarding dropped routed traffic to container IPs;
  root cause proved by wrapping `nft`/`iptables` (caller was `dockerd`); fixed with
  `allow-direct-routing` + a `DOCKER-USER` accept rule
  ([step1 §5](step1-network-deployment.md)).
- AppArmor's `tshark` profile blocked reading captures outside `user-tmp`; worked
  around with `aa-exec -p unconfined`
  ([step2 §7](step2-traffic-observation.md)).

**7. Conclusions** — complete path established and verified (every generated packet
traverses it); protocol behaviour quantified under baseline and three degraded
conditions; the method localises where packets are generated, forwarded, delayed or dropped.

**8. Reproducibility** — commands in [README §Quickstart](../README.md#quickstart).

**9. Appendix** — evidence index (below) and the raw files under `results/`.

## 3. Figures and tables

| ID | Item | Source |
|---|---|---|
| Fig. 1 | Topology diagram (Mermaid, with IPs) | [README §Architecture](../README.md#architecture) |
| Fig. 2 | Step 3 comparative plots | `results/step3/plots/comparison.png` |
| Tab. 1 | Subnet relationships | [addressing-plan.md](addressing-plan.md) |
| Tab. 2 | Interface / IP addressing | [addressing-plan.md](addressing-plan.md) |
| Tab. 3 | Step 2 cross-point packet counts | `results/step2/cross-point-packet-counts.txt` |
| Tab. 4 | Step 3 comparative results | `results/step3/comparison-table.md` |
| Tab. 5 | Condition → protocol-behaviour mapping | [step3 §7](step3-performance-measurement.md) |

## 4. Evidence index

```
docs/   addressing-plan, step1, step2, step3, final-report (this)
scripts/ deploy/ (setup, verify) · observe/ (capture, analyze)
         measure/ (impair, measure, run-all, plot) · teardown/ (cleanup)
results/ step1/ · step2/ · step3/   (raw outputs, dissections, tables, plots)
captures/ (git-ignored)             raw .pcap files for Steps 2–3
```

**References:** the project brief PDF; `iproute2`/`ip netns`, Docker Engine, Nginx,
iperf3, tcpdump/tshark, Linux `tc` + NetEm.
