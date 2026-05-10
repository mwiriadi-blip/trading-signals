---
phase: 29-5
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backtest/cli.py
  - tests/test_backtest_cli.py
autonomous: true
requirements:
  - UAT-23-1
must_haves:
  truths:
    - "`python -m backtest --years 5` exits 0 (PASS)"
    - "SPI200 simulation produces > 0 trades over the 5y window"
    - "AUDUSD simulation produces > 0 trades over the 5y window"
    - "`_run_one_instrument` passes per-market settings to `simulate()`"
  artifacts:
    - path: backtest/cli.py
      provides: "Fixed _run_one_instrument passing settings= to simulate()"
      contains: "default_settings_for_market(instrument)"
    - path: tests/test_backtest_cli.py
      provides: "Integration test asserting non-zero trades for both instruments"
      exports: ["TestSettingsWiring"]
  key_links:
    - from: backtest/cli.py
      to: system_params.default_settings_for_market
      via: "import system_params at top of _run_one_instrument body"
      pattern: "default_settings_for_market\\(instrument\\)"
    - from: backtest/cli.py
      to: backtest/simulator.py
      via: "settings= kwarg in simulate() call"
      pattern: "simulate.*settings=.*default_settings_for_market"
---

<objective>
Wire `settings=system_params.default_settings_for_market(instrument)` into
`backtest/cli.py::_run_one_instrument` at the single call site (line 135).

Purpose: Close UAT-23-1. With `settings=None`, `sizing_engine` uses
`one_contract_floor=False` → every SPI200 position sizes to 0 contracts → 0
trades → FAIL exit code. Per-market settings already exist in `system_params`
and are used by the live signal loop; this wires them into the backtest path.

Output:
- `backtest/cli.py` — one argument added to the `simulate()` call; one
  `import system_params` added inside `_run_one_instrument` body.
- `tests/test_backtest_cli.py` — new `TestSettingsWiring` class with two tests
  asserting non-zero trades for both instruments when settings are wired.
</objective>

<execution_context>
@/Users/marcwiriadisastra/.claude/get-shit-done/workflows/execute-plan.md
@/Users/marcwiriadisastra/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md

<interfaces>
<!-- Extracted from source files — no codebase exploration needed. -->

From backtest/simulator.py (line 101):
```python
def simulate(
  df: pd.DataFrame,
  instrument: str,
  multiplier: float,
  cost_round_trip_aud: float,
  initial_account_aud: float,
  settings: dict | None = None,
) -> SimResult:
```

From system_params.py (line 381):
```python
def default_settings_for_market(market_id: str) -> dict:
    '''Per-market optimum strategy settings, falling back to conservative defaults.
    Returns a fresh dict; callers may mutate the returned value.
    '''
```

From backtest/cli.py (line 125–138, the fix site):
```python
def _run_one_instrument(instrument: str, start: str, end: str,
                        cost_round_trip: float, initial_account: float,
                        refresh: bool):
  symbol = INSTRUMENT_SYMBOLS[instrument]
  df = fetch_ohlcv(symbol, start, end, refresh=refresh)
  multiplier = INSTRUMENT_MULTIPLIERS[instrument]
  result = simulate(df, instrument, multiplier, cost_round_trip, initial_account)
  # ^^^ BUG: settings= not passed; simulate() defaults to None
  logger.info('[Backtest] Simulating %s: %d bars, %d trades', ...)
  return result
```

From backtest/cli.py (line 221–223, existing import pattern to follow):
```python
# Fresh STRATEGY_VERSION read at call time (LEARNINGS G-45)
import system_params
strategy_version = system_params.STRATEGY_VERSION
```

From tests/test_backtest_cli.py (existing fixture pattern):
```python
@pytest.fixture
def patched_fetcher(monkeypatch):
  def _fake_fetch(symbol, start, end, refresh=False, cache_dir=None, min_years=5):
    return _bull_5y_df()
  monkeypatch.setattr('backtest.cli.fetch_ohlcv', _fake_fetch)
  return _fake_fetch
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Wire settings= into _run_one_instrument</name>
  <files>backtest/cli.py</files>

  <read_first>
    - `backtest/cli.py` — read the full file; the fix site is line 135 and the
      existing import pattern is at line 221-223.
    - `system_params.py` lines 381-390 — confirm `default_settings_for_market`
      signature and that it takes `market_id: str`.
  </read_first>

  <behavior>
    - After fix: `simulate()` is called with `settings=system_params.default_settings_for_market(instrument)`.
    - `import system_params` is present inside `_run_one_instrument` body, before the `simulate()` call (following LEARNINGS G-45 fresh-read pattern used at line 221).
    - The rest of `_run_one_instrument` is unchanged.
  </behavior>

  <action>
Edit `backtest/cli.py` — two changes inside `_run_one_instrument` only:

1. After the line `multiplier = INSTRUMENT_MULTIPLIERS[instrument]`, add:
   ```python
   import system_params
   settings = system_params.default_settings_for_market(instrument)
   ```

2. Change the `simulate()` call from:
   ```python
   result = simulate(df, instrument, multiplier, cost_round_trip, initial_account)
   ```
   to:
   ```python
   result = simulate(df, instrument, multiplier, cost_round_trip, initial_account,
                     settings=settings)
   ```

No other lines in the file change. Do NOT add a module-level import of
`system_params` — use the local import pattern (LEARNINGS G-45) consistent with
the existing `run_backtest()` pattern at line 221.
  </action>

  <verify>
    <automated>grep -n "default_settings_for_market" /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/backtest/cli.py</automated>
  </verify>

  <acceptance_criteria>
    - `grep -n "default_settings_for_market(instrument)" backtest/cli.py` returns exactly 1 match inside `_run_one_instrument`.
    - `grep -n "import system_params" backtest/cli.py` returns a match inside the `_run_one_instrument` function body (indented, not at module level).
    - `grep -n "settings=settings" backtest/cli.py` returns exactly 1 match on the `simulate(...)` call line.
    - The `simulate(` call in `_run_one_instrument` is the ONLY one in the file; verify with `grep -c "simulate(" backtest/cli.py` — must still be 1.
    - File line count does not exceed 500: `wc -l backtest/cli.py | awk '{print $1}'` — must be <= 500.
  </acceptance_criteria>

  <done>
`_run_one_instrument` calls `simulate(..., settings=system_params.default_settings_for_market(instrument))`. No module-level import added. File under 500 LOC.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add TestSettingsWiring integration tests</name>
  <files>tests/test_backtest_cli.py</files>

  <read_first>
    - `tests/test_backtest_cli.py` — read the full file to understand existing
      fixture patterns (`patched_fetcher`, `_bull_5y_df`) and class naming.
    - `backtest/cli.py` — confirm `_run_one_instrument` signature after Task 1.
  </read_first>

  <behavior>
    - `test_spi200_produces_nonzero_trades_with_settings`: calls `run_backtest`
      with bull data stubbed; asserts `report['metrics']['SPI200']['total_trades'] > 0`.
    - `test_audusd_produces_nonzero_trades_with_settings`: same pattern for AUDUSD.
    - Both tests use the existing `patched_fetcher` fixture (bull 5y df).
    - Both tests must PASS after Task 1 is applied (green from the start — these
      are regression-guard tests, not red-first TDD in this instance, because the
      fix in Task 1 already makes them green).
  </behavior>

  <action>
Append a new test class `TestSettingsWiring` at the END of
`tests/test_backtest_cli.py` (after `TestStrategyVersionTagging`):

```python
class TestSettingsWiring:
  """UAT-23-1 regression guard: _run_one_instrument must pass per-market
  settings to simulate(), producing non-zero trades for both instruments."""

  def test_spi200_produces_nonzero_trades_with_settings(
      self, tmp_path, patched_fetcher
  ):
    out = tmp_path / 'spi_wiring.json'
    args = RunArgs(years=5, end_date='2026-05-01', output=out)
    report, _, _ = run_backtest(args)
    spi_trades = report['metrics']['SPI200']['total_trades']
    assert spi_trades > 0, (
      f'SPI200 must produce >0 trades when per-market settings are wired; '
      f'got {spi_trades}. This likely means settings= was not passed to '
      f'simulate() in _run_one_instrument (UAT-23-1 regression).'
    )

  def test_audusd_produces_nonzero_trades_with_settings(
      self, tmp_path, patched_fetcher
  ):
    out = tmp_path / 'audusd_wiring.json'
    args = RunArgs(years=5, end_date='2026-05-01', output=out)
    report, _, _ = run_backtest(args)
    audusd_trades = report['metrics']['AUDUSD']['total_trades']
    assert audusd_trades > 0, (
      f'AUDUSD must produce >0 trades when per-market settings are wired; '
      f'got {audusd_trades}. This likely means settings= was not passed to '
      f'simulate() in _run_one_instrument (UAT-23-1 regression).'
    )
```

Do NOT modify any existing test. Append only.
  </action>

  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -m pytest tests/test_backtest_cli.py::TestSettingsWiring -v 2>&1 | tail -20</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "TestSettingsWiring" tests/test_backtest_cli.py` returns 1.
    - `python -m pytest tests/test_backtest_cli.py::TestSettingsWiring -v` exits 0 with both tests PASSED.
    - `python -m pytest tests/test_backtest_cli.py -v` exits 0 — no regressions in existing tests.
    - File line count does not exceed 500: `wc -l tests/test_backtest_cli.py | awk '{print $1}'` — must be <= 500.
  </acceptance_criteria>

  <done>
`TestSettingsWiring` class present with two passing tests. Full test suite still green.
  </done>
</task>

<task type="auto">
  <name>Task 3: Acceptance gate — run backtest against cached parquet</name>
  <files></files>

  <read_first>
    - `.planning/backtests/data/` — confirm both parquet files are present:
      `^AXJO-2021-05-10-2026-05-10.parquet` and `AUDUSD=X-2021-05-10-2026-05-10.parquet`.
  </read_first>

  <action>
Run the acceptance gate command using cached parquet (no yfinance hit):

```bash
cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals
python -m backtest --years 5 --end-date 2026-05-10 2>&1
echo "Exit code: $?"
```

The `--end-date 2026-05-10` combined with `--years 5` produces a start of
`2021-05-10`, matching the cached parquet filenames exactly. The data_fetcher
will find the cache and skip yfinance. Do NOT pass `--refresh`.

Observe the log output. The PASS/FAIL verdict line and trade counts confirm UAT-23-1 status.

If the command exits 1 (FAIL), do NOT proceed — re-examine Task 1 to ensure
`settings=` was wired correctly and the import path is `system_params.default_settings_for_market`.
  </action>

  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -m backtest --years 5 --end-date 2026-05-10; echo "EXIT:$?"</automated>
  </verify>

  <acceptance_criteria>
    - Command exits with code 0 (PASS). The final line of `echo "EXIT:$?"` must be `EXIT:0`.
    - Log output contains `[Backtest] Simulating SPI200: ... trades` with a trade count > 0.
    - Log output contains `[Backtest] Simulating AUDUSD: ... trades` with a trade count > 0.
    - Log output contains `[Backtest] PASS` (not `[Backtest] FAIL`).
    - UAT-23-1 is closed. Record the trade counts and final combined return in the SUMMARY.
  </acceptance_criteria>

  <done>
`python -m backtest --years 5` exits 0. SPI200 and AUDUSD each have >0 trades. UAT-23-1 closed.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| CLI args → run_backtest | User-supplied --years, --end-date validated by argparse; no new surface added |
| parquet cache → simulator | Cached OHLCV data read; no change to data layer |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-29.5-01 | Tampering | system_params.py — DEFAULT_STRATEGY_SETTINGS_BY_MARKET | accept | Read-only at call time; no user input touches this dict. Local import in _run_one_instrument is a fresh read but from a trusted module file. |
| T-29.5-02 | Information Disclosure | backtest JSON output | accept | JSON written to .planning/backtests/ — local filesystem only, no network path. No PII. |
</threat_model>

<verification>
Full test suite must pass:

```bash
cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals
python -m pytest tests/test_backtest_cli.py tests/test_backtest_simulator.py -v
```

Acceptance gate:

```bash
python -m backtest --years 5 --end-date 2026-05-10
echo "Exit: $?"
```

Must print `[Backtest] PASS` and exit 0.
</verification>

<success_criteria>
- `backtest/cli.py::_run_one_instrument` passes `settings=system_params.default_settings_for_market(instrument)` to `simulate()`.
- `tests/test_backtest_cli.py::TestSettingsWiring` has two passing tests asserting non-zero trades for SPI200 and AUDUSD.
- `python -m backtest --years 5 --end-date 2026-05-10` exits 0.
- All pre-existing tests in `test_backtest_cli.py` still pass.
- UAT-23-1 is closed.
</success_criteria>

<output>
After completion, create `.planning/phases/29-5-yfinance-regression-fix/29-5-01-SUMMARY.md` with:
- Fix applied (exact lines changed)
- Trade counts observed: SPI200 N trades, AUDUSD N trades
- Final combined cumulative return and PASS verdict
- UAT-23-1 closure confirmation
</output>
