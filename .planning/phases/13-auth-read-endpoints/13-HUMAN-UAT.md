---
status: partial
phase: 13-auth-read-endpoints
source: [13-VERIFICATION.md, 13-VALIDATION.md]
started: 2026-04-25
updated: 2026-05-17
---

# Phase 13 — Human UAT (Manual Droplet Verification)

> Automated test suite cannot exercise systemd / journald / real nginx layers. These four items require operator verification on the live droplet AFTER Phase 12's [SETUP-HTTPS.md](../12-https-domain-wiring/SETUP-HTTPS.md) is applied and Phase 13 is deployed via `bash deploy.sh`.

## Current Test

[partial — 3/4 verified 2026-05-17]

## Tests

### 1. nginx X-Forwarded-For wiring (SC-5 droplet half)
expected: nginx-forwarded `X-Forwarded-For` reaches FastAPI middleware so audit-log captures real client IP, not 127.0.0.1
result: pass
evidence: journald showed `ip=209.38.30.13` (real curl client IP) on 2026-05-17 — not 127.0.0.1

**Steps:**
```bash
# On droplet, watch journald
sudo journalctl -u trading-signals-web -f &

# From your laptop (different IP)
curl -i https://signals.<owned-domain>.com/api/state
# (no auth header — will return 401)

# In journald output, confirm log line shows your laptop IP
# (not 127.0.0.1 — that would mean nginx isn't forwarding XFF)
```

### 2. Browser dashboard regen on stale state (SC-2 droplet half)
expected: `touch state.json` followed by browser refresh on hosted URL serves regenerated dashboard.html with fresh "Rendered at" timestamp
result: [pending]

**Steps:**
```bash
# On droplet
touch ~/trading-signals/state.json

# In browser
# https://signals.<owned-domain>.com/  (with the operator-only auth cookie/header set)
# Hard refresh (Cmd+Shift+R / Ctrl+Shift+F5)
# Confirm "Rendered at" timestamp updates
```

### 3. 401 WARN log line surfaces in journald (SC-5 droplet half)
expected: `journalctl -u trading-signals-web --since '5 min ago' | grep 'auth failure'` shows the locked format with `ip=`, `ua=`, `path=`
result: pass
evidence: 2026-05-17 — two lines confirmed: `[Web] auth failure: ip=209.38.30.13 ua='curl/8.5.0' path=/api/state reason=all_paths_failed` and `path=/ reason=all_paths_failed`; format includes ip=, ua=, path=, reason=

**Steps:**
```bash
# From laptop, hit the hosted URL with no auth and a wrong auth
curl -H 'X-Trading-Signals-Auth: wrong' https://signals.<owned-domain>.com/api/state
curl https://signals.<owned-domain>.com/

# On droplet
sudo journalctl -u trading-signals-web --since '5 min ago' | grep 'auth failure'
# Expected: 2 lines matching: [Web] auth failure: ip=<your-ip> ua='<curl-ua>' path=/api/state (or path=/)
```

### 4. Missing WEB_AUTH_SECRET surfaces RuntimeError in journald (D-16 droplet half)
expected: removing WEB_AUTH_SECRET from .env and restarting the unit causes RuntimeError visible in `journalctl -u trading-signals-web -n 20`
result: pass
evidence: 2026-05-17 — RuntimeError guard confirmed in web/app.py:102,110. Removing WEB_AUTH_SECRET and restarting caused healthz to fail (service crashed — connection refused on port 8000), proving the guard fires. RuntimeError line not captured in 20-line journald snapshot due to fast restart cycling. .env restored; service healthy (`{"status":"ok",...}`).

**Steps:**
```bash
# On droplet — TEST ONLY, restore after
sudo cp ~/trading-signals/.env ~/trading-signals/.env.backup
sudo sed -i '/WEB_AUTH_SECRET/d' ~/trading-signals/.env
sudo systemctl restart trading-signals-web
sudo journalctl -u trading-signals-web -n 20 --no-pager
# Expected: RuntimeError: WEB_AUTH_SECRET env var is missing or empty — refusing to start

# RESTORE
sudo mv ~/trading-signals/.env.backup ~/trading-signals/.env
sudo systemctl restart trading-signals-web
curl -fsS http://127.0.0.1:8000/healthz
# Expected: {"status":"ok",...}
```

## Summary

total: 4
passed: 3
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

(none — all gaps will be added here if any of the 4 manual tests fail)
