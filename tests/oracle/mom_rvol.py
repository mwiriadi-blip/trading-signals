'''Pure-Python-loop Mom and RVol oracle per SIG-03, SIG-04.

- mom(closes, lookback): N-day return, NaN for bars 0..lookback-1.
- rvol(closes, period, annualisation_factor): rolling std of daily returns * sqrt(annualisation).
- On bit-identical flat prices, rvol returns 0.0 exactly (D-12).
'''
import math
from typing import Sequence  # noqa: UP035 — AC requires `from typing` import for oracle-purity grep

NaN = float('nan')


def mom(closes: Sequence[float], lookback: int) -> list[float]:
  '''N-day price return: (c[t] - c[t-N]) / c[t-N]. NaN for bars 0..lookback-1.

  If c[t-N] == 0 the result is NaN (let div-by-zero propagate; prices shouldn't be zero).
  '''
  n = len(closes)
  out = [NaN] * n
  for i in range(lookback, n):
    prev = closes[i - lookback]
    if prev == 0.0:
      out[i] = NaN
    else:
      out[i] = (closes[i] - prev) / prev
  return out


def rvol(
  closes: Sequence[float],
  period: int = 20,
  annualisation_factor: int = 252,
) -> list[float]:
  '''Annualised rolling std of daily returns.

  1. daily_ret[t] = (closes[t] - closes[t-1]) / closes[t-1]; daily_ret[0] = NaN.
  2. rvol[t] = stdev(daily_ret[t-period+1 .. t], ddof=1) * sqrt(annualisation_factor)
  3. rvol[0..period-1] = NaN (need `period` non-NaN daily_ret values; since daily_ret[0]
     is NaN, first valid rvol is at bar `period`).

  Matches pandas rolling(period).std() * sqrt(252) convention exactly on bit-identical
  flat inputs (returns 0.0).
  '''
  n = len(closes)
  # daily returns
  ret = [NaN] * n
  for i in range(1, n):
    if closes[i - 1] == 0.0:
      ret[i] = NaN
    else:
      ret[i] = (closes[i] - closes[i - 1]) / closes[i - 1]
  # rolling std with ddof=1
  out = [NaN] * n
  sqrt_ann = math.sqrt(annualisation_factor)
  for i in range(period, n):
    window = ret[i - period + 1 : i + 1]
    # If any window value is NaN, result is NaN (covers warmup at index `period-1`).
    if any(math.isnan(v) for v in window):
      out[i] = NaN
      continue
    mean = sum(window) / period
    # Sample std (ddof=1). On bit-identical flat prices => returns 0 => mean 0 =>
    # sum of sq dev 0 => 0.0 exactly.
    sq_dev = sum((v - mean) ** 2 for v in window)
    variance = sq_dev / (period - 1)
    out[i] = math.sqrt(variance) * sqrt_ann
  return out
