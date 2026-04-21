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

# Module-level path constants (mirrors test_signal_engine.py SIGNAL_ENGINE_PATH pattern)
SIZING_ENGINE_PATH = Path('sizing_engine.py')
SYSTEM_PARAMS_PATH = Path('system_params.py')
PHASE2_FIXTURES_DIR = Path('tests/fixtures/phase2')
PHASE2_SNAPSHOT_PATH = Path('tests/determinism/phase2_snapshot.json')


# =========================================================================
# TestSizing — SIZE-01..06: calc_position_size unit tests
# =========================================================================

class TestSizing:
  '''Unit tests for calc_position_size (SIZE-01..06).

  Covers: risk_pct by direction, trail_mult by direction, vol_scale clip + NaN
  guard, n_contracts formula, no max(1,...) floor (SIZE-05 skip + warn).

  Implementations land in Plan 02-02.
  '''

  def test_risk_pct_long_is_1pct(self) -> None:
    '''SIZE-01: LONG entry uses 1.0% account risk.'''
    pytest.skip('implement in Plan 02-02')

  def test_risk_pct_short_is_half_pct(self) -> None:
    '''SIZE-01: SHORT entry uses 0.5% account risk.'''
    pytest.skip('implement in Plan 02-02')

  def test_trail_mult_by_direction(self) -> None:
    '''SIZE-02: trail_mult = 3.0 for LONG, 2.0 for SHORT.'''
    pytest.skip('implement in Plan 02-02')

  def test_vol_scale_nan_guard(self) -> None:
    '''SIZE-03: NaN/zero/inf rvol -> vol_scale = VOL_SCALE_MAX (2.0).'''
    pytest.skip('implement in Plan 02-02')

  def test_vol_scale_clip_min(self) -> None:
    '''SIZE-03: very high rvol clips vol_scale to VOL_SCALE_MIN (0.3).'''
    pytest.skip('implement in Plan 02-02')

  def test_vol_scale_clip_max(self) -> None:
    '''SIZE-03: very low rvol clips vol_scale to VOL_SCALE_MAX (2.0).'''
    pytest.skip('implement in Plan 02-02')

  def test_calc_position_size_formula(self) -> None:
    '''SIZE-04: n_contracts = int((account * risk_pct / stop_dist) * vol_scale).'''
    pytest.skip('implement in Plan 02-02')

  def test_zero_contracts_warning(self) -> None:
    '''SIZE-05: n_contracts == 0 returns SizingDecision(0, warning="size=0: ...").'''
    pytest.skip('implement in Plan 02-02')

  def test_no_max1_floor(self) -> None:
    '''SIZE-05: no max(1,...) floor applied — undersized result stays at 0.'''
    pytest.skip('implement in Plan 02-02')

  def test_spi_mini_multiplier_constant(self) -> None:
    '''D-11: SPI_MULT = 5 used in stop_dist; $5/pt confirmed (not $25).'''
    pytest.skip('implement in Plan 02-02')


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
