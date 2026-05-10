---
phase: 29-5-yfinance-regression-fix
reviewed: 2026-05-10T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - backtest/cli.py
  - tests/test_backtest_cli.py
findings:
  critical: 0
  warning: 3
  info: 1
  total: 4
status: issues_found
---

# Phase 29.5: Code Review Report

**Reviewed:** 2026-05-10T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Phase 29.5 wired `settings=system_params.default_settings_for_market(instrument)` into `_run_one_instrument` using a local import (G-45 pattern), and added `TestSettingsWiring` in the test file. The core wiring is correct — `system_params` is imported locally at call time, `default_settings_for_market` is called with the instrument key, and the result is forwarded to `simulate()` via the `settings=` keyword arg. No data loss or security issues found.

Three warnings were found: the `TestSettingsWiring` tests do not actually prove that `settings=` is wired (they would pass even if the kwarg were dropped), `default_settings_for_market` is called without guarding against an unknown instrument key, and `_run_one_instrument` silently ignores several keys that `default_settings_for_market` returns (`direction_mode`, `contract_cap`, `one_contract_floor`, `risk_pct_*`).

## Warnings

### WR-01: TestSettingsWiring does not prove settings= wiring — tests are false-positive safe

**File:** `tests/test_backtest_cli.py:282-306`

**Issue:** Both `test_spi200_produces_nonzero_trades_with_settings` and `test_audusd_produces_nonzero_trades_with_settings` only assert `total_trades > 0`. They use `patched_fetcher_trend` which generates compound-return data that satisfies `Mom1/Mom3/Mom12 > MOM_THRESHOLD` even with the default `settings=None` path (because `votes_required` defaults to 2 which trend data also passes). If someone removes the `settings=settings` kwarg from `_run_one_instrument` entirely, both tests would still pass. The wiring is not isolated — no spy or mock asserts that `simulate()` was called with a non-`None` `settings` argument.

**Fix:** Spy on `backtest.cli.simulate` and assert the `settings` kwarg is present and matches `system_params.default_settings_for_market(instrument)`:

```python
from unittest.mock import patch, call
import system_params

def test_settings_kwarg_forwarded_to_simulate(self, tmp_path, patched_fetcher_trend, monkeypatch):
    calls = []
    real_simulate = backtest.cli.simulate

    def _spy_simulate(df, instrument, multiplier, cost, account, settings=None):
        calls.append((instrument, settings))
        return real_simulate(df, instrument, multiplier, cost, account, settings=settings)

    monkeypatch.setattr('backtest.cli.simulate', _spy_simulate)
    out = tmp_path / 'spy.json'
    run_backtest(RunArgs(years=5, end_date='2026-05-01', output=out))

    instruments_seen = {c[0]: c[1] for c in calls}
    for inst in ('SPI200', 'AUDUSD'):
        expected = system_params.default_settings_for_market(inst)
        assert instruments_seen.get(inst) == expected, (
            f'{inst}: simulate() called with settings={instruments_seen.get(inst)!r}, '
            f'expected {expected!r}'
        )
```

---

### WR-02: _run_one_instrument will KeyError on any instrument not in INSTRUMENT_SYMBOLS / INSTRUMENT_MULTIPLIERS

**File:** `backtest/cli.py:129,134`

**Issue:** Lines 129 and 134 use bare dict subscription on `INSTRUMENT_SYMBOLS` and `INSTRUMENT_MULTIPLIERS`. If `_run_one_instrument` is ever called with an instrument name not in those dicts (e.g., due to a future `run_backtest` extension or a test that passes a bad value), Python raises an unhandled `KeyError` with no useful error message. `default_settings_for_market` (line 136) has a safe fallback via `.get()`, but the two dict lookups above it do not.

**Fix:**

```python
symbol = INSTRUMENT_SYMBOLS.get(instrument)
multiplier = INSTRUMENT_MULTIPLIERS.get(instrument)
if symbol is None or multiplier is None:
    raise ValueError(
        f'Unknown instrument {instrument!r}. '
        f'Valid: {list(INSTRUMENT_SYMBOLS)}'
    )
```

---

### WR-03: settings keys direction_mode, contract_cap, one_contract_floor, risk_pct_* are returned by default_settings_for_market but never consumed by simulate()

**File:** `backtest/cli.py:136` / `backtest/simulator.py:46-49`

**Issue:** `default_settings_for_market('SPI200')` returns eight keys including `direction_mode='long_only'`, `contract_cap=1`, `one_contract_floor=True`, `risk_pct_long=0.05`, `risk_pct_short=0.005`. The simulator's `_extract_signals` only reads `adx_gate`, `momentum_threshold`, and `momentum_votes_required`. The remaining five keys are silently ignored. The SPI200 market is configured as `direction_mode='long_only'` but the simulator has no code to enforce that — it will still generate SHORT signals if the data warrants them. This is a logic gap between the settings contract and the simulator implementation.

**Fix:** Either consume `direction_mode` in `_extract_signals` (or `simulate`):

```python
direction_mode = settings.get('direction_mode', 'both') if settings else 'both'
# ... after computing votes_up / votes_dn:
if votes_up >= votes_required and direction_mode != 'short_only':
    signals.append(LONG)
elif votes_dn >= votes_required and direction_mode != 'long_only':
    signals.append(SHORT)
```

Or document explicitly that those keys are reserved for a future phase, and remove them from `DEFAULT_STRATEGY_SETTINGS_BY_MARKET` until the simulator implements them, to avoid silent no-ops.

---

## Info

### IN-01: Local import inside hot function called twice per backtest run

**File:** `backtest/cli.py:135`

**Issue:** `import system_params` is placed inside `_run_one_instrument`, which is called once for SPI200 and once for AUDUSD per `run_backtest` invocation. Python caches modules in `sys.modules` so repeated imports are cheap, but the pattern is inconsistent: `run_backtest` also does `import system_params` at line 225 for `STRATEGY_VERSION`. The G-45 rationale (avoid kwarg-capture of module-level values) is valid and documented; a cleaner expression is to hoist both local imports into `run_backtest` and pass `settings` as a parameter to `_run_one_instrument`.

**Fix:** Add `settings` as an explicit parameter:

```python
def _run_one_instrument(instrument, start, end, cost_round_trip, initial_account,
                        refresh, settings):
    ...

# in run_backtest:
import system_params
strategy_version = system_params.STRATEGY_VERSION
spi_result = _run_one_instrument(
    'SPI200', ..., settings=system_params.default_settings_for_market('SPI200')
)
audusd_result = _run_one_instrument(
    'AUDUSD', ..., settings=system_params.default_settings_for_market('AUDUSD')
)
```

This keeps the G-45 freshness guarantee (import is still inside `run_backtest`, not at module level), removes the hidden import from a private helper, and makes the data flow explicit.

---

_Reviewed: 2026-05-10T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
