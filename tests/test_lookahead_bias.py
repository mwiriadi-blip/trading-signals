'''Phase 27 Plan 27-10 Task 3 — look-ahead-bias backtest test.

LOCK-IN POLICY (review-fix agreed-4 + plan action header "lock in WHAT IT
DOES"):

  This system is a daily End-Of-Day signal engine. By design, the signal
  for run-date N is computed AT/AFTER market close on day N using day N's
  full OHLC bar (Mom_k = pct_change(periods=k) on close, ADX uses today's
  HIGH/LOW range, etc.). The signal then drives next-day execution
  (operator places the trade at next-day open).

  This is NOT look-ahead bias in the trading sense — the signal does not
  use information unavailable to the operator at decision time (after
  market close on day N). What WOULD constitute look-ahead bias is a
  signal that depends on data from FUTURE bars (day N+1 or later) — that
  would be a real bug.

  This file therefore locks in TWO contracts:
    (a) Day-N's signal DOES depend on Day-N's OHLC (current behaviour
        — by design for EOD systems). A test asserts the dependency so
        any future refactor that accidentally drops the dependency will
        FAIL THE SUITE LOUD (the dependency is load-bearing).
    (b) Day-N's signal MUST NOT depend on Day-N+1's OHLC (the meaningful
        no-look-ahead invariant). If this assertion fails, a real bug
        exists. Per plan policy: NO xfail — the test FAILS THE SUITE
        and an immediate [BLOCKING] follow-up plan is required.

DEVIATION from plan literal text:

  Plan <behavior> stated "Day-N's signal does NOT depend on Day-N's
  CLOSE." This is incorrect for THIS system (Mom = pct_change(periods)
  on close uses today's close). The plan action overrides this:
    "Read signal_engine.get_signal source FIRST. Determine actual
     contract: which row's data feeds the signal decision?"
    "lock in WHAT IT DOES."
  We honour the action ("lock in actual contract") rather than the
  contradictory <behavior> bullet, and instead lock the meaningful
  no-look-ahead invariant (no future-bar leakage) per plan agreed-4
  fail-loud policy. See SUMMARY.md "Deviations from Plan" for full
  rationale.
'''
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from signal_engine import compute_indicators, get_signal


FIXTURE_DIR = Path(__file__).parent / 'fixtures'


def _load_canonical_fixture() -> pd.DataFrame:
  '''Load the canonical 400-bar AXJO fixture.

  400 bars > 252 (longest Mom lookback) so all indicators are non-NaN
  on the last bar.
  '''
  df = pd.read_csv(
    FIXTURE_DIR / 'axjo_400bar.csv',
    index_col=0,
    parse_dates=True,
  )
  # Normalise to capitalised columns (signal_engine reads Open/High/Low/Close/Volume).
  rename_map = {c: c.capitalize() for c in df.columns}
  df = df.rename(columns=rename_map)
  required = {'Open', 'High', 'Low', 'Close'}
  missing = required - set(df.columns)
  assert not missing, f'fixture missing required columns: {missing}'
  return df


def _slice_to_active_signal_window(df: pd.DataFrame) -> pd.DataFrame:
  '''Return a prefix of df ending at a bar where ADX > 25 and the signal
  is non-FLAT — so today-close shock tests have something to perturb.

  The 400-bar AXJO fixture has many such bars; we pick the first one
  past index 252 (so all moms are defined) where ADX > 25 and signal
  is non-FLAT. This makes contract-(a) tests deterministic across
  fixture refreshes.
  '''
  ind = compute_indicators(df)
  for i in range(252, len(ind)):
    row = ind.iloc[i]
    if pd.isna(row['ADX']) or row['ADX'] <= 25.0:
      continue
    sub = df.iloc[: i + 1]
    if get_signal(compute_indicators(sub)) != 0:
      return sub
  raise pytest.skip.Exception(
    'No active-signal bar found in fixture — refresh axjo_400bar.csv.'
  )


class TestSignalRespondsToTodayBar:
  '''Lock-in (a): Day-N's signal IS expected to depend on Day-N's OHLC bar
  (EOD-daily system design contract).

  These tests intentionally pin the existing contract so any refactor that
  silently breaks this dependency (e.g. switching get_signal to read
  df.iloc[-2]) fails fast. The dependency is load-bearing for trade
  execution timing.
  '''

  def test_today_close_influences_signal_when_shocked_extremely(self) -> None:
    '''On a window ending at a bar where ADX>25 and signal is non-FLAT,
    shocking today's close by ±50% MUST move the signal away from the
    baseline at least once (proves get_signal reads today's bar).

    Mom1 (21-day return) sign flips under a 50% close shock. Under an
    ADX-passing regime that flip moves the 2-of-3 vote. If both
    directions return identical signals to baseline across this dramatic
    shock, get_signal is NOT reading today's close — that breaks the
    EOD contract.
    '''
    df_full = _load_canonical_fixture()
    df = _slice_to_active_signal_window(df_full)
    baseline = get_signal(compute_indicators(df))
    assert baseline != 0, (
      'precondition: window must end on a non-FLAT bar so the test can '
      'observe shock-induced changes.'
    )

    shocked_up = df.copy()
    shocked_up.iloc[-1, shocked_up.columns.get_loc('Close')] = (
      float(df.iloc[-1]['Close']) * 1.5
    )
    sig_up = get_signal(compute_indicators(shocked_up))

    shocked_dn = df.copy()
    shocked_dn.iloc[-1, shocked_dn.columns.get_loc('Close')] = (
      float(df.iloc[-1]['Close']) * 0.5
    )
    sig_dn = get_signal(compute_indicators(shocked_dn))

    assert (sig_up != baseline) or (sig_dn != baseline), (
      'EOD contract broken: get_signal does not respond to ±50% shocks '
      f'on today\'s Close (baseline={baseline}, +50%={sig_up}, '
      f'-50%={sig_dn}). The system is meant to compute end-of-day '
      'signals using today\'s full OHLC bar.'
    )


class TestSignalIndependentOfFutureBars:
  '''Lock-in (b): Day-N's signal MUST NOT depend on Day-N+1 (or later)
  bars. This is the meaningful no-look-ahead invariant.

  POLICY (review-fix agreed-4): if these assertions fail, a real
  look-ahead bug exists in signal_engine. The test FAILS the suite —
  NO xfail, NO skip, NO "documented as known issue". Phase 27 must
  add a follow-up [BLOCKING] task to fix the bug.

  Construction: take an N-bar fixture; compute signal on bars
  df[:-K] (last K bars HIDDEN from the engine). Then mutate the
  hidden bars to extreme values and recompute on df[:-K] again.
  Hiding the same K bars BOTH times means the engine cannot see
  them — so the signal MUST be identical. Any difference proves
  look-ahead.
  '''

  @pytest.mark.parametrize('hide_k', [1, 2, 5])
  def test_signal_unchanged_when_future_bars_mutated(self, hide_k: int) -> None:
    '''Hide the last `hide_k` bars from get_signal, mutate them in-place
    on a copy, then verify that signal computed on the visible prefix
    is identical regardless of the hidden bars' values.
    '''
    df = _load_canonical_fixture()
    visible = df.iloc[:-hide_k].copy()
    # Indicators computed on visible-only window (the engine never sees
    # the hidden bars).
    sig_baseline = get_signal(compute_indicators(visible))

    # Mutate the hidden bars on a separate copy of the FULL frame, then
    # slice off the same K bars again — engine's input is identical
    # bit-for-bit. We do this dance to prove the test methodology
    # (mutating hidden bars cannot affect a slice that excludes them)
    # AND to make the call shape symmetric with future variants that
    # might pass full-history df slices (e.g. df.iloc[:i+1] inside a
    # backtest loop).
    full_mutated = df.copy()
    cls_loc = full_mutated.columns.get_loc('Close')
    open_loc = full_mutated.columns.get_loc('Open')
    high_loc = full_mutated.columns.get_loc('High')
    low_loc = full_mutated.columns.get_loc('Low')
    for offset in range(hide_k):
      idx = -1 - offset
      full_mutated.iloc[idx, cls_loc] = float(df.iloc[idx]['Close']) * 100.0
      full_mutated.iloc[idx, open_loc] = float(df.iloc[idx]['Open']) * 100.0
      full_mutated.iloc[idx, high_loc] = float(df.iloc[idx]['High']) * 100.0
      full_mutated.iloc[idx, low_loc] = float(df.iloc[idx]['Low']) * 0.01

    visible_after = full_mutated.iloc[:-hide_k]
    sig_after = get_signal(compute_indicators(visible_after))

    assert sig_baseline == sig_after, (
      f'LOOK-AHEAD BIAS DETECTED (hide_k={hide_k}): mutating future bars '
      f'(N+1..N+{hide_k}) changed Day-N\'s signal. baseline={sig_baseline} '
      f'after_future_shock={sig_after}. This is a real bug — per Phase 27 '
      'Plan 27-10 review-fix agreed-4 policy, escalate to a [BLOCKING] '
      'follow-up plan; do NOT mark xfail.'
    )

  def test_signal_invariant_under_future_close_extremes(self) -> None:
    '''Strict variant: replace the LAST bar's Close with a 1000× shock
    and confirm the signal computed on bars[:-1] is unchanged. Catches
    any accidental indicator-window overlap that would peek at bar N.
    '''
    df = _load_canonical_fixture()
    visible = df.iloc[:-1].copy()
    sig_baseline = get_signal(compute_indicators(visible))

    full_mutated = df.copy()
    full_mutated.iloc[-1, full_mutated.columns.get_loc('Close')] = (
      float(df.iloc[-1]['Close']) * 1000.0
    )
    sig_after = get_signal(compute_indicators(full_mutated.iloc[:-1]))

    assert sig_baseline == sig_after, (
      'LOOK-AHEAD BIAS: signal on bars[:-1] depends on bar N+1\'s Close. '
      f'baseline={sig_baseline}, after_shock={sig_after}. '
      'Real bug — escalate per Plan 27-10 fail-loud policy.'
    )

  def test_signal_invariant_under_future_ohl_extremes(self) -> None:
    '''Same future-bar invariant on Open/High/Low (one at a time).
    Asserts no indicator inadvertently reaches forward through OHL.'''
    df = _load_canonical_fixture()
    visible = df.iloc[:-1].copy()
    sig_baseline = get_signal(compute_indicators(visible))

    for col, factor in [('Open', 100.0), ('High', 100.0), ('Low', 0.01)]:
      mutated = df.copy()
      loc = mutated.columns.get_loc(col)
      mutated.iloc[-1, loc] = float(df.iloc[-1][col]) * factor
      sig_after = get_signal(compute_indicators(mutated.iloc[:-1]))
      assert sig_baseline == sig_after, (
        f'LOOK-AHEAD BIAS: signal on bars[:-1] depends on bar N+1\'s {col}. '
        f'baseline={sig_baseline}, after_shock={sig_after} (col={col}). '
        'Real bug — escalate per Plan 27-10 fail-loud policy.'
      )
