'''Offline oracle->goldens->determinism-snapshot pipeline.

Per D-04 (.planning/phases/01-signal-engine-core-indicators-vote/01-CONTEXT.md):
this script is NEVER invoked by CI. Run manually when formulas intentionally change:

  .venv/bin/python tests/regenerate_goldens.py

Produces:
  - tests/oracle/goldens/axjo_400bar_indicators.csv     (canonical fixture 1)
  - tests/oracle/goldens/audusd_400bar_indicators.csv   (canonical fixture 2, R-03)
  - tests/oracle/goldens/scenario_*.json                (9 scenario expected-signals)
  - tests/determinism/snapshot.json                     (SHA256 per indicator per fixture)

Writes CSVs with float_format='%.17g' (Pitfall 4). Casts all floats to float64 before
hashing (Pitfall 5). Scenario JSONs have NaN represented as JSON null (allow_nan=False)
so the format is stable and portable.

Golden CSV format: Date,ATR,ADX,PDI,NDI,Mom1,Mom3,Mom12,RVol
Golden JSON format:
  {
    'expected_signal': -1 | 0 | 1,
    'last_row': {'atr': float|null, 'adx': ..., 'pdi': ..., 'ndi': ...,
                 'mom1': ..., 'mom3': ..., 'mom12': ..., 'rvol': ...}
  }
'''
import hashlib
import json
import math
import sys
from pathlib import Path

import pandas as pd

# Ensure repo root on sys.path so `tests.oracle` imports resolve when run as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.oracle.wilder import atr, adx_plus_minus_di  # noqa: E402, I001
from tests.oracle.mom_rvol import mom, rvol  # noqa: E402, I001

ATR_PERIOD = 14
ADX_PERIOD = 20
MOM_PERIODS = (21, 63, 252)  # Mom1 / Mom3 / Mom12 (bar counts, not months)
RVOL_PERIOD = 20
ANNUALISATION_FACTOR = 252

ADX_GATE = 25.0
MOM_THRESHOLD = 0.02
LONG, SHORT, FLAT = 1, -1, 0

FIXTURES_DIR = ROOT / 'tests' / 'fixtures'
GOLDENS_DIR = ROOT / 'tests' / 'oracle' / 'goldens'
DETERMINISM_DIR = ROOT / 'tests' / 'determinism'

CANONICAL_STEMS = ['axjo_400bar', 'audusd_400bar']
SCENARIO_STEMS = [
  'scenario_adx_below_25_flat',
  'scenario_adx_above_25_long_3_votes',
  'scenario_adx_above_25_long_2_votes',
  'scenario_adx_above_25_short_3_votes',
  'scenario_adx_above_25_short_2_votes',
  'scenario_adx_above_25_split_vote_flat',  # 1 up / 1 down / 1 abstain per REVIEWS MUST FIX
  'scenario_warmup_nan_adx_flat',
  'scenario_warmup_mom12_nan_two_mom_agreement',
  'scenario_flat_prices_divide_by_zero',
]


def _load_fixture(stem: str) -> pd.DataFrame:
  '''Load a fixture CSV and force float64 on all OHLCV columns (Pitfall 5).'''
  path = FIXTURES_DIR / f'{stem}.csv'
  df = pd.read_csv(path, parse_dates=['Date'], index_col='Date')
  for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
    df[col] = df[col].astype('float64')
  return df


def compute_oracle_indicators(df: pd.DataFrame) -> dict:
  '''Run the pure-loop oracle on an OHLCV DataFrame, returning 8 list[float] series.'''
  highs = df['High'].tolist()
  lows = df['Low'].tolist()
  closes = df['Close'].tolist()
  atr_vals = atr(highs, lows, closes, ATR_PERIOD)
  adx_vals, pdi_vals, ndi_vals = adx_plus_minus_di(highs, lows, closes, ADX_PERIOD)
  mom1 = mom(closes, MOM_PERIODS[0])
  mom3 = mom(closes, MOM_PERIODS[1])
  mom12 = mom(closes, MOM_PERIODS[2])
  rvol_vals = rvol(closes, RVOL_PERIOD, ANNUALISATION_FACTOR)
  return {
    'ATR': atr_vals,
    'ADX': adx_vals,
    'PDI': pdi_vals,
    'NDI': ndi_vals,
    'Mom1': mom1,
    'Mom3': mom3,
    'Mom12': mom12,
    'RVol': rvol_vals,
  }


def _compute_expected_signal(last_vals: dict) -> int:
  '''Apply D-09 (NaN ADX => FLAT), D-10 (NaN Mom abstains), SIG-05..08 vote.'''
  adx = last_vals['ADX']
  if adx is None or (isinstance(adx, float) and math.isnan(adx)) or adx < ADX_GATE:
    return FLAT
  moms = [last_vals['Mom1'], last_vals['Mom3'], last_vals['Mom12']]
  valid = [m for m in moms if m is not None and not (isinstance(m, float) and math.isnan(m))]
  votes_up = sum(1 for m in valid if m > MOM_THRESHOLD)
  votes_dn = sum(1 for m in valid if m < -MOM_THRESHOLD)
  if votes_up >= 2:
    return LONG
  if votes_dn >= 2:
    return SHORT
  return FLAT


def write_canonical_golden_csv(stem: str, df: pd.DataFrame, indicators: dict) -> None:
  '''Emit canonical fixture goldens as CSV with Date index and %.17g precision.'''
  gdf = pd.DataFrame(
    {col: pd.Series(vals, index=df.index, dtype='float64') for col, vals in indicators.items()}
  )
  gdf.index.name = 'Date'
  out_path = GOLDENS_DIR / f'{stem}_indicators.csv'
  out_path.parent.mkdir(parents=True, exist_ok=True)
  gdf.to_csv(out_path, float_format='%.17g', date_format='%Y-%m-%d')


def write_scenario_golden_json(stem: str, indicators: dict) -> None:
  '''Emit per-scenario expected_signal + last_row dict as JSON (NaN => null).'''
  last_raw = {col: vals[-1] for col, vals in indicators.items()}
  last_row = {
    'atr': None if math.isnan(last_raw['ATR']) else float(last_raw['ATR']),
    'adx': None if math.isnan(last_raw['ADX']) else float(last_raw['ADX']),
    'pdi': None if math.isnan(last_raw['PDI']) else float(last_raw['PDI']),
    'ndi': None if math.isnan(last_raw['NDI']) else float(last_raw['NDI']),
    'mom1': None if math.isnan(last_raw['Mom1']) else float(last_raw['Mom1']),
    'mom3': None if math.isnan(last_raw['Mom3']) else float(last_raw['Mom3']),
    'mom12': None if math.isnan(last_raw['Mom12']) else float(last_raw['Mom12']),
    'rvol': None if math.isnan(last_raw['RVol']) else float(last_raw['RVol']),
  }
  expected = _compute_expected_signal(last_raw)
  out_path = GOLDENS_DIR / f'{stem}.json'
  out_path.parent.mkdir(parents=True, exist_ok=True)
  with out_path.open('w') as fh:
    json.dump(
      {'expected_signal': expected, 'last_row': last_row},
      fh,
      indent=2,
      allow_nan=False,
      sort_keys=True,
    )
    fh.write('\n')


def _hash_series(values: list) -> str:
  '''SHA256 of float64 byte representation (Pitfall 5). NaN has stable bit pattern.'''
  s = pd.Series(values, dtype='float64').to_numpy(dtype='float64', copy=True)
  return hashlib.sha256(s.tobytes()).hexdigest()


def write_determinism_snapshot(snapshots: dict) -> None:
  '''Persist {fixture: {indicator: sha256}} to tests/determinism/snapshot.json.'''
  DETERMINISM_DIR.mkdir(parents=True, exist_ok=True)
  out = DETERMINISM_DIR / 'snapshot.json'
  with out.open('w') as fh:
    json.dump(snapshots, fh, indent=2, sort_keys=True)
    fh.write('\n')


def main() -> None:
  snapshots = {}
  for stem in CANONICAL_STEMS:
    df = _load_fixture(stem)
    indicators = compute_oracle_indicators(df)
    write_canonical_golden_csv(stem, df, indicators)
    snapshots[stem] = {col: _hash_series(vals) for col, vals in indicators.items()}
    print(f'[regen] wrote {stem} golden + snapshot')
  for stem in SCENARIO_STEMS:
    df = _load_fixture(stem)
    indicators = compute_oracle_indicators(df)
    write_scenario_golden_json(stem, indicators)
    print(f'[regen] wrote {stem} json')
  write_determinism_snapshot(snapshots)
  print('[regen] wrote determinism/snapshot.json')


if __name__ == '__main__':
  main()
