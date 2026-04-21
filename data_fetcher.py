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

Wave 1 (04-02-PLAN.md, C-6 revision 2026-04-22): fetch_ohlcv body implements
the retry loop + narrow-catch tuple + empty-frame guard + required-OHLCV-column
validation (C-6 prevents KeyError-as-generic-Exception schema-drift leak).
'''
import logging
import time

import pandas as pd
import requests.exceptions
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

logger = logging.getLogger(__name__)


# Retry-eligible transient exceptions (04-RESEARCH.md §Pattern 1, Pitfall 4).
# Empty-frame-on-invalid-symbol is raised as ValueError inside the try block
# and added to the except tuple via tuple-unpack — NEVER catch bare Exception.
_RETRY_EXCEPTIONS = (
  YFRateLimitError,
  requests.exceptions.ReadTimeout,
  requests.exceptions.ConnectionError,
)

# C-6 revision 2026-04-22: required OHLCV columns for downstream signal_engine +
# sizing_engine consumption. If yfinance schema drifts and one is missing, raise
# DataFetchError with explicit missing-column names — do NOT let a KeyError leak
# as a generic Exception (which would map to exit 1 "unexpected crash" instead of
# exit 2 "data failure" in the Wave 3 top-level handler).
_REQUIRED_COLUMNS = frozenset({'Open', 'High', 'Low', 'Close', 'Volume'})


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
                    exceptions OR empty-frame response. Also raised directly
                    (non-retry-eligible) if the response is missing any of the
                    required OHLCV columns — C-6 revision 2026-04-22.
  '''
  last_err: Exception | None = None
  for attempt in range(1, retries + 1):
    try:
      ticker = yf.Ticker(symbol)
      df = ticker.history(
        period=f'{days}d',
        interval='1d',
        auto_adjust=True,
        actions=False,
        timeout=10,
      )
      if df.empty:
        raise ValueError(
          f'yfinance returned empty DataFrame for {symbol} '
          f'(likely invalid symbol or Yahoo outage)',
        )
      # C-6 revision 2026-04-22: validate required-column coverage BEFORE the
      # defensive slice. A KeyError from the slice would leak as a generic
      # Exception; a dedicated DataFetchError maps to exit 2 cleanly.
      # This raise is NOT in _RETRY_EXCEPTIONS or ValueError, so it propagates
      # past the except tuple — correct posture for a non-retry-eligible
      # schema-drift failure.
      missing = _REQUIRED_COLUMNS - set(df.columns)
      if missing:
        raise DataFetchError(
          f'{symbol}: missing required columns: {sorted(missing)} '
          f'(got {sorted(df.columns)}); yfinance schema may have drifted',
        )
      return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except (*_RETRY_EXCEPTIONS, ValueError) as e:
      last_err = e
      logger.warning(
        '[Fetch] %s attempt %d/%d failed: %s: %s',
        symbol, attempt, retries, type(e).__name__, e,
      )
      if attempt < retries:
        time.sleep(backoff_s)
  raise DataFetchError(
    f'{symbol}: retries exhausted after {retries} attempts; '
    f'last error: {type(last_err).__name__}: {last_err}',
  ) from last_err
