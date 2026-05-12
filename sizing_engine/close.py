'''Sizing Engine — position close logic (D-13, B-5).

Functions:
  _close_position: build a ClosedTrade record for a position being closed

Hex boundary: pure math only. No I/O, no datetime, no state_manager.
'''
from sizing_engine._models import ClosedTrade
from sizing_engine.sizing import compute_unrealised_pnl  # noqa: F401 — available for callers


# =========================================================================
# Private helpers
# =========================================================================


def _close_position(
  position: dict,
  bar: dict,
  multiplier: float,
  cost_aud_open: float,
  exit_reason: str,
  *,
  exit_price: float | None = None,
) -> ClosedTrade:
  '''Build a ClosedTrade record for a position being closed.

  B-5: exit_price kwarg allows stop-hit fills to use the computed stop level
  rather than bar['close']. Default (None) uses bar['close'].

  D-13 (close-half cost): realised_pnl = gross_pnl - close_cost_half.
  The close-half cost equals cost_aud_open (same as the open-half — both
  are half of the round-trip cost). Phase 3 record_trade wires this into
  the trade log; Phase 2 computes it here.

  Args:
    position:      position being closed (D-08 TypedDict)
    bar:           today's OHLC dict with 'close' and 'date' keys
    multiplier:    instrument point value
    cost_aud_open: per-contract opening cost in AUD (= closing cost per D-13)
    exit_reason:   one of 'flat_signal', 'signal_reversal', 'stop_hit', 'adx_exit'
    exit_price:    override exit fill price; defaults to bar['close'] if None (B-5)

  Returns:
    ClosedTrade with realised_pnl reflecting closing-half cost.
  '''
  effective_exit_price = exit_price if exit_price is not None else bar['close']
  direction_mult = 1.0 if position['direction'] == 'LONG' else -1.0
  gross = (
    direction_mult
    * (effective_exit_price - position['entry_price'])
    * position['n_contracts']
    * multiplier
  )
  # D-13: closing half is same per-contract cost as opening half.
  # Phase 27 #1 (truth #3): close_cost arithmetic uses Decimal so AUD-cent
  # precision is preserved; coerce back to float for ClosedTrade.realised_pnl
  # which downstream callers (state_manager.record_trade gross_pnl projection,
  # dashboard formatters) already consume as float. Authority for the cent-
  # boundary lives in this Decimal slice; the float() at return is the boundary.
  from system_params import to_aud
  close_cost_decimal = to_aud(cost_aud_open) * to_aud(position['n_contracts'])
  realised_pnl = gross - float(close_cost_decimal)
  return ClosedTrade(
    direction=position['direction'],
    entry_price=position['entry_price'],
    exit_price=effective_exit_price,
    n_contracts=position['n_contracts'],
    realised_pnl=realised_pnl,
    exit_reason=exit_reason,
  )
