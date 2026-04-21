'''Phase 2 test suite: position sizing, exits, pyramid, transitions, and step().

Organized into classes per D-13 / Phase 2 RESEARCH §Validation Architecture.
Test skeletons created in Plan 02-01 (Wave 0 scaffold); implementations land
in Plans 02-02 (sizing), 02-03 (exits + pyramid), 02-04 (scenario fixtures),
02-05 (step() integration).

Fixture files live at tests/fixtures/phase2/*.json (15 JSON scenario fixtures
per D-14); Phase 2 determinism snapshot at tests/determinism/phase2_snapshot.json.
'''
from pathlib import Path

import pytest

from signal_engine import FLAT, LONG, SHORT
from sizing_engine import SizingDecision, calc_position_size, compute_unrealised_pnl
from system_params import Position

# Module-level path constants (mirrors test_signal_engine.py SIGNAL_ENGINE_PATH pattern)
SIZING_ENGINE_PATH = Path('sizing_engine.py')
SYSTEM_PARAMS_PATH = Path('system_params.py')
PHASE2_FIXTURES_DIR = Path('tests/fixtures/phase2')
PHASE2_SNAPSHOT_PATH = Path('tests/determinism/phase2_snapshot.json')


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
  '''Unit tests for get_trailing_stop and check_stop_hit (EXIT-06..09).

  Covers: LONG/SHORT stop computation, intraday H/L hit detection, D-15
  ATR anchor, None-guard for peak/trough, NaN guard per D-03.

  Implementations land in Plan 02-03.
  '''

  def test_long_trailing_stop_formula(self) -> None:
    '''EXIT-06: LONG stop = peak_price - TRAIL_MULT_LONG * atr_entry.'''
    pytest.skip('implement in Plan 02-03')

  def test_short_trailing_stop_formula(self) -> None:
    '''EXIT-07: SHORT stop = trough_price + TRAIL_MULT_SHORT * atr_entry.'''
    pytest.skip('implement in Plan 02-03')

  def test_long_trailing_stop_peak_update(self) -> None:
    '''EXIT-06: peak updates with today HIGH (owned by step(), D-16).'''
    pytest.skip('implement in Plan 02-03')

  def test_short_trailing_stop_trough_update(self) -> None:
    '''EXIT-07: trough updates with today LOW (owned by step(), D-16).'''
    pytest.skip('implement in Plan 02-03')

  def test_long_stop_hit_intraday_low(self) -> None:
    '''EXIT-08: LONG stop hit when low <= stop.'''
    pytest.skip('implement in Plan 02-03')

  def test_short_stop_hit_intraday_high(self) -> None:
    '''EXIT-09: SHORT stop hit when high >= stop.'''
    pytest.skip('implement in Plan 02-03')

  def test_long_stop_not_hit_above(self) -> None:
    '''EXIT-08: LONG stop NOT hit when low > stop.'''
    pytest.skip('implement in Plan 02-03')

  def test_short_stop_not_hit_below(self) -> None:
    '''EXIT-09: SHORT stop NOT hit when high < stop.'''
    pytest.skip('implement in Plan 02-03')

  def test_stop_hit_nan_guard_returns_false(self) -> None:
    '''D-03: NaN inputs to check_stop_hit -> False (no false exit).'''
    pytest.skip('implement in Plan 02-03')

  def test_trailing_stop_nan_guard_returns_nan(self) -> None:
    '''D-03: NaN inputs to get_trailing_stop -> float("nan").'''
    pytest.skip('implement in Plan 02-03')

  def test_d15_uses_atr_entry_not_today_atr(self) -> None:
    '''D-15: stop distance uses position["atr_entry"] not the atr argument.'''
    pytest.skip('implement in Plan 02-03')

  def test_peak_none_falls_back_to_entry_price(self) -> None:
    '''Pitfall 3: peak_price=None -> fallback to entry_price prevents TypeError.'''
    pytest.skip('implement in Plan 02-03')


# =========================================================================
# TestPyramid — PYRA-01..05: check_pyramid unit tests
# =========================================================================

class TestPyramid:
  '''Unit tests for check_pyramid (PYRA-01..05).

  Covers: level 0->1 at 1x ATR, level 1->2 at 2x ATR, cap at level 2,
  PYRA-05 single-step per call, NaN guard per D-03, stateless invariant.

  Implementations land in Plan 02-03.
  '''

  def test_position_carries_pyramid_level(self) -> None:
    '''PYRA-01: Position TypedDict has pyramid_level field.'''
    pytest.skip('implement in Plan 02-03')

  def test_pyramid_level_0_to_1(self) -> None:
    '''PYRA-02: level 0 -> 1 when unrealised >= 1 * atr_entry.'''
    pytest.skip('implement in Plan 02-03')

  def test_pyramid_level_1_to_2(self) -> None:
    '''PYRA-03: level 1 -> 2 when unrealised >= 2 * atr_entry.'''
    pytest.skip('implement in Plan 02-03')

  def test_pyramid_capped_at_level_2(self) -> None:
    '''PYRA-04: at level 2, check_pyramid returns add_contracts=0.'''
    pytest.skip('implement in Plan 02-03')

  def test_pyramid_below_threshold_no_add(self) -> None:
    '''PYRA-02: unrealised < 1 * atr_entry at level 0 -> no add.'''
    pytest.skip('implement in Plan 02-03')

  def test_pyramid_short_direction(self) -> None:
    '''PYRA-02: SHORT pyramid triggers on price fall (distance = entry - current).'''
    pytest.skip('implement in Plan 02-03')

  def test_pyramid_nan_guard_no_add(self) -> None:
    '''D-03: NaN current_price or atr_entry -> PyramidDecision(0, current_level).'''
    pytest.skip('implement in Plan 02-03')

  def test_pyramid_stateless_no_side_effects(self) -> None:
    '''D-12: check_pyramid does not mutate the input position.'''
    pytest.skip('implement in Plan 02-03')


# =========================================================================
# TestTransitions — EXIT-01..04: 9-cell signal transition truth table
# =========================================================================

class TestTransitions:
  '''Scenario-fixture tests for the 9-cell signal transition truth table.

  9 JSON fixtures per D-14/D-05 (tests/fixtures/phase2/transition_*.json).
  Implementations land in Plan 02-04 (fixtures) + 02-05 (step() wiring).
  '''

  def test_transition_long_to_long(self) -> None:
    '''LONG->LONG: hold; check stop + pyramid + pnl. No exit/entry.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_transition_long_to_short(self) -> None:
    '''EXIT-03: LONG->SHORT — close LONG then open SHORT in one step.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_transition_long_to_flat(self) -> None:
    '''EXIT-01: LONG->FLAT closes the LONG, no new position.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_transition_short_to_long(self) -> None:
    '''EXIT-04: SHORT->LONG — close SHORT then open LONG in one step.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_transition_short_to_short(self) -> None:
    '''SHORT->SHORT: hold; check stop + pyramid + pnl. No exit/entry.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_transition_short_to_flat(self) -> None:
    '''EXIT-02: SHORT->FLAT closes the SHORT, no new position.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_transition_none_to_long(self) -> None:
    '''Flat->LONG: new LONG entry — calc_position_size + open position.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_transition_none_to_short(self) -> None:
    '''Flat->SHORT: new SHORT entry — calc_position_size + open position.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_transition_none_to_flat(self) -> None:
    '''Flat->FLAT: no position, no signal — no action.'''
    pytest.skip('implement in Plan 02-04/02-05')


# =========================================================================
# TestEdgeCases — 6 edge-case scenario fixtures (D-14)
# =========================================================================

class TestEdgeCases:
  '''Edge-case scenario tests: EXIT-05, stop hit, PYRA-05 gap, SIZE-05 zero.

  6 JSON fixtures per D-14 (tests/fixtures/phase2/<name>.json).
  Implementations land in Plan 02-04 (fixtures) + 02-05 (step() wiring).
  '''

  def test_pyramid_gap_crosses_both_levels_caps_at_1(self) -> None:
    '''PYRA-05: gap day where close is past 2*ATR but only 1 contract added (D-12).'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_adx_drop_below_20_while_in_trade(self) -> None:
    '''EXIT-05: ADX falls to < 20 during LONG -> close regardless of new_signal.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_long_trail_stop_hit_intraday_low(self) -> None:
    '''EXIT-08: today LOW is at or below the LONG trailing stop -> position closed.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_short_trail_stop_hit_intraday_high(self) -> None:
    '''EXIT-09: today HIGH is at or above the SHORT trailing stop -> position closed.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_long_gap_through_stop(self) -> None:
    '''EXIT-08: open gaps below LONG stop; LOW also below stop -> stop detected.'''
    pytest.skip('implement in Plan 02-04/02-05')

  def test_n_contracts_zero_skip_warning(self) -> None:
    '''SIZE-05: account+ATR combination yields n_raw < 1 -> SizingDecision(0, warning).'''
    pytest.skip('implement in Plan 02-04/02-05')
