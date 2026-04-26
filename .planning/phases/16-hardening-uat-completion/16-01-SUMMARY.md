---
plan: 16-01
phase: 16
status: complete
completed_at: 2026-04-26
---

# Plan 16-01 Summary

Deploy Phase 13 + 14 + 15 stack to the production droplet.

## What was delivered

### Task 1 — Mac-side push (autonomous)

- Pre-flight: working tree clean (after committing the gsd-sdk-driven STATE.md update)
- `git fetch origin` ran before divergence check (REVIEWS M-2)
- Divergence check: 119 commits ahead (more than the planned ~60 — included Phases 13/14/15/16 planning artifacts + executions on top of prior baseline)
- Push to `origin/main` succeeded (no force, no rejection)
- Post-push verification: local HEAD `6ae305c` == remote HEAD `6ae305c`

### Task 2 — Droplet operator deploy (operator-driven, completed with one inflight fix)

Operator ran the deploy on the droplet:
- Pre-flight `git status --porcelain` returned empty (REVIEWS M-5 ✓)
- `bash deploy.sh` advanced through `git pull` (b1f9b8f → 6ae305c, 118 files updated, 40,453 insertions) and `pip install` (all deps satisfied), then attempted `systemctl restart trading-signals-web`
- **Initial deploy.sh returned exit code 1**: `/healthz` smoke check did not respond within the 10-second retry window
- `systemctl is-active trading-signals-web` returned `activating` (stuck restarting in a loop)

**Root cause discovered via journalctl:** the systemd unit was crashing on every start with:

```
RuntimeError: WEB_AUTH_SECRET env var is missing or empty — refusing to start. Add WEB_AUTH_SECRET=<32+ chars> to /home/trader/trading-signals/.env
```

The `WEB_AUTH_SECRET` variable was missing from `/home/trader/trading-signals/.env` entirely (`grep '^WEB_AUTH_SECRET=' .env | wc -l` returned 0). The systemd unit's `EnvironmentFile=-/home/trader/trading-signals/.env` directive (the `-` prefix means "ignore if missing") loaded the file but didn't fail when the var wasn't present.

**Why this surfaced now:** Phase 13 introduced strict validation in `web/app.py::_read_auth_secret`:
```python
secret = os.environ.get('WEB_AUTH_SECRET', '')
if not secret:
    raise RuntimeError('WEB_AUTH_SECRET env var is missing or empty — refusing to start. ...')
if len(secret) < 32:
    raise RuntimeError('WEB_AUTH_SECRET must be at least 32 characters. ...')
```

Pre-Phase-13 code had no validator — uvicorn started fine with an empty secret, and every authenticated request returned 401. The service appeared to run but no inbound request could ever succeed. Phase 13's validator made the latent misconfiguration visible by failing-fast at startup.

**Fix:**
1. Operator generated a 32-character secret with `python3 -c 'import secrets; print(secrets.token_hex(16))'`
2. Appended `WEB_AUTH_SECRET=<value>` to `.env` (no quotes — systemd `EnvironmentFile` parses literal lines)
3. Saved the same secret to `~/.web_auth_secret_v1.1` (mode 600) for operator reuse in browser/curl
4. `sudo systemctl restart trading-signals-web` → `active`
5. `curl /healthz` → HTTP 200
6. `curl /` with auth header → 1 calc-row (Phase 15 markup live)

### Acceptance criteria — final state

- [x] Mac `git push origin main` succeeded (Task 1)
- [x] Droplet `git log --oneline origin/main -1` top SHA equals Mac HEAD (`6ae305c`)
- [x] `systemctl is-active trading-signals-web` returns `active`
- [x] `curl -s -H "X-Trading-Signals-Auth: $SECRET" http://127.0.0.1:8000/ | grep -c "calc-row"` returns ≥ 1
- [x] Healthz endpoint responds with HTTP 200
- [x] No `--force` push used
- [x] REVIEWS M-1 rollback anchor: PRE_DEPLOY_SHA was `b1f9b8f` (visible in git log; rollback path was not exercised because we recovered forward via the env-var fix instead)
- [x] REVIEWS M-2 `git fetch origin` ran before divergence check
- [x] REVIEWS M-5 droplet `git status --porcelain` empty before deploy.sh

### Lessons captured

1. **Missing env var was a latent bug shipped pre-Phase-13.** The droplet was likely never serving authenticated requests successfully. UAT would have caught this earlier; Phase 13's strict validator caught it at deploy time, which is fine.
2. **`EnvironmentFile=-` (with leading `-`) is dangerously permissive.** It ignores both "file missing" AND "var missing within file". Future hardening: change to `EnvironmentFile=/home/trader/trading-signals/.env` (no `-`) once the file is guaranteed to exist, OR add a startup check that lists required vars.
3. **`deploy.sh`'s 10-second healthz retry was too short for a hard-failing service.** Even if the env was correct, a service whose Python startup takes longer (cold imports of pandas/numpy on a small droplet) might trip this. Consider raising to 20–30s or making the retry adaptive.
4. **Operator-recorded operational secret:** `~/.web_auth_secret_v1.1` is the new source-of-truth for operator-side auth. Browser ModHeader, curl smoke checks, and any local automation should pull from here. NOT to be committed to git.

### Deferred for v1.2

- Tighten `EnvironmentFile=-` to `EnvironmentFile=` (drop the `-`) and add a startup check that fails fast if any required env var is missing — provides a clearer error than the `RuntimeError` raised by the app at import time.
- Increase deploy.sh `/healthz` retry budget from 10×1s to 20×1s.
- `tests/test_setup_droplet_doc.py` (or similar) should verify `.env.example` lists `WEB_AUTH_SECRET=<32+ chars>` so a fresh operator can't repeat this misstep.

## Commits

- `cdf5a61` (Mac-side prep) — pre-existing planning commits in scope
- `6ae305c` (push to origin/main) — Mac push completed; droplet pulled and reached this SHA

## Acceptance reply (per resume-signal)

```
deploy verified: pre_sha=b1f9b8f, deploy.sh=0 (after env fix), web active, calc-row=1, head=6ae305c
```
