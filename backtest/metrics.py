"""Phase 23 — pure aggregation: Sharpe / max DD / win rate / expectancy / cum return.

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY.
Forbidden imports (BACKTEST_PATHS_PURE AST guard): state_manager, notifier,
dashboard, main, requests, datetime, os, json, html, yfinance, pyarrow.
Allowed: math, statistics, typing, pandas, numpy.

Pass criterion (CONTEXT D-16): cumulative_return_pct > 100.0 STRICT (greater-than,
not greater-or-equal). Boundary at exactly 100.0 → pass=False.

Sharpe convention (RESEARCH A1 + planner D-19): emit BOTH the raw daily ratio
(sharpe_daily) AND the annualized form (sharpe_annualized = daily × √252). UI
label corrects D-05's misleading 'sharpe_daily' name to 'Sharpe (annualised)'.
"""
from __future__ import annotations
import math
import statistics
from typing import Sequence

import pandas as pd

_TRADING_DAYS_PER_YEAR = 252
_PASS_THRESHOLD_PCT = 100.0  # D-16 strict greater-than


def _cumulative_return_pct(equity_curve: Sequence[float]) -> float:
  """((final - initial) / initial) * 100. Returns 0.0 if initial <= 0 or len < 2."""
  if len(equity_curve) < 2:
    return 0.0
  initial = equity_curve[0]
  final = equity_curve[-1]
  if initial <= 0:
    return 0.0
  return (final / initial - 1.0) * 100.0


def _daily_returns(equity_curve: Sequence[float]) -> list[float]:
  """Per-bar simple returns; skips bars where prior equity <= 0."""
  out: list[float] = []
  for i in range(1, len(equity_curve)):
    prev = equity_curve[i - 1]
    if prev > 0:
      out.append(equity_curve[i] / prev - 1.0)
  return out


def _sharpe_daily(returns: Sequence[float]) -> float:
  """Raw daily Sharpe = mean / std (ddof=1). Returns 0.0 if undefined."""
  if len(returns) < 2:
    return 0.0
  mean_r = statistics.mean(returns)
  std_r = statistics.stdev(returns)  # ddof=1
  if std_r <= 0 or not math.isfinite(std_r):
    return 0.0
  return mean_r / std_r


def _max_drawdown_pct(equity_curve: Sequence[float]) -> float:
  """Peak-to-trough drawdown using pandas cummax idiom (RESEARCH §Pattern 7).

  Returns a negative percentage (e.g. -23.10 for a 23.10% drawdown). 0.0 if
  flat or len < 2.
  """
  if len(equity_curve) < 2:
    return 0.0
  eq = pd.Series(equity_curve, dtype='float64')
  rolling_max = eq.cummax()
  # Guard: divide-by-zero if rolling_max ever 0 (initial=0 already screened above)
  drawdown = (eq / rolling_max) - 1.0
  return float(drawdown.min()) * 100.0


def _win_rate_expectancy(trades: list[dict]) -> tuple[float, float, int]:
  """Returns (win_rate, expectancy_aud, total_trades). Empty list → (0.0, 0.0, 0)."""
  n = len(trades)
  if n == 0:
    return 0.0, 0.0, 0
  pnls = [float(t['net_pnl_aud']) for t in trades]
  wins = sum(1 for p in pnls if p > 0)
  win_rate = wins / n
  expectancy = sum(pnls) / n
  return win_rate, expectancy, n


def compute_metrics(equity_curve: Sequence[float], trades: list[dict]) -> dict:
  """Phase 23 BACKTEST-02 — aggregate equity curve + closed trades into D-05 metrics.

  Args:
    equity_curve: list of AUD account balances, ascending. equity_curve[0] = initial.
    trades: list of trade dicts (D-05 schema; only `net_pnl_aud` consumed here).

  Returns:
    dict with keys: cumulative_return_pct, sharpe_daily, sharpe_annualized,
    max_drawdown_pct, win_rate, expectancy_aud, total_trades, pass.
  """
  cum_return = _cumulative_return_pct(equity_curve)
  returns = _daily_returns(equity_curve)
  sharpe_d = _sharpe_daily(returns)
  sharpe_a = sharpe_d * math.sqrt(_TRADING_DAYS_PER_YEAR)
  max_dd = _max_drawdown_pct(equity_curve)
  win_rate, expectancy, total_trades = _win_rate_expectancy(trades)

  return {
    'cumulative_return_pct': round(cum_return, 4),
    'sharpe_daily': round(sharpe_d, 4),
    'sharpe_annualized': round(sharpe_a, 4),
    'max_drawdown_pct': round(max_dd, 4),
    'win_rate': round(win_rate, 4),
    'expectancy_aud': round(expectancy, 4),
    'total_trades': total_trades,
    'pass': cum_return > _PASS_THRESHOLD_PCT,  # STRICT (D-16)
  }
