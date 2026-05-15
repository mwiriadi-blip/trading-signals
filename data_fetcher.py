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
import requests
import requests.exceptions

# Phase 27 #13: redact_secret imported as a future-proof anchor. yfinance
# does not consume an API key today, so no call site exercises this import
# yet. If a vendor-key fetcher (e.g. Alpha Vantage, Polygon) is added later,
# any logger.* / raise that would interpolate the key MUST flow through
# redact_secret first — see system_params.redact_secret docstring.
from system_params import HTTP_TIMEOUT_S, redact_secret  # noqa: F401

logger = logging.getLogger(__name__)


# =========================================================================
# Phase 27 #14: deferred yfinance import.
#
# yfinance is heavy (~30+ submodules; pulls protobuf, scrapers, screeners,
# domain modules). Importing at data_fetcher module-load time bloats the
# cold-start cost of `python main.py --version`, dashboard-only routes, and
# any test that doesn't actually fetch data.
#
# Strategy:
#   1. NO module-top `import yfinance as yf`.
#   2. PEP 562 `__getattr__` exposes `data_fetcher.yf` as a module attribute
#      that lazily imports yfinance on first access. This preserves the
#      existing test monkeypatch contract (`monkeypatch.setattr(
#      'data_fetcher.yf.Ticker', ...)`) without forcing eager import.
#   3. `_get_yf()` is the explicit accessor used by fetch_ohlcv. It memoizes
#      the yfinance module; future Plan 27-02 (HTTP_TIMEOUT_S) can extend it
#      to also inject timeout defaults into requests if needed.
#   4. `YFRateLimitError` stays importable at module level via a lightweight
#      Exception subclass (review-fix M4). External code that does
#      `from data_fetcher import YFRateLimitError` keeps working WITHOUT
#      forcing yfinance import. Internal `except` clauses catch BOTH the
#      module-level proxy (so re-raising as our own type composes) AND the
#      real yfinance.exceptions.YFRateLimitError (resolved lazily through
#      `_get_yf_rate_limit_error()` so the actual library exception class is
#      caught when fetch is exercised).
# =========================================================================

_yf = None  # memoized yfinance module reference; populated by _get_yf()


def _get_yf():
  '''Lazy-import accessor for the yfinance module (Phase 27 #14).

  Returns the imported `yfinance` module. Memoized — first call pays the
  import cost; subsequent calls are O(1).
  '''
  global _yf
  if _yf is None:
    import yfinance as yf_  # local import — first call only
    _yf = yf_
  return _yf



def _get_yf_rate_limit_error():
  '''Lazy resolver for the real yfinance.exceptions.YFRateLimitError class.

  Used inside the retry-loop except tuple so that real yfinance rate-limit
  errors (raised from inside ticker.history()) are caught even though the
  module-top no longer imports them. yfinance is already loaded by the time
  this function runs (fetch_ohlcv calls `_get_yf()` first).
  '''
  from yfinance.exceptions import YFRateLimitError as _YFE
  return _YFE


def __getattr__(name: str):
  '''PEP 562 module-level __getattr__ — lazily expose `yf` as a module
  attribute so existing test monkeypatches keep working.

  Tests do `monkeypatch.setattr('data_fetcher.yf.Ticker', fake)`. That
  resolves `data_fetcher.yf` first; PEP 562 __getattr__ fires for missing
  attributes, calls _get_yf() to populate, and binds it on the module so
  monkeypatch (which uses setattr on the module) works unchanged.
  '''
  if name == 'yf':
    yf_ = _get_yf()
    # Bind on the module so subsequent attribute lookups skip __getattr__.
    import sys as _sys
    _sys.modules[__name__].yf = yf_
    return yf_
  raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


class YFRateLimitError(Exception):
  '''Phase 27 #14: module-level proxy for yfinance.exceptions.YFRateLimitError.

  Importable at data_fetcher module-import time WITHOUT forcing yfinance to
  load. External `from data_fetcher import YFRateLimitError` clauses
  continue to work; the retry loop catches BOTH this proxy AND the real
  yfinance class (via _get_yf_rate_limit_error()) so callers can choose
  either name in their `except` clauses.
  '''


# Retry-eligible transient exceptions (04-RESEARCH.md §Pattern 1, Pitfall 4).
# Empty-frame-on-invalid-symbol is raised as ValueError inside the try block
# and added to the except tuple via tuple-unpack — NEVER catch bare Exception.
#
# Phase 27 #14: the module-level YFRateLimitError proxy is in this tuple so
# the retry loop catches `raise data_fetcher.YFRateLimitError(...)` from any
# external test/code path. The REAL yfinance.exceptions.YFRateLimitError is
# resolved lazily inside fetch_ohlcv (see body) and added to the live except
# tuple — keeping module-import time off yfinance.
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

  Uses yf.Ticker(symbol).history() — NOT the module-level bulk-download helper
  (see RESEARCH.md §Standard Stack: that helper returns MultiIndex columns
  for a single ticker, which breaks the defensive column slice).

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
  # Phase 27 #14: lazy yfinance load on first attempt. _get_yf() memoizes,
  # so repeat fetches in the same process pay the import cost once.
  yf_mod = _get_yf()
  # Lazy-resolve the real yfinance YFRateLimitError class and extend the
  # retry-eligible except tuple for THIS call. Module-level _RETRY_EXCEPTIONS
  # keeps the proxy class so external tests can raise the proxy directly;
  # this local extension catches the real library exception that history()
  # raises in production.
  _real_yfe = _get_yf_rate_limit_error()
  retry_exceptions = _RETRY_EXCEPTIONS + (_real_yfe,)
  for attempt in range(1, retries + 1):
    try:
      ticker = yf_mod.Ticker(symbol)
      df = ticker.history(
        period=f'{days}d',
        interval='1d',
        auto_adjust=True,
        actions=False,
        timeout=HTTP_TIMEOUT_S,
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
    except (*retry_exceptions, ValueError) as e:
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
