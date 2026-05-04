'''Signal Engine — pure-math indicator library + 2-of-3 momentum vote.

Computes ATR(14), ADX(20) with +DI/-DI, Mom(21/63/252), RVol(20) on an OHLCV
DataFrame and derives a deterministic LONG/SHORT/FLAT signal gated by ADX >= 25.

SIG-01 formula interpretation (R-01): the spec text
"ATR(14) computed via Wilder's ewm(alpha=1/14, adjust=False, min_periods=14)"
is interpreted as intent. The literal pandas one-liner seeds from the first TR
value, which diverges from Wilder canonical by up to 5 units (see
.planning/phases/01-signal-engine-core-indicators-vote/01-RESEARCH.md §Pitfall 1).
This module uses the SMA-seeded ewm idiom to match Wilder canonical to ~1e-14.
See tests/oracle/wilder.py for the pure-loop reference oracle.

Seed-window NaN rule (REVIEWS.md MEDIUM): if any value in the `period`-bar SMA
seed window is NaN, `_wilder_smooth` emits NaN until a full non-NaN seed window
of `period` bars is observed. This matches the oracle's behaviour exactly;
pandas `.mean()` would default to skipna=True and diverge.

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY. No I/O, no network,
no clock reads, no imports of state_manager / notifier / dashboard.
'''
import numpy as np
import pandas as pd

from system_params import (
  ADX_GATE,
  ADX_PERIOD,
  ANNUALISATION_FACTOR,
  ATR_PERIOD,
  MOM_PERIODS,
  MOM_THRESHOLD,
  RVOL_PERIOD,
)

# --- Signal constants (CLAUDE.md) — remain here as signal-encoding primitives (D-01) ---
LONG: int = 1
SHORT: int = -1
FLAT: int = 0


# =========================================================================
# Private helpers (per D-05)
# =========================================================================

def _true_range(df: pd.DataFrame) -> pd.Series:
  '''TR_t = max(H-L, |H - Cprev|, |L - Cprev|).

  Bar 0: Cprev is NaN; pandas max(skipna=True) returns H-L (per R-04), matching
  the oracle's explicit bar-0 convention TR[0] = H[0] - L[0].
  '''
  prev_close = df['Close'].shift(1)
  tr1 = df['High'] - df['Low']
  tr2 = (df['High'] - prev_close).abs()
  tr3 = (df['Low'] - prev_close).abs()
  return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
  '''Wilder smoothing with SMA seed (R-01) + NaN-strict seed window (REVIEWS MEDIUM).

  Contract (matches tests/oracle/wilder.py bit-for-bit):
    - bars [0..period-2]: NaN
    - First bar `i` where series[i-period+1 : i+1] has ZERO NaN values:
      out[i] = mean of that window (SMA seed)
    - bar >= i+1 (recursion): out[t] = out[t-1] + (raw[t] - out[t-1]) / period
    - If NaN appears in the seed window OR in raw[t] during recursion, drop the
      seed and scan forward for the next full non-NaN window of `period` bars
      to re-seed (matches oracle Pitfall 1 / REVIEWS MEDIUM rule).
  '''
  n = len(series)
  values = series.astype('float64').to_numpy(copy=True)
  out = np.full(n, np.nan, dtype='float64')
  if n < period:
    return pd.Series(out, index=series.index, dtype='float64')
  seeded = False
  prev = np.nan
  for i in range(period - 1, n):
    window = values[i - period + 1 : i + 1]
    if np.any(np.isnan(window)):
      # Seed attempt (or continuation) blocked by NaN in the trailing window.
      seeded = False
      continue
    if not seeded:
      # First valid seed window ending at bar i ⇒ SMA seed here.
      prev = float(window.mean())
      out[i] = prev
      seeded = True
    else:
      # Wilder recursion: sm[t] = sm[t-1] + (raw[t] - sm[t-1]) / period
      prev = prev + (values[i] - prev) / period
      out[i] = prev
  return pd.Series(out, index=series.index, dtype='float64')


def _atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
  '''Wilder ATR. First non-NaN at bar period-1 (= bar 13 for period=14).'''
  return _wilder_smooth(_true_range(df), period)


def _directional_movement(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
  '''+DM / -DM per canonical Wilder.

  upMove = H[t] - H[t-1]; downMove = L[t-1] - L[t].
  +DM = upMove if (upMove > downMove AND upMove > 0) else 0.0
  -DM = downMove if (downMove > upMove AND downMove > 0) else 0.0
  Bar 0: diff is NaN ⇒ comparisons False ⇒ DM = 0.0 (canonical; matches oracle).
  '''
  up = df['High'].diff()
  dn = -df['Low'].diff()
  plus_dm = pd.Series(
    np.where((up > dn) & (up > 0), up, 0.0),
    index=df.index,
    dtype='float64',
  )
  minus_dm = pd.Series(
    np.where((dn > up) & (dn > 0), dn, 0.0),
    index=df.index,
    dtype='float64',
  )
  return plus_dm, minus_dm


def _adx_plus_minus_di(
  df: pd.DataFrame, period: int = ADX_PERIOD
) -> tuple[pd.Series, pd.Series, pd.Series]:
  '''Returns (adx, plus_di, minus_di). First non-NaN ADX at bar 2*period-2.

  D-11: sum(TR) == 0 (flat prices) ⇒ +DI/-DI/ADX all NaN via NaN propagation.
  '''
  tr = _true_range(df)
  plus_dm, minus_dm = _directional_movement(df)
  sm_tr = _wilder_smooth(tr, period)
  sm_plus_dm = _wilder_smooth(plus_dm, period)
  sm_minus_dm = _wilder_smooth(minus_dm, period)
  # Replace zero sm_tr with NaN to force NaN propagation (D-11)
  sm_tr_safe = sm_tr.where(sm_tr != 0.0, np.nan)
  plus_di = 100.0 * sm_plus_dm / sm_tr_safe
  minus_di = 100.0 * sm_minus_dm / sm_tr_safe
  denom = plus_di + minus_di
  denom_safe = denom.where(denom != 0.0, np.nan)
  dx = 100.0 * (plus_di - minus_di).abs() / denom_safe
  adx = _wilder_smooth(dx, period)
  return adx.astype('float64'), plus_di.astype('float64'), minus_di.astype('float64')


def _mom(close: pd.Series, lookback: int) -> pd.Series:
  '''N-day price return. First `lookback` bars NaN. pct_change handles NaN cleanly.'''
  return close.pct_change(periods=lookback).astype('float64')


def _rvol(
  close: pd.Series,
  period: int = RVOL_PERIOD,
  annualisation_factor: int = ANNUALISATION_FACTOR,
) -> pd.Series:
  '''Annualised rolling std of daily returns. D-12: flat prices ⇒ 0.0 exactly.

  First non-NaN at bar `period` (daily_ret[0] is NaN, poisons the rolling window
  until bar `period` where it drops out). Matches oracle: rolling std with
  ddof=1 × sqrt(annualisation_factor).
  '''
  daily_ret = close.pct_change()
  rv = daily_ret.rolling(period).std() * np.sqrt(annualisation_factor)
  return rv.astype('float64')


# =========================================================================
# Public API (per D-05, D-07)
# =========================================================================

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
  '''Return NEW DataFrame = input + 8 indicator columns.

  Columns appended (exact names, exact order):
    ATR, ADX, PDI, NDI, Mom1, Mom3, Mom12, RVol.

  Guarantees:
    - Input DataFrame is NOT mutated (D-07).
    - All added columns are float64 (Pitfall 5).
    - NaN for warmup bars per each indicator's period.
  '''
  out = df.copy()
  out['ATR'] = _atr(out, ATR_PERIOD).astype('float64')
  adx, plus_di, minus_di = _adx_plus_minus_di(out, ADX_PERIOD)
  out['ADX'] = adx.astype('float64')
  out['PDI'] = plus_di.astype('float64')
  out['NDI'] = minus_di.astype('float64')
  out['Mom1'] = _mom(out['Close'], MOM_PERIODS[0]).astype('float64')
  out['Mom3'] = _mom(out['Close'], MOM_PERIODS[1]).astype('float64')
  out['Mom12'] = _mom(out['Close'], MOM_PERIODS[2]).astype('float64')
  out['RVol'] = _rvol(out['Close'], RVOL_PERIOD, ANNUALISATION_FACTOR).astype('float64')
  return out


# =========================================================================
# Vote logic + latest-indicator extractor (D-06, D-08, D-09, D-10)
# =========================================================================

def get_signal(
  df: pd.DataFrame,
  settings: dict | None = None,
) -> int:
  '''2-of-3 momentum vote on the last bar, gated by ADX >= ADX_GATE.

  Returns one of {LONG=1, SHORT=-1, FLAT=0} as a bare int (D-06).

  Rules:
    - D-09: NaN ADX => FLAT (also triggered by ADX < ADX_GATE per SIG-05)
    - D-10: NaN Mom values abstain from voting (do not count toward either direction)
    - SIG-06: >=2 non-NaN moms > +MOM_THRESHOLD => LONG
    - SIG-07: >=2 non-NaN moms < -MOM_THRESHOLD => SHORT
    - SIG-08: otherwise => FLAT

  Boundary behaviour (REVIEWS STRONGLY RECOMMENDED):
    - ADX exactly == ADX_GATE (25.0) opens the gate (rule is `adx < ADX_GATE` for FLAT).
    - Mom exactly == +MOM_THRESHOLD abstains (rule is `m > +MOM_THRESHOLD`).
    - Mom exactly == -MOM_THRESHOLD abstains (rule is `m < -MOM_THRESHOLD`).

  Does NOT call compute_indicators -- assumes indicator columns already on df.
  (Caller flow: df2 = compute_indicators(df); signal = get_signal(df2).)
  '''
  row = df.iloc[-1]
  adx_gate = ADX_GATE
  votes_required = 2
  mom_threshold = MOM_THRESHOLD
  if settings is not None:
    adx_gate = float(settings.get('adx_gate', adx_gate))
    votes_required = int(settings.get('momentum_votes_required', votes_required))
    mom_threshold = float(settings.get('momentum_threshold', mom_threshold))

  adx = row['ADX']
  if pd.isna(adx) or adx < adx_gate:
    return FLAT
  moms = [row['Mom1'], row['Mom3'], row['Mom12']]
  valid = [m for m in moms if not pd.isna(m)]
  votes_up = sum(1 for m in valid if m > mom_threshold)
  votes_dn = sum(1 for m in valid if m < -mom_threshold)
  if votes_up >= votes_required:
    return LONG
  if votes_dn >= votes_required:
    return SHORT
  return FLAT


def get_latest_indicators(df: pd.DataFrame) -> dict:
  '''Last-row indicator scalars per D-08.

  Returns dict with keys: atr, adx, pdi, ndi, mom1, mom3, mom12, rvol.
  Every value is Python `float` (numpy.float64 is explicitly unwrapped via `float()`
  per REVIEWS POLISH so downstream JSON serialisation in Phase 3+ does not encounter
  numpy scalar types). NaN is preserved as `float('nan')`, NOT None -- callers use
  `math.isnan()` or `pd.isna()` to check.
  '''
  row = df.iloc[-1]
  return {
    'atr': float(row['ATR']),
    'adx': float(row['ADX']),
    'pdi': float(row['PDI']),
    'ndi': float(row['NDI']),
    'mom1': float(row['Mom1']),
    'mom3': float(row['Mom3']),
    'mom12': float(row['Mom12']),
    'rvol': float(row['RVol']),
  }
