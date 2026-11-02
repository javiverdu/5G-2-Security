# 5G-2-Security

**Project 2 — Telecommunication Security, DevSecOps, and Traffic Intelligence**

This repository is a **fork of Project 1** (`5G-project-RTU`, full history kept)
used as the base: the **5G Standalone network** built in
[`scenario-b/`](scenario-b/README.md) (Open5GS + UERANSIM, `UE → gNB → UPF → N6`)
is reused as the transport for Project 2.

> **Workflow:** Secure the app path → test it → automate the testing → observe and correlate.

## Scenarios

* **Scenario A — secure application delivery over 5G.** Reuse the 5G SA path and
  add a **Django application** behind an **Nginx TLS reverse proxy**: a public
  Data Network (N6) and a **private application network**, lab PKI, HTTP→HTTPS
  redirection, and a security baseline (login, CSRF, secure cookies, HSTS).
* **Scenario B — DevSecOps security-testing pipeline.** Jenkins + Selenium +
  OWASP ZAP + Suricata + Trivy/Syft against a Juice Shop target, packet capture,
  event correlation and a security gate.

## Status

| Scenario | Phase | Description | Status |
|---|---|---|---|
| A | 1A | 5G SA base + **persistent UE route** (survives container restart) | ✅ done |
| A | 1B | Django + Gunicorn + SQLite on a private `app-net`, `/health/` | ✅ done |
| A | 1C | Lab PKI + Nginx TLS gateway (`80 → 301 → 443`) | ✅ done |
| A | 1D | Django security baseline (login, CSRF, cookies, HSTS, headers) | ✅ done |
| A | 1E | End-to-end acceptance from the UE through the 5G path | ⬜ |
| B | 2A–2E | Preflight, ZAP + Selenium, PCAP + Suricata, Trivy/Syft, correlation + gate | ⬜ planned |

## Structure

```
5G-2-Security/
├── AGENTS.md              # agent rules: design invariants that survive compaction
├── scenario-b/            # 5G SA core (inherited from Project 1)
│   └── AGENTS.md          # inherited-base invariants and gotchas
├── project2/
│   └── scenario-a/        # secure application delivery (phases 1A–1E)
│       └── AGENTS.md      # exact Scenario A contract from the brief
├── docs/                  # brief, reports and reference material
├── scripts/               # Project 1 Scenario A tooling (reference)
└── results/               # evidence
```

## Inherited base (Project 1)

The 5G SA deployment and its runbook are unchanged:

```bash
cd scenario-b
./scripts/fetch-upstream.sh     # pin the upstream + images + params
./scripts/deploy.sh             # core -> gNB -> UE -> subscriber -> route
./scripts/verify.sh             # 7/7 checks
sudo ./scripts/enable-n6.sh     # N6 + apps, no NAT
```

Project 2 work happens in [`project2/scenario-a/`](project2/scenario-a/README.md).

## Working specification (from the brief — confirm before wiring)

These are the values used while scaffolding; if your copy of the brief differs,
they are collected in one place to change:

| Item | Value |
|---|---|
| UE PDU pool | `10.45.0.0/16` (`uesimtun0`) |
| N6 / data network | `dn-net` `10.20.6.0/24`; `scenario-b-nginx` at `10.20.6.20` |
| Private application network | `app-net` `10.20.8.0/24` (internal); `scenario-b-django` at `10.20.8.20:8000`; Nginx `10.20.8.10` |
| Lab PKI | local root CA; server cert with `SAN = IP:10.20.6.20` |
| TLS policy | TLS 1.2/1.3, `HTTP:80 → 301 → HTTPS:443` |
| UE image (Project 2) | `telecom-lab-ueransim:3.3.0-p2` — keeps `10.20.6.0/24 dev uesimtun0` across restarts |

## Repository

Fork of [`javiverdu/5G-project-RTU`](https://github.com/javiverdu/5G-project-RTU)
(Project 1). Project 2 lives at
[`javiverdu/5G-2-Security`](https://github.com/javiverdu/5G-2-Security).

```bash
git clone https://github.com/javiverdu/5G-2-Security.git ~/5G-2-Security
```

Clone it to a **native VM path** (not the VirtualBox shared folder): vboxsf
breaks container mounts such as Grafana's provisioning directory.

## For AI agents / new sessions

The design that must not drift is written down, not inferred from chat history:

- [`AGENTS.md`](AGENTS.md) — architecture, frozen values, phase gates, evidence rules.
- [`scenario-b/AGENTS.md`](scenario-b/AGENTS.md) — inherited 5G invariants and gotchas.
- [`project2/scenario-a/AGENTS.md`](project2/scenario-a/AGENTS.md) — exact Scenario A contract.

Requirements source of truth:
`Project 2_Telecommunication Security, DevSecOps, and Traffic Intelligence.pdf`.
