---
phase: 07
phase_name: scheduler-github-actions-deployment
review_date: 2026-04-23
reviewer: gsd-code-reviewer (Claude, Opus 4.7 1M)
depth: standard
files_reviewed: 10
status: issues_found
findings:
  critical: 0
  warning: 1
  info: 4
  total: 5
---

# Phase 7: Code Review Report

**Reviewed:** 2026-04-23
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found (1 Warning, 4 Info)

## Summary

Phase 7 lands a clean, well-tested scheduler+GHA-deploy increment. The hex boundary is preserved (`schedule`/`dotenv` are imported only from inside `main.py` helpers, and the AST blocklist correctly forbids them in every other module). The weekday gate, immediate-first-run dispatch, UTC assertion, and never-crash wrappers are all wired and individually unit-tested. The GHA workflow follows least-privilege (explicit secret mapping, `contents: write` only, concurrency serialization, `if: success()` commit gate, `add_options: '-f'` for the gitignored `state.json`). Documentation (`README.md`, `docs/DEPLOY.md`) accurately reflects the code. Pin discipline is maintained (`==` only).

The one substantive finding is an unused constant (`LOOP_SLEEP_S`) — declared in `system_params.py` and validated in CI but never referenced by the loop driver. The remaining four items are info-level polish suggestions (workflow hardening, README badge UX, weekday-gate test fake mismatch, log-line micro-detail).

No bugs, no security issues, no test regressions. Phase is production-ready.

## Files Reviewed

- `.env.example`
- `.github/workflows/daily.yml`
- `README.md`
- `docs/DEPLOY.md`
- `main.py`
- `requirements.txt`
- `system_params.py`
- `tests/test_main.py`
- `tests/test_scheduler.py`
- `tests/test_signal_engine.py`

---

## Warnings

### WR-01: `LOOP_SLEEP_S` constant declared but never consumed by the loop driver

**File:** `main.py:208`
**Cross-ref:** `system_params.py:130`

**Issue:** `system_params.LOOP_SLEEP_S = 60` is intentionally added in Wave 0 as the canonical tick-budget constant (per CONTEXT/PLAN/PATTERNS docs), but `_run_schedule_loop`'s signature defaults to a magic literal `tick_budget_s: float = 60.0` instead of reading the constant. Production calls (`_run_schedule_loop(run_daily_check, args)` at `main.py:908`) therefore never reach the constant — they get the hard-coded 60.0 default. The two values happen to agree today (60 / 60.0), so behavior is correct, but the constant is dead code by reference and the canonical-source-of-truth contract documented in `07-RESEARCH.md` §"Where to put LOOP_SLEEP_S" is not actually enforced.

If an operator later edits `LOOP_SLEEP_S` (e.g. drops to 30 to reduce idle CPU on Replit), the loop will silently keep ticking at 60 because the constant is bypassed. The CI assertion `assert system_params.LOOP_SLEEP_S == 60` (07-01-PLAN line 303) just verifies the constant's value — it does not verify the loop uses it.

**Fix:** Reference the constant from the default, so the constant is the single source of truth:

```python
def _run_schedule_loop(
  job,
  args,
  scheduler=None,
  sleep_fn=None,
  tick_budget_s: float | None = None,
  max_ticks: int | None = None,
) -> int:
  ...
  _tick_budget = tick_budget_s if tick_budget_s is not None else float(system_params.LOOP_SLEEP_S)
  ...
  _sleep(_tick_budget)
```

Alternative (minimal diff): `tick_budget_s: float = float(system_params.LOOP_SLEEP_S)` as the default. Either form makes the constant load-bearing and lets tests still inject `tick_budget_s=60.0` explicitly without breaking.

---

## Info

### IN-01: GHA job has no `timeout-minutes` cap

**File:** `.github/workflows/daily.yml:15`

**Issue:** The `daily` job inherits GitHub's default 6-hour timeout. `data_fetcher.fetch_ohlcv` retries 3× with 10s backoff on yfinance failures (per `docs/DEPLOY.md` Troubleshooting), so the practical worst case is well under a minute — but a stuck DNS resolution or upstream hang could pin a runner for hours and consume a chunk of the 2000-min/month free-tier budget on private repos. Cost-estimate section in `DEPLOY.md` cites ~21 min/month — a single hung run could exceed that.

**Fix:** Add `timeout-minutes: 10` (generous given the ~60s typical run) to the job under `runs-on: ubuntu-latest`:

```yaml
jobs:
  daily:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      ...
```

### IN-02: README status badge ships with literal `${{GITHUB_REPOSITORY}}` placeholder

**File:** `README.md:3`

**Issue:** The badge URL embeds `${{GITHUB_REPOSITORY}}` as a literal string. GitHub does NOT substitute that placeholder in static markdown (only inside workflows). The Setup section (lines 12-16) explains this, and `docs/DEPLOY.md` step 4 + Troubleshooting both call it out — so it's documented, not a bug. But on a forked repo or a fresh clone the badge renders as broken (404) until the operator does the one-time edit. This is a UX wart for first-time visitors who see a broken badge before they read the Setup section.

**Fix:** Either (a) leave as-is and accept the documented one-time edit, or (b) seed the badge with the canonical owner/repo (`mwiriadi/trading-signals`) so it renders immediately for the canonical repo, with the Setup section then telling forkers to update it. Option (b) trades fork-friction for canonical-repo polish.

### IN-03: `TestWeekdayGate` fake `fetch_ohlcv` returns `None` — would crash `data_fetcher.fetch_ohlcv` callers if the gate ever regressed

**File:** `tests/test_scheduler.py:64-67`

**Issue:** `TestWeekdayGate` patches `data_fetcher.fetch_ohlcv` with `lambda *a, **kw: fetch_calls.append(a) or None`. `list.append` returns `None`, and `None or None` is `None`, so the fake returns `None`. Today this is fine because the weekday gate short-circuits before any fetch happens (the test asserts `fetch_calls == []`). But if the gate ever regresses to NOT short-circuit, the test would fail with a confusing `TypeError: object of type 'NoneType' has no len()` (from `len(df) < _MIN_BARS_REQUIRED` at `main.py:613`) instead of a clean "weekday gate did not fire" assertion. This obscures the regression's root cause.

**Fix:** Make the fake return a deterministic empty/short DataFrame so a regression fails on the explicit `fetch_calls == []` assertion or the explicit `ShortFrameError`, not on a NoneType. Or document the intent inline. Example:

```python
def _no_fetch_expected(*a, **kw):
  fetch_calls.append(a)
  raise AssertionError(
    'weekday gate regression: fetch_ohlcv must NOT be called on weekends'
  )
monkeypatch.setattr(main_module.data_fetcher, 'fetch_ohlcv', _no_fetch_expected)
```

This way a future regression fails immediately and loudly with the exact diagnosis.

### IN-04: `[Sched] scheduler entered` log line uses unicode en-dash `\u2013` rather than ASCII hyphen

**File:** `main.py:242`

**Issue:** The log message `'[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon\u2013Fri'` uses an en-dash (`–`, U+2013). The matching test asserts `'00:00 UTC' in r.message and '08:00 AWST' in r.message` (test_scheduler.py:309-311) — it does NOT assert on the dash, so the test passes either way. But operators grepping logs for ASCII `Mon-Fri` (with a hyphen) will get zero matches. Minor but operationally relevant on a runbook/grep-driven workflow.

**Fix:** Replace `\u2013` with an ASCII hyphen `-`. Doc convention everywhere else in the codebase uses ASCII hyphens for ranges (e.g. `'0 0 * * 1-5'` in the cron line). Two-char change:

```python
logger.info(
  '[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon-Fri'
)
```

---

## Items Verified Clean (from focus areas)

- **Hex boundary intact.** `FORBIDDEN_MODULES` (tests/test_signal_engine.py:488), `FORBIDDEN_MODULES_DASHBOARD` (:556), and `FORBIDDEN_MODULES_NOTIFIER` (:574) all include `'schedule'` and `'dotenv'`. `FORBIDDEN_MODULES_MAIN` (:544) correctly does NOT include them — `main.py` is their sole legitimate consumer. The `import schedule` and `from dotenv import load_dotenv` statements in `main.py` are inside function bodies (not module-top), preserving the never-crash-on-import pattern shared with `_render_dashboard_never_crash` / `_send_email_never_crash`.
- **Pin discipline.** `requirements.txt` uses exact `==` for all 9 deps including the 3 new Phase 7 additions (`PyYAML==6.0.2`, `python-dotenv==1.0.1`, `schedule==1.2.2`). No `>=` or `~=` — matches CLAUDE.md pinning rule.
- **Weekday gate.** `run_daily_check` short-circuits at main.py:565 BEFORE any fetch/compute/state mutation, returning the proper 4-tuple `(0, None, None, run_date)` so `main()`'s dispatch ladder None-guards (lines 894-899) handle it. Applies to ALL invocation modes per the docstring.
- **UTC assertion.** `_run_schedule_loop` asserts at main.py:233 via the patchable `_get_process_tzname()` wrapper; tests patch `main._get_process_tzname` (not `time.tzname`) per the locked Codex MEDIUM fix.
- **Workflow secret handling.** Explicit per-secret env mapping at workflow lines 32-34; no bulk `${{ secrets }}` exposure. `permissions: contents: write` only — no `issues` or `pull-requests`. Test `test_permissions_contents_write` (test_scheduler.py:417) asserts both inclusions and exclusions.
- **Commit-back behavior.** `if: success()` (line 38), `file_pattern: state.json` (line 41), `add_options: '-f'` (line 42) for the gitignored file, canonical bot identity (lines 43-44). `commit_message: '... [skip ci]'` prevents push-trigger CI loops on bot commits.
- **Concurrency.** `group: trading-signals` + `cancel-in-progress: false` (workflow lines 11-12) serialize cron+dispatch overlap without killing in-flight runs.
- **Deprecated log line removal.** `'One-shot mode (scheduler wiring lands in Phase 7)'` is no longer emitted from `run_daily_check`. Multiple tests assert its absence (test_main.py:144, 187; test_scheduler.py:314).
- **`load_dotenv()` bootstrap.** Called inside `main()` at line 872 BEFORE `parse_args`, with default `override=False` so env-var precedence is preserved (correct for GHA where secrets come via the workflow's `env:` block, not a `.env` file in the runner). `TestDotenvLoading` patches and verifies this.
- **Test classes complete.** `TestWeekdayGate` (3), `TestImmediateFirstRun` (1), `TestLoopDriver` (3), `TestLoopErrorHandling` (3), `TestDefaultModeDispatch` (1), `TestDotenvLoading` (1), `TestGHAWorkflow` (12), `TestDeployDocs` (12). Zero `xfail`, zero `pytest.skip`, zero `pytest.importorskip`.
- **YAML static-validation Codex HIGH fix applied.** `test_workflow_parses_as_yaml` computes `on_block = parsed.get('on') or parsed.get(True)` BEFORE indexing (test_scheduler.py:388), tolerating PyYAML 1.1's `on: True` boolean coercion.
- **DEPLOY.md TZ=UTC invariant for default loop mode.** Documented in §"Local development" (DEPLOY.md:91-102) and in the troubleshooting entry "AssertionError: [Sched] process tz must be UTC" (lines 160-164). Test `test_deploy_md_local_dev_tz_note` (test_scheduler.py:594) enforces this.
- **README badge present.** `actions/workflows/daily.yml/badge.svg` substring present at README.md:3, asserted by `test_readme_has_gha_status_badge`.

---

_Reviewed: 2026-04-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
