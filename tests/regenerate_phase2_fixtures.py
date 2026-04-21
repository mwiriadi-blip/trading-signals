'''Offline scenario-fixture regenerator for Phase 2.

Regenerates the 15 JSON scenario fixtures under tests/fixtures/phase2/ from the
recipes encoded inline below. Mirrors the discipline of tests/regenerate_goldens.py
(Phase 1 D-04): offline-only, never runs in CI. Run manually when scenario recipes
change. Does NOT import from sizing_engine.py -- the recipes ARE the authoritative
spec, computed longhand here, and sizing_engine.py is verified against them at test
time. This separation prevents a sizing_engine bug from silently propagating into
the goldens.

Scenarios (D-14): 9 transition cells (the 9-cell truth table) + 6 edge cases.
  Transition cells:
    transition_long_to_long      -- LONG hold: pyramid 0->1, no stop hit
    transition_long_to_short     -- EXIT-03: close LONG + open SHORT
    transition_long_to_flat      -- EXIT-01: close LONG, go flat
    transition_short_to_long     -- EXIT-04: close SHORT + open LONG
    transition_short_to_short    -- SHORT hold: pyramid 0->1, no stop hit
    transition_short_to_flat     -- EXIT-02: close SHORT, go flat
    transition_none_to_long      -- New LONG entry, sizing applied
    transition_none_to_short     -- New SHORT entry, sizing applied
    transition_none_to_flat      -- No position, FLAT signal: no action
  Edge cases:
    pyramid_gap_crosses_both_levels_caps_at_1  -- PYRA-05/D-12 cap at 1 add
    adx_drop_below_20_while_in_trade           -- EXIT-05 overrides new_signal
    long_trail_stop_hit_intraday_low           -- EXIT-08 intraday LOW boundary
    short_trail_stop_hit_intraday_high         -- EXIT-09 intraday HIGH boundary
    long_gap_through_stop                      -- EXIT-08 + Pitfall 2 detection only
    n_contracts_zero_skip_warning              -- SIZE-05 no-floor + size=0 warning

Usage:
  .venv/bin/python tests/regenerate_phase2_fixtures.py

Output:
  tests/fixtures/phase2/<fixture_name>.json   (15 files)

Determinism contract:
  - sort_keys=True, indent=2 consistent with Phase 1 conventions
  - allow_nan=False (NaN serialized as null per regenerate_goldens.py pattern)
  - Trailing newline after json.dump
  - Running twice produces zero git diff

B-4 dual-maintenance note:
  Inline math helpers (_vol_scale, _n_contracts, _trailing_stop, _stop_hit,
  _pyramid_decision, _close_position) intentionally mirror sizing_engine.py.
  This is the oracle pattern from Phase 1 (D-04): two independent implementations
  so a production bug shows up as a fixture mismatch. When sizing math changes,
  both files must be updated in the same commit.

Log prefix: [regen-p2]
'''
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PHASE2_DIR = str(ROOT / 'tests' / 'fixtures' / 'phase2')
FIXTURES_DIR = Path(os.environ.get('PHASE2_FIXTURES_DIR', _DEFAULT_PHASE2_DIR))


# =========================================================================
# Constants copied from system_params.py (D-11) -- literal for self-containment
# (Do NOT import system_params or sizing_engine -- B-4 oracle independence)
# =========================================================================

RISK_PCT_LONG = 0.01
RISK_PCT_SHORT = 0.005
TRAIL_MULT_LONG = 3.0
TRAIL_MULT_SHORT = 2.0
VOL_SCALE_TARGET = 0.12
VOL_SCALE_MIN = 0.3
VOL_SCALE_MAX = 2.0
SPI_MULT = 5.0
SPI_COST_AUD = 6.0
AUDUSD_NOTIONAL = 10000.0
AUDUSD_COST_AUD = 5.0
MAX_PYRAMID_LEVEL = 2
ADX_EXIT_GATE = 20.0

LONG = 1
SHORT = -1
FLAT = 0


# =========================================================================
# Inline math helpers (B-4: dual-maintenance accepted -- oracle pattern)
# Each helper mirrors the corresponding sizing_engine.py function exactly.
# =========================================================================


def _vol_scale(rvol):
  '''SIZE-03 inline. Mirrors sizing_engine._vol_scale exactly.
  D-03: NaN/zero rvol -> VOL_SCALE_MAX.'''
  if not math.isfinite(rvol) or rvol <= 1e-9:
    return VOL_SCALE_MAX
  return max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, VOL_SCALE_TARGET / rvol))


def _n_contracts(account, signal, atr, rvol, multiplier):
  '''SIZE-04 inline. Returns dict {contracts, warning}.'''
  if signal == LONG:
    risk_pct = RISK_PCT_LONG
    trail_mult = TRAIL_MULT_LONG
  elif signal == SHORT:
    risk_pct = RISK_PCT_SHORT
    trail_mult = TRAIL_MULT_SHORT
  else:
    return {
      'contracts': 0,
      'warning': f'size=0: signal={signal} is not LONG or SHORT',
    }
  vs = _vol_scale(rvol)
  stop_dist = trail_mult * atr * multiplier
  if not math.isfinite(stop_dist) or stop_dist <= 0.0:
    return {'contracts': 0, 'warning': f'size=0: stop_dist={stop_dist}'}
  n_raw = (account * risk_pct / stop_dist) * vs
  n = int(n_raw)
  warn = None
  if n == 0:
    warn = (
      f'size=0: account={account:.2f}, atr={atr:.4f}, rvol={rvol:.4f}, '
      f'vol_scale={vs:.4f}, stop_dist={stop_dist:.4f}, n_raw={n_raw:.6f}'
    )
  return {'contracts': n, 'warning': warn}


def _trailing_stop(direction, peak_or_trough, entry_price, atr_entry):
  '''EXIT-06/07 inline. peak_or_trough may be None (fallback to entry_price).
  D-15: stop distance anchored to atr_entry (entry-time ATR), NOT today's ATR.
  Callers pass prev_position["atr_entry"] explicitly to enforce D-15.
  B-1: NaN atr_entry -> float("nan").'''
  if not math.isfinite(atr_entry):
    return float('nan')  # B-1
  if direction == 'LONG':
    p = peak_or_trough if peak_or_trough is not None else entry_price
    return p - TRAIL_MULT_LONG * atr_entry
  t = peak_or_trough if peak_or_trough is not None else entry_price
  return t + TRAIL_MULT_SHORT * atr_entry


def _stop_hit(direction, peak_or_trough, entry_price, atr_entry, high, low):
  '''EXIT-08/09 inline. D-15: anchored to atr_entry (not today's ATR).
  B-1: NaN HIGH or LOW -> False (cannot detect hit on missing data).'''
  if not math.isfinite(high) or not math.isfinite(low):
    return False  # B-1
  stop = _trailing_stop(direction, peak_or_trough, entry_price, atr_entry)
  if not math.isfinite(stop):
    return False  # B-1: NaN stop from NaN atr_entry -> no hit
  if direction == 'LONG':
    return low <= stop
  return high >= stop


def _pyramid_decision(direction, entry_price, current_price, atr_entry, level):
  '''PYRA-01..05 / D-12 inline. Returns dict {add_contracts, new_level}.
  Stateless single-step: evaluates ONLY the next-level threshold.
  D-18: this inline mirror is pure (no position mutation).
  B-1: NaN current_price OR NaN atr_entry -> {add_contracts:0, new_level:level}.'''
  if not math.isfinite(current_price) or not math.isfinite(atr_entry):
    return {'add_contracts': 0, 'new_level': level}  # B-1
  if level >= MAX_PYRAMID_LEVEL:
    return {'add_contracts': 0, 'new_level': level}
  if direction == 'LONG':
    distance = current_price - entry_price
  else:
    distance = entry_price - current_price
  threshold = (level + 1) * atr_entry
  if distance >= threshold:
    return {'add_contracts': 1, 'new_level': level + 1}
  return {'add_contracts': 0, 'new_level': level}


def _close_position(direction, entry_price, current_price, n_contracts, multiplier,
                    cost_aud_open, exit_price=None):
  '''D-13 inline: realised PnL on close.
  direction_mult = +1 LONG, -1 SHORT. cost_aud_open is half the round-trip cost.
  B-5: exit_price overrides current_price when provided (stop-hit fill at stop level).'''
  eff_price = exit_price if exit_price is not None else current_price
  dm = 1.0 if direction == 'LONG' else -1.0
  gross = dm * (eff_price - entry_price) * n_contracts * multiplier
  return gross - cost_aud_open * n_contracts


def _step(prev_position, bar, indicators, old_signal, new_signal, account,
          multiplier, cost_aud_open):
  '''Inline mirror of sizing_engine.step() (B-4 dual-maintenance accepted).

  Mirrors the production step() phase order exactly:
    Phase 0 (D-16): shallow-copy position, update peak/trough from bar.high/low.
    Phase 1: exits — ADX<20 exit (forced), stop-hit (forced), FLAT signal, reversal.
    Phase 2 (D-19): entry sizing if not forced exit.
    Phase 3+4 (D-18): pyramid check + apply add to position_after.
    Phase 5 (B-6): unrealised PnL on final position state.

  Returns a dict mirroring StepResult fields:
    {position_after, closed_trade_realised_pnl, sizing_decision,
     pyramid_decision, unrealised_pnl, warnings}

  Inline — does NOT import sizing_engine (B-4 oracle independence).
  '''
  warnings_list = []
  closed_trade_pnl = None
  sizing_dec = None
  pyramid_dec = None
  forced_exit = False

  # Phase 0: shallow copy + peak/trough update (D-16).
  cur = None
  if prev_position is not None:
    cur = dict(prev_position)
    if cur['direction'] == 'LONG':
      prev_peak = cur['peak_price']
      if prev_peak is None:
        prev_peak = cur['entry_price']
      cur['peak_price'] = max(prev_peak, bar['high'])
    else:
      prev_trough = cur['trough_price']
      if prev_trough is None:
        prev_trough = cur['entry_price']
      cur['trough_price'] = min(prev_trough, bar['low'])

  # Phase 1: exits.
  if cur is not None:
    adx = indicators.get('adx', float('nan'))
    if math.isfinite(adx) and adx < ADX_EXIT_GATE:
      # EXIT-05: ADX exit — close at bar close, forced, no new entry (A2).
      closed_trade_pnl = _close_position(
        cur['direction'], cur['entry_price'], bar['close'],
        cur['n_contracts'], multiplier, cost_aud_open,
      )
      cur = None
      forced_exit = True
    elif _stop_hit(
      cur['direction'],
      cur.get('peak_price') if cur['direction'] == 'LONG' else cur.get('trough_price'),
      cur['entry_price'], cur['atr_entry'], bar['high'], bar['low'],
    ):
      # EXIT-08/09: stop hit — close at stop level (B-5).
      stop_lvl = _trailing_stop(
        cur['direction'],
        cur.get('peak_price') if cur['direction'] == 'LONG' else cur.get('trough_price'),
        cur['entry_price'], cur['atr_entry'],
      )
      eff_exit = stop_lvl if math.isfinite(stop_lvl) else bar['close']
      closed_trade_pnl = _close_position(
        cur['direction'], cur['entry_price'], bar['close'],
        cur['n_contracts'], multiplier, cost_aud_open,
        exit_price=eff_exit,  # B-5 stop-level fill
      )
      cur = None
      forced_exit = True
    elif new_signal == FLAT:
      # EXIT-01/02: FLAT signal.
      closed_trade_pnl = _close_position(
        cur['direction'], cur['entry_price'], bar['close'],
        cur['n_contracts'], multiplier, cost_aud_open,
      )
      cur = None
    elif (
      (prev_position['direction'] == 'LONG' and new_signal == SHORT)
      or (prev_position['direction'] == 'SHORT' and new_signal == LONG)
    ):
      # EXIT-03/04: reversal — close existing, open new in Phase 2.
      closed_trade_pnl = _close_position(
        cur['direction'], cur['entry_price'], bar['close'],
        cur['n_contracts'], multiplier, cost_aud_open,
      )
      cur = None

  # Phase 2: entry sizing (D-19: uses INPUT account, no mutation; A2: skip if forced).
  pos_after = cur
  if not forced_exit:
    is_reversal = closed_trade_pnl is not None and pos_after is None
    is_fresh = prev_position is None and new_signal != FLAT
    if is_reversal or is_fresh:
      if new_signal != FLAT:
        sizing_dec = _n_contracts(account, new_signal,
                                  indicators.get('atr', float('nan')),
                                  indicators.get('rvol', float('nan')),
                                  multiplier)
        if sizing_dec['contracts'] > 0:
          dir_str = 'LONG' if new_signal == LONG else 'SHORT'
          pos_after = {
            'direction': dir_str,
            'entry_price': bar['close'],
            'entry_date': bar['date'],
            'n_contracts': sizing_dec['contracts'],
            'pyramid_level': 0,
            'peak_price': bar['close'] if dir_str == 'LONG' else None,
            'trough_price': bar['close'] if dir_str == 'SHORT' else None,
            'atr_entry': indicators.get('atr', float('nan')),
          }
        else:
          if sizing_dec['warning']:
            warnings_list.append(sizing_dec['warning'])
          pos_after = None

  # Phase 3+4 (D-18): pyramid check + apply. Only on surviving pre-existing position.
  is_new_entry = (
    (closed_trade_pnl is not None and pos_after is not None)
    or (prev_position is None and pos_after is not None)
  )
  if pos_after is not None and not forced_exit and not is_new_entry:
    pyramid_dec = _pyramid_decision(
      pos_after['direction'], pos_after['entry_price'],
      bar['close'], pos_after['atr_entry'], pos_after['pyramid_level'],
    )
    if pyramid_dec['add_contracts'] > 0:
      pos_after = {
        **pos_after,
        'n_contracts': pos_after['n_contracts'] + pyramid_dec['add_contracts'],
        'pyramid_level': pyramid_dec['new_level'],
      }

  # Phase 5 (B-6): unrealised PnL on final position state.
  if pos_after is not None:
    unreal = _close_position(
      pos_after['direction'], pos_after['entry_price'],
      bar['close'], pos_after['n_contracts'], multiplier, cost_aud_open,
    )
  else:
    unreal = 0.0

  return {
    'position_after': pos_after,
    'closed_trade_realised_pnl': closed_trade_pnl,
    'sizing_decision': sizing_dec,
    'pyramid_decision': pyramid_dec,
    'unrealised_pnl': unreal,
    'warnings': warnings_list,
  }


# =========================================================================
# Shared fixture builder helpers
# =========================================================================


def _spi_indicators(adx=30.0, atr=53.0, rvol=0.15, mom1=0.04, mom3=0.05,
                    mom12=0.06, pdi=35.0, ndi=15.0):
  '''Build an indicators dict with SPI-typical defaults.'''
  return {
    'atr': atr, 'adx': adx, 'pdi': pdi, 'ndi': ndi,
    'mom1': mom1, 'mom3': mom3, 'mom12': mom12, 'rvol': rvol,
  }


def _spi_position(direction='LONG', entry_price=7000.0, n_contracts=2,
                  pyramid_level=0, peak_price=None, trough_price=None,
                  atr_entry=53.0, entry_date='2026-01-02'):
  '''Build a Position TypedDict dict with SPI-typical defaults.'''
  return {
    'direction': direction,
    'entry_price': entry_price,
    'entry_date': entry_date,
    'n_contracts': n_contracts,
    'pyramid_level': pyramid_level,
    'peak_price': peak_price,
    'trough_price': trough_price,
    'atr_entry': atr_entry,
  }


def _bar(o=7060.0, h=7120.0, lo=7045.0, c=7110.0, v=5000.0, date='2026-01-03'):
  '''Build a bar dict with SPI-typical defaults.
  Uses `lo` for low to avoid E741 ambiguous name lint error.'''
  return {'open': o, 'high': h, 'low': lo, 'close': c, 'volume': v, 'date': date}


# =========================================================================
# Recipe builders -- one function per fixture (9 transitions + 6 edge cases)
# Each returns the full fixture dict written to tests/fixtures/phase2/<name>.json.
# =========================================================================


def fixture_transition_long_to_long():
  '''LONG->LONG hold: price rises, pyramid level 0->1 at +1xATR, no stop hit.
  trail_stop = 7050 - 3*53 = 6891.0 (D-15: prev["atr_entry"]=53, not ind["atr"]=55).
  pyramid: close=7110 - entry=7000 = 110 >= 1*53=53 -> add_contracts=1, new_level=1.
  unrealised_pnl: (7110-7000)*2*5 - 3.0*2 = 1100 - 6 = 1094.0.'''
  prev = _spi_position(direction='LONG', entry_price=7000.0, peak_price=7050.0)
  bar = _bar()  # close=7110, high=7120, low=7045
  ind = _spi_indicators(atr=55.0, adx=30.0)
  # D-15: anchor to entry ATR (prev["atr_entry"]=53, not ind["atr"]=55)
  trail = _trailing_stop(
    'LONG', prev['peak_price'], prev['entry_price'], prev['atr_entry'],
  )
  hit = _stop_hit(
    'LONG', prev['peak_price'], prev['entry_price'],
    prev['atr_entry'], bar['high'], bar['low'],  # D-15
  )
  pyr = _pyramid_decision(
    'LONG', prev['entry_price'], bar['close'],
    prev['atr_entry'], prev['pyramid_level'],
  )
  pnl = _close_position(
    'LONG', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': None,
    'trail_stop': trail,
    'stop_hit': hit,
    'pyramid_decision': pyr,
    'unrealised_pnl': pnl,
    'position_after': None,  # populated by 02-05 step() integration
  }
  return {
    'description': (
      'LONG hold (LONG signal continues): price rises, '
      'pyramid level 0->1 at +1xATR, no stop hit'
    ),
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': LONG, 'new_signal': LONG, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_transition_long_to_short():
  '''LONG->SHORT reversal (EXIT-03): close existing LONG then size new SHORT.
  sizing_decision = SHORT entry at ind[atr]=55, rvol=0.15 (RESEARCH §Pattern 1).'''
  prev = _spi_position(direction='LONG', entry_price=7000.0, peak_price=7050.0,
                       n_contracts=2)
  bar = _bar(o=7000.0, h=7020.0, lo=6980.0, c=6990.0)  # mild down day
  ind = _spi_indicators(atr=55.0, adx=30.0, mom1=-0.04, mom3=-0.05, mom12=-0.06)
  # Two-phase: close LONG, then size new SHORT. sizing_decision = new SHORT entry.
  new_sizing = _n_contracts(100000.0, SHORT, ind['atr'], ind['rvol'], SPI_MULT)
  # D-15: anchor to entry ATR
  trail = _trailing_stop(
    'LONG', prev['peak_price'], prev['entry_price'], prev['atr_entry'],
  )
  hit = _stop_hit(
    'LONG', prev['peak_price'], prev['entry_price'],
    prev['atr_entry'], bar['high'], bar['low'],  # D-15
  )
  pnl = _close_position(
    'LONG', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': new_sizing,
    'trail_stop': trail,
    'stop_hit': hit,
    'pyramid_decision': None,  # closed before pyramid eval
    'unrealised_pnl': pnl,
    'position_after': None,
  }
  return {
    'description': (
      'LONG to SHORT reversal (EXIT-03): close existing LONG '
      'then open new SHORT in same step'
    ),
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': LONG, 'new_signal': SHORT, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_transition_long_to_flat():
  '''LONG->FLAT (EXIT-01): signal goes FLAT, close LONG, no new entry.'''
  prev = _spi_position(direction='LONG', entry_price=7000.0, peak_price=7050.0)
  bar = _bar(o=7000.0, h=7020.0, lo=6980.0, c=6990.0)
  ind = _spi_indicators(atr=55.0, adx=24.0, mom1=0.01, mom3=0.0, mom12=-0.01)
  # D-15: anchor to entry ATR
  trail = _trailing_stop(
    'LONG', prev['peak_price'], prev['entry_price'], prev['atr_entry'],
  )
  hit = _stop_hit(
    'LONG', prev['peak_price'], prev['entry_price'],
    prev['atr_entry'], bar['high'], bar['low'],  # D-15
  )
  pnl = _close_position(
    'LONG', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': None,
    'trail_stop': trail,
    'stop_hit': hit,
    'pyramid_decision': None,
    'unrealised_pnl': pnl,
    'position_after': None,
  }
  return {
    'description': 'LONG to FLAT (EXIT-01): signal goes FLAT, close LONG, no new entry',
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': LONG, 'new_signal': FLAT, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_transition_short_to_long():
  '''SHORT->LONG reversal (EXIT-04): close existing SHORT then size new LONG.'''
  prev = _spi_position(direction='SHORT', entry_price=7000.0, peak_price=None,
                       trough_price=6950.0)
  bar = _bar(o=7000.0, h=7050.0, lo=6980.0, c=7040.0)
  ind = _spi_indicators(atr=55.0, adx=30.0, mom1=0.04, mom3=0.05, mom12=0.06)
  new_sizing = _n_contracts(100000.0, LONG, ind['atr'], ind['rvol'], SPI_MULT)
  # D-15: anchor to entry ATR; SHORT uses trough_price
  trail = _trailing_stop(
    'SHORT', prev['trough_price'], prev['entry_price'], prev['atr_entry'],
  )
  hit = _stop_hit(
    'SHORT', prev['trough_price'], prev['entry_price'],
    prev['atr_entry'], bar['high'], bar['low'],  # D-15
  )
  pnl = _close_position(
    'SHORT', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': new_sizing,
    'trail_stop': trail,
    'stop_hit': hit,
    'pyramid_decision': None,
    'unrealised_pnl': pnl,
    'position_after': None,
  }
  return {
    'description': (
      'SHORT to LONG reversal (EXIT-04): close existing SHORT '
      'then open new LONG in same step'
    ),
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': SHORT, 'new_signal': LONG, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_transition_short_to_short():
  '''SHORT->SHORT hold: price falls, pyramid level 0->1 at +1xATR distance.
  trail_stop = 6950 + 2*53 = 7056.0 (D-15: prev["atr_entry"]=53).
  SHORT distance: entry=7000 - close=6900 = 100 >= 1*53=53 -> pyramid adds.'''
  prev = _spi_position(direction='SHORT', entry_price=7000.0, peak_price=None,
                       trough_price=6950.0)
  bar = _bar(o=6950.0, h=6970.0, lo=6890.0, c=6900.0)  # SHORT in profit
  ind = _spi_indicators(atr=55.0, adx=30.0, mom1=-0.04, mom3=-0.05, mom12=-0.06,
                        pdi=15.0, ndi=35.0)
  # D-15: anchor to entry ATR; SHORT uses trough_price
  trail = _trailing_stop(
    'SHORT', prev['trough_price'], prev['entry_price'], prev['atr_entry'],
  )
  hit = _stop_hit(
    'SHORT', prev['trough_price'], prev['entry_price'],
    prev['atr_entry'], bar['high'], bar['low'],  # D-15
  )
  pyr = _pyramid_decision(
    'SHORT', prev['entry_price'], bar['close'],
    prev['atr_entry'], prev['pyramid_level'],
  )
  pnl = _close_position(
    'SHORT', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': None,
    'trail_stop': trail,
    'stop_hit': hit,
    'pyramid_decision': pyr,
    'unrealised_pnl': pnl,
    'position_after': None,
  }
  return {
    'description': (
      'SHORT hold (SHORT signal continues): price falls, '
      'pyramid level 0->1 at +1xATR distance'
    ),
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': SHORT, 'new_signal': SHORT, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_transition_short_to_flat():
  '''SHORT->FLAT (EXIT-02): signal goes FLAT, close SHORT, no new entry.'''
  prev = _spi_position(direction='SHORT', entry_price=7000.0, peak_price=None,
                       trough_price=6950.0)
  bar = _bar(o=6960.0, h=6980.0, lo=6940.0, c=6960.0)
  ind = _spi_indicators(atr=55.0, adx=24.0, mom1=-0.01, mom3=0.0, mom12=0.01)
  # D-15: anchor to entry ATR; SHORT uses trough_price
  trail = _trailing_stop(
    'SHORT', prev['trough_price'], prev['entry_price'], prev['atr_entry'],
  )
  hit = _stop_hit(
    'SHORT', prev['trough_price'], prev['entry_price'],
    prev['atr_entry'], bar['high'], bar['low'],  # D-15
  )
  pnl = _close_position(
    'SHORT', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': None,
    'trail_stop': trail,
    'stop_hit': hit,
    'pyramid_decision': None,
    'unrealised_pnl': pnl,
    'position_after': None,
  }
  return {
    'description': (
      'SHORT to FLAT (EXIT-02): signal goes FLAT, close SHORT, no new entry'
    ),
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': SHORT, 'new_signal': FLAT, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_transition_none_to_long():
  '''No position -> LONG: new LONG entry, sizing applied, position created.
  account=100000, atr=53, rvol=0.15, mult=5 -> contracts=1 (RESEARCH §Pattern 1).'''
  bar = _bar(o=7000.0, h=7050.0, lo=6980.0, c=7040.0)
  ind = _spi_indicators(atr=53.0, adx=30.0)
  sizing = _n_contracts(100000.0, LONG, ind['atr'], ind['rvol'], SPI_MULT)
  exp = {
    'sizing_decision': sizing,
    'trail_stop': None, 'stop_hit': None,
    'pyramid_decision': None, 'unrealised_pnl': None,
    'position_after': None,
  }
  return {
    'description': (
      'No position to LONG: new LONG entry, sizing applied, position created'
    ),
    'prev_position': None, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': FLAT, 'new_signal': LONG, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_transition_none_to_short():
  '''No position -> SHORT: new SHORT entry, sizing applied, position created.'''
  bar = _bar(o=7000.0, h=7020.0, lo=6960.0, c=6970.0)
  ind = _spi_indicators(atr=53.0, adx=30.0, mom1=-0.04, mom3=-0.05, mom12=-0.06,
                        pdi=15.0, ndi=35.0)
  sizing = _n_contracts(100000.0, SHORT, ind['atr'], ind['rvol'], SPI_MULT)
  exp = {
    'sizing_decision': sizing,
    'trail_stop': None, 'stop_hit': None,
    'pyramid_decision': None, 'unrealised_pnl': None,
    'position_after': None,
  }
  return {
    'description': (
      'No position to SHORT: new SHORT entry, sizing applied, position created'
    ),
    'prev_position': None, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': FLAT, 'new_signal': SHORT, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_transition_none_to_flat():
  '''No position -> FLAT: no action, stay flat. Exists for truth-table completeness.'''
  bar = _bar(o=7000.0, h=7010.0, lo=6995.0, c=7005.0)
  ind = _spi_indicators(atr=53.0, adx=22.0, mom1=0.005, mom3=0.0, mom12=-0.005)
  exp = {
    'sizing_decision': None,
    'trail_stop': None, 'stop_hit': None,
    'pyramid_decision': None, 'unrealised_pnl': None,
    'position_after': None,
  }
  return {
    'description': (
      'No position to FLAT: no action, stay flat. '
      'Cell exists for matrix completeness.'
    ),
    'prev_position': None, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': FLAT, 'new_signal': FLAT, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


# =========================================================================
# Edge cases (6 fixtures per D-14)
# =========================================================================


def fixture_pyramid_gap_crosses_both_levels_caps_at_1():
  '''PYRA-05 + D-12: gap day where current price is past BOTH 1*ATR and 2*ATR.
  Expected: add_contracts=1, new_level=1 -- NOT (2, 2).
  close=7150: distance = 7150-7000 = 150 > 1*53=53 AND > 2*53=106.
  D-12 stateless: only evaluates level+1 threshold (level=0 -> threshold=53),
  so returns add_contracts=1 even though price is past both levels.'''
  prev = _spi_position(direction='LONG', entry_price=7000.0, peak_price=7050.0,
                       pyramid_level=0, atr_entry=53.0)
  bar = _bar(o=7100.0, h=7160.0, lo=7095.0, c=7150.0)  # close=7150: past both
  ind = _spi_indicators(atr=55.0, adx=30.0, mom1=0.06, mom3=0.07, mom12=0.08)
  pyramid = _pyramid_decision(
    'LONG', prev['entry_price'], bar['close'],
    prev['atr_entry'], prev['pyramid_level'],
  )
  # Inline assertion-as-comment: pyramid['add_contracts'] must be 1 (not 2) per D-12.
  assert pyramid['add_contracts'] == 1, f'regenerator D-12 violation: {pyramid}'
  trail = _trailing_stop(
    'LONG', prev['peak_price'], prev['entry_price'], prev['atr_entry'],  # D-15
  )
  pnl = _close_position(
    'LONG', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': None,
    'trail_stop': trail,
    'stop_hit': False,
    'pyramid_decision': pyramid,
    'unrealised_pnl': pnl,
    'position_after': None,
  }
  return {
    'description': (
      'PYRA-05 / D-12: gap day past both 1xATR and 2xATR thresholds. '
      'Stateless cap = 1 add only.'
    ),
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': LONG, 'new_signal': LONG, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_adx_drop_below_20_while_in_trade():
  '''EXIT-05: ADX falls to 18 during a LONG. Position closes regardless of new_signal.
  ADX_EXIT_GATE=20; adx=18 < 20 -> EXIT-05 override. stop_hit=False (stop not reached).
  The orchestrator (step() in 02-05) applies EXIT-05; here we assert indicators payload.'''
  prev = _spi_position(direction='LONG', entry_price=7000.0, peak_price=7050.0)
  bar = _bar(o=7050.0, h=7060.0, lo=7040.0, c=7045.0)
  ind = _spi_indicators(atr=55.0, adx=18.0)  # adx=18 < ADX_EXIT_GATE=20
  pnl = _close_position(
    'LONG', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': None,
    'trail_stop': None,  # dominated by adx exit; omitting for clarity
    'stop_hit': False,
    'pyramid_decision': None,
    'unrealised_pnl': pnl,
    'position_after': None,
  }
  return {
    'description': (
      'EXIT-05: ADX=18 < ADX_EXIT_GATE=20 while LONG is open. '
      'Position must close regardless of new_signal.'
    ),
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': LONG, 'new_signal': LONG, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_long_trail_stop_hit_intraday_low():
  '''EXIT-08: LONG trail stop hit when today LOW <= stop.
  peak=7050, atr_entry=53 -> stop = 7050 - 3*53 = 6891.0 (D-15).
  bar low=6890 <= stop=6891 -> stop_hit=True.'''
  prev = _spi_position(direction='LONG', entry_price=7000.0, peak_price=7050.0)
  bar = _bar(o=7000.0, h=7010.0, lo=6890.0, c=6900.0)  # low=6890 <= stop=6891
  ind = _spi_indicators(atr=53.0, adx=30.0)
  # D-15: anchor to entry ATR = 6891.0
  trail = _trailing_stop(
    'LONG', prev['peak_price'], prev['entry_price'], prev['atr_entry'],
  )
  pnl = _close_position(
    'LONG', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': None,
    'trail_stop': trail,
    'stop_hit': True,
    'pyramid_decision': None,
    'unrealised_pnl': pnl,
    'position_after': None,
  }
  return {
    'description': (
      'EXIT-08: LONG trail stop hit by intraday LOW. '
      'peak=7050, atr_entry=53 -> stop=6891; low=6890.'
    ),
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': LONG, 'new_signal': LONG, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_short_trail_stop_hit_intraday_high():
  '''EXIT-09: SHORT trail stop hit when today HIGH >= stop.
  trough=6950, atr_entry=53 -> stop = 6950 + 2*53 = 7056.0 (D-15).
  bar high=7060 >= stop=7056 -> stop_hit=True.'''
  prev = _spi_position(direction='SHORT', entry_price=7000.0, peak_price=None,
                       trough_price=6950.0)
  bar = _bar(o=7000.0, h=7060.0, lo=6990.0, c=7050.0)  # high=7060 >= stop=7056
  ind = _spi_indicators(atr=53.0, adx=30.0)
  # D-15: anchor to entry ATR = 7056.0
  trail = _trailing_stop(
    'SHORT', prev['trough_price'], prev['entry_price'], prev['atr_entry'],
  )
  pnl = _close_position(
    'SHORT', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': None,
    'trail_stop': trail,
    'stop_hit': True,
    'pyramid_decision': None,
    'unrealised_pnl': pnl,
    'position_after': None,
  }
  return {
    'description': (
      'EXIT-09: SHORT trail stop hit by intraday HIGH. '
      'trough=6950, atr_entry=53 -> stop=7056; high=7060.'
    ),
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': SHORT, 'new_signal': SHORT, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_long_gap_through_stop():
  '''EXIT-08 + Pitfall 2: LONG stop hit by gap-down where open gaps BELOW stop.
  peak=7050, atr_entry=53 -> stop=6891.0. open=6800, low=6750: both below stop.
  Pitfall 2: check_stop_hit returns bool only; fill price is Phase 3.'''
  prev = _spi_position(direction='LONG', entry_price=7000.0, peak_price=7050.0)
  bar = _bar(o=6800.0, h=6810.0, lo=6750.0, c=6790.0)  # gap down well below stop
  ind = _spi_indicators(atr=53.0, adx=30.0)
  # D-15: anchor to entry ATR = 6891.0
  trail = _trailing_stop(
    'LONG', prev['peak_price'], prev['entry_price'], prev['atr_entry'],
  )
  pnl = _close_position(
    'LONG', prev['entry_price'], bar['close'],
    prev['n_contracts'], SPI_MULT, SPI_COST_AUD / 2,
  )
  exp = {
    'sizing_decision': None,
    'trail_stop': trail,
    'stop_hit': True,
    'pyramid_decision': None,
    'unrealised_pnl': pnl,
    'position_after': None,
  }
  return {
    'description': (
      'EXIT-08 + Pitfall 2: gap-down through stop. open=6800, low=6750, '
      'stop=6891. Detection only; fill price is Phase 3.'
    ),
    'prev_position': prev, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': LONG, 'new_signal': LONG, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


def fixture_n_contracts_zero_skip_warning():
  '''SIZE-05 + operator no-floor: account+atr combination yields n_raw < 1.
  account=100000, atr=80, rvol=0.15, mult=5 -> stop_dist=80*3*5=1200,
  vol_scale=0.12/0.15=0.8, n_raw=(100000*0.01/1200)*0.8=0.6667 -> contracts=0.
  Expects sizing_decision with contracts=0 and warning starting with "size=0:".'''
  bar = _bar()
  ind = _spi_indicators(atr=80.0, adx=30.0)
  sizing = _n_contracts(100000.0, LONG, ind['atr'], ind['rvol'], SPI_MULT)
  # Sanity: this fixture fails its purpose if sizing['contracts'] != 0.
  assert sizing['contracts'] == 0, f'fixture broken: expected size=0 got {sizing}'
  exp = {
    'sizing_decision': sizing,
    'trail_stop': None, 'stop_hit': None,
    'pyramid_decision': None, 'unrealised_pnl': None,
    'position_after': None,
  }
  return {
    'description': (
      'SIZE-05 + operator no-floor: account=100k, atr=80, rvol=0.15 '
      '-> n_raw=0.667 -> contracts=0 + size=0 warning.'
    ),
    'prev_position': None, 'bar': bar, 'indicators': ind, 'account': 100000.0,
    'old_signal': FLAT, 'new_signal': LONG, 'multiplier': SPI_MULT,
    'instrument_cost_aud': SPI_COST_AUD, 'expected': exp,
  }


# =========================================================================
# Writer + main
# =========================================================================

ALL_FIXTURES = {
  'transition_long_to_long': fixture_transition_long_to_long,
  'transition_long_to_short': fixture_transition_long_to_short,
  'transition_long_to_flat': fixture_transition_long_to_flat,
  'transition_short_to_long': fixture_transition_short_to_long,
  'transition_short_to_short': fixture_transition_short_to_short,
  'transition_short_to_flat': fixture_transition_short_to_flat,
  'transition_none_to_long': fixture_transition_none_to_long,
  'transition_none_to_short': fixture_transition_none_to_short,
  'transition_none_to_flat': fixture_transition_none_to_flat,
  'pyramid_gap_crosses_both_levels_caps_at_1': (
    fixture_pyramid_gap_crosses_both_levels_caps_at_1
  ),
  'adx_drop_below_20_while_in_trade': fixture_adx_drop_below_20_while_in_trade,
  'long_trail_stop_hit_intraday_low': fixture_long_trail_stop_hit_intraday_low,
  'short_trail_stop_hit_intraday_high': fixture_short_trail_stop_hit_intraday_high,
  'long_gap_through_stop': fixture_long_gap_through_stop,
  'n_contracts_zero_skip_warning': fixture_n_contracts_zero_skip_warning,
}


def write_fixture(name, data):
  '''Write one fixture JSON. allow_nan=False, sort_keys=True, trailing newline.'''
  out_path = FIXTURES_DIR / f'{name}.json'
  out_path.parent.mkdir(parents=True, exist_ok=True)
  with out_path.open('w') as fh:
    json.dump(data, fh, indent=2, sort_keys=True, allow_nan=False)
    fh.write('\n')
  print(f'[regen-p2] wrote {name}')


def _enrich_position_after(data):
  '''Call _step() on a fixture dict and populate expected.position_after.

  This is the Task 2 (plan 02-05) extension: run each fixture through the
  inline _step() oracle and store the resulting position_after so TestStep
  can assert step() produces matching output.

  B-4 dual-maintenance: _step() here mirrors sizing_engine.step() exactly;
  if they diverge, TestStep will catch it as a fixture mismatch.
  '''
  step_result = _step(
    prev_position=data['prev_position'],
    bar=data['bar'],
    indicators=data['indicators'],
    old_signal=data['old_signal'],
    new_signal=data['new_signal'],
    account=data['account'],
    multiplier=data['multiplier'],
    cost_aud_open=data['instrument_cost_aud'] / 2.0,
  )
  data['expected']['position_after'] = step_result['position_after']
  return data


def main():
  '''Generate all 15 Phase 2 scenario fixtures.'''
  FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
  for name, builder in ALL_FIXTURES.items():
    data = builder()
    data = _enrich_position_after(data)
    write_fixture(name, data)
  print(f'[regen-p2] wrote {len(ALL_FIXTURES)} fixtures to {FIXTURES_DIR}')


if __name__ == '__main__':
  main()
