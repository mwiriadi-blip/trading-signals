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
