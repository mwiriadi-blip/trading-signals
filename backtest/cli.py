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
import os
import sys
import tempfile
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
  """Fetch + simulate one instrument. Returns sim_result."""
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


def _atomic_write_json(path: Path, payload: dict) -> None:
  """Atomic JSON persistence: tempfile + fsync + replace + dir fsync."""
  path.parent.mkdir(parents=True, exist_ok=True)
  tmp_path_str: str | None = None
  try:
    with tempfile.NamedTemporaryFile(
      mode='w',
      encoding='utf-8',
      dir=str(path.parent),
      prefix=f'.{path.name}.',
      suffix='.tmp',
      delete=False,
    ) as tmp:
      json.dump(payload, tmp, indent=2, allow_nan=False)
      tmp.write('\n')
      tmp.flush()
      os.fsync(tmp.fileno())
      tmp_path_str = tmp.name
    os.replace(tmp_path_str, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
      os.fsync(dir_fd)
    finally:
      os.close(dir_fd)
    tmp_path_str = None
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass


def load_report(path: Path) -> dict | None:
  """Corruption-safe report read. Returns None on unreadable JSON."""
  try:
    data = json.loads(path.read_text(encoding='utf-8'))
  except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
    logger.warning('[Backtest] corrupt report %s: %s', path, exc)
    return None
  if not isinstance(data, dict):
    logger.warning('[Backtest] invalid report shape %s: expected object', path)
    return None
  data.setdefault('metadata', {})
  data['metadata']['filename'] = path.name
  return data


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
  _atomic_write_json(output_path, report)
  logger.info('[Backtest] Wrote %s', output_path)

  return report, output_path, exit_code


def main(argv: list[str] | None = None) -> int:
  """CLI entry. Returns exit code (0 PASS, 1 FAIL)."""
  logging.basicConfig(level=logging.INFO, format='%(message)s',
                      stream=sys.stderr, force=True)
  args = _parse_args(argv)
  _, _, exit_code = run_backtest(args)
  return exit_code
