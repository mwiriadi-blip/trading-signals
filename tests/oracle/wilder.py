'''Pure-Python-loop Wilder oracle for ATR, ADX, +DI, -DI.

Separate from signal_engine.py (SUT) per D-02. No pandas, no numpy, no external TA libs.
Every formula is 3 lines per bar in an obvious for-loop.

Conventions:
  - Bar-0 TR = highs[0] - lows[0] (per R-04; matches pandas skipna=True default).
  - Wilder smoothing seeds at bar period-1 with SMA of first `period` values (per R-01).
  - Seed-window NaN rule: if any of series[i-period+1 : i+1] is NaN, the seed attempt
    at bar `i` fails and output stays NaN. First non-NaN output occurs at the first bar
    where the trailing `period` values are ALL non-NaN.
  - NaN in list positions represents warmup bars.
'''
import math
from typing import Sequence  # noqa: UP035 — AC requires `from typing` import for oracle-purity grep

NaN = float('nan')


def true_range(
  highs: Sequence[float],
  lows: Sequence[float],
  closes: Sequence[float],
) -> list[float]:
  '''TR_t = max(H-L, |H-Cprev|, |L-Cprev|). Bar 0: TR[0] = H[0] - L[0] per R-04.'''
  n = len(highs)
  assert len(lows) == n and len(closes) == n, 'H/L/C length mismatch'
  tr = [NaN] * n
  tr[0] = highs[0] - lows[0]
  for i in range(1, n):
    tr1 = highs[i] - lows[i]
    tr2 = abs(highs[i] - closes[i - 1])
    tr3 = abs(lows[i] - closes[i - 1])
    tr[i] = max(tr1, tr2, tr3)
  return tr


def _wilder_smooth(series: Sequence[float], period: int) -> list[float]:
  '''Wilder smoothing per R-01 + seed-window NaN rule.

  Contract:
    - Bars [0..period-2]: output NaN.
    - Bar `period-1`: output = SMA of series[0:period], ONLY if all values are non-NaN.
    - If ANY NaN is present in the seed window, output stays NaN. The smoothing does
      NOT start until a full `period`-length non-NaN window ends at some bar `i`:
      at that bar, output = SMA of series[i-period+1 : i+1]; from bar `i+1` onward,
      the Wilder recursion applies.
    - Recursion: sm[t] = sm[t-1] + (raw[t] - sm[t-1]) / period
      Equivalent to: sm[t] = (sm[t-1] * (period-1) + raw[t]) / period
    - If any `raw[t]` is NaN once recursion is running, propagate NaN and require a
      fresh `period`-length non-NaN window to re-seed.
  '''
  n = len(series)
  out = [NaN] * n
  if n < period:
    return out
  seeded = False
  for i in range(period - 1, n):
    window = series[i - period + 1 : i + 1]
    if any(math.isnan(v) for v in window):
      # Seed attempt (or continuation) blocked by NaN in the trailing window.
      seeded = False
      continue
    if not seeded:
      # First valid seed window ending at bar i => SMA-seed here.
      out[i] = sum(window) / period
      seeded = True
    else:
      # Wilder recursion
      out[i] = (out[i - 1] * (period - 1) + series[i]) / period
  return out


def atr(
  highs: Sequence[float],
  lows: Sequence[float],
  closes: Sequence[float],
  period: int = 14,
) -> list[float]:
  '''Wilder ATR. First non-NaN at bar period-1 (= bar 13 for period=14).'''
  tr = true_range(highs, lows, closes)
  return _wilder_smooth(tr, period)


def adx_plus_minus_di(
  highs: Sequence[float],
  lows: Sequence[float],
  closes: Sequence[float],
  period: int = 20,
) -> tuple[list[float], list[float], list[float]]:
  '''Wilder ADX with +DI, -DI. First non-NaN ADX at bar 2*period-2 (= bar 38 for period=20).

  Stages per Pattern 2:
    1. TR, +DM, -DM:
       +DM = upMove if (upMove > downMove and upMove > 0) else 0 (mirror for -DM).
       Bar 0 DM = 0.
    2. Wilder-smooth each of TR, +DM, -DM.
    3. +DI = 100 * sm_pDM / sm_TR; -DI mirror;
       DX = 100 * |+DI - -DI| / (+DI + -DI); NaN on div-by-0 per D-11.
    4. ADX = Wilder-smooth(DX)
  '''
  n = len(highs)
  tr = true_range(highs, lows, closes)
  plus_dm = [0.0] * n
  minus_dm = [0.0] * n
  # Bar 0: no diff => DM = 0 (canonical)
  for i in range(1, n):
    up_move = highs[i] - highs[i - 1]
    down_move = lows[i - 1] - lows[i]
    plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
    minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
  sm_tr = _wilder_smooth(tr, period)
  sm_plus_dm = _wilder_smooth(plus_dm, period)
  sm_minus_dm = _wilder_smooth(minus_dm, period)
  plus_di = [NaN] * n
  minus_di = [NaN] * n
  dx = [NaN] * n
  for i in range(n):
    tr_val = sm_tr[i]
    if math.isnan(tr_val) or tr_val == 0.0:
      # D-11: divide-by-zero => NaN propagates
      plus_di[i] = NaN
      minus_di[i] = NaN
      dx[i] = NaN
      continue
    plus_di[i] = 100.0 * sm_plus_dm[i] / tr_val
    minus_di[i] = 100.0 * sm_minus_dm[i] / tr_val
    denom = plus_di[i] + minus_di[i]
    if denom == 0.0:
      dx[i] = NaN
    else:
      dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / denom
  adx = _wilder_smooth(dx, period)
  return adx, plus_di, minus_di
