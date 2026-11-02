# AGENTS.md — 5G-2-Security (Project 2)

**Read this before changing anything.** It encodes the design that must survive
compaction and new sessions. Precedence: **the brief (PDF) > this file > any
chat summary**. When you learn something that contradicts this file, fix this
file in the same change.

---

## 1. What this repository is

- Course **Project 2: Telecommunication Security, DevSecOps, and Traffic
  Intelligence**, built as a **fork of Project 1** (`javiverdu/5G-project-RTU`,
  full history kept, remote `origin` = `javiverdu/5G-2-Security`).
- **Project 1 is finished.** Its Scenario A (Linux namespaces) and its docs,
  results and PDFs in `docs/`, `scripts/`, `results/`, are **reference only**.
  Do not refactor, "improve" or delete them.
- The reusable asset inherited from Project 1 is the **5G Standalone network**
  in `scenario-b/` (Open5GS + UERANSIM + MongoDB + N6 + Prometheus/Grafana/
  cAdvisor). Project 2 is built **on top of** it, never as a second network.
- Requirements source of truth: `Project 2_Telecommunication Security,
  DevSecOps, and Traffic Intelligence.pdf` (repo root).

Working mnemonic from the brief:
**Reuse → Secure → Model → Test → Detect → Automate → Analyze → Defend.**

## 2. Architecture contract

**Scenario A (BASIC)** — secure application delivery over the real 5G path:

```text
UE → gNB → N3/GTP-U → UPF → N6 → Nginx (TLS) → app-net → Django
```

Nginx is the **only** bridge between `dn-net` and `app-net`. Django is **never**
attached to `dn-net`. TLS terminates at Nginx; internally it is plain HTTP with
`X-Forwarded-Proto: https`.

**Scenario B (ADVANCED)** — a security-engineering layer around the working
Scenario A, **not** a telecom function and **not** a second 5G network:

```text
GitHub → Jenkins → Preflight → ZAP / Selenium → fresh PCAP → Suricata
      → Trivy / Syft → Python correlation → Security Gate (REPORT_ONLY|ENFORCE)
```

Juice Shop (`10.20.10.20:3000`) and Selenium Grid (`10.20.10.30:4444`) live on
`security-net` (`10.20.10.0/24`) and are **isolated** from the Django service.

## 3. Frozen values

Change these only by updating the brief table **and** every doc that repeats
them. They are the spine of the project.

| Item | Value |
|---|---|
| UE PDU pool / UPF TUN | `10.45.0.0/16`, gateway `ogstun = 10.45.0.1` |
| N6 / data network | `dn-net` `10.20.6.0/24`; Nginx `10.20.6.20` |
| Private application net | `app-net` `10.20.8.0/24`, **internal** |
| Security test net | `security-net` `10.20.10.0/24` |
| Nginx | container `scenario-b-nginx`, image `telecom-lab-nginx:p2`, `dn-net .20`, `app-net .10` |
| Django | container `scenario-b-django`, image `telecom-lab-django:0.1`, `app-net .20:8000` |
| UE image | `telecom-lab-ueransim:3.3.0-p2` |
| Persistent UE route | `10.20.6.0/24 → uesimtun0` |
| Django DB | `/app/data/db.sqlite3` on volume `django-data` |
| PKI | Telecom Lab Root CA → server cert (`SAN IP:10.20.6.20`, DNS `telecom-lab.local`, `localhost`) |
| TLS | 1.2 + 1.3; `HTTP:80 → 301 → HTTPS:443` |
| UE CA | `/etc/telecom-lab/ca.crt` (read-only) |
| Repo exclusions | `env`, `secrets/tls/`, `*.pcap`, `*.pcapng` |

**Never commit** the CA private key, server keys, `env`, captures, or secrets.
The CA private key stays on the host and is mounted into **no** container.

## 4. Order of work — phase gates are hard

```text
1A reuse+verify → 1B Django → 1C Nginx+TLS → 1D Django baseline → 1E acceptance
   → 2A Preflight → 2B-1 ZAP baseline → 2B-2 Selenium → 2B-3 arm PCAP
   → 2B-4 controlled SQLi → 2B-5 targeted ZAP (40018) → 2C stop/validate PCAP
   → 2C Suricata (SID 1000001) → 2C-Advanced analytics (optional)
   → 2D Trivy → 2D Syft → 2E correlation → Evidence archive → Security Gate
```

- **Do not skip a phase** or start B before 1E is green. Do not silently reorder
  Scenario B stages.
- 1E is **not** new code: it is the verified baseline that unlocks B.
- Report **tool result → finding → gate decision** separately. A passing
  pipeline never means "the app has no vulnerabilities".

## 5. Conventions

**Layout.** Project 2 work lives in `project2/scenario-a/` and
`project2/scenario-b/`. The inherited 5G base stays in `scenario-b/` untouched.
Do not scatter new files into the inherited tree; add a narrow `AGENTS.md` if a
subtree needs its own rules.

**Scripts.** Bash, `#!/usr/bin/env bash`, `set -euo pipefail`, idempotent,
POSIX-safe paths, effect first then verify. Print `[tag]` prefixes. Never hide
failures with `|| true` unless the failure is explicitly tolerated.

**Docs.** English in the repository, Spanish with the user. Every claim of
success needs an artifact under `results/` or a command the reader can rerun.
Never invent measurements, screenshots, versions or outputs.

**Git.** Conventional, descriptive messages. Never rewrite published history or
force-push. Do not commit unless the user asks. Raw `.pcap`/`.pcapng` and
`secrets/tls/` stay out of Git and are delivered separately.

**Verification.** Each phase ends with a script (`verify-*.sh`) and a documented
exit criterion. Prefer machine-checkable assertions over prose.

## 6. Evidence rules (the brief's attention traps)

| Trap | Required behavior |
|---|---|
| Container state ≠ packet evidence | Never use `docker ps` as proof of N2/N3/N4/N6. Use captures or real requests. |
| Ping ≠ full validation | Also verify registration, HTTP/TLS, TCP/UDP, and the GTP-U path. |
| Docker IP ≠ UE PDU IP | The UE address is `10.45.0.x` on `uesimtun0`; the container IP is management only. |
| N4/PFCP ≠ application traffic | Keep control-plane captures separate from user-plane flows. |
| N6 reachability ≠ 5G user plane | Traffic must originate **inside the UE** and the server must log `10.45.0.x`. |
| N3 ≈ N6 | Expected: GTP-U encapsulated on N3, plain IP on N6. |
| `curl -k` | Allowed for troubleshooting only, **never** as final certificate validation. Use `--cacert`. |

## 7. Environment facts

- Development happens on the **host** at
  `/home/x0riso/Documentos/VSCODE/5G-2-Security`.
- Docker work happens in the **Ubuntu 25.04 VM `UWUNTU`**, reachable from the
  host as `ssh uwuntu` (VirtualBox port forward `127.0.0.1:2222`). Repo path in
  the VM: `~/5G-2-Security` (native disk, **not** the shared folder).
- VM after preparation: 10 GB RAM, 32 GB disk (`/dev/sda2`), 4 GB swap.
  Host: 15 GB RAM, ~21 GB free disk. Do not raise the VM above 10 GB or grow the
  VDI beyond 32 GB without checking the host first.
- **vboxsf breaks container mounts and permissions** (Grafana uid 472). Never run
  Project 2 containers from `/media/sf_5G_project`; use the native clone.
- The host has `gh` authenticated as `javiverdu`; the repository is public.
- The brief is readable by agents at `docs/brief-p2.txt` (PDF text extraction).

## 8. Decisions taken (do not reopen without cause)

1. **Base images — Option B.** The course's `gradiant/*` environment is not
   deployed in the lab. Keep `docker_open5gs`; build the RAN from UERANSIM
   **v3.3.0** source (`telecom-lab-ueransim:3.3.0-p2`) instead of using
   `herlesupreeth/docker_ueransim:latest`, which is **v3.2.6**. Record the
   substitution and the verified versions in the report.
2. **Network names — documented mapping.** Keep the flat `core`
   (`172.22.0.0/24`) for N2/N3/N4/SBI, distinguished by port (`38412/2152/8805/
   7777`). Create `dn-net`, `app-net` and `security-net` with the exact names the
   brief requires. Never claim networks that do not exist.
3. **Container names.** `scenario-b-nginx` replaces `sb-nginx`; never run both.
   `scenario-b-django` is new.
4. **Django version.** `Django==6.0.8` exists on PyPI (verified). Pin it exactly.
5. **UE route.** Only `10.20.6.0/24 dev uesimtun0`. The Project 1
   `default dev uesimtun0` is deliberately not installed.

## 9. Definition of done (per phase)

- [ ] Code/config committed under the documented path.
- [ ] `verify-*.sh` returns success, output saved under `results/`.
- [ ] Doc updated with the exact command and the observed result.
- [ ] `.gitignore` still excludes captures, keys and `env`.
- [ ] No claim that is not backed by an artifact or a rerunnable command.
