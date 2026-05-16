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
import os
import time
from decimal import Decimal

import pandas as pd
import requests
import requests.exceptions

# Phase 27 #13: redact_secret imported as a future-proof anchor. yfinance
# does not consume an API key today, so no call site exercises this import
# yet. If a vendor-key fetcher (e.g. Alpha Vantage, Polygon) is added later,
# any logger.* / raise that would interpolate the key MUST flow through
# redact_secret first — see system_params.redact_secret docstring.
import system_params  # noqa: F401 — used by _epic_for_symbol
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

# =========================================================================
# Phase 41: IG REST API base URLs + fetch-source tracking
# =========================================================================

_IG_BASE_URLS: dict[str, str] = {
  'live': 'https://api.ig.com/gateway/deal',
  'demo': 'https://demo-api.ig.com/gateway/deal',
}

# Plan 03 reads this from daily_run.py to append a state warning on fallback (D-02).
LAST_FETCH_SOURCE: dict[str, str] = {}

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


# =========================================================================
# Phase 41: IG REST API private helpers
# =========================================================================

def _ig_base_url() -> str:
  '''Return the IG REST API base URL for the configured account type.

  Reads IG_ACCOUNT_TYPE from env; defaults to 'demo'. Unknown values
  also default to 'demo' — SSRF guard (T-41-02-04).
  '''
  account_type = os.environ.get('IG_ACCOUNT_TYPE', 'demo').lower()
  if account_type not in _IG_BASE_URLS:
    account_type = 'demo'
  return _IG_BASE_URLS[account_type]


def _ig_create_session() -> dict:
  '''POST /session with VERSION:2 header. Returns headers dict for subsequent calls.

  Raises requests.exceptions.HTTPError on non-2xx (e.g. 403 bad credentials).
  Session tokens are in-memory only — never logged, never persisted (D-05).
  '''
  api_key = os.environ.get('IG_API_KEY', '')
  url = f'{_ig_base_url()}/session'
  resp = requests.post(
    url,
    json={
      'identifier': os.environ.get('IG_USERNAME', ''),
      'password': os.environ.get('IG_PASSWORD', ''),
      'encryptedPassword': False,
    },
    headers={
      'X-IG-API-KEY': api_key,
      'Content-Type': 'application/json',
      'Accept': 'application/json; charset=UTF-8',
      'VERSION': '2',
    },
    timeout=HTTP_TIMEOUT_S,
  )
  resp.raise_for_status()
  return {
    'X-IG-API-KEY': api_key,
    'CST': resp.headers['CST'],
    'X-SECURITY-TOKEN': resp.headers['X-SECURITY-TOKEN'],
    'Content-Type': 'application/json',
    'Accept': 'application/json; charset=UTF-8',
  }


def _ig_fetch_ohlcv_raw(
  epic: str,
  num_points: int,
  session_headers: dict,
) -> list:
  '''GET /prices/{epic}/D/{num_points} with VERSION:1 header (Pitfall 1).

  Returns the raw prices list from the IG response JSON.
  Raises requests.exceptions.HTTPError on non-2xx.
  '''
  url = f'{_ig_base_url()}/prices/{epic}/D/{num_points}'
  resp = requests.get(
    url,
    headers={**session_headers, 'VERSION': '1'},
    timeout=HTTP_TIMEOUT_S,
  )
  resp.raise_for_status()
  return resp.json()['prices']


def _ig_normalise(prices: list) -> pd.DataFrame:
  '''Convert raw IG prices list to canonical OHLCV DataFrame.

  Mid price = (bid + ask) / 2 for O/H/L/C (D-12).
  Volume = lastTradedVolume (0 accepted for spread-bet instruments, Pitfall 2).
  Index: UTC-aware DatetimeIndex (Pitfall 3).
  Fallback: snapshotTime used if snapshotTimeUTC absent (A4).
  '''
  rows = []
  timestamps = []
  for p in prices:
    ts_str = p.get('snapshotTimeUTC') or p.get('snapshotTime')
    if not ts_str:
      raise DataFetchError(
        f'IG price candle missing snapshotTimeUTC and snapshotTime: {p!r}',
      )
    timestamps.append(ts_str)
    def _mid(side: dict) -> float:
      return float((Decimal(str(side['bid'])) + Decimal(str(side['ask']))) / 2)
    rows.append({
      'Open': _mid(p['openPrice']),
      'High': _mid(p['highPrice']),
      'Low': _mid(p['lowPrice']),
      'Close': _mid(p['closePrice']),
      'Volume': p.get('lastTradedVolume', 0),
    })
  df = pd.DataFrame(rows)
  df.index = pd.to_datetime(timestamps, utc=True)
  missing = _REQUIRED_COLUMNS - set(df.columns)
  if missing:
    raise DataFetchError(
      f'IG normalise: missing required columns: {sorted(missing)}',
    )
  return df[['Open', 'High', 'Low', 'Close', 'Volume']]


def _epic_for_symbol(symbol: str) -> str | None:
  '''Look up the IG EPIC code for a yfinance symbol via DEFAULT_MARKETS.

  Returns None if symbol not found or has no ig_epic field.
  '''
  for entry in system_params.DEFAULT_MARKETS.values():
    if entry.get('symbol') == symbol:
      return entry.get('ig_epic')
  return None


def _fetch_via_ig(
  epic: str,
  days: int,
  retries: int,
  backoff_s: float,
  symbol: str,
) -> 'pd.DataFrame | None':
  '''Orchestrate IG session + fetch + normalise with retry and one re-auth on 403.

  Returns DataFrame on success, None when all attempts exhausted (caller falls
  back to yfinance). Session-level 403 or network error at session creation also
  returns None immediately (non-transient, no point retrying the fetch).
  '''
  try:
    session = _ig_create_session()
  except requests.exceptions.HTTPError as e:
    if e.response is not None and e.response.status_code == 403:
      logger.warning(
        '[Fetch] IG session auth failed (403): key=%s — falling back to yfinance',
        redact_secret(os.environ.get('IG_API_KEY', '')),
      )
    else:
      logger.warning(
        '[Fetch] IG session HTTP error %s — falling back to yfinance',
        e.response.status_code if e.response is not None else 'unknown',
      )
    return None
  except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
    logger.warning('[Fetch] IG session network error: %s', e)
    return None

  # CR-03 fix: use while loop so re-auth can retry the SAME attempt slot
  # without consuming the next iteration (a `continue` in a for-loop always
  # advances the iterator, which on the last attempt skips past the boundary
  # and returns None without ever using the fresh session).
  re_authed = False
  attempt = 0
  while attempt < retries:
    attempt += 1
    try:
      raw = _ig_fetch_ohlcv_raw(epic, days, session)
      try:
        df = _ig_normalise(raw)
      except DataFetchError as norm_err:
        # CR-01 fix: normalise errors (e.g. empty/malformed prices) are
        # non-retryable — return None so caller falls back to yfinance.
        logger.warning('[Fetch] IG normalise failed: %s — falling back', norm_err)
        return None
      LAST_FETCH_SOURCE[symbol] = 'ig'
      return df
    except requests.exceptions.HTTPError as e:
      if (
        e.response is not None
        and e.response.status_code == 403
        and not re_authed
      ):
        logger.warning(
          '[Fetch] IG prices 403 on attempt %d — re-authing',
          attempt,
        )
        try:
          session = _ig_create_session()
          re_authed = True
          attempt -= 1  # CR-03: don't consume attempt slot for re-auth
          continue
        except (
          requests.exceptions.HTTPError,
          requests.exceptions.ReadTimeout,
          requests.exceptions.ConnectionError,
        ) as re_auth_err:
          logger.warning('[Fetch] IG re-auth failed: %s', re_auth_err)
          return None
      else:
        logger.warning(
          '[Fetch] IG prices HTTP error attempt %d/%d: status=%s',
          attempt, retries,
          e.response.status_code if e.response is not None else 'unknown',
        )
        if attempt < retries:
          time.sleep(backoff_s)
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
      logger.warning(
        '[Fetch] IG prices network error attempt %d/%d: %s',
        attempt, retries, e,
      )
      if attempt < retries:
        time.sleep(backoff_s)
  return None


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
  # WR-04: clear stale entry from prior runs in the same process so daily_run.py
  # always sees the current run's source, never a leftover from a prior fetch.
  LAST_FETCH_SOURCE.pop(symbol, None)

  # Phase 41: IG credential gate — try IG first; fall back to yfinance.
  ig_key = os.environ.get('IG_API_KEY', '').strip()
  if ig_key:
    ig_epic = _epic_for_symbol(symbol)
    if ig_epic:
      df = _fetch_via_ig(ig_epic, days, retries, backoff_s, symbol)
      if df is not None:
        return df
      logger.warning(
        '[Fetch] IG fetch failed for %s — falling back to yfinance', symbol,
      )
      LAST_FETCH_SOURCE[symbol] = 'yfinance_fallback'
    else:
      # CR-02: no epic mapping — treat same as fallback so daily_run.py logs
      # the warning instead of silently missing it.
      logger.warning('[Fetch] No IG epic for %s — falling back to yfinance', symbol)
      LAST_FETCH_SOURCE[symbol] = 'yfinance_fallback'
  else:
    logger.warning('[Fetch] IG credentials not configured — falling back to yfinance')
    LAST_FETCH_SOURCE[symbol] = 'yfinance'

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
