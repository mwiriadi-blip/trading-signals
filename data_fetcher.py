'''Data Fetcher — yfinance I/O hex for daily OHLCV.

DATA-01/02/03 (REQUIREMENTS.md §Data Ingestion). Owns all yfinance calls and
exposes one public function plus two public exception classes:
  fetch_ohlcv, DataFetchError, ShortFrameError.

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. This is the ONE module
allowed to open HTTPS connections. Must NOT import signal_engine,
sizing_engine, state_manager, notifier, dashboard, main, or numpy directly.
AST blocklist in tests/test_signal_engine.py::TestDeterminism enforces this
structurally via FORBIDDEN_MODULES_DATA_FETCHER.

Retries catch ONLY transient failures (YFRateLimitError, ReadTimeout,
ConnectionError, empty-frame-on-invalid-symbol). Bugs / auth failures /
4xx errors propagate as-is — narrow-catch discipline (CLAUDE.md Pitfall 4)
mirrored from state_manager.py.

All retry-loop parameters (`timeout=10`, `retries=3`, `backoff_s=10.0`) are
parameterised for test determinism — Wave 1 tests pass `retries=3, backoff_s=0.01`
to exercise the loop quickly without real sleeps.

Wave 0 (this commit): stub module with docstrings, imports, exception classes,
and a NotImplementedError fetch_ohlcv body. Wave 1 fills the retry loop
(04-02-PLAN.md).
'''
import logging
import time  # noqa: F401 — used in Wave 1 fetch_ohlcv retry loop (time.sleep)

import pandas as pd  # noqa: F401 — used in Wave 1 fetch_ohlcv return type
import requests.exceptions  # noqa: F401 — used in Wave 1 _RETRY_EXCEPTIONS
import yfinance as yf  # noqa: F401 — used in Wave 1 yf.Ticker(sym).history()
from yfinance.exceptions import (  # noqa: F401 — Wave 1 _RETRY_EXCEPTIONS member
  YFRateLimitError,
)

logger = logging.getLogger(__name__)


class DataFetchError(Exception):
  '''Raised when a symbol's fetch fails after all retries exhaust (DATA-03).

  Caught at the top of run_daily_check; aborts the whole run (D-03).
  '''


class ShortFrameError(Exception):
  '''Raised when a successful fetch returned fewer than 300 bars (DATA-04).

  Distinct from DataFetchError because it represents a PERMANENT condition
  (Yahoo only has that much history for this symbol) — retrying won't help.
  Orchestrator catches it at top level and exits 2 with a clear message.
  '''


def fetch_ohlcv(
  symbol: str,
  days: int = 400,
  retries: int = 3,
  backoff_s: float = 10.0,
) -> pd.DataFrame:
  '''DATA-01/02/03: fetch `days` days of daily OHLCV for `symbol`.

  Uses yf.Ticker(symbol).history() NOT yf.download() (see RESEARCH.md
  §Standard Stack — yf.download returns MultiIndex columns by default).

  Returns:
    DataFrame with exactly columns [Open, High, Low, Close, Volume] and a
    DatetimeIndex in exchange-local tz (NOT converted to Perth per D-13).

  Raises:
    DataFetchError: after `retries` attempts all fail with retry-eligible
                    exceptions OR empty-frame response.
  '''
  raise NotImplementedError('Wave 1 implements fetch_ohlcv — see 04-02-PLAN.md')
