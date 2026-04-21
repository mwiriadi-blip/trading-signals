'''Phase 2 test suite: position sizing, exits, pyramid, transitions, and step().

Organized into classes per D-13 / Phase 2 RESEARCH §Validation Architecture.
Test skeletons created in Plan 02-01 (Wave 0 scaffold); implementations land
in Plans 02-02 (sizing), 02-03 (exits + pyramid), 02-04 (scenario fixtures),
02-05 (step() integration).

Fixture files live at tests/fixtures/phase2/*.json (15 JSON scenario fixtures
per D-14); Phase 2 determinism snapshot at tests/determinism/phase2_snapshot.json.
'''
import math
from pathlib import Path

import pytest

from signal_engine import FLAT, LONG, SHORT
from sizing_engine import (
  PyramidDecision,
  SizingDecision,
  calc_position_size,
  check_pyramid,
  check_stop_hit,
  compute_unrealised_pnl,
  get_trailing_stop,
  step,
)
from system_params import Position

# Module-level path constants (mirrors test_signal_engine.py SIGNAL_ENGINE_PATH pattern)
SIZING_ENGINE_PATH = Path('sizing_engine.py')
SYSTEM_PARAMS_PATH = Path('system_params.py')
PHASE2_FIXTURES_DIR = Path('tests/fixtures/phase2')
PHASE2_SNAPSHOT_PATH = Path('tests/determinism/phase2_snapshot.json')

TRANSITION_FIXTURES = [
  'transition_long_to_long',
  'transition_long_to_short',
  'transition_long_to_flat',
  'transition_short_to_long',
  'transition_short_to_short',
  'transition_short_to_flat',
  'transition_none_to_long',
  'transition_none_to_short',
  'transition_none_to_flat',
]

EDGE_CASE_FIXTURES = [
  'pyramid_gap_crosses_both_levels_caps_at_1',
  'adx_drop_below_20_while_in_trade',
  'long_trail_stop_hit_intraday_low',
  'short_trail_stop_hit_intraday_high',
  'long_gap_through_stop',
  'n_contracts_zero_skip_warning',
]


def _load_phase2_fixture(name: str) -> dict:
  '''Load a Phase 2 JSON scenario fixture.'''
  import json
  path = PHASE2_FIXTURES_DIR / f'{name}.json'
  return json.loads(path.read_text())


def _assert_callable_outputs_match_fixture(fix: dict) -> None:
  '''Shared assertion: walk the `expected` dict; for each non-null field, call the
  matching individual callable with the fixture's inputs and assert equality.

  Skips fields that are null in `expected` (those represent "not evaluated this
  cell" and are not asserted). position_after is always skipped here -- it is
  populated by step() in plan 02-05.
  '''
  prev = fix['prev_position']
  bar = fix['bar']
  ind = fix['indicators']
  account = fix['account']
  multiplier = fix['multiplier']
  cost_aud_open = fix['instrument_cost_aud'] / 2.0  # D-13 split: half on open
  exp = fix['expected']

  # 1. sizing_decision (calc_position_size on the new_signal direction)
  if exp['sizing_decision'] is not None:
    actual = calc_position_size(
      account=account, signal=fix['new_signal'],
      atr=ind['atr'], rvol=ind['rvol'], multiplier=multiplier,
    )
    assert actual.contracts == exp['sizing_decision']['contracts'], (
      f'sizing.contracts mismatch: {actual.contracts} '
      f'vs {exp["sizing_decision"]["contracts"]}'
    )
    assert actual.warning == exp['sizing_decision']['warning'], (
      f'sizing.warning mismatch:\n  actual: {actual.warning!r}\n'
      f'  expected: {exp["sizing_decision"]["warning"]!r}'
    )

  # 2. trail_stop (get_trailing_stop on prev_position)
  if exp['trail_stop'] is not None:
    actual_stop = get_trailing_stop(prev, current_price=bar['close'], atr=ind['atr'])
    assert abs(actual_stop - exp['trail_stop']) < 1e-9, (
      f'trail_stop: {actual_stop} vs {exp["trail_stop"]}'
    )

  # 3. stop_hit
  if exp['stop_hit'] is not None:
    actual_hit = check_stop_hit(prev, high=bar['high'], low=bar['low'], atr=ind['atr'])
    assert actual_hit == exp['stop_hit'], (
      f'stop_hit: {actual_hit} vs {exp["stop_hit"]}'
    )

  # 4. pyramid_decision
  if exp['pyramid_decision'] is not None:
    actual_pyr = check_pyramid(
      prev, current_price=bar['close'], atr_entry=prev['atr_entry'],
    )
    assert actual_pyr == PyramidDecision(**exp['pyramid_decision']), (
      f'pyramid: {actual_pyr} vs {exp["pyramid_decision"]}'
    )

  # 5. unrealised_pnl
  if exp['unrealised_pnl'] is not None:
    actual_pnl = compute_unrealised_pnl(
      prev, current_price=bar['close'], multiplier=multiplier,
      cost_aud_open=cost_aud_open,
    )
    assert abs(actual_pnl - exp['unrealised_pnl']) < 1e-9, (
      f'pnl: {actual_pnl} vs {exp["unrealised_pnl"]}'
    )


def _make_position(
  direction: str = 'LONG',
  entry_price: float = 7000.0,
  n_contracts: int = 2,
  pyramid_level: int = 0,
  peak_price: float | None = None,
  trough_price: float | None = None,
  atr_entry: float = 53.0,
  entry_date: str = '2026-01-02',
) -> Position:
  '''Build a Position TypedDict with sensible defaults for unit tests.

  Defaults to LONG with atr_entry=53 (matches RESEARCH §Pattern 2 reference numbers).
  peak_price/trough_price default to None so tests must override the relevant one
  to test stop-hit math beyond the entry-price fallback.
  '''
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


# =========================================================================
# TestSizing — SIZE-01..06: calc_position_size unit tests
# =========================================================================

class TestSizing:
  '''SIZE-01..06 unit tests for calc_position_size and compute_unrealised_pnl.

  Verified numbers come from RESEARCH.md §Pattern 1 (computed live at research time).
  All assertions are exact (==) — sizing is integer math + simple float multiplication;
  no Wilder smoothing, no rolling windows, no tolerance needed.

  D-17 alignment: compute_unrealised_pnl takes explicit cost_aud_open. One test
  here pins that signature so accidental API regressions are caught at unit-test time.
  '''

  # --- SIZE-01: risk_pct = 1.0% LONG, 0.5% SHORT ---

  def test_risk_pct_long_is_1pct(self) -> None:
    '''SIZE-01 LONG branch: account=100000, atr=53, rvol=0.15, mult=5 -> contracts=1.

    Computed: risk_pct=0.01, trail_mult=3.0, stop_dist=53*3*5=795,
    vol_scale=clip(0.12/0.15,0.3,2.0)=0.8, n_raw=(100000*0.01/795)*0.8=1.00629,
    int(1.00629)=1.
    '''
    decision = calc_position_size(
      account=100000.0, signal=LONG, atr=53.0, rvol=0.15, multiplier=5.0,
    )
    assert decision == SizingDecision(contracts=1, warning=None), decision

  def test_risk_pct_short_is_half_pct(self) -> None:
    '''SIZE-01 SHORT branch: account=100000, atr=53, rvol=0.15, mult=5 -> contracts=0.

    Computed: risk_pct=0.005 (half of LONG), trail_mult=2.0, stop_dist=53*2*5=530,
    vol_scale=0.8, n_raw=(100000*0.005/530)*0.8=0.7547, int=0 -> SIZE-05 warning.
    '''
    decision = calc_position_size(
      account=100000.0, signal=SHORT, atr=53.0, rvol=0.15, multiplier=5.0,
    )
    assert decision.contracts == 0, decision
    assert decision.warning is not None and decision.warning.startswith('size=0:'), decision

  # --- SIZE-02: trail_mult = 3.0 LONG, 2.0 SHORT ---

  def test_trail_mult_by_direction(self) -> None:
    '''SIZE-02: SHORT (trail_mult=2) needs HALF the stop_dist a LONG (trail_mult=3) needs.

    Direct evidence via differential test: same atr/multiplier, only signal changes.
    LONG stop_dist = 53*3*5 = 795; SHORT stop_dist = 53*2*5 = 530; ratio 2/3 = 0.667.
    At atr=20, mult=5: LONG stop_dist=300, n_raw=(100000*0.01/300)*0.8=2.667, int=2.
    SHORT same atr/mult: stop_dist=200, n_raw=(100000*0.005/200)*0.8=2.0, int=2.
    Both produce 2 — the ratio is clean and verifiable.
    '''
    long_d = calc_position_size(100000.0, LONG, 20.0, 0.15, 5.0)
    short_d = calc_position_size(100000.0, SHORT, 20.0, 0.15, 5.0)
    assert long_d.contracts == 2, long_d
    assert short_d.contracts == 2, short_d
    # Differential: LONG at larger atr produces more contracts than SHORT (3.0/2.0 ratio)
    long_smaller = calc_position_size(100000.0, LONG, 53.0, 0.15, 5.0)   # 1
    short_smaller = calc_position_size(100000.0, SHORT, 53.0, 0.15, 5.0)  # 0
    assert long_smaller.contracts > short_smaller.contracts, (long_smaller, short_smaller)

  # --- SIZE-03: vol_scale = clip(0.12 / RVol, 0.3, 2.0); NaN/zero -> 2.0 ---

  def test_vol_scale_clip_ceiling(self) -> None:
    '''SIZE-03 ceiling: rvol=0.05 -> 0.12/0.05=2.4 -> clipped to VOL_SCALE_MAX=2.0.

    Computed: stop_dist=795, n_raw=(100000*0.01/795)*2.0=2.5157, int=2.
    '''
    decision = calc_position_size(100000.0, LONG, 53.0, 0.05, 5.0)
    assert decision.contracts == 2, decision

  def test_vol_scale_clip_floor(self) -> None:
    '''SIZE-03 floor: rvol=0.50 -> 0.12/0.50=0.24 -> clipped to VOL_SCALE_MIN=0.3.

    Computed: stop_dist=795, n_raw=(100000*0.01/795)*0.3=0.3774, int=0 -> warning.
    '''
    decision = calc_position_size(100000.0, LONG, 53.0, 0.50, 5.0)
    assert decision.contracts == 0, decision
    assert decision.warning is not None and decision.warning.startswith('size=0:'), decision

  def test_vol_scale_nan_guard(self) -> None:
    '''SIZE-03 + D-03: NaN rvol -> vol_scale = VOL_SCALE_MAX (2.0). Does NOT crash.

    Computed with vol_scale=2.0: stop_dist=795, n_raw=2.5157, int=2.
    '''
    decision = calc_position_size(100000.0, LONG, 53.0, float('nan'), 5.0)
    assert decision.contracts == 2, decision
    assert decision.warning is None, decision  # Not size=0; the nan was absorbed by the guard

  def test_vol_scale_zero_guard(self) -> None:
    '''SIZE-03 + D-03: rvol <= 1e-9 -> vol_scale = VOL_SCALE_MAX (2.0). No div-by-zero.'''
    decision = calc_position_size(100000.0, LONG, 53.0, 1e-10, 5.0)
    assert decision.contracts == 2, decision
    assert decision.warning is None, decision

  # --- SIZE-04: n_contracts = int(n_raw); no floor (operator-locked) ---

  def test_no_max_one_floor_when_undersized(self) -> None:
    '''SIZE-04 + STATE.md operator decision: n_raw < 1 produces contracts=0, NOT 1.

    atr=80 makes stop_dist big enough that even with vol_scale=0.8 the raw count
    is sub-1: n_raw=(100000*0.01/(80*3*5))*0.8=0.6667, int=0.
    A floor would silently return 1 here and breach the 1% risk budget.
    '''
    decision = calc_position_size(100000.0, LONG, 80.0, 0.15, 5.0)
    assert decision.contracts == 0, decision
    assert decision.warning is not None, decision

  def test_calc_position_size_formula(self) -> None:
    '''SIZE-04: n_contracts = int((account * risk_pct / stop_dist) * vol_scale).

    Verify the atr=20 case: stop_dist=300, n_raw=(100000*0.01/300)*0.8=2.667, int=2.
    '''
    decision = calc_position_size(100000.0, LONG, 20.0, 0.15, 5.0)
    assert decision.contracts == 2, decision
    assert decision.warning is None, decision

  # --- SIZE-05: contracts==0 -> warning with diagnostic substrings ---

  def test_zero_contracts_warning_format(self) -> None:
    '''SIZE-05: warning contains diagnostic substrings for log readability.

    Operator can paste the warning into a debug session and reproduce sizing math
    without re-running the function.
    '''
    decision = calc_position_size(100000.0, LONG, 80.0, 0.15, 5.0)
    assert decision.contracts == 0
    w = decision.warning
    assert w is not None
    for substr in ['size=0:', 'account=', 'atr=', 'rvol=', 'vol_scale=', 'stop_dist=']:
      assert substr in w, f'warning missing {substr!r}: {w!r}'

  # --- SIZE-06: SPI mini multiplier ($5/pt per D-11) and AUDUSD ($10000 notional) ---

  def test_contract_specs_spi_mini(self) -> None:
    '''SIZE-06 + D-11: SPI multiplier is 5.0 (mini), NOT 25 (full ASX 200 SPI).

    Sanity: same account/risk/atr/rvol with mult=5 vs mult=25 produces different
    n_contracts (because stop_dist scales with multiplier).
    '''
    from system_params import SPI_MULT
    assert SPI_MULT == 5.0, f'D-11 violation: SPI_MULT={SPI_MULT}, expected 5.0'
    spi_mini = calc_position_size(100000.0, LONG, 53.0, 0.15, SPI_MULT)
    spi_full_legacy = calc_position_size(100000.0, LONG, 53.0, 0.15, 25.0)
    # mini stop_dist=795, n_raw=1.006, int=1
    # full stop_dist=3975, n_raw=0.201, int=0
    assert spi_mini.contracts == 1, spi_mini
    assert spi_full_legacy.contracts == 0, spi_full_legacy

  def test_contract_specs_audusd(self) -> None:
    '''SIZE-06: AUDUSD multiplier is AUDUSD_NOTIONAL ($10,000 mini-lot). atr is in
    USD-per-AUD price (e.g. 0.005 = 50 pip ATR). Verify the formula doesn't blow up
    with a small atr times a large notional.
    '''
    from system_params import AUDUSD_NOTIONAL
    assert AUDUSD_NOTIONAL == 10000.0
    # stop_dist = 3.0 * 0.005 * 10000 = 150 (AUD); n_raw = (100000*0.01/150)*0.8 = 5.333; int=5
    decision = calc_position_size(100000.0, LONG, 0.005, 0.15, AUDUSD_NOTIONAL)
    assert decision.contracts == 5, decision

  def test_flat_signal_returns_size_zero_with_warning(self) -> None:
    '''SIZE-04 caller-error guard: signal=FLAT (0) is not LONG or SHORT — return
    contracts=0 with a clear warning rather than silently picking LONG defaults.
    '''
    decision = calc_position_size(100000.0, FLAT, 53.0, 0.15, 5.0)
    assert decision.contracts == 0
    assert decision.warning is not None and 'is not LONG or SHORT' in decision.warning, decision

  # --- compute_unrealised_pnl: D-13 split-cost + D-17 explicit cost_aud_open + Pitfall 7 ---

  def test_unrealised_pnl_signature_has_cost_aud_open(self) -> None:
    '''D-17: signature must include cost_aud_open. Pre-emptive guard against
    accidental API regression — the test_sizing_engine_has_core_public_surface
    test in TestDeterminism also pins this; this is the unit-level mirror.'''
    import inspect
    sig = inspect.signature(compute_unrealised_pnl)
    assert 'cost_aud_open' in sig.parameters, (
      f'D-17 violation: compute_unrealised_pnl missing cost_aud_open: {sig}'
    )

  def test_unrealised_pnl_long_profit(self) -> None:
    '''D-13 + D-17: LONG position in profit. gross=(7050-7000)*2*5=500; minus 3.0*2=6 = 494.0.'''
    pos: Position = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-01-02',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 7050.0,
      'trough_price': None, 'atr_entry': 53.0,
    }
    pnl = compute_unrealised_pnl(pos, current_price=7050.0, multiplier=5.0, cost_aud_open=3.0)
    assert pnl == 494.0, pnl

  def test_unrealised_pnl_long_loss(self) -> None:
    '''D-13: LONG position in loss. gross=(6950-7000)*2*5=-500; minus 6 = -506.0.'''
    pos: Position = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-01-02',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 7000.0,
      'trough_price': None, 'atr_entry': 53.0,
    }
    pnl = compute_unrealised_pnl(pos, current_price=6950.0, multiplier=5.0, cost_aud_open=3.0)
    assert pnl == -506.0, pnl

  def test_unrealised_pnl_short_profit_pitfall_7(self) -> None:
    '''Pitfall 7: SHORT direction_mult flips the sign so falling price = positive PnL.

    SHORT entry=7000, current=6950 -> direction_mult=-1, gross=-1*(6950-7000)*2*5=+500;
    minus 6 = +494.0. Without direction_mult this would be -506 (wrong: a winning
    SHORT showing as a loss).
    '''
    pos: Position = {
      'direction': 'SHORT', 'entry_price': 7000.0, 'entry_date': '2026-01-02',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': None,
      'trough_price': 6950.0, 'atr_entry': 53.0,
    }
    pnl = compute_unrealised_pnl(pos, current_price=6950.0, multiplier=5.0, cost_aud_open=3.0)
    assert pnl == 494.0, pnl

  def test_unrealised_pnl_short_loss(self) -> None:
    '''SHORT entry=7000, current=7050 (price went UP -> SHORT loss).
    direction_mult=-1, gross=-1*(7050-7000)*2*5=-500; minus 6 = -506.0.'''
    pos: Position = {
      'direction': 'SHORT', 'entry_price': 7000.0, 'entry_date': '2026-01-02',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': None,
      'trough_price': 7000.0, 'atr_entry': 53.0,
    }
    pnl = compute_unrealised_pnl(pos, current_price=7050.0, multiplier=5.0, cost_aud_open=3.0)
    assert pnl == -506.0, pnl

  def test_unrealised_pnl_audusd_split_cost(self) -> None:
    '''D-13 + AUDUSD: with AUDUSD_NOTIONAL=10000 and cost_aud_open=2.5,
    LONG entry=0.65, current=0.66, n=2 -> gross=0.01*2*10000=200; minus 2.5*2=5 = 195.0.
    '''
    pos: Position = {
      'direction': 'LONG', 'entry_price': 0.65, 'entry_date': '2026-01-02',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 0.66,
      'trough_price': None, 'atr_entry': 0.005,
    }
    pnl = compute_unrealised_pnl(pos, current_price=0.66, multiplier=10000.0, cost_aud_open=2.5)
    assert abs(pnl - 195.0) < 1e-9, pnl  # float multiplication on 0.01 has tiny epsilon


# =========================================================================
# TestExits — EXIT-06..09: get_trailing_stop and check_stop_hit unit tests
# =========================================================================

class TestExits:
  '''EXIT-06..09 unit tests for get_trailing_stop + check_stop_hit.

  D-15 anchor: stop distance uses position['atr_entry'] (NOT the `atr` argument).
  Some tests pass a deliberately-wrong `atr=999.0` to prove the parameter is
  ignored — the result should still be the entry-ATR-anchored value.

  CLAUDE.md operator decision: intraday HIGH/LOW for both peak/trough updates
  AND hit detection. Stop boundaries are INCLUSIVE (low <= stop / high >= stop).

  D-16 ownership: peak/trough is assumed already updated by caller (step()).
  These unit tests build positions with the post-update peak/trough values.

  B-1 NaN policy (per D-03 + reviews-revision pass):
    - get_trailing_stop NaN atr_entry -> float('nan')
    - check_stop_hit NaN high or low -> False
  All numeric expectations from RESEARCH.md §Pattern 2 verified-numbers table.
  '''

  # --- EXIT-06: LONG trailing stop = peak - 3*atr_entry (D-15) ---

  def test_long_trailing_stop_peak_update(self) -> None:
    '''EXIT-06 + D-15: LONG stop = peak_price - TRAIL_MULT_LONG * atr_entry.
    peak=7050, atr_entry=53 -> stop = 7050 - 3*53 = 6891.0.
    Pass atr=999 to prove the argument is ignored (D-15 anchor).'''
    pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=53.0)
    assert get_trailing_stop(pos, current_price=7100.0, atr=999.0) == 6891.0  # D-15

  def test_long_trailing_stop_d15_anchor_explicit(self) -> None:
    '''D-15 explicit anchor proof: same position, two different atr arguments,
    same stop result. If the atr arg leaked into the math, the two calls would
    return different stops.'''
    pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=53.0)
    assert get_trailing_stop(pos, 7100.0, atr=53.0) == get_trailing_stop(pos, 7100.0, atr=200.0)

  def test_long_trailing_stop_peak_none_falls_back_to_entry(self) -> None:
    '''Pitfall 3: peak_price=None -> use entry_price (no TypeError).
    entry=7000, atr_entry=53 -> stop = 7000 - 159 = 6841.0.'''
    pos = _make_position(direction='LONG', peak_price=None, entry_price=7000.0, atr_entry=53.0)
    assert get_trailing_stop(pos, current_price=7100.0, atr=53.0) == 6841.0

  # --- EXIT-07: SHORT trailing stop = trough + 2*atr_entry (D-15) ---

  def test_short_trailing_stop_trough_update(self) -> None:
    '''EXIT-07 + D-15: SHORT stop = trough_price + TRAIL_MULT_SHORT * atr_entry.
    trough=6950, atr_entry=53 -> stop = 6950 + 2*53 = 7056.0.'''
    pos = _make_position(direction='SHORT', trough_price=6950.0, atr_entry=53.0)
    assert get_trailing_stop(pos, current_price=6900.0, atr=999.0) == 7056.0  # D-15

  def test_short_trailing_stop_trough_none_falls_back_to_entry(self) -> None:
    '''Pitfall 3: trough_price=None -> use entry_price.
    entry=7000, atr_entry=53 -> stop = 7000 + 106 = 7106.0.'''
    pos = _make_position(direction='SHORT', trough_price=None, entry_price=7000.0, atr_entry=53.0)
    assert get_trailing_stop(pos, current_price=6900.0, atr=53.0) == 7106.0

  # --- EXIT-08: LONG stop hit if today's LOW <= stop (intraday) ---

  def test_long_stop_hit_intraday_low_at_boundary(self) -> None:
    '''EXIT-08: low EXACTLY at stop is a hit (inclusive boundary).
    peak=7050, atr_entry=53 -> stop=6891. low=6891, high=7100 -> hit.'''
    pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=53.0)
    assert check_stop_hit(pos, high=7100.0, low=6891.0, atr=53.0) is True

  def test_long_stop_hit_intraday_low_below(self) -> None:
    '''EXIT-08: low far below stop -> hit. Models intraday flush.'''
    pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=53.0)
    assert check_stop_hit(pos, high=7100.0, low=6850.0, atr=53.0) is True

  def test_long_no_stop_hit_low_above(self) -> None:
    '''EXIT-08 negative: low above stop -> no hit. peak=7050, stop=6891, low=6900.'''
    pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=53.0)
    assert check_stop_hit(pos, high=7100.0, low=6900.0, atr=53.0) is False

  # --- EXIT-09: SHORT stop hit if today's HIGH >= stop ---

  def test_short_stop_hit_intraday_high_at_boundary(self) -> None:
    '''EXIT-09: high EXACTLY at stop is a hit. trough=6950, atr_entry=53 -> stop=7056.
    high=7056, low=6900 -> hit.'''
    pos = _make_position(direction='SHORT', trough_price=6950.0, atr_entry=53.0)
    assert check_stop_hit(pos, high=7056.0, low=6900.0, atr=53.0) is True

  def test_short_no_stop_hit_high_below(self) -> None:
    '''EXIT-09 negative: high below stop -> no hit. trough=6950, stop=7056, high=7050.'''
    pos = _make_position(direction='SHORT', trough_price=6950.0, atr_entry=53.0)
    assert check_stop_hit(pos, high=7050.0, low=6900.0, atr=53.0) is False

  # --- B-1 NaN policy (per D-03; formalised in reviews-revision pass) ---

  def test_get_trailing_stop_nan_atr_returns_nan(self) -> None:
    '''B-1: NaN position[atr_entry] -> float('nan'). Caller must isnan-check.'''
    pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=float('nan'))
    result = get_trailing_stop(pos, current_price=7100.0, atr=53.0)
    assert math.isnan(result), f'B-1 violation: expected nan, got {result}'

  def test_check_stop_hit_nan_high_returns_false(self) -> None:
    '''B-1: NaN HIGH -> False (cannot detect hit on missing data; defer to next bar).'''
    pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=53.0)
    assert check_stop_hit(pos, high=float('nan'), low=6850.0, atr=53.0) is False

  def test_check_stop_hit_nan_low_returns_false(self) -> None:
    '''B-1: NaN LOW -> False (mirror; LONG check uses low so NaN low must defer).'''
    pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=53.0)
    assert check_stop_hit(pos, high=7100.0, low=float('nan'), atr=53.0) is False

  def test_check_stop_hit_nan_atr_entry_returns_false(self) -> None:
    '''B-1: NaN position[atr_entry] -> False (computed stop would be NaN; comparison
    against any real number returns False; we make this explicit for clarity).'''
    pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=float('nan'))
    assert check_stop_hit(pos, high=7100.0, low=6850.0, atr=53.0) is False


# =========================================================================
# TestPyramid — PYRA-01..05: check_pyramid unit tests
# =========================================================================

class TestPyramid:
  '''PYRA-01..05 unit tests for check_pyramid (D-12 stateless single-step).

  Stateless invariant: function reads position.pyramid_level and evaluates ONLY
  the next-level threshold. add_contracts is always 0 or 1, never higher.
  D-18: check_pyramid does NOT mutate position; step() applies the add.

  B-1 NaN policy (per D-03 + reviews-revision pass): NaN current_price OR NaN
  atr_entry -> PyramidDecision(0, current_level). No add when uncertain.

  All numeric expectations from RESEARCH.md §Pattern 3 verified-numbers table.
  '''

  # --- PYRA-01: pyramid_level persists in Position TypedDict (structural) ---

  def test_position_carries_pyramid_level(self) -> None:
    '''PYRA-01: Position TypedDict has pyramid_level: int field that survives
    a dict round-trip. The field is part of the Wave 0 D-08 schema.'''
    expected_keys = set(Position.__required_keys__) | set(
      getattr(Position, '__optional_keys__', set())
    )
    assert 'pyramid_level' in expected_keys
    pos = _make_position(pyramid_level=1)
    assert pos['pyramid_level'] == 1

  # --- PYRA-02: Level 0 -> 1 at 1*ATR distance ---

  def test_pyramid_level_0_to_1_long(self) -> None:
    '''PYRA-02 LONG: distance = current - entry = 53 = 1*atr_entry -> add 1.'''
    pos = _make_position(direction='LONG', entry_price=7000.0, pyramid_level=0)
    decision = check_pyramid(pos, current_price=7053.0, atr_entry=53.0)
    assert decision == PyramidDecision(add_contracts=1, new_level=1), decision

  def test_pyramid_level_0_to_1_short(self) -> None:
    '''PYRA-02 SHORT mirror: distance = entry - current = 53 -> add 1.'''
    pos = _make_position(direction='SHORT', entry_price=7000.0, pyramid_level=0)
    decision = check_pyramid(pos, current_price=6947.0, atr_entry=53.0)
    assert decision == PyramidDecision(add_contracts=1, new_level=1), decision

  def test_pyramid_level_0_no_add_below_threshold(self) -> None:
    '''PYRA-02 negative: distance=52 < 53 -> no add.'''
    pos = _make_position(direction='LONG', entry_price=7000.0, pyramid_level=0)
    decision = check_pyramid(pos, current_price=7052.0, atr_entry=53.0)
    assert decision == PyramidDecision(add_contracts=0, new_level=0), decision

  # --- PYRA-03: Level 1 -> 2 at 2*ATR distance ---

  def test_pyramid_level_1_to_2_long(self) -> None:
    '''PYRA-03 LONG: distance = 110 >= 2*53=106 -> add 1, advance to level 2.'''
    pos = _make_position(direction='LONG', entry_price=7000.0, pyramid_level=1)
    decision = check_pyramid(pos, current_price=7110.0, atr_entry=53.0)
    assert decision == PyramidDecision(add_contracts=1, new_level=2), decision

  def test_pyramid_level_1_to_2_short(self) -> None:
    '''PYRA-03 SHORT mirror: distance = 110 = 7000-6890 -> add, advance to 2.'''
    pos = _make_position(direction='SHORT', entry_price=7000.0, pyramid_level=1)
    decision = check_pyramid(pos, current_price=6890.0, atr_entry=53.0)
    assert decision == PyramidDecision(add_contracts=1, new_level=2), decision

  def test_pyramid_level_1_no_add_below_threshold(self) -> None:
    '''PYRA-03 negative: distance=105 < 106 -> no add at level 1.'''
    pos = _make_position(direction='LONG', entry_price=7000.0, pyramid_level=1)
    decision = check_pyramid(pos, current_price=7105.0, atr_entry=53.0)
    assert decision == PyramidDecision(add_contracts=0, new_level=1), decision

  # --- PYRA-04: cap at level 2 (3 total contracts) ---

  def test_pyramid_capped_at_level_2(self) -> None:
    '''PYRA-04: at level 2, NEVER advance regardless of distance.
    current=7500, distance=500 (way past everything) -> still add_contracts=0.'''
    pos = _make_position(direction='LONG', entry_price=7000.0, pyramid_level=2)
    decision = check_pyramid(pos, current_price=7500.0, atr_entry=53.0)
    assert decision == PyramidDecision(add_contracts=0, new_level=2), decision

  def test_pyramid_cap_independent_of_max_constant(self) -> None:
    '''PYRA-04 + sanity: MAX_PYRAMID_LEVEL is 2 (3 total contracts: levels 0/1/2).'''
    from system_params import MAX_PYRAMID_LEVEL
    assert MAX_PYRAMID_LEVEL == 2, MAX_PYRAMID_LEVEL

  # --- PYRA-05 (D-12): max 1 step per call — stateless single-level check ---

  def test_pyramid_gap_day_caps_at_one_add_long(self) -> None:
    '''D-12 + PYRA-05: gap day where current is past BOTH 1*atr and 2*atr
    thresholds — function still returns add_contracts=1 because only the CURRENT
    level (0) trigger is evaluated. The next bar will see level=1 and trigger again.

    distance = 7150 - 7000 = 150 (past 1*53=53 AND 2*53=106).
    Expected: PyramidDecision(add_contracts=1, new_level=1), NOT (add_contracts>1).'''
    pos = _make_position(direction='LONG', entry_price=7000.0, pyramid_level=0)
    decision = check_pyramid(pos, current_price=7150.0, atr_entry=53.0)
    assert decision == PyramidDecision(add_contracts=1, new_level=1), (
      f'D-12 violation: gap day past both thresholds returned {decision} '
      f'but PYRA-05 requires single-step (max one add per call).'
    )

  def test_pyramid_gap_day_caps_at_one_add_short(self) -> None:
    '''D-12 SHORT mirror: gap-down day where price is well past both thresholds.
    distance = 7000 - 6800 = 200 (past 1*53 and 2*53). Still adds 1 only.'''
    pos = _make_position(direction='SHORT', entry_price=7000.0, pyramid_level=0)
    decision = check_pyramid(pos, current_price=6800.0, atr_entry=53.0)
    assert decision == PyramidDecision(add_contracts=1, new_level=1), (
      f'D-12 SHORT mirror violation: returned {decision}'
    )

  # --- B-1 NaN policy ---

  def test_check_pyramid_nan_current_price_returns_no_add(self) -> None:
    '''B-1: NaN current_price -> PyramidDecision(0, current_level). pyramid_level
    passes through unchanged so subsequent (valid) bars can pick up state.'''
    pos = _make_position(direction='LONG', entry_price=7000.0, pyramid_level=1)
    decision = check_pyramid(pos, current_price=float('nan'), atr_entry=53.0)
    assert decision == PyramidDecision(add_contracts=0, new_level=1), decision

  def test_check_pyramid_nan_atr_entry_returns_no_add(self) -> None:
    '''B-1: NaN atr_entry -> no add, level held.'''
    pos = _make_position(direction='LONG', entry_price=7000.0, pyramid_level=0)
    decision = check_pyramid(pos, current_price=7150.0, atr_entry=float('nan'))
    assert decision == PyramidDecision(add_contracts=0, new_level=0), decision


# =========================================================================
# TestTransitions — EXIT-01..04: 9-cell signal transition truth table
# =========================================================================

class TestTransitions:
  '''9-cell signal-transition truth table -- one named test per cell.

  Each test loads the matching JSON fixture (D-14 names) and exercises the
  individual callables (calc_position_size, get_trailing_stop, check_stop_hit,
  check_pyramid, compute_unrealised_pnl) per the fixture's `expected` map.
  step() integration tests live in plan 02-05.
  '''

  @pytest.mark.parametrize('fixture_name', TRANSITION_FIXTURES)
  def test_fixture_loads_with_canonical_schema(self, fixture_name: str) -> None:
    '''Schema sanity: every transition fixture has the canonical 9 top-level keys.'''
    fix = _load_phase2_fixture(fixture_name)
    expected_keys = {
      'description', 'prev_position', 'bar', 'indicators', 'account',
      'old_signal', 'new_signal', 'multiplier', 'instrument_cost_aud', 'expected',
    }
    assert expected_keys.issubset(fix.keys()), (
      f'{fixture_name} missing keys: {expected_keys - fix.keys()}'
    )

  @pytest.mark.parametrize('fixture_name', TRANSITION_FIXTURES)
  def test_individual_callables_match_fixture_expected(
    self, fixture_name: str,
  ) -> None:
    '''Truth table: for each fixture, every populated `expected` field must match
    the matching callable's actual output. Null fields are not asserted.'''
    fix = _load_phase2_fixture(fixture_name)
    _assert_callable_outputs_match_fixture(fix)

  # --- Named shortcuts so failures point straight at the broken cell ---

  def test_transition_long_to_long(self) -> None:
    '''LONG hold: pyramid_decision and unrealised_pnl populated; no entry.'''
    _assert_callable_outputs_match_fixture(
      _load_phase2_fixture('transition_long_to_long'),
    )

  def test_transition_long_to_short(self) -> None:
    '''EXIT-03: close LONG, then size new SHORT in same step. sizing_decision populated.'''
    _assert_callable_outputs_match_fixture(
      _load_phase2_fixture('transition_long_to_short'),
    )

  def test_transition_long_to_flat(self) -> None:
    '''EXIT-01: close LONG on FLAT signal; no entry.'''
    _assert_callable_outputs_match_fixture(
      _load_phase2_fixture('transition_long_to_flat'),
    )

  def test_transition_short_to_long(self) -> None:
    '''EXIT-04: close SHORT, then size new LONG in same step.'''
    _assert_callable_outputs_match_fixture(
      _load_phase2_fixture('transition_short_to_long'),
    )

  def test_transition_short_to_short(self) -> None:
    '''SHORT hold: pyramid + unrealised_pnl evaluated.'''
    _assert_callable_outputs_match_fixture(
      _load_phase2_fixture('transition_short_to_short'),
    )

  def test_transition_short_to_flat(self) -> None:
    '''EXIT-02: close SHORT on FLAT signal.'''
    _assert_callable_outputs_match_fixture(
      _load_phase2_fixture('transition_short_to_flat'),
    )

  def test_transition_none_to_long(self) -> None:
    '''New LONG entry: sizing_decision populated; no exit fields.'''
    _assert_callable_outputs_match_fixture(
      _load_phase2_fixture('transition_none_to_long'),
    )

  def test_transition_none_to_short(self) -> None:
    '''New SHORT entry: sizing_decision populated.'''
    _assert_callable_outputs_match_fixture(
      _load_phase2_fixture('transition_none_to_short'),
    )

  def test_transition_none_to_flat(self) -> None:
    '''No-position + FLAT: matrix-completeness cell; nothing evaluated.'''
    _assert_callable_outputs_match_fixture(
      _load_phase2_fixture('transition_none_to_flat'),
    )


# =========================================================================
# TestEdgeCases — 6 edge-case scenario fixtures (D-14)
# =========================================================================

class TestEdgeCases:
  '''6 named edge-case scenario fixtures (D-14). Each test docstring cites the
  invariant or pitfall the fixture exists to prove.
  '''

  @pytest.mark.parametrize('fixture_name', EDGE_CASE_FIXTURES)
  def test_edge_fixture_individual_callables_match_expected(
    self, fixture_name: str,
  ) -> None:
    '''Parametrized version of the per-fixture assertion across all 6 edge cases.'''
    fix = _load_phase2_fixture(fixture_name)
    _assert_callable_outputs_match_fixture(fix)

  def test_pyramid_gap_crosses_both_levels_caps_at_1(self) -> None:
    '''PYRA-05 / D-12 invariant: gap day past 1xATR AND 2xATR thresholds still
    returns add_contracts=1 because check_pyramid is stateless single-step.'''
    fix = _load_phase2_fixture('pyramid_gap_crosses_both_levels_caps_at_1')
    actual = check_pyramid(
      fix['prev_position'],
      current_price=fix['bar']['close'],
      atr_entry=fix['prev_position']['atr_entry'],
    )
    assert actual == PyramidDecision(add_contracts=1, new_level=1), (
      f'D-12 violation: {actual} should be PyramidDecision(1, 1)'
    )

  def test_adx_drop_below_20_while_in_trade(self) -> None:
    '''EXIT-05 detection: when indicators.adx < ADX_EXIT_GATE (20.0), the orchestrator
    must close the position regardless of new_signal. Plan 02-04 exposes this only as
    a fixture comparison -- the orchestrator decision (close-on-adx-exit) is wired in
    plan 02-05 step(). Here we assert the indicator value satisfies the EXIT-05
    precondition and the fixture stop_hit field is False (so the close is ADX-driven).'''
    from system_params import ADX_EXIT_GATE
    fix = _load_phase2_fixture('adx_drop_below_20_while_in_trade')
    assert fix['indicators']['adx'] < ADX_EXIT_GATE, (
      f'fixture broken: adx={fix["indicators"]["adx"]} should be < '
      f'ADX_EXIT_GATE={ADX_EXIT_GATE}'
    )
    assert fix['expected']['stop_hit'] is False, (
      'fixture should isolate ADX-exit (stop_hit must be False to prove ADX dominates)'
    )

  def test_long_trail_stop_hit_intraday_low(self) -> None:
    '''EXIT-08 boundary: peak=7050, atr=53 -> stop=6891. low=6890 (below stop) -> hit.'''
    fix = _load_phase2_fixture('long_trail_stop_hit_intraday_low')
    actual_hit = check_stop_hit(
      fix['prev_position'],
      high=fix['bar']['high'], low=fix['bar']['low'],
      atr=fix['indicators']['atr'],
    )
    actual_stop = get_trailing_stop(
      fix['prev_position'],
      current_price=fix['bar']['close'],
      atr=fix['indicators']['atr'],
    )
    assert actual_hit is True, 'EXIT-08 must fire when low <= stop'
    assert abs(actual_stop - 6891.0) < 1e-9, f'stop {actual_stop} should be 6891.0'

  def test_short_trail_stop_hit_intraday_high(self) -> None:
    '''EXIT-09 boundary: trough=6950, atr=53 -> stop=7056. high=7060 -> hit.'''
    fix = _load_phase2_fixture('short_trail_stop_hit_intraday_high')
    actual_hit = check_stop_hit(
      fix['prev_position'],
      high=fix['bar']['high'], low=fix['bar']['low'],
      atr=fix['indicators']['atr'],
    )
    actual_stop = get_trailing_stop(
      fix['prev_position'],
      current_price=fix['bar']['close'],
      atr=fix['indicators']['atr'],
    )
    assert actual_hit is True, 'EXIT-09 must fire when high >= stop'
    assert abs(actual_stop - 7056.0) < 1e-9, f'stop {actual_stop} should be 7056.0'

  def test_long_gap_through_stop_detection_only(self) -> None:
    '''EXIT-08 + Pitfall 2: gap-down where open=6800 and low=6750, both well below
    stop=6891. check_stop_hit returns True (detection); the question of FILL PRICE
    (stop=6891 vs gap-open=6800) is Phase 3 record_trade territory and NOT exposed
    by check_stop_hit signature.'''
    import inspect
    fix = _load_phase2_fixture('long_gap_through_stop')
    assert check_stop_hit(
      fix['prev_position'],
      high=fix['bar']['high'], low=fix['bar']['low'],
      atr=fix['indicators']['atr'],
    ) is True
    # Pitfall 2 structural enforcement: check_stop_hit returns bool, not (bool, float).
    sig = inspect.signature(check_stop_hit)
    assert sig.return_annotation is bool, (
      f'Pitfall 2 violation: return_annotation={sig.return_annotation}, expected bool'
    )

  def test_n_contracts_zero_skip_warning(self) -> None:
    '''SIZE-05 + operator no-floor: n_raw=0.667 -> contracts=0 + size=0 warning.
    Direct end-to-end via the fixture rather than via the unit test in TestSizing,
    so a regression in the warning string format would surface here too.'''
    fix = _load_phase2_fixture('n_contracts_zero_skip_warning')
    actual = calc_position_size(
      account=fix['account'], signal=fix['new_signal'],
      atr=fix['indicators']['atr'], rvol=fix['indicators']['rvol'],
      multiplier=fix['multiplier'],
    )
    assert actual.contracts == 0
    assert actual.warning is not None and actual.warning.startswith('size=0:'), (
      actual.warning
    )


# =========================================================================
# TestStep — D-10 step() integration: 15 parametrized fixtures + named
#            invariant tests for D-16/D-17/D-18/D-19/B-5/B-6/A2.
# =========================================================================

ALL_PHASE2_FIXTURES = TRANSITION_FIXTURES + EDGE_CASE_FIXTURES


def _call_step(fix: dict):
  '''Call step() with inputs from a fixture dict, return StepResult.'''
  return step(
    position=fix['prev_position'],
    bar=fix['bar'],
    indicators=fix['indicators'],
    old_signal=fix['old_signal'],
    new_signal=fix['new_signal'],
    account=fix['account'],
    multiplier=fix['multiplier'],
    cost_aud_open=fix['instrument_cost_aud'] / 2.0,
  )


class TestStep:
  '''D-10/D-17 step() orchestrator integration tests.

  Parametrized over all 15 Phase 2 fixtures (D-14); each fixture's
  expected.position_after was populated by the inline _step() oracle in
  tests/regenerate_phase2_fixtures.py (plan 02-05 Task 2, B-4 dual-maintenance).

  Named tests assert specific invariants per the reviews-revision decisions:
    D-16: peak/trough update before exit logic; input position NOT mutated
    D-18: pyramid add applied to position_after (n_contracts + pyramid_level updated)
    D-19: reversal sizing uses INPUT account (Phase 2 does not mutate account)
    B-5: stop-hit fixtures fill at stop level, not bar.close
    B-6: unrealised_pnl computed AFTER pyramid add (post-mutation state)
    A2:  no new entry on forced-exit day (ADX exit or stop hit)
  '''

  @pytest.mark.parametrize('fixture_name', ALL_PHASE2_FIXTURES)
  def test_step_position_after_matches_fixture(self, fixture_name: str) -> None:
    '''Integration: step() position_after must match expected.position_after for all 15 fixtures.

    This is the primary TestStep gate: if step() misimplements any phase
    (D-16/D-18/D-19/B-5/A2), the position_after mismatch will surface here.
    '''
    fix = _load_phase2_fixture(fixture_name)
    result = _call_step(fix)
    exp_pos = fix['expected']['position_after']
    if exp_pos is None:
      assert result.position_after is None, (
        f'{fixture_name}: expected position_after=None, got {result.position_after}'
      )
    else:
      assert result.position_after is not None, (
        f'{fixture_name}: expected non-null position_after but got None'
      )
      for field, expected_val in exp_pos.items():
        actual_val = result.position_after[field]
        if isinstance(expected_val, float):
          assert abs(actual_val - expected_val) < 1e-9, (
            f'{fixture_name} position_after.{field}: {actual_val} != {expected_val}'
          )
        else:
          assert actual_val == expected_val, (
            f'{fixture_name} position_after.{field}: {actual_val!r} != {expected_val!r}'
          )

  @pytest.mark.parametrize('fixture_name', ALL_PHASE2_FIXTURES)
  def test_step_no_notimplementederror(self, fixture_name: str) -> None:
    '''step() must not raise NotImplementedError on any of the 15 fixtures.
    Catches the stub-not-removed regression.'''
    fix = _load_phase2_fixture(fixture_name)
    _call_step(fix)  # must not raise

  # --- D-16: input position not mutated; peak_price updated on copy ---

  def test_step_d16_updates_peak_on_copy_not_input(self) -> None:
    '''D-16: step() updates peak_price on a shallow copy, NOT on the input dict.

    The input position must be unchanged after step() returns. The output
    position_after reflects the updated peak (bar.high > prev peak).
    '''
    fix = _load_phase2_fixture('transition_long_to_long')
    prev = fix['prev_position']
    original_peak = prev['peak_price']  # 7050.0
    result = _call_step(fix)
    # Input not mutated.
    assert prev['peak_price'] == original_peak, (
      f'D-16 violation: input peak_price mutated from {original_peak} '
      f'to {prev["peak_price"]}'
    )
    # Output peak reflects bar.high = 7120.
    assert result.position_after is not None, 'position_after must be non-null (LONG hold)'
    assert result.position_after['peak_price'] == fix['bar']['high'], (
      f'D-16: position_after.peak_price {result.position_after["peak_price"]} '
      f'should be bar.high {fix["bar"]["high"]}'
    )

  # --- D-18: pyramid add applied to position_after ---

  def test_step_d18_pyramid_add_applied_to_position_after(self) -> None:
    '''D-18: after pyramid_decision.add_contracts=1, position_after.n_contracts
    must equal prev.n_contracts + 1 and position_after.pyramid_level must equal
    pyramid_decision.new_level.

    Gap fixture: prev.n_contracts=2, pyramid fires -> position_after.n_contracts=3,
    pyramid_level=1.
    '''
    fix = _load_phase2_fixture('pyramid_gap_crosses_both_levels_caps_at_1')
    prev_n = fix['prev_position']['n_contracts']  # 2
    result = _call_step(fix)
    assert result.pyramid_decision is not None, (
      'D-18: pyramid_decision must be populated for this fixture'
    )
    assert result.pyramid_decision.add_contracts == 1, (
      f'D-12 violation: expected add_contracts=1, got {result.pyramid_decision.add_contracts}'
    )
    assert result.position_after is not None, (
      'D-18: position_after must be non-null when pyramid fires on a held position'
    )
    assert result.position_after['n_contracts'] == prev_n + 1, (
      f'D-18: n_contracts should be {prev_n + 1}, '
      f'got {result.position_after["n_contracts"]}'
    )
    assert result.position_after['pyramid_level'] == result.pyramid_decision.new_level, (
      f'D-18: pyramid_level {result.position_after["pyramid_level"]} '
      f'!= pyramid_decision.new_level {result.pyramid_decision.new_level}'
    )

  # --- D-19: reversal uses INPUT account ---

  def test_step_d19_reversal_uses_input_account(self) -> None:
    '''D-19: step() sizes the new entry leg with the INPUT account — no mutation.

    The StepResult does not carry an account_after field; Phase 3 owns account
    state. Using the LONG->SHORT fixture: sizing uses account=100000 (input).
    The sizing_decision.contracts==0 because the SHORT at atr=55 undersizes —
    this still confirms the function ran with account=100000.
    '''
    fix = _load_phase2_fixture('transition_long_to_short')
    result = _call_step(fix)
    # sizing_decision must be populated (entry was attempted, even though size=0).
    assert result.sizing_decision is not None, (
      'D-19: sizing_decision must be populated for reversal fixture'
    )
    # Account is unchanged (no account_after on StepResult).
    assert not hasattr(result, 'account_after'), (
      'D-19 violation: StepResult must not have account_after (Phase 3 owns account)'
    )

  # --- B-5: stop-hit exits use stop level as fill price, not bar.close ---

  def test_step_b5_long_stop_hit_uses_stop_level_as_exit_price(self) -> None:
    '''B-5 LONG: stop-hit close fills at stop level (6891.0), not bar.close (6900.0).

    Realised PnL = (6891 - 7000) * 2 * 5 - 3.0 * 2 = -1090 - 6 = -1096.0.
    If bar.close were used: (6900 - 7000) * 2 * 5 - 6 = -1000 - 6 = -1006.0 (wrong).
    '''
    fix = _load_phase2_fixture('long_trail_stop_hit_intraday_low')
    result = _call_step(fix)
    assert result.closed_trade is not None, 'B-5: stop hit must produce a closed_trade'
    assert result.closed_trade.exit_reason == 'stop_hit', (
      f'B-5: exit_reason {result.closed_trade.exit_reason!r} should be "stop_hit"'
    )
    # Stop level = peak(7050) - 3*atr_entry(53) = 7050 - 159 = 6891.0
    assert abs(result.closed_trade.exit_price - 6891.0) < 1e-9, (
      f'B-5: exit_price {result.closed_trade.exit_price} should be stop level 6891.0'
    )
    expected_pnl = (6891.0 - 7000.0) * 2 * 5 - 3.0 * 2  # -1096.0
    assert abs(result.closed_trade.realised_pnl - expected_pnl) < 1e-9, (
      f'B-5: realised_pnl {result.closed_trade.realised_pnl} should be {expected_pnl}'
    )

  def test_step_b5_short_stop_hit_uses_stop_level_as_exit_price(self) -> None:
    '''B-5 SHORT: stop-hit close fills at stop level (7056.0), not bar.close (7050.0).

    Realised PnL = -1*(7056 - 7000) * 2 * 5 - 3.0 * 2 = -560 - 6 = -566.0.
    '''
    fix = _load_phase2_fixture('short_trail_stop_hit_intraday_high')
    result = _call_step(fix)
    assert result.closed_trade is not None, 'B-5 SHORT: stop hit must produce a closed_trade'
    assert result.closed_trade.exit_reason == 'stop_hit'
    # Stop level = trough(6950) + 2*atr_entry(53) = 6950 + 106 = 7056.0
    assert abs(result.closed_trade.exit_price - 7056.0) < 1e-9, (
      f'B-5 SHORT: exit_price {result.closed_trade.exit_price} should be 7056.0'
    )
    expected_pnl = -1.0 * (7056.0 - 7000.0) * 2 * 5 - 3.0 * 2  # -566.0
    assert abs(result.closed_trade.realised_pnl - expected_pnl) < 1e-9, (
      f'B-5 SHORT: realised_pnl {result.closed_trade.realised_pnl} should be {expected_pnl}'
    )

  def test_step_b5_flat_signal_close_still_uses_bar_close(self) -> None:
    '''B-5 negative: FLAT signal exit uses bar.close (not stop level).

    LONG->FLAT fixture: bar.close=6990, exit_price must be 6990.0.
    '''
    fix = _load_phase2_fixture('transition_long_to_flat')
    result = _call_step(fix)
    assert result.closed_trade is not None, 'FLAT must produce a closed_trade'
    assert result.closed_trade.exit_reason == 'flat_signal'
    assert abs(result.closed_trade.exit_price - fix['bar']['close']) < 1e-9, (
      f'B-5 negative: flat exit should use bar.close {fix["bar"]["close"]}, '
      f'got {result.closed_trade.exit_price}'
    )

  # --- A2: no new entry on forced-exit day ---

  def test_step_no_entry_on_adx_exit_day(self) -> None:
    '''A2 (RESEARCH): ADX-exit forces close; no new entry fires on the same bar.

    EXIT-05 fixture: adx=18 < 20, new_signal=LONG. Despite LONG signal,
    sizing_decision must be None (forced exit suppresses entry per A2).
    '''
    fix = _load_phase2_fixture('adx_drop_below_20_while_in_trade')
    result = _call_step(fix)
    assert result.closed_trade is not None, 'A2: ADX exit must close the position'
    assert result.closed_trade.exit_reason == 'adx_exit'
    assert result.sizing_decision is None, (
      f'A2 violation: sizing_decision should be None on forced ADX-exit day, '
      f'got {result.sizing_decision}'
    )
    assert result.position_after is None, (
      'A2: position_after must be None (no new entry on forced-exit day)'
    )

  def test_step_no_entry_on_long_stop_hit(self) -> None:
    '''A2: LONG stop hit forces close; new_signal=LONG but no new entry fires.'''
    fix = _load_phase2_fixture('long_trail_stop_hit_intraday_low')
    result = _call_step(fix)
    assert result.closed_trade is not None
    assert result.closed_trade.exit_reason == 'stop_hit'
    assert result.sizing_decision is None, (
      'A2 violation: sizing_decision must be None on stop-hit day'
    )
    assert result.position_after is None, (
      'A2: position_after must be None after stop hit (no new entry)'
    )

  def test_step_no_entry_on_short_stop_hit(self) -> None:
    '''A2: SHORT stop hit forces close; new_signal=SHORT but no new entry fires.'''
    fix = _load_phase2_fixture('short_trail_stop_hit_intraday_high')
    result = _call_step(fix)
    assert result.closed_trade is not None
    assert result.closed_trade.exit_reason == 'stop_hit'
    assert result.sizing_decision is None, (
      'A2 violation: sizing_decision must be None on stop-hit day'
    )
    assert result.position_after is None, (
      'A2: position_after must be None after stop hit (no new entry)'
    )

  # --- SIZE-05 warning propagation ---

  def test_step_size_zero_warning_propagates(self) -> None:
    '''SIZE-05: when new entry sizes to 0 contracts, the warning appears in
    StepResult.warnings. The position_after stays None (no position opened).'''
    fix = _load_phase2_fixture('n_contracts_zero_skip_warning')
    result = _call_step(fix)
    assert result.position_after is None, 'SIZE-05: no position opened when contracts=0'
    assert result.sizing_decision is not None, (
      'SIZE-05: sizing_decision must be populated even when contracts=0'
    )
    assert result.sizing_decision.contracts == 0
    assert result.sizing_decision.warning is not None and (
      result.sizing_decision.warning.startswith('size=0:')
    ), f'SIZE-05: warning format wrong: {result.sizing_decision.warning!r}'
    assert any(w.startswith('size=0:') for w in result.warnings), (
      f'SIZE-05: size=0 warning must appear in StepResult.warnings: {result.warnings}'
    )

  # --- B-6: unrealised_pnl is post-pyramid (computed on final n_contracts) ---

  def test_step_b6_unrealised_pnl_is_post_pyramid(self) -> None:
    '''B-6: step().unrealised_pnl is computed on position_after AFTER pyramid add.

    LONG hold fixture: prev.n_contracts=2; pyramid fires (add=1); position_after.n_contracts=3.
    unrealised_pnl must be computed with n=3, not n=2.

    Pre-pyramid (n=2): (7110-7000)*2*5 - 3.0*2 = 1100-6 = 1094.0  (fixture unrealised_pnl)
    Post-pyramid (n=3): (7110-7000)*3*5 - 3.0*3 = 1650-9 = 1641.0
    '''
    fix = _load_phase2_fixture('transition_long_to_long')
    result = _call_step(fix)
    # Fixture's unrealised_pnl field = pre-pyramid value from individual callable.
    pre_pyramid_pnl = fix['expected']['unrealised_pnl']  # 1094.0 (n=2)
    # step() must return the POST-pyramid value (n=3).
    post_pyramid_pnl = (7110.0 - 7000.0) * 3 * 5 - 3.0 * 3  # 1641.0
    assert abs(result.unrealised_pnl - post_pyramid_pnl) < 1e-9, (
      f'B-6: unrealised_pnl {result.unrealised_pnl} should be post-pyramid '
      f'{post_pyramid_pnl} (not pre-pyramid {pre_pyramid_pnl})'
    )
    assert abs(result.unrealised_pnl - pre_pyramid_pnl) > 1.0, (
      f'B-6 sanity: if pre and post pnl are equal, pyramid was not applied '
      f'({result.unrealised_pnl} vs {pre_pyramid_pnl})'
    )

  # --- D-17: step() signature check ---

  def test_step_d17_signature(self) -> None:
    '''D-17: step() must have all 8 parameters with no defaults on the last 3.

    The four post-D-10 parameters (account, multiplier, cost_aud_open) are
    required — defaulting them would introduce hidden state coupling.
    '''
    import inspect
    sig = inspect.signature(step)
    params = list(sig.parameters)
    assert params == [
      'position', 'bar', 'indicators', 'old_signal', 'new_signal',
      'account', 'multiplier', 'cost_aud_open',
    ], f'D-17: step() parameters mismatch: {params}'
    # The last 3 must have no default (required args).
    for name in ('account', 'multiplier', 'cost_aud_open'):
      p = sig.parameters[name]
      assert p.default is inspect.Parameter.empty, (
        f'D-17: step() parameter {name!r} must have no default '
        f'(got {p.default!r})'
      )

  # --- Gap-through-stop: B-5 stop-level fill even when gapped through ---

  def test_step_b5_long_gap_through_stop_uses_stop_level(self) -> None:
    '''B-5 + Pitfall 2: gap-down through stop (open=6800 < stop=6891).
    exit_price must be the STOP level (6891.0), not bar.close (6790.0),
    not bar.open (6800.0). Detection only: check_stop_hit returned True.
    Realised PnL = (6891-7000)*2*5 - 3.0*2 = -1090 - 6 = -1096.0.
    '''
    fix = _load_phase2_fixture('long_gap_through_stop')
    result = _call_step(fix)
    assert result.closed_trade is not None
    assert result.closed_trade.exit_reason == 'stop_hit'
    assert abs(result.closed_trade.exit_price - 6891.0) < 1e-9, (
      f'B-5 gap: exit_price {result.closed_trade.exit_price} should be stop=6891.0'
    )
    expected_pnl = (6891.0 - 7000.0) * 2 * 5 - 3.0 * 2  # -1096.0
    assert abs(result.closed_trade.realised_pnl - expected_pnl) < 1e-9, (
      f'B-5 gap: realised_pnl {result.closed_trade.realised_pnl} != {expected_pnl}'
    )
