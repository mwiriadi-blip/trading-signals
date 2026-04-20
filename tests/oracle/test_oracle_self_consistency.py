'''Oracle self-consistency tests. No dependency on signal_engine.py.'''
import math

from tests.oracle.mom_rvol import mom, rvol
from tests.oracle.wilder import (
  _wilder_smooth,
  adx_plus_minus_di,
  atr,
  true_range,
)

HIGHS_5 = [10.5, 11.0, 11.5, 10.8, 11.2]
LOWS_5 = [10.0, 10.3, 10.9, 10.2, 10.7]
CLOSES_5 = [10.2, 10.9, 11.1, 10.5, 11.0]


class TestTrueRange:
  def test_bar_0_is_high_minus_low(self):
    # Per R-04: bar-0 TR uses pandas skipna=True default => high - low
    tr = true_range(HIGHS_5, LOWS_5, CLOSES_5)
    assert abs(tr[0] - 0.5) < 1e-12

  def test_bar_1_uses_max_of_three(self):
    tr = true_range(HIGHS_5, LOWS_5, CLOSES_5)
    # TR[1] = max(11.0-10.3=0.7, |11.0-10.2|=0.8, |10.3-10.2|=0.1) = 0.8
    assert abs(tr[1] - 0.8) < 1e-12

  def test_bar_3_uses_high_minus_prev_close(self):
    tr = true_range(HIGHS_5, LOWS_5, CLOSES_5)
    # TR[3] = max(10.8-10.2=0.6, |10.8-11.1|=0.3, |10.2-11.1|=0.9) = 0.9
    assert abs(tr[3] - 0.9) < 1e-12


class TestATRWarmup:
  def test_atr14_warmup_bars_are_nan(self):
    flat_high = [1.0] * 40
    flat_low = [0.0] * 40
    flat_close = [0.5] * 40
    a = atr(flat_high, flat_low, flat_close, 14)
    for i in range(13):
      assert math.isnan(a[i]), f'bar {i} should be NaN, got {a[i]}'
    assert not math.isnan(a[13]), 'bar 13 must be finite (first non-NaN)'

  def test_atr3_matches_hand_calc_on_5_bars(self):
    a = atr(HIGHS_5, LOWS_5, CLOSES_5, 3)
    # Hand-calc:
    #   TRs = [0.5, 0.8, 0.6, 0.9, 0.7]
    #   ATR[2] = SMA(0.5, 0.8, 0.6) = 0.633333...
    #   ATR[3] = (0.6333*2 + 0.9) / 3 = 0.722222...
    #   ATR[4] = (0.7222*2 + 0.7) / 3 = 0.714814...
    assert math.isnan(a[0]) and math.isnan(a[1])
    assert abs(a[2] - (0.5 + 0.8 + 0.6) / 3) < 1e-12
    assert abs(a[3] - (a[2] * 2 + 0.9) / 3) < 1e-12
    assert abs(a[4] - (a[3] * 2 + 0.7) / 3) < 1e-12


class TestADXWarmup:
  def test_adx20_first_non_nan_at_bar_38(self):
    # Deterministic non-trivial input (linear trend + small oscillation)
    n = 60
    highs = [100.0 + i * 0.5 + (0.1 if i % 2 else -0.1) for i in range(n)]
    lows = [h - 1.0 for h in highs]
    closes = [(hi + lo) / 2 for hi, lo in zip(highs, lows, strict=True)]
    a, p, m = adx_plus_minus_di(highs, lows, closes, 20)
    for i in range(38):
      assert math.isnan(a[i]), f'bar {i}: ADX should be NaN, got {a[i]}'
    assert not math.isnan(a[38]), 'bar 38: ADX must be finite'

  def test_plus_di_minus_di_return_nan_on_flat_prices(self):
    # D-11: flat prices => sum(TR) = 0 => +DI/-DI NaN => ADX NaN
    n = 60
    a, p, m = adx_plus_minus_di([1.0] * n, [1.0] * n, [1.0] * n, 20)
    # After Wilder smoothing of TR (all zero), sm_TR = 0 at bar 19+, so DI = NaN from bar 19+
    assert math.isnan(p[20]) and math.isnan(m[20]) and math.isnan(a[38])


class TestWilderSeedWindowNaNRule:
  '''Per REVIEWS.md MEDIUM: oracle and production must enforce the same rule -
  if any value in the seed window is NaN, _wilder_smooth output stays NaN until
  a full `period`-length non-NaN window is observed.'''

  def test_nan_in_seed_window_produces_all_nan_when_no_valid_window(self):
    # Only 5 values, period 3, first value NaN => valid seed windows exist at indices 2,3,4
    # Wait — first valid window is [1:4] = [1,2,3] ending at index 3.
    # With only 5 total elements [NaN, 1, 2, 3, 4] the windows are:
    #   i=2: [NaN, 1, 2] => NaN
    #   i=3: [1, 2, 3]   => valid; out[3] = 2.0
    #   i=4: [2, 3, 4]   => recursion; out[4] = (2.0*2 + 4)/3 = 2.6667
    out = _wilder_smooth([float('nan'), 1.0, 2.0, 3.0, 4.0], 3)
    assert math.isnan(out[0]) and math.isnan(out[1]) and math.isnan(out[2])
    assert abs(out[3] - 2.0) < 1e-12
    assert abs(out[4] - (2.0 * 2 + 4.0) / 3.0) < 1e-12

  def test_nan_in_seed_window_full_nan_when_window_never_clean(self):
    # period=3 but EVERY 3-window contains NaN => all output NaN
    out = _wilder_smooth([float('nan'), 1.0, float('nan'), 3.0, float('nan')], 3)
    for v in out:
      assert math.isnan(v), f'expected all NaN, got {out}'

  def test_short_series_returns_all_nan(self):
    # len < period => cannot seed at all
    out = _wilder_smooth([1.0, 2.0], 3)
    for v in out:
      assert math.isnan(v)


class TestMom:
  def test_mom_1_returns_percentage_diff(self):
    m = mom([100.0, 101.0, 102.0], 1)
    assert math.isnan(m[0])
    assert abs(m[1] - 0.01) < 1e-12
    assert abs(m[2] - (102.0 - 101.0) / 101.0) < 1e-12

  def test_mom_warmup_is_nan(self):
    m = mom([100.0, 105.0, 110.0], 5)
    assert all(math.isnan(v) for v in m)

  def test_mom_on_flat_prices_is_zero(self):
    m = mom([100.0] * 10, 3)
    for i in range(3):
      assert math.isnan(m[i])
    for i in range(3, 10):
      assert m[i] == 0.0


class TestRVol:
  def test_rvol_warmup_is_nan(self):
    r = rvol([100.0 + i for i in range(50)], 20, 252)
    for i in range(20):
      assert math.isnan(r[i]), f'bar {i}: RVol should be NaN, got {r[i]}'
    assert not math.isnan(r[20])

  def test_rvol_on_flat_prices_is_exactly_zero(self):
    # D-12: bit-identical flat prices => zero std => RVol = 0.0 exactly
    r = rvol([100.0] * 50, 20, 252)
    assert r[20] == 0.0
    assert r[30] == 0.0

  def test_rvol_on_uniform_linear_trend_is_finite_and_positive(self):
    # Non-flat closes => non-zero RVol. A geometric 1.01**i series has constant 1%
    # return ALGEBRAICALLY, but in float64 the compounded values introduce rounding
    # noise, so the std of returns is float-positive (~1e-15), not bit-exact 0.
    # RESEARCH Pitfall 6: only bit-identical closes produce bit-exact 0 RVol (D-12).
    r = rvol([100.0 * (1.01 ** i) for i in range(50)], 20, 252)
    assert not math.isnan(r[20])
    assert r[20] >= 0.0
    assert r[20] < 1e-10  # effectively zero modulo float noise

  def test_rvol_on_alternating_returns_is_positive(self):
    # Alternating +1% / -1% => non-zero return std => non-zero RVol
    closes = [100.0]
    for i in range(1, 50):
      multiplier = 1.01 if i % 2 else 0.99
      closes.append(closes[-1] * multiplier)
    r = rvol(closes, 20, 252)
    assert r[20] > 0.0
