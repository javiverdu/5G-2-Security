# Phase 1E — end-to-end acceptance (gate into Scenario B)

Single script, `project2/scenario-a/scripts/verify-phase1.sh`, run from the VM.
Every request leaves the UE network namespace, crosses the PDU session
(`uesimtun0`), the UPF, `dn-net`, the TLS gateway and reaches Django over
`app-net`. No request uses `-k`.

- Date: 2026-11-02
- UE address during the run: `10.45.0.3`
- Gateway: `scenario-b-nginx` (`telecom-lab-nginx:p2`), `10.20.6.20`
- Application: `scenario-b-django`, `10.20.8.20:8000`
- RAN: UERANSIM `v3.3.0` image on `nr_gnb` and `nr_ue`

## Command

```bash
cd ~/5G-2-Security
./project2/scenario-a/scripts/verify-phase1.sh
```

## Files

| File | Content |
|---|---|
| `verify-phase1.txt` | unedited output of the acceptance script (48 lines) |
| `https-headers.txt` | response headers on `GET /health/` over HTTPS |
| `gateway-access.txt` | gateway access log: every request from `10.45.0.3` |
| `ue-route.txt` | `ip route get 10.20.6.20` and the `uesimtun0` address |

## Result

All checks green:

1. `uesimtun0 = 10.45.0.3/16`; `10.20.6.20` resolves via `uesimtun0`; the UE
   reaches the gateway.
2. Server certificate verifies against the lab CA; TLS 1.2 and TLS 1.3
   handshakes succeed with `-verify_return_error`.
3. HTTP `/` and `/health/` return `301` to `https://10.20.6.20/...`; HTTPS
   returns `200` with the exact `/health/` body, validated by the CA.
4. Public endpoints `/api/status/` (200, `"authenticated": false`), `/search/`
   (200), `/admin/` (302 to login).
5. Anonymous `/profile/` redirects to `/accounts/login/`; login returns 302;
   `/profile/` then returns 200 with `Username: securityadmin` and
   `Authenticated: True`.
6. `/feedback/`: valid CSRF POST `200`; missing token `403`; invalid token
   `403`.
7. Session cookie `Secure; HttpOnly; SameSite=Lax`; CSRF cookie `Secure`;
   `Strict-Transport-Security: max-age=3600`, `X-Frame-Options: DENY`,
   `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`;
   `/search/` escapes reflected input.
8. The gateway access log lists every request with the UE address
   `10.45.0.3`, so no NAT hides the client.

## Environment note

The guest VM hung while idle after phase 1D and had to be hard-reset. After
boot the core containers had to be started again (`deploy.sh`, the N6 override)
and the RAN recreated with `upgrade-ran.sh`; this run is from that restored
deployment. The UE got a new address (`10.45.0.3` instead of `10.45.0.6`),
which is why the gateway log shows the new value.
