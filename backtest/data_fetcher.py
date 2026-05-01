"""Phase 23 — I/O adapter for backtest module (the ONE I/O exception per CONTEXT D-09).

Wraps yfinance with parquet cache at `.planning/backtests/data/<symbol>-<from>-<to>.parquet`.
24h staleness; --refresh forces re-fetch.

EXPLICITLY EXCLUDED from BACKTEST_PATHS_PURE AST guard (tests/test_signal_engine.py).
This is the documented I/O exception per CONTEXT D-09; do NOT add to any pure-AST list.

Allowed imports per D-09: yfinance, pyarrow, pandas, pathlib, datetime, dateutil,
logging, time.
Forbidden: state_manager, notifier, dashboard, main, sibling backtest/ pure modules.
"""
from __future__ import annotations
# Wave 1 Plan 23-02 fills in fetch_ohlcv() and cache helpers.


def fetch_ohlcv(symbol: str, start: str, end: str, refresh: bool = False):
  raise NotImplementedError('Phase 23 Wave 1 Plan 02 — to be implemented')
