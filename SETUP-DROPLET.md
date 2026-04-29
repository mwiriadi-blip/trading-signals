# SETUP-DROPLET.md — Trading Signals web-layer one-time setup

**Phase:** 11 (Web Skeleton — FastAPI + uvicorn + systemd)
**Audience:** Operator (Marc), running once on the DigitalOcean droplet.
**Prerequisites:**
- Droplet provisioned (Ubuntu LTS 22.04 or 24.04, systemd, public IP)
- Repo cloned to `/home/trader/trading-signals` with `.venv` populated
- Logged in as `trader` (or able to `sudo -u trader`) on the droplet
- Plan 11-01..11-03 artifacts present: `web/app.py`, `systemd/trading-signals-web.service`, `deploy.sh`
- `.env` file is **NOT required** for Phase 11. The unit file uses `EnvironmentFile=-` (leading dash = systemd treats the file as optional). Phase 13 will introduce `WEB_AUTH_SECRET` and require `.env`.

> **Note (Phase 13):** Phase 13 (AUTH) makes `.env` REQUIRED — see [§Configure auth secret](#configure-auth-secret-phase-13-auth-01) below. Phase 11's "optional .env" note is historical context.

This runbook is run ONCE per droplet. After completion, all updates flow through `bash deploy.sh`.

---

## Install systemd unit

```bash
sudo cp /home/trader/trading-signals/systemd/trading-signals-web.service \
        /etc/systemd/system/trading-signals-web.service

sudo systemctl daemon-reload
sudo systemctl enable trading-signals-web
sudo systemctl start trading-signals-web
systemctl status trading-signals-web
```

Expected `systemctl status` output excerpt:

```
● trading-signals-web.service - Trading Signals — FastAPI web process
     Loaded: loaded (/etc/systemd/system/trading-signals-web.service; enabled; preset: enabled)
     Active: active (running) since ...
   Main PID: ... (uvicorn)
```

Validate unit file syntax:

```bash
sudo systemd-analyze verify /etc/systemd/system/trading-signals-web.service
# Expected: no output (silence = success)
```

---

## Configure auth secret (Phase 13 AUTH-01)

Phase 13 introduces shared-secret header auth. The web service refuses to start if `WEB_AUTH_SECRET` is missing, empty, or shorter than 32 characters (D-16, D-17 — fail-closed).

Generate a 32-character hex secret (≈128 bits of entropy):

```bash
openssl rand -hex 16
# Example output: a1b2c3d4e5f67890abcdef1234567890  (32 hex chars)
```

Fallback if `openssl` is not on the droplet:

```bash
python3 -c "import secrets; print(secrets.token_hex(16))"
```

Append the secret to `/home/trader/trading-signals/.env` (create the file if absent — `EnvironmentFile=-` makes it optional in Phase 11, but Phase 13 D-16 fail-closed requires it):

```bash
echo "WEB_AUTH_SECRET=<paste-32-char-hex-here>" >> /home/trader/trading-signals/.env
chmod 600 /home/trader/trading-signals/.env
```

Restart the web unit and verify it boots cleanly:

```bash
sudo systemctl restart trading-signals-web
journalctl -u trading-signals-web -n 20 --no-pager
# Expected: no `RuntimeError: WEB_AUTH_SECRET env var is missing or empty` line.
```

Test the auth gate end-to-end (after Phase 12 nginx is wired, replace `127.0.0.1:8000` with `https://signals.<owned-domain>.com`):

```bash
curl -sI http://127.0.0.1:8000/
# Expected: HTTP/1.1 401 Unauthorized

curl -sI -H "X-Trading-Signals-Auth: <your-secret>" http://127.0.0.1:8000/
# Expected: HTTP/1.1 200 OK (or 503 if dashboard.html not yet rendered).
```

> **Rotation:** Operator-manual; not tooled in v1.1. To rotate: regenerate with `openssl rand -hex 16`, edit `.env`, `sudo systemctl restart trading-signals-web`. Deferred to v1.2 — see CONTEXT.md D-20.

---

## Configure auth username (Phase 16.1 AUTH-04 + AUTH-08)

Phase 16.1 introduces cookie-based login + TOTP 2FA. The form has two fields — a username and a password. The password is `WEB_AUTH_SECRET` from the section above; the username is a new env var:

```bash
echo "WEB_AUTH_USERNAME=marc" >> /home/trader/trading-signals/.env
sudo systemctl restart trading-signals-web
```

> **Constraint:** Username must be non-empty and must NOT contain the `:` character (legacy Basic Auth field separator — fail-closed at boot if violated; the unit will refuse to start with a clear `RuntimeError` in journald).

> **Why a username is needed:** with TOTP enrolled, the operator types creds into the form and then a 6-digit code from their authenticator app. The username carries no security entropy (`hmac.compare_digest` constant-time compare; auth strength is in `WEB_AUTH_SECRET`) — pick whatever's memorable.

Verify by visiting `https://signals.<owned-domain>.com/` from a browser (curl path is unchanged — header still works without a username).

---

## First-login TOTP enrollment walkthrough (Phase 16.1 AUTH-08)

Run this ONCE per droplet, the first time the operator visits the dashboard from a browser after Phase 16.1 ships:

1. Visit `https://signals.<owned-domain>.com/` from your phone or laptop.
2. The browser is redirected to `/login` (302). Enter `WEB_AUTH_USERNAME` and `WEB_AUTH_SECRET` from `.env`.
3. The server detects no TOTP secret on file and redirects to `/enroll-totp`. A QR code renders.
4. Open your authenticator app (Google Authenticator, 1Password, Authy, Microsoft Authenticator) and scan the QR code. The app shows a 6-digit code that rotates every 30 seconds. (If the camera doesn't work, type the displayed secret string manually.)
5. Type the current 6-digit code into the form and press "Verify and finish".
6. The server marks enrollment complete, sets a 12-hour `tsi_session` cookie, and redirects to `/`. The dashboard renders with a "Sign out" button in the top-right of the header.

Subsequent logins: enter creds + 6-digit code (no QR rescan). iOS Safari Keychain auto-fills creds on next-day re-login (one tap).

> **Lost phone / new device:** click "Lost 2FA? Reset via email" on `/login` (Phase 16.1 Plan 03 wires the route — see "Recovery walkthrough (lost phone)" below).

---

## Configure recovery email (Phase 16.1 AUTH-11)

The Phase 16.1 magic-link reset (Plan 03) emails a one-time signed link to a recovery address when the operator clicks "Lost 2FA?". The recipient is the `OPERATOR_RECOVERY_EMAIL` env var; default `mwiriadi@gmail.com`.

```bash
echo "OPERATOR_RECOVERY_EMAIL=mwiriadi@gmail.com" >> /home/trader/trading-signals/.env
sudo systemctl restart trading-signals-web
```

> **Boot validation:** the unit refuses to start if `OPERATOR_RECOVERY_EMAIL` is malformed (must match `name@domain.tld`). systemd `Restart=on-failure` surfaces the `RuntimeError` in journald — `journalctl -u trading-signals-web -n 50 -f` shows the exact line.

> **Why this is required:** the recovery email is the operator's ONLY out-of-band channel for re-enrolling a new authenticator. Choose an inbox you can actually reach from the new device. Resend (the email transport) bills against the project's existing API key — no new vendor.

---

## Configure base URL for magic-link emails (Phase 16.1 AUTH-11)

Magic-link emails contain an absolute URL pointing back to `/reset-totp?token=<...>`. The server constructs this URL from the `BASE_URL` env var. There is **NO localhost fallback** — if `BASE_URL` is unset, the server logs `[Web] BASE_URL env var not set — magic-link email skipped` and the operator gets the generic "Check your email" page without an email actually being sent (LEARNING `Localhost fallbacks in URL construction break silently in production`).

```bash
echo "BASE_URL=https://signals.<owned-domain>.com" >> /home/trader/trading-signals/.env
sudo systemctl restart trading-signals-web
```

Replace `<owned-domain>.com` with the actual domain pointing at the droplet (matches what nginx serves; `https://` required).

---

## Recovery walkthrough (lost phone)

When the operator loses access to their authenticator app, follow these steps. The flow assumes Phase 16.1 Plan 03 (`/forgot-2fa` + `/reset-totp`) is deployed.

1. From any device with browser access, visit `https://signals.<owned-domain>.com/login`.
2. Click "Lost 2FA? Reset via email" beneath the submit button.
3. On the `/forgot-2fa` form, enter `WEB_AUTH_USERNAME` and `WEB_AUTH_SECRET`. Submit.
4. The page reads "Check your email." (Same generic page renders regardless of cred validity — no leak per E-07 spec.)
5. Open Gmail (or whatever inbox `OPERATOR_RECOVERY_EMAIL` points at). Within ~30 seconds, an email arrives:
   - Subject: `Trading Signals — 2FA reset link (valid 1 hour)`
   - Body: prominent "Reset 2FA" button + plain-text fallback link
6. Click the "Reset 2FA" button. The link is **single-use and expires in 1 hour**. Clicking redirects to `/enroll-totp?reset=1` with two action buttons:
   - **Keep current authenticator** — operator still has the device but lost the cookie session; clicking returns straight to `/`.
   - **Set up new authenticator** — operator picks up a new device; clicking regenerates the TOTP secret and renders a fresh QR code. Scan the new QR with the new authenticator app, type the displayed 6-digit code, and submit. The dashboard loads.
7. **Token is now consumed.** Visiting the same email link again returns the generic "Reset link is no longer valid" page. To recover from another lost-phone event, restart the flow at step 1.

> **Rate limits:** maximum 3 reset emails per 24-hour window per account, plus 3 POST `/forgot-2fa` per hour per IP. If you somehow burn through these, wait the window out OR ssh to the droplet and clear `pending_magic_links` in `auth.json` manually (then `sudo systemctl restart trading-signals-web`).

---

## Trusted-device management (/devices)

Phase 16.1 Plan 02 introduced the per-device 30-day "Trust this device" cookie (`tsi_trusted`). Operators manage these via `https://signals.<owned-domain>.com/devices`.

The page lists every trusted device with its derived label (e.g. `iPhone Safari · 203.0.113.x · 2026-04-29`), last-seen timestamp, granted-at date, and a "Revoke" button. There's also a "Revoke all other devices" bulk action that clears every device EXCEPT the one currently signed in.

> **Cookie-session-only gate:** `/devices` is reachable ONLY via cookie session (E-06). The legacy `X-Trading-Signals-Auth` header path returns 403 here — by design, since revocation needs to know "which device am I revoking from", and headerless callers have no device identity.

> **Why revoke?** if a phone is lost or sold, revoke its trust cookie so the legacy 30-day skip can no longer be used. The trust cookie is a *signed* JWT-like token, but it carries a UUID; the server checks the UUID against `auth.json.trusted_devices[].revoked` on every request and refuses revoked entries.

---

## Troubleshooting — 302 redirects to /login

Browser navigation to `/` without an active cookie session now returns `302 Location: /login?next=<path>` (Phase 16.1 D-04). This is expected.

- **curl / scripts** (no browser headers): `curl -H "X-Trading-Signals-Auth: $secret" /` → 200 (header path unchanged per AUTH-05).
- **curl WITHOUT header**: `curl /` → 401 plain-text `unauthorized` (Phase 13 AUTH-07 contract preserved verbatim — no redirect, no `WWW-Authenticate`).
- **Browser without auth**: 302 to `/login?next=/`. Sign in to land back on `/`.
- **Browser WITH expired/tampered cookie**: same 302 → `/login`. Sign in to issue a fresh cookie.

If a browser visit returns 401 instead of 302: the request likely lacks `Sec-Fetch-Mode: navigate` AND lacks `Accept: text/html`. Modern Safari/Chrome/Firefox always send these on top-level navigations; if the operator is testing via curl with a custom Accept, that's expected curl-shaped behaviour.

---

## Install sudoers entry for trader

`deploy.sh` calls `sudo -n systemctl restart trading-signals` AND `sudo -n systemctl restart trading-signals-web` as two separate invocations (split form per Phase 11 REVIEWS HIGH #4 — sudo matches the full argv, so a combined invocation may NOT match either sudoers rule).

First, verify the actual `systemctl` path:

```bash
which systemctl
# Expected: /usr/bin/systemctl
```

Create the sudoers file using visudo:

```bash
sudo visudo -f /etc/sudoers.d/trading-signals-deploy
```

Paste exactly (replace `/usr/bin/systemctl` if your `which systemctl` returned a different path). The line has TWO comma-separated rules — one per unit — matching deploy.sh's two split `sudo -n` calls:

```
# Phase 11 D-21: trader may restart ONLY these two units.
# Two comma-separated rules match deploy.sh's two split `sudo -n systemctl
# restart <unit>` calls (REVIEWS HIGH #4 — combining both unit names into
# one sudo invocation may NOT match either rule).
trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web
```

Save and exit. Set permissions:

```bash
sudo chmod 440 /etc/sudoers.d/trading-signals-deploy
sudo chown root:root /etc/sudoers.d/trading-signals-deploy
```

Validate the file:

```bash
sudo visudo -c -f /etc/sudoers.d/trading-signals-deploy
# Expected: /etc/sudoers.d/trading-signals-deploy: parsed OK
```

**Verify passwordless sudo works** (REVIEWS HIGH #4 — deploy.sh uses `sudo -n`; a missing/mismatched rule here would make every deploy fail fast. Catch the miss BEFORE the first deploy):

```bash
sudo -n systemctl restart trading-signals-web
# Expected: silent success. The service restarts without any prompt.
# If this prints 'sudo: a password is required' or similar, the sudoers
# rule is wrong:
#   - Check the systemctl path matches `which systemctl`
#   - Check file permissions are 0440 and owner is root:root
#   - Re-run `sudo visudo -c -f /etc/sudoers.d/trading-signals-deploy`

# Also test the first unit (deploy.sh restarts both):
sudo -n systemctl restart trading-signals
# Expected: silent success OR 'Unit trading-signals.service not found'
# (acceptable if Phase 10 hasn't installed the signal unit; sudoers rule
# still matches — the `not found` error is from systemctl not sudo).
```

If `sudo -n systemctl restart trading-signals-web` prompts or errors with an auth-related message, deploy.sh will fail on every run. Fix the sudoers rule before proceeding.

Anti-pattern WARNING: NEVER grant `trader ALL=(root) NOPASSWD: ALL` or `trader ALL=(root) NOPASSWD: /usr/bin/systemctl *` — both create privilege escalation. The entry MUST list the two specific unit names per D-21. NEVER bind uvicorn with `--host 0.0.0.0` — external access goes through nginx in Phase 12.

---

## Verify port binding (WEB-02 / SC-4)

```bash
ss -tlnp | grep 8000
```

Expected:

```
LISTEN 0  ...  127.0.0.1:8000  0.0.0.0:*  users:(("uvicorn",pid=...,fd=...))
```

If `0.0.0.0:8000` appears on the local-address column, fix the unit file immediately — NEVER ship `0.0.0.0` in Phase 11.

Test loopback HTTP:

```bash
curl -fsS http://127.0.0.1:8000/healthz
# Expected: {"status":"ok","last_run":<YYYY-MM-DD string or null>,"stale":<true|false>}
# Note: last_run is DATE-ONLY (YYYY-MM-DD) per REVIEWS HIGH #1.
```

From OUTSIDE (your laptop), confirm port 8000 is NOT externally reachable:

```bash
curl --max-time 5 http://<DROPLET_IP>:8000/healthz
# Expected: connection refused or timeout
```

---

## Verify deploy.sh end-to-end (INFRA-04 / SC-3)

On the droplet:

```bash
cd /home/trader/trading-signals
bash deploy.sh
```

Expected (first run):

```
[deploy] starting deploy at YYYY-MM-DD HH:MM:SS
[deploy] branch: main — OK
[deploy] fetching from origin...
[deploy] pulling (ff-only)...
Already up to date.
[deploy] installing requirements...
Requirement already satisfied: ...
[deploy] restarting services...
[deploy] smoke testing /healthz...
[deploy] /healthz OK after 1 attempt(s)
[deploy] deploy complete. commit=<hash>
```

Run AGAIN without changes:

```bash
bash deploy.sh
```

Expected (idempotent — SC-3):

```
[deploy] starting deploy at ...
[deploy] branch: main — OK
[deploy] fetching from origin...
[deploy] pulling (ff-only)...
Already up to date.            ← MUST appear
[deploy] installing requirements...
Requirement already satisfied: ...
[deploy] restarting services...
[deploy] smoke testing /healthz...
[deploy] /healthz OK after 1 attempt(s)
[deploy] deploy complete. commit=<hash>
```

Both runs must exit 0.

Optional shellcheck:

```bash
sudo apt install shellcheck
shellcheck deploy.sh
```

---

## Verify boot persistence (WEB-01 / SC-1)

```bash
sudo reboot
```

Wait ~30 seconds, reconnect:

```bash
systemctl status trading-signals-web
# Expected: Active: active (running) since <reboot timestamp>
ss -tlnp | grep 8000
# Expected: 127.0.0.1:8000
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Phase 11-specific: no `.env` file, unit still starts | Expected — `EnvironmentFile=-` makes `.env` OPTIONAL in Phase 11 | No action needed. Phase 13 will require `.env`. |
| `command not found: uvicorn` | `.venv` not populated | `cd /home/trader/trading-signals && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt` |
| `sudo -n systemctl restart` prompts for password | sudoers path mismatch / perms wrong | Re-run `which systemctl`, edit sudoers, verify `chmod 440` + `chown root:root`, run `sudo visudo -c -f /etc/sudoers.d/trading-signals-deploy` |
| `curl 127.0.0.1:8000/healthz` returns connection refused | uvicorn not running | `systemctl status trading-signals-web`; `journalctl -u trading-signals-web -n 50` |
| `ss -tlnp` shows `0.0.0.0:8000` | unit file `--host` wrong | Fix systemd unit, re-copy, daemon-reload, restart |
| `bash deploy.sh` fails with `expected branch 'main'` | feature branch/detached HEAD | `git checkout main` |
| `git pull --ff-only` fails | commits diverged | Investigate manually; D-22/D-25 forbid auto-rollback |
| deploy.sh smoke test fails with `/healthz did not respond within 10s` | uvicorn crashed OR port occupied | `journalctl -u trading-signals-web -n 50`; `ss -tlnp \| grep 8000` |

---

## What's NOT in this doc

- HTTPS / nginx / Let's Encrypt → Phase 12
- Domain / DNS → operator prerequisite
- GitHub deploy key → Phase 10

---

*Last updated: Phase 11 (Web Skeleton). 2026-04-24 post-cross-AI-review.*
*Run this runbook ONCE per droplet. Subsequent updates use `bash deploy.sh`.*
