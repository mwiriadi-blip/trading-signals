---
phase: 02
plan: 02
subsystem: sizing
tags:
  - phase-2-sizing
  - vol-scale-clip
  - nan-guard
  - skip-if-zero
  - half-cost-on-open
  - frozen-dataclass
dependency_graph:
  requires:
    - 02-01-SUMMARY.md  # Wave 0 scaffold — stubs + AST guard in place
  provides:
    - sizing_engine.calc_position_size  # SIZE-01..05 implemented
    - sizing_engine.compute_unrealised_pnl  # D-13, D-17 implemented
    - sizing_engine._vol_scale  # private helper for NaN-safe vol clip
    - tests/test_sizing_engine.py::TestSizing  # 19 named tests
  affects:
    - sizing_engine.py  # 300 stub lines -> 351 lines (calc_position_size + compute_unrealised_pnl implemented)
    - tests/test_sizing_engine.py  # 265 skeleton lines -> 454 lines (TestSizing populated)
tech_stack:
  added:
    - math.isfinite NaN guard pattern (vol_scale + stop_dist guards)
    - direction_mult sign-flip pattern (Pitfall 7 mitigation in compute_unrealised_pnl)
  patterns:
    - _vol_scale private helper: clip(VOL_SCALE_TARGET/rvol, MIN, MAX) with isfinite guard
    - SizingDecision warning prefix 'size=0:' for SIZE-05 diagnostics
    - D-17 explicit cost_aud_open param (no instrument-lookup coupling)
key_files:
  modified:
    - sizing_engine.py  # 300 -> 351 lines; calc_position_size + compute_unrealised_pnl implemented
    - tests/test_sizing_engine.py  # 265 -> 454 lines; TestSizing class fully populated
decisions:
  - "D-17 enforced: compute_unrealised_pnl takes explicit cost_aud_open, not multiplier lookup"
  - "SIZE-05 no-floor confirmed: int() truncation with 'size=0:' warning when result is 0"
  - "D-03 NaN policy: math.isfinite guard returns VOL_SCALE_MAX (2.0) for degenerate rvol"
  - "Pitfall 7 mitigated: direction_mult = +1 LONG / -1 SHORT prevents sign error on SHORT PnL"
metrics:
  duration: "6m34s"
  completed_date: "2026-04-21"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 2
---

# Phase 02 Plan 02: Sizing Implementation (calc_position_size + compute_unrealised_pnl) Summary

**One-liner:** Wave 1 sizing layer: calc_position_size with direction-aware risk/trail/vol-scale and SIZE-05 zero-skip, compute_unrealised_pnl with D-17 explicit cost_aud_open and Pitfall 7 direction sign-flip, plus 19 named TestSizing tests covering SIZE-01..06.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement calc_position_size + compute_unrealised_pnl | a904f18 | sizing_engine.py |
| 2 | Populate TestSizing with 19 named tests | 687a0a3 | tests/test_sizing_engine.py |

## What Was Built

### Task 1 — sizing_engine.py implementation (300 → 351 lines)

**Private helper `_vol_scale(rvol: float) -> float`** added in new private-helpers section:
- `math.isfinite(rvol) or rvol <= 1e-9` guard returns `VOL_SCALE_MAX` (2.0) per D-03
- Otherwise `max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, VOL_SCALE_TARGET / rvol))` — one-line clip

**`calc_position_size` implementation** (replaced `NotImplementedError`):
- SIZE-01: `risk_pct = RISK_PCT_LONG (0.01)` for LONG, `RISK_PCT_SHORT (0.005)` for SHORT
- SIZE-02: `trail_mult = TRAIL_MULT_LONG (3.0)` for LONG, `TRAIL_MULT_SHORT (2.0)` for SHORT
- SIZE-03: delegates to `_vol_scale(rvol)`
- SIZE-04: `stop_dist = trail_mult * atr * multiplier`; `n_raw = (account * risk_pct / stop_dist) * vol_scale`; `n_contracts = int(n_raw)` — truncating, no floor
- SIZE-05: when `n_contracts == 0`, returns `SizingDecision(contracts=0, warning='size=0: account=..., atr=..., rvol=..., vol_scale=..., stop_dist=..., n_raw=...')` — 6 diagnostic fields
- FLAT guard: signal not LONG/SHORT returns `size=0` warning with "is not LONG or SHORT" message
- stop_dist guard: non-positive/non-finite stop_dist returns `size=0` warning

**`compute_unrealised_pnl` implementation** (replaced `NotImplementedError`):
- `direction_mult = 1.0` for LONG, `-1.0` for SHORT (Pitfall 7 mitigation)
- `gross = direction_mult * (current - entry) * n_contracts * multiplier`
- `open_cost = cost_aud_open * n_contracts`
- Returns `gross - open_cost` (D-13 half-cost-on-open; D-17 explicit param)

**4 remaining stubs untouched:** `get_trailing_stop`, `check_stop_hit`, `check_pyramid`, `step` (plans 02-03/02-05).

### Task 2 — tests/test_sizing_engine.py TestSizing (265 → 454 lines)

19 named test methods replacing 10 `pytest.skip()` placeholders:

| Method | Covers |
|--------|--------|
| `test_risk_pct_long_is_1pct` | SIZE-01 LONG: contracts=1 at atr=53, rvol=0.15 |
| `test_risk_pct_short_is_half_pct` | SIZE-01 SHORT: contracts=0 (half risk_pct) |
| `test_trail_mult_by_direction` | SIZE-02: differential + absolute contract assertions |
| `test_vol_scale_clip_ceiling` | SIZE-03: rvol=0.05 → 2.4 clipped to 2.0 → contracts=2 |
| `test_vol_scale_clip_floor` | SIZE-03: rvol=0.50 → 0.24 clipped to 0.3 → contracts=0 |
| `test_vol_scale_nan_guard` | SIZE-03+D-03: NaN rvol → vol_scale=2.0, contracts=2 |
| `test_vol_scale_zero_guard` | SIZE-03+D-03: rvol=1e-10 → vol_scale=2.0, contracts=2 |
| `test_no_max_one_floor_when_undersized` | SIZE-04+operator: atr=80 → contracts=0, NOT 1 |
| `test_calc_position_size_formula` | SIZE-04: atr=20 → n_raw=2.667 → contracts=2 |
| `test_zero_contracts_warning_format` | SIZE-05: 6 diagnostic substrings present |
| `test_contract_specs_spi_mini` | SIZE-06+D-11: SPI_MULT==5.0, mini vs full comparison |
| `test_contract_specs_audusd` | SIZE-06: AUDUSD_NOTIONAL=10000, contracts=5 |
| `test_flat_signal_returns_size_zero_with_warning` | caller-error guard for FLAT signal |
| `test_unrealised_pnl_signature_has_cost_aud_open` | D-17: inspect.signature spot-check |
| `test_unrealised_pnl_long_profit` | D-13: LONG profit 494.0 |
| `test_unrealised_pnl_long_loss` | D-13: LONG loss -506.0 |
| `test_unrealised_pnl_short_profit_pitfall_7` | Pitfall 7: SHORT profit 494.0 (correct sign) |
| `test_unrealised_pnl_short_loss` | SHORT loss -506.0 |
| `test_unrealised_pnl_audusd_split_cost` | AUDUSD 195.0 (epsilon tolerance for float mul) |

## Key Evidence

**pytest output (`tests/test_sizing_engine.py::TestSizing -v`):**
```
19 passed in 0.39s
```
0 failures, 0 skips.

**D-17 signature (`inspect.signature(compute_unrealised_pnl)`):**
```
(position: system_params.Position, current_price: float, multiplier: float, cost_aud_open: float) -> float
```

**RESEARCH.md §Pattern 1 verified-numbers spot-check:**
```
calc_position_size(100000, LONG, 53.0, 0.15, 5.0).contracts == 1   ✓
calc_position_size(100000, LONG, 80.0, 0.15, 5.0).contracts == 0   ✓
calc_position_size(100000, LONG, 20.0, 0.15, 5.0).contracts == 2   ✓
```

**Full suite:** 124 passed, 35 skipped (TestExits/TestPyramid/TestTransitions/TestEdgeCases placeholders), 0 failures.

**ruff:** All files clean (`signal_engine.py sizing_engine.py system_params.py tests/`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `max(1` pattern appeared in docstrings/comments triggering AC grep**
- **Found during:** Task 1 acceptance criteria check
- **Issue:** The plan AC requires `grep -cF 'max(1' sizing_engine.py` to return 0. Three comments/docstrings contained the forbidden pattern for documentation purposes ("no max(1,...) floor").
- **Fix:** Rephrased all three occurrences to convey the same intent without the literal string: "No floor applied", "SIZE-05 handles contracts==0 (no floor)", "SIZE=0 contracts skips + warns (no floor per operator)"
- **Files modified:** sizing_engine.py
- **Commit:** a904f18

**2. [Rule 1 - Bug] E501 line-too-long in sizing_engine.py and tests**
- **Found during:** Task 1 ruff check; Task 2 ruff check
- **Issue:** `compute_unrealised_pnl` gross calculation line was 107 chars; two test call sites were 101-102 chars; one docstring was 101 chars
- **Fix:** Split `gross` calculation into `price_diff` intermediate; wrapped long `calc_position_size()` calls to multi-line; shortened docstring line
- **Files modified:** sizing_engine.py, tests/test_sizing_engine.py
- **Commit:** a904f18 (sizing_engine.py), 687a0a3 (test file)

## Known Stubs

| Stub | File | Implementing Plan |
|------|------|-------------------|
| `get_trailing_stop` | sizing_engine.py | 02-03 |
| `check_stop_hit` | sizing_engine.py | 02-03 |
| `check_pyramid` | sizing_engine.py | 02-03 |
| `step` | sizing_engine.py | 02-05 |

All test methods in TestExits (12), TestPyramid (8), TestTransitions (9), TestEdgeCases (6) remain `pytest.skip()` — intentional Wave 0/1 stubs, not defects.

## Threat Flags

None — pure math, no network endpoints, no filesystem access, no auth paths.

## Self-Check

**Checking files exist:**
- sizing_engine.py: FOUND
- tests/test_sizing_engine.py: FOUND
- .planning/phases/02-signal-engine-sizing-exits-pyramiding/02-02-SUMMARY.md: FOUND

**Checking commits exist:**
- a904f18: feat(02-02) sizing implementation
- 687a0a3: test(02-02) TestSizing

## Self-Check: PASSED
