"""Phase 23 — I/O adapter for backtest module (the ONE I/O exception per CONTEXT D-09).

Wraps yfinance with parquet cache at `.planning/backtests/data/<symbol>-<from>-<to>.parquet`.
24h staleness; refresh=True forces re-fetch.

EXPLICITLY EXCLUDED from BACKTEST_PATHS_PURE AST guard (tests/test_signal_engine.py).
This is the documented I/O exception per CONTEXT D-09; do NOT add to any pure-AST list.

Allowed imports per D-09: yfinance, pyarrow (transitive via pandas), pandas, pathlib,
datetime, logging, time, os.
Forbidden: state_manager, notifier, dashboard, main, sibling backtest/ pure modules.
"""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_CACHE_DIR_DEFAULT = Path('.planning/backtests/data')
_CACHE_TTL_SECONDS = 86_400  # 24h per CONTEXT D-01
_REQUIRED_COLUMNS = frozenset({'Open', 'High', 'Low', 'Close', 'Volume'})


class DataFetchError(Exception):
  """yfinance fetch terminal failure (empty frame, missing columns, network)."""


class ShortFrameError(ValueError):
  """yfinance returned fewer than min_years of data per CONTEXT D-17."""


def _cache_path(symbol: str, start: str, end: str, cache_dir: Path) -> Path:
  """Filename format per CONTEXT D-01: <symbol>-<start>-<end>.parquet.

  Symbol is kept verbatim — '^AXJO' contains '^' which is filesystem-safe on
  POSIX/macOS/Linux. CONTEXT D-01 example: '^AXJO-2021-05-01-2026-05-01.parquet'.
  """
  return cache_dir / f'{symbol}-{start}-{end}.parquet'


def _is_cache_fresh(path: Path, max_age_seconds: int = _CACHE_TTL_SECONDS) -> bool:
  """True iff `path` exists and its mtime is within `max_age_seconds` of now."""
  if not path.exists():
    return False
  age = time.time() - os.path.getmtime(path)
  return age < max_age_seconds


def _fetch_yfinance(symbol: str, start: str, end: str) -> pd.DataFrame:
  """Single yfinance fetch. Returns OHLCV DataFrame or raises DataFetchError.

  Broad except is appropriate here: yfinance has many failure modes
  (rate limits, network, schema drift). The backtest CLI is the operator-
  driven entry point; DataFetchError surfaces clearly in the [Backtest] log
  prefix per CONTEXT D-11.
  """
  logger.info('[Backtest] Fetching %s %s..%s (cache miss; pulling yfinance)',
              symbol, start, end)
  try:
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end, interval='1d', auto_adjust=False)
  except Exception as exc:
    raise DataFetchError(f'yfinance fetch failed for {symbol}: {exc}') from exc

  if df is None or df.empty:
    raise DataFetchError(
      f'yfinance returned empty frame for {symbol} {start}..{end}',
    )

  missing = _REQUIRED_COLUMNS - set(df.columns)
  if missing:
    raise DataFetchError(
      f'yfinance frame for {symbol} missing required columns: {sorted(missing)}',
    )
  return df


def _validate_min_years(df: pd.DataFrame, symbol: str, min_years: int) -> None:
  """Raises ShortFrameError per CONTEXT D-17 if data spans < min_years."""
  if df.empty:
    raise ShortFrameError(
      f'[Backtest] FAIL {symbol} returned empty frame; need {min_years}y',
    )
  span_days = (df.index.max() - df.index.min()).days
  span_years = span_days / 365.25
  if span_years < min_years:
    raise ShortFrameError(
      f'[Backtest] FAIL {symbol} only has {span_years:.2f} years of data; '
      f'need {min_years}',
    )


def fetch_ohlcv(
  symbol: str,
  start: str,
  end: str,
  refresh: bool = False,
  cache_dir: Path | None = None,
  min_years: int = 5,
) -> pd.DataFrame:
  """Phase 23 BACKTEST-01 — fetch with 24h parquet cache.

  Args:
    symbol: yfinance ticker (e.g. '^AXJO', 'AUDUSD=X').
    start: ISO 'YYYY-MM-DD'.
    end: ISO 'YYYY-MM-DD'.
    refresh: if True, ignore cache and re-fetch.
    cache_dir: override cache root (test isolation).
    min_years: bail if data spans < this many years (CONTEXT D-17).

  Returns:
    OHLCV DataFrame with DatetimeIndex preserved through parquet round-trip.

  Raises:
    DataFetchError: yfinance terminal failure or missing required columns.
    ShortFrameError: data spans < min_years.
  """
  cache_root = cache_dir if cache_dir is not None else _CACHE_DIR_DEFAULT
  path = _cache_path(symbol, start, end, cache_root)

  if not refresh and _is_cache_fresh(path):
    logger.info('[Backtest] Fetching %s %s..%s (cache hit)', symbol, start, end)
    df = pd.read_parquet(path, engine='pyarrow')
    _validate_min_years(df, symbol, min_years)
    return df

  df = _fetch_yfinance(symbol, start, end)
  _validate_min_years(df, symbol, min_years)

  cache_root.mkdir(parents=True, exist_ok=True)
  df.to_parquet(path, engine='pyarrow')
  logger.info('[Backtest] Cached %s %s..%s to %s', symbol, start, end, path)
  return df
