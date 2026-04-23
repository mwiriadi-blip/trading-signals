---
status: complete
phase: 07-scheduler-github-actions-deployment
source:
  - 07-01-SUMMARY.md
  - 07-02-SUMMARY.md
  - 07-03-SUMMARY.md
started: 2026-04-23T00:00:00Z
updated: 2026-04-23T00:06:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: With a clean venv, `pip install -r requirements.txt` + `python main.py --test` boots without errors, prints indicators for both instruments, and exits cleanly. No state writes, no email.
result: pass

### 2. `--once` one-shot preserved
expected: `python main.py --once` runs exactly one daily check (fetch + compute + state + email on a trading day) then exits with code 0. Does NOT emit `[Sched] scheduler entered` and does NOT tick in a loop.
result: pass

### 3. Default mode = immediate run + scheduler loop
expected: `python main.py` (no flags) performs one immediate daily check, logs `[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon-Fri`, then stays alive. Ctrl-C exits cleanly without traceback.
result: pass

### 4. Local `.env` is loaded before argparse
expected: Create a local `.env` with `RESEND_API_KEY=test-key-local` and `SIGNALS_EMAIL_TO=you@example.com`. Run `python main.py --test`. The values resolve via `os.environ` (dashboard + notifier code paths that read env vars pick them up). If the .env is absent, existing OS env vars still win (override=False).
result: pass

### 5. GHA workflow_dispatch end-to-end (pre-verified at 07-03 checkpoint)
expected: Actions tab → "Daily signal check" → "Run workflow" on main completes green. `github-actions[bot]` creates a commit `chore(state): daily signal update [skip ci]` touching ONLY `state.json`. Email arrives in `SIGNALS_EMAIL_TO` inbox with the day's signal. README GHA badge renders as "passing". Operator already verified this 2026-04-23 before closing Plan 07-03.
result: pass

### 6. Operator runbook (docs/DEPLOY.md) is accurate
expected: Quickstart steps (1-6) on docs/DEPLOY.md match reality (Fork + add 2 secrets + enable Actions + workflow_dispatch). Env-var reference mentions `RESEND_API_KEY` + `SIGNALS_EMAIL_TO` (not `ANTHROPIC_API_KEY`). Local development section calls out `TZ=UTC` for default loop mode.
result: pass

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
