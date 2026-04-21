---
phase: 02
plan: 03
subsystem: exits-pyramid
tags:
  - phase-2-exits
  - phase-2-pyramid
  - intraday-high-low
  - stateless-pyramid-step
  - peak-trough-tracking
  - entry-atr-anchor
  - nan-policy
dependency_graph:
  requires:
    - 02-02-SUMMARY.md  # Wave 1 sizing — _vol_scale + calc_position_size + compute_unrealised_pnl
  provides:
    - sizing_engine.get_trailing_stop  # EXIT-06/07 with D-15 entry-ATR anchor
    - sizing_engine.check_stop_hit    # EXIT-08/09 intraday H/L with D-15 anchor
    - sizing_engine.check_pyramid     # PYRA-01..05 stateless single-step (D-12)
    - tests/test_sizing_engine.py::TestExits    # 14 named EXIT tests + B-1 NaN
    - tests/test_sizing_engine.py::TestPyramid  # 13 named PYRA tests + B-1 NaN
  affects:
    - sizing_engine.py  # 351 -> 442 lines; 3 stubs replaced, only step() remains
    - tests/test_sizing_engine.py  # 454 -> 629 lines; TestExits + TestPyramid populated
tech_stack:
  added:
    - del atr pattern (D-15: explicit arg deletion to enforce entry-ATR anchor)
    - math.isfinite NaN guard in get_trailing_stop + check_stop_hit + check_pyramid
    - float('nan') return from get_trailing_stop on NaN atr_entry (B-1)
  patterns:
    - D-15 entry-ATR anchor: del atr in get_trailing_stop + check_stop_hit; uses position['atr_entry']
    - B-1 NaN policy: get_trailing_stop->nan, check_stop_hit->False, check_pyramid->hold level
    - D-12 stateless single-step: check_pyramid evaluates only (level+1)*atr_entry threshold
    - Pitfall 3 None-fallback: peak_price/trough_price None -> entry_price
    - _make_position helper in tests for readable Position dicts with sensible defaults
key_files:
  modified:
    - sizing_engine.py  # 351 -> 442 lines; get_trailing_stop + check_stop_hit + check_pyramid implemented
    - tests/test_sizing_engine.py  # 454 -> 629 lines; TestExits (14) + TestPyramid (13) + helpers
decisions:
  - "D-15 enforced via del atr in both get_trailing_stop and check_stop_hit — atr arg present for API stability but discarded at top of body"
  - "D-12 stateless invariant: check_pyramid uses threshold=(level+1)*atr_entry; never returns add_contracts>1"
  - "B-1 NaN policy: get_trailing_stop NaN atr_entry->nan; check_stop_hit NaN high/low/atr_entry->False; check_pyramid NaN->hold level"
  - "Docstring AC grep compliance: 'add_contracts=2' literal avoided in code; 'high >= stop' and 'low <= stop' each appear exactly once (in return statements)"
metrics:
  duration: "460s (~7m40s)"
  completed_date: "2026-04-21"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 2
---

# Phase 02 Plan 03: Exits + Pyramid Implementation Summary

**One-liner:** Wave 2 exits + pyramid: get_trailing_stop (D-15 entry-ATR anchor), check_stop_hit (intraday H/L inclusive boundary), check_pyramid (D-12 stateless single-step), with B-1 NaN policy across all three and 27 named unit tests proving EXIT-06..09 + PYRA-01..05.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement get_trailing_stop + check_stop_hit + check_pyramid | b22befb | sizing_engine.py |
| 2 | Populate TestExits + TestPyramid (27 named tests) | a8e4491 | tests/test_sizing_engine.py |

## What Was Built

### Task 1 — sizing_engine.py (351 -> 442 lines)

**`get_trailing_stop(position, current_price, atr) -> float`** implemented:
- `del current_price` and `del atr` at top — D-15 enforcement; only `position['atr_entry']` is used for trail distance
- LONG: `peak - TRAIL_MULT_LONG * atr_entry` (peak falls back to entry_price if None — Pitfall 3)
- SHORT: `trough + TRAIL_MULT_SHORT * atr_entry` (trough falls back to entry_price if None)
- B-1: if `not math.isfinite(atr_entry)` -> return `float('nan')`
- Docstring cites D-15, D-16 ownership ("assumes peak/trough already updated by caller"), Pitfall 3, B-1

**`check_stop_hit(position, high, low, atr) -> bool`** implemented:
- `del atr` at top — D-15 enforcement
- B-1: NaN high or low -> return False; NaN atr_entry -> return False
- LONG: `stop = peak - TRAIL_MULT_LONG * atr_entry; return low <= stop` (inclusive)
- SHORT: `stop = trough + TRAIL_MULT_SHORT * atr_entry; return high >= stop` (inclusive)
- None-safety mirrors get_trailing_stop (Pitfall 3)

**`check_pyramid(position, current_price, atr_entry) -> PyramidDecision`** implemented:
- B-1: NaN current_price or atr_entry -> `PyramidDecision(0, level)` — hold level, no add
- Level >= MAX_PYRAMID_LEVEL (2): `PyramidDecision(0, level)` — cap (PYRA-04)
- LONG distance: `current_price - entry_price`; SHORT distance: `entry_price - current_price`
- `threshold = (level + 1) * atr_entry` — single-level evaluation (D-12)
- if distance >= threshold: `PyramidDecision(1, level + 1)` else `PyramidDecision(0, level)`
- add_contracts is always 0 or 1 — D-12 invariant (`grep -cF 'add_contracts=2' sizing_engine.py == 0`)

**Only `step()` remains a NotImplementedError stub** (`grep -c 'NotImplementedError' sizing_engine.py == 1`).

### Task 2 — tests/test_sizing_engine.py (454 -> 629 lines)

**Module-level helpers added:**
- `_load_phase2_fixture(name)` — JSON fixture loader for future plans
- `_make_position(...)` — Position TypedDict builder with sensible defaults (direction='LONG', atr_entry=53.0, all fields)

**TestExits (14 named tests):**

| Method | Covers |
|--------|--------|
| `test_long_trailing_stop_peak_update` | EXIT-06 + D-15: atr=999 passed, stop uses atr_entry=53 |
| `test_long_trailing_stop_d15_anchor_explicit` | D-15 proof: atr=53 vs atr=200 -> same stop |
| `test_long_trailing_stop_peak_none_falls_back_to_entry` | Pitfall 3: None peak -> entry_price |
| `test_short_trailing_stop_trough_update` | EXIT-07 + D-15: atr=999 passed, stop uses atr_entry=53 |
| `test_short_trailing_stop_trough_none_falls_back_to_entry` | Pitfall 3: None trough -> entry_price |
| `test_long_stop_hit_intraday_low_at_boundary` | EXIT-08: low==stop -> True (inclusive) |
| `test_long_stop_hit_intraday_low_below` | EXIT-08: low < stop -> True |
| `test_long_no_stop_hit_low_above` | EXIT-08 negative: low > stop -> False |
| `test_short_stop_hit_intraday_high_at_boundary` | EXIT-09: high==stop -> True (inclusive) |
| `test_short_no_stop_hit_high_below` | EXIT-09 negative: high < stop -> False |
| `test_get_trailing_stop_nan_atr_returns_nan` | B-1: NaN atr_entry -> math.isnan(result) |
| `test_check_stop_hit_nan_high_returns_false` | B-1: NaN high -> False |
| `test_check_stop_hit_nan_low_returns_false` | B-1: NaN low -> False |
| `test_check_stop_hit_nan_atr_entry_returns_false` | B-1: NaN atr_entry -> False |

**TestPyramid (13 named tests):**

| Method | Covers |
|--------|--------|
| `test_position_carries_pyramid_level` | PYRA-01: TypedDict has pyramid_level field |
| `test_pyramid_level_0_to_1_long` | PYRA-02 LONG: dist=53 >= 1*53 -> add 1, level->1 |
| `test_pyramid_level_0_to_1_short` | PYRA-02 SHORT: dist=53 >= 1*53 -> add 1, level->1 |
| `test_pyramid_level_0_no_add_below_threshold` | PYRA-02 negative: dist=52 < 53 -> no add |
| `test_pyramid_level_1_to_2_long` | PYRA-03 LONG: dist=110 >= 2*53=106 -> add 1, level->2 |
| `test_pyramid_level_1_to_2_short` | PYRA-03 SHORT: dist=110 >= 106 -> add 1, level->2 |
| `test_pyramid_level_1_no_add_below_threshold` | PYRA-03 negative: dist=105 < 106 -> no add |
| `test_pyramid_capped_at_level_2` | PYRA-04: level=2, dist=500 -> add_contracts=0 |
| `test_pyramid_cap_independent_of_max_constant` | PYRA-04 sanity: MAX_PYRAMID_LEVEL==2 |
| `test_pyramid_gap_day_caps_at_one_add_long` | D-12 LONG: dist=150 > both thresholds -> add_contracts=1, level->1 |
| `test_pyramid_gap_day_caps_at_one_add_short` | D-12 SHORT: dist=200 > both thresholds -> add_contracts=1, level->1 |
| `test_check_pyramid_nan_current_price_returns_no_add` | B-1: NaN current_price -> hold level |
| `test_check_pyramid_nan_atr_entry_returns_no_add` | B-1: NaN atr_entry -> hold level |

## Key Evidence

**D-15 anchor proof (`test_long_trailing_stop_d15_anchor_explicit`):**
```
get_trailing_stop(pos, 7100.0, atr=53.0) == get_trailing_stop(pos, 7100.0, atr=200.0)
# Both return 6891.0 — atr argument is ignored, position['atr_entry']=53 is used
```

**D-12 invariant (`grep -cF 'add_contracts=2' sizing_engine.py`):**
```
0
```
Gap-day gap-day tests in both directions confirm only 1 level advance per call.

**B-1 NaN policy (`pytest tests/test_sizing_engine.py -k nan -v`):**
```
TestSizing::test_vol_scale_nan_guard                           PASSED
TestExits::test_get_trailing_stop_nan_atr_returns_nan          PASSED
TestExits::test_check_stop_hit_nan_high_returns_false          PASSED
TestExits::test_check_stop_hit_nan_low_returns_false           PASSED
TestExits::test_check_stop_hit_nan_atr_entry_returns_false     PASSED
TestPyramid::test_check_pyramid_nan_current_price_returns_no_add PASSED
TestPyramid::test_check_pyramid_nan_atr_entry_returns_no_add   PASSED
7 passed, 54 deselected
```

**TestExits + TestPyramid (`pytest tests/test_sizing_engine.py::TestExits tests/test_sizing_engine.py::TestPyramid -v`):**
```
27 passed in 0.30s
```
0 failures, 0 skips.

**Full suite:**
```
151 passed, 15 skipped in 1.26s
```
15 skips = TestTransitions (9) + TestEdgeCases (6) placeholders awaiting plans 02-04/02-05.

**ruff:** both files clean.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `add_contracts=2` literal in docstring triggering AC grep**
- **Found during:** Task 1 acceptance criteria check (`grep -cF 'add_contracts=2' sizing_engine.py` returned 1)
- **Issue:** The docstring stated "NEVER returns add_contracts=2" — the literal matched the grep that must return 0
- **Fix:** Rephrased to "add_contracts is always 0 or 1, never higher" — conveys same intent without the prohibited literal
- **Files modified:** sizing_engine.py
- **Commit:** b22befb

**2. [Rule 1 - Bug] `high >= stop` and `low <= stop` literals in docstrings triggering AC grepping**
- **Found during:** Task 1 acceptance criteria check (each returned 2 instead of required 1)
- **Issue:** Docstring used the exact boundary expressions as inline code examples, matching the same grep patterns as the actual return statements
- **Fix:** Rephrased docstring boundary descriptions to prose without the literal comparison expressions
- **Files modified:** sizing_engine.py
- **Commit:** b22befb

## Known Stubs

| Stub | File | Implementing Plan |
|------|------|-------------------|
| `step` | sizing_engine.py | 02-05 |

All TestTransitions (9) and TestEdgeCases (6) methods remain `pytest.skip()` — intentional, awaiting plans 02-04/02-05.

## Threat Flags

None — pure math, no network endpoints, no filesystem access, no auth paths. The D-12 stateless invariant (no `add_contracts=2` in the file) and D-15 entry-ATR anchor are risk-discipline controls, not security mitigations.

## Self-Check

**Checking files exist:**
- sizing_engine.py: FOUND
- tests/test_sizing_engine.py: FOUND
- .planning/phases/02-signal-engine-sizing-exits-pyramiding/02-03-SUMMARY.md: FOUND (this file)

**Checking commits exist:**
- b22befb: feat(02-03) exits+pyramid implementation
- a8e4491: test(02-03) TestExits + TestPyramid

## Self-Check: PASSED
