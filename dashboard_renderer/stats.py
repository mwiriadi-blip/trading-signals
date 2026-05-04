'''Dashboard stats and display math helpers extracted from dashboard.py.'''

import logging
import math
import statistics

from system_params import INITIAL_ACCOUNT, TRAIL_MULT_LONG, TRAIL_MULT_SHORT

logger = logging.getLogger(__name__)


def compute_sharpe(state: dict, em_dash: str = '—') -> str:
  equities = [row['equity'] for row in state.get('equity_history', [])]
  if len(equities) < 30:
    return em_dash
  if any(e <= 0 for e in equities):
    return em_dash
  log_returns = [math.log(equities[i] / equities[i - 1]) for i in range(1, len(equities))]
  if len(log_returns) < 2:
    return em_dash
  mean_r = statistics.mean(log_returns)
  std_r = statistics.stdev(log_returns)
  if std_r == 0:
    return em_dash
  sharpe = (mean_r / std_r) * math.sqrt(252)
  return f'{sharpe:.2f}'


def compute_max_drawdown(state: dict, em_dash: str = '—') -> str:
  equities = [row['equity'] for row in state.get('equity_history', [])]
  if not equities:
    return em_dash
  running_max = equities[0]
  max_dd = 0.0
  for eq in equities:
    running_max = max(running_max, eq)
    if running_max == 0:
      continue
    dd = (eq - running_max) / running_max
    max_dd = min(max_dd, dd)
  return f'{max_dd * 100:.1f}%'


def compute_win_rate(state: dict, em_dash: str = '—') -> str:
  closed = state.get('trade_log', [])
  if not closed:
    return em_dash
  wins = sum(1 for t in closed if t.get('gross_pnl', 0) > 0)
  return f'{wins / len(closed) * 100:.1f}%'


def compute_total_return(state: dict) -> str:
  initial = state.get('initial_account', INITIAL_ACCOUNT)
  eq_hist = state.get('equity_history', [])
  if eq_hist:
    current = eq_hist[-1].get('equity', state.get('account', initial))
  else:
    current = state.get('account', initial)
  total_return = (current - initial) / initial
  return f'{total_return * 100:+.1f}%'


def compute_aggregate_stats(paper_trades=None, signals=None) -> dict:
  if paper_trades is None:
    paper_trades = []
  if signals is None:
    signals = {}
  from pnl_engine import compute_unrealised_pnl
  mult_map = {'SPI200': 5.0, 'AUDUSD': 10000.0}
  realised = 0.0
  unrealised = 0.0
  wins = 0
  losses = 0
  for row in paper_trades:
    status = row.get('status')
    if status == 'closed':
      pnl = row.get('realised_pnl') or 0.0
      realised += pnl
      if pnl > 0:
        wins += 1
      elif pnl < 0:
        losses += 1
    elif status == 'open':
      instrument = row.get('instrument', '')
      sig = signals.get(instrument, {})
      lc = sig.get('last_close')
      if lc is None:
        continue
      try:
        lc_float = float(lc)
      except (TypeError, ValueError):
        continue
      if math.isnan(lc_float):
        continue
      mult = mult_map.get(instrument, 1.0)
      upnl = compute_unrealised_pnl(
        row['side'], row['entry_price'], lc_float,
        row['contracts'], mult, row['entry_cost_aud'],
      )
      unrealised += upnl
  denom = wins + losses
  win_rate = f'{wins * 100 // denom}%' if denom > 0 else '—'
  return {
    'realised': realised,
    'unrealised': unrealised,
    'wins': wins,
    'losses': losses,
    'win_rate': win_rate,
  }


def compute_trail_stop_display(position: dict, settings: dict | None = None) -> float:
  atr_entry = position['atr_entry']
  if not math.isfinite(atr_entry):
    return float('nan')
  manual = position.get('manual_stop')
  if manual is not None:
    return manual
  if position['direction'] == 'LONG':
    peak = position.get('peak_price')
    if peak is None:
      peak = position['entry_price']
    trail_mult = float((settings or {}).get('trail_mult_long', TRAIL_MULT_LONG))
    return peak - trail_mult * atr_entry
  trough = position.get('trough_price')
  if trough is None:
    trough = position['entry_price']
  trail_mult = float((settings or {}).get('trail_mult_short', TRAIL_MULT_SHORT))
  return trough + trail_mult * atr_entry


def compute_unrealised_pnl_display(
  position: dict,
  state_key: str,
  current_close: float | None,
  contract_specs: dict,
  state: dict | None = None,
) -> float | None:
  if current_close is None:
    return None
  resolved = None
  if state is not None:
    resolved = state.get('_resolved_contracts', {}).get(state_key)
  if resolved is not None:
    multiplier = resolved['multiplier']
    cost_aud_round_trip = resolved['cost_aud']
  else:
    logger.debug(
      '[Dashboard] _resolved_contracts missing for %s; falling back to '
      'module-level contract specs default tier', state_key,
    )
    multiplier, cost_aud_round_trip = contract_specs[state_key]
  cost_aud_open = cost_aud_round_trip / 2
  direction_mult = 1.0 if position['direction'] == 'LONG' else -1.0
  price_diff = current_close - position['entry_price']
  gross = direction_mult * price_diff * position['n_contracts'] * multiplier
  open_cost = cost_aud_open * position['n_contracts']
  return gross - open_cost
