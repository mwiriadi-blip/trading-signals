---
phase: 15
plan: "03"
subsystem: state-manager
tags:
  - phase15
  - state-manager
  - drift-warnings
  - sentinel
dependency_graph:
  requires:
    - "15-01 (TestClearWarningsBySource skeleton)"
  provides:
    - "clear_warnings_by_source(state, source) -> dict in state_manager.py"
    - "5 passing TestClearWarningsBySource test methods"
  affects:
    - "Plans 04 and 06 (consumers of clear_warnings_by_source)"
tech_stack:
  added: []
  patterns:
    - "list-comprehension filter on w.get('source') != source (surgical partial-clear)"
    - "in-place mutation with same-dict return for chaining (mirrors clear_warnings)"
key_files:
  created: []
  modified:
    - state_manager.py
    - tests/test_state_manager.py
decisions:
  - "Used state.get('warnings', []) in the filter comprehension to handle missing 'warnings' key gracefully (avoids KeyError, resets to [])"
  - "Local imports inside test methods reference only state_manager symbols; UTC/datetime come from module-level imports already in scope — eliminates F811 redefinition warnings"
  - "Import names one-per-line inside from-import parens to satisfy ruff I001 sort rule"
metrics:
  duration: "~20 minutes"
  completed: "2026-04-26T02:32:29Z"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 2
---

# Phase 15 Plan 03: clear_warnings_by_source — Summary

**One-liner:** Surgical partial-clear helper `clear_warnings_by_source(state, source)` added to `state_manager.py` alongside existing `clear_warnings`; 5 `TestClearWarningsBySource` methods populated and passing.

## What Was Built

### `state_manager.py` — `clear_warnings_by_source` (lines 646–666)

Inserted immediately after `clear_warnings` (line 644). Implementation:

```python
def clear_warnings_by_source(state: dict, source: str) -> dict:
  state['warnings'] = [
    w for w in state.get('warnings', [])
    if w.get('source') != source
  ]
  return state
```

- Pure dict operation — no I/O, no lock acquisition
- Caller wraps in `mutate_state` for persistence atomicity
- Returns same `state` dict reference for chaining (mirrors `clear_warnings` contract)
- `state.get('warnings', [])` handles missing key gracefully (resets to `[]`)
- D-10 sole-writer invariant preserved: only `state_manager` mutates `state['warnings']`

### `tests/test_state_manager.py` — `TestClearWarningsBySource` (lines 1382–1444)

All 5 skipped methods from the Plan 01 Wave 0 skeleton replaced with full test bodies:

| Method | What it proves |
|--------|---------------|
| `test_removes_matching_source` | drift warnings removed; sizing_engine warning kept |
| `test_leaves_other_sources_intact` | clearing non-existent source leaves all 3 others intact |
| `test_idempotent_on_no_match` | double-call on no-match produces identical list |
| `test_returns_same_state_reference` | `result is state` (in-place chaining contract) |
| `test_handles_missing_warnings_key` | empty dict → no KeyError; sets `warnings = []` |

## Verification Results

```
pytest tests/test_state_manager.py::TestClearWarningsBySource tests/test_state_manager.py::TestClearWarnings -x -q
9 passed in 0.06s  (5 new + 4 existing Phase 8)
```

All acceptance criteria passed:
- `grep -c "^def clear_warnings_by_source" state_manager.py` → 1
- `grep -c "^def clear_warnings" state_manager.py` → 2
- Identity + empty-list smoke test → OK
- Source-filter smoke test → OK
- ruff: no new errors introduced in modified lines

## Sole-Writer Invariant Preservation

`clear_warnings_by_source` lives inside `state_manager.py` — the only module permitted to mutate `state['warnings']`. No direct `state['warnings'].append(...)` or `state['warnings'] = ...` calls were added anywhere else. Pitfall 8 (D-02 full-clear vs partial-clear confusion) is documented in the function docstring.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] F811 redefinition + UP017 timezone alias in test methods**
- **Found during:** ruff check after initial test method implementation
- **Issue:** Test methods imported `from datetime import datetime, timezone` locally, redeclaring `timezone` already imported at module level (F811) and using `timezone.utc` instead of `UTC` alias (UP017)
- **Fix:** Dropped local `timezone` import; used module-level `UTC` constant directly in all three datetime-using test methods
- **Files modified:** `tests/test_state_manager.py`
- **Commit:** 67b1f58 (same task commit)

**2. [Rule 1 - Bug] I001 import-sort in new test methods**
- **Found during:** ruff check after F811/UP017 fix
- **Issue:** Multi-name `from state_manager import (append_warning, clear_warnings_by_source, reset_state,)` on one line failed ruff I001 sort check
- **Fix:** Split each imported name onto its own line inside the parenthesised block
- **Files modified:** `tests/test_state_manager.py`
- **Commit:** 67b1f58 (same task commit)

**Pre-existing ruff issues (out of scope, not touched):**
- `state_manager.py:56 I001` — pre-existing module-level import sort
- `state_manager.py:69 UP035` — pre-existing `typing.Callable` vs `collections.abc`
- `tests/test_state_manager.py:16 I001` — pre-existing module-level import sort
- `tests/test_state_manager.py:1468 I001/E401` — pre-existing `import fcntl, os, time` in `TestFcntlLock`

These were present before Plan 03 and are logged to `deferred-items.md`.

## Known Stubs

None. The function is fully implemented and all test method bodies are complete.

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes introduced. `clear_warnings_by_source` is a pure in-memory dict operation.

## Self-Check: PASSED

- `state_manager.py` contains `def clear_warnings_by_source` at line 646: FOUND
- `tests/test_state_manager.py` contains 5 passing test methods (no `pytest.skip`): FOUND
- Commit `67b1f58` exists: FOUND
- `pytest TestClearWarningsBySource TestClearWarnings` → 9 passed: VERIFIED
