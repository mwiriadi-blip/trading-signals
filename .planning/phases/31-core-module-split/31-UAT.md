---
status: complete
phase: 31-core-module-split
source:
  - .planning/phases/31-core-module-split/31-01-SUMMARY.md
  - .planning/phases/31-core-module-split/31-02-SUMMARY.md
  - .planning/phases/31-core-module-split/31-03-SUMMARY.md
started: "2026-05-12T12:15:00.000Z"
updated: "2026-05-12T12:15:00.000Z"
---

## Current Test

[testing complete]

## Tests

### 1. state_manager package exists, flat file deleted
expected: state_manager/ package with 5 daughter files (≤500 LOC each); state_manager.py deleted
result: pass

### 2. sizing_engine package exists, flat file deleted
expected: sizing_engine/ package with 6 daughter files (≤500 LOC each); sizing_engine.py deleted
result: pass

### 3. Caller imports resolve unchanged
expected: `from state_manager import load_state, save_state, reset_state, mutate_state, append_warning, clear_warnings, clear_warnings_by_source, record_trade, update_equity_history` all resolve; same for sizing_engine public API
result: pass

### 4. Hex boundary intact
expected: No I/O imports (state_manager, notifier, os, requests) in sizing_engine daughter files
result: pass

### 5. Deadlock guard preserved
expected: mutate_state calls io._save_state_unlocked directly (not save_state) — flock re-acquisition avoidance
result: pass

### 6. Migration contiguity check fires on import
expected: `_assert_migration_chain_contiguous()` at module level in migrations.py
result: pass

### 7. Full test suite green
expected: pytest -x --tb=short exits 0 with 2084+ tests passing (state_manager, sizing_engine, signal_engine::TestDeterminism::test_forbidden_imports_absent all pass)
result: pass

### 8. AST gate tests updated for package layout
expected: test_signal_engine.py, test_entry_side_cost.py, test_warnings_fifo.py all walk package directories (not deleted flat files)
result: pass

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
