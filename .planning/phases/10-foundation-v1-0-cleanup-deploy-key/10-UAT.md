---
status: partial
phase: 10-foundation-v1-0-cleanup-deploy-key
source: [10-01-SUMMARY.md, 10-02-SUMMARY.md, 10-03-SUMMARY.md, 10-04-SUMMARY.md]
started: 2026-04-24T19:40:00+08:00
updated: 2026-04-24T20:08:00+08:00
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: From a fresh shell in the repo root, `python -m pytest -x -q` completes with rc=0 and reports 681 tests passing. No warnings about import cycles, missing fixtures, or skipped test files. `python main.py --test` (no `state.json` seeded) runs to completion with rc=0 and does NOT log `[State] state.json pushed` (since --test is read-only per D-15).
result: pass
note: "Verified on local Mac dev environment — `pytest -x -q` exited 0 with 681 tests passing (93.46s) during Phase 10 execution. First run was attempted on the droplet but failed because the droplet's main is still at 6b3a8c1 (v1.1 milestone start, pre-Phase-10) — droplet-specific test failure was a golden-email fixture mismatch caused by droplet env also missing RESEND_FROM. Neither finding represents a Phase 10 regression. Droplet UAT deferred until push/pull after `/gsd-ship`."

### 2. BUG-01: --reset syncs account to initial_account (CLI-flag path)
expected: Run `python main.py --reset --initial-account 50000 --spi-contract spi-mini --audusd-contract audusd-standard` then `python -c "import json; s=json.load(open('state.json')); print(s['account'], s['initial_account'])"`. Both values print as `50000.0`. Prior to Phase 10 this reset would leave `account` at the old baseline (100000.0), producing the spurious +900% return bug on the dashboard.
result: pass
evidence: "Local Mac run with .venv/bin/python: 'account: 50000.0   initial_account: 50000.0' — both fields synced. D-01 fix at main.py:1497 verified live. Pre-Phase-10 behavior would have left account at the on-disk value (100000.0 in the backed-up state)."

### 3. CHORE-02: ruff clean on notifier.py + CI guard
expected: `ruff check notifier.py` exits 0 with no output (zero warnings of any category, not just F401). `python -m pytest tests/test_notifier.py::test_ruff_clean_notifier tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression -q` exits 0 — both tests green. The sensitivity test proves the guard would catch a future F401 regression via a tmp_path probe.
result: pass
evidence: "`ruff check notifier.py` → 'All checks passed!' exit 0. `pytest -q` for both tests → 2 passed in 0.22s. REVIEW-HIGH gate (returncode==0 assertion) is live; sensitivity probe verified."

### 4. INFRA-03: GHA workflow renamed, history preserved, tests pass
expected: `ls .github/workflows/` shows only `daily.yml.disabled` (no `daily.yml`). `git log --follow -1 --format='%h %s' .github/workflows/daily.yml.disabled` returns the latest commit for that file and the follow history traces back through Phase 7 origin. `python -m pytest tests/test_scheduler.py::TestGHAWorkflow tests/test_scheduler.py::TestDeployDocs -q` exits 0 with 25 tests passing (12 TestGHAWorkflow + 13 TestDeployDocs).
result: pass
evidence: "`ls .github/workflows/` → only `daily.yml.disabled`. git log --follow traces: 11fdd3b (Phase 10 rename) → 2e3d314 (Phase 9 timeout) → bbdc5e9 (Phase 7 origin). pytest → 25 passed in 0.48s. D-16 + D-18(a) verified."

### 5. SETUP-DEPLOY-KEY.md content review
expected: Opening `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` in any editor shows a 234-line operator runbook with: (a) top-of-file "docs/DEPLOY.md is stale" blockquote banner pointing readers at this file as the current source of truth, (b) Quickstart 6-step checklist, (c) detailed Steps 1-6 covering ssh-keygen → GitHub deploy-key UI → ~/.ssh/config with IdentitiesOnly yes → HTTPS→SSH remote switch → ssh -T bootstrap → `python main.py --once` first-run exercising `_push_state_to_git`, (d) Pitfalls section with 6 entries including systemd WorkingDirectory, clock drift, rollback procedure, README badge rationale, and docs/DEPLOY.md staleness explanation.
result: pass
evidence: "234 lines. Banner at lines 15-25 present verbatim with docs/DEPLOY.md staleness pointer. 10/10 content grep markers hit: ssh-keygen, 'Add deploy key', 'IdentitiesOnly yes', 'git remote set-url', 'ssh -T git@github.com', 'python main.py --once', _push_state_to_git, WorkingDirectory=, docs/DEPLOY.md, docs-sweep."

### 6. D-19 prose: CLAUDE.md + PROJECT.md reflect droplet-primary posture
expected: `CLAUDE.md` line 46 starts with `- **Deployment:** DigitalOcean droplet systemd is the primary path (Phase 11+).` and includes "daily.yml.disabled" + a docs/DEPLOY.md staleness pointer. `.planning/PROJECT.md` §Context §Deployment reads "DigitalOcean droplet systemd is the PRIMARY path", names `_push_state_to_git` in the state-persistence line, and the Key Decisions table row reads "DO droplet systemd PRIMARY (v1.1); GHA cron disabled, Replit alternative". `docs/DEPLOY.md` is unchanged (`git diff --quiet docs/DEPLOY.md` returns rc=0).
result: pass
evidence: "CLAUDE.md:46 rewritten verbatim per spec. PROJECT.md:77-78 rewritten; state persistence names _push_state_to_git. PROJECT.md:105 Key Decisions row updated. Old 'GitHub Actions is the primary path' wording absent from both files. docs/DEPLOY.md git diff clean."

### 7. INFRA-02 live push — droplet deploy-key end-to-end
expected: On the DO droplet, with the deploy key registered per SETUP-DEPLOY-KEY.md Steps 1–5, run `python main.py --once`. Journalctl shows `[State] state.json pushed to origin/main`. `git log -1 --format='%an <%ae> %s'` on the droplet shows `DO Droplet <droplet@trading-signals> chore(state): daily signal update [skip ci]`. The same commit is visible at `https://github.com/<owner>/trading-signals/commits/main` within a minute. After 3 successive weekdays, the last 3 commits in the GitHub commit log are authored by `DO Droplet`.
result: blocked
blocked_by: physical-device
reason: "Requires live SSH deploy-key registration on the DO droplet + 3-weekday observation of GitHub commit log. Documented as manual-only verification in 10-VALIDATION.md §Manual-Only. Operator performs post-`/gsd-ship` when Phase 10+11 reach the droplet via pull."

### 8. INFRA-03 GHA cron silent for 2 consecutive weekdays post-merge
expected: After this phase merges to main, no `[Trading Signals]` email arrives from GitHub Actions between T+0 and T+2 weekdays. The operator inbox shows only the droplet's daily signal email (same sender/subject as before, but arrives from the droplet systemd unit — Phase 11+). If GHA cron were still firing, duplicate emails would arrive per weekday; their absence confirms the `.disabled` suffix retired the schedule.
result: blocked
blocked_by: prior-phase
reason: "Requires 2-weekday observation window post-merge AND the droplet to be actively running the signal. Documented as manual-only verification in 10-VALIDATION.md §Manual-Only. Operator confirms by monitoring inbox for duplicate emails after Phase 10+11 ship."

## Summary

total: 8
passed: 6
issues: 0
pending: 0
skipped: 0
blocked: 2

## Gaps

[none — all issues resolved on reclassification; 2 manual-only verifications tracked as blocked per 10-VALIDATION.md §Manual-Only]
