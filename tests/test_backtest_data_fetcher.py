"""Phase 23 — backtest/data_fetcher.py tests (BACKTEST-01 data layer).

Coverage: cache hit/miss, refresh, parquet round-trip, <5y bail.
"""
from __future__ import annotations
from unittest.mock import MagicMock

import pandas as pd
import pytest

from backtest.data_fetcher import (
  DataFetchError,
  ShortFrameError,
  _cache_path,
  fetch_ohlcv,
)


def _make_5y_df(start: str = '2021-04-15', end: str = '2026-05-15') -> pd.DataFrame:
  """Synthetic 5y+ calendar-daily OHLCV frame with TZ-aware DatetimeIndex.

  Uses freq='D' (calendar daily) and slightly wider start/end so the frame's
  calendar span comfortably exceeds 5 years. Tests then call the production
  min_years=5 threshold (no workaround).
  """
  idx = pd.date_range(start=start, end=end, freq='D', tz='Australia/Perth')
  n = len(idx)
  return pd.DataFrame({
    'Open':   [7000.0 + i * 0.1 for i in range(n)],
    'High':   [7010.0 + i * 0.1 for i in range(n)],
    'Low':    [6990.0 + i * 0.1 for i in range(n)],
    'Close':  [7005.0 + i * 0.1 for i in range(n)],
    'Volume': [1_000_000 for _ in range(n)],
  }, index=idx)


def _make_short_df() -> pd.DataFrame:
  """Synthetic <5y daily frame to trigger ShortFrameError."""
  idx = pd.date_range(start='2025-05-01', end='2026-05-01', freq='B', tz='Australia/Perth')
  n = len(idx)
  return pd.DataFrame({
    'Open':   [7000.0] * n, 'High':   [7010.0] * n,
    'Low':    [6990.0] * n, 'Close':  [7005.0] * n,
    'Volume': [1_000_000] * n,
  }, index=idx)


@pytest.fixture
def mock_yfinance(monkeypatch):
  """Returns a list capturing every yfinance.Ticker.history call."""
  calls = []

  def _ticker_factory(symbol):
    mock = MagicMock()
    def _history(**kwargs):
      calls.append({'symbol': symbol, **kwargs})
      # Widen synthetic frame by 60 days each side so calendar span comfortably
      # exceeds min_years=5 regardless of the requested window.
      import datetime as _dt
      s = (_dt.date.fromisoformat(kwargs['start']) - _dt.timedelta(days=60)).isoformat()
      e = (_dt.date.fromisoformat(kwargs['end']) + _dt.timedelta(days=60)).isoformat()
      return _make_5y_df(start=s, end=e)
    mock.history = _history
    return mock

  monkeypatch.setattr('backtest.data_fetcher.yf.Ticker', _ticker_factory)
  return calls


class TestCacheHitMiss:
  def test_cache_miss_calls_yfinance_and_writes_parquet(self, tmp_path, mock_yfinance):
    df = fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01',
                     cache_dir=tmp_path, min_years=5)
    assert len(mock_yfinance) == 1
    assert mock_yfinance[0]['symbol'] == '^AXJO'
    cache_file = tmp_path / '^AXJO-2021-05-01-2026-05-01.parquet'
    assert cache_file.exists()
    assert len(df) > 1000  # ~5y calendar days

  def test_cache_hit_skips_yfinance(self, tmp_path, mock_yfinance):
    # First call: cache miss
    fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01',
                cache_dir=tmp_path, min_years=5)
    assert len(mock_yfinance) == 1
    # Second call: cache hit (file just created, well under 24h old)
    fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01',
                cache_dir=tmp_path, min_years=5)
    assert len(mock_yfinance) == 1, 'second call should not invoke yfinance'

  def test_stale_cache_refetches(self, tmp_path, mock_yfinance):
    fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01',
                cache_dir=tmp_path, min_years=5)
    assert len(mock_yfinance) == 1
    # Make cache appear 25h old
    cache_file = tmp_path / '^AXJO-2021-05-01-2026-05-01.parquet'
    old_ts = cache_file.stat().st_mtime - 25 * 3600
    import os as _os
    _os.utime(cache_file, (old_ts, old_ts))
    # Next call must re-fetch
    fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01',
                cache_dir=tmp_path, min_years=5)
    assert len(mock_yfinance) == 2


class TestParquetRoundTrip:
  def test_parquet_preserves_tz_aware_index(self, tmp_path, mock_yfinance):
    df1 = fetch_ohlcv('AUDUSD=X', '2021-05-01', '2026-05-01',
                      cache_dir=tmp_path, min_years=5)
    cache_file = tmp_path / 'AUDUSD=X-2021-05-01-2026-05-01.parquet'
    df2 = pd.read_parquet(cache_file, engine='pyarrow')
    assert df1.index.tz is not None
    assert df2.index.tz is not None
    assert str(df1.index.tz) == str(df2.index.tz)
    pd.testing.assert_frame_equal(df1, df2, check_freq=False)

  def test_required_columns_present(self, tmp_path, mock_yfinance):
    df = fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01',
                     cache_dir=tmp_path, min_years=5)
    assert {'Open', 'High', 'Low', 'Close', 'Volume'}.issubset(set(df.columns))


class TestRefreshFlag:
  def test_refresh_true_ignores_fresh_cache(self, tmp_path, mock_yfinance):
    fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01',
                cache_dir=tmp_path, min_years=5)
    assert len(mock_yfinance) == 1
    # refresh=True forces re-fetch even though cache is brand new
    fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01',
                cache_dir=tmp_path, min_years=5, refresh=True)
    assert len(mock_yfinance) == 2


class TestShortDataBail:
  def test_short_frame_raises_short_frame_error(self, tmp_path, monkeypatch):
    def _ticker_factory(symbol):
      mock = MagicMock()
      mock.history = lambda **kw: _make_short_df()
      return mock
    monkeypatch.setattr('backtest.data_fetcher.yf.Ticker', _ticker_factory)

    with pytest.raises(ShortFrameError, match='only has'):
      fetch_ohlcv('^AXJO', '2025-05-01', '2026-05-01',
                  cache_dir=tmp_path, min_years=5)

  def test_empty_frame_raises_data_fetch_error(self, tmp_path, monkeypatch):
    def _ticker_factory(symbol):
      mock = MagicMock()
      mock.history = lambda **kw: pd.DataFrame()
      return mock
    monkeypatch.setattr('backtest.data_fetcher.yf.Ticker', _ticker_factory)

    with pytest.raises(DataFetchError):
      fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01',
                  cache_dir=tmp_path, min_years=5)


class TestCacheFilename:
  def test_filename_includes_symbol_and_dates(self, tmp_path):
    path = _cache_path('^AXJO', '2021-05-01', '2026-05-01', tmp_path)
    assert path.name == '^AXJO-2021-05-01-2026-05-01.parquet'

  def test_audusd_filename(self, tmp_path):
    path = _cache_path('AUDUSD=X', '2021-05-01', '2026-05-01', tmp_path)
    assert path.name == 'AUDUSD=X-2021-05-01-2026-05-01.parquet'
