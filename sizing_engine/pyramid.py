'''Sizing Engine — pyramid + drift logic (PYRA-01..05, SENTINEL-01/02, D-01, D-12).

Functions:
  detect_drift:  pure-math drift detector (Phase 15 D-01)
  check_pyramid: stateless single-step pyramid trigger (PYRA-01..05)

Hex boundary: pure math only. No I/O, no datetime, no state_manager.
'''
import math

from signal_engine import FLAT, LONG, SHORT
from system_params import MAX_PYRAMID_LEVEL

from sizing_engine._models import DriftEvent, PyramidDecision


# =========================================================================
# Public API
# =========================================================================


def detect_drift(positions: dict, signals: dict) -> list:
  '''Phase 15 D-01 (SENTINEL-01/02): pure-math drift detector.

  Args:
    positions: state['positions'] — keyed by 'SPI200'/'AUDUSD'; each value
               is a Position TypedDict (or None for no open position).
    signals:   state['signals'] — keyed by 'SPI200'/'AUDUSD'; each value
               is either a dict with key 'signal' (LONG/SHORT/FLAT int)
               OR a bare int (Pitfall 3 backward-compat with reset_state()).

  Returns:
    list[DriftEvent] — one event per drifted instrument; empty list when
    no drift OR when signal data is missing (D-04 conservative skip).

  D-04 conservative-skip cases (return no event for that instrument):
    - positions[instrument] is None (no open position)
    - signals.get(instrument) is None (signal not computed)
    - signals[instrument] is a dict with 'signal' key set to None
    - signals[instrument] is neither int nor dict (defensive — unknown shape)

  D-14 message templates:
    drift:    "You hold {held} {instrument}, today's signal is FLAT — consider closing."
    reversal: "You hold {held} {instrument}, today's signal is {sig_label} —
              reversal recommended (close {held}, open {new_dir})."
  '''
  events: list = []
  for instrument in positions:
    pos = positions.get(instrument)
    if pos is None:
      continue
    sig_entry = signals.get(instrument)
    if sig_entry is None:
      continue
    # D-04 + Pitfall 3: handle both int-shape (reset state) and dict-shape (daily run state)
    if isinstance(sig_entry, int):
      sig_val = sig_entry
    elif isinstance(sig_entry, dict):
      sig_val = sig_entry.get('signal')
    else:
      continue
    if sig_val is None:
      continue
    held = pos.get('direction')
    if held not in ('LONG', 'SHORT'):
      continue
    held_int = LONG if held == 'LONG' else SHORT
    if sig_val == held_int:
      continue  # position matches signal — no drift
    signal_label = {LONG: 'LONG', SHORT: 'SHORT', FLAT: 'FLAT'}.get(sig_val)
    if signal_label is None:
      continue  # unknown int — defensive skip
    if sig_val == FLAT:
      severity = 'drift'
      message = (
        f'You hold {held} {instrument}, today\'s signal is FLAT — consider closing.'
      )
    else:
      severity = 'reversal'
      new_dir = 'SHORT' if held == 'LONG' else 'LONG'
      message = (
        f'You hold {held} {instrument}, today\'s signal is {signal_label} — '
        f'reversal recommended (close {held}, open {new_dir}).'
      )
    events.append(DriftEvent(
      instrument=instrument,
      held_direction=held,
      signal_direction=signal_label,
      severity=severity,
      message=message,
    ))
  return events


def check_pyramid(
  position: dict,
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
