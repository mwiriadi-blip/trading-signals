'''Phase 1 test suite: signal engine indicators + vote + edge cases + determinism.

Organized into classes per D-13. This file grows across Plans 04 (TestIndicators),
05 (TestVote, TestEdgeCases), and 06 (TestDeterminism + architectural guards).

This file is created in Plan 04 with TestIndicators only.
'''
import numpy as np
import pandas as pd
import pytest

from signal_engine import compute_indicators

CANONICAL_FIXTURES = ['axjo_400bar', 'audusd_400bar']
INDICATOR_COLUMNS = ['ATR', 'ADX', 'PDI', 'NDI', 'Mom1', 'Mom3', 'Mom12', 'RVol']
EXPECTED_OUTPUT_COLUMNS = [
  'Open', 'High', 'Low', 'Close', 'Volume',
  'ATR', 'ADX', 'PDI', 'NDI', 'Mom1', 'Mom3', 'Mom12', 'RVol',
]


def _load_fixture(stem: str) -> pd.DataFrame:
  '''Load an OHLCV fixture CSV, cast numeric columns to float64.'''
  df = pd.read_csv(
    f'tests/fixtures/{stem}.csv',
    parse_dates=['Date'],
    index_col='Date',
  )
  for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
    df[col] = df[col].astype('float64')
  return df


def _load_golden(stem: str) -> pd.DataFrame:
  '''Load an oracle golden indicators CSV (Plan 03 output) at float64.'''
  df = pd.read_csv(
    f'tests/oracle/goldens/{stem}_indicators.csv',
    parse_dates=['Date'],
    index_col='Date',
  )
  for col in INDICATOR_COLUMNS:
    df[col] = df[col].astype('float64')
  return df


def _assert_index_aligned(computed: pd.DataFrame, golden: pd.DataFrame) -> None:
  '''REVIEWS MEDIUM: assert shape + index + column order BEFORE float comparison.

  Without these assertions a date-index mismatch would fail assert_allclose
  opaquely (wrong floats compared against wrong goldens).
  '''
  assert len(computed) == len(golden), (
    f'row-count mismatch: computed={len(computed)} golden={len(golden)}'
  )
  assert computed.index.equals(golden.index), (
    f'date-index mismatch: computed[0]={computed.index[0]} '
    f'golden[0]={golden.index[0]} computed[-1]={computed.index[-1]} '
    f'golden[-1]={golden.index[-1]}'
  )
  assert list(computed.columns) == EXPECTED_OUTPUT_COLUMNS, (
    f'column-order mismatch: got {list(computed.columns)}, '
    f'expected {EXPECTED_OUTPUT_COLUMNS}'
  )


class TestIndicators:
  '''Per-indicator oracle-vs-production comparisons + invariants.

  Every test that compares floats first calls _assert_index_aligned to guard
  against date-index drift (REVIEWS MEDIUM).
  '''

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  @pytest.mark.parametrize('col', INDICATOR_COLUMNS)
  def test_indicator_matches_oracle(self, stem: str, col: str) -> None:
    '''Parametrized 8 indicators × 2 fixtures = 16 oracle comparisons.'''
    fixture = _load_fixture(stem)
    golden = _load_golden(stem)
    computed = compute_indicators(fixture)
    # REVIEWS MEDIUM: index-alignment assertions BEFORE assert_allclose
    _assert_index_aligned(computed, golden)
    actual = computed[col].to_numpy(dtype='float64')
    expected = golden[col].to_numpy(dtype='float64')
    np.testing.assert_allclose(
      actual, expected, atol=1e-9, equal_nan=True,
      err_msg=f'{stem} {col} production != oracle golden',
    )

  # --- Named SIG-XX shortcut tests (for targeted pytest -k filters) ---

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_atr_matches_oracle(self, stem: str) -> None:
    '''SIG-01: ATR(14) Wilder, SMA-seeded per R-01.'''
    fixture = _load_fixture(stem)
    golden = _load_golden(stem)
    computed = compute_indicators(fixture)
    _assert_index_aligned(computed, golden)
    np.testing.assert_allclose(
      computed['ATR'].to_numpy(dtype='float64'),
      golden['ATR'].to_numpy(dtype='float64'),
      atol=1e-9, equal_nan=True,
    )

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_adx_matches_oracle(self, stem: str) -> None:
    '''SIG-02: ADX(20) + +DI + -DI Wilder.'''
    fixture = _load_fixture(stem)
    golden = _load_golden(stem)
    out = compute_indicators(fixture)
    _assert_index_aligned(out, golden)
    for col in ['ADX', 'PDI', 'NDI']:
      np.testing.assert_allclose(
        out[col].to_numpy(dtype='float64'),
        golden[col].to_numpy(dtype='float64'),
        atol=1e-9, equal_nan=True,
        err_msg=f'{stem} {col}',
      )

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_mom_matches_oracle(self, stem: str) -> None:
    '''SIG-03: Mom(21/63/252).'''
    fixture = _load_fixture(stem)
    golden = _load_golden(stem)
    out = compute_indicators(fixture)
    _assert_index_aligned(out, golden)
    for col in ['Mom1', 'Mom3', 'Mom12']:
      np.testing.assert_allclose(
        out[col].to_numpy(dtype='float64'),
        golden[col].to_numpy(dtype='float64'),
        atol=1e-9, equal_nan=True,
        err_msg=f'{stem} {col}',
      )

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_rvol_matches_oracle(self, stem: str) -> None:
    '''SIG-04: RVol(20) annualised.'''
    fixture = _load_fixture(stem)
    golden = _load_golden(stem)
    computed = compute_indicators(fixture)
    _assert_index_aligned(computed, golden)
    np.testing.assert_allclose(
      computed['RVol'].to_numpy(dtype='float64'),
      golden['RVol'].to_numpy(dtype='float64'),
      atol=1e-9, equal_nan=True,
    )

  # --- REVIEWS MEDIUM: dedicated shape/index/column-order guard ---

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_output_shape_index_columns_are_correct(self, stem: str) -> None:
    '''REVIEWS MEDIUM: explicit assertion for row-count, index, and column order.'''
    fixture = _load_fixture(stem)
    golden = _load_golden(stem)
    computed = compute_indicators(fixture)
    assert len(computed) == len(golden), 'row count differs from golden'
    assert computed.index.equals(golden.index), 'index differs from golden'
    assert list(computed.columns) == EXPECTED_OUTPUT_COLUMNS, (
      f'column order must be {EXPECTED_OUTPUT_COLUMNS}, got {list(computed.columns)}'
    )

  # --- Warmup invariants per R-01 (ATR bar 13, ADX bar 38, Mom12 bar 252, RVol bar 20) ---

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_atr_warmup_bars_0_to_12_are_nan(self, stem: str) -> None:
    out = compute_indicators(_load_fixture(stem))
    assert out['ATR'].iloc[:13].isna().all(), f'{stem}: ATR bars 0..12 must be NaN'
    assert not pd.isna(out['ATR'].iloc[13]), f'{stem}: ATR bar 13 must be finite'

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_adx_warmup_bars_0_to_37_are_nan(self, stem: str) -> None:
    out = compute_indicators(_load_fixture(stem))
    assert out['ADX'].iloc[:38].isna().all(), f'{stem}: ADX bars 0..37 must be NaN'
    assert not pd.isna(out['ADX'].iloc[38]), f'{stem}: ADX bar 38 must be finite'

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_mom12_warmup_bars_0_to_251_are_nan(self, stem: str) -> None:
    out = compute_indicators(_load_fixture(stem))
    assert out['Mom12'].iloc[:252].isna().all(), f'{stem}: Mom12 bars 0..251 must be NaN'
    assert not pd.isna(out['Mom12'].iloc[252]), f'{stem}: Mom12 bar 252 must be finite'

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_rvol_warmup_bars_0_to_19_are_nan(self, stem: str) -> None:
    out = compute_indicators(_load_fixture(stem))
    assert out['RVol'].iloc[:20].isna().all(), f'{stem}: RVol bars 0..19 must be NaN'
    assert not pd.isna(out['RVol'].iloc[20]), f'{stem}: RVol bar 20 must be finite'

  # --- D-07 non-mutation ---

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_compute_indicators_non_mutating(self, stem: str) -> None:
    '''D-07: compute_indicators returns a NEW DataFrame; input is unchanged.'''
    fixture = _load_fixture(stem)
    original_cols = set(fixture.columns)
    original_len = len(fixture)
    original_close_sum = fixture['Close'].sum()
    _ = compute_indicators(fixture)
    assert set(fixture.columns) == original_cols, 'input columns mutated'
    assert len(fixture) == original_len, 'input length mutated'
    assert fixture['Close'].sum() == original_close_sum, 'input Close mutated'
    # And ensure no indicator cols leaked onto input
    for col in INDICATOR_COLUMNS:
      assert col not in fixture.columns, f'input gained {col} column'

  # --- Pitfall 5 float64 dtype guarantee ---

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  def test_all_indicator_columns_are_float64(self, stem: str) -> None:
    '''Pitfall 5: force float64 so numpy 2.0 float32 leaks can't poison SHA256 snapshots.'''
    out = compute_indicators(_load_fixture(stem))
    for col in INDICATOR_COLUMNS:
      assert out[col].dtype.name == 'float64', (
        f'{stem} {col} has dtype {out[col].dtype.name}, expected float64 (Pitfall 5)'
      )


# =========================================================================
# TestVote -- 9 scenario fixtures covering the vote truth table (D-16)
# =========================================================================

SCENARIOS = [
  'scenario_adx_below_25_flat',
  'scenario_adx_above_25_long_3_votes',
  'scenario_adx_above_25_long_2_votes',
  'scenario_adx_above_25_short_3_votes',
  'scenario_adx_above_25_short_2_votes',
  'scenario_adx_above_25_split_vote_flat',
  'scenario_warmup_nan_adx_flat',
  'scenario_warmup_mom12_nan_two_mom_agreement',
  'scenario_flat_prices_divide_by_zero',
]


def _load_scenario_expected(stem: str) -> dict:
  import json
  with open(f'tests/oracle/goldens/{stem}.json') as fh:
    return json.load(fh)


def _make_single_bar_df(*, adx, mom1, mom3, mom12,
                         atr=1.0, pdi=20.0, ndi=20.0, rvol=0.1) -> pd.DataFrame:
  '''Build a 1-bar DataFrame with the minimum indicator columns `get_signal` reads.

  Used by threshold-equality tests -- no need to run `compute_indicators`.
  '''
  return pd.DataFrame({
    'ATR': [atr], 'ADX': [adx], 'PDI': [pdi], 'NDI': [ndi],
    'Mom1': [mom1], 'Mom3': [mom3], 'Mom12': [mom12], 'RVol': [rvol],
  })


class TestVote:
  '''Per-scenario signal correctness (D-16). Each test name encodes the truth-table row.'''

  @pytest.mark.parametrize('stem', SCENARIOS)
  def test_scenario_produces_expected_signal(self, stem: str) -> None:
    from signal_engine import compute_indicators, get_signal
    fixture = _load_fixture(stem)
    expected = _load_scenario_expected(stem)['expected_signal']
    actual = get_signal(compute_indicators(fixture))
    assert actual == expected, f'{stem}: got {actual}, expected {expected}'

  # --- Named SIG-05..08 shortcut tests ---

  def test_adx_below_25_flat(self) -> None:
    '''SIG-05: ADX < 25 returns FLAT regardless of momentum.'''
    from signal_engine import FLAT, compute_indicators, get_signal
    fixture = _load_fixture('scenario_adx_below_25_flat')
    assert get_signal(compute_indicators(fixture)) == FLAT

  def test_adx_above_25_long_3_votes(self) -> None:
    '''SIG-06: ADX >= 25 + 3 moms > +0.02 -> LONG.'''
    from signal_engine import LONG, compute_indicators, get_signal
    fixture = _load_fixture('scenario_adx_above_25_long_3_votes')
    assert get_signal(compute_indicators(fixture)) == LONG

  def test_adx_above_25_long_2_votes(self) -> None:
    '''SIG-06: ADX >= 25 + 2 moms > +0.02 -> LONG.'''
    from signal_engine import LONG, compute_indicators, get_signal
    fixture = _load_fixture('scenario_adx_above_25_long_2_votes')
    assert get_signal(compute_indicators(fixture)) == LONG

  def test_adx_above_25_short_3_votes(self) -> None:
    '''SIG-07: ADX >= 25 + 3 moms < -0.02 -> SHORT.'''
    from signal_engine import SHORT, compute_indicators, get_signal
    fixture = _load_fixture('scenario_adx_above_25_short_3_votes')
    assert get_signal(compute_indicators(fixture)) == SHORT

  def test_adx_above_25_short_2_votes(self) -> None:
    '''SIG-07: ADX >= 25 + 2 moms < -0.02 -> SHORT.'''
    from signal_engine import SHORT, compute_indicators, get_signal
    fixture = _load_fixture('scenario_adx_above_25_short_2_votes')
    assert get_signal(compute_indicators(fixture)) == SHORT

  def test_adx_above_25_split_vote_flat(self) -> None:
    '''SIG-08: ADX >= 25 + split vote (neither direction reaches 2) -> FLAT.

    Per REVIEWS MUST FIX the fixture is 1 up / 1 down / 1 abstain (not 2 up / 1 down).
    '''
    from signal_engine import FLAT, compute_indicators, get_signal
    fixture = _load_fixture('scenario_adx_above_25_split_vote_flat')
    assert get_signal(compute_indicators(fixture)) == FLAT


# =========================================================================
# TestEdgeCases -- D-09 / D-10 / D-11 / D-12 + threshold-equality boundaries
# =========================================================================

class TestEdgeCases:
  '''NaN and divide-by-zero policy per CONTEXT.md D-09..D-12, plus
  threshold-equality boundary tests per REVIEWS STRONGLY RECOMMENDED.'''

  def test_warmup_nan_adx_flat(self) -> None:
    '''D-09: NaN ADX (warmup) -> FLAT (no position taken).'''
    from signal_engine import FLAT, compute_indicators, get_signal
    fixture = _load_fixture('scenario_warmup_nan_adx_flat')
    out = compute_indicators(fixture)
    assert pd.isna(out['ADX'].iloc[-1]), 'fixture must have NaN ADX at last bar'
    assert get_signal(out) == FLAT

  def test_warmup_mom12_nan_two_mom_agreement(self) -> None:
    '''D-10: NaN Mom12 + Mom1+Mom3 agree -> LONG/SHORT via 2-of-2.'''
    from signal_engine import compute_indicators, get_signal
    stem = 'scenario_warmup_mom12_nan_two_mom_agreement'
    expected = _load_scenario_expected(stem)['expected_signal']
    assert expected != 0, 'scenario should produce non-FLAT per D-10'
    fixture = _load_fixture(stem)
    out = compute_indicators(fixture)
    assert pd.isna(out['Mom12'].iloc[-1]), 'fixture must have NaN Mom12 at last bar'
    assert get_signal(out) == expected

  def test_flat_prices_divide_by_zero(self) -> None:
    '''D-11: flat prices -> +DI/-DI/ADX NaN -> signal FLAT via D-09.'''
    from signal_engine import FLAT, compute_indicators, get_signal
    fixture = _load_fixture('scenario_flat_prices_divide_by_zero')
    out = compute_indicators(fixture)
    assert pd.isna(out['ADX'].iloc[-1])
    assert pd.isna(out['PDI'].iloc[-1])
    assert pd.isna(out['NDI'].iloc[-1])
    assert get_signal(out) == FLAT

  def test_rvol_zero_on_flat_prices(self) -> None:
    '''D-12: flat prices -> RVol exactly 0.0 (no guard in Phase 1; Phase 2 clamps).'''
    from signal_engine import compute_indicators
    fixture = _load_fixture('scenario_flat_prices_divide_by_zero')
    out = compute_indicators(fixture)
    # Bit-identical floats -> zero std -> RVol = 0.0 exactly per Pitfall 6 + D-12
    assert out['RVol'].iloc[-1] == 0.0, (
      f'RVol on flat prices must be bit-exact 0.0, got {out["RVol"].iloc[-1]}'
    )

  # --- REVIEWS STRONGLY RECOMMENDED: threshold-equality boundary tests ---

  def test_adx_exactly_25_opens_gate(self) -> None:
    '''REVIEWS STRONGLY RECOMMENDED: rule is `adx < ADX_GATE` for FLAT, so equality
    (adx == 25.0) opens the gate. With three up-votes this must be LONG.'''
    from signal_engine import LONG, get_signal
    df = _make_single_bar_df(adx=25.0, mom1=0.03, mom3=0.04, mom12=0.05)
    assert get_signal(df) == LONG, 'adx=25.0 exactly must pass the gate (rule is `< 25`)'

  def test_mom_exactly_plus_threshold_abstains(self) -> None:
    '''REVIEWS STRONGLY RECOMMENDED: rule is `m > +MOM_THRESHOLD`. A mom of exactly
    +0.02 abstains -- neither up nor down vote. With all three at +0.02 -> 0 votes -> FLAT.'''
    from signal_engine import FLAT, get_signal
    df = _make_single_bar_df(adx=30.0, mom1=0.02, mom3=0.02, mom12=0.02)
    assert get_signal(df) == FLAT, 'mom=+0.02 exactly must abstain (rule is `> +0.02`)'

  def test_mom_exactly_minus_threshold_abstains(self) -> None:
    '''REVIEWS STRONGLY RECOMMENDED: rule is `m < -MOM_THRESHOLD`. A mom of exactly
    -0.02 abstains. With all three at -0.02 -> 0 votes -> FLAT.'''
    from signal_engine import FLAT, get_signal
    df = _make_single_bar_df(adx=30.0, mom1=-0.02, mom3=-0.02, mom12=-0.02)
    assert get_signal(df) == FLAT, 'mom=-0.02 exactly must abstain (rule is `< -0.02`)'

  # --- get_latest_indicators shape + type contract (D-08, REVIEWS POLISH) ---

  def test_get_latest_indicators_returns_expected_keys(self) -> None:
    '''D-08: get_latest_indicators returns dict with 8 specific lowercase keys.'''
    from signal_engine import compute_indicators, get_latest_indicators
    fixture = _load_fixture('axjo_400bar')
    out = compute_indicators(fixture)
    latest = get_latest_indicators(out)
    assert set(latest.keys()) == {'atr', 'adx', 'pdi', 'ndi', 'mom1', 'mom3', 'mom12', 'rvol'}

  def test_get_latest_indicators_values_are_python_float(self) -> None:
    '''REVIEWS POLISH (Gemini + Codex): every returned scalar is Python `float`,
    not numpy.float64 -- so downstream JSON serialisation (Phase 3+) never sees
    numpy scalar types.'''
    from signal_engine import compute_indicators, get_latest_indicators
    fixture = _load_fixture('axjo_400bar')
    latest = get_latest_indicators(compute_indicators(fixture))
    for k, v in latest.items():
      assert type(v) is float, (
        f'{k}: type is {type(v).__name__}, expected Python float (not numpy.float64)'
      )

  def test_get_latest_indicators_preserves_nan_as_float_nan(self) -> None:
    '''REVIEWS POLISH (Codex): NaN values are preserved as float("nan"),
    NOT converted to None. Callers use math.isnan() / pd.isna() to check.'''
    import math

    from signal_engine import compute_indicators, get_latest_indicators
    # Pick a fixture guaranteed to have NaN at last-bar ADX: warmup_nan_adx_flat (30 bars)
    fixture = _load_fixture('scenario_warmup_nan_adx_flat')
    latest = get_latest_indicators(compute_indicators(fixture))
    assert latest['adx'] is not None, 'NaN must be preserved as float, not None'
    assert isinstance(latest['adx'], float), 'NaN should be a float, not None'
    assert math.isnan(latest['adx']), (
      f'Expected float("nan") for ADX at warmup last bar, got {latest["adx"]}'
    )
