---
phase: 43-codebase-improvement-sweep
plan: 03
subsystem: system_params / state / notifier / dashboard
tags: [decimal, money, type-safety, CLAUDE.md]
requires: []
provides: [INITIAL_ACCOUNT-is-Decimal]
affects: [system_params.py, interactive.py, dashboard_renderer/stats.py, notifier/templates_sections.py]
tech-stack:
  added: []
  patterns: [Decimal(str(x)) coercion at I/O boundary]
key-files:
  created: [tests/test_system_params.py (TestInitialAccount class)]
  modified:
    - system_params.py
    - interactive.py
    - dashboard_renderer/stats.py
    - notifier/templates_sections.py
    - tests/test_system_params.py
    - tests/test_state_manager.py
decisions:
  - "Coerce equity/initial to Decimal at arithmetic sites rather than changing state_manager wire format (float stays on disk for JSON compat)"
  - "Test seeds use float(INITIAL_ACCOUNT) to match state_manager's float-on-disk contract"
metrics:
  duration: ~8 minutes
  completed: 2026-05-16
  tasks: 1
  files: 6
---

# Phase 43 Plan 03: INITIAL_ACCOUNT Decimal Type Fix Summary

**One-liner:** Typed `INITIAL_ACCOUNT` as `Decimal('10000.00')` and fixed all downstream float/Decimal mixed-arithmetic sites.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Fix INITIAL_ACCOUNT type + downstream arithmetic + tests | 080d309 | system_params.py, interactive.py, dashboard_renderer/stats.py, notifier/templates_sections.py, tests/test_system_params.py, tests/test_state_manager.py |

## What Was Done

**system_params.py (line 282):** Changed `INITIAL_ACCOUNT: float = 10_000.0` to `INITIAL_ACCOUNT: Decimal = Decimal('10000.00')`. `Decimal` was already imported at line 18.

**interactive.py:** Added `from decimal import Decimal`. Changed both `fresh_state['initial_account']` and `fresh_state['account']` casts from `float(initial_account)` to `Decimal(str(initial_account))`. The `initial_account` variable itself remains float throughout (argparse provides float; `math.isfinite` requires float) — only the state write is Decimal.

**dashboard_renderer/stats.py:** Added `from decimal import Decimal`. In `compute_total_return`, coerced both `initial` and `current` to `Decimal(str(...))` before division to fix float/Decimal mixed-arithmetic `TypeError`.

**notifier/templates_sections.py:** Added local `from decimal import Decimal` inside `_render_todays_pnl_email`. Coerced `equity` to `Decimal(str(equity))` before the `since_inception_frac` calculation.

**tests/test_system_params.py:** Added `from decimal import Decimal` import and new `TestInitialAccount` class with two tests: `test_initial_account_is_decimal` and `test_initial_account_value`.

**tests/test_state_manager.py:** Updated all dict seeds that place `INITIAL_ACCOUNT` into dicts later serialized with plain `json.dumps` to use `float(INITIAL_ACCOUNT)`. Arithmetic test comparisons similarly updated. Assertions like `user['account'] == INITIAL_ACCOUNT` left unchanged (Python float == Decimal comparison works correctly).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Float/Decimal arithmetic TypeError in dashboard_renderer/stats.py**
- **Found during:** Running full test suite after primary fix
- **Issue:** `compute_total_return` mixed float `current`/`initial` with Decimal `INITIAL_ACCOUNT` after the type change
- **Fix:** `dashboard_renderer/stats.py` — coerce both values to `Decimal(str(...))` before arithmetic
- **Files modified:** `dashboard_renderer/stats.py`
- **Commit:** 080d309

**2. [Rule 1 - Bug] Float/Decimal arithmetic TypeError in notifier/templates_sections.py**
- **Found during:** Running full test suite
- **Issue:** `_render_todays_pnl_email` computed `(equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT` with float `equity` and Decimal `INITIAL_ACCOUNT`
- **Fix:** `notifier/templates_sections.py` — coerce `equity` to `Decimal(str(equity))` before division
- **Files modified:** `notifier/templates_sections.py`
- **Commit:** 080d309

**3. [Rule 1 - Bug] JSON serialization TypeError in test_state_manager.py**
- **Found during:** Running full test suite
- **Issue:** Many test state seeds placed raw `INITIAL_ACCOUNT` into dicts serialized via plain `json.dumps` (without `_decimal_default` hook). Now that `INITIAL_ACCOUNT` is `Decimal`, these raised `TypeError: Object of type Decimal is not JSON serializable`
- **Fix:** `tests/test_state_manager.py` — replaced all dict-seed occurrences with `float(INITIAL_ACCOUNT)` to match state_manager's float-on-wire contract
- **Files modified:** `tests/test_state_manager.py`
- **Commit:** 080d309

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- system_params.py: INITIAL_ACCOUNT is `Decimal('10000.00')` ✓
- interactive.py: Decimal import present; state writes use `Decimal(str(...))` ✓
- tests/test_system_params.py: `TestInitialAccount` class with 2 tests ✓
- Commit 080d309 exists ✓
- Full test suite: 2415 passed, 1 skipped, 1 xfailed, 3 xpassed ✓
