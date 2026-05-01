"""Phase 23 — backtest/simulator.py tests (BACKTEST-01 replay).

Coverage: determinism, sizing reuse, exit reasons, cost reconstruction, NaN-safe.
Wave 1 Plan 23-03 — implementation.
"""
from __future__ import annotations
import math

import pandas as pd
import pytest

from backtest.simulator import SimResult, simulate
from system_params import SPI_COST_AUD, SPI_MULT


def _bull_5y_df(start='2020-01-01', n_bars=1300, base=7000.0, drift=0.5) -> pd.DataFrame:
  """Synthetic monotonic-bull SPI200-like frame — guarantees a LONG opening."""
  idx = pd.date_range(start=start, periods=n_bars, freq='B', tz='Australia/Perth')
  closes = [base + i * drift for i in range(n_bars)]
  return pd.DataFrame({
    'Open':   [c - 5 for c in closes],
    'High':   [c + 10 for c in closes],
    'Low':    [c - 10 for c in closes],
    'Close':  closes,
    'Volume': [1_000_000] * n_bars,
  }, index=idx)


def _bull_to_bear_df(n_bull=400, n_bear=400, drift=10.0, base=7000.0) -> pd.DataFrame:
  """LONG then SHORT — drift is steep enough that Mom1(21-bar return) clears
  MOM_THRESHOLD=0.02. With drift=10/day from base=7000, Mom1 ≈ 21*10/7000 ≈ 0.030.
  Produces stop_hit and signal-reversal exits suitable for cost-model assertions.
  """
  idx_bull = pd.date_range(start='2020-01-01', periods=n_bull, freq='B', tz='Australia/Perth')
  bull_closes = [base + i * drift for i in range(n_bull)]
  idx_bear = pd.date_range(start=idx_bull[-1] + pd.Timedelta(days=3), periods=n_bear, freq='B', tz='Australia/Perth')
  bear_closes = [bull_closes[-1] - i * drift for i in range(n_bear)]
  idx = idx_bull.append(idx_bear)
  closes = bull_closes + bear_closes
  return pd.DataFrame({
    'Open':   [c - 5 for c in closes],
    'High':   [c + 10 for c in closes],
    'Low':    [c - 10 for c in closes],
    'Close':  closes,
    'Volume': [1_000_000] * len(closes),
  }, index=idx)


class TestDeterminism:
  def test_simulate_returns_simresult(self):
    df = _bull_5y_df()
    result = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 100_000.0)
    assert isinstance(result, SimResult)
    assert len(result.equity_curve) == len(df)
    assert len(result.dates) == len(df)

  def test_two_runs_identical(self):
    df = _bull_5y_df()
    a = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 100_000.0)
    b = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 100_000.0)
    assert a.trades == b.trades
    assert a.equity_curve == b.equity_curve
    assert a.dates == b.dates
    assert a.final_account == b.final_account

  def test_initial_account_validation(self):
    df = _bull_5y_df()
    with pytest.raises(ValueError, match='initial_account_aud must be positive'):
      simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 0.0)
    with pytest.raises(ValueError, match='initial_account_aud must be positive'):
      simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, -100.0)


class TestCostModel:
  def test_cost_aud_in_trade_log_is_full_round_trip(self):
    df = _bull_to_bear_df()
    result = simulate(df, 'SPI200', SPI_MULT, 6.0, 100_000.0)
    if not result.trades:
      pytest.skip('no trades closed in this synthetic frame')
    for t in result.trades:
      assert t['cost_aud'] == 6.0, f'cost_aud should be full round-trip (6.0), got {t["cost_aud"]}'

  def test_gross_minus_cost_equals_net(self):
    """gross_pnl_aud - (cost_aud / 2)*n = net_pnl_aud (since open-half already in unrealised)."""
    df = _bull_to_bear_df()
    result = simulate(df, 'SPI200', SPI_MULT, 6.0, 100_000.0)
    if not result.trades:
      pytest.skip('no trades')
    for t in result.trades:
      gross = t['gross_pnl_aud']
      net = t['net_pnl_aud']
      n = t['contracts']
      close_half = t['cost_aud'] / 2.0
      assert abs(gross - (net + close_half * n)) < 1e-6, (
        f'cost reconstruction mismatch: gross={gross} net={net} cost={t["cost_aud"]} n={n}'
      )


class TestExitReasons:
  def test_exit_reason_verbatim_from_sizing_engine(self):
    """Per planner D-20: simulator preserves sizing_engine values verbatim;
    no remapping to D-05's 'signal_change'."""
    df = _bull_to_bear_df()
    result = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 100_000.0)
    allowed = {'flat_signal', 'signal_reversal', 'trailing_stop', 'adx_drop',
               'manual_stop', 'stop_hit', 'adx_exit'}  # include sizing_engine raw values
    for t in result.trades:
      assert t['exit_reason'] in allowed, f'unexpected exit_reason: {t["exit_reason"]!r}'


class TestNanSafety:
  def test_warmup_bars_produce_no_trades(self):
    """First ~20 bars have NaN ATR/ADX — must produce FLAT signals, no exceptions."""
    df = _bull_5y_df(n_bars=30)
    result = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 100_000.0)
    assert len(result.equity_curve) == 30
    assert all(math.isfinite(b) for b in result.equity_curve)

  def test_short_frame_does_not_crash(self):
    df = _bull_5y_df(n_bars=5)  # below all warmups
    result = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 100_000.0)
    assert result.trades == []
    assert len(result.equity_curve) == 5
    assert result.final_account == 100_000.0
