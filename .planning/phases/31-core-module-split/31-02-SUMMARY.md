---
plan: 31-02
phase: 31-core-module-split
status: complete
tasks_completed: 2
files_created:
  - sizing_engine/__init__.py
  - sizing_engine/_models.py
  - sizing_engine/sizing.py
  - sizing_engine/stops.py
  - sizing_engine/pyramid.py
  - sizing_engine/close.py
files_deleted:
  - sizing_engine.py
key_commits:
  - "0f27543: feat(31-02): scaffold sizing_engine package — five daughter files + stub __init__.py"
  - "b058c73: feat(31-02): complete sizing_engine package — step() orchestrator + delete flat file"
---

## Summary

`sizing_engine.py` (820 LOC) split into a `sizing_engine/` package with six focused daughter files.

| File | LOC | Responsibility |
|------|-----|----------------|
| `sizing_engine/__init__.py` | 286 | `step()` orchestrator + all public re-exports |
| `sizing_engine/_models.py` | 87 | Dataclasses: SizingDecision, PyramidDecision, ClosedTrade, StepResult, DriftEvent |
| `sizing_engine/sizing.py` | 167 | `_vol_scale`, `calc_position_size`, `compute_unrealised_pnl` |
| `sizing_engine/stops.py` | 178 | `get_trailing_stop`, `check_stop_hit` |
| `sizing_engine/pyramid.py` | 146 | `detect_drift`, `check_pyramid` |
| `sizing_engine/close.py` | 71 | `_close_position` |

## What Was Built

**Task 1:** Scaffolded `sizing_engine/` directory with five daughter files (`_models.py`, `sizing.py`, `stops.py`, `pyramid.py`, `close.py`) plus stub `__init__.py`. All functions moved verbatim from the flat file.

**Task 2:** Completed `__init__.py` with the full `step()` orchestrator (220 LOC moved from flat file) plus all re-exports. Deleted `sizing_engine.py`.

## Invariants Preserved

- **Hex boundary**: No `datetime`, `os`, `state_manager`, `notifier` imports in any daughter file — pure math constraint maintained
- **Caller surface unchanged**: All existing import forms (`import sizing_engine`, `from sizing_engine import X`) resolve identically
- **All files ≤500 LOC**: Largest file is `__init__.py` at 286 lines
- **`ClosedTrade` re-exported**: `from sizing_engine import ClosedTrade` resolves (used by `daily_run_helpers.py`)

## Self-Check: PASSED

- `sizing_engine.py` deleted
- All 6 daughter files parse cleanly
- All caller imports verified
- Hex boundary intact
