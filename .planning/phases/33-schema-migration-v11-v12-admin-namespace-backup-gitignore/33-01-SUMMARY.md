---
phase: 33-schema-migration-v11-v12-admin-namespace-backup-gitignore
plan: "01"
subsystem: state_manager
tags: [migration, schema, tenant, v12, pydantic]
dependency_graph:
  requires: []
  provides: [v12-state-shape, _migrate_v11_to_v12, StateV12, _ADMIN_UID, reset_state-v12]
  affects: [daily_run, paper_trade_alerts, notifier, web, backtest]
tech_stack:
  added: [pydantic BaseModel for StateV12 shape validation]
  patterns: [idempotent dict-to-dict migration, per-user state bucket, shutil.copy2 pre-migration backup]
key_files:
  created:
    - tests/subprocess_helpers_v12.py
  modified:
    - system_params.py
    - state_manager/migrations.py
    - state_manager/validation.py
    - state_manager/__init__.py
    - state_manager/trades.py
    - daily_run.py
    - paper_trade_alerts.py
    - tests/test_state_manager.py
    - tests/test_system_params.py
    - tests/test_signal_shape_migration.py
    - tests/test_main.py
    - tests/test_main_alerts.py
    - tests/test_integration_f1.py
    - tests/test_decimal_money_math.py
    - tests/test_naive_datetime_fail_closed.py
decisions:
  - "Use idempotent guard ('if users in out: return out') to make _migrate_v11_to_v12 safe to call multiple times"
  - "StateV12 uses extra='allow' for forward compatibility with unknown top-level keys"
  - "Backup via shutil.copy2 before migration (schema_version < 12 guard); no-op for already-migrated state"
  - "_ADMIN_UID locked to 'u_admin_marc' — Phase 34 makes dynamic per TENANT-01"
  - "Use spawn + worktree-only subprocess_helpers_v12.py to avoid multiprocessing resolving main-repo test module with mismatched signature"
metrics:
  duration: "~3 hours (multi-session)"
  completed: "2026-05-13"
  tasks_completed: 4
  files_changed: 15
---

# Phase 33 Plan 01: v11->v12 State Schema Migration Summary

**One-liner:** Moves 7 per-user keys into `state['users']['u_admin_marc']` user bucket with idempotent migration, Pydantic StateV12 validation, shutil.copy2 pre-migration backup, and v12-shaped reset_state().

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Bump STATE_SCHEMA_VERSION=12, add _migrate_v11_to_v12, MIGRATIONS[12] | 7a6eb52 |
| 2 | validation.py: _REQUIRED_STATE_KEYS v12, StateV12 model, per-user naive-iso scan | f1dc8f1 |
| 3 | __init__.py backup+validate, reset_state() v12, trades.py user-bucket reads | 43f416f |
| 4 (deviation) | daily_run.py + paper_trade_alerts.py v12 user-bucket wiring | ac9fcf5 |
| 5 (test fixes) | Downstream test updates for v12 shape across 5 test files | 6180a01 |

## What Was Built

**Core migration (`state_manager/migrations.py`):**
- `_ADMIN_UID = 'u_admin_marc'` — locked constant
- `_migrate_v11_to_v12`: moves `account`, `initial_account`, `contracts`, `positions`, `trade_log`, `equity_history`, `paper_trades` from top-level into `state['users']['u_admin_marc']`; adds `ui_prefs: {'tour_completed': True}`; sets `admin_user_id`
- Idempotency guard: `if 'users' in out: return out`
- `MIGRATIONS[12] = _migrate_v11_to_v12`; chain 1..12 contiguous

**Validation (`state_manager/validation.py`):**
- `_REQUIRED_STATE_KEYS` updated to v12 set: `{'schema_version', 'last_run', 'signals', 'markets', 'strategy_settings', 'warnings', 'admin_user_id', 'users'}`
- `StateV12(BaseModel)` with `extra='allow'` for post-migration shape validation
- `_coerce_legacy_naive_iso` scans `state['users'][uid]['equity_history']` (not top-level)

**Load/Init (`state_manager/__init__.py`):**
- `load_state()`: `shutil.copy2` backup before `_migrate()` when `schema_version < 12`
- `StateV12.model_validate(state)` after migration
- `reset_state()` emits v12 shape with `users` bucket and `admin_user_id`
- Re-exports `_ADMIN_UID`, `_migrate_v11_to_v12`, `StateV12`

**Trades (`state_manager/trades.py`):**
- `_admin_user(state)` helper with pre-v12 fallback
- `record_trade` and `update_equity_history` read/write via user bucket

## Deviations from Plan

### Auto-fixed Issues (Rule 3 — Blocking)

**1. [Rule 3 - Blocking] daily_run.py accessed stale top-level per-user keys**
- **Found during:** Task 3 (running tests after __init__.py changes)
- **Issue:** `daily_run.py` read `state['positions']`, `state['account']` etc. directly — all moved to user bucket in v12. Caused 55+ test failures.
- **Fix:** Added `_ADMIN_UID` + `_user` locals after `load_state()`. Updated all per-user key accesses. Rewrote `_apply_daily_run` closure to replay to user bucket.
- **Files modified:** `daily_run.py`
- **Commit:** ac9fcf5

**2. [Rule 3 - Blocking] paper_trade_alerts.py accessed stale top-level paper_trades**
- **Found during:** Task 3 (same test run)
- **Issue:** `_evaluate_paper_trade_alerts_impl` iterated `state.get('paper_trades', [])` — moved to user bucket.
- **Fix:** Added `_uid`/`_user` locals with pre-v12 fallback. Updated `_apply_alert_states` closure.
- **Files modified:** `paper_trade_alerts.py`
- **Commit:** ac9fcf5

**3. [Rule 3 - Blocking] multiprocessing spawn resolves test_state_manager from main-repo tests/**
- **Found during:** test_concurrent_writers_no_lost_update failing in full suite
- **Issue:** pytest adds main-repo `tests/` to `sys.path` with higher priority. Subprocess spawn serializes function by module+qualname, then reimports test_state_manager from main-repo (5-param signature vs 6-param worktree version). Using fork caused deadlocks in multi-threaded pytest on Python 3.13.
- **Fix:** Created `tests/subprocess_helpers_v12.py` (worktree-only; no equivalent in main-repo tests/) as the spawn target. Subprocess inserts `proj_root` at position 0 in `sys.path` unconditionally.
- **Files modified:** `tests/subprocess_helpers_v12.py` (new), `tests/test_state_manager.py`
- **Commit:** 7a6eb52

## Known Stubs

None — all v12 per-user key accesses are wired to real data.

## Test Results

**Final:** 2095 passed, 0 failed, 13 deselected

All 5 `TestMigrateV11ToV12` tests pass. All 2 `TestV12ValidationBehavior` tests pass. All 4 `TestV12InitBehavior` tests pass. W3 invariant preserved (2 `mutate_state` calls per run). Integration test F1 passes with v12 seed.

## Self-Check: PASSED

All committed files verified present. All 5 commit hashes confirmed in git log.
