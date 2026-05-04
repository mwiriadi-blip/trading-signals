# DEPLOY.md — Trading Signals operator runbook

**Primary deployment:** GitHub Actions (free, stateless-by-design, cron-driven).
**Alternative deployment:** Replit Reserved VM + Always On (persistent process).

***

## Quickstart — GitHub Actions (primary)

1. Fork / clone the repo.
2. Add Secrets under **Settings → Secrets and variables → Actions**:
   - `RESEND_API_KEY` (required) — from Resend Dashboard → API Keys
   - `SIGNALS_EMAIL_TO` (required) — your email address
3. Enable Actions: **Settings → Actions → General → "Allow all actions and reusable workflows"**.
4. **Update the README.md status badge URL** to your own `owner/repo` slug: replace the literal `${{GITHUB_REPOSITORY}}` placeholder in README.md with e.g. `mwiriadi/trading-signals`. Commit and push.
5. Verify: **Actions tab → Daily signal check → "Run workflow"** (manual dispatch) → confirm green run + email arrives. The badge in README.md should now render as a green "passing" indicator.
6. Wait for first scheduled run at **00:00 UTC (08:00 AWST)** next weekday.

### What the workflow does

The `.github/workflows/daily.yml` workflow runs every weekday at 00:00 UTC:

1. Checks out the repo at HEAD.
2. Installs Python 3.13.x (pinned in `.python-version`) with pip cache.
3. Runs `.venv/bin/python main.py --once` — fetches OHLCV, computes signals, updates `state.json`, renders `dashboard.html`, sends the daily email.
4. If step 3 succeeded, commits the updated `state.json` back to the repo using `stefanzweifel/git-auto-commit-action@v5` with `add_options: '-f'` (force-add; `state.json` is gitignored locally).

### Cost estimate

Daily run × 5 weekdays × 4.3 weeks/month × ~60s/run ≈ 21 minutes/month.

- **Public repos:** unlimited Actions minutes.
- **Private repos:** 2000 minutes/month free tier. Our usage is ~1% of the tier.
- Ubuntu-latest runner is billed at the 1× multiplier. No other billable resources.

***

## Alternative — Replit (Reserved VM + Always On)

Why Replit is an alternative, not primary:

- Replit Autoscale cold-starts kill the in-process `schedule` loop — cannot persist a daily cron.
- Replit Reserved VM + Always On keeps the process alive 24/7 but requires a paid plan.
- GitHub Actions is free and stateless-by-design — no process to keep alive.

### Setup

1. Import this repo into Replit.
2. Add Secrets in the **Replit Secrets tab**:
   - `RESEND_API_KEY`
   - `SIGNALS_EMAIL_TO`
3. Enable **Reserved VM + Always On** under the Replit project's Deployments / Always On settings. Required for the `schedule` loop to persist across Replit's resource-reclaim cycles.
4. Click **Run**. `.venv/bin/python main.py` (no flags) enters the schedule loop automatically per Phase 7 default-mode dispatch:
   - Runs an immediate first check (SCHED-02).
   - Registers `schedule.every().day.at('00:00').do(...)` for the daily loop.
   - Loops forever calling `schedule.run_pending()` every 60 seconds.

### Filesystem-persistence caveat

- Replit **Reserved VM** persists `state.json` across process restarts.
- Replit **Autoscale** DOES NOT — cold starts reset the filesystem on every wake. **Do not deploy this on Autoscale.**

### Timezone invariant

The `schedule` library's `.at('00:00')` uses **process-local time**. Both `ubuntu-latest` (GHA) and Replit Reserved VM default to UTC, and `_run_schedule_loop` asserts this at entry via the `_get_process_tzname()` wrapper:

```python
assert _get_process_tzname() == 'UTC', '[Sched] process tz must be UTC ...'
```

If the assertion fails (custom `TZ` environment variable somewhere), set `TZ=UTC` in the Replit Secrets tab.

***

## Environment variable reference

| Variable | Required | Purpose |
|----------|----------|---------|
| `RESEND_API_KEY` | Yes (deploy) | Resend API key for daily email dispatch. Local dev without this key triggers Phase 6 graceful-degradation (writes `last_email.html` + console log). |
| `SIGNALS_EMAIL_TO` | Yes (deploy) | Recipient email address override. If unset, notifier.py falls back to the Phase 6 hardcoded default. |
| `RESET_CONFIRM` | No (dev/CI only) | Set to `YES` to skip the interactive prompt inside `_handle_reset` during CI runs. Never set this in production. |

**Not in the formal contract (superseded / deferred):**

- `ANTHROPIC_API_KEY` — LLM-backed summarisation was considered for v1 but deferred. Env var is ignored by current code.
- `FROM_EMAIL` — sender address is hardcoded in `notifier.py` (Resend-verified-domain invariant per Phase 6 D-14).
- `TO_EMAIL` — superseded by `SIGNALS_EMAIL_TO`.

***

## Local development

Phase 7 introduced a default-mode schedule loop. Running `.venv/bin/python main.py`
with NO flags now enters an infinite `schedule.run_pending()` loop, and
`_run_schedule_loop` asserts the process TZ is UTC. That means local
developers need to be aware of TZ in one specific case.

- **Provision a local venv with Python 3.13 first:** `python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- **`.venv/bin/python main.py` (default / loop mode) requires `TZ=UTC` in the shell.**
  If you run this on a non-UTC workstation (e.g. macOS with `Australia/Perth`),
  export UTC first: `export TZ=UTC && .venv/bin/python main.py`. Without this, the UTC
  assertion raises at loop entry and the process exits non-zero.
- **`.venv/bin/python main.py --once`, `.venv/bin/python main.py --test`, `.venv/bin/python main.py --force-email`, and `.venv/bin/python main.py --reset` are always safe locally, regardless of shell TZ.** These flags short-circuit before the schedule loop, so the UTC assertion never runs. The weekday gate inside `run_daily_check` uses `_compute_run_date()` which reads AWST via `zoneinfo`, not process TZ — so "today AWST" is computed correctly no matter what `TZ` your shell has.

***

## Troubleshooting

### "Green run but no email arrived"

Check the `RESEND_API_KEY` secret is set correctly under Actions → Secrets. Phase 6 graceful-degradation writes `last_email.html` to the runner's ephemeral filesystem when the key is missing; the workflow run still shows green because email failures are non-fatal (NOTF-07 / NOTF-08).

### "Email arrives later than 08:00 AWST"

GitHub Actions cron drifts 5–30 minutes during peak hours — 00:00 UTC is the most popular cron slot on the planet and gets queued. This is **documented GitHub behaviour, not a bug**. For sub-minute precision, pick a less-popular offset (e.g. `'17 0 * * 1-5'` fires at 08:17 AWST) — but this is not recommended unless the daily schedule really demands it.

### "Run failed with DataFetchError"

Yahoo Finance transient outage. `data_fetcher.fetch_ohlcv` retries 3× with 10s backoff (DATA-03) before raising. If all retries fail, the workflow exits non-zero and the commit step is skipped (`if: success()`), so `state.json` stays at yesterday's value and next weekday's run retries. No manual intervention needed.

### "State.json commit conflict"

You manually edited `state.json` during a cron run. Resolve the git conflict manually:

```bash
git pull --rebase
# resolve conflicts in state.json
git rebase --continue
git push
```

**Never force-push** (CLAUDE.md safety rule).

### "Scheduler loop crashed on Replit"

Check the Replit console logs. `schedule.every().day.at('00:00')` requires the process to stay alive — verify **Always On** is active in the Replit project settings. If the loop logged an exception at WARNING level (e.g. `[Sched] unexpected error caught in loop`), that individual run failed but the loop kept ticking. If the process terminated, restart it manually.

### "Scheduler fires at the wrong wall-clock time on Replit"

Confirm the Replit container's timezone is UTC (default for Reserved VM). Run `date` in the Replit shell; the output should end in `UTC`. If it doesn't, add `TZ=UTC` to the Replit Secrets tab and restart the process.

### "First workflow run after deploy — no state.json commit"

Check the workflow Actions log for `"Working tree clean. Nothing to commit."` — that means `add_options: '-f'` is missing from the `stefanzweifel/git-auto-commit-action@v5` step. `state.json` is in `.gitignore`, so the action's default `git add` is a no-op on it. Fix by adding `add_options: '-f'` to the step's `with:` block in `.github/workflows/daily.yml`.

### "[skip ci] token limitations"

The `[skip ci]` token in our commit messages prevents future push-triggered CI workflows from running on `state.json`-only commits. It does NOT affect the daily cron schedule — cron triggers are independent of commits. If you add a push-triggered test workflow later, `[skip ci]` will correctly prevent it from running on the bot's daily-update commits.

### "Branch protection blocked the commit"

If the `github-actions[bot]` commit was blocked by branch protection rules:

- **Recommended:** Add `github-actions[bot]` to **Settings → Branches → Branch protection rules → Allow specified actors to bypass required pull requests**.
- **Alternative:** Use a Personal Access Token with `contents: write` scope, store it as a repo secret (e.g. `BOT_PAT`), and pass it via `token: ${{ secrets.BOT_PAT }}` to the `git-auto-commit-action` step.

### "README badge not rendering / shows 'Workflow not found'"

The README.md status badge URL embeds the literal string `${{GITHUB_REPOSITORY}}` as a placeholder. Replace that placeholder with your own `owner/repo` slug (e.g. `mwiriadi/trading-signals`) and commit. The badge should render within a few seconds after the first green workflow run. If it still doesn't render, check that the workflow file is at `.github/workflows/daily.yml` (GitHub is case-sensitive about the `.github/workflows/` path).

### "AssertionError: [Sched] process tz must be UTC" when running locally

You ran `.venv/bin/python main.py` (default loop mode) on a workstation with non-UTC system TZ. Either:
- Run `export TZ=UTC && .venv/bin/python main.py` (recommended for local loop-mode dev).
- Use `.venv/bin/python main.py --once` instead — `--once` short-circuits before the loop so the TZ assertion never runs.

***

## Notes

- `SPEC.md` is the historical project brief; `PROJECT.md` and `CLAUDE.md` are the current source of truth for deployment specifics.
- Env-var names in this runbook supersede `SPEC.md`: `TO_EMAIL` → `SIGNALS_EMAIL_TO`, `FROM_EMAIL` → hardcoded in `notifier.py`, `ACCOUNT_START` / `SEND_TEST_ON_START` removed entirely.
- If you migrate the deployment to a minimal container image (Alpine, distroless), add `tzdata==2024.1` to `requirements.txt` — default ubuntu-latest and Replit Reserved VM ship with OS tzdata so current Phase 7 does not pin it.
