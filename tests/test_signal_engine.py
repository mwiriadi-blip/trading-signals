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
