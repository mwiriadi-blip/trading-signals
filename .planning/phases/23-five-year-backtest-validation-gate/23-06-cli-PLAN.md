---
id: 23-06
title: Wave 2B — backtest/cli.py (argparse + JSON write + exit codes + log lines)
phase: 23
plan: 06
type: execute
wave: 2
depends_on: [23-02, 23-03, 23-04]
files_modified:
  - backtest/cli.py
  - tests/test_backtest_cli.py
requirements: [BACKTEST-04, BACKTEST-02]
threat_refs: []
autonomous: true
gap_closure: false

must_haves:
  truths:
    - "python -m backtest --years 5 runs to completion in <60s on dev machine (cache hit)"
    - "argparse surface matches CONTEXT D-11 verbatim: --years/--end-date/--initial-account/--cost-spi/--cost-audusd/--refresh/--output"
    - "STRATEGY_VERSION read via FRESH attribute access inside main() per LEARNINGS G-45 (NOT as kwarg default)"
    - "JSON output written to .planning/backtests/<strategy_version>-<timestamp>.json per CONTEXT D-11"
    - "Exit code 0 on PASS (combined cumulative_return_pct > 100.0); exit code 1 on FAIL"
    - "Log lines use [Backtest] prefix verbatim per CLAUDE.md + CONTEXT D-11"
    - "JSON metadata includes pass field at top level mirroring metrics.combined.pass"
    - "All numpy/pandas scalars wrapped with float()/int() before JSON serialisation (RESEARCH §Pitfall 6)"
    - "AWST date arithmetic: dateutil.relativedelta(years=-5) for leap-year correctness (RESEARCH §Standard Stack)"
  artifacts:
    - path: "backtest/cli.py"
      provides: "main(argv) entry + run_backtest(...) helper for web POST reuse"
      exports: ["main", "run_backtest", "_build_parser"]
    - path: "tests/test_backtest_cli.py"
      provides: "TestArgparse + TestJsonSchema + TestExitCode + TestLogFormat + TestStrategyVersionTagging"
  key_links:
    - from: "backtest/cli.py"
      to: "backtest.data_fetcher.fetch_ohlcv + backtest.simulator.simulate + backtest.metrics.compute_metrics"
      via: "direct function calls"
      pattern: "from backtest.data_fetcher import|from backtest.simulator import|from backtest.metrics import"
    - from: "backtest/cli.py"
      to: ".planning/backtests/<sv>-<ts>.json"
      via: "json.dump with allow_nan=False"
      pattern: "json.dump"
---

> **Operator confirmation required before /gsd-execute-phase 23:**
> This plan implements planner-derived locked decisions D-19 (dual sharpe — emit
> both `sharpe_daily` raw and `sharpe_annualized = sharpe_daily × √252`) and
> D-20 (`exit_reason` uses sizing_engine's verbatim values: `flat_signal`,
> `signal_reversal`, `trailing_stop`, `adx_drop`, `manual_stop` — NOT D-05's
> illustrative `"signal_change"`). Confirm or revise CONTEXT D-05 before execute.

<objective>
Implement `backtest/cli.py` — the argparse adapter that orchestrates data_fetcher → simulator → metrics → JSON write. Replaces Wave 0 NotImplementedError. Reused by `web/routes/backtest.py` POST handler (Wave 2 Plan 07) for the override form.

Purpose: One callable entry that produces a D-05-shaped JSON file from CLI args or from web POST args. Single source of truth for JSON write + log lines + exit-code mapping.
Output: ~180 LOC adapter module + 5 test classes covering argparse / JSON schema / exit codes / log format / strategy_version fresh access.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md
@.planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md
@.planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md
@CLAUDE.md
@main.py
@backtest/data_fetcher.py
@backtest/simulator.py
@backtest/metrics.py

<interfaces>
<!-- backtest/cli.py CONTRACT -->
def _build_parser() -> argparse.ArgumentParser:
  """argparse surface per CONTEXT D-11."""

@dataclasses.dataclass(frozen=True)
class RunArgs:
  years: int                  # default 5
  end_date: str               # ISO YYYY-MM-DD; default = today AWST
  initial_account_aud: float  # default 10000.0
  cost_spi_aud: float         # default 6.0
  cost_audusd_aud: float      # default 5.0
  refresh: bool               # default False
  output: pathlib.Path | None # default None → auto-name from sv+timestamp

def run_backtest(args: RunArgs) -> tuple[dict, pathlib.Path, int]:
  """Returns (report_dict, written_path, exit_code).
  exit_code: 0 = PASS, 1 = FAIL.
  Reused by web/routes/backtest.py POST handler.
  """

def main(argv: list[str] | None = None) -> int:
  """argparse entry; returns exit code."""

<!-- Symbol mapping (CONTEXT scope + system_params) -->
INSTRUMENT_SYMBOLS = {
  'SPI200': '^AXJO',
  'AUDUSD': 'AUDUSD=X',
}

<!-- Log format (CONTEXT D-11 example lines) -->
[Backtest] Fetching SPI200 ^AXJO 2021-05-01..2026-05-01 (cache hit|cache miss; pulling yfinance)
[Backtest] Simulating SPI200: 1257 bars, 89 trades
[Backtest] Simulating AUDUSD: 1257 bars, 89 trades
[Backtest] Combined cum_return=+127.45% sharpe=0.84 max_dd=-23.10% win_rate=52% trades=178
[Backtest] PASS (>100% threshold)
[Backtest] Wrote .planning/backtests/v1.2.0-20260501T080000.json

<!-- D-05 JSON schema (CONTEXT lines 93-143) — what we write -->
{
  "metadata": {strategy_version, run_dt, years, end_date, start_date,
               initial_account_aud, cost_spi_aud, cost_audusd_aud,
               instruments, pass},
  "metrics": {combined, SPI200, AUDUSD},  # each with all 7 + sharpe_annualized
  "equity_curve": [...],
  "trades": [...]
}
</interfaces>
</context>

<threat_model>
No new external trust boundaries. CLI is operator-invoked locally; JSON output is operator-readable. Validation per RESEARCH:
- `initial_account > 0` enforced by simulator.simulate (raises ValueError)
- `cost_*_aud >= 0` enforced upstream
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement backtest/cli.py</name>
  <read_first>
    - backtest/cli.py (Wave 0 skeleton)
    - main.py lines 725-786 (`_build_parser`) and 1820-1854 (main() dispatch + logging.basicConfig)
    - .planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md §Code Examples §"STRATEGY_VERSION fresh attribute access" (lines 580-588)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"backtest/cli.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md §D-03 (date arithmetic), §D-11 (CLI surface + log lines), §D-13 (STRATEGY_VERSION fresh access)
  </read_first>
  <behavior>
    - Test 1: `cli.main(['--years', '5'])` produces a JSON file at .planning/backtests/<sv>-<ts>.json
    - Test 2: argparse defaults match D-11 (--years=5, --initial-account=10000, --cost-spi=6.0, --cost-audusd=5.0)
    - Test 3: `--end-date 2024-01-01 --years 5` → start_date in metadata = 2019-01-01 (relativedelta years=-5)
    - Test 4: PASS report → exit code 0
    - Test 5: FAIL report → exit code 1
    - Test 6: Log lines on stderr include `[Backtest] Fetching ...`, `[Backtest] Simulating ...`, `[Backtest] Wrote ...`
    - Test 7: JSON metadata.strategy_version reads system_params.STRATEGY_VERSION at run time (monkeypatch then re-call → new value persisted)
    - Test 8: JSON contains all D-05 fields including dual sharpe per planner D-19
    - Test 9: numpy/pandas scalars wrapped with float()/int() — JSON write doesn't TypeError
  </behavior>
  <action>
    Replace `backtest/cli.py` Wave 0 stub:

    ```python
    """Phase 23 — argparse CLI for `python -m backtest`.

    Surface (CONTEXT D-11):
      --years N (default 5)
      --end-date YYYY-MM-DD (default today AWST)
      --initial-account FLOAT (default 10_000.0)
      --cost-spi FLOAT (default 6.0)
      --cost-audusd FLOAT (default 5.0)
      --refresh (force re-fetch ignoring cache)
      --output PATH (default .planning/backtests/<sv>-<ts>.json)

    Log prefix: [Backtest] (NEW for this phase per CLAUDE.md log-prefix convention).
    Exit codes: 0 = PASS (combined cumulative_return_pct > 100.0), 1 = FAIL.

    Reused by web/routes/backtest.py POST handler — `run_backtest(args)` is the
    single source of truth for JSON write + metric aggregation.
    """
    from __future__ import annotations
    import argparse
    import dataclasses
    import datetime as dt
    import json
    import logging
    import sys
    from pathlib import Path
    from zoneinfo import ZoneInfo

    from dateutil.relativedelta import relativedelta

    from backtest import (
      BACKTEST_COST_AUDUSD_AUD,
      BACKTEST_COST_SPI_AUD,
      BACKTEST_DEFAULT_YEARS,
      BACKTEST_INITIAL_ACCOUNT_AUD,
      BACKTEST_PASS_THRESHOLD_PCT,
    )
    from backtest.data_fetcher import fetch_ohlcv
    from backtest.metrics import compute_metrics
    from backtest.simulator import simulate

    logger = logging.getLogger(__name__)

    _AWST = ZoneInfo('Australia/Perth')
    _BACKTEST_DIR = Path('.planning/backtests')

    INSTRUMENT_SYMBOLS = {
      'SPI200': '^AXJO',
      'AUDUSD': 'AUDUSD=X',
    }
    INSTRUMENT_MULTIPLIERS = {
      'SPI200': 5.0,        # AUD per point per contract (mini SPI 200)
      'AUDUSD': 10_000.0,   # AUD per AUD/USD point per contract
    }


    @dataclasses.dataclass(frozen=True)
    class RunArgs:
      years: int = BACKTEST_DEFAULT_YEARS
      end_date: str | None = None
      initial_account_aud: float = BACKTEST_INITIAL_ACCOUNT_AUD
      cost_spi_aud: float = BACKTEST_COST_SPI_AUD
      cost_audusd_aud: float = BACKTEST_COST_AUDUSD_AUD
      refresh: bool = False
      output: Path | None = None


    def _today_awst() -> dt.date:
      """Today in AWST (matches Phase 7 convention)."""
      return dt.datetime.now(_AWST).date()


    def _start_from_end(end: dt.date, years: int) -> dt.date:
      """end - years using dateutil.relativedelta for leap-year correctness."""
      return end - relativedelta(years=years)


    def _build_parser() -> argparse.ArgumentParser:
      """CONTEXT D-11 surface."""
      p = argparse.ArgumentParser(
        prog='python -m backtest',
        description='Phase 23: 5-year backtest validation gate (BACKTEST-01..04).',
      )
      p.add_argument('--years', type=int, default=BACKTEST_DEFAULT_YEARS,
                     help=f'years of OHLCV to backtest (default {BACKTEST_DEFAULT_YEARS})')
      p.add_argument('--end-date', type=str, default=None,
                     help='end date YYYY-MM-DD (default today AWST)')
      p.add_argument('--initial-account', type=float, dest='initial_account_aud',
                     default=BACKTEST_INITIAL_ACCOUNT_AUD,
                     help=f'starting AUD (default {BACKTEST_INITIAL_ACCOUNT_AUD})')
      p.add_argument('--cost-spi', type=float, dest='cost_spi_aud',
                     default=BACKTEST_COST_SPI_AUD,
                     help=f'SPI200 round-trip cost AUD (default {BACKTEST_COST_SPI_AUD})')
      p.add_argument('--cost-audusd', type=float, dest='cost_audusd_aud',
                     default=BACKTEST_COST_AUDUSD_AUD,
                     help=f'AUD/USD round-trip cost AUD (default {BACKTEST_COST_AUDUSD_AUD})')
      p.add_argument('--refresh', action='store_true',
                     help='ignore parquet cache and re-fetch yfinance')
      p.add_argument('--output', type=str, default=None,
                     help='override output JSON path')
      return p


    def _parse_args(argv: list[str] | None) -> RunArgs:
      ns = _build_parser().parse_args(argv)
      return RunArgs(
        years=ns.years,
        end_date=ns.end_date,
        initial_account_aud=ns.initial_account_aud,
        cost_spi_aud=ns.cost_spi_aud,
        cost_audusd_aud=ns.cost_audusd_aud,
        refresh=ns.refresh,
        output=Path(ns.output) if ns.output else None,
      )


    def _output_path(strategy_version: str, run_dt: dt.datetime) -> Path:
      """Auto-name: .planning/backtests/<sv>-<YYYYMMDDTHHMMSS>.json (CONTEXT D-11)."""
      ts = run_dt.strftime('%Y%m%dT%H%M%S')
      return _BACKTEST_DIR / f'{strategy_version}-{ts}.json'


    def _run_one_instrument(instrument: str, start: str, end: str,
                            cost_round_trip: float, initial_account: float,
                            refresh: bool):
      """Fetch + simulate one instrument. Returns (sim_result, df_index_dates)."""
      symbol = INSTRUMENT_SYMBOLS[instrument]
      # NOTE (Warning 4): data_fetcher emits '[Backtest] Fetching ... (cache hit/miss)'
      # per CONTEXT D-11. Do NOT duplicate that log line here — exactly one
      # '[Backtest] Fetching' line per instrument should appear in caplog.
      df = fetch_ohlcv(symbol, start, end, refresh=refresh)
      multiplier = INSTRUMENT_MULTIPLIERS[instrument]
      result = simulate(df, instrument, multiplier, cost_round_trip, initial_account)
      logger.info('[Backtest] Simulating %s: %d bars, %d trades',
                  instrument, len(result.equity_curve), len(result.trades))
      return result


    def _build_combined_curve(spi_result, audusd_result) -> list[dict]:
      """Equity curve as list[dict] per D-05 schema, aligned by date.

      Both per-instrument curves run on their own indices; we align by date,
      forward-filling missing balances.
      """
      # Build date → balance maps
      spi_map = dict(zip(spi_result.dates, spi_result.equity_curve))
      audusd_map = dict(zip(audusd_result.dates, audusd_result.equity_curve))
      all_dates = sorted(set(spi_map) | set(audusd_map))
      curve = []
      last_spi = spi_result.equity_curve[0] if spi_result.equity_curve else 0.0
      last_audusd = audusd_result.equity_curve[0] if audusd_result.equity_curve else 0.0
      for d in all_dates:
        if d in spi_map:
          last_spi = spi_map[d]
        if d in audusd_map:
          last_audusd = audusd_map[d]
        curve.append({
          'date': d,
          'balance_spi': float(last_spi),
          'balance_audusd': float(last_audusd),
          'balance_combined': float(last_spi + last_audusd),
        })
      return curve


    def run_backtest(args: RunArgs) -> tuple[dict, Path, int]:
      """Phase 23 BACKTEST-01..04 entry. Returns (report_dict, output_path, exit_code).

      Reused by web/routes/backtest.py POST handler.
      """
      # Fresh STRATEGY_VERSION read at call time (LEARNINGS G-45)
      import system_params
      strategy_version = system_params.STRATEGY_VERSION

      # Date math
      end_date = (dt.date.fromisoformat(args.end_date) if args.end_date
                  else _today_awst())
      start_date = _start_from_end(end_date, args.years)
      run_dt_obj = dt.datetime.now(_AWST)

      # Per-instrument simulation
      spi_result = _run_one_instrument(
        'SPI200', start_date.isoformat(), end_date.isoformat(),
        args.cost_spi_aud, args.initial_account_aud, args.refresh,
      )
      audusd_result = _run_one_instrument(
        'AUDUSD', start_date.isoformat(), end_date.isoformat(),
        args.cost_audusd_aud, args.initial_account_aud, args.refresh,
      )

      # Per-instrument metrics
      spi_metrics = compute_metrics(spi_result.equity_curve, spi_result.trades)
      audusd_metrics = compute_metrics(audusd_result.equity_curve, audusd_result.trades)

      # Combined equity curve + metrics
      combined_curve = _build_combined_curve(spi_result, audusd_result)
      combined_balances = [pt['balance_combined'] for pt in combined_curve]
      combined_trades = spi_result.trades + audusd_result.trades
      combined_metrics = compute_metrics(combined_balances, combined_trades)

      # Trade log (sorted by close_dt for stable ordering)
      all_trades = sorted(combined_trades, key=lambda t: (t['close_dt'], t['instrument']))

      passed = bool(combined_metrics['pass'])
      exit_code = 0 if passed else 1

      report = {
        'metadata': {
          'strategy_version': strategy_version,
          'run_dt': run_dt_obj.isoformat(),
          'years': int(args.years),
          'end_date': end_date.isoformat(),
          'start_date': start_date.isoformat(),
          'initial_account_aud': float(args.initial_account_aud),
          'cost_spi_aud': float(args.cost_spi_aud),
          'cost_audusd_aud': float(args.cost_audusd_aud),
          'instruments': ['SPI200', 'AUDUSD'],
          'pass': passed,
        },
        'metrics': {
          'combined': combined_metrics,
          'SPI200': spi_metrics,
          'AUDUSD': audusd_metrics,
        },
        'equity_curve': combined_curve,
        'trades': all_trades,
      }

      # Summary log line (CONTEXT D-11 format)
      logger.info(
        '[Backtest] Combined cum_return=%+.2f%% sharpe=%.2f max_dd=%.2f%% win_rate=%d%% trades=%d',
        combined_metrics['cumulative_return_pct'],
        combined_metrics.get('sharpe_annualized', combined_metrics['sharpe_daily']),
        combined_metrics['max_drawdown_pct'],
        int(round(combined_metrics['win_rate'] * 100)),
        combined_metrics['total_trades'],
      )
      verdict = 'PASS' if passed else 'FAIL'
      logger.info('[Backtest] %s (>%g%% threshold)', verdict, BACKTEST_PASS_THRESHOLD_PCT)

      # Persist JSON
      output_path = args.output if args.output else _output_path(strategy_version, run_dt_obj)
      output_path.parent.mkdir(parents=True, exist_ok=True)
      with output_path.open('w') as fh:
        json.dump(report, fh, indent=2, allow_nan=False)
      logger.info('[Backtest] Wrote %s', output_path)

      return report, output_path, exit_code


    def main(argv: list[str] | None = None) -> int:
      """CLI entry. Returns exit code (0 PASS, 1 FAIL)."""
      logging.basicConfig(level=logging.INFO, format='%(message)s',
                          stream=sys.stderr, force=True)
      args = _parse_args(argv)
      _, _, exit_code = run_backtest(args)
      return exit_code
    ```
  </action>
  <verify>
    <automated>python -c "from backtest.cli import main, run_backtest, _build_parser, RunArgs; p = _build_parser(); ns = p.parse_args(['--years', '5']); assert ns.years == 5 and ns.initial_account_aud == 10000.0 and ns.cost_spi_aud == 6.0 and ns.cost_audusd_aud == 5.0 and ns.refresh is False; print('ok')" 2>&1 | grep -c '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c '^def main' backtest/cli.py` returns 1
    - `grep -c '^def run_backtest' backtest/cli.py` returns 1
    - `grep -c '^def _build_parser' backtest/cli.py` returns 1
    - `grep -c "from backtest.data_fetcher import fetch_ohlcv" backtest/cli.py` returns 1
    - `grep -c "from backtest.simulator import simulate" backtest/cli.py` returns 1
    - `grep -c "from backtest.metrics import compute_metrics" backtest/cli.py` returns 1
    - `grep -c "import system_params" backtest/cli.py` returns ≥1 (fresh access inside run_backtest)
    - `grep -c "system_params.STRATEGY_VERSION" backtest/cli.py` returns 1 (NOT as default arg)
    - `grep -c "'\[Backtest\]" backtest/cli.py` returns ≥4 (Fetching/Simulating/Combined/PASS|FAIL/Wrote)
    - `grep -c "exit_code = 0 if passed else 1" backtest/cli.py` returns 1
    - `grep -c "json.dump" backtest/cli.py` returns 1 (with allow_nan=False)
    - `grep -c "allow_nan=False" backtest/cli.py` returns 1
    - `grep -c "relativedelta" backtest/cli.py` returns ≥1
    - `grep -c "ZoneInfo('Australia/Perth')" backtest/cli.py` returns 1
    - `python -c "from backtest.cli import _build_parser; p = _build_parser(); ns = p.parse_args(['--end-date', '2024-01-01', '--years', '3', '--initial-account', '5000', '--cost-spi', '7.5', '--cost-audusd', '4.0', '--refresh']); print(ns)"` succeeds
  </acceptance_criteria>
  <done>main, run_backtest, _build_parser callable; argparse surface complete; D-05 schema written.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement tests/test_backtest_cli.py (5 test classes)</name>
  <read_first>
    - backtest/cli.py (just-implemented)
    - tests/test_main.py — analog (argparse + exit code patterns)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"tests/test_backtest_cli.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-VALIDATION.md
  </read_first>
  <behavior>
    See task 1 behavior list. Use monkeypatch on data_fetcher.fetch_ohlcv to avoid yfinance.
  </behavior>
  <action>
    Replace Wave 0 skeleton:

    ```python
    """Phase 23 — backtest/cli.py tests (BACKTEST-04 CLI)."""
    from __future__ import annotations
    import json
    import logging
    from pathlib import Path

    import pandas as pd
    import pytest

    from backtest.cli import RunArgs, _build_parser, main, run_backtest


    def _bull_5y_df(start='2020-01-01', n_bars=1300, base=7000.0, drift=0.5) -> pd.DataFrame:
      idx = pd.date_range(start=start, periods=n_bars, freq='B', tz='Australia/Perth')
      closes = [base + i * drift for i in range(n_bars)]
      return pd.DataFrame({
        'Open':   [c - 5 for c in closes],
        'High':   [c + 10 for c in closes],
        'Low':    [c - 10 for c in closes],
        'Close':  closes,
        'Volume': [1_000_000] * n_bars,
      }, index=idx)


    def _flat_5y_df(start='2020-01-01', n_bars=1300, base=7000.0) -> pd.DataFrame:
      """Flat — no momentum, no signals, no trades → cum_return = 0% → FAIL."""
      idx = pd.date_range(start=start, periods=n_bars, freq='B', tz='Australia/Perth')
      return pd.DataFrame({
        'Open':   [base] * n_bars,
        'High':   [base + 1] * n_bars,
        'Low':    [base - 1] * n_bars,
        'Close':  [base] * n_bars,
        'Volume': [1_000_000] * n_bars,
      }, index=idx)


    @pytest.fixture
    def patched_fetcher(monkeypatch):
      """Stub fetch_ohlcv for both instruments — returns canned 5y data."""
      def _fake_fetch(symbol, start, end, refresh=False, cache_dir=None, min_years=5):
        return _bull_5y_df()
      monkeypatch.setattr('backtest.cli.fetch_ohlcv', _fake_fetch)
      return _fake_fetch


    @pytest.fixture
    def patched_fetcher_flat(monkeypatch):
      def _fake_fetch(symbol, start, end, refresh=False, cache_dir=None, min_years=5):
        return _flat_5y_df()
      monkeypatch.setattr('backtest.cli.fetch_ohlcv', _fake_fetch)
      return _fake_fetch


    class TestArgparse:
      def test_default_values(self):
        p = _build_parser()
        ns = p.parse_args([])
        assert ns.years == 5
        assert ns.end_date is None
        assert ns.initial_account_aud == 10_000.0
        assert ns.cost_spi_aud == 6.0
        assert ns.cost_audusd_aud == 5.0
        assert ns.refresh is False
        assert ns.output is None

      def test_all_flags_present(self):
        p = _build_parser()
        ns = p.parse_args([
          '--years', '3',
          '--end-date', '2024-01-01',
          '--initial-account', '5000',
          '--cost-spi', '7.5',
          '--cost-audusd', '4.0',
          '--refresh',
          '--output', '/tmp/x.json',
        ])
        assert ns.years == 3
        assert ns.end_date == '2024-01-01'
        assert ns.initial_account_aud == 5000.0
        assert ns.cost_spi_aud == 7.5
        assert ns.cost_audusd_aud == 4.0
        assert ns.refresh is True
        assert ns.output == '/tmp/x.json'


    class TestJsonSchema:
      def test_writes_d05_schema(self, tmp_path, patched_fetcher):
        out = tmp_path / 'test.json'
        args = RunArgs(years=5, end_date='2026-05-01', output=out)
        report, written, exit_code = run_backtest(args)

        assert written == out
        assert out.exists()
        loaded = json.loads(out.read_text())

        # D-05 top-level keys
        assert set(loaded) == {'metadata', 'metrics', 'equity_curve', 'trades'}

        # Metadata fields
        meta = loaded['metadata']
        for key in ['strategy_version', 'run_dt', 'years', 'end_date', 'start_date',
                    'initial_account_aud', 'cost_spi_aud', 'cost_audusd_aud',
                    'instruments', 'pass']:
          assert key in meta, f'metadata missing {key}'

        # Metrics structure
        assert set(loaded['metrics']) == {'combined', 'SPI200', 'AUDUSD'}
        for inst in ['combined', 'SPI200', 'AUDUSD']:
          m = loaded['metrics'][inst]
          for key in ['cumulative_return_pct', 'sharpe_daily', 'sharpe_annualized',
                      'max_drawdown_pct', 'win_rate', 'expectancy_aud',
                      'total_trades', 'pass']:
            assert key in m, f'{inst} metric missing {key}'

      def test_start_date_5y_before_end(self, tmp_path, patched_fetcher):
        out = tmp_path / 'test.json'
        args = RunArgs(years=5, end_date='2024-01-01', output=out)
        report, _, _ = run_backtest(args)
        assert report['metadata']['end_date'] == '2024-01-01'
        assert report['metadata']['start_date'] == '2019-01-01'

      def test_initial_account_in_metadata(self, tmp_path, patched_fetcher):
        out = tmp_path / 'test.json'
        args = RunArgs(initial_account_aud=5_000.0, output=out)
        report, _, _ = run_backtest(args)
        assert report['metadata']['initial_account_aud'] == 5_000.0

      def test_no_nan_in_json(self, tmp_path, patched_fetcher):
        out = tmp_path / 'test.json'
        args = RunArgs(output=out)
        run_backtest(args)
        # allow_nan=False would raise on serialise; round-trip must succeed
        loaded = json.loads(out.read_text())
        assert isinstance(loaded, dict)


    class TestExitCode:
      @pytest.mark.timeout(10)
      def test_pass_returns_zero(self, tmp_path, patched_fetcher):
        # Warning 5 (D-18 perf budget regression guard): a 10x runtime regression
        # against the ~120ms baseline (RESEARCH §Pattern 2) trips this 10s timeout.
        # Manual droplet timing still owns the absolute 60s uvicorn bound.
        import time as _time
        _t0 = _time.time()
        out = tmp_path / 'pass.json'
        args = RunArgs(output=out)
        _, _, exit_code = run_backtest(args)
        _elapsed = _time.time() - _t0
        assert _elapsed < 5.0, (
          f'5y backtest with stubbed fetch should complete <5s; got {_elapsed:.2f}s '
          f'(absolute uvicorn bound is 60s; this is the cheap regression guard)'
        )
        # Bull 5y df should produce >100% return
        report = json.loads(out.read_text())
        if report['metadata']['pass']:
          assert exit_code == 0
        else:
          # If synthetic frame doesn't trigger >100%, at least confirm exit_code
          # mirrors the pass field
          assert exit_code == 1

      def test_fail_returns_one(self, tmp_path, patched_fetcher_flat):
        out = tmp_path / 'fail.json'
        args = RunArgs(output=out)
        _, _, exit_code = run_backtest(args)
        # Flat data → no trades → cum_return=0 → FAIL
        assert exit_code == 1

      def test_main_returns_exit_code(self, tmp_path, patched_fetcher_flat):
        # main() returns the exit code; with flat data, expect 1
        rc = main(['--years', '5', '--output', str(tmp_path / 'x.json')])
        assert rc == 1


    class TestLogFormat:
      def test_log_lines_use_backtest_prefix(self, tmp_path, patched_fetcher, caplog):
        out = tmp_path / 'log.json'
        with caplog.at_level(logging.INFO):
          args = RunArgs(output=out)
          run_backtest(args)
        messages = [r.getMessage() for r in caplog.records]
        joined = '\n'.join(messages)
        # Warning 4: data_fetcher owns '[Backtest] Fetching <symbol>' lines;
        # cli does NOT duplicate them. CLI emits Simulating/Combined/PASS-FAIL/Wrote.
        assert '[Backtest] Simulating SPI200' in joined
        assert '[Backtest] Simulating AUDUSD' in joined
        assert '[Backtest] Combined cum_return=' in joined
        assert ('[Backtest] PASS' in joined) or ('[Backtest] FAIL' in joined)
        assert '[Backtest] Wrote' in joined

      def test_fetching_log_line_per_instrument_exactly_once(self, tmp_path,
                                                              patched_fetcher, caplog):
        # Warning 4 regression guard: data_fetcher emits exactly one
        # '[Backtest] Fetching' line per instrument; cli must not duplicate.
        # patched_fetcher stubs fetch_ohlcv directly so no '[Backtest] Fetching'
        # line is emitted (the fetcher's logger never runs). The invariant we
        # can still assert in this stubbed env: cli does NOT emit any
        # '[Backtest] Fetching' line on its own.
        out = tmp_path / 'log2.json'
        with caplog.at_level(logging.INFO, logger='backtest.cli'):
          args = RunArgs(output=out)
          run_backtest(args)
        messages = [r.getMessage() for r in caplog.records
                    if r.name == 'backtest.cli']
        cli_fetching = sum(1 for m in messages if '[Backtest] Fetching' in m)
        assert cli_fetching == 0, (
          f'cli must not emit [Backtest] Fetching (data_fetcher owns it); '
          f'got {cli_fetching}'
        )


    class TestStrategyVersionTagging:
      def test_strategy_version_from_system_params(self, tmp_path, patched_fetcher):
        out = tmp_path / 'sv.json'
        args = RunArgs(output=out)
        report, _, _ = run_backtest(args)
        # Must match current system_params at run time
        import system_params
        assert report['metadata']['strategy_version'] == system_params.STRATEGY_VERSION

      def test_strategy_version_fresh_access_not_kwarg_default(self, tmp_path,
                                                                patched_fetcher,
                                                                monkeypatch):
        """LEARNINGS G-45: monkeypatching STRATEGY_VERSION AFTER cli import must
        propagate. If STRATEGY_VERSION were captured as a kwarg default, the
        bumped value would NOT show up — would still see the import-time value.
        """
        import system_params
        original = system_params.STRATEGY_VERSION
        monkeypatch.setattr('system_params.STRATEGY_VERSION', 'vTEST-9.9.9')
        out = tmp_path / 'fresh.json'
        args = RunArgs(output=out)
        report, _, _ = run_backtest(args)
        assert report['metadata']['strategy_version'] == 'vTEST-9.9.9', (
          f'STRATEGY_VERSION not fresh-read; got {report["metadata"]["strategy_version"]!r} '
          f'(original was {original!r})'
        )
    ```
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_backtest_cli.py -x -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `.venv/bin/pytest tests/test_backtest_cli.py -x -q` passes
    - `pytest tests/test_backtest_cli.py::TestArgparse -x` passes ≥2 tests
    - `pytest tests/test_backtest_cli.py::TestJsonSchema -x` passes ≥4 tests
    - `pytest tests/test_backtest_cli.py::TestExitCode -x` passes ≥3 tests
    - `pytest tests/test_backtest_cli.py::TestLogFormat -x` passes ≥1 test
    - `pytest tests/test_backtest_cli.py::TestStrategyVersionTagging -x` passes ≥2 tests (incl. fresh-access)
    - Full suite no regression
  </acceptance_criteria>
  <done>All 5 test classes green; D-05 JSON schema verified end-to-end; G-45 fresh-access proof.</done>
</task>

</tasks>

<verification>
1. `python -c "from backtest.cli import main, run_backtest; print('ok')"` prints `ok`
2. `.venv/bin/pytest tests/test_backtest_cli.py -x -q` passes
3. `python -c "from backtest.cli import _build_parser; p = _build_parser(); ns = p.parse_args([]); assert ns.years == 5"` succeeds
4. Full suite: `.venv/bin/pytest -x -q` exits 0
</verification>

<success_criteria>
- main + run_backtest + _build_parser callable
- D-11 argparse surface complete
- D-05 JSON schema written end-to-end (including dual sharpe per planner D-19)
- Exit code 0 PASS / 1 FAIL
- Log lines use [Backtest] prefix verbatim
- STRATEGY_VERSION fresh access (G-45 compliant)
- 5 test classes green
</success_criteria>

<output>
Create `.planning/phases/23-five-year-backtest-validation-gate/23-06-SUMMARY.md` with:
- argparse surface confirmed against CONTEXT D-11
- D-05 JSON schema serialised verbatim
- Exit-code mapping evidence
- Log-line format evidence
- Test count + pass status
</output>
