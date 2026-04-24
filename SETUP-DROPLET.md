# SETUP-DROPLET.md — Trading Signals web-layer one-time setup

**Phase:** 11 (Web Skeleton — FastAPI + uvicorn + systemd)
**Audience:** Operator (Marc), running once on the DigitalOcean droplet.
**Prerequisites:**
- Droplet provisioned (Ubuntu LTS 22.04 or 24.04, systemd, public IP)
- Repo cloned to `/home/trader/trading-signals` with `.venv` populated
- Logged in as `trader` (or able to `sudo -u trader`) on the droplet
- Plan 11-01..11-03 artifacts present: `web/app.py`, `systemd/trading-signals-web.service`, `deploy.sh`
- `.env` file is **NOT required** for Phase 11. The unit file uses `EnvironmentFile=-` (leading dash = systemd treats the file as optional). Phase 13 will introduce `WEB_AUTH_SECRET` and require `.env`.

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
- Auth secret → Phase 13 (will require `.env` with WEB_AUTH_SECRET)
- Domain / DNS → operator prerequisite
- GitHub deploy key → Phase 10

---

*Last updated: Phase 11 (Web Skeleton). 2026-04-24 post-cross-AI-review.*
*Run this runbook ONCE per droplet. Subsequent updates use `bash deploy.sh`.*
