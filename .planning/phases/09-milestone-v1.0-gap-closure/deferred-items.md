# Phase 9 — Deferred Items

Out-of-scope pre-existing issues discovered during Plan 09-01 execution. Not caused by Phase 9 changes; deferred per executor scope-boundary rule.

## Pre-existing ruff F401 warnings in notifier.py (19 errors, 17 auto-fixable)

Confirmed pre-existing via `git stash` comparison before Phase 9 edits. Unused imports from `system_params` in `notifier.py`:

- `AUDUSD_COST_AUD`, `AUDUSD_NOTIONAL`, `SPI_COST_AUD`, `SPI_MULT`, `TRAIL_MULT_LONG` (and ~12 more)

These lint warnings predate Phase 9 (likely introduced during Phase 8 `CONF-02` contract-tier refactor — the imports became unused when the `FALLBACK_CONTRACT_SPECS` dict replaced direct constant reads). They do not affect runtime behaviour (F401 = import unused, not name error).

**Fix path:** A tiny `chore(quick)` task can run `ruff check --fix notifier.py` and commit. Phase 9 scope is doc/config/test-only reconciliation; fixing notifier.py imports is out of scope.

**Files affected:** `notifier.py` (single file).

**Risk:** None. F401 auto-fix only removes `from X import Y` lines where `Y` is unreferenced — no behaviour change.
