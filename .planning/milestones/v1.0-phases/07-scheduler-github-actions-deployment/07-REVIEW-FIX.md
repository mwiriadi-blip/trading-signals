---
phase: 07
fixed_at: 2026-04-23
review_path: .planning/phases/07-scheduler-github-actions-deployment/07-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 7: Code Review Fix Report

**Fixed at:** 2026-04-23
**Source review:** `.planning/phases/07-scheduler-github-actions-deployment/07-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 1
- Fixed: 1
- Skipped: 0
- Out of scope (Info, excluded by `fix_scope: critical_warning`): 4

## Fixed Issues

### WR-01: `LOOP_SLEEP_S` constant declared but never consumed by the loop driver

**Files modified:** `main.py`
**Commit:** `e271156`
**Applied fix:** Changed the default value of `_run_schedule_loop`'s `tick_budget_s` parameter from the magic literal `60.0` to `float(system_params.LOOP_SLEEP_S)` (main.py:208). This makes `system_params.LOOP_SLEEP_S` the single source of truth — production calls (`_run_schedule_loop(run_daily_check, args)`) now flow through the constant, so an operator editing `LOOP_SLEEP_S` in `system_params.py` actually changes the loop tick cadence. Public signature preserved: existing tests that explicitly pass `tick_budget_s=60.0` continue to work unchanged.

**Verification:**
- Tier 1 (re-read): change present at main.py:208, surrounding loop body intact.
- Tier 2 (Python AST parse): `main.py` parses cleanly.
- Tier 2 (ruff): `ruff check main.py system_params.py` — all checks passed.
- Full test suite: `python -m pytest -q` → 552 passed, 0 failed in 23.78s (matches pre-fix baseline; no regressions).

**Note on default-arg evaluation timing:** Python evaluates default arguments once at function definition time (module load), not on each call. Because `system_params.LOOP_SLEEP_S` is a module-level constant set at import, this is semantically equivalent to "read the constant at module load." If a future operator wants per-call rebinding (e.g. monkey-patching `LOOP_SLEEP_S` mid-test), the alternative form from the REVIEW (`tick_budget_s: float | None = None` with internal `_tick_budget = ... if tick_budget_s is not None else float(system_params.LOOP_SLEEP_S)`) would be needed. The minimal-diff form was chosen per orchestrator guidance — it satisfies the canonical-source-of-truth contract for the realistic edit case (operator changes the constant and restarts the process).

## Skipped Issues

_(None — all 1 in-scope finding was fixed.)_

## Out-of-Scope Findings (Info — excluded by `fix_scope: critical_warning`)

The following Info-level findings were intentionally NOT addressed in this iteration. They are tracked here for visibility; they may be picked up in a follow-up `fix_scope: all` pass or as ad-hoc polish.

### IN-01: GHA job has no `timeout-minutes` cap

**File:** `.github/workflows/daily.yml:15`
**Reason:** `out_of_scope` (Info severity, `fix_scope: critical_warning`)
**Original issue:** The `daily` job inherits GitHub's default 6-hour timeout; a stuck DNS or upstream hang could pin a runner and consume free-tier minutes. Suggested fix: add `timeout-minutes: 10`.

### IN-02: README status badge ships with literal `${{GITHUB_REPOSITORY}}` placeholder

**File:** `README.md:3`
**Reason:** `out_of_scope` (Info severity, `fix_scope: critical_warning`)
**Original issue:** Badge URL embeds an unsubstituted placeholder; renders as a broken 404 on fresh clones until the operator does the documented one-time edit. Suggested fix: seed with canonical owner/repo string.

### IN-03: `TestWeekdayGate` fake `fetch_ohlcv` returns `None`

**File:** `tests/test_scheduler.py:64-67`
**Reason:** `out_of_scope` (Info severity, `fix_scope: critical_warning`)
**Original issue:** Fake `lambda *a, **kw: fetch_calls.append(a) or None` returns `None`; if the weekday gate ever regresses, the test would fail with a confusing `TypeError` from `len(None)` rather than a clean diagnostic. Suggested fix: raise `AssertionError` from the fake to fail loudly with the regression's root cause.

### IN-04: `[Sched] scheduler entered` log line uses unicode en-dash `\u2013`

**File:** `main.py:242`
**Reason:** `out_of_scope` (Info severity, `fix_scope: critical_warning`)
**Original issue:** Log message contains `Mon\u2013Fri` (en-dash); operators grepping for ASCII `Mon-Fri` get zero matches. Suggested fix: two-char change to ASCII hyphen for grep-friendliness.

---

_Fixed: 2026-04-23_
_Fixer: Claude (gsd-code-fixer, Opus 4.7 1M)_
_Iteration: 1_
