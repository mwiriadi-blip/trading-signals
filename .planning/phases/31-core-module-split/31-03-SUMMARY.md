---
plan: 31-03
phase: 31-core-module-split
status: complete
tasks_completed: 1
files_modified:
  - tests/test_signal_engine.py
  - tests/test_entry_side_cost.py
  - tests/test_warnings_fifo.py
key_commits:
  - "2e0a5cc: fix(31-03): update AST gate tests for state_manager + sizing_engine packages"
---

## Summary

Wave 2 integration verification — all structural invariants confirmed, three AST gate tests updated for the new package layout.

## Checks Passed

| Check | Result |
|-------|--------|
| Full pytest suite | 2084 passed, 13 deselected |
| `test_forbidden_imports_absent` | PASS |
| All 11 daughter files ≤500 LOC | PASS (max: migrations.py 419 LOC) |
| Caller import resolution (state_manager + sizing_engine) | PASS |
| `state_manager.py` deleted | CONFIRMED |
| `sizing_engine.py` deleted | CONFIRMED |
| `io._save_state_unlocked` in `mutate_state` | 1 match |
| `_assert_migration_chain_contiguous()` at bottom of migrations.py | 1 match |
| Hex boundary (no I/O imports in sizing_engine daughters) | PASS |

## Test Fixes Required (Post-Merge)

Three test files referenced the old flat-file paths and needed updates:

**`tests/test_entry_side_cost.py`** (committed before Wave 2):
- Added `_sizing_engine_pkg_files()` helper to glob `sizing_engine/*.py`
- Replaced `'sizing_engine.py'` in `PROD_FILES` with `*_sizing_engine_pkg_files()`

**`tests/test_signal_engine.py`**:
- `SIZING_ENGINE_PATH` → `SIZING_ENGINE_PKG_FILES = sorted(Path('sizing_engine').glob('*.py'))`
- `STATE_MANAGER_PATH` → `STATE_MANAGER_PKG_FILES = sorted(Path('state_manager').glob('*.py'))`
- Expanded `_HEX_PATHS_ALL`, `_HEX_PATHS_STDLIB_ONLY`, parametrize decorator, and indent `covered_paths` to splat the new lists

**`tests/test_warnings_fifo.py`**:
- `test_state_manager_imports_max_warnings`: now iterates all `state_manager/*.py` files for AST walk
- `test_no_hardcoded_warnings_bound_literal_in_state_manager`: now concatenates all package files before regex search for `def append_warning`

## Self-Check: PASSED

- `pytest -x --tb=short` → 2084 passed
- All 11 daughter files ≤500 LOC
- Both flat files deleted
- All caller imports verified
- Hex boundary intact
