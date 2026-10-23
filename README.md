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
| A | 1A | 5G SA base + **persistent UE route** (survives container restart) | 🚧 in progress |
| A | 1B | Django + Gunicorn + SQLite on a private `app-net`, `/health/` | ⬜ |
| A | 1C | Lab PKI + Nginx TLS gateway (`80 → 301 → 443`) | ⬜ |
| A | 1D | Django security baseline (login, CSRF, cookies, HSTS, headers) | ⬜ |
| A | 1E | End-to-end acceptance from the UE through the 5G path | ⬜ |
| B | 2A–2E | Preflight, ZAP + Selenium, PCAP + Suricata, Trivy/Syft, correlation + gate | ⬜ planned |

## Structure

```
5G-2-Security/
├── scenario-b/            # 5G SA core (inherited from Project 1) + Project 2 additions
│   └── p2/                # Project 2 — Scenario A work (phases 1A–1E)
├── docs/                  # Project 1 reports (kept as reference; history preserves all)
├── scripts/               # Project 1 Scenario A tooling (reference)
└── results/               # Project 1 evidence (reference)
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

Project 2 work happens in [`scenario-b/p2/`](scenario-b/p2/README.md).

## Working specification (from the brief — confirm before wiring)

These are the values used while scaffolding; if your copy of the brief differs,
they are collected in one place to change:

| Item | Value |
|---|---|
| UE PDU pool | `10.45.0.0/16` (`uesimtun0`) |
| N6 / public network | `10.20.6.0/24` (`dn-net`), Nginx at `10.20.6.20` |
| Private application network | `app-net` `10.20.8.0/24` (internal), Django at `10.20.8.20:8000` |
| Lab PKI | local root CA; server cert with `SAN = IP:10.20.6.20` |
| TLS policy | TLS 1.2/1.3, `HTTP:80 → 301 → HTTPS:443` |
| UE image (Project 2) | `telecom-lab-ueransim:3.3.0-p2` — keeps `10.20.6.0/24 dev uesimtun0` across restarts |

## Repository

Fork of `javiverdu/5G-project-RTU` (Project 1). The origin of this fork points to
the new Project 2 repository — create it on GitHub and:

```bash
git remote add origin https://github.com/<user>/5G-2-Security.git
git push -u origin main
```
