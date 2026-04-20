'''Offline scenario-CSV regenerator.

Regenerates the 9 scenario fixtures under tests/fixtures/scenario_*.csv from the
recipes documented in tests/fixtures/scenarios.README.md. Mirrors the discipline
of tests/regenerate_goldens.py per D-04: offline-only, never runs in CI. Run
manually when scenario recipes change. Does NOT import from signal_engine.py or
tests/oracle/ -- pure fixture generation (recipes are the authoritative spec).

Usage:
  .venv/bin/python tests/regenerate_scenarios.py

Override the output directory via env var (used by tests for determinism checks):
  SCENARIO_FIXTURES_DIR=/tmp/foo .venv/bin/python tests/regenerate_scenarios.py

Determinism contract:
  - Running twice produces byte-identical CSVs (linspace + %.17g + no random state).
  - Scenario 6 uses continuity-preserving segments (each segment starts from the
    prior segment's actual last bar). This matches the README's "~=" markers on
    segment starts and avoids drift between the README spec and generated output.

Output:
  - tests/fixtures/scenario_*.csv (9 files, Date index, %.17g precision)
  - prints per-scenario bar count

Not produced here: tests/oracle/goldens/scenario_*.json -- those require oracle
import (see tests/regenerate_goldens.py). If scenario CSVs change, run this
script first, then run tests/regenerate_goldens.py to refresh the goldens.
'''
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
# Env override lets tests/CI send output to a temp dir without touching committed CSVs.
FIXTURES_DIR = Path(os.environ.get('SCENARIO_FIXTURES_DIR', str(ROOT / 'tests' / 'fixtures')))
START_DATE = '2020-01-01'
DEFAULT_VOLUME = 1000.0
HIGH_MULT = 1.005
LOW_MULT = 0.995


def _build_segments(n_bars, segments):
  '''Build a close series from a list of (kind, length, endpoint) tuples.

  - ('flat', length, value): `length` bars at `value`.
  - ('linear', length, endpoint): np.linspace from the prior segment's last value
    to `endpoint`, of length `length`. The first segment may also be linear; in
    that case start = endpoint (degenerate; not used by any current scenario).
  - ('point', 1, value): single-bar override, equivalent to ('flat', 1, value)
    but names the intent (used for bar 279 final-value overrides in scenarios 3/5/6).

  Continuity: each non-first linear segment starts at the LAST bar of the
  preceding segment. This is why scenario 6's segment starts are marked "~=" in
  scenarios.README.md -- the exact values are derived here from linspace, not
  hardcoded in the recipe.
  '''
  closes = []
  for kind, length, val in segments:
    if kind in ('flat', 'point'):
      closes.extend([val] * length)
    elif kind == 'linear':
      start = closes[-1] if closes else val
      closes.extend(np.linspace(start, val, length).tolist())
    else:
      raise ValueError(f'unknown segment kind: {kind}')
  assert len(closes) == n_bars, f'segment total {len(closes)} != n_bars {n_bars}'
  return closes


# SEGMENT_RECIPES: declarative per-scenario data.
#   key: fixture stem (no .csv)
#   value: dict with
#     n_bars: total bar count
#     close_builder: callable(n_bars) -> list[float]
#     ohlc_equal (optional): if True, Open=High=Low=Close bit-identical (scenario 9)
#     volume (optional): override DEFAULT_VOLUME (scenario 9 sets 0.0)
SEGMENT_RECIPES = {
  'scenario_adx_below_25_flat': {
    'n_bars': 80,
    'close_builder': lambda n: [100.0 + 0.1 * math.sin(i * 0.3) for i in range(n)],
  },
  'scenario_adx_above_25_long_3_votes': {
    'n_bars': 280,
    'close_builder': lambda n: _build_segments(n, [
      ('flat', 30, 100.0),
      ('linear', 240, 80.0),
      ('linear', 10, 110.0),
    ]),
  },
  'scenario_adx_above_25_long_2_votes': {
    'n_bars': 280,
    'close_builder': lambda n: _build_segments(n, [
      ('flat', 18, 100.0),
      ('linear', 239, 80.0),
      ('linear', 19, 97.5),
      ('flat', 3, 97.5),
      ('point', 1, 99.7),
    ]),
  },
  'scenario_adx_above_25_short_3_votes': {
    'n_bars': 280,
    'close_builder': lambda n: _build_segments(n, [
      ('flat', 30, 80.0),
      ('linear', 240, 100.0),
      ('linear', 10, 70.0),
    ]),
  },
  'scenario_adx_above_25_short_2_votes': {
    'n_bars': 280,
    'close_builder': lambda n: _build_segments(n, [
      ('flat', 18, 100.0),
      ('linear', 239, 120.0),
      ('linear', 19, 102.5),
      ('flat', 3, 102.5),
      ('point', 1, 100.3),
    ]),
  },
  'scenario_adx_above_25_split_vote_flat': {
    'n_bars': 280,
    'close_builder': lambda n: _build_segments(n, [
      ('flat', 18, 100.0),
      ('linear', 113, 110.0),
      ('linear', 86, 105.0),    # continuity from 110.0 -> 105.0
      ('linear', 42, 95.0),     # continuity from 105.0 -> 95.0
      ('linear', 20, 99.0),     # continuity from 95.0 -> 99.0
      ('point', 1, 100.5),
    ]),
  },
  'scenario_warmup_nan_adx_flat': {
    'n_bars': 30,
    'close_builder': lambda n: [100.0 + math.sin(i * 0.5) for i in range(n)],
  },
  'scenario_warmup_mom12_nan_two_mom_agreement': {
    'n_bars': 80,
    'close_builder': lambda n: _build_segments(n, [
      ('flat', 30, 100.0),
      ('linear', 30, 90.0),
      ('linear', 20, 105.0),
    ]),
  },
  'scenario_flat_prices_divide_by_zero': {
    'n_bars': 40,
    'close_builder': lambda n: [100.0] * n,
    'ohlc_equal': True,
    'volume': 0.0,
  },
}


def _build_ohlcv(closes, ohlc_equal=False, volume=DEFAULT_VOLUME):
  '''Apply shared OHLC convention from scenarios.README.md to a close series.

  Standard: High = Close * 1.005; Low = Close * 0.995;
            Open = closes[i-1] for i>=1, closes[0] for bar 0; Volume = 1000.
  ohlc_equal override (scenario 9): Open = High = Low = Close bit-identical.
  volume override (scenario 9): Volume = 0 instead of 1000.
  '''
  n = len(closes)
  if ohlc_equal:
    highs = list(closes)
    lows = list(closes)
    opens = list(closes)
  else:
    highs = [c * HIGH_MULT for c in closes]
    lows = [c * LOW_MULT for c in closes]
    opens = [closes[0]] + closes[:-1]
  dates = pd.date_range(start=START_DATE, periods=n, freq='D')
  df = pd.DataFrame({
    'Open': opens,
    'High': highs,
    'Low': lows,
    'Close': closes,
    'Volume': [volume] * n,
  }, index=dates)
  df.index.name = 'Date'
  return df


def regenerate_scenario(stem, recipe):
  '''Build and write one scenario CSV. Returns the bar count written.'''
  n = recipe['n_bars']
  closes = recipe['close_builder'](n)
  df = _build_ohlcv(
    closes,
    ohlc_equal=recipe.get('ohlc_equal', False),
    volume=recipe.get('volume', DEFAULT_VOLUME),
  )
  FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
  out_path = FIXTURES_DIR / f'{stem}.csv'
  df.to_csv(out_path, float_format='%.17g', date_format='%Y-%m-%d')
  print(f'[regen-scn] {stem}: {n} bars written')
  return n


def main() -> None:
  for stem, recipe in SEGMENT_RECIPES.items():
    regenerate_scenario(stem, recipe)
  print(f'[regen-scn] wrote {len(SEGMENT_RECIPES)} scenario CSVs to {FIXTURES_DIR}')


if __name__ == '__main__':
  main()
