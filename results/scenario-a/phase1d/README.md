# Phase 1D — evidence

Django security baseline: public/protected endpoints, the controlled
`securityadmin` account, CSRF enforcement, secure cookies, HSTS and the
application security headers.

- Date: 2026-11-02
- Container: `scenario-b-django`, reached only through `scenario-b-nginx`
- Account: `securityadmin` (password in the git-ignored `env`, created after
  migrations by `manage.py ensure_lab_user`)
- All requests run in a throwaway client that shares `nr_ue`'s network
  namespace, so they cross the 5G user plane and the TLS gateway.

## Commands

```bash
cd ~/5G-2-Security
./project2/scenario-a/scripts/verify-phase1d.sh
```

## Files

| File | Content |
|---|---|
| `verify-phase1d.txt` | unedited output of the acceptance script |
| `https-headers.txt` | response headers on `GET /health/` over HTTPS |
| `cookies.txt` | `Set-Cookie` lines for the CSRF and session cookies |

## Observed

- Public: `/`, `/health/`, `/api/status/`, `/search/` return `200`; `/admin/`
  returns `302` to the login page.
- Anonymous `GET /profile/` → `302 https://10.20.6.20/accounts/login/?next=/profile/`.
- `POST /accounts/login/` with a valid CSRF token → `302`; then
  `GET /profile/` → `200` with `Username: securityadmin` and
  `Authenticated: True`.
- Session cookie:
  `sessionid=…; HttpOnly; Max-Age=1209600; Path=/; SameSite=Lax; Secure`.
- CSRF cookie: `csrftoken=…; Path=/; SameSite=Lax; Secure`.
- `GET /feedback/` → `200`; `POST` with the form token → `200`; missing token →
  `403`; invalid token → `403`.
- Headers: `Strict-Transport-Security: max-age=3600`, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
  `Cross-Origin-Opener-Policy: same-origin`.
- `/search/?q=<script>alert(1)</script>` renders the query escaped
  (`&lt;script&gt;`) and never as live HTML.

## Notes

- HSTS appears only because Django trusts `X-Forwarded-Proto: https` from
  Nginx (`SECURE_PROXY_SSL_HEADER`); a direct HTTP request to Django would not
  receive it. The header is therefore evidence that the proxy contract works.
- Logout is a CSRF-protected POST (`/accounts/logout/`), matching Django's
  default `LogoutView`; a GET returns `405`.
- The `securityadmin` password is set only when the account is first created;
  changing `LAB_ADMIN_PASSWORD` on an existing `django-data` volume does not
  reset it.
