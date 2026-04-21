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
'''
import dataclasses
import math  # noqa: F401 — used in implementation plans 02-02..02-05

from signal_engine import FLAT, LONG, SHORT  # noqa: F401 — used in 02-02..02-05
from system_params import (
  ADX_EXIT_GATE,  # noqa: F401 — used in step() 02-05
  MAX_PYRAMID_LEVEL,  # noqa: F401 — used in check_pyramid 02-03
  RISK_PCT_LONG,  # noqa: F401 — used in calc_position_size 02-02
  RISK_PCT_SHORT,  # noqa: F401 — used in calc_position_size 02-02
  TRAIL_MULT_LONG,  # noqa: F401 — used in get_trailing_stop/check_stop_hit 02-03
  TRAIL_MULT_SHORT,  # noqa: F401 — used in get_trailing_stop/check_stop_hit 02-03
  VOL_SCALE_MAX,  # noqa: F401 — used in calc_position_size 02-02
  VOL_SCALE_MIN,  # noqa: F401 — used in calc_position_size 02-02
  VOL_SCALE_TARGET,  # noqa: F401 — used in calc_position_size 02-02
  Position,
)

# =========================================================================
# Return-type dataclasses (D-09)
# =========================================================================


@dataclasses.dataclass(frozen=True, slots=True)
class SizingDecision:
  '''Result of calc_position_size.

  contracts: number of contracts to trade (0 = skip, SIZE-05)
  warning:   human-readable explanation when contracts == 0, else None
  '''
  contracts: int
  warning: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class PyramidDecision:
  '''Result of check_pyramid.

  add_contracts: 0 or 1 (never 2 per D-12 / PYRA-05)
  new_level:     pyramid level after this decision is applied
  '''
  add_contracts: int
  new_level: int


@dataclasses.dataclass(frozen=True, slots=True)
class ClosedTrade:
  '''Realised trade record populated by step() on close/reversal.

  exit_reason: one of 'signal_exit', 'signal_reversal', 'stop_hit', 'adx_exit'
  realised_pnl: gross PnL minus closing-half cost (close-half deducted here;
                open-half was already deducted in compute_unrealised_pnl)
  '''
  direction: str           # 'LONG' or 'SHORT'
  entry_price: float
  exit_price: float
  n_contracts: int
  realised_pnl: float
  exit_reason: str


@dataclasses.dataclass(frozen=True, slots=True)
class StepResult:
  '''Complete result of one step() call.

  position_after:   updated position after all exit/entry/pyramid logic (None = flat)
  closed_trade:     populated if a position was closed in this step (None if no close)
  sizing_decision:  populated when a new entry was sized (None if no new entry)
  pyramid_decision: populated when pyramid was evaluated on an open position (None if flat)
  unrealised_pnl:   mark-to-market PnL on position_after (0.0 if flat)
  warnings:         list of human-readable warnings surfaced during step (e.g. size=0)
  '''
  position_after: Position | None
  closed_trade: ClosedTrade | None
  sizing_decision: SizingDecision | None
  pyramid_decision: PyramidDecision | None
  unrealised_pnl: float
  warnings: list[str]


# =========================================================================
# Public API — stubs (implementations land in Plans 02-02..02-05)
# =========================================================================


def calc_position_size(
  account: float,
  signal: int,
  atr: float,
  rvol: float,
  multiplier: float,
) -> SizingDecision:
  '''SIZE-01..05. ATR-based risk sizing with vol-targeting. No max(1,...) floor.

  risk_pct  = RISK_PCT_LONG (1%) for LONG, RISK_PCT_SHORT (0.5%) for SHORT.
  trail_mult = TRAIL_MULT_LONG (3.0) for LONG, TRAIL_MULT_SHORT (2.0) for SHORT.
  vol_scale  = clip(VOL_SCALE_TARGET / rvol, VOL_SCALE_MIN, VOL_SCALE_MAX).
  stop_dist  = trail_mult * atr * multiplier
  n_raw      = (account * risk_pct / stop_dist) * vol_scale
  contracts  = int(n_raw)  -- no max(1,...) floor (SIZE-05, CLAUDE.md Operator Decisions)

  SIZE-03 NaN guard: if rvol is NaN, inf, or <= 1e-9, vol_scale = VOL_SCALE_MAX (2.0).
  SIZE-05: if contracts == 0, returns SizingDecision(contracts=0, warning='size=0: ...').

  Args:
    account:    current account equity in AUD
    signal:     LONG or SHORT (from signal_engine)
    atr:        ATR at time of entry (today's bar)
    rvol:       20-day realised volatility (annualised)
    multiplier: instrument point value (e.g. SPI_MULT=5.0, AUDUSD_NOTIONAL=10000.0)

  Returns:
    SizingDecision with contracts >= 0 and optional warning string.
  '''
  raise NotImplementedError('calc_position_size: implement in Plan 02-02')


def get_trailing_stop(
  position: Position,
  current_price: float,
  atr: float,
) -> float:
  '''EXIT-06/07. Current trailing stop price from position peak/trough.

  LONG: stop = peak_price - TRAIL_MULT_LONG * position['atr_entry']
  SHORT: stop = trough_price + TRAIL_MULT_SHORT * position['atr_entry']

  D-15: stop distance is anchored to position['atr_entry'] (NOT the `atr` argument).
  The `atr` parameter is retained in the signature for API stability but is unused.
  D-16: peak_price / trough_price must already be updated by the caller (typically
  step()) before this is called.

  NaN guard (D-03): if peak_price/trough_price is None, falls back to entry_price.
  Returns float('nan') if position data is invalid.

  Args:
    position:      open position TypedDict (D-08)
    current_price: current bar close (used only as None-guard fallback)
    atr:           today's ATR (unused per D-15; retained for API stability)

  Returns:
    Stop price as float.
  '''
  raise NotImplementedError('get_trailing_stop: implement in Plan 02-03')


def check_stop_hit(
  position: Position,
  high: float,
  low: float,
  atr: float,
) -> bool:
  '''EXIT-08/09. Returns True if today's intraday bar hits the trailing stop.

  LONG: hit if today's low <= stop  (stop = peak_price - TRAIL_MULT_LONG * atr_entry)
  SHORT: hit if today's high >= stop (stop = trough_price + TRAIL_MULT_SHORT * atr_entry)

  D-15: uses position['atr_entry'] for stop distance (NOT the `atr` argument).
  D-16: assumes peak/trough already updated by caller (typically step()).
  Uses intraday HIGH/LOW per CLAUDE.md Operator Decisions.

  NaN guard (D-03): returns False if position data is invalid (prevents false exits).

  Args:
    position: open position TypedDict (D-08)
    high:     today's intraday HIGH
    low:      today's intraday LOW
    atr:      today's ATR (unused per D-15; retained for API stability)

  Returns:
    True if stop was hit, False otherwise.
  '''
  raise NotImplementedError('check_stop_hit: implement in Plan 02-03')


def check_pyramid(
  position: Position,
  current_price: float,
  atr_entry: float,
) -> PyramidDecision:
  '''PYRA-01..05. Stateless next-level pyramid trigger check (D-12).

  Reads position['pyramid_level'] and evaluates ONLY the trigger for the next level:
    Level 0: add if unrealised_distance >= 1 * atr_entry -> PyramidDecision(1, 1)
    Level 1: add if unrealised_distance >= 2 * atr_entry -> PyramidDecision(1, 2)
    Level 2: never add (cap) -> PyramidDecision(0, 2)

  PYRA-05: never returns add_contracts=2. Gap days that cross both thresholds still
  return add_contracts=1 because only the current-level trigger is evaluated (D-12).

  Unrealised distance uses CLOSE price (current_price) per D-14 / RESEARCH A1.

  NaN guard (D-03): if current_price or atr_entry is NaN/invalid, returns
  PyramidDecision(0, position['pyramid_level']) (no-op).

  Args:
    position:      open position TypedDict (D-08)
    current_price: today's bar close (mark-to-market)
    atr_entry:     ATR at time of entry (from position['atr_entry'])

  Returns:
    PyramidDecision with add_contracts in {0, 1} and updated new_level.
  '''
  raise NotImplementedError('check_pyramid: implement in Plan 02-03')


def compute_unrealised_pnl(
  position: Position,
  current_price: float,
  multiplier: float,
  cost_aud_open: float,
) -> float:
  '''D-13. Unrealised P&L minus half-cost-on-open.

  Formula: direction_mult * (current_price - entry_price) * n_contracts * multiplier
           - cost_aud_open * n_contracts

  where direction_mult = +1 for LONG, -1 for SHORT.
  cost_aud_open is the per-contract opening cost (half of round-trip):
    SPI: SPI_COST_AUD / 2 = 3.0 AUD per contract
    AUDUSD: AUDUSD_COST_AUD / 2 = 2.5 AUD per contract
  The closing half is deducted by Phase 3 record_trade.

  D-17: signature expanded from D-10 -- cost_aud_open is an explicit parameter
  (not derived from multiplier) to avoid coupling to the constant table (Pitfall 6).

  Args:
    position:      open position TypedDict (D-08)
    current_price: current mark-to-market price
    multiplier:    instrument point value (e.g. SPI_MULT=5.0)
    cost_aud_open: per-contract opening cost in AUD (instrument_cost_aud / 2)

  Returns:
    Unrealised P&L in AUD (can be negative).
  '''
  raise NotImplementedError('compute_unrealised_pnl: implement in Plan 02-02')


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
  raise NotImplementedError('step: implement in Plan 02-05')
