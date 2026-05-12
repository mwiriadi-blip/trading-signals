'''Sizing Engine — position sizing math (SIZE-01..05, D-13, D-17).

Functions:
  _vol_scale:             clip(VOL_SCALE_TARGET / rvol, min, max)
  calc_position_size:     ATR-based risk sizing with vol-targeting
  compute_unrealised_pnl: gross mark-to-market minus half open cost (delegates to pnl_engine)

Hex boundary: pure math only. No I/O, no datetime, no state_manager.
'''
import math

from signal_engine import LONG, SHORT
from system_params import (
  DEFAULT_STRATEGY_SETTINGS,
  RISK_PCT_LONG,
  RISK_PCT_SHORT,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
  VOL_SCALE_MAX,
  VOL_SCALE_MIN,
  VOL_SCALE_TARGET,
)

from sizing_engine._models import SizingDecision


# =========================================================================
# Private helpers
# =========================================================================


def _vol_scale(rvol: float) -> float:
  '''SIZE-03: clip(VOL_SCALE_TARGET / rvol, VOL_SCALE_MIN, VOL_SCALE_MAX).

  D-03: NaN rvol or rvol <= 1e-9 -> VOL_SCALE_MAX (2.0). Returning the ceiling on
  degenerate input is the sizing-friendly choice — undersize is reflected in
  n_contracts==0; oversize from a junk RVol would be more dangerous.
  '''
  if not math.isfinite(rvol) or rvol <= 1e-9:
    return VOL_SCALE_MAX
  return max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, VOL_SCALE_TARGET / rvol))


# =========================================================================
# Public API
# =========================================================================


def calc_position_size(
  account: float,
  signal: int,
  atr: float,
  rvol: float,
  multiplier: float,
  settings: dict | None = None,
) -> SizingDecision:
  '''SIZE-01..05. ATR-based risk sizing with vol-targeting. No floor applied.

  risk_pct  = RISK_PCT_LONG (1%) for LONG, RISK_PCT_SHORT (0.5%) for SHORT.
  trail_mult = TRAIL_MULT_LONG (3.0) for LONG, TRAIL_MULT_SHORT (2.0) for SHORT.
  vol_scale  = clip(VOL_SCALE_TARGET / rvol, VOL_SCALE_MIN, VOL_SCALE_MAX).
  stop_dist  = trail_mult * atr * multiplier
  n_raw      = (account * risk_pct / stop_dist) * vol_scale
  contracts  = int(n_raw)  -- SIZE-05: 0 contracts skips + warns (no floor per operator)

  SIZE-03 NaN guard: if rvol is NaN, inf, or <= 1e-9, vol_scale = VOL_SCALE_MAX (2.0).
  SIZE-05: if contracts == 0, SizingDecision.warning is a 'size=0: ...' diagnostic string.

  Args:
    account:    current account equity in AUD
    signal:     LONG or SHORT (from signal_engine)
    atr:        ATR at time of entry (today's bar)
    rvol:       20-day realised volatility (annualised)
    multiplier: instrument point value (e.g. SPI_MULT=5.0, AUDUSD_NOTIONAL=10000.0)

  Returns:
    SizingDecision with contracts >= 0 and optional warning string.
  '''
  settings = settings or DEFAULT_STRATEGY_SETTINGS
  if signal == LONG:
    risk_pct = float(settings.get('risk_pct_long', RISK_PCT_LONG))
    trail_mult = float(settings.get('trail_mult_long', TRAIL_MULT_LONG))
  elif signal == SHORT:
    risk_pct = float(settings.get('risk_pct_short', RISK_PCT_SHORT))
    trail_mult = float(settings.get('trail_mult_short', TRAIL_MULT_SHORT))
  else:
    # FLAT (0) is a caller error; surface as size=0 with a clear warning.
    return SizingDecision(
      contracts=0,
      warning=f'size=0: signal={signal} is not LONG or SHORT — caller must not size FLAT',
    )
  vol_scale = _vol_scale(rvol)
  stop_dist = trail_mult * atr * multiplier
  if not math.isfinite(stop_dist) or stop_dist <= 0.0:
    return SizingDecision(
      contracts=0,
      warning=(
        f'size=0: stop_dist={stop_dist} is not positive-finite '
        f'(atr={atr}, trail_mult={trail_mult}, multiplier={multiplier})'
      ),
    )
  n_raw = (account * risk_pct / stop_dist) * vol_scale
  n_contracts = int(n_raw)  # truncating int(); SIZE-05 handles contracts==0 (no floor)
  if settings.get('one_contract_floor') and 0.0 < n_raw < 1.0:
    n_contracts = 1
  cap = settings.get('contract_cap')
  if cap is not None:
    n_contracts = min(n_contracts, int(cap))
  warning: str | None = None
  if n_contracts == 0:
    warning = (
      f'size=0: account={account:.2f}, atr={atr:.4f}, rvol={rvol:.4f}, '
      f'vol_scale={vol_scale:.4f}, stop_dist={stop_dist:.4f}, n_raw={n_raw:.6f}'
    )
  return SizingDecision(contracts=n_contracts, warning=warning)


def compute_unrealised_pnl(
  position: dict,
  current_price: float,
  multiplier: float,
  cost_aud_open: float,
) -> float:
  '''D-13. Unrealised P&L minus half-cost-on-open.

  Phase 27 #1 (review-fix agreed-7): delegates to pnl_engine.compute_unrealised_pnl
  to eliminate duplicate money-math logic. pnl_engine returns Decimal AUD-quantized;
  this wrapper coerces to float for downstream callers (state['account'] += pnl,
  equity sums, dashboard formatting) that already expect float arithmetic. The
  Decimal authority lives in pnl_engine; this wrapper is a thin adapter.

  Adapter shape (pnl_engine signature):
    pnl_engine.compute_unrealised_pnl(side, entry_price, last_close,
                                       contracts, multiplier, entry_cost_aud)
  where entry_cost_aud is the TOTAL opening cost (per-contract * n_contracts),
  matching pnl_engine's contract — sizing_engine's cost_aud_open is per-contract,
  so we multiply by n_contracts at the boundary.

  D-13 split-cost contract preserved: caller passes cost_aud_open = round_trip / 2.
  The closing half is deducted by Phase 3 record_trade.

  D-17: signature expanded from D-10 -- cost_aud_open is an explicit parameter
  (not derived from multiplier) to avoid coupling to the constant table (Pitfall 6).

  Args:
    position:      open position TypedDict (D-08)
    current_price: current mark-to-market price
    multiplier:    instrument point value (e.g. SPI_MULT=5.0)
    cost_aud_open: per-contract opening cost in AUD (instrument_cost_aud / 2)

  Returns:
    Unrealised P&L in AUD (can be negative). Float for downstream compatibility;
    underlying authority is Decimal AUD-quantized via pnl_engine.
  '''
  from pnl_engine import compute_unrealised_pnl as _pnl_engine_unrealised
  n = position['n_contracts']
  total_entry_cost_aud = cost_aud_open * n
  result_decimal = _pnl_engine_unrealised(
    position['direction'],
    position['entry_price'],
    current_price,
    n,
    multiplier,
    total_entry_cost_aud,
  )
  # NaN propagation: Decimal('NaN') -> float('nan') is well-defined.
  return float(result_decimal)
