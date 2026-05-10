---
phase: 29
plan: 13
kind: spike-rca
created: 2026-05-10
---

## Root Cause

`backtest/cli.py::_run_one_instrument` (line 135) calls `simulate()` with no
`settings=` argument:

```python
result = simulate(df, instrument, multiplier, cost_round_trip, initial_account)
```

`simulate()` signature is `simulate(..., settings=None)`. With `settings=None`:

1. `_extract_signals(df_ind, settings=None)` — ADX gate = 25.0, votes_required = 2
   (Phase-1 defaults from `system_params`).
2. `sizing_engine.calc_position_size(settings=None)` — uses
   `DEFAULT_STRATEGY_SETTINGS`: `risk_pct_long=0.01`, `trail_mult_long=3.0`,
   **`one_contract_floor=False`**.

At $10k starting equity and SPI200 mini (~7,000 pts × 5 AUD/pt):

```
stop_dist = 3.0 × ATR(≈101) × 5 = 1,515 AUD/contract
n_raw     = (10,000 × 0.01 / 1,515) × vol_scale(≈0.583) ≈ 0.038
n_contracts = int(0.038) = 0
```

`one_contract_floor=False` → SIZE-05 guard fires: position skipped, no trade opened.

Every one of 176 non-FLAT signals (111 LONG + 65 SHORT) over 5 years resolves to
`n_contracts=0`. Zero trades → equity curve stays flat → FAIL exit code.

**The per-market settings that fix this already exist in
`system_params.DEFAULT_STRATEGY_SETTINGS_BY_MARKET['SPI200']`** (`adx_gate=20`,
`votes_required=1`, `risk_pct_long=0.05`, `one_contract_floor=True`). They were
added in Phase 24 and are used by the live signal loop but were never plumbed into
the backtest CLI path. This is a **missing wiring bug**, not a schema change or
engine regression.

Confirmed: running `simulate()` with `DEFAULT_STRATEGY_SETTINGS_BY_MARKET['SPI200']`
produces 67 trades and final_account=$23,082.84 over the same 5-year window.

---

## Files Affected

| File | Role |
|------|------|
| `backtest/cli.py` | **Fix site.** `_run_one_instrument` at line 135 calls `simulate()` with no `settings=`. Single call site. |
| `backtest/simulator.py` | Receives `settings=None`; propagates to `_extract_signals` and `sizing_engine.step`. No change needed — correct by contract. |
| `signal_engine/` (multiple) | `_extract_signals` uses `settings=None` → Phase-1 defaults for ADX gate + vote threshold. No change needed. |
| `sizing_engine.py` | `calc_position_size` uses `DEFAULT_STRATEGY_SETTINGS` when `settings=None` → `one_contract_floor=False`. No change needed. |
| `system_params.py` | Already contains `DEFAULT_STRATEGY_SETTINGS_BY_MARKET` with correct per-market values. No change needed. |
| `tests/test_backtest_simulator.py` | Will need a fixture/test update to cover the `settings=` wired path in `_run_one_instrument`. |
| `tests/test_backtest_cli.py` | May need a companion test asserting non-zero trades when `settings` is correctly wired. |

---

## Blast Radius

**Scope: TIGHT.**

- **Single call site changed:** `backtest/cli.py:135` — one argument added to one
  function call.
- **No new logic:** `DEFAULT_STRATEGY_SETTINGS_BY_MARKET` and
  `default_settings_for_market()` (or equivalent lookup) already exist in
  `system_params` and are imported elsewhere. No new constants or modules.
- **No data-layer changes:** parquet cache format unchanged; yfinance schema unchanged.
  The existing cached parquet files (1265 AXJO bars, 1300 AUDUSD bars) are correct
  and require no regeneration.
- **No AST hex boundary involved:** the fix does not touch `signal_engine` internals
  or the sizing algorithm — only the call site that invokes the simulator.
- **Deterministic-fixture tests:** existing `tests/test_backtest_*` fixtures were
  generated with `settings=None` (Phase-1 defaults). After the fix, the CLI path
  uses per-market settings; fixture tests that call `simulate()` directly with
  explicit settings are unaffected. Tests that test the CLI integration path
  (`_run_one_instrument` or `run_backtest`) will need updating to expect non-zero
  trades — these are companion tests for the fix, not regenerations of data fixtures.
- **No regression to live signal loop:** the live signal path already uses
  per-market settings and is unaffected by this change.

---

## Recommended Phase 29.5 Shape

**1 plan only:**

| Plan | Title | Depends On | Expected Files Modified |
|------|-------|------------|------------------------|
| 29.5-01 | Wire `settings` in backtest CLI | none | `backtest/cli.py` (1 line), `tests/test_backtest_cli.py` or `tests/test_backtest_simulator.py` (1–2 test cases) |

Implementation steps:
1. Import `default_settings_for_market` (or equivalent lookup) from `system_params`
   in `backtest/cli.py`.
2. Pass `settings=default_settings_for_market(instrument)` to `simulate()` in
   `_run_one_instrument`.
3. Update / add integration test asserting `len(result.trades) > 0` for both
   SPI200 and AUDUSD over 1y with cached parquet data.
4. Run `python -m backtest --years 5` (or equivalent with cached data) and verify
   non-zero trades + PASS exit code.

No Phase 29.5 discuss-phase or context-gather needed — root cause is fully
characterised. Planner can proceed to plan-phase directly from this RCA.

---

## Time-Box Final

Estimated hours used: ~1.5h
- Codebase read: 45m
- Diagnostic harness + run: 30m
- Signal + sizing trace: 15m
- RCA doc: 20m
