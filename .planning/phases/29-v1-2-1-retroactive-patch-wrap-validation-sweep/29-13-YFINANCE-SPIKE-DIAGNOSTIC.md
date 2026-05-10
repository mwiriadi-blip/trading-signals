---
phase: 29
plan: 13
kind: spike-diagnostic
created: 2026-05-10
---

## Symptom — UAT-23-1: `python -m backtest --years 5` → 0 trades

`python -m backtest --years 5` exits with code 1 (FAIL). Backtest reports for
both SPI200 (1265 bars) and AUDUSD (1300 bars) show `total_trades: 0` and
`cumulative_return_pct: 0.0`. All equity curve points remain flat at the
initial $10,000 account balance.

Confirmed from cached reports:
- `v1.2.0-20260510T132547.json`: `pass: false`, SPI200 trades=0, AUDUSD trades=0
- `v1.2.0-20260510T132707.json`: same

## Repro Command

```bash
python -m backtest --years 5
# or read cached parquet directly:
.venv/bin/python /tmp/spike_diagnostic.py 2>&1 | tee /tmp/spike_output.log
```

Harness used the cached parquet files at:
- `.planning/backtests/data/^AXJO-2021-05-10-2026-05-10.parquet` (1265 rows)
- `.planning/backtests/data/AUDUSD=X-2021-05-10-2026-05-10.parquet` (1300 rows)

Network was available (verified live fetch during diagnostic). Cached data was
used to avoid rate-limit noise; schema matches live fetch exactly.

## Yfinance Schema Snapshot

yfinance version: **1.2.0**

Columns returned by `yf.Ticker(symbol).history(..., auto_adjust=False)`:

| Column | dtype |
|---|---|
| Open | float64 |
| High | float64 |
| Low | float64 |
| Close | float64 |
| **Adj Close** | float64 |
| Volume | int64 |
| **Dividends** | float64 |
| **Stock Splits** | float64 |

Index: `DatetimeIndex` — tz=`Australia/Sydney` (AXJO), tz=`Europe/London` (AUDUSD=X).

Additional columns in bold are **extra** relative to `_REQUIRED_COLUMNS`.

## Fixture Schema Comparison

Test fixtures (`tests/test_backtest_data_fetcher.py::_make_5y_df`) build a
DataFrame with exactly these columns:

```
['Open', 'High', 'Low', 'Close', 'Volume']
```

Live yfinance returns these 8 columns:

```
['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume', 'Dividends', 'Stock Splits']
```

**Missing vs fixture:** none — all 5 required columns are present.
**Extra vs fixture:** `Adj Close`, `Dividends`, `Stock Splits`.

`_REQUIRED_COLUMNS = frozenset({'Open', 'High', 'Low', 'Close', 'Volume'})` guard in
`data_fetcher._fetch_yfinance` passes cleanly. No `DataFetchError` raised.
**Branch (a) schema change: FALSE** — the schema has extra columns but not missing ones.
The code only needs the 5 required columns and ignores extras.

## RVol Diagnostic

RVol computation in `signal_engine._rvol()` uses `close.pct_change().rolling(period).std() * sqrt(252)`.
Manual re-computation matches engine output to full float64 precision at every bar.

First 10 bars after warmup (AXJO, index 38–47):

| Bar | Date | ADX | RVol (manual) | RVol (engine) | Match |
|-----|------|-----|---------------|---------------|-------|
| 38 | 2021-07-02 | 12.70 | 0.1063 | 0.1063 | YES |
| 39 | 2021-07-05 | 12.29 | 0.1050 | 0.1050 | YES |
| 40 | 2021-07-06 | 11.83 | 0.1081 | 0.1081 | YES |
| 41 | 2021-07-07 | 11.44 | 0.1127 | 0.1127 | YES |
| 42 | 2021-07-08 | 11.08 | 0.1121 | 0.1121 | YES |
| 43 | 2021-07-09 | 11.08 | 0.1197 | 0.1197 | YES |
| 44 | 2021-07-12 | 10.89 | 0.1265 | 0.1265 | YES |
| 45 | 2021-07-13 | 10.48 | 0.1220 | 0.1220 | YES |
| 46 | 2021-07-14 | 10.13 | 0.1225 | 0.1225 | YES |
| 47 | 2021-07-15 | 9.83 | 0.1221 | 0.1221 | YES |

RVol computation is correct. **Branch (b) RVol regression: FALSE.**

## Signal Engine Trace

Full bar-by-bar signal count over 1265 AXJO bars with default `settings=None`
(ADX_GATE=25.0, votes_required=2):

| Outcome | Count |
|---------|-------|
| LONG signals | 111 |
| SHORT signals | 65 |
| FLAT — ADX < 25.0 or NaN | 1055 |
| FLAT — ADX ok, < 2 votes | 34 |
| **Total** | **1265** |

ADX distribution (non-NaN, 1227 bars):
- min=7.94, max=36.32, mean=18.51, median=17.35
- **% bars ≥ 25.0: 17.1%**

There ARE 176 non-FLAT signals (111 LONG + 65 SHORT) with ADX_GATE=25. Signal
generation is working. However, **0 trades are opened** despite these signals.

### Why 0 trades despite 176 non-FLAT signals?

`backtest/cli.py::_run_one_instrument` calls:

```python
result = simulate(df, instrument, multiplier, cost_round_trip, initial_account)
```

`simulate()` signature is:

```python
def simulate(df, instrument, multiplier, cost_round_trip_aud, initial_account_aud, settings=None):
```

**`settings=None` is passed.** Inside `_extract_signals(df_ind, settings=None)`,
the gate defaults to `ADX_GATE=25.0` and `votes_required=2` from `system_params`.

Inside `sizing_engine.step()`, `settings` is extracted from `indicators['_settings']`
(which is `None` when `simulate(settings=None)`). `calc_position_size` therefore uses
`DEFAULT_STRATEGY_SETTINGS` with:
- `risk_pct_long = 0.01` (1%)
- `risk_pct_short = 0.005` (0.5%)
- `trail_mult_long = 3.0`, `trail_mult_short = 2.0`
- `one_contract_floor = False` (no floor)

For bar 188 (first non-FLAT bar, signal=SHORT, ADX=25.02):

```
risk_pct       = 0.005 (SHORT)
trail_mult     = 2.0
vol_scale      = clip(0.12 / 0.2057, 0.3, 2.0) = 0.5834
stop_dist      = 2.0 × 101.38 × 5.0 = 1013.85 AUD/contract
n_raw          = (10000 × 0.005 / 1013.85) × 0.5834 = 0.0288
n_contracts    = int(0.0288) = 0
```

`one_contract_floor=False` (default), so SIZE-05 fires: contracts=0, no position opened.

The same applies to LONG signals:
```
n_raw_long = (10000 × 0.01 / 1520.77) × 0.5834 = 0.0384 → int = 0
```

**The $10k account is too small to open even a single SPI200 mini contract at default
risk/trail settings.** Every sizing attempt yields `n_raw < 1.0` → `n_contracts = 0`.

### Comparison with per-market optimal settings

Running `simulate()` with `DEFAULT_STRATEGY_SETTINGS_BY_MARKET['SPI200']`:
- `adx_gate=20.0`, `votes_required=1`, `risk_pct_long=0.05`, `one_contract_floor=True`
- Result: **67 trades, final_account=$23,082.84**

The per-market settings use `one_contract_floor=True` which overrides the SIZE-05 skip
and forces 1 contract even when `n_raw < 1.0`.

## Initial Hypothesis

- **Branch (a) — yfinance schema change:** FALSE. Required columns present. Schema
  has 3 extra columns but none are missing. No `DataFetchError` raised.
- **Branch (b) — RVol regression:** FALSE. RVol matches manual computation exactly
  at every bar. No regression.

**Actual root cause:** `backtest/cli.py` does not pass `settings` to `simulate()`.
The backtest runs with hardcoded `system_params` defaults (`ADX_GATE=25`,
`risk_pct_long=1%`, `risk_pct_short=0.5%`, `one_contract_floor=False`). At $10k
starting equity and SPI200 mini at ~7,000 pts, `n_raw` is always `< 1.0`, and
without `one_contract_floor=True`, every entry attempt produces 0 contracts (SIZE-05).

This is a **Branch (c) missing wiring**: the per-market strategy settings in
`system_params.DEFAULT_STRATEGY_SETTINGS_BY_MARKET` were added in Phase 24 but
were never plumbed into the backtest CLI path.

## Time-Box Status

Estimated hours used: ~1.5h (codebase read 45m, harness + run 30m, trace 15m, doc 20m)

---

## Root Cause Classification

### Branch (a): yfinance schema change — FALSE

Evidence:
- Live fetch (yfinance 1.2.0) returns `['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume', 'Dividends', 'Stock Splits']`.
- `_REQUIRED_COLUMNS = {'Open', 'High', 'Low', 'Close', 'Volume'}` — all present.
- No `DataFetchError` raised in either run. Parquet cache round-trip confirmed (1265 AXJO bars, 1300 AUDUSD bars).
- Extra columns (`Adj Close`, `Dividends`, `Stock Splits`) are silently ignored by `compute_indicators` which only reads `Open/High/Low/Close/Volume`.

### Branch (b): RVol gate regression on live data — FALSE

Evidence:
- `signal_engine._rvol()` manual re-computation matches engine output to full float64 precision at every bar tested (bars 38–47).
- RVol values are non-NaN and non-zero (range ~0.10–0.12 annualised) at the first 10 non-warmup bars.
- `_vol_scale(rvol)` with `rvol≈0.20` gives `vol_scale=0.583` — within the `[0.3, 2.0]` clip range, not at the NaN/degenerate guard.

### Actual root cause: missing settings wiring in backtest CLI — CONFIRMED

`backtest/cli.py::_run_one_instrument` calls `simulate(df, instrument, multiplier, cost, account)` with **no `settings=` argument**. This causes `simulate()` to use `settings=None` throughout, which propagates to:

1. `_extract_signals(df_ind, settings=None)` → ADX gate = 25.0, votes_required = 2 (Phase 1 defaults)
2. `sizing_engine.calc_position_size(settings=None)` → uses `DEFAULT_STRATEGY_SETTINGS` with `risk_pct_long=0.01`, `trail_mult_long=3.0`, `one_contract_floor=False`

At $10k starting equity and SPI200 mini (~7,000 pts):
- stop_dist = 3.0 × ATR(≈100) × 5 = 1,500 AUD/contract
- n_raw = (10,000 × 0.01 / 1,500) × vol_scale ≈ 0.046 → int() = **0**
- `one_contract_floor=False` → SIZE-05: no position opened, warning emitted but not surfaced in the report

Every single entry attempt across 176 non-FLAT signals yields `n_contracts=0`. No trades → equity curve stays flat → FAIL.

### Fix shape: TIGHT

Single fix site: `backtest/cli.py::_run_one_instrument` (line 135). Add
`settings=default_settings_for_market(instrument)` to the `simulate()` call.
The per-market settings (`adx_gate=20`, `votes_required=1`, `one_contract_floor=True`,
`risk_pct_long=5%`) already exist in `system_params.DEFAULT_STRATEGY_SETTINGS_BY_MARKET`
and are imported by the rest of the codebase. No new logic required.

No cache invalidation needed — the parquet files contain correct OHLCV data.
No schema changes required. Fix is localised to `backtest/cli.py` only.
Blast radius: `backtest/cli.py` (1 call site) + `tests/test_backtest_simulator.py`
(may need a settings fixture update to cover the wired path).

## Recommended Branch

**Land in 29-13** — fix is tight, single call site, no new logic.

Rationale:
- The fix is `settings=default_settings_for_market(instrument)` at one call site.
- No data-layer changes, no schema changes, no new constants.
- `default_settings_for_market` already exists, is tested, and is already used by the daily live signal loop.
- Escape to Phase 29.5 would be warranted only if the fix required new backtest methodology decisions (e.g. sweep over multiple settings combinations, new CLI flags, schema bumps). None of those apply here.
- Risk: test coverage for the `settings=` wired path may need a companion update in `tests/test_backtest_simulator.py` and `tests/test_backtest_cli.py`, but both files are straightforward to extend within the 29-13 timebox.
