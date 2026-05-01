"""Phase 23 — bar-by-bar replay simulator.

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY.
Reuses signal_engine.compute_indicators + sizing_engine.step verbatim per CONTEXT D-10.

Forbidden imports (BACKTEST_PATHS_PURE AST guard):
  state_manager, notifier, dashboard, main, requests, datetime, os, yfinance, schedule,
  json, html, pyarrow.
Allowed: math, dataclasses, typing, system_params, signal_engine, sizing_engine, pandas, numpy.

Cost model (RESEARCH §Pattern 1, §Pitfall 1):
  step() uses Phase 2 D-13 half/half split internally. Backtest passes
  cost_aud_open = round_trip / 2. ClosedTrade.realised_pnl already has the
  closing half deducted; the opening half was charged against unrealised_pnl
  during the open period. Reconstruct full-round-trip cost in the JSON trade
  log per CONTEXT D-05 schema.
"""
from __future__ import annotations
import dataclasses
import math
from typing import Any

import pandas as pd

from signal_engine import ADX_GATE, FLAT, LONG, MOM_THRESHOLD, SHORT, compute_indicators
from sizing_engine import step


@dataclasses.dataclass(frozen=True)
class SimResult:
  trades: list[dict]            # D-05 trade log entries
  equity_curve: list[float]     # one entry per bar, ascending; aligned to df.index
  dates: list[str]              # ISO YYYY-MM-DD aligned with equity_curve
  final_account: float


def _extract_signals(df_ind: pd.DataFrame) -> list[int]:
  """Per-bar LONG/SHORT/FLAT extraction — O(n), NOT O(n^2) (RESEARCH §Pattern 2).

  Replicates signal_engine.get_signal logic inline against the pre-computed
  indicators. Avoids the get_signal(df.iloc[:i+1]) anti-pattern.
  """
  signals: list[int] = []
  for i in range(len(df_ind)):
    row = df_ind.iloc[i]
    adx = row['ADX']
    if pd.isna(adx) or adx < ADX_GATE:
      signals.append(FLAT)
      continue
    moms = [row['Mom1'], row['Mom3'], row['Mom12']]
    valid = [m for m in moms if not pd.isna(m)]
    votes_up = sum(1 for m in valid if m > MOM_THRESHOLD)
    votes_dn = sum(1 for m in valid if m < -MOM_THRESHOLD)
    if votes_up >= 2:
      signals.append(LONG)
    elif votes_dn >= 2:
      signals.append(SHORT)
    else:
      signals.append(FLAT)
  return signals


def _row_to_bar(row: pd.Series, idx) -> dict:
  """Convert pandas row + index to step()-compatible bar dict."""
  return {
    'open': float(row['Open']),
    'high': float(row['High']),
    'low':  float(row['Low']),
    'close': float(row['Close']),
    'date': idx.date().isoformat() if hasattr(idx, 'date') else str(idx)[:10],
  }


def _row_to_indicators(row: pd.Series) -> dict:
  """Convert pandas row to step()-compatible indicators dict.

  NaN preservation: NaN ATR/ADX during warmup propagates to step(), which
  handles it via Phase 2 B-1 NaN policy (NaN guards in get_trailing_stop +
  check_stop_hit + check_pyramid).
  """
  def _f(name: str) -> float:
    v = row[name]
    return float(v) if not pd.isna(v) else float('nan')
  return {
    'atr':  _f('ATR'),
    'adx':  _f('ADX'),
    'pdi':  _f('PDI'),
    'ndi':  _f('NDI'),
    'rvol': _f('RVol'),
  }


def simulate(
  df: pd.DataFrame,
  instrument: str,
  multiplier: float,
  cost_round_trip_aud: float,
  initial_account_aud: float,
) -> SimResult:
  """Phase 23 BACKTEST-01 — bar-by-bar replay.

  Args:
    df: OHLCV DataFrame with DatetimeIndex (from data_fetcher.fetch_ohlcv).
    instrument: 'SPI200' or 'AUDUSD' (used in trade log).
    multiplier: SPI_MULT (5.0) or AUDUSD_MULT (10_000.0).
    cost_round_trip_aud: 6.0 (SPI) or 5.0 (AUDUSD). Halved before step().
    initial_account_aud: starting equity (default 10_000.0 per CONTEXT D-02).

  Returns:
    SimResult with trade log + equity curve aligned to df.index.
  """
  if not math.isfinite(initial_account_aud) or initial_account_aud <= 0:
    raise ValueError(f'initial_account_aud must be positive finite, got {initial_account_aud}')
  if cost_round_trip_aud < 0:
    raise ValueError(f'cost_round_trip_aud must be non-negative, got {cost_round_trip_aud}')

  df_ind = compute_indicators(df)
  signals = _extract_signals(df_ind)
  cost_open = cost_round_trip_aud / 2.0  # half/half split per Phase 2 D-13

  account = float(initial_account_aud)
  position: dict[str, Any] | None = None
  old_signal = FLAT

  trades: list[dict] = []
  equity_curve: list[float] = []
  dates: list[str] = []

  for i in range(len(df_ind)):
    row = df_ind.iloc[i]
    idx = df_ind.index[i]
    bar = _row_to_bar(row, idx)
    indicators = _row_to_indicators(row)
    new_signal = signals[i]

    # Capture position state BEFORE step() in case the position closes this bar
    # — we need entry_date, atr_entry, pyramid_level for the trade log.
    position_before = dict(position) if position is not None else None

    result = step(
      position, bar, indicators, old_signal, new_signal,
      account, multiplier, cost_open,
    )

    if result.closed_trade is not None:
      ct = result.closed_trade
      account += ct.realised_pnl  # close-half already deducted (Phase 2 D-13)

      # Reconstruct trade-log fields per CONTEXT D-05 schema
      # (RESEARCH §Pitfall 1, §Pitfall 7, §Open Question 3 + planner D-20)
      entry_date = (position_before or {}).get('entry_date', bar['date'])
      entry_atr = (position_before or {}).get('atr_entry', float('nan'))
      level = (position_before or {}).get('pyramid_level', 1)

      entry_atr_value: float | None
      if isinstance(entry_atr, float) and math.isnan(entry_atr):
        entry_atr_value = None
      else:
        entry_atr_value = float(entry_atr)

      trades.append({
        'open_dt': entry_date,
        'close_dt': bar['date'],
        'instrument': instrument,
        'side': ct.direction,
        'entry_price': float(ct.entry_price),
        'exit_price': float(ct.exit_price),
        'contracts': int(ct.n_contracts),
        'entry_atr': entry_atr_value,
        'exit_reason': ct.exit_reason,  # verbatim from sizing_engine per planner D-20
        'gross_pnl_aud': float(ct.realised_pnl + cost_open * ct.n_contracts),
        'cost_aud': float(cost_round_trip_aud),  # full round-trip for D-05 display
        'net_pnl_aud': float(ct.realised_pnl),
        'balance_after_aud': float(account),
        'level': int(level),
      })

    position = result.position_after
    old_signal = new_signal
    equity_curve.append(float(account))
    dates.append(bar['date'])

  return SimResult(
    trades=trades,
    equity_curve=equity_curve,
    dates=dates,
    final_account=float(account),
  )
