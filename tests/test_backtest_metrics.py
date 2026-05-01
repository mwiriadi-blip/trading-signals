"""Phase 23 — backtest/metrics.py tests (BACKTEST-02 formulas)."""
from __future__ import annotations
import math

import pytest

from backtest.metrics import compute_metrics


class TestCumulativeReturn:
  def test_doubling_account_is_100pct(self):
    m = compute_metrics([10_000.0, 20_000.0], [])
    assert m['cumulative_return_pct'] == 100.0
    assert m['pass'] is False  # STRICT > 100.0 per D-16

  def test_127pct_passes(self):
    m = compute_metrics([10_000.0, 22_745.0], [])
    assert m['cumulative_return_pct'] == pytest.approx(127.45, abs=1e-4)
    assert m['pass'] is True

  def test_loss_negative(self):
    m = compute_metrics([10_000.0, 8_000.0], [])
    assert m['cumulative_return_pct'] == -20.0
    assert m['pass'] is False

  def test_single_bar_zero(self):
    m = compute_metrics([10_000.0], [])
    assert m['cumulative_return_pct'] == 0.0


class TestSharpe:
  def test_annualized_is_sqrt252_times_daily(self):
    eq = [10_000.0, 10_100.0, 10_050.0, 10_200.0, 10_180.0, 10_300.0]
    m = compute_metrics(eq, [])
    if m['sharpe_daily'] == 0.0:
      pytest.skip('insufficient variance')
    ratio = m['sharpe_annualized'] / m['sharpe_daily']
    assert abs(ratio - math.sqrt(252)) < 1e-4

  def test_zero_variance_returns_zero(self):
    # Flat equity → all returns zero → std=0 → sharpe=0 (guarded)
    m = compute_metrics([10_000.0, 10_000.0, 10_000.0], [])
    assert m['sharpe_daily'] == 0.0
    assert m['sharpe_annualized'] == 0.0

  def test_single_return_returns_zero(self):
    # Only one return point → stdev undefined (needs 2+) → 0
    m = compute_metrics([10_000.0, 11_000.0], [])
    assert m['sharpe_daily'] == 0.0


class TestMaxDrawdown:
  def test_peak_to_trough(self):
    # Rises to 12k, falls to 9k, recovers to 11k
    # Peak=12k, trough after peak = 9k → DD = (9-12)/12 = -25%
    m = compute_metrics([10_000.0, 12_000.0, 9_000.0, 11_000.0], [])
    assert m['max_drawdown_pct'] == pytest.approx(-25.0, abs=1e-4)

  def test_monotonic_rise_zero_dd(self):
    m = compute_metrics([10_000.0, 11_000.0, 12_000.0, 13_000.0], [])
    assert m['max_drawdown_pct'] == 0.0

  def test_strict_decline(self):
    # Pure decline: peak=initial, trough=final
    m = compute_metrics([10_000.0, 9_000.0, 8_000.0, 7_700.0], [])
    assert m['max_drawdown_pct'] == pytest.approx(-23.0, abs=1e-4)

  def test_dd_uses_cummax_not_global_min_over_max(self):
    """Anti-pattern from RESEARCH §Pattern 7: equity.min()/equity.max() - 1
    is WRONG (worst-point vs global-max). Must use cummax peak-to-trough."""
    # Sequence: 100 → 120 → 80 → 200. Global min=80, max=200.
    # Wrong formula would give 80/200 - 1 = -60%.
    # Correct cummax: peak-to-trough is 120 → 80 = -33.33%.
    m = compute_metrics([100.0, 120.0, 80.0, 200.0], [])
    assert m['max_drawdown_pct'] == pytest.approx(-33.3333, abs=1e-3)


class TestWinRateExpectancy:
  def test_zero_trades(self):
    m = compute_metrics([10_000.0, 11_000.0], [])
    assert m['total_trades'] == 0
    assert m['win_rate'] == 0.0
    assert m['expectancy_aud'] == 0.0

  def test_all_wins(self):
    trades = [{'net_pnl_aud': 100.0}, {'net_pnl_aud': 200.0}, {'net_pnl_aud': 50.0}]
    m = compute_metrics([10_000.0, 10_350.0], trades)
    assert m['total_trades'] == 3
    assert m['win_rate'] == 1.0
    assert m['expectancy_aud'] == pytest.approx(116.6667, abs=1e-3)

  def test_all_losses(self):
    trades = [{'net_pnl_aud': -100.0}, {'net_pnl_aud': -50.0}]
    m = compute_metrics([10_000.0, 9_850.0], trades)
    assert m['win_rate'] == 0.0
    assert m['expectancy_aud'] == -75.0

  def test_mixed_50pct(self):
    trades = [{'net_pnl_aud': 100.0}, {'net_pnl_aud': -100.0},
              {'net_pnl_aud': 200.0}, {'net_pnl_aud': -50.0}]
    m = compute_metrics([10_000.0, 10_150.0], trades)
    assert m['win_rate'] == 0.5
    assert m['expectancy_aud'] == pytest.approx(37.5, abs=1e-4)


class TestPassCriterion:
  def test_strictly_above_100_passes(self):
    m = compute_metrics([10_000.0, 20_001.0], [])
    assert m['cumulative_return_pct'] > 100.0
    assert m['pass'] is True

  def test_exactly_100_fails(self):
    """D-16 STRICT greater-than: equality at exactly 100.0 = FAIL."""
    m = compute_metrics([10_000.0, 20_000.0], [])
    assert m['cumulative_return_pct'] == 100.0
    assert m['pass'] is False

  def test_below_100_fails(self):
    m = compute_metrics([10_000.0, 19_999.0], [])
    assert m['cumulative_return_pct'] < 100.0
    assert m['pass'] is False
