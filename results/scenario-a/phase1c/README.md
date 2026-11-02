# Phase 1C — evidence

Lab PKI + Nginx TLS gateway: `scenario-b-nginx` on `dn-net 10.20.6.20` and
`app-net 10.20.8.10`, proxying to `http://10.20.8.20:8000`.

- Date: 2026-11-02
- Image: `telecom-lab-nginx:p2` (`nginx:latest` + `iproute2`)
- PKI: `secrets/tls/` (`ca.crt`, `ca.key`, `server.crt`, `server.key`), created
  by `scripts/gen-pki.sh`
- CA key is mounted into no container

## Commands

```bash
cd ~/5G-2-Security
./project2/scenario-a/scripts/gen-pki.sh
./project2/scenario-a/scripts/up.sh
./project2/scenario-a/scripts/verify-phase1c.sh
```

## Files

| File | Content |
|---|---|
| `verify-phase1c.txt` | unedited output of the acceptance script |
| `server-cert.txt` | `openssl x509 -text` of the Nginx certificate |
| `ca-cert.txt` | `openssl x509 -text` of the lab root CA |
| `handshake-tls1_2.txt` | `s_client -tls1_2 -verify_return_error`, from the UE namespace |
| `handshake-tls1_3.txt` | `s_client -tls1_3 -verify_return_error`, from the UE namespace |
| `ue-requests.txt` | `curl -v` HTTP (301) and HTTPS `--cacert` (200), from the UE namespace |
| `nginx-access.txt` | gateway access log: client `10.45.0.6`, no NAT |
| `nginx-inspect.json` | Docker inspect: networks, mounts, capabilities |

## Observed

- Certificate: `subject=O=Telecom Lab, CN=telecom-lab.local`,
  `issuer=O=Telecom Lab, CN=Telecom Lab Root CA`,
  SAN `DNS:telecom-lab.local, DNS:localhost, IP Address:10.20.6.20`,
  valid 2026-11-02 → 2027-11-02, chain verifies against `ca.crt`.
- HTTP `301 Moved Permanently` with `Location: https://10.20.6.20/health/`.
- HTTPS `200` with `--cacert /etc/telecom-lab/ca.crt`; curl reports the
  certificate subject/issuer and `SSL certificate verify ok` (no `-k`).
- TLS 1.2: `ECDHE-RSA-AES256-GCM-SHA384`, verify code 0.
- TLS 1.3: `TLS_AES_256_GCM_SHA384`, verify code 0.
- Access log shows `10.45.0.6` as the client (the UE address from this run), so
  the UPF did not NAT the flow.
- No running container mounts `ca.key`.

## Change to the inherited base

The Project 1 compose called the N6 network `scenario-b-dn`; it is now
`dn-net` (same `10.20.6.0/24`), the name the brief requires. Recreating the
network forced a recreation of `upf` and a new PDU session, so the UE address in
this evidence (`10.45.0.6`) differs from phase 1A's.
