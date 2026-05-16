'''Phase 4 test suite: yfinance fetch, retry policy, empty-frame handling,
400-bar shape validation.

Organized into classes per D-13 (one class per concern dimension):
  TestFetch, TestColumnShape.

All tests are OFFLINE. Happy-path tests load committed JSON fixtures from
tests/fixtures/fetch/*.json via pd.read_json(orient='split') and monkeypatch
`data_fetcher.yf.Ticker` (NOT `yfinance.Ticker`) at the import site — the
patch target is `data_fetcher.yf` because `import yfinance as yf` binds `yf`
as an attribute of `data_fetcher` at module-import time. Scenario / error
tests use the same monkeypatch idiom. NEVER calls live yfinance in CI.

Wave 1 (this commit — 04-02-PLAN.md Task 1): populated TestFetch (6 methods,
DATA-01/02/03 + empty-frame-exhausts-retries) and TestColumnShape (2 methods,
Pitfall-1 strip + C-6 revision missing-columns check).
'''
import json
import logging
from pathlib import Path

import data_fetcher
import pandas as pd
import pytest
import requests.exceptions
from yfinance.exceptions import YFRateLimitError

from data_fetcher import (
  DataFetchError,
  ShortFrameError,  # noqa: F401 — imported for surface contract; raised in Wave 2 main.py
  fetch_ohlcv,
)

# =========================================================================
# Module-level path + fixture-dir constants (mirrors test_state_manager.py
# STATE_MANAGER_PATH / TEST_STATE_MANAGER_PATH pattern)
# =========================================================================

DATA_FETCHER_PATH = Path('data_fetcher.py')
TEST_DATA_FETCHER_PATH = Path('tests/test_data_fetcher.py')
FETCH_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'fetch'


# =========================================================================
# Fixture loader helper — TestFetch uses this to replay recorded JSON
# =========================================================================

def _load_recorded_fixture(name: str) -> pd.DataFrame:
  '''Load a committed JSON fixture preserving DatetimeIndex + float64 dtypes.

  D-13: keep market-local tz (exchange-local DatetimeIndex); strftime drops
  the tz for signal_as_of downstream. orient='split' is the only pandas
  orient that losslessly round-trips a tz-aware DatetimeIndex.
  '''
  path = FETCH_FIXTURE_DIR / name
  df = pd.read_json(path, orient='split')
  return df


# =========================================================================
# FakeTicker — drop-in for yfinance.Ticker in monkeypatched tests.
# Per 04-PATTERNS.md §Monkeypatch strategy + 04-RESEARCH.md §Example 3:
# patch `data_fetcher.yf.Ticker` at the import site (NOT `yfinance.Ticker`).
# =========================================================================

class _FakeTicker:
  '''Drop-in for yfinance.Ticker. The class-level `call_count` is a
  reference to a list mutated on every .history() call — gives TestFetch
  retry methods a way to assert how many attempts the retry loop made.

  Instantiated by a factory closure inside each test method so each test
  gets a fresh counter + its own behaviour script.
  '''

  def __init__(self, symbol: str, behaviour, call_count: list) -> None:
    '''behaviour: list of (exc_or_df) entries; each call pops/uses index (call_count-1).
    Last entry is re-used if call_count exceeds list length (for all-fail scenarios).
    '''
    self.symbol = symbol
    self._behaviour = behaviour
    self._call_count = call_count

  def history(self, **kwargs):
    self._call_count.append(1)
    idx = min(len(self._call_count) - 1, len(self._behaviour) - 1)
    item = self._behaviour[idx]
    if isinstance(item, Exception):
      raise item
    return item


def _make_fake_ticker_factory(behaviour, call_count):
  '''Return a callable that mimics the `yf.Ticker` constructor.

  Accepts (and ignores) `session=` kwarg per Phase 27 #5: production
  passes `session=_get_yf_session()` so yfinance internals inherit the
  HTTP_TIMEOUT_S default. Fakes don't make real HTTP calls so the
  session is irrelevant — but the kwarg must be accepted to match the
  real Ticker signature.
  '''
  def _factory(symbol: str, session=None):
    return _FakeTicker(symbol, behaviour, call_count)
  return _factory


# =========================================================================
# Test classes — one per concern dimension (D-13)
# =========================================================================

class TestFetch:
  '''DATA-01 / DATA-02 / DATA-03: happy path + retry + empty-frame-exhausts-retries.

  Happy paths load tests/fixtures/fetch/axjo_400d.json + audusd_400d.json
  via _load_recorded_fixture and monkeypatch data_fetcher.yf.Ticker at the
  import site (per Pitfall 3 / 04-PATTERNS.md §Monkeypatch strategy).
  NEVER calls live yfinance in CI.
  '''

  def test_happy_path_axjo_returns_400_bars(self, monkeypatch) -> None:
    '''DATA-01: ^AXJO fetch returns >= 400 bars with exact column order.'''
    fixture_df = _load_recorded_fixture('axjo_400d.json')
    call_count: list = []
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory([fixture_df], call_count),
    )
    df = fetch_ohlcv('^AXJO', days=400, retries=3, backoff_s=0.0)
    assert len(df) >= 400
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert isinstance(df.index, pd.DatetimeIndex)
    assert len(call_count) == 1

  def test_happy_path_audusd_returns_400_bars(self, monkeypatch) -> None:
    '''DATA-02: AUDUSD=X fetch returns >= 400 bars with exact column order.'''
    fixture_df = _load_recorded_fixture('audusd_400d.json')
    call_count: list = []
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory([fixture_df], call_count),
    )
    df = fetch_ohlcv('AUDUSD=X', days=400, retries=3, backoff_s=0.0)
    assert len(df) >= 400
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert isinstance(df.index, pd.DatetimeIndex)
    assert len(call_count) == 1

  def test_retry_on_rate_limit_then_success(self, monkeypatch) -> None:
    '''DATA-03: first attempt raises YFRateLimitError, second returns fixture.'''
    fixture_df = _load_recorded_fixture('axjo_400d.json')
    call_count: list = []
    # Pitfall 5: monkeypatch time.sleep to a no-op so we don't wait backoff_s.
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)
    # yfinance 1.2.0's YFRateLimitError.__init__ takes no args — message is
    # fixed by the library. Rule 1 auto-fix: call with no arguments.
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory(
        [YFRateLimitError(), fixture_df],
        call_count,
      ),
    )
    df = fetch_ohlcv('^AXJO', days=400, retries=3, backoff_s=0.0)
    assert len(df) >= 400
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert len(call_count) == 2

  def test_retry_on_timeout_then_success(self, monkeypatch) -> None:
    '''DATA-03: first attempt raises requests.exceptions.ReadTimeout, second succeeds.'''
    fixture_df = _load_recorded_fixture('audusd_400d.json')
    call_count: list = []
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory(
        [requests.exceptions.ReadTimeout('socket timeout'), fixture_df],
        call_count,
      ),
    )
    df = fetch_ohlcv('AUDUSD=X', days=400, retries=3, backoff_s=0.0)
    assert len(df) >= 400
    assert len(call_count) == 2

  def test_retry_on_connection_error_then_success(self, monkeypatch) -> None:
    '''DATA-03: first attempt raises requests.exceptions.ConnectionError, second succeeds.'''
    fixture_df = _load_recorded_fixture('axjo_400d.json')
    call_count: list = []
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory(
        [requests.exceptions.ConnectionError('dns fail'), fixture_df],
        call_count,
      ),
    )
    df = fetch_ohlcv('^AXJO', days=400, retries=3, backoff_s=0.0)
    assert len(df) >= 400
    assert len(call_count) == 2

  def test_empty_frame_exhausts_retries_then_raises_data_fetch_error(self, monkeypatch) -> None:
    '''DATA-04 boundary: every attempt returns empty DataFrame → DataFetchError
    raised after `retries` attempts; chained cause is the last ValueError.
    '''
    empty_df = pd.DataFrame()
    call_count: list = []
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory([empty_df], call_count),
    )
    with pytest.raises(DataFetchError, match='retries exhausted') as excinfo:
      fetch_ohlcv('BOGUS', days=400, retries=3, backoff_s=0.0)
    assert len(call_count) == 3
    # Chained cause is the last ValueError raised inside the try block.
    assert isinstance(excinfo.value.__cause__, ValueError)
    assert 'empty DataFrame' in str(excinfo.value.__cause__)


class TestColumnShape:
  '''Pitfall 1 / DATA-01: returned DataFrame has EXACTLY
  [Open, High, Low, Close, Volume] in that order — not alphabetised, no
  Dividends/Stock Splits columns, DatetimeIndex preserved.

  Also covers C-6 revision 2026-04-22: missing required columns must raise
  DataFetchError (NOT a leaked KeyError) so the Wave 3 top-level handler maps
  it to exit 2 (data failure) rather than exit 1 (unexpected crash).
  '''

  def test_column_shape_strips_extra_columns(self, monkeypatch) -> None:
    '''Pitfall 1: source DataFrame has Dividends + Stock Splits alongside
    OHLCV; fetch_ohlcv defensively slices to exactly the 5 required columns.
    '''
    idx = pd.date_range('2025-01-01', periods=5, freq='D', tz='Australia/Sydney')
    extra_df = pd.DataFrame(
      {
        'Open': [100.0, 101.0, 102.0, 103.0, 104.0],
        'High': [101.0, 102.0, 103.0, 104.0, 105.0],
        'Low': [99.0, 100.0, 101.0, 102.0, 103.0],
        'Close': [100.5, 101.5, 102.5, 103.5, 104.5],
        'Volume': [1000, 1100, 1200, 1300, 1400],
        'Dividends': [0.0, 0.0, 0.0, 0.0, 0.0],
        'Stock Splits': [0.0, 0.0, 0.0, 0.0, 0.0],
      },
      index=idx,
    )
    call_count: list = []
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory([extra_df], call_count),
    )
    df = fetch_ohlcv('^AXJO', days=5, retries=1, backoff_s=0.0)
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert isinstance(df.index, pd.DatetimeIndex)
    assert 'Dividends' not in df.columns
    assert 'Stock Splits' not in df.columns

  def test_missing_required_columns_raises_clear_fetch_error(self, monkeypatch) -> None:
    '''C-6 revision 2026-04-22: yfinance schema drift (missing High + Low)
    must raise DataFetchError — NEVER a KeyError leaking as generic Exception.

    The dedicated DataFetchError lets the Wave 3 top-level handler map this
    to exit 2 (data failure) rather than exit 1 (unexpected crash).
    '''
    idx = pd.date_range('2025-01-01', periods=3, freq='D', tz='Australia/Sydney')
    missing_df = pd.DataFrame(
      {
        'Open': [100.0, 101.0, 102.0],
        'Close': [100.5, 101.5, 102.5],
        'Volume': [1000, 1100, 1200],
        # High + Low deliberately omitted
      },
      index=idx,
    )
    call_count: list = []
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory([missing_df], call_count),
    )
    with pytest.raises(DataFetchError, match='missing required columns') as excinfo:
      fetch_ohlcv('^AXJO', days=3, retries=3, backoff_s=0.0)
    msg = str(excinfo.value)
    assert 'High' in msg
    assert 'Low' in msg
    # Non-retry-eligible schema drift — raises on attempt 1, NOT after retries.
    assert len(call_count) == 1
    # Confirm we got the domain-specific exception, not a stray KeyError.
    assert not isinstance(excinfo.value, KeyError)


# =========================================================================
# Phase 41 Plan 01 — IG REST API test infrastructure
# =========================================================================
# These classes are SKIPPED until Plan 41-02 ships the IG helpers.
# Skip guard uses class-level pytestmark to avoid affecting TestFetch above.
# =========================================================================

def _load_ig_fixture(name: str) -> dict:
  '''Load a hand-crafted IG response JSON fixture via json.load (NOT pd.read_json).

  IG fixtures are raw IG /prices response dicts, not DataFrame orient='split'.
  Path mirrors FETCH_FIXTURE_DIR above: tests/fixtures/fetch/<name>.
  '''
  path = FETCH_FIXTURE_DIR / name
  with open(path) as fh:
    return json.load(fh)


# =========================================================================
# _FakeResponse — drop-in for requests.Response in IG monkeypatched tests.
# Defined here (adjacent to TestIGFetch) for locality.
# =========================================================================

class _FakeResponse:
  '''Minimal requests.Response mimic for monkeypatching requests.post/get.

  Args:
    json_data: dict returned by .json()
    headers: dict returned by .headers
    status_code: int; .raise_for_status() raises HTTPError if >= 400
  '''

  def __init__(self, json_data=None, headers=None, status_code=200):
    self._json = json_data or {}
    self.headers = headers or {}
    self.status_code = status_code

  def raise_for_status(self):
    if self.status_code >= 400:
      raise requests.exceptions.HTTPError(response=self)

  def json(self):
    return self._json


# =========================================================================
# TestIGNormalise — D-12 mid-price math, Pitfall 2 (Volume=0), Pitfall 3 (UTC)
# =========================================================================

class TestIGNormalise:
  '''Verify _ig_normalise contract once Plan 41-02 ships the helper.'''

  def test_mid_price_calculation(self) -> None:
    '''D-12: every Open == (bid + ask) / 2 for openPrice across all rows.'''
    fixture = _load_ig_fixture('ig_spi200_prices.json')
    prices = fixture['prices']
    result = data_fetcher._ig_normalise(prices)
    for i, candle in enumerate(prices):
      expected_open = (candle['openPrice']['bid'] + candle['openPrice']['ask']) / 2
      assert abs(result['Open'].iloc[i] - expected_open) < 1e-10, (
        f'Row {i}: Open={result["Open"].iloc[i]!r}, expected mid={expected_open!r}'
      )

  def test_volume_zero_accepted(self) -> None:
    '''Pitfall 2: lastTradedVolume=0 is valid for IG spread-bet instruments.
    Must NOT raise; every row must have Volume == 0.
    '''
    fixture = _load_ig_fixture('ig_spi200_prices.json')
    result = data_fetcher._ig_normalise(fixture['prices'])
    assert list(result['Volume']) == [0] * len(result), (
      'Expected all Volume == 0 for IG spread-bet fixture'
    )

  def test_index_is_utc_datetimeindex(self) -> None:
    '''Pitfall 3: index must be UTC-aware DatetimeIndex, monotonically increasing.'''
    fixture = _load_ig_fixture('ig_spi200_prices.json')
    result = data_fetcher._ig_normalise(fixture['prices'])
    assert isinstance(result.index, pd.DatetimeIndex), (
      f'Expected DatetimeIndex, got {type(result.index)}'
    )
    import pytz
    assert result.index.tz is not None, 'DatetimeIndex must be tz-aware (UTC)'
    assert str(result.index.tz) in ('UTC', 'utc'), (
      f'Expected UTC timezone, got {result.index.tz!r}'
    )
    assert result.index.is_monotonic_increasing, (
      'DatetimeIndex must be monotonically increasing'
    )

  def test_columns_are_canonical_ohlcv(self) -> None:
    '''Columns must be exactly [Open, High, Low, Close, Volume] in that order.'''
    fixture = _load_ig_fixture('ig_spi200_prices.json')
    result = data_fetcher._ig_normalise(fixture['prices'])
    assert list(result.columns) == ['Open', 'High', 'Low', 'Close', 'Volume'], (
      f'Expected canonical OHLCV columns, got {list(result.columns)}'
    )


# =========================================================================
# TestIGFetch — DATA-01/02/03 + D-01/D-02/D-06/D-12 + Pitfall 1/2/3/4
# =========================================================================

class TestIGFetch:
  '''IG fetch branch: happy path, retry, fallback, warning, auth gate.

  Monkeypatch targets:
    data_fetcher.requests.post  — IG session POST /session
    data_fetcher.requests.get   — IG prices GET /prices/{epic}/D/{n}
    data_fetcher.yf.Ticker      — yfinance fallback
    data_fetcher.time.sleep     — no-op to keep suite fast

  All tests set required IG env vars via monkeypatch.setenv to isolate from
  any host environment.
  '''

  @pytest.fixture(autouse=True)
  def _clear_last_fetch_source(self):
    '''WR-04: clear LAST_FETCH_SOURCE before and after each test in this class
    to prevent cross-test contamination from the module-level mutable dict.
    '''
    data_fetcher.LAST_FETCH_SOURCE.clear()
    yield
    data_fetcher.LAST_FETCH_SOURCE.clear()

  # Shared IG session response headers (returned by POST /session).
  _SESSION_HEADERS = {
    'CST': 'test-cst-token-abc123',
    'X-SECURITY-TOKEN': 'test-xst-token-xyz789',
  }

  def _fake_session_response(self):
    '''Return a _FakeResponse mimicking a successful IG POST /session.'''
    return _FakeResponse(
      json_data={'accountType': 'SPREADBET', 'hasActiveDemoAccounts': True},
      headers=self._SESSION_HEADERS,
      status_code=200,
    )

  def _fake_prices_response(self, fixture_name: str):
    '''Return a _FakeResponse mimicking a successful IG GET /prices/{epic}/D/{n}.'''
    fixture = _load_ig_fixture(fixture_name)
    return _FakeResponse(json_data=fixture, status_code=200)

  def _set_ig_env(self, monkeypatch):
    '''Inject required IG env vars via monkeypatch.'''
    monkeypatch.setenv('IG_API_KEY', 'test-key-123')
    monkeypatch.setenv('IG_USERNAME', 'testuser@example.com')
    monkeypatch.setenv('IG_PASSWORD', 'testpass99')
    monkeypatch.setenv('IG_ACCOUNT_TYPE', 'demo')

  def test_ig_happy_path_spi200(self, monkeypatch) -> None:
    '''D-01/DATA-01: ^AXJO IG fetch returns DataFrame with canonical OHLCV columns.'''
    self._set_ig_env(monkeypatch)
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)

    post_calls: list = []
    get_calls: list = []

    def fake_post(url, **kwargs):
      post_calls.append(url)
      return self._fake_session_response()

    def fake_get(url, **kwargs):
      get_calls.append(url)
      return self._fake_prices_response('ig_spi200_prices.json')

    monkeypatch.setattr('data_fetcher.requests.post', fake_post)
    monkeypatch.setattr('data_fetcher.requests.get', fake_get)

    df = fetch_ohlcv('^AXJO', days=5, retries=3, backoff_s=0.0)

    fixture = _load_ig_fixture('ig_spi200_prices.json')
    expected_rows = len(fixture['prices'])
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert isinstance(df.index, pd.DatetimeIndex)
    assert len(df) == expected_rows, f'Expected {expected_rows} rows, got {len(df)}'
    assert len(post_calls) >= 1, 'Expected at least one POST /session'
    assert len(get_calls) >= 1, 'Expected at least one GET /prices'

  def test_ig_happy_path_audusd(self, monkeypatch) -> None:
    '''D-01/DATA-02: AUDUSD=X IG fetch returns DataFrame with canonical OHLCV columns.'''
    self._set_ig_env(monkeypatch)
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)

    def fake_post(url, **kwargs):
      return self._fake_session_response()

    def fake_get(url, **kwargs):
      return self._fake_prices_response('ig_audusd_prices.json')

    monkeypatch.setattr('data_fetcher.requests.post', fake_post)
    monkeypatch.setattr('data_fetcher.requests.get', fake_get)

    df = fetch_ohlcv('AUDUSD=X', days=5, retries=3, backoff_s=0.0)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert isinstance(df.index, pd.DatetimeIndex)
    assert len(df) >= 5

  def test_ig_retry_on_timeout(self, monkeypatch) -> None:
    '''DATA-03: first 2 GET /prices calls raise ReadTimeout; 3rd returns fixture.
    assert fetch succeeds; assert exactly 3 GET /prices calls attempted.
    '''
    self._set_ig_env(monkeypatch)
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)

    post_calls: list = []
    get_calls: list = []

    def fake_post(url, **kwargs):
      post_calls.append(url)
      return self._fake_session_response()

    def fake_get(url, **kwargs):
      get_calls.append(url)
      if len(get_calls) < 3:
        raise requests.exceptions.ReadTimeout('socket timeout')
      return self._fake_prices_response('ig_spi200_prices.json')

    monkeypatch.setattr('data_fetcher.requests.post', fake_post)
    monkeypatch.setattr('data_fetcher.requests.get', fake_get)

    df = fetch_ohlcv('^AXJO', days=5, retries=3, backoff_s=0.0)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert len(get_calls) == 3, (
      f'Expected 3 GET attempts (2 timeout + 1 success), got {len(get_calls)}'
    )

  def test_ig_fallback_to_yfinance(self, monkeypatch) -> None:
    '''D-01: IG raises ReadTimeout on all 3 attempts → yfinance fallback triggered.
    assert returned df is from yfinance path via LAST_FETCH_SOURCE sentinel.
    '''
    self._set_ig_env(monkeypatch)
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)

    fixture_df = _load_recorded_fixture('axjo_400d.json')
    yf_call_count: list = []

    def fake_post(url, **kwargs):
      return self._fake_session_response()

    def fake_get(url, **kwargs):
      raise requests.exceptions.ReadTimeout('timeout on all attempts')

    monkeypatch.setattr('data_fetcher.requests.post', fake_post)
    monkeypatch.setattr('data_fetcher.requests.get', fake_get)
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory([fixture_df], yf_call_count),
    )

    df = fetch_ohlcv('^AXJO', days=400, retries=3, backoff_s=0.0)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert len(yf_call_count) >= 1, 'Expected yfinance to be called as fallback'
    # Verify LAST_FETCH_SOURCE sentinel records fallback origin
    assert data_fetcher.LAST_FETCH_SOURCE.get('^AXJO') in (
      'yfinance_fallback', 'yfinance',
    ), (
      f'Expected LAST_FETCH_SOURCE to record yfinance fallback, '
      f'got {data_fetcher.LAST_FETCH_SOURCE.get("^AXJO")!r}'
    )

  def test_fallback_emits_warning(self, monkeypatch, caplog) -> None:
    '''D-02: IG fallback to yfinance emits WARNING log with "falling back to yfinance".'''
    self._set_ig_env(monkeypatch)
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)

    fixture_df = _load_recorded_fixture('axjo_400d.json')

    def fake_post(url, **kwargs):
      return self._fake_session_response()

    def fake_get(url, **kwargs):
      raise requests.exceptions.ReadTimeout('timeout')

    monkeypatch.setattr('data_fetcher.requests.post', fake_post)
    monkeypatch.setattr('data_fetcher.requests.get', fake_get)
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory([fixture_df], []),
    )

    with caplog.at_level(logging.WARNING, logger='data_fetcher'):
      fetch_ohlcv('^AXJO', days=400, retries=3, backoff_s=0.0)

    assert any(
      'falling back to yfinance' in r.message
      for r in caplog.records
    ), (
      f'Expected "falling back to yfinance" in WARNING logs; '
      f'got: {[r.message for r in caplog.records]}'
    )

  def test_missing_credentials_uses_yfinance(self, monkeypatch, caplog) -> None:
    '''D-06: missing IG_API_KEY → no requests.post to /session; yfinance invoked;
    WARNING log "IG credentials not configured".
    '''
    monkeypatch.delenv('IG_API_KEY', raising=False)
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)

    fixture_df = _load_recorded_fixture('axjo_400d.json')
    post_calls: list = []

    def fake_post(url, **kwargs):
      post_calls.append(url)
      return self._fake_session_response()

    yf_call_count: list = []
    monkeypatch.setattr('data_fetcher.requests.post', fake_post)
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory([fixture_df], yf_call_count),
    )

    with caplog.at_level(logging.WARNING, logger='data_fetcher'):
      fetch_ohlcv('^AXJO', days=400, retries=3, backoff_s=0.0)

    assert len(post_calls) == 0, (
      'requests.post should NOT be called when IG_API_KEY is absent'
    )
    assert len(yf_call_count) >= 1, 'yfinance should be invoked as primary path'
    assert any(
      'IG credentials not configured' in r.message
      for r in caplog.records
    ), (
      f'Expected "IG credentials not configured" warning; '
      f'got: {[r.message for r in caplog.records]}'
    )

  def test_session_403_does_not_retry(self, monkeypatch) -> None:
    '''Anti-pattern: 403 on POST /session is auth failure — NOT transient.
    Only ONE POST attempt should be made; no retry; fallback to yfinance.
    '''
    self._set_ig_env(monkeypatch)
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)

    post_calls: list = []
    fixture_df = _load_recorded_fixture('axjo_400d.json')

    def fake_post(url, **kwargs):
      post_calls.append(url)
      return _FakeResponse(status_code=403)

    monkeypatch.setattr('data_fetcher.requests.post', fake_post)
    monkeypatch.setattr(
      'data_fetcher.yf.Ticker',
      _make_fake_ticker_factory([fixture_df], []),
    )

    df = fetch_ohlcv('^AXJO', days=400, retries=3, backoff_s=0.0)

    assert isinstance(df, pd.DataFrame)
    assert len(post_calls) == 1, (
      f'Expected exactly 1 POST /session attempt on 403 (no retry); '
      f'got {len(post_calls)}'
    )

  def test_prices_403_triggers_one_reauth(self, monkeypatch) -> None:
    '''Pitfall 4: prices GET returns 403 once → one re-auth (second POST /session)
    → second GET succeeds. Asserts exactly 2 POST /session calls + 2 GET calls.
    '''
    self._set_ig_env(monkeypatch)
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)

    post_calls: list = []
    get_calls: list = []

    def fake_post(url, **kwargs):
      post_calls.append(url)
      return self._fake_session_response()

    def fake_get(url, **kwargs):
      get_calls.append(url)
      if len(get_calls) == 1:
        # First GET → 403 (session expired)
        return _FakeResponse(status_code=403)
      # Second GET (after re-auth) → success
      return self._fake_prices_response('ig_spi200_prices.json')

    monkeypatch.setattr('data_fetcher.requests.post', fake_post)
    monkeypatch.setattr('data_fetcher.requests.get', fake_get)

    df = fetch_ohlcv('^AXJO', days=5, retries=3, backoff_s=0.0)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert len(post_calls) == 2, (
      f'Expected 2 POST /session (initial + re-auth on 403); got {len(post_calls)}'
    )
    assert len(get_calls) == 2, (
      f'Expected 2 GET /prices (one 403 + one success); got {len(get_calls)}'
    )
