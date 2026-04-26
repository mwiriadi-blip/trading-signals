---
phase: 15
plan: 02
subsystem: sizing-engine
tags:
  - phase15
  - pure-math
  - drift-detection
  - sizing-engine
  - SENTINEL-01
  - SENTINEL-02

dependency_graph:
  requires:
    - 15-01 (TestDetectDrift skeleton in tests/test_sizing_engine.py)
    - sizing_engine.py (existing dataclass + import block)
  provides:
    - sizing_engine.DriftEvent (frozen+slots dataclass, D-01 contract)
    - sizing_engine.detect_drift (pure-math function, D-04 + D-14 templates)
    - tests/test_sizing_engine.py::TestDetectDrift (12 passing methods)
  affects:
    - 15-04 (main.py calls detect_drift — data contract now locked)
    - 15-06 (web/routes/trades.py calls detect_drift post-mutation)
    - 15-05 + 15-07 (dashboard.py + notifier.py render drift from state['warnings'])

tech_stack:
  added: []
  patterns:
    - frozen+slots dataclass (Phase 2 D-09 convention — DriftEvent follows SizingDecision/PyramidDecision/ClosedTrade/StepResult)
    - conservative-skip pattern (D-04: missing/None/unrecognised signal data returns no event)
    - backward-compat int-shape signals (Pitfall 3: reset_state() produces bare ints)

key_files:
  modified:
    - path: sizing_engine.py
      lines_inserted: '97-188 (DriftEvent class 97-114; detect_drift function 115-188)'
      description: 'DriftEvent frozen+slots dataclass + detect_drift pure-math function'
    - path: tests/test_sizing_engine.py
      lines_replaced: '1377-1424 (TestDetectDrift class bodies)'
      description: '12 pytest.skip stubs replaced with real test logic'

decisions:
  - 'DriftEvent placed immediately after StepResult dataclass (line 95) and before _vol_scale private helper — maintains existing dataclass block convention'
  - 'detect_drift iterates fixed tuple ("SPI200", "AUDUSD") — deterministic ordering for list output, matches test_two_instruments_both_drift assertion'
  - 'D-14 reversal message uses f-string continuation across two lines to stay within 100-char ruff limit'
  - 'Docstring reversal template line wrapped at 100 chars (E501 fix) — does not affect the actual runtime string'
  - 'Pre-existing ruff E501 violations at lines 1343/1346 of test_sizing_engine.py (TestStepProducesV3Schema) left untouched — out of scope for this plan'

metrics:
  duration: '~15 minutes'
  completed_date: '2026-04-26T02:32:52Z'
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
  commits: 2
---

# Phase 15 Plan 02: DriftEvent + detect_drift — Summary

Pure-math drift detector added to `sizing_engine.py`. `DriftEvent` frozen+slots dataclass and `detect_drift(positions, signals) -> list[DriftEvent]` function ship together as a locked data contract for the rest of Phase 15.

## What Was Built

**Task 1 — `DriftEvent` dataclass + `detect_drift` in `sizing_engine.py` (commit `ae2cda8`)**

- `DriftEvent` inserted at lines 97–114 following the Phase 2 D-09 `@dataclasses.dataclass(frozen=True, slots=True)` convention. Fields: `instrument`, `held_direction`, `signal_direction`, `severity`, `message`.
- `detect_drift` inserted at lines 115–188. Iterates over `('SPI200', 'AUDUSD')` in fixed order. Implements:
  - D-04 conservative skip: `None` position, missing signal key, `None` signal value, or unrecognised shape → no event
  - Pitfall 3 backward-compat: bare `int` signal (from `reset_state()`) handled alongside `dict`-shape signals
  - T-15-02-03 defensive skip: unknown int values (e.g., `2`, `-2`) skipped via `dict.get()` returning `None`
  - D-14 exact message templates for `severity='drift'` and `severity='reversal'`
- No new module-level imports added. `dataclasses` was already imported. `FLAT`, `LONG`, `SHORT` already imported from `signal_engine`.
- `ruff check sizing_engine.py` → All checks passed.

**Task 2 — Populate `TestDetectDrift` method bodies (commit `241e79a`)**

All 12 `pytest.skip` stubs in `tests/test_sizing_engine.py::TestDetectDrift` replaced with real test logic:

| Method | What it tests |
|--------|---------------|
| `test_drift_long_vs_flat` | LONG position + FLAT signal → severity='drift' |
| `test_drift_short_vs_flat` | SHORT position + FLAT signal → severity='drift', instrument='AUDUSD' |
| `test_reversal_long_vs_short` | LONG position + SHORT signal → severity='reversal' |
| `test_reversal_short_vs_long` | SHORT position + LONG signal → severity='reversal' |
| `test_no_event_when_position_flat` | Empty positions dict → [] |
| `test_no_event_when_signal_missing` | Missing signal key → D-04 skip → [] |
| `test_no_event_when_signal_dict_signal_is_none` | `{'signal': None}` → D-04 skip → [] |
| `test_signal_int_shape_compat` | Bare `int` signal=0 → Pitfall 3 compat → drift event |
| `test_drift_event_message_long_vs_flat_exact` | D-14 drift template byte-for-byte equality |
| `test_drift_event_message_reversal_long_to_short_exact` | D-14 reversal template byte-for-byte equality |
| `test_two_instruments_both_drift` | 2 instruments, both drifted → list length 2, correct severities |
| `test_returns_empty_list_when_no_positions` | Degenerate `{}` positions → [] |

Result: `pytest tests/test_sizing_engine.py::TestDetectDrift -x -q` → **12 passed, 0 skipped, 0 failed**.

## Acceptance Criteria Status

| Check | Result |
|-------|--------|
| `grep -c "^class DriftEvent" sizing_engine.py` | 1 |
| `grep -c "^def detect_drift" sizing_engine.py` | 1 |
| `@dataclasses.dataclass(frozen=True, slots=True)` count increased by 1 | 5 total (was 4) |
| `from sizing_engine import DriftEvent, detect_drift` exits 0 | PASS |
| `detect_drift({}, {}) == []` | PASS |
| Frozen instance raises `FrozenInstanceError` on assignment | PASS |
| `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` | PASS (3 passed) |
| D-14 drift template string present | PASS |
| D-14 reversal template string present | PASS |
| All 12 `TestDetectDrift` methods pass | PASS |

## Deviations from Plan

**1. [Rule 3 - Blocking] `git stash` / `git stash pop` reverted Task 2 edit**

- **Found during:** Task 2 commit staging
- **Issue:** Used `git stash` to test a pre-existing failure (`test_force_email_sends_live_email`). The stash pop restored `state_manager.py` and `tests/test_state_manager.py` from another parallel worktree's stash entry, but did NOT restore `tests/test_sizing_engine.py` (the test showed no diff after pop). The Task 2 edit was silently lost.
- **Fix:** Re-read the file (confirmed old stubs still present), re-applied the identical edit, ran tests to confirm 12 passed, committed with `git add tests/test_sizing_engine.py` only (leaving `state_manager.py` and `tests/test_state_manager.py` unstaged — those belong to plan 15-03).
- **Files modified:** `tests/test_sizing_engine.py` (re-applied same edit)
- **Commits:** `241e79a`

**2. [Rule 1 - Bug] Docstring E501 line in `detect_drift`**

- **Found during:** Task 1 ruff check
- **Issue:** The D-14 reversal template docstring line was 130 chars, exceeding the 100-char ruff limit.
- **Fix:** Wrapped the docstring line at 100 chars. Runtime string (in the f-string) was unaffected.
- **Files modified:** `sizing_engine.py`
- **Commit:** `ae2cda8` (fixed before commit)

## Known Stubs

None — both `DriftEvent` and `detect_drift` are fully implemented. No placeholder text or hardcoded empty values.

## Threat Flags

No new threat surface beyond what is documented in the plan's `<threat_model>`. `detect_drift` is pure-math with no network endpoints, no auth surface, no I/O. All threat dispositions from T-15-02-01 through T-15-02-04 are handled as specified.

## Hex Boundary Confirmation

`pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x -q` → **3 passed**. No new imports added to `sizing_engine.py` module-level scope. `dataclasses` was already present; `FLAT`, `LONG`, `SHORT` were already imported from `signal_engine`.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `sizing_engine.py` exists | FOUND |
| `tests/test_sizing_engine.py` exists | FOUND |
| `15-02-SUMMARY.md` exists | FOUND |
| Commit `ae2cda8` (Task 1) | FOUND |
| Commit `241e79a` (Task 2) | FOUND |
