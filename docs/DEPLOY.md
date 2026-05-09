# DEPLOY.md — Trading Signals operator runbook

**Primary deployment:** DigitalOcean droplet running two systemd units behind nginx + Let's Encrypt TLS. The daily-run unit fetches data, computes signals, persists `state.json`, renders `dashboard.html`, sends the daily email, and pushes `state.json` back to `origin/main` via a deploy key. The web unit serves the FastAPI dashboard.

The one-time bring-up runbook is **[SETUP-DROPLET.md](../SETUP-DROPLET.md)**. This file is the routine-operations runbook.

---

## TL;DR

```bash
# Routine deploy (after pushing to origin/main from your workstation):
ssh trader@<droplet>
cd /home/trader/trading-signals
bash deploy.sh
```

`deploy.sh` is fail-loud and idempotent: branch check → fetch → ff-only pull → pip install → restart `trading-signals` + `trading-signals-web` units → curl `/healthz` retry loop → echo success + commit hash. It does NOT auto-revert (D-25 — fail-loud).

---

## Architecture

| Piece | Path | Role |
|-------|------|------|
| Daily-run unit | `trading-signals.service` | One-shot `python main.py --once` triggered by systemd timer at 00:00 UTC weekdays. Fetches data, computes signals, sends email, commits `state.json` back via deploy key. |
| Web unit | `trading-signals-web.service` | Long-running `uvicorn web.app:app --host 127.0.0.1 --port 8000`. Source: `systemd/trading-signals-web.service` in this repo. |
| nginx | `/etc/nginx/sites-enabled/signals.conf` | TLS termination + reverse-proxy `127.0.0.1:8000`. Source: `nginx/signals.conf` in this repo. |
| Deploy script | `deploy.sh` | Pull-and-restart wrapper invoked by the operator. |

Both units run as the `trader` user, write only to `/home/trader/trading-signals` (systemd `ProtectSystem=strict` + `ReadWritePaths=` on the web unit), and log to journald.

---

## One-time bring-up

See **[SETUP-DROPLET.md](../SETUP-DROPLET.md)** for the full runbook:

- Systemd unit install
- `WEB_AUTH_SECRET` + `WEB_AUTH_USERNAME` provisioning (Phase 13 / 16.1 fail-closed)
- TOTP enrollment walkthrough
- `OPERATOR_RECOVERY_EMAIL` + `BASE_URL` for magic-link 2FA reset
- Sudoers entry granting `trader` passwordless restart of the two units + nginx reload
- nginx + Let's Encrypt wiring (see also `docs/SETUP-HTTPS.md`)
- GitHub deploy-key setup for `state.json` push-back (Phase 10 INFRA-02)

---

## Routine deploys

Workflow:

1. Push code changes to `origin/main` from your workstation (PR or direct).
2. SSH to the droplet as `trader`.
3. `cd /home/trader/trading-signals && bash deploy.sh`.

`deploy.sh` will exit non-zero if:

- The droplet's checked-out branch is not `main` (D-22 branch safety).
- `git pull --ff-only` rejects (the droplet has diverged — typically because the daily-run committed `state.json` and your push raced; resolve by pulling locally and rebasing).
- `python3.13 -m venv` is missing or the venv is the wrong Python version.
- Either systemctl restart returns non-zero (sudoers rule mismatch — see SETUP-DROPLET.md §Install sudoers).
- The healthz retry loop (10 attempts × 1s) cannot reach `http://127.0.0.1:8000/healthz`.

There is **no auto-revert.** If a deploy fails mid-flight, fix forward — pull a corrective commit and re-run `deploy.sh`.

---

## Environment variables

All env vars live in `/home/trader/trading-signals/.env` (mode `0600`, owned by `trader`). The web unit's `EnvironmentFile=-/home/trader/trading-signals/.env` reads them at startup; the daily-run unit reads them via `python-dotenv`.

| Variable | Required | Purpose |
|----------|----------|---------|
| `RESEND_API_KEY` | Yes (deploy) | Resend API key for daily email + magic-link 2FA reset email. |
| `SIGNALS_EMAIL_TO` | Yes | Recipient address for the daily signal email. Required at notifier boot — no fallback (Phase 27-05). |
| `SIGNALS_EMAIL_FROM` | Yes | Verified-domain sender (Phase 12). Resend rejects unverified senders. |
| `WEB_AUTH_SECRET` | Yes (web) | 32-character hex shared secret. Web unit refuses to start if missing/empty/short (Phase 13 D-16, fail-closed). |
| `WEB_AUTH_USERNAME` | Yes (web) | Login username for cookie + TOTP flow (Phase 16.1 AUTH-04). Must not contain `:`. |
| `OPERATOR_RECOVERY_EMAIL` | Yes (web) | Recovery address for magic-link 2FA reset (Phase 16.1 AUTH-11). Must validate as `name@domain.tld` at boot. |
| `BASE_URL` | Yes (web) | Absolute base URL (e.g. `https://signals.<owned-domain>.com`) used to construct magic-link reset URLs. Server skips magic-link emails if unset (no localhost fallback — see global LEARNING). |
| `RESET_CONFIRM` | No (dev/CI only) | Set to `YES` to skip the interactive prompt inside `_handle_reset`. Never set in production. |

See [SETUP-DROPLET.md](../SETUP-DROPLET.md) for the canonical command sequence to provision each variable on a fresh droplet.

**Not in the formal contract (superseded / deferred):**

- `ANTHROPIC_API_KEY` — LLM-backed summarisation considered for v1, deferred. Ignored by current code.
- `FROM_EMAIL` / `TO_EMAIL` — superseded by `SIGNALS_EMAIL_FROM` / `SIGNALS_EMAIL_TO`.

---

## Local development

The `schedule` library's `.at('00:00')` uses **process-local time**. The droplet runs UTC; local workstations rarely do. `_run_schedule_loop` asserts `time.tzname == 'UTC'` at entry and exits non-zero otherwise.

- **Provision a local venv with Python 3.13 first:** `python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- **`.venv/bin/python main.py` (default / loop mode) requires `TZ=UTC` in the shell.** On a non-UTC workstation (e.g. macOS with `Australia/Perth`): `export TZ=UTC && .venv/bin/python main.py`. Without this, the UTC assertion raises at loop entry.
- **`.venv/bin/python main.py --once`, `--test`, `--force-email`, `--reset` are always safe locally regardless of shell TZ.** These flags short-circuit before the schedule loop, so the UTC assertion never runs. The weekday gate inside `run_daily_check` reads AWST via `zoneinfo`, not process TZ — "today AWST" is computed correctly no matter what `TZ` the shell has.

---

## Troubleshooting

### "No email arrived after a successful daily run"

`RESEND_API_KEY` likely missing or revoked. Phase 6 graceful-degradation writes `last_email.html` to disk and logs `[Email] no Resend API key — wrote last_email.html` instead of crashing (NOTF-07 / NOTF-08). Check `journalctl -u trading-signals -n 100 --no-pager` for the log line, fix the key in `.env`, and re-run with `python main.py --force-email`.

### "DataFetchError on the daily run"

Yahoo Finance transient outage. `data_fetcher.fetch_ohlcv` retries 3× with 10s backoff (DATA-03) before raising. If all retries fail, `main.py --once` exits rc=2 and the unit logs the failure; `state.json` stays at yesterday's value and next weekday's run retries. No manual intervention needed (ERR-01 spec amendment).

### "deploy.sh exits with branch safety error"

The droplet's working tree is not on `main`. Likely cause: a manual commit done directly on the droplet. Resolve by `git status` to confirm working state is clean, then `git checkout main`. If the droplet committed `state.json` to a detached HEAD, recover it with `git reflog`.

### "deploy.sh exits at the healthz retry loop"

The web unit failed to start within ~10 seconds. Inspect:

```bash
journalctl -u trading-signals-web -n 50 --no-pager
```

Common causes:

- **`RuntimeError: WEB_AUTH_SECRET env var is missing or empty`** — fail-closed at boot (Phase 13 D-16). Fix `.env` and `sudo systemctl restart trading-signals-web`.
- **`RuntimeError: OPERATOR_RECOVERY_EMAIL ...`** — malformed recovery address. Fix `.env` per SETUP-DROPLET.md §Configure recovery email.
- **Address already in use on 127.0.0.1:8000** — a prior process didn't shut down. `sudo systemctl stop trading-signals-web` then start fresh.

### "Magic-link 2FA reset email never arrives"

Most common cause: `BASE_URL` is unset, so the server skipped sending the email and only rendered the "Check your email" page (no localhost fallback by design — see LEARNING `Localhost fallbacks in URL construction break silently in production`). Check `journalctl -u trading-signals-web -n 50 | grep BASE_URL`. Fix `.env` and restart the web unit.

### "AssertionError: [Sched] process tz must be UTC" when running locally

You ran `.venv/bin/python main.py` (default loop mode) on a workstation with non-UTC system TZ. Either:

- `export TZ=UTC && .venv/bin/python main.py` (recommended for local loop-mode dev).
- Use `.venv/bin/python main.py --once` instead — `--once` short-circuits before the loop so the TZ assertion never runs.

### "state.json on the droplet drifted from origin/main"

The daily-run unit pushes `state.json` back to `origin/main` via a deploy key after a green run (Phase 10 INFRA-02, `_push_state_to_git` in `main.py`). If the push fails (network, deploy key revoked, branch protection), the droplet keeps the local update but the repo is stale. Inspect `journalctl -u trading-signals -n 100 | grep -E 'state push|deploy key'` and re-run `python main.py --once --no-fetch` (or fix the underlying push path) to retry the push.

---

## Notes

- `SPEC.md` is the historical v0 project brief; `.planning/PROJECT.md` and this file are the current source of truth for deployment specifics.
- `.github/workflows/daily.yml.disabled` is preserved as rollback insurance per Phase 10 INFRA-03 (cron retired to avoid duplicate emails when DO took over). The trailing `.disabled` suffix tells GitHub to skip parsing it; the structural contract is pinned by `tests/test_scheduler.py::TestGHAWorkflow` so we can re-enable in a hurry if the droplet ever goes down.
- The v1.0 milestone archive at `.planning/milestones/v1.0-phases/07-scheduler-github-actions-deployment/` retains the original GHA-primary runbook for historical context.
