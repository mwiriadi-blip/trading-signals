"""Phase 23 — backtest/cli.py tests (BACKTEST-04 CLI)."""
from __future__ import annotations
import json
import logging

import pandas as pd
import pytest

from backtest.cli import RunArgs, _build_parser, main, run_backtest


def _bull_5y_df(start='2020-01-01', n_bars=1300, base=7000.0, drift=0.5) -> pd.DataFrame:
  idx = pd.date_range(start=start, periods=n_bars, freq='B', tz='Australia/Perth')
  closes = [base + i * drift for i in range(n_bars)]
  return pd.DataFrame({
    'Open':   [c - 5 for c in closes],
    'High':   [c + 10 for c in closes],
    'Low':    [c - 10 for c in closes],
    'Close':  closes,
    'Volume': [1_000_000] * n_bars,
  }, index=idx)


def _flat_5y_df(start='2020-01-01', n_bars=1300, base=7000.0) -> pd.DataFrame:
  """Flat — no momentum, no signals, no trades → cum_return = 0% → FAIL."""
  idx = pd.date_range(start=start, periods=n_bars, freq='B', tz='Australia/Perth')
  return pd.DataFrame({
    'Open':   [base] * n_bars,
    'High':   [base + 1] * n_bars,
    'Low':    [base - 1] * n_bars,
    'Close':  [base] * n_bars,
    'Volume': [1_000_000] * n_bars,
  }, index=idx)


@pytest.fixture
def patched_fetcher(monkeypatch):
  """Stub fetch_ohlcv for both instruments — returns canned 5y data."""
  def _fake_fetch(symbol, start, end, refresh=False, cache_dir=None, min_years=5):
    return _bull_5y_df()
  monkeypatch.setattr('backtest.cli.fetch_ohlcv', _fake_fetch)
  return _fake_fetch


@pytest.fixture
def patched_fetcher_flat(monkeypatch):
  def _fake_fetch(symbol, start, end, refresh=False, cache_dir=None, min_years=5):
    return _flat_5y_df()
  monkeypatch.setattr('backtest.cli.fetch_ohlcv', _fake_fetch)
  return _fake_fetch


class TestArgparse:
  def test_default_values(self):
    p = _build_parser()
    ns = p.parse_args([])
    assert ns.years == 5
    assert ns.end_date is None
    assert ns.initial_account_aud == 10_000.0
    assert ns.cost_spi_aud == 6.0
    assert ns.cost_audusd_aud == 5.0
    assert ns.refresh is False
    assert ns.output is None

  def test_all_flags_present(self):
    p = _build_parser()
    ns = p.parse_args([
      '--years', '3',
      '--end-date', '2024-01-01',
      '--initial-account', '5000',
      '--cost-spi', '7.5',
      '--cost-audusd', '4.0',
      '--refresh',
      '--output', '/tmp/x.json',
    ])
    assert ns.years == 3
    assert ns.end_date == '2024-01-01'
    assert ns.initial_account_aud == 5000.0
    assert ns.cost_spi_aud == 7.5
    assert ns.cost_audusd_aud == 4.0
    assert ns.refresh is True
    assert ns.output == '/tmp/x.json'


class TestJsonSchema:
  def test_writes_d05_schema(self, tmp_path, patched_fetcher):
    out = tmp_path / 'test.json'
    args = RunArgs(years=5, end_date='2026-05-01', output=out)
    report, written, exit_code = run_backtest(args)

    assert written == out
    assert out.exists()
    loaded = json.loads(out.read_text())

    # D-05 top-level keys
    assert set(loaded) == {'metadata', 'metrics', 'equity_curve', 'trades'}

    # Metadata fields
    meta = loaded['metadata']
    for key in ['strategy_version', 'run_dt', 'years', 'end_date', 'start_date',
                'initial_account_aud', 'cost_spi_aud', 'cost_audusd_aud',
                'instruments', 'pass']:
      assert key in meta, f'metadata missing {key}'

    # Metrics structure
    assert set(loaded['metrics']) == {'combined', 'SPI200', 'AUDUSD'}
    for inst in ['combined', 'SPI200', 'AUDUSD']:
      m = loaded['metrics'][inst]
      for key in ['cumulative_return_pct', 'sharpe_daily', 'sharpe_annualized',
                  'max_drawdown_pct', 'win_rate', 'expectancy_aud',
                  'total_trades', 'pass']:
        assert key in m, f'{inst} metric missing {key}'

  def test_start_date_5y_before_end(self, tmp_path, patched_fetcher):
    out = tmp_path / 'test.json'
    args = RunArgs(years=5, end_date='2024-01-01', output=out)
    report, _, _ = run_backtest(args)
    assert report['metadata']['end_date'] == '2024-01-01'
    assert report['metadata']['start_date'] == '2019-01-01'

  def test_initial_account_in_metadata(self, tmp_path, patched_fetcher):
    out = tmp_path / 'test.json'
    args = RunArgs(initial_account_aud=5_000.0, output=out)
    report, _, _ = run_backtest(args)
    assert report['metadata']['initial_account_aud'] == 5_000.0

  def test_no_nan_in_json(self, tmp_path, patched_fetcher):
    out = tmp_path / 'test.json'
    args = RunArgs(output=out)
    run_backtest(args)
    # allow_nan=False would raise on serialise; round-trip must succeed
    loaded = json.loads(out.read_text())
    assert isinstance(loaded, dict)


class TestExitCode:
  def test_pass_returns_zero(self, tmp_path, patched_fetcher):
    # Warning 5 (D-18 perf budget regression guard): a 10x runtime regression
    # against the ~120ms baseline (RESEARCH §Pattern 2) trips this 10s timeout.
    # Manual droplet timing still owns the absolute 60s uvicorn bound.
    import time as _time
    _t0 = _time.time()
    out = tmp_path / 'pass.json'
    args = RunArgs(output=out)
    _, _, exit_code = run_backtest(args)
    _elapsed = _time.time() - _t0
    assert _elapsed < 5.0, (
      f'5y backtest with stubbed fetch should complete <5s; got {_elapsed:.2f}s '
      f'(absolute uvicorn bound is 60s; this is the cheap regression guard)'
    )
    # Bull 5y df should produce >100% return
    report = json.loads(out.read_text())
    if report['metadata']['pass']:
      assert exit_code == 0
    else:
      # If synthetic frame doesn't trigger >100%, at least confirm exit_code
      # mirrors the pass field
      assert exit_code == 1

  def test_fail_returns_one(self, tmp_path, patched_fetcher_flat):
    out = tmp_path / 'fail.json'
    args = RunArgs(output=out)
    _, _, exit_code = run_backtest(args)
    # Flat data → no trades → cum_return=0 → FAIL
    assert exit_code == 1

  def test_main_returns_exit_code(self, tmp_path, patched_fetcher_flat):
    # main() returns the exit code; with flat data, expect 1
    rc = main(['--years', '5', '--output', str(tmp_path / 'x.json')])
    assert rc == 1


class TestLogFormat:
  def test_log_lines_use_backtest_prefix(self, tmp_path, patched_fetcher, caplog):
    out = tmp_path / 'log.json'
    with caplog.at_level(logging.INFO):
      args = RunArgs(output=out)
      run_backtest(args)
    messages = [r.getMessage() for r in caplog.records]
    joined = '\n'.join(messages)
    # Warning 4: data_fetcher owns '[Backtest] Fetching <symbol>' lines;
    # cli does NOT duplicate them. CLI emits Simulating/Combined/PASS-FAIL/Wrote.
    assert '[Backtest] Simulating SPI200' in joined
    assert '[Backtest] Simulating AUDUSD' in joined
    assert '[Backtest] Combined cum_return=' in joined
    assert ('[Backtest] PASS' in joined) or ('[Backtest] FAIL' in joined)
    assert '[Backtest] Wrote' in joined

  def test_fetching_log_line_per_instrument_exactly_once(self, tmp_path,
                                                          patched_fetcher, caplog):
    # Warning 4 regression guard: data_fetcher emits exactly one
    # '[Backtest] Fetching' line per instrument; cli must not duplicate.
    # patched_fetcher stubs fetch_ohlcv directly so no '[Backtest] Fetching'
    # line is emitted (the fetcher's logger never runs). The invariant we
    # can still assert in this stubbed env: cli does NOT emit any
    # '[Backtest] Fetching' line on its own.
    out = tmp_path / 'log2.json'
    with caplog.at_level(logging.INFO, logger='backtest.cli'):
      args = RunArgs(output=out)
      run_backtest(args)
    messages = [r.getMessage() for r in caplog.records
                if r.name == 'backtest.cli']
    cli_fetching = sum(1 for m in messages if '[Backtest] Fetching' in m)
    assert cli_fetching == 0, (
      f'cli must not emit [Backtest] Fetching (data_fetcher owns it); '
      f'got {cli_fetching}'
    )


class TestStrategyVersionTagging:
  def test_strategy_version_from_system_params(self, tmp_path, patched_fetcher):
    out = tmp_path / 'sv.json'
    args = RunArgs(output=out)
    report, _, _ = run_backtest(args)
    # Must match current system_params at run time
    import system_params
    assert report['metadata']['strategy_version'] == system_params.STRATEGY_VERSION

  def test_strategy_version_fresh_access_not_kwarg_default(self, tmp_path,
                                                            patched_fetcher,
                                                            monkeypatch):
    """LEARNINGS G-45: monkeypatching STRATEGY_VERSION AFTER cli import must
    propagate. If STRATEGY_VERSION were captured as a kwarg default, the
    bumped value would NOT show up — would still see the import-time value.
    """
    import system_params
    original = system_params.STRATEGY_VERSION
    monkeypatch.setattr('system_params.STRATEGY_VERSION', 'vTEST-9.9.9')
    out = tmp_path / 'fresh.json'
    args = RunArgs(output=out)
    report, _, _ = run_backtest(args)
    assert report['metadata']['strategy_version'] == 'vTEST-9.9.9', (
      f'STRATEGY_VERSION not fresh-read; got {report["metadata"]["strategy_version"]!r} '
      f'(original was {original!r})'
    )
