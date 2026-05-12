'''Sizing Engine — pure-math position sizing, trailing stops, and pyramid state machine.

Phase 2 pure-math hex (D-07). Analogous to signal_engine.py (Phase 1). Implements:
  - calc_position_size: ATR-based risk sizing with vol-targeting (SIZE-01..05)
  - get_trailing_stop:  current stop price from peak/trough (EXIT-06/07, D-15)
  - check_stop_hit:     intraday H/L stop detection (EXIT-08/09, D-15)
  - check_pyramid:      stateless next-level trigger check (PYRA-01..05, D-12)
  - compute_unrealised_pnl: gross mark-to-market minus half open cost (D-13, D-17)
  - step:               thin orchestrator that chains exit-then-entry per EXIT-03/04
                        (D-10, D-16, D-17, D-18, D-19)

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY. Imports system_params
(constants + Position TypedDict) and signal constants (LONG/SHORT/FLAT) from
signal_engine. Must NOT import state_manager, notifier, dashboard, main, requests,
datetime, os, or any I/O/network/clock module.

Phase 31-02: converted from flat sizing_engine.py (820 LOC) to package with six
focused daughter files. Public API and all caller import paths are unchanged.
'''
import math

from signal_engine import FLAT, LONG, SHORT  # noqa: F401 — used in 02-02..02-05
from system_params import (
  ADX_EXIT_GATE,  # noqa: F401 — used in step() 02-05
  DEFAULT_STRATEGY_SETTINGS,  # noqa: F401
  MAX_PYRAMID_LEVEL,  # noqa: F401 — used in check_pyramid 02-03
  RISK_PCT_LONG,  # noqa: F401
  RISK_PCT_SHORT,  # noqa: F401
  TRAIL_MULT_LONG,  # noqa: F401 — used in get_trailing_stop/check_stop_hit 02-03
  TRAIL_MULT_SHORT,  # noqa: F401 — used in get_trailing_stop/check_stop_hit 02-03
  VOL_SCALE_MAX,  # noqa: F401
  VOL_SCALE_MIN,  # noqa: F401
  VOL_SCALE_TARGET,  # noqa: F401
  Position,
)
from sizing_engine._models import (
  ClosedTrade,
  DriftEvent,
  PyramidDecision,
  SizingDecision,
  StepResult,
)
from sizing_engine.close import _close_position
from sizing_engine.pyramid import check_pyramid, detect_drift
from sizing_engine.sizing import (
  _vol_scale,  # noqa: F401
  calc_position_size,
  compute_unrealised_pnl,
)
from sizing_engine.stops import check_stop_hit, get_trailing_stop

__all__ = [
  'step',
  'calc_position_size',
  'get_trailing_stop',
  'check_stop_hit',
  'check_pyramid',
  'detect_drift',
  'compute_unrealised_pnl',
  'ClosedTrade',
  'SizingDecision',
  'PyramidDecision',
  'StepResult',
  'DriftEvent',
]


def step(
  position: Position | None,
  bar: dict,
  indicators: dict,
  old_signal: int,
  new_signal: int,
  account: float,
  multiplier: float,
  cost_aud_open: float,
) -> StepResult:
  '''D-10/D-17. Thin orchestrator: chains exit-then-entry per EXIT-03/04.

  Evaluation order (verified from SPEC.md §7 + RESEARCH Pattern 4):
    1. Peak/trough update: update position copy with today's HIGH (LONG) / LOW (SHORT)
       BEFORE any exit logic (D-16 ownership).
    2. EXIT-05: if ADX < ADX_EXIT_GATE(20) -> close position regardless of signals.
    3. Stop hit: check_stop_hit(bar.high, bar.low) -> close position if hit.
    4. Signal transition: apply 9-cell truth table if not already closed by 2/3.
       LONG->SHORT / SHORT->LONG: exit-then-entry (EXIT-03/04, two-phase eval).
    5. Pyramid: check_pyramid on surviving open position (no pyramid after stop/adx exit).
    6. Apply pyramid decision to position_after (D-18).
    7. Unrealised PnL: compute_unrealised_pnl on final position state.

  Reversal sizing uses INPUT account (D-19); account mutation is Phase 3's
  responsibility (record_trade in state_manager.py).

  D-17: signature expanded from D-10. account/multiplier/cost_aud_open cannot be
  defaulted -- Phase 4 orchestrator must supply them explicitly.

  NaN guard: if indicators dict contains NaN values, ADX exit uses math.isnan check;
  NaN ATR falls through to individual function NaN guards.

  Data quality contract: step() does NOT guard against NaN bar['high'] or bar['low'].
  If bar['high'] is NaN, max(prev_peak, NaN) returns NaN and peak_price is persisted as
  NaN in the output position (same for bar['low'] / trough_price on SHORT). This is a
  known gap — Phase 3's record_trade / data-fetch layer is responsible for ensuring
  clean finite OHLC data before calling step().

  Args:
    position:      current open position or None (flat)
    bar:           today's OHLC dict: {'open': f, 'high': f, 'low': f, 'close': f}
    indicators:    dict from get_latest_indicators: {atr, adx, pdi, ndi, ...}
    old_signal:    yesterday's signal (LONG/SHORT/FLAT)
    new_signal:    today's signal (LONG/SHORT/FLAT)
    account:       current account equity in AUD (used for new entry sizing, D-19)
    multiplier:    instrument point value
    cost_aud_open: per-contract opening cost in AUD (instrument_cost_aud / 2)

  Returns:
    StepResult capturing position_after, closed_trade, sizing_decision,
    pyramid_decision, unrealised_pnl, and warnings list.
  '''
  warnings: list[str] = []
  closed_trade: ClosedTrade | None = None
  sizing_decision: SizingDecision | None = None
  pyramid_decision: PyramidDecision | None = None
  forced_exit = False
  settings = indicators.get('_settings') if isinstance(indicators.get('_settings'), dict) else None

  # -----------------------------------------------------------------------
  # Phase 0 (D-16): peak/trough update — shallow copy, update BEFORE exits.
  # step() owns peak/trough updates; individual callables assume it's done.
  # -----------------------------------------------------------------------
  current_position: Position | None = None
  if position is not None:
    current_position = dict(position)  # type: ignore[assignment]
    # D-16: peak/trough updated by step() before stop logic
    if current_position['direction'] == 'LONG':
      prev_peak = current_position['peak_price']
      if prev_peak is None:
        prev_peak = current_position['entry_price']
      current_position['peak_price'] = max(prev_peak, bar['high'])
    else:
      prev_trough = current_position['trough_price']
      if prev_trough is None:
        prev_trough = current_position['entry_price']
      current_position['trough_price'] = min(prev_trough, bar['low'])

  # -----------------------------------------------------------------------
  # Phase 1: exits on existing position.
  # -----------------------------------------------------------------------
  if current_position is not None:
    adx = indicators.get('adx', float('nan'))
    # EXIT-05 (A4): check today's ADX against ADX_EXIT_GATE.
    if math.isfinite(adx) and adx < ADX_EXIT_GATE:
      # ADX exit: close at bar close, no new entry (A2).
      closed_trade = _close_position(
        current_position, bar, multiplier, cost_aud_open, 'adx_exit',
      )
      current_position = None
      forced_exit = True
    elif check_stop_hit(
      current_position, bar['high'], bar['low'], indicators.get('atr', float('nan')),
      settings=settings,
    ):
      # EXIT-08/09 stop hit: close at computed stop level (B-5).
      stop_level = get_trailing_stop(
        current_position, bar['close'], indicators.get('atr', float('nan')),
        settings=settings,
      )
      # B-5: if stop_level is NaN (should not happen if atr_entry is finite),
      # fall back to bar['close'] to avoid producing a NaN exit price.
      exit_price = stop_level if math.isfinite(stop_level) else bar['close']
      closed_trade = _close_position(
        current_position, bar, multiplier, cost_aud_open, 'stop_hit',
        exit_price=exit_price,  # B-5 stop-level fill
      )
      current_position = None
      forced_exit = True
    elif new_signal == FLAT:
      # EXIT-01/02: FLAT signal closes the open position.
      closed_trade = _close_position(
        current_position, bar, multiplier, cost_aud_open, 'flat_signal',
      )
      current_position = None
      # forced_exit stays False: FLAT is voluntary; doesn't suppress next-bar entry.
    elif (
      (current_position['direction'] == 'LONG' and new_signal == SHORT)
      or (current_position['direction'] == 'SHORT' and new_signal == LONG)
    ):
      # EXIT-03/04: signal reversal — close existing, then open new (Phase 2).
      closed_trade = _close_position(
        current_position, bar, multiplier, cost_aud_open, 'signal_reversal',
      )
      current_position = None
      # forced_exit stays False: reversal explicitly opens new position below.

  # -----------------------------------------------------------------------
  # Phase 2: entry sizing. D-19: reversal uses INPUT account (no mutation).
  # A2: no new entry on forced-exit (ADX-exit or stop-hit) day.
  # -----------------------------------------------------------------------
  position_after: Position | None = current_position  # may already be updated
  if not forced_exit:
    # New entry conditions:
    # (a) reversal: closed_trade exists AND position_after is None AND new_signal not FLAT
    # (b) fresh entry: position was None (no existing position) AND new_signal not FLAT
    is_reversal = closed_trade is not None and position_after is None
    is_fresh_entry = position is None and new_signal != FLAT
    if is_reversal or is_fresh_entry:
      if new_signal != FLAT:
        # D-19: D-17 signature: account is INPUT account passed by caller.
        sizing_decision = calc_position_size(
          account=account,
          signal=new_signal,
          atr=indicators.get('atr', float('nan')),
          rvol=indicators.get('rvol', float('nan')),
          multiplier=multiplier,
          settings=settings,
        )
        if sizing_decision.contracts > 0:
          # Build new position dict (fresh; not a copy of old).
          direction_str = 'LONG' if new_signal == LONG else 'SHORT'
          position_after = {
            'direction': direction_str,
            'entry_price': bar['close'],
            'entry_date': bar['date'],
            'n_contracts': sizing_decision.contracts,
            'pyramid_level': 0,
            'peak_price': bar['close'] if direction_str == 'LONG' else None,
            'trough_price': bar['close'] if direction_str == 'SHORT' else None,
            'atr_entry': indicators.get('atr', float('nan')),
            # REVIEW HR-03 / Phase 14 D-09: v3 schema requires manual_stop on every
            # Position dict. Daily-loop opens always start with no operator override.
            'manual_stop': None,
          }
        else:
          # SIZE-05: contracts == 0, no new position.
          if sizing_decision.warning:
            warnings.append(sizing_decision.warning)
          position_after = None

  # -----------------------------------------------------------------------
  # Phase 3 + Phase 4 (D-18): pyramid check on surviving open position,
  # then APPLY the add to position_after.
  # Only pyramid if position was ALREADY open before this bar (not a new entry
  # or reversal-open this very bar) AND no forced exit occurred.
  # -----------------------------------------------------------------------
  is_new_entry_this_bar = (
    (closed_trade is not None and position_after is not None)  # reversal
    or (position is None and position_after is not None)  # fresh entry
  )
  if (
    position_after is not None
    and not forced_exit
    and not is_new_entry_this_bar
  ):
    pyramid_decision = check_pyramid(
      position_after,
      current_price=bar['close'],  # A1: CLOSE for pyramid trigger
      atr_entry=position_after['atr_entry'],
    )
    if pyramid_decision.add_contracts > 0:
      # D-18: apply pyramid add to position_after (mutate the working copy).
      # position_after['n_contracts'] and position_after['pyramid_level'] are
      # updated here; check_pyramid itself stays pure (D-12 / D-18).
      position_after = {
        **position_after,
        'n_contracts': position_after['n_contracts'] + pyramid_decision.add_contracts,
        'pyramid_level': pyramid_decision.new_level,  # D-18
      }

  # -----------------------------------------------------------------------
  # Phase 5 (B-6): unrealised PnL on FINAL position state (post-pyramid).
  # -----------------------------------------------------------------------
  if position_after is not None:
    unrealised_pnl = compute_unrealised_pnl(
      position_after, bar['close'], multiplier, cost_aud_open,
    )
  else:
    unrealised_pnl = 0.0

  return StepResult(
    position_after=position_after,  # type: ignore[arg-type]
    closed_trade=closed_trade,
    sizing_decision=sizing_decision,
    pyramid_decision=pyramid_decision,
    unrealised_pnl=unrealised_pnl,
    warnings=warnings,
  )
