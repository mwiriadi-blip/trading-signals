'''Sizing Engine — trailing stop logic (EXIT-06/07/08/09, D-15).

Functions:
  get_trailing_stop: compute current trailing stop price from peak/trough
  check_stop_hit:    True if today's intraday bar hit the trailing stop

Hex boundary: pure math only. No I/O, no datetime, no state_manager.
'''
import math

from system_params import (
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
)


# =========================================================================
# Public API
# =========================================================================


def get_trailing_stop(
  position: dict,
  current_price: float,
  atr: float,
  settings: dict | None = None,
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

  Phase 14 D-09 manual_stop precedence: when position['manual_stop'] is not
  None (operator override set via POST /trades/modify), the function returns
  that value directly, bypassing the peak/trough computed stop. When None
  (the v1.0 default), falls through to the computed trailing stop. NaN
  guard on atr_entry runs FIRST so NaN passthrough is preserved regardless
  of the override. Defensive position.get('manual_stop') so pre-migration
  state dicts (no key) silently fall through (RESEARCH §Pitfall 5).

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
  # Phase 14 D-09: manual_stop takes precedence over computed trailing stop.
  # When operator has set a stop via /trades/modify, return it directly.
  # When None (default), fall through to v1.0 computed trailing stop.
  # Defensive .get() handles pre-migration position dicts (no key) — RESEARCH Pitfall 5.
  manual = position.get('manual_stop')
  if manual is not None:
    return manual
  if position['direction'] == 'LONG':
    peak = position['peak_price']
    if peak is None:
      peak = position['entry_price']
    trail_mult = float((settings or {}).get('trail_mult_long', TRAIL_MULT_LONG))
    return peak - trail_mult * atr_entry
  # SHORT branch
  trough = position['trough_price']
  if trough is None:
    trough = position['entry_price']
  trail_mult = float((settings or {}).get('trail_mult_short', TRAIL_MULT_SHORT))
  return trough + trail_mult * atr_entry


def check_stop_hit(
  position: dict,
  high: float,
  low: float,
  atr: float,
  settings: dict | None = None,
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

  Phase 14 D-15 (REVIEWS MEDIUM #6) — manual_stop NOT honored here, intentionally:
    get_trailing_stop honors position['manual_stop'] (D-09) for display
    and operator-facing reporting. check_stop_hit is invoked by the daily
    signal loop (main.run_daily_check), which is OUT OF Phase 14 scope —
    the loop continues to use the v1.0 computed stop level for hit
    detection. Phase 15 candidate (deferred): align check_stop_hit with
    manual_stop so dashboard and exit-detection no longer diverge. If a
    future phase wants the daily loop to honor manual_stop, a parallel
    branch must be added here. As of Phase 14, the discrepancy is
    documented and accepted: the operator can override the displayed
    stop without changing the loop's trigger condition.

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
    trail_mult = float((settings or {}).get('trail_mult_long', TRAIL_MULT_LONG))
    stop = peak - trail_mult * atr_entry
    return low <= stop
  # SHORT branch
  trough = position['trough_price']
  if trough is None:
    trough = position['entry_price']
  trail_mult = float((settings or {}).get('trail_mult_short', TRAIL_MULT_SHORT))
  stop = trough + trail_mult * atr_entry
  return high >= stop
