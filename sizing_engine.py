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
import math

from signal_engine import FLAT, LONG, SHORT  # noqa: F401 — used in 02-02..02-05
from system_params import (
  ADX_EXIT_GATE,  # noqa: F401 — used in step() 02-05
  MAX_PYRAMID_LEVEL,  # noqa: F401 — used in check_pyramid 02-03
  RISK_PCT_LONG,
  RISK_PCT_SHORT,
  TRAIL_MULT_LONG,  # noqa: F401 — used in get_trailing_stop/check_stop_hit 02-03
  TRAIL_MULT_SHORT,  # noqa: F401 — used in get_trailing_stop/check_stop_hit 02-03
  VOL_SCALE_MAX,
  VOL_SCALE_MIN,
  VOL_SCALE_TARGET,
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
# Public API — stubs (implementations land in Plans 02-02..02-05)
# =========================================================================


def calc_position_size(
  account: float,
  signal: int,
  atr: float,
  rvol: float,
  multiplier: float,
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
  if signal == LONG:
    risk_pct = RISK_PCT_LONG
    trail_mult = TRAIL_MULT_LONG
  elif signal == SHORT:
    risk_pct = RISK_PCT_SHORT
    trail_mult = TRAIL_MULT_SHORT
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
  warning: str | None = None
  if n_contracts == 0:
    warning = (
      f'size=0: account={account:.2f}, atr={atr:.4f}, rvol={rvol:.4f}, '
      f'vol_scale={vol_scale:.4f}, stop_dist={stop_dist:.4f}, n_raw={n_raw:.6f}'
    )
  return SizingDecision(contracts=n_contracts, warning=warning)


def get_trailing_stop(
  position: Position,
  current_price: float,
  atr: float,
) -> float:
  '''EXIT-06/07: compute current trailing stop price. D-15 anchor: stop distance
  uses position['atr_entry'], NOT the `atr` argument.

  LONG:  stop = peak_price  - TRAIL_MULT_LONG  * position['atr_entry']
  SHORT: stop = trough_price + TRAIL_MULT_SHORT * position['atr_entry']

  D-15 rationale: anchoring stop distance to the ATR captured at entry keeps
  the risk consistent with the original sizing decision. Using today's ATR
  would let a vol spike ratchet the stop AWAY from price (LONG stop drifts
  down on a vol spike), which violates the conservative-defaults posture.
  The `atr` parameter stays in the signature for API stability — callers
  (Phase 4 orchestrator) keep passing today's atr without breaking; this
  function ignores it for the trail distance.

  D-16 ownership: this function ASSUMES peak/trough is already updated for
  today's bar (HIGH for LONG, LOW for SHORT). The owner of that update is
  step() (per D-16); individual callers must update peak/trough before
  calling this function.

  Pitfall 3: peak_price (LONG) or trough_price (SHORT) may be None on the
  first bar of a new position before peak/trough has been initialized by
  the orchestrator. Fall back to entry_price — gives a stop equal to
  entry +/- trail_mult*atr_entry (no profit lock yet).

  B-1 NaN policy: if position['atr_entry'] is NaN (broken upstream data),
  return float('nan'). Callers must math.isnan check before using the
  result. This is safer than raising — Phase 2 functions are documented
  as NaN-pass-through (D-03) so the orchestrator can decide how to react
  (e.g. log + skip stop check) rather than crashing the whole step.

  current_price parameter is reserved for future callers; today the function
  only needs peak/trough/entry/atr_entry. Kept in signature for API stability.

  Args:
    position:      open position TypedDict (D-08)
    current_price: reserved; not used in trail-stop math (D-16)
    atr:           today's ATR (unused per D-15; retained for API stability)

  Returns:
    Stop price as float, or float('nan') if atr_entry is NaN (B-1).
  '''
  del current_price  # Reserved; not used in trail-stop math (D-16).
  del atr  # D-15: stop distance uses position['atr_entry'] not this parameter.
  atr_entry = position['atr_entry']
  if not math.isfinite(atr_entry):
    return float('nan')  # B-1: NaN-pass-through
  if position['direction'] == 'LONG':
    peak = position['peak_price']
    if peak is None:
      peak = position['entry_price']
    return peak - TRAIL_MULT_LONG * atr_entry
  # SHORT branch
  trough = position['trough_price']
  if trough is None:
    trough = position['entry_price']
  return trough + TRAIL_MULT_SHORT * atr_entry


def check_stop_hit(
  position: Position,
  high: float,
  low: float,
  atr: float,
) -> bool:
  '''EXIT-08/09: True if today's intraday bar hit the trailing stop.
  D-15 anchor: uses position['atr_entry'], NOT the `atr` argument.

  LONG:  stop = peak_price - TRAIL_MULT_LONG * position['atr_entry']
         hit when today's low is at or below stop (inclusive boundary)
  SHORT: stop = trough_price + TRAIL_MULT_SHORT * position['atr_entry']
         hit when today's high is at or above stop (inclusive boundary)

  Boundary check is inclusive on both sides — a bar touching the stop exactly counts as a hit.

  CLAUDE.md operator decision: intraday HIGH/LOW (NOT close-only). Phase 2
  fixtures must supply both HIGH and LOW; close-only fixtures are
  under-specified for this phase.

  D-16 ownership: assumes peak/trough already updated for today's bar by
  caller (typically step()).

  Pitfall 2: this function returns BOOL ONLY. Fill price logic (stop vs
  gap-open for gap-through-stop case) is Phase 3 record_trade territory.

  Pitfall 3: peak_price/trough_price None safety mirrors get_trailing_stop.

  B-1 NaN policy: if HIGH OR LOW is NaN, return False. We cannot detect a
  hit on missing data and an auto-True would force an unwanted close;
  False defers the decision. If position['atr_entry'] is NaN, also return
  False (a NaN-stop comparison would be False anyway, but we make it
  explicit to short-circuit the math).

  Args:
    position: open position TypedDict (D-08)
    high:     today's intraday HIGH
    low:      today's intraday LOW
    atr:      today's ATR (unused per D-15; retained for API stability)

  Returns:
    True if stop was hit, False otherwise (including NaN inputs, B-1).
  '''
  del atr  # D-15: stop distance uses position['atr_entry'] not this parameter.
  if not math.isfinite(high) or not math.isfinite(low):
    return False  # B-1: NaN-pass-through
  atr_entry = position['atr_entry']
  if not math.isfinite(atr_entry):
    return False  # B-1: NaN-pass-through
  if position['direction'] == 'LONG':
    peak = position['peak_price']
    if peak is None:
      peak = position['entry_price']
    stop = peak - TRAIL_MULT_LONG * atr_entry
    return low <= stop
  # SHORT branch
  trough = position['trough_price']
  if trough is None:
    trough = position['entry_price']
  stop = trough + TRAIL_MULT_SHORT * atr_entry
  return high >= stop


def check_pyramid(
  position: Position,
  current_price: float,
  atr_entry: float,
) -> PyramidDecision:
  '''PYRA-01..05 stateless single-step (D-12). check_pyramid is PURE — it does
  NOT mutate position. Application of the add to position_after['n_contracts']
  and position_after['pyramid_level'] is owned by step() per D-18.

  Reads position.pyramid_level. Evaluates ONLY the trigger for the NEXT level:
    - Level 0: add 1 if unrealised_distance >= 1 * atr_entry -> PyramidDecision(1, 1)
    - Level 1: add 1 if unrealised_distance >= 2 * atr_entry -> PyramidDecision(1, 2)
    - Level 2: never adds; returns PyramidDecision(0, 2)            (PYRA-04 cap)

  Unrealised distance is in PRICE units (not P&L) and uses the position direction:
    LONG:  distance = current_price - entry_price
    SHORT: distance = entry_price - current_price

  D-12 stateless invariant (PYRA-05): add_contracts is always 0 or 1, never
  higher. Gap days past BOTH thresholds still return add_contracts=1 (only
  the current level trigger is evaluated). The next bar sees pyramid_level=1
  and triggers the second add then.

  RESEARCH A1: current_price = today's CLOSE (passed by orchestrator as
  bar['close']). Pitfall 1: atr_entry is from position['atr_entry'] (NOT today's atr).

  B-1 NaN policy: if current_price OR atr_entry is NaN, return
  PyramidDecision(add_contracts=0, new_level=position['pyramid_level']) —
  no add when uncertain. The pyramid_level passes through unchanged so
  subsequent bars (with valid data) can pick up where we left off.

  Args:
    position:      open position TypedDict (D-08)
    current_price: today's bar close (mark-to-market; RESEARCH A1)
    atr_entry:     ATR at time of entry (from position['atr_entry'])

  Returns:
    PyramidDecision with add_contracts in {0, 1} and new_level.
  '''
  level = position['pyramid_level']
  if not math.isfinite(current_price) or not math.isfinite(atr_entry):
    return PyramidDecision(add_contracts=0, new_level=level)  # B-1
  if level >= MAX_PYRAMID_LEVEL:
    return PyramidDecision(add_contracts=0, new_level=level)
  if position['direction'] == 'LONG':
    distance = current_price - position['entry_price']
  else:
    distance = position['entry_price'] - current_price
  threshold = (level + 1) * atr_entry
  if distance >= threshold:
    return PyramidDecision(add_contracts=1, new_level=level + 1)
  return PyramidDecision(add_contracts=0, new_level=level)


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
  direction_mult = 1.0 if position['direction'] == 'LONG' else -1.0
  price_diff = current_price - position['entry_price']
  gross = direction_mult * price_diff * position['n_contracts'] * multiplier
  open_cost = cost_aud_open * position['n_contracts']
  return gross - open_cost


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
