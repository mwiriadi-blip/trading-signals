---
id: 23-02
title: Wave 1A — backtest/data_fetcher.py (yfinance + parquet cache)
phase: 23
plan: 02
type: execute
wave: 1
depends_on: [23-01]
files_modified:
  - backtest/data_fetcher.py
  - tests/test_backtest_data_fetcher.py
requirements: [BACKTEST-01]
threat_refs: [T-23-cache-tamper, T-23-pyarrow]
autonomous: true
gap_closure: false

must_haves:
  truths:
    - "backtest/data_fetcher.fetch_ohlcv(symbol, start, end, refresh) returns a pandas DataFrame with at least 5y of OHLCV"
    - "First call writes a parquet cache file at .planning/backtests/data/<symbol>-<start>-<end>.parquet"
    - "Subsequent calls within 24h read from the cache (no yfinance call)"
    - "refresh=True forces re-fetch even when cache is fresh"
    - "Symbols with <5y of data raise ShortFrameError (D-17)"
    - "DatetimeIndex round-trips through parquet without timezone drift"
  artifacts:
    - path: "backtest/data_fetcher.py"
      provides: "fetch_ohlcv(symbol, start, end, refresh) public API + cache helpers"
      exports: ["fetch_ohlcv", "ShortFrameError", "DataFetchError", "_is_cache_fresh", "_cache_path"]
    - path: "tests/test_backtest_data_fetcher.py"
      provides: "TestCacheHitMiss + TestParquetRoundTrip + TestRefreshFlag + TestShortDataBail"
  key_links:
    - from: "backtest/data_fetcher.py"
      to: "yfinance"
      via: "yfinance.Ticker(symbol).history(start=, end=, interval='1d')"
      pattern: "yfinance.Ticker"
    - from: "backtest/data_fetcher.py"
      to: "pyarrow"
      via: "df.to_parquet(path, engine='pyarrow') / pd.read_parquet(path, engine='pyarrow')"
      pattern: "engine='pyarrow'"
---

<objective>
Implement `backtest/data_fetcher.py` — the ONE I/O exception in the backtest hex (per CONTEXT D-09). Wraps yfinance with a 24h parquet cache at `.planning/backtests/data/<symbol>-<start>-<end>.parquet`. Replaces the Wave 0 NotImplementedError stub.

Purpose: Decouple yfinance latency (10-30s on cache miss) from per-run cost. Backtests after the first within 24h are sub-second on the data layer.
Output: `fetch_ohlcv` callable + 4 test classes covering cache hit/miss, parquet round-trip, refresh flag, <5y bail.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md
@.planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md
@.planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md
@CLAUDE.md
@data_fetcher.py
@tests/test_data_fetcher.py
@.planning/phases/23-five-year-backtest-validation-gate/23-01-wave0-scaffolding-PLAN.md

<interfaces>
<!-- Existing data_fetcher.py (top-level, Phase 4) — analog for backtest/data_fetcher.py -->
data_fetcher.py exports:
- fetch_ohlcv(symbol: str, retries: int = 3, backoff_s: float = 10.0) -> pd.DataFrame
- DataFetchError(Exception)
- ShortFrameError(Exception)  # raised when N rows < threshold
- _RETRY_EXCEPTIONS = (YFRateLimitError, ReadTimeout, ConnectionError)
- _REQUIRED_COLUMNS = frozenset({'Open', 'High', 'Low', 'Close', 'Volume'})

<!-- Backtest data_fetcher CONTRACT (this plan) -->
def fetch_ohlcv(
  symbol: str,                     # '^AXJO' or 'AUDUSD=X'
  start: str,                      # ISO 'YYYY-MM-DD'
  end: str,                        # ISO 'YYYY-MM-DD'
  refresh: bool = False,           # ignore cache if True
  cache_dir: pathlib.Path | None = None,  # default '.planning/backtests/data'
  min_years: int = 5,              # bail if data spans <5y per D-17
) -> pd.DataFrame:
  """Returns OHLCV DataFrame with DatetimeIndex (TZ-aware preserved through parquet)."""

class ShortFrameError(ValueError):
  """Raised when yfinance returns < min_years of data per CONTEXT D-17."""

class DataFetchError(Exception):
  """Raised after exhausting retries on yfinance network errors."""

<!-- pyarrow round-trip pattern (RESEARCH §Pitfall 8) -->
df.to_parquet(path, engine='pyarrow')              # writes TZ-aware DatetimeIndex correctly
df_read = pd.read_parquet(path, engine='pyarrow')  # round-trip preserves index
</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| yfinance HTTPS → fetcher | Untrusted external data source; retry-loop handles transient failure |
| operator → cache file | Operator-controlled (manually deletable); recovery = `--refresh` flag |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-23-cache-tamper | Tampering | .planning/backtests/data/*.parquet | mitigate | Parquet schema-typed binary format (no eval/code paths on read); validate `_REQUIRED_COLUMNS` after read; `--refresh` recovery |
| T-23-pyarrow | Tampering/Supply-chain | pyarrow read path | accept | Wave 0 pinned `pyarrow==24.0.0` from PyPI binary wheel; this plan uses the engine without further attack-surface expansion |
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement backtest/data_fetcher.py (cache + fetch + bail)</name>
  <read_first>
    - backtest/data_fetcher.py (current Wave 0 skeleton)
    - data_fetcher.py lines 1-132 (analog: top-level fetch_ohlcv with retry loop, narrow exception tuple, _REQUIRED_COLUMNS validation)
    - .planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md §Code Examples §"Parquet cache hit/miss check" (lines 558-577)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"backtest/data_fetcher.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md §D-01, §D-17
  </read_first>
  <behavior>
    - Test 1: cache miss → calls yfinance, writes parquet, returns DataFrame
    - Test 2: cache hit (file exists, mtime <24h) → reads parquet, no yfinance call
    - Test 3: cache stale (mtime >24h) → re-fetches yfinance
    - Test 4: refresh=True with fresh cache → still re-fetches
    - Test 5: yfinance returns <5y of data → raises ShortFrameError
    - Test 6: yfinance returns DataFrame missing OHLCV columns → raises DataFetchError
    - Test 7: parquet round-trip preserves TZ-aware DatetimeIndex (RESEARCH §Pitfall 8)
    - Test 8: cache filename format = `<symbol>-<start>-<end>.parquet` exactly
  </behavior>
  <action>
    Replace the `backtest/data_fetcher.py` Wave 0 stub with the full implementation:

    ```python
    """Phase 23 — I/O adapter for backtest module (the ONE I/O exception per CONTEXT D-09).

    Wraps yfinance with parquet cache at `.planning/backtests/data/<symbol>-<from>-<to>.parquet`.
    24h staleness; refresh=True forces re-fetch.

    EXPLICITLY EXCLUDED from BACKTEST_PATHS_PURE AST guard (tests/test_signal_engine.py).
    Allowed imports per D-09: yfinance, pyarrow, pandas, pathlib, datetime, logging, time.
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
      """yfinance fetch terminal failure."""


    class ShortFrameError(ValueError):
      """yfinance returned fewer than min_years of data (CONTEXT D-17)."""


    def _cache_path(symbol: str, start: str, end: str, cache_dir: Path) -> Path:
      """Filename format per CONTEXT D-01: <symbol>-<start>-<end>.parquet."""
      # Sanitize symbol — '^AXJO' contains '^' which is filesystem-safe but
      # we keep it verbatim per D-01 example: '^AXJO-2021-05-01-2026-05-01.parquet'.
      return cache_dir / f'{symbol}-{start}-{end}.parquet'


    def _is_cache_fresh(path: Path, max_age_seconds: int = _CACHE_TTL_SECONDS) -> bool:
      if not path.exists():
        return False
      age = time.time() - os.path.getmtime(path)
      return age < max_age_seconds


    def _fetch_yfinance(symbol: str, start: str, end: str) -> pd.DataFrame:
      """Single yfinance call; returns DataFrame or raises DataFetchError."""
      logger.info('[Backtest] Fetching %s %s..%s (cache miss; pulling yfinance)', symbol, start, end)
      try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval='1d', auto_adjust=False)
      except Exception as exc:  # broad — yfinance has many failure modes
        raise DataFetchError(f'yfinance fetch failed for {symbol}: {exc}') from exc

      if df is None or df.empty:
        raise DataFetchError(f'yfinance returned empty frame for {symbol} {start}..{end}')

      missing = _REQUIRED_COLUMNS - set(df.columns)
      if missing:
        raise DataFetchError(
          f'yfinance frame for {symbol} missing required columns: {sorted(missing)}'
        )
      return df


    def _validate_min_years(df: pd.DataFrame, symbol: str, min_years: int) -> None:
      """Raises ShortFrameError per CONTEXT D-17 if data spans < min_years."""
      if df.empty:
        raise ShortFrameError(f'[Backtest] FAIL {symbol} returned empty frame; need {min_years}y')
      span_days = (df.index.max() - df.index.min()).days
      span_years = span_days / 365.25
      if span_years < min_years:
        raise ShortFrameError(
          f'[Backtest] FAIL {symbol} only has {span_years:.2f} years of data; need {min_years}'
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
        min_years: bail if data spans < this many years (D-17).

      Returns:
        OHLCV DataFrame with DatetimeIndex preserved through parquet round-trip.

      Raises:
        DataFetchError: yfinance terminal failure or missing required columns.
        ShortFrameError: data spans < min_years.
      """
      cache_root = cache_dir or _CACHE_DIR_DEFAULT
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
    ```
  </action>
  <verify>
    <automated>python -c "from backtest.data_fetcher import fetch_ohlcv, DataFetchError, ShortFrameError, _cache_path, _is_cache_fresh; from pathlib import Path; assert _cache_path('^AXJO', '2021-05-01', '2026-05-01', Path('/tmp')).name == '^AXJO-2021-05-01-2026-05-01.parquet'; print('ok')" 2>&1 | grep -c '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c '^def fetch_ohlcv' backtest/data_fetcher.py` returns 1
    - `grep -c '^class ShortFrameError' backtest/data_fetcher.py` returns 1
    - `grep -c '^class DataFetchError' backtest/data_fetcher.py` returns 1
    - `grep -c '_REQUIRED_COLUMNS' backtest/data_fetcher.py` returns ≥1 (set contains Open/High/Low/Close/Volume)
    - `grep -c "engine='pyarrow'" backtest/data_fetcher.py` returns ≥2 (write + read)
    - `grep -c '\[Backtest\]' backtest/data_fetcher.py` returns ≥3 (cache hit, cache miss, cached log lines)
    - `grep -c '^import state_manager\|^from state_manager\|^import notifier\|^from notifier\|^import dashboard\|^from dashboard\|^import main' backtest/data_fetcher.py` returns 0 (D-09)
    - `python -c "from backtest.data_fetcher import _cache_path; from pathlib import Path; assert str(_cache_path('AUDUSD=X', '2021-05-01', '2026-05-01', Path('.planning/backtests/data'))).endswith('AUDUSD=X-2021-05-01-2026-05-01.parquet')"` succeeds
    - `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism -x -q` continues to pass (data_fetcher excluded from AST guard per D-09)
  </acceptance_criteria>
  <done>fetch_ohlcv handles cache hit/miss/refresh/short-frame correctly; module imports cleanly; AST guard regression-free.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement tests/test_backtest_data_fetcher.py (4 test classes)</name>
  <read_first>
    - backtest/data_fetcher.py (just-implemented)
    - tests/test_data_fetcher.py — analog (existing yfinance retry tests; structure to mirror)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"tests/test_backtest_data_fetcher.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-VALIDATION.md (Per-Task Verification Map)
  </read_first>
  <behavior>
    - TestCacheHitMiss: monkeypatch yfinance.Ticker to return canned 5y DataFrame; first call hits yfinance, second call within 24h does NOT
    - TestParquetRoundTrip: write 5y df, read back, assert frame_equal (incl. DatetimeIndex tz)
    - TestRefreshFlag: with fresh cache, refresh=True still calls yfinance
    - TestShortDataBail: yfinance returns 1y of data → ShortFrameError raised
    - Bonus: cache filename format test (no edge-case escapes for `^AXJO` symbol)
  </behavior>
  <action>
    Replace the Wave 0 `tests/test_backtest_data_fetcher.py` skeleton with full tests:

    ```python
    """Phase 23 — backtest/data_fetcher.py tests (BACKTEST-01 data layer).

    Coverage: cache hit/miss, refresh, parquet round-trip, <5y bail.
    """
    from __future__ import annotations
    from pathlib import Path
    from unittest.mock import MagicMock

    import pandas as pd
    import pytest

    from backtest.data_fetcher import (
      DataFetchError,
      ShortFrameError,
      _cache_path,
      _is_cache_fresh,
      fetch_ohlcv,
    )


    def _make_5y_df(start: str = '2021-04-15', end: str = '2026-05-15') -> pd.DataFrame:
      """Synthetic 5y+ calendar-daily OHLCV frame with TZ-aware DatetimeIndex.

      Warning 3 fix: uses freq='D' (calendar daily) and slightly wider start/end
      so the frame's calendar span comfortably exceeds 5 years. This lets the
      tests below call the PRODUCTION min_years=5 threshold instead of the
      previous min_years=4 workaround.
      """
      idx = pd.date_range(start=start, end=end, freq='D', tz='Australia/Perth')  # calendar days
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
          # exceeds min_years=5 regardless of the requested window (Warning 3).
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
        assert len(df) > 1000  # ~5y business days

      def test_cache_hit_skips_yfinance(self, tmp_path, mock_yfinance):
        # First call: cache miss
        fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01', cache_dir=tmp_path, min_years=5)
        assert len(mock_yfinance) == 1
        # Second call: cache hit (file just created, well under 24h old)
        fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01', cache_dir=tmp_path, min_years=5)
        assert len(mock_yfinance) == 1, 'second call should not invoke yfinance'

      def test_stale_cache_refetches(self, tmp_path, mock_yfinance, monkeypatch):
        # Seed cache
        fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01', cache_dir=tmp_path, min_years=5)
        assert len(mock_yfinance) == 1
        # Make cache appear 25h old
        cache_file = tmp_path / '^AXJO-2021-05-01-2026-05-01.parquet'
        old_ts = cache_file.stat().st_mtime - 25 * 3600
        import os as _os
        _os.utime(cache_file, (old_ts, old_ts))
        # Next call must re-fetch
        fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01', cache_dir=tmp_path, min_years=5)
        assert len(mock_yfinance) == 2


    class TestParquetRoundTrip:
      def test_parquet_preserves_tz_aware_index(self, tmp_path, mock_yfinance):
        df1 = fetch_ohlcv('AUDUSD=X', '2021-05-01', '2026-05-01',
                         cache_dir=tmp_path, min_years=5)
        # Read directly to bypass the cache-fresh path
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
        fetch_ohlcv('^AXJO', '2021-05-01', '2026-05-01', cache_dir=tmp_path, min_years=5)
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
    ```
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_backtest_data_fetcher.py -x -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `.venv/bin/pytest tests/test_backtest_data_fetcher.py -x -q` passes (all classes green, no skips)
    - `pytest tests/test_backtest_data_fetcher.py::TestCacheHitMiss -x` passes ≥3 tests
    - `pytest tests/test_backtest_data_fetcher.py::TestParquetRoundTrip -x` passes ≥2 tests
    - `pytest tests/test_backtest_data_fetcher.py::TestRefreshFlag -x` passes ≥1 test
    - `pytest tests/test_backtest_data_fetcher.py::TestShortDataBail -x` passes ≥2 tests
    - No real yfinance network calls (all monkeypatched)
    - Test runtime < 5 seconds
  </acceptance_criteria>
  <done>All four test classes from VALIDATION.md are green; backtest/data_fetcher.py is feature-complete and tested.</done>
</task>

</tasks>

<verification>
1. `.venv/bin/pytest tests/test_backtest_data_fetcher.py -x -q` passes
2. `python -c "from backtest.data_fetcher import fetch_ohlcv, ShortFrameError, DataFetchError; print('ok')"` prints `ok`
3. `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism -x -q` continues to pass (data_fetcher excluded from AST guard)
4. No regression in full suite: `.venv/bin/pytest -x -q` exits 0
</verification>

<success_criteria>
- `backtest/data_fetcher.fetch_ohlcv` callable; cache hit/miss/refresh/short-bail all work
- 4 test classes in tests/test_backtest_data_fetcher.py all green
- Parquet round-trip preserves TZ-aware DatetimeIndex
- ShortFrameError raised per CONTEXT D-17 on <5y data
- Log lines use `[Backtest]` prefix per CONTEXT D-11
</success_criteria>

<output>
Create `.planning/phases/23-five-year-backtest-validation-gate/23-02-SUMMARY.md` documenting:
- fetch_ohlcv signature finalized
- Cache filename format verified
- Test count + pass status
- Any deviations from RESEARCH §Code Examples
</output>
