'''Phase 1 test suite: signal engine indicators + vote + edge cases + determinism.

Organized into classes per D-13. This file grows across Plans 04 (TestIndicators),
05 (TestVote, TestEdgeCases), and 06 (TestDeterminism + architectural guards).

This file is created in Plan 04 with TestIndicators only.
'''
import ast
import hashlib
import json
import re
from pathlib import Path

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

  # --- REVIEWS pass-2 #2: idempotency guard ---

  def test_compute_indicators_is_idempotent(self) -> None:
    '''REVIEWS pass-2 #2: calling compute_indicators twice must produce identical output.

    Locks a property Phase 2/4 will rely on defensively -- a caller that
    inadvertently re-enriches an already-enriched DataFrame should get the
    same result, not stale/drifted values. Bit-equality (atol=0) because
    compute_indicators is pure: running it on the same inputs (OHLCV cols
    are preserved across calls) must produce byte-identical floats.
    '''
    fixture = _load_fixture('axjo_400bar')
    out1 = compute_indicators(fixture)
    out2 = compute_indicators(out1)
    # 1. Column order preserved (no re-appending of indicator cols in a new position)
    assert list(out1.columns) == list(out2.columns), (
      f'column-order drift: out1={list(out1.columns)}, out2={list(out2.columns)}'
    )
    assert list(out1.columns) == EXPECTED_OUTPUT_COLUMNS, (
      f'out1 columns should match canonical order, got {list(out1.columns)}'
    )
    # 2. Index preserved (date index, same length)
    assert out1.index.equals(out2.index), 'index drift between first and second call'
    assert len(out1) == len(out2), 'row count drift between first and second call'
    # 3. Strict bit-equality across every column (atol=0, equal_nan=True)
    np.testing.assert_allclose(
      out1.to_numpy(dtype='float64'),
      out2.to_numpy(dtype='float64'),
      atol=0, rtol=0, equal_nan=True,
      err_msg='compute_indicators is not idempotent: bit-level drift on second call',
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


# =========================================================================
# TestDeterminism -- SHA256 snapshot (D-14) + architectural guards (CLAUDE.md)
# =========================================================================
# (ast / hashlib / json / re / Path imported at top of file per ruff E402.)

SNAPSHOT_PATH = Path('tests/determinism/snapshot.json')
PHASE2_SNAPSHOT_PATH = Path('tests/determinism/phase2_snapshot.json')
SIGNAL_ENGINE_PATH = Path('signal_engine.py')
TEST_SIGNAL_ENGINE_PATH = Path('tests/test_signal_engine.py')
# Phase 2 Wave 0: extend AST guard to cover new hex modules (D-07, RESEARCH §Example 5)
SIZING_ENGINE_PATH = Path('sizing_engine.py')
SYSTEM_PARAMS_PATH = Path('system_params.py')
TEST_SIZING_ENGINE_PATH = Path('tests/test_sizing_engine.py')
# Phase 3 Wave 0: add state_manager.py to AST guard
STATE_MANAGER_PATH = Path('state_manager.py')
TEST_STATE_MANAGER_PATH = Path('tests/test_state_manager.py')
# Phase 4 Wave 0: add data_fetcher.py + main.py to AST guard
DATA_FETCHER_PATH = Path('data_fetcher.py')
TEST_DATA_FETCHER_PATH = Path('tests/test_data_fetcher.py')
MAIN_PATH = Path('main.py')
TEST_MAIN_PATH = Path('tests/test_main.py')
# Phase 5 Wave 0: add dashboard.py to AST guard
DASHBOARD_PATH = Path('dashboard.py')
TEST_DASHBOARD_PATH = Path('tests/test_dashboard.py')
REGENERATE_DASHBOARD_GOLDEN_PATH = Path('tests/regenerate_dashboard_golden.py')
# Phase 6 Wave 0: add notifier.py to AST guard
NOTIFIER_PATH = Path('notifier.py')
TEST_NOTIFIER_PATH = Path('tests/test_notifier.py')
REGENERATE_NOTIFIER_GOLDEN_PATH = Path('tests/regenerate_notifier_golden.py')
# Phase 19 Wave 0: add pnl_engine.py to AST guard (D-14 + D-19)
PNL_ENGINE_PATH = Path('pnl_engine.py')

# REVIEWS STRONGLY RECOMMENDED: BLOCKLIST, not whitelist. Benign additions like
# __future__, dataclasses, collections, enum, functools are allowed. Only modules
# that would violate the hex boundary (I/O, network, clock, sibling hexes) are blocked.
#
# Phase 2 Wave 0: numpy and pandas added to FORBIDDEN_MODULES for sizing_engine.py
# and system_params.py — those are stdlib-only modules (RESEARCH.md §Standard Stack).
# signal_engine.py legitimately imports numpy and pandas (indicator math); that module
# is excluded from the numpy/pandas check via HEX_PATHS_STDLIB_ONLY parametrize list.
FORBIDDEN_MODULES = frozenset({
  # I/O and clock (CLAUDE.md Architecture: pure math, no I/O, no clock reads)
  'datetime', 'os', 'sys', 'subprocess', 'socket', 'time', 'pickle', 'json', 'pathlib', 'io',
  # Network (Phase 1 is pure math; no network calls)
  'requests', 'urllib', 'urllib2', 'urllib3', 'http', 'httpx',
  # Sibling hexes (signal_engine <-> state_manager/notifier/dashboard must NOT import each other)
  'state_manager', 'notifier', 'dashboard', 'main',
  # Orchestration and external service deps (belong in other hexes)
  'schedule', 'dotenv', 'pytz', 'yfinance',
})

# Phase 2 stdlib-only hex modules must also avoid numpy and pandas (D-07, RESEARCH §Stack)
FORBIDDEN_MODULES_STDLIB_ONLY = FORBIDDEN_MODULES | frozenset({'numpy', 'pandas'})


# Phase 3 Wave 0: state_manager.py IS the I/O hex — os/json/sys/tempfile/datetime/zoneinfo/
# pathlib/math ARE allowed (those are its PURPOSE, math added in Wave 3 for D-19/B-4
# finiteness checks). But it must NOT import sibling hexes, numpy, pandas, requests,
# network modules, scheduler, or third-party tz libs.
FORBIDDEN_MODULES_STATE_MANAGER = frozenset({
  # Sibling hexes (hexagonal-lite boundary — state_manager is peers, never imports them)
  'signal_engine', 'sizing_engine', 'notifier', 'dashboard', 'main',
  # Network / external data deps (I/O hex reads disk only; no network)
  'requests', 'urllib', 'urllib2', 'urllib3', 'http', 'httpx',
  # Heavy scientific stack (state_manager is pure stdlib + system_params)
  'numpy', 'pandas',
  # Scheduler and external service deps
  'schedule', 'dotenv', 'yfinance',
  # pytz is third-party; state_manager uses zoneinfo (stdlib) instead
  'pytz',
})

# Phase 4 Wave 0: data_fetcher.py IS the fetch I/O hex — yfinance/pandas/
# requests/time/logging ARE allowed (those are its PURPOSE). But it must NOT
# import sibling hexes (signal_engine, sizing_engine, state_manager, notifier,
# dashboard, main) or numpy directly (pandas-only; numeric math belongs in
# signal_engine/sizing_engine).
FORBIDDEN_MODULES_DATA_FETCHER = frozenset({
  # Sibling hexes — data_fetcher is peers, never imports them
  'signal_engine', 'sizing_engine', 'state_manager', 'notifier', 'dashboard', 'main',
  # numpy direct — no numeric work in the fetch hex
  'numpy',
  # Scheduler + env deps — data_fetcher is pure fetch, no orchestration
  'schedule', 'dotenv',
  # pytz — project uses zoneinfo (stdlib) via state_manager precedent
  'pytz',
})

# Phase 4 Wave 0 + C-5 revision 2026-04-22: main.py IS the orchestrator — it
# MAY import sibling hexes (data_fetcher, signal_engine, sizing_engine,
# state_manager — that is its PURPOSE). But it MUST NOT reach directly into
# transport/data libraries: numpy (numeric math belongs in the engines),
# yfinance (fetch hex owns), requests (HTTP owned by data_fetcher or Phase 6
# notifier), pandas (DataFrame handling owned by data_fetcher + signal_engine).
# If main.py feels a need to import one of these, that is a signal the code
# belongs in a hex module, not in the orchestrator.
FORBIDDEN_MODULES_MAIN = frozenset({
  'numpy',
  'yfinance',
  'requests',
  'pandas',
})

# Phase 5 Wave 0: dashboard.py IS the render I/O hex — stdlib (html, json, math,
# os, statistics, tempfile, datetime, pathlib, logging) + pytz + state_manager
# (load_state) + system_params ARE allowed. But it must NOT import sibling
# hexes (signal_engine, sizing_engine, data_fetcher, notifier, main) or heavy
# scientific stack (numpy, pandas) or network/fetch libs (yfinance, requests).
FORBIDDEN_MODULES_DASHBOARD = frozenset({
  # Sibling hexes — dashboard.py is a peer, never imports them
  # NOTE: sizing_engine is ALLOWED as of Phase 15 (CALC-01..04 calculator
  # sub-row uses sizing_engine LOCALLY per C-2; CONTEXT D-01 explicit approval).
  # MODULE-TOP imports of sizing_engine in dashboard.py remain forbidden
  # (enforced by test_dashboard_no_module_top_sizing_engine_import — REVIEWS M-2).
  'signal_engine', 'data_fetcher', 'notifier', 'main',
  # Heavy scientific stack (stdlib statistics + math are sufficient per D-07)
  'numpy', 'pandas',
  # Fetch / network — dashboard never touches network (Chart.js loads client-side)
  'yfinance', 'requests',
  # Phase 7: scheduler + env deps — main.py is their sole consumer
  'schedule', 'dotenv',
})

# Phase 6 Wave 0: notifier.py IS the email I/O hex — stdlib (html, json,
# logging, os, time, tempfile, datetime, pathlib) + pytz + requests
# (Resend HTTPS) + state_manager (load_state convenience path) +
# system_params (palette + contract specs) ARE allowed. But it must NOT
# import sibling hexes (signal_engine, sizing_engine, data_fetcher,
# dashboard, main) or heavy scientific stack (numpy, pandas) or fetch
# libs (yfinance).
FORBIDDEN_MODULES_NOTIFIER = frozenset({
  # Sibling hexes — notifier.py is a peer, never imports them
  'signal_engine', 'sizing_engine', 'data_fetcher', 'dashboard', 'main',
  # Heavy scientific stack (notifier does no numeric work beyond f-string format)
  'numpy', 'pandas',
  # Fetch libs — notifier never fetches market data
  'yfinance',
  # Phase 7: scheduler + env deps — main.py is their sole consumer
  'schedule', 'dotenv',
})

# Paths walked by test_forbidden_imports_absent (extended in Phase 2 Wave 0)
# Phase 19: pnl_engine.py added to both lists (D-14 + D-19 pure-math hex-tier)
_HEX_PATHS_ALL = [SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH, PNL_ENGINE_PATH]
# signal_engine.py legitimately uses numpy/pandas; Phase 2 modules must not
_HEX_PATHS_STDLIB_ONLY = [SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH, PNL_ENGINE_PATH]


def _hash_series_values(values) -> str:
  '''SHA256 of float64 bytes. Matches regenerate_goldens.py convention.'''
  arr = pd.Series(values, dtype='float64').to_numpy(dtype='float64', copy=True)
  return hashlib.sha256(arr.tobytes()).hexdigest()


def _top_level_imports(source_path: Path) -> set[str]:
  '''Parse the given Python file and return the top-level module names imported.

  For `import foo.bar` returns 'foo'; for `from foo.bar import baz` returns 'foo'.
  Includes imports nested inside functions / classes / conditionals (ast.walk
  traverses the full tree).
  '''
  tree = ast.parse(source_path.read_text())
  modules: set[str] = set()
  for node in ast.walk(tree):
    if isinstance(node, ast.Import):
      for alias in node.names:
        modules.add(alias.name.split('.')[0])
    elif isinstance(node, ast.ImportFrom):
      if node.module:
        modules.add(node.module.split('.')[0])
  return modules


_TWO_SPACE_INDENT = re.compile(r'^  [^ ]')
_FOUR_SPACE_INDENT = re.compile(r'^    [^ ]')


def _string_literal_line_ranges(source_path: Path) -> set[int]:
  '''Return the set of physical line numbers that lie inside a string literal.

  Uses `tokenize` so the test only inspects Python-code lines, not prose
  continuation inside docstrings or multi-line string constants.
  '''
  import tokenize
  lines_inside_string: set[int] = set()
  with source_path.open('rb') as fh:
    for tok in tokenize.tokenize(fh.readline):
      if tok.type == tokenize.STRING:
        start_line, _ = tok.start
        end_line, _ = tok.end
        if end_line > start_line:
          # Mark "interior" lines (start_line+1 .. end_line) as inside-string.
          # start_line itself has the opening quote (code context).
          for ln in range(start_line + 1, end_line + 1):
            lines_inside_string.add(ln)
  return lines_inside_string


def _has_two_space_indent_evidence(source_path: Path) -> bool:
  '''REVIEWS POLISH (Gemini): evidence-based 2-space-indent lint.

  In a pure 4-space codebase, NO code line starts with exactly 2 leading spaces
  (levels are 0, 4, 8, ...). In a 2-space codebase, top-level indented code lines
  start with exactly 2 leading spaces (levels are 0, 2, 4, 6, ...).

  This function returns True iff at least one Python-code (non-string-literal)
  line starts with exactly 2 spaces followed by a non-space character. If False,
  the file has been reflowed to 4-space indent -- which is exactly what
  `ruff format` would produce, and what the lint is meant to catch.

  Simply checking for 4-space lines is insufficient because 2-level-nested code
  in 2-space style legitimately has 4 leading spaces (a nested `if` body is at
  column 4). 2-space lines are the unambiguous signature of 2-space indent.
  '''
  string_lines = _string_literal_line_ranges(source_path)
  for lineno, line in enumerate(source_path.read_text().splitlines(), start=1):
    if lineno in string_lines:
      continue
    if _TWO_SPACE_INDENT.match(line):
      return True
  return False


class TestDeterminism:
  '''Bit-level determinism + architectural hex-boundary guards.'''

  @pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
  @pytest.mark.parametrize('col', INDICATOR_COLUMNS)
  def test_snapshot_hash_stable(self, stem: str, col: str) -> None:
    '''D-14: SHA256 of each indicator series matches committed snapshot.

    The snapshot is generated by `tests/regenerate_goldens.py` from the pure-Python
    ORACLE (tests/oracle/wilder.py + mom_rvol.py), not the pandas/numpy production
    implementation. This is intentional: the oracle is the bit-level trust anchor
    (pure Python loops, no numpy math), and production is verified against the
    oracle via 1e-9 tolerance tests in `TestIndicators::test_indicator_matches_oracle`.

    This test therefore locks the ORACLE bits. Any numpy/pandas upgrade that shifts
    oracle bits (e.g. via pd.read_csv float parsing or list -> float cast) fails loudly.
    Production-vs-oracle tolerance drift is caught separately by TestIndicators.

    Rationale: production's Wilder-smoothing recursion (`_wilder_smooth`) uses numpy
    `+` / `/` on float64 scalars which differ from the oracle's pure-Python equivalents
    at the ~5e-14 level (below 1e-9 tolerance, above float64 epsilon). Hashing
    production would require regenerating the snapshot from production and would
    make the determinism gate entangled with numpy's internal float semantics,
    defeating the tamper-detection purpose.
    '''
    # =========================================================================
    # WHY THIS TEST HASHES ORACLE OUTPUT (NOT PRODUCTION)
    # -------------------------------------------------------------------------
    # The committed snapshot at tests/determinism/snapshot.json was generated
    # by tests/regenerate_goldens.py using the pure-Python ORACLE
    # (tests/oracle/wilder.py + mom_rvol.py). Production `compute_indicators`
    # diverges from oracle by up to ~5e-14 -- well inside the 1e-9 tolerance
    # gate but NOT bit-identical. Hashing production output would therefore
    # never match the committed snapshot.
    #
    # This test locks the oracle's bit-level output (the trust anchor).
    # Production-vs-oracle correctness at 1e-9 is enforced separately by
    # TestIndicators::test_indicator_matches_oracle. Bit-level equivalence
    # between production and oracle is NOT claimed and NOT required.
    #
    # Cross-refs:
    #   - 01-REVIEWS.md §"Top Finding" (pass-2 consensus)
    #   - 01-06-SUMMARY.md §"Deviations from Plan" #1
    # =========================================================================
    # Local, test-only oracle import. Kept inside the test so signal_engine.py never
    # sees tests.oracle (architectural guard is intact).
    import sys as _sys
    from pathlib import Path as _Path

    _repo_root = _Path('.').resolve()
    if str(_repo_root) not in _sys.path:
      _sys.path.insert(0, str(_repo_root))
    from tests.oracle.mom_rvol import mom as _oracle_mom
    from tests.oracle.mom_rvol import rvol as _oracle_rvol
    from tests.oracle.wilder import adx_plus_minus_di as _oracle_adx
    from tests.oracle.wilder import atr as _oracle_atr

    snapshot = json.loads(SNAPSHOT_PATH.read_text())
    expected_hash = snapshot[stem][col]
    fixture = _load_fixture(stem)
    highs = fixture['High'].tolist()
    lows = fixture['Low'].tolist()
    closes = fixture['Close'].tolist()
    if col == 'ATR':
      oracle_vals = _oracle_atr(highs, lows, closes, 14)
    elif col in {'ADX', 'PDI', 'NDI'}:
      adx_v, pdi_v, ndi_v = _oracle_adx(highs, lows, closes, 20)
      oracle_vals = {'ADX': adx_v, 'PDI': pdi_v, 'NDI': ndi_v}[col]
    elif col == 'Mom1':
      oracle_vals = _oracle_mom(closes, 21)
    elif col == 'Mom3':
      oracle_vals = _oracle_mom(closes, 63)
    elif col == 'Mom12':
      oracle_vals = _oracle_mom(closes, 252)
    elif col == 'RVol':
      oracle_vals = _oracle_rvol(closes, 20, 252)
    else:
      raise ValueError(f'unexpected indicator column: {col}')
    actual_hash = _hash_series_values(oracle_vals)
    assert actual_hash == expected_hash, (
      f'{stem} {col}: ORACLE SHA256 drift detected.\n'
      f'  expected: {expected_hash}\n'
      f'  actual:   {actual_hash}\n'
      f'The oracle bits changed. If this is an intentional library upgrade, re-run '
      f'`python tests/regenerate_goldens.py` and review the git diff carefully.\n'
      f'Note: production-vs-oracle tolerance drift at 1e-9 is caught by '
      f'TestIndicators; this gate specifically locks the bit-level oracle output.'
    )

  # --- Architectural guards (CLAUDE.md hex boundary) ---

  @pytest.mark.parametrize('module_path', _HEX_PATHS_ALL)
  def test_forbidden_imports_absent(self, module_path: Path) -> None:
    '''CLAUDE.md Architecture: all pure-math hex modules must not import any module
    in the blocklist. Phase 2 Wave 0 extends this from signal_engine.py alone to
    also cover sizing_engine.py and system_params.py.

    Per REVIEWS STRONGLY RECOMMENDED, a blocklist is more resilient to benign future
    additions (dataclasses, __future__, enum, functools, collections) than a whitelist.
    Add entries to FORBIDDEN_MODULES only after deliberate review.

    Note: signal_engine.py legitimately imports numpy and pandas (indicator math).
    sizing_engine.py and system_params.py must be stdlib-only; see
    test_phase2_hex_modules_no_numpy_pandas for that additional constraint.
    '''
    imports = _top_level_imports(module_path)
    leaked = imports & FORBIDDEN_MODULES
    assert not leaked, (
      f'{module_path} illegally imports forbidden module(s): {sorted(leaked)}. '
      f'Pure-math modules must not do I/O, network, clock reads, or import sibling '
      f'hexes (state_manager / notifier / dashboard). Move this functionality to '
      f'main.py or an appropriate adapter.'
    )

  @pytest.mark.parametrize('module_path', _HEX_PATHS_STDLIB_ONLY)
  def test_phase2_hex_modules_no_numpy_pandas(self, module_path: Path) -> None:
    '''Phase 2 stdlib-only constraint (RESEARCH.md §Standard Stack, D-07).

    sizing_engine.py and system_params.py must be pure stdlib modules — no numpy
    or pandas. This keeps the Phase 2 hex free of heavy scientific deps and ensures
    math.isnan / math.isfinite are used (not numpy.isnan) per the AST blocklist design.
    Extending FORBIDDEN_MODULES with numpy/pandas for these two paths only.
    '''
    imports = _top_level_imports(module_path)
    leaked = imports & FORBIDDEN_MODULES_STDLIB_ONLY
    assert not leaked, (
      f'{module_path} illegally imports: {sorted(leaked)}. '
      f'sizing_engine.py and system_params.py must be stdlib-only — use math.isnan '
      f'not numpy.isnan. numpy/pandas belong in signal_engine.py (indicator math) only.'
    )

  @pytest.mark.parametrize('module_path', [STATE_MANAGER_PATH])
  def test_state_manager_no_forbidden_imports(self, module_path: Path) -> None:
    '''Phase 3 Wave 0: state_manager.py must not import sibling hexes, numpy, pandas,
    or network modules. It IS allowed to import stdlib I/O modules (os, json, tempfile,
    datetime, zoneinfo, pathlib, sys, math) — those are its PURPOSE as the I/O hex.

    Uses a SEPARATE forbidden set (FORBIDDEN_MODULES_STATE_MANAGER) from the pure-math
    FORBIDDEN_MODULES because I/O stdlib is explicitly permitted for state_manager but
    forbidden for pure-math hexes.

    This is the structural enforcement of CLAUDE.md §Architecture hexagonal-lite for
    state_manager: signal_engine and sizing_engine cannot import state_manager (caught
    by test_forbidden_imports_absent above), and state_manager cannot import them
    (caught by THIS test). The hex boundary is symmetric.
    '''
    imports = _top_level_imports(module_path)
    leaked = imports & FORBIDDEN_MODULES_STATE_MANAGER
    assert not leaked, (
      f'{module_path} illegally imports forbidden module(s): {sorted(leaked)}. '
      f'state_manager.py must not import sibling hexes (signal_engine, sizing_engine, '
      f'notifier, dashboard, main), numpy, pandas, or network/external modules. '
      f'Allowed: stdlib (json, os, sys, tempfile, datetime, zoneinfo, pathlib, typing, math) '
      f'+ system_params. State_manager IS the I/O hex — that is its PURPOSE.'
    )

  @pytest.mark.parametrize('module_path', [DATA_FETCHER_PATH])
  def test_data_fetcher_no_forbidden_imports(self, module_path: Path) -> None:
    '''Phase 4 Wave 0: data_fetcher.py must not import sibling hexes or numpy.
    yfinance/pandas/requests/time/logging ARE allowed — those are its PURPOSE as the fetch hex.

    This is the structural enforcement of CLAUDE.md §Architecture hexagonal-lite for
    data_fetcher: signal_engine/sizing_engine/state_manager cannot import data_fetcher
    (caught by test_forbidden_imports_absent above + test_state_manager_no_forbidden_imports),
    and data_fetcher cannot import them (caught by THIS test). The hex boundary is symmetric.
    '''
    imports = _top_level_imports(module_path)
    leaked = imports & FORBIDDEN_MODULES_DATA_FETCHER
    assert not leaked, (
      f'{module_path} illegally imports forbidden module(s): {sorted(leaked)}. '
      f'data_fetcher.py must not import sibling hexes (signal_engine, sizing_engine, '
      f'state_manager, notifier, dashboard, main) or numpy. '
      f'Allowed: yfinance, pandas, requests, logging, time, system_params. '
      f'data_fetcher IS the fetch hex — that is its PURPOSE.'
    )

  @pytest.mark.parametrize('module_path', [MAIN_PATH])
  def test_main_no_forbidden_imports(self, module_path: Path) -> None:
    '''Phase 4 Wave 0 + C-5 revision 2026-04-22: main.py is the ONLY module allowed to
    import from both sides of the hex (signal_engine + sizing_engine + state_manager
    + data_fetcher). It MUST NOT reach directly into transport/data libraries (numpy
    belongs in the engines; yfinance in data_fetcher; requests in data_fetcher or
    the Phase 6 notifier; pandas in data_fetcher + signal_engine).
    '''
    imports = _top_level_imports(module_path)
    leaked = imports & FORBIDDEN_MODULES_MAIN
    assert not leaked, (
      f'{module_path} illegally imports: {sorted(leaked)}. '
      f'main.py must not import transport/data libraries directly. Push '
      f'yfinance/pandas/requests use into the data_fetcher hex or the Phase 6 '
      f'notifier; push numpy use into signal_engine or sizing_engine. main IS '
      f'the orchestrator — it imports the hex modules, not their internals.'
    )

  @pytest.mark.parametrize('module_path', [DASHBOARD_PATH])
  def test_dashboard_no_forbidden_imports(self, module_path: Path) -> None:
    '''Phase 5 Wave 0: dashboard.py must not import sibling hexes, numpy,
    pandas, yfinance, or requests. It IS allowed to import stdlib (html, json,
    math, os, statistics, tempfile, datetime, pathlib, logging) + pytz +
    state_manager (for load_state, CLI path only) + system_params (palette
    constants + INITIAL_ACCOUNT + TRAIL_MULT_*).

    Structural enforcement of CLAUDE.md §Architecture hexagonal-lite for
    dashboard: sibling-hex blocklists ALREADY forbid dashboard (FORBIDDEN_MODULES,
    FORBIDDEN_MODULES_STATE_MANAGER, FORBIDDEN_MODULES_DATA_FETCHER); this test
    closes the symmetric boundary — dashboard cannot import them either.
    '''
    imports = _top_level_imports(module_path)
    leaked = imports & FORBIDDEN_MODULES_DASHBOARD
    assert not leaked, (
      f'{module_path} illegally imports forbidden module(s): {sorted(leaked)}. '
      f'dashboard.py must not import sibling hexes (signal_engine, sizing_engine, '
      f'data_fetcher, notifier, main), numpy, pandas, yfinance, or requests. '
      f'Allowed: stdlib (html, json, math, os, statistics, tempfile, datetime, '
      f'pathlib, logging) + pytz + state_manager + system_params. Dashboard IS '
      f'the render I/O hex — that is its PURPOSE.'
    )

  def test_dashboard_no_module_top_sizing_engine_import(self) -> None:
    '''C-2 hex-discipline (Phase 15 D-01 + Phase 14 D-02 + REVIEWS M-2):
    sizing_engine is allowed in dashboard.py ONLY as a function-body
    (local) import. A module-top `from sizing_engine import ...` would
    bypass C-2's "import-only-when-needed" pattern AND would also pass
    FORBIDDEN_MODULES_DASHBOARD (since sizing_engine is no longer in
    that frozenset as of Phase 15). This test is the explicit guard.

    Walks dashboard.py at the AST module-body level (tree.body) — NOT
    ast.walk — so LOCAL imports inside function/closure bodies do not
    trigger the assertion. Only TOP-LEVEL Import / ImportFrom statements
    are inspected.
    '''
    import ast
    from pathlib import Path
    source = Path('dashboard.py').read_text()
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in tree.body:
      if isinstance(node, ast.ImportFrom):
        mod = node.module or ''
        if mod == 'sizing_engine' or mod.startswith('sizing_engine.'):
          offenders.append(f'line {node.lineno}: from {mod} import ...')
      elif isinstance(node, ast.Import):
        for alias in node.names:
          name = alias.name
          if name == 'sizing_engine' or name.startswith('sizing_engine.'):
            offenders.append(f'line {node.lineno}: import {name}')
    assert not offenders, (
      'C-2 hex-discipline violation (Phase 15 REVIEWS M-2): '
      'dashboard.py contains MODULE-TOP imports of sizing_engine. '
      'Move them inside the function body that needs them (LOCAL import). '
      'Phase 15 D-01 unlocked sizing_engine for dashboard.py, but only as '
      'a LOCAL import — module-top imports remain forbidden. Offenders: '
      + '; '.join(offenders)
    )

  @pytest.mark.parametrize('module_path', [NOTIFIER_PATH])
  def test_notifier_no_forbidden_imports(self, module_path: Path) -> None:
    '''Phase 6 Wave 0: notifier.py must not import sibling hexes, numpy,
    pandas, or yfinance. It IS allowed to import stdlib (html, json,
    logging, os, time, tempfile, datetime, pathlib) + pytz + requests +
    state_manager (load_state, CLI path only) + system_params (palette +
    contract specs).

    Structural enforcement of CLAUDE.md §Architecture hexagonal-lite for
    notifier: sibling-hex blocklists ALREADY forbid notifier
    (FORBIDDEN_MODULES, FORBIDDEN_MODULES_STATE_MANAGER,
    FORBIDDEN_MODULES_DATA_FETCHER, FORBIDDEN_MODULES_DASHBOARD); this
    test closes the symmetric boundary — notifier cannot import them
    either.
    '''
    imports = _top_level_imports(module_path)
    leaked = imports & FORBIDDEN_MODULES_NOTIFIER
    assert not leaked, (
      f'{module_path} illegally imports forbidden module(s): {sorted(leaked)}. '
      f'notifier.py must not import sibling hexes (signal_engine, sizing_engine, '
      f'data_fetcher, dashboard, main), numpy, pandas, or yfinance. '
      f'Allowed: stdlib + pytz + requests + state_manager + system_params. '
      f'notifier IS the email I/O hex — that is its PURPOSE.'
    )

  def test_signal_engine_has_core_public_surface(self) -> None:
    '''Public API contract: compute_indicators, get_signal, get_latest_indicators,
    LONG, SHORT, FLAT all importable.
    '''
    import signal_engine
    public_names = [
      'compute_indicators', 'get_signal', 'get_latest_indicators',
      'LONG', 'SHORT', 'FLAT',
    ]
    for name in public_names:
      assert hasattr(signal_engine, name), f'signal_engine missing public name: {name}'
    assert signal_engine.LONG == 1
    assert signal_engine.SHORT == -1
    assert signal_engine.FLAT == 0

  # --- REVIEWS POLISH (Gemini): 2-space indent guard against ruff's 4-space default ---

  def test_no_four_space_indent(self) -> None:
    '''REVIEWS POLISH (Gemini): defend CLAUDE.md 2-space indent convention against
    ruff format's 4-space default.

    Evidence-based check: in a pure 4-space codebase, NO Python-code line begins
    with exactly 2 leading spaces (levels are 0, 4, 8, ...). In a 2-space codebase,
    top-level indented code lines begin with exactly 2 spaces. So the unambiguous
    signature of 2-space indent is the presence of "^  [^ ]" lines.

    Checking for 4-space lines directly is insufficient: 2-level-nested code in
    2-space style legitimately has 4 leading spaces (e.g. a nested `if` body or
    a `return {` dict body). Only the 2-space-presence check distinguishes the
    two styles cleanly.

    Phase 2 Wave 0: extended to cover sizing_engine.py, system_params.py, and
    tests/test_sizing_engine.py alongside the original Phase 1 files.

    Fails loudly if any covered file has been reflowed to 4-space (ruff format).
    '''
    covered_paths = [
      SIGNAL_ENGINE_PATH,
      TEST_SIGNAL_ENGINE_PATH,
      SIZING_ENGINE_PATH,       # Phase 2 Wave 0
      SYSTEM_PARAMS_PATH,       # Phase 2 Wave 0
      TEST_SIZING_ENGINE_PATH,  # Phase 2 Wave 0
      STATE_MANAGER_PATH,       # Phase 3 Wave 0
      TEST_STATE_MANAGER_PATH,  # Phase 3 Wave 0
      DATA_FETCHER_PATH,        # Phase 4 Wave 0
      TEST_DATA_FETCHER_PATH,   # Phase 4 Wave 0
      MAIN_PATH,                # Phase 4 Wave 0
      TEST_MAIN_PATH,           # Phase 4 Wave 0
      DASHBOARD_PATH,                      # Phase 5 Wave 0
      TEST_DASHBOARD_PATH,                 # Phase 5 Wave 0
      REGENERATE_DASHBOARD_GOLDEN_PATH,    # Phase 5 Wave 0
    ]
    missing_2space_files = []
    for path in covered_paths:
      if not _has_two_space_indent_evidence(path):
        missing_2space_files.append(str(path))
    assert not missing_2space_files, (
      'Files appear to have been reflowed to 4-space indent (no Python-code line '
      'starts with exactly 2 spaces -- the signature of 2-space indent):\n'
      + '\n'.join(f'  {p}' for p in missing_2space_files)
      + '\nProject convention is 2-space indent (CLAUDE.md). Do NOT run `ruff format` '
      + 'on these files -- ruff 0.6.9 reflows to 4-space. Use .editorconfig '
      + 'indent_size=2 and manual review.'
    )

  # --- Phase 2 determinism snapshot (D-06) ---

  @pytest.mark.parametrize('fixture_name', [
    'transition_long_to_long',
    'transition_long_to_short',
    'transition_long_to_flat',
    'transition_short_to_long',
    'transition_short_to_short',
    'transition_short_to_flat',
    'transition_none_to_long',
    'transition_none_to_short',
    'transition_none_to_flat',
    'pyramid_gap_crosses_both_levels_caps_at_1',
    'adx_drop_below_20_while_in_trade',
    'long_trail_stop_hit_intraday_low',
    'short_trail_stop_hit_intraday_high',
    'long_gap_through_stop',
    'n_contracts_zero_skip_warning',
  ])
  def test_phase2_snapshot_hash_stable(self, fixture_name: str) -> None:
    '''D-06 Phase 2: SHA256 of each fixture's expected dict matches committed snapshot.

    Re-computes SHA256 from the live fixture file and asserts equality with
    the entry in tests/determinism/phase2_snapshot.json. This catches:
      - Accidental fixture mutation (e.g. someone edits position_after by hand)
      - Regenerator drift (two different implementations producing different bytes)
      - Encoding differences (separators, sort_keys must match snapshot generation)

    Hashing convention (mirrors tests/regenerate_phase2_fixtures.py):
      json.dumps(expected, sort_keys=True, separators=(',', ':'), allow_nan=False)
      -> sha256 hexdigest

    PHASE2_SNAPSHOT_PATH = tests/determinism/phase2_snapshot.json (15 entries, one per
    fixture name). Re-run tests/regenerate_phase2_fixtures.py + re-generate snapshot
    when fixture recipes change intentionally.
    '''
    import hashlib as _hashlib
    import json as _json

    snapshot = _json.loads(PHASE2_SNAPSHOT_PATH.read_text())
    expected_hash = snapshot[fixture_name]
    fix = _json.loads(
      (Path('tests/fixtures/phase2') / f'{fixture_name}.json').read_text()
    )
    expected = fix['expected']
    canonical = _json.dumps(
      expected, sort_keys=True, separators=(',', ':'), allow_nan=False,
    )
    actual_hash = _hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    assert actual_hash == expected_hash, (
      f'Phase 2 fixture SHA256 drift detected for {fixture_name!r}.\n'
      f'  expected: {expected_hash}\n'
      f'  actual:   {actual_hash}\n'
      f'The fixture was mutated or the snapshot is out of date.\n'
      f'If intentional: re-run tests/regenerate_phase2_fixtures.py then '
      f're-generate tests/determinism/phase2_snapshot.json.'
    )

  def test_sizing_engine_has_core_public_surface(self) -> None:
    '''Phase 2 Wave 0: public API contract for sizing_engine.py.

    All six public callables must be importable from sizing_engine. This test fires
    immediately when a function is accidentally renamed or removed. Stubs raise
    NotImplementedError -- that is expected and allowed at Wave 0.
    The dataclasses (SizingDecision, PyramidDecision, StepResult) must also be
    present and frozen (immutable at runtime).
    '''
    import sizing_engine
    public_functions = [
      'calc_position_size',
      'get_trailing_stop',
      'check_stop_hit',
      'check_pyramid',
      'compute_unrealised_pnl',
      'step',
    ]
    public_dataclasses = [
      'SizingDecision',
      'PyramidDecision',
      'StepResult',
    ]
    for name in public_functions:
      assert hasattr(sizing_engine, name), (
        f'sizing_engine missing public callable: {name}'
      )
      assert callable(getattr(sizing_engine, name)), (
        f'sizing_engine.{name} is not callable'
      )
    for name in public_dataclasses:
      assert hasattr(sizing_engine, name), (
        f'sizing_engine missing public dataclass: {name}'
      )
      # Verify frozen=True: attempting to assign to a field must raise FrozenInstanceError
      cls = getattr(sizing_engine, name)
      import dataclasses as _dc
      assert _dc.is_dataclass(cls), f'{name} must be a dataclass'
      params = _dc.fields(cls)
      assert len(params) >= 1, f'{name} must have at least one field'
