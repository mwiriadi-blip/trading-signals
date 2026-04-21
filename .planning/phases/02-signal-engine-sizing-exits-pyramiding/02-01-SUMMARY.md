---
phase: 02
plan: 01
subsystem: scaffold
tags:
  - phase-2-scaffold
  - hexagonal-lite
  - python-3.11
  - typed-dict
  - dataclass-frozen-slots
  - ast-blocklist
  - scaffolding
  - enables-SIZE-01-to-06
  - enables-EXIT-06-to-09
  - enables-PYRA-01-to-05
dependency_graph:
  requires:
    - 01-06-SUMMARY.md  # Phase 1 complete — TestDeterminism AST guard in place
  provides:
    - system_params.py  # constants + Position TypedDict for all Phase 2 plans
    - sizing_engine.py  # public API stubs; implementations in 02-02..02-05
    - tests/test_sizing_engine.py  # test skeletons for 02-02..02-05 to fill
  affects:
    - signal_engine.py  # constant import migrated to system_params
    - tests/test_signal_engine.py  # TestDeterminism extended with Phase 2 hex guards
    - SPEC.md           # §6 + §signal_engine.py amended (D-11, D-07)
    - CLAUDE.md         # §Stack + §Architecture amended (D-11, D-07)
tech_stack:
  added:
    - system_params.py (stdlib: typing.TypedDict, typing.Literal)
    - sizing_engine.py (stdlib: dataclasses, math; imports signal_engine + system_params)
  patterns:
    - frozen dataclass with slots=True for SizingDecision, PyramidDecision, ClosedTrade, StepResult
    - TypedDict Position for state.json round-trip compatibility (D-08)
    - parametrized AST blocklist over _HEX_PATHS_ALL (D-07)
    - FORBIDDEN_MODULES_STDLIB_ONLY extension (numpy/pandas blocked for Phase 2 hex)
key_files:
  created:
    - system_params.py
    - sizing_engine.py
    - tests/test_sizing_engine.py
  modified:
    - signal_engine.py  # constants migrated to system_params; from system_params import ...
    - tests/test_signal_engine.py  # TestDeterminism extended (5 new tests, 24 total)
    - SPEC.md           # §6 SPI mini amendment + §signal_engine.py module-split note
    - CLAUDE.md         # §Stack contract specs bullet + §Architecture hex expansion
decisions:
  - "D-11 SPI mini $5/pt, $6 AUD RT confirmed by operator and propagated to SPEC.md, CLAUDE.md, system_params.py"
  - "D-07 sizing_engine.py module split: SPEC.md §signal_engine.py gets forward-reference note"
  - "FORBIDDEN_MODULES_STDLIB_ONLY adds numpy+pandas to blocklist for Phase 2 stdlib-only hex modules"
  - "noqa: F401 annotations on all forward-declared imports in sizing_engine.py stubs (used in 02-02..02-05)"
metrics:
  duration: "9m58s"
  completed_date: "2026-04-21"
  tasks_completed: 3
  tasks_total: 3
  files_created: 3
  files_modified: 4
---

# Phase 02 Plan 01: Wave 0 Scaffold — system_params + sizing_engine + AST Guard Summary

**One-liner:** Wave 0 blocking scaffold: SPI mini D-11 doc amendments, system_params.py with Phase 1+2 constants and Position TypedDict, sizing_engine.py with D-17 expanded stubs, and extended AST blocklist enforcing the Phase 2 hex boundary.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Amend SPEC.md and CLAUDE.md for D-11, D-07 | f46c12e | SPEC.md, CLAUDE.md |
| 2 | Module skeletons: system_params.py + sizing_engine.py + test stubs | f77df70 | system_params.py, sizing_engine.py, tests/test_sizing_engine.py, signal_engine.py |
| 3 | Extend AST blocklist to cover Phase 2 hex modules | 2d2290c | tests/test_signal_engine.py |

## What Was Built

### Task 1 — Doc amendments (D-11, D-07)

SPEC.md §6 updated from `SPI: $25/point, $30 AUD RT` to `SPI 200 mini: $5/point, $6 AUD RT ($3 open + $3 close per D-13)`. AUD/USD spec unchanged. D-13 cost-timing note added. D-17 signature note inserted in §signal_engine.py module-split paragraph (D-07). CLAUDE.md §Stack gets contract-specs bullet; §Architecture paragraph expanded to mention `sizing_engine.py` and `system_params.py` with a hex-boundary rule bullet.

### Task 2 — Module skeletons

- **system_params.py** (95 lines): All Phase 1 policy constants migrated from `signal_engine.py` (ATR_PERIOD, ADX_PERIOD, MOM_PERIODS, RVOL_PERIOD, ANNUALISATION_FACTOR, ADX_GATE, MOM_THRESHOLD). Phase 2 sizing/exit/pyramid constants added (RISK_PCT_LONG/SHORT, TRAIL_MULT_LONG/SHORT, VOL_SCALE_*, PYRAMID_TRIGGERS, MAX_PYRAMID_LEVEL, ADX_EXIT_GATE). D-11 contract specs (SPI_MULT=5.0, SPI_COST_AUD=6.0, AUDUSD_NOTIONAL=10000.0, AUDUSD_COST_AUD=5.0). Position TypedDict (D-08) with 8 fields including `peak_price: float | None` and `trough_price: float | None`.
- **signal_engine.py** migration: `from system_params import ADX_GATE, ADX_PERIOD, ANNUALISATION_FACTOR, ATR_PERIOD, MOM_PERIODS, MOM_THRESHOLD, RVOL_PERIOD` — LONG/SHORT/FLAT remain as local signal-encoding primitives (D-01).
- **sizing_engine.py** (300 lines): Four frozen dataclasses — `SizingDecision(contracts, warning)`, `PyramidDecision(add_contracts, new_level)`, `ClosedTrade`, `StepResult`. Six public function stubs with complete docstrings and D-17 expanded signatures: `compute_unrealised_pnl(position, current_price, multiplier, cost_aud_open)` and `step(position, bar, indicators, old_signal, new_signal, account, multiplier, cost_aud_open)`. All stubs raise `NotImplementedError` pending 02-02..02-05.
- **tests/test_sizing_engine.py** (265 lines): Five class skeletons — TestSizing (10 methods), TestExits (12 methods), TestPyramid (8 methods), TestTransitions (9 methods), TestEdgeCases (6 methods). All `pytest.skip()` with target plan references. Module-level path constants matching test_signal_engine.py pattern.
- **Phase 1 test suite**: 83 tests still pass after constant migration — no regressions.

### Task 3 — AST blocklist extension

Added `SIZING_ENGINE_PATH`, `SYSTEM_PARAMS_PATH`, `TEST_SIZING_ENGINE_PATH`, `FORBIDDEN_MODULES_STDLIB_ONLY` (extends base + numpy/pandas), `_HEX_PATHS_ALL`, `_HEX_PATHS_STDLIB_ONLY` to module-level constants. Replaced single `test_forbidden_imports_absent` with parametrized version over all 3 hex paths. Added `test_phase2_hex_modules_no_numpy_pandas` covering sizing_engine + system_params. Extended `test_no_four_space_indent` from 2 to 5 files. Added `test_sizing_engine_has_core_public_surface` verifying all 6 callables and 3 frozen dataclasses. Result: 24 TestDeterminism tests, 88 total passing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `Optional[X]` → `X | None` ruff UP007 warnings**
- **Found during:** Task 2 ruff check
- **Issue:** `Optional[float]` in system_params.py and `Optional[str]`, `Optional[Position]` etc. in sizing_engine.py triggered ruff UP007 (prefer `X | Y` union syntax for Python 3.10+)
- **Fix:** Replaced all `Optional[X]` with `X | None` in both files; removed `Optional` from typing imports
- **Files modified:** system_params.py, sizing_engine.py
- **Commit:** f77df70

**2. [Rule 1 - Bug] Unused imports ruff F401 warnings in sizing_engine.py stubs**
- **Found during:** Task 2 ruff check
- **Issue:** All constants imported at module level are unused in stub-only file (implementations pending). `math`, FLAT/LONG/SHORT, and all system_params constants triggered F401.
- **Fix:** Added `# noqa: F401` with descriptive comments (e.g. `# noqa: F401 — used in calc_position_size 02-02`) to document the intentional forward-declaration pattern.
- **Files modified:** sizing_engine.py
- **Commit:** f77df70

**3. [Rule 1 - Bug] Bare `python3` vs `.venv/bin/python` version difference**
- **Found during:** SUMMARY verification step
- **Issue:** Running `python3 -c "..."` hit macOS system Python which may differ from project's 3.11.8 venv. `float | None` in TypedDict body raised `TypeError` on older Python. Not a code bug — the venv Python (3.11.8) handles it correctly.
- **Fix:** All verification commands use `.venv/bin/python`. Test suite exclusively uses `.venv/bin/python -m pytest`. No code change needed.
- **Commit:** N/A (observation only)

## Known Stubs

All stubs in `sizing_engine.py` are intentional Wave 0 scaffolding — each raises `NotImplementedError`. Plans 02-02 through 02-05 implement them:

| Stub | File | Implementing Plan |
|------|------|-------------------|
| `calc_position_size` | sizing_engine.py:100 | 02-02 |
| `compute_unrealised_pnl` | sizing_engine.py:219 | 02-02 |
| `get_trailing_stop` | sizing_engine.py:131 | 02-03 |
| `check_stop_hit` | sizing_engine.py:162 | 02-03 |
| `check_pyramid` | sizing_engine.py:192 | 02-03 |
| `step` | sizing_engine.py:256 | 02-05 |

All test methods in `tests/test_sizing_engine.py` (45 total) call `pytest.skip()` with target plan references. These are tracked Wave 0 stubs, not defects.

## Threat Flags

None — this plan creates no network endpoints, auth paths, file access patterns, or schema changes at trust boundaries. All new code is pure-math stdlib.

## Self-Check

**Checking created files exist:**
- system_params.py: FOUND
- sizing_engine.py: FOUND
- tests/test_sizing_engine.py: FOUND

**Checking commits exist:**
- f46c12e: FOUND (docs(02-01): amend SPEC.md and CLAUDE.md)
- f77df70: FOUND (feat(02-01): scaffold system_params.py + sizing_engine.py)
- 2d2290c: FOUND (test(02-01): extend AST blocklist)

**Test suite:** 88 tests pass (83 Phase 1 + 5 new guards), 45 Phase 2 skips, 0 failures.

## Self-Check: PASSED
