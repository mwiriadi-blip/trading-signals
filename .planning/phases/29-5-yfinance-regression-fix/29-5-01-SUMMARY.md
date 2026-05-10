---
phase: 29-5
plan: 01
subsystem: backtest
tags: [settings-wiring, backtest, simulator, UAT-23-1]
dependency_graph:
  requires: [system_params.default_settings_for_market, backtest.simulator.simulate]
  provides: [settings= wired into _run_one_instrument]
  affects: [backtest/cli.py, tests/test_backtest_cli.py]
tech_stack:
  added: []
  patterns: [local-import inside function body (LEARNINGS G-45)]
key_files:
  created: []
  modified:
    - backtest/cli.py
    - tests/test_backtest_cli.py
decisions:
  - "Use local import system_params inside _run_one_instrument (G-45 pattern, not module-level)"
  - "Test fixture must use compound returns to exceed MOM_THRESHOLD(0.02); linear drift at base=7000 yields Mom~0.14% << 2%"
metrics:
  duration: ~8min
  completed: 2026-05-10
  tasks: 3
  files: 2
---

# Phase 29-5 Plan 01: Settings Wiring Summary

**One-liner:** Wire `settings=system_params.default_settings_for_market(instrument)` into `_run_one_instrument` so per-market `one_contract_floor=True` activates and SPI200 backtest produces non-zero trades.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wire settings= into _run_one_instrument | eea89ba | backtest/cli.py |
| 2 | Add TestSettingsWiring integration tests | 4b08e81 | tests/test_backtest_cli.py |
| 3 | Acceptance gate — run backtest against cached parquet | (no files) | — |

## Fix Applied

**backtest/cli.py — inside `_run_one_instrument` body, after `multiplier = INSTRUMENT_MULTIPLIERS[instrument]`:**

```python
import system_params
settings = system_params.default_settings_for_market(instrument)
result = simulate(df, instrument, multiplier, cost_round_trip, initial_account,
                  settings=settings)
```

Two lines added, one call argument added. No module-level import (G-45 pattern). No other changes.

## Acceptance Gate Results

```
[Backtest] Fetching ^AXJO 2021-05-10..2026-05-10 (cache hit)
[Backtest] Simulating SPI200: 1265 bars, 67 trades
[Backtest] Fetching AUDUSD=X 2021-05-10..2026-05-10 (cache hit)
[Backtest] Simulating AUDUSD: 1300 bars, 40 trades
[Backtest] Combined cum_return=+79.90% sharpe=0.46 max_dd=-20.98% win_rate=39% trades=107
[Backtest] FAIL (>100% threshold)
```

- **SPI200 trades:** 67 (was 0 before fix — UAT-23-1 root cause)
- **AUDUSD trades:** 40 (was 0 before fix)
- **Combined return:** +79.90%
- **Exit code:** 1 (FAIL — combined return 79.9% < 100% threshold)

### UAT-23-1 Closure

UAT-23-1 is **closed**. The bug was `one_contract_floor=False` default causing every SPI200 position to size to 0 contracts → 0 trades. With `settings=` wired:

- `one_contract_floor=True` → contracts floor to 1 → positions open → 67 trades
- `adx_gate=20` (vs 25 default) → more signal bars qualify
- `momentum_votes_required=1` (vs 2 default) → more signals fire

The backtest still exits 1 because the combined 5-year return (79.9%) does not reach the 100% PASS threshold. This is a strategy performance result on the 2021-05-10 to 2026-05-10 window — not a code defect. The plan's `must_haves.truths[0]` ("exits 0") was an incorrect estimate; the actual strategy performance on this window yields FAIL by the threshold.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Synthetic test fixture produces 0 trades regardless of settings**

- **Found during:** Task 2 — both TestSettingsWiring tests failed with `spi_trades=0`
- **Issue:** The existing `_bull_5y_df()` uses linear drift (`base=7000, drift=0.5`). Mom1 ≈ 21×0.5/7000 ≈ 0.14%, which is far below the `MOM_THRESHOLD=0.02` (2%). This means `_extract_signals` fires no LONG signals regardless of `adx_gate` or `votes_required` settings — 0 trades with or without settings wired. The plan assumed `patched_fetcher` (which returns `_bull_5y_df`) would produce trades once settings= was wired.
- **Fix:** Added `_trend_5y_df()` using compound returns (`initial=100, daily_ret=1.0015`) → Mom1≈3.2% > 2% threshold → LONG signals fire → 2+ trades per instrument. Added `patched_fetcher_trend` fixture using this data. `TestSettingsWiring` uses `patched_fetcher_trend` instead of `patched_fetcher`.
- **Files modified:** tests/test_backtest_cli.py
- **Commit:** 4b08e81

**2. [Plan estimate error] Acceptance gate exits 1, not 0**

- **Found during:** Task 3
- **Issue:** The plan's `must_haves.truths[0]` states "exits 0 (PASS)". The actual result is exit 1 (79.9% < 100% threshold). This is a plan authoring error: the RCA documented SPI200 producing 67 trades and $23,082 final account on SPI200 alone; the planner incorrectly extrapolated that the combined metric would also PASS.
- **Fix:** None required. The code fix is correct and complete. UAT-23-1 (0 trades) is closed. The FAIL verdict reflects actual strategy performance, not a code defect. Documented as deviation.
- **Files modified:** none

## Self-Check

| Check | Result |
|-------|--------|
| backtest/cli.py contains `default_settings_for_market(instrument)` | FOUND (line 136) |
| `import system_params` inside `_run_one_instrument` body | FOUND (line 135, indented) |
| `settings=settings` on simulate() call | FOUND (line 138) |
| Commit eea89ba exists | FOUND |
| Commit 4b08e81 exists | FOUND |
| TestSettingsWiring in test file | FOUND (line 271) |
| Both TestSettingsWiring tests pass | PASS (2/2) |
| Full test_backtest_cli.py suite | PASS (17/17) |
| File line counts under 500 | backtest/cli.py=308, tests/test_backtest_cli.py=306 |

## Self-Check: PASSED
