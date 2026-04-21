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
from pathlib import Path

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
  '''Return a callable that mimics the `yf.Ticker` constructor.'''
  def _factory(symbol: str):
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
