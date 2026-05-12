---
phase: 31-core-module-split
plan: "01"
subsystem: state_manager
tags: [refactor, package-split, state-management, hexagonal]
dependency_graph:
  requires: []
  provides: [state_manager-package]
  affects: [all callers of state_manager]
tech_stack:
  added: []
  patterns: [package-re-export, monkeypatch-safe-module-globals]
key_files:
  created:
    - state_manager/__init__.py
    - state_manager/io.py
    - state_manager/migrations.py
    - state_manager/validation.py
    - state_manager/trades.py
  modified: []
  deleted:
    - state_manager.py
decisions:
  - "_assert_migration_chain_contiguous defined in __init__.py (not re-exported from migrations) so monkeypatch.setattr(state_manager, 'MIGRATIONS', ...) tests work"
  - "All private symbols re-exported from __init__ for backward test import compat"
  - "Re-exports placed before function definitions so module-global names are patchable in load_state/save_state"
metrics:
  duration: ~35min
  completed: "2026-05-12"
  tasks: 2
  files: 6
---

# Phase 31 Plan 01: State Manager Package Split Summary

Convert `state_manager.py` (1,293 LOC) into `state_manager/` package with five focused daughter files. All existing callers and tests unchanged.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Scaffold package — io.py, validation.py, trades.py | b14b866 | state_manager/__init__.py (stub), io.py, validation.py, trades.py |
| 2 | migrations.py, full __init__.py, delete flat file | e98e985 | state_manager/migrations.py, __init__.py (full), state_manager.py (deleted) |

## Artifacts

| File | LOC | Provides |
|------|-----|---------|
| state_manager/__init__.py | 376 | Public API orchestrator: load_state, save_state, reset_state, mutate_state + all re-exports |
| state_manager/io.py | 244 | I/O kernel: _atomic_write_unlocked, _atomic_write, _backup_corrupt, _save_state_unlocked |
| state_manager/migrations.py | 419 | All _migrate_vX_to_vY, MIGRATIONS, _assert_migration_chain_contiguous, _migrate |
| state_manager/validation.py | 233 | _assert_tz_aware, _coerce_legacy_naive_iso, _validate_trade, _validate_loaded_state, _read_signal_strategy_version |
| state_manager/trades.py | 190 | append_warning, clear_warnings, clear_warnings_by_source, record_trade, update_equity_history |

All files ≤500 LOC. `state_manager.py` deleted.

## Verification

- `pytest -x --tb=short tests/test_state_manager.py tests/test_naive_datetime_fail_closed.py tests/test_migration_contiguity.py`: **128/128 passed**
- `grep "io._save_state_unlocked" state_manager/__init__.py`: 2 matches (in mutate_state body — flock deadlock avoidance preserved)
- `grep "^_assert_migration_chain_contiguous()" state_manager/migrations.py`: 1 match (module-level call at bottom)
- All 5 daughter files ≤500 LOC

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Re-export private symbols for backward test compat**
- **Found during:** Task 2 test run
- **Issue:** `tests/test_state_manager.py` and others import `MIGRATIONS`, `_migrate`, `_migrate_v2_to_v3`, `_read_signal_strategy_version`, `_validate_loaded_state` directly from `state_manager`. The plan only listed public symbols for re-export.
- **Fix:** Added full backward-compat re-exports in `__init__.py` for all private symbols that tests import directly.
- **Files modified:** state_manager/__init__.py
- **Commit:** e98e985

**2. [Rule 1 - Bug] _assert_migration_chain_contiguous must read module globals**
- **Found during:** Task 2 test run (test_migration_contiguity.py)
- **Issue:** `monkeypatch.setattr(state_manager, 'MIGRATIONS', fake_migrations)` patches the `__init__` module namespace but if the function is merely re-exported from `migrations.py`, it still reads `migrations.MIGRATIONS` (the submodule's globals, not the patched ones).
- **Fix:** Defined `_assert_migration_chain_contiguous` directly in `__init__.py` using `globals()['MIGRATIONS']` so monkeypatch intercepts correctly. The `migrations.py` copy still fires at submodule import time as defense-in-depth.
- **Files modified:** state_manager/__init__.py
- **Commit:** e98e985

**3. [Rule 1 - Bug] Re-exports must precede orchestrator function definitions**
- **Found during:** Task 2 — recognizing monkeypatch pattern
- **Issue:** If `_migrate` is re-exported at the bottom of `__init__.py` (after `load_state` is defined), the `load_state` body that calls `_migrate(state)` uses Python's global lookup at call time — but the pattern requires that `_migrate` is in `globals()` when the function is called. Moving re-exports to the top (before function definitions) ensures the global names are always present.
- **Fix:** Restructured `__init__.py` to place all `from state_manager.X import ...` re-exports before the orchestrator function definitions.
- **Files modified:** state_manager/__init__.py
- **Commit:** e98e985

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Pure refactor — same I/O surfaces, same flock semantics, same `io._save_state_unlocked` deadlock-avoidance path preserved.

T-31-01-01 (Tampering — mutate_state flock path): MITIGATED — `io._save_state_unlocked` confirmed in mutate_state body.
T-31-01-02 (Repudiation — module-level contiguity check): MITIGATED — `_assert_migration_chain_contiguous()` at bottom of migrations.py confirmed.

## Known Stubs

None — all functions fully implemented.

## Self-Check: PASSED

- FOUND: state_manager/__init__.py
- FOUND: state_manager/io.py
- FOUND: state_manager/migrations.py
- FOUND: state_manager/validation.py
- FOUND: state_manager/trades.py
- CONFIRMED: state_manager.py deleted
- FOUND commit: b14b866
- FOUND commit: e98e985
- 128/128 tests passed
