'''Offline recorded-fixture regenerator for Phase 4 data_fetcher tests.

Per D-02 (04-CONTEXT.md): this script is NEVER invoked by CI. Makes real
network calls to yfinance. Run manually when recorded fixtures need refresh:

  .venv/bin/python tests/regenerate_fetch_fixtures.py

Produces:
  - tests/fixtures/fetch/axjo_400d.json    (DATA-01 happy-path fixture)
  - tests/fixtures/fetch/audusd_400d.json  (DATA-02 happy-path fixture)

Format: pandas DataFrame.to_json(orient='split', date_format='iso') for
lossless DatetimeIndex round-trip (Phase 1 CSV fixtures would lose the tz).
Verified via: `df_r = pd.read_json(path, orient='split'); pd.testing.assert_frame_equal(df, df_r)`.

Defensive checks on every fetch (Pitfall 1 + Pitfall 2):
  - Slice to [Open, High, Low, Close, Volume] in that order (Pitfall 1 —
    yf.download returns alphabetical + MultiIndex; Ticker.history returns
    OHLCV + Dividends/Stock Splits unless actions=False, and even then we
    slice defensively against future yfinance additions).
  - Assert len(df) >= 400 bars (Pitfall 2 — yfinance silently returns an
    empty DataFrame on invalid symbols; raising RuntimeError loudly aborts
    so a typo in SYMBOLS cannot write empty fixtures that would silently
    pass Wave 1 happy-path tests against nothing).

# NOTE (2026-04-22 revision): Wave 0 uses yf.Ticker directly because
# data_fetcher.fetch_ohlcv is still a NotImplementedError stub. After
# Wave 1 merges and fetch_ohlcv is production-ready, 04-02-PLAN.md Task 2
# switches this script to import and call data_fetcher.fetch_ohlcv so
# fixtures reflect the production code path (C-9 follow-up).
'''
import sys
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES_DIR = ROOT / 'tests' / 'fixtures' / 'fetch'

SYMBOLS = [
  ('^AXJO', 'axjo_400d.json'),
  ('AUDUSD=X', 'audusd_400d.json'),
]


def fetch_one(symbol: str):
  '''Fetch >= 400 bars of daily OHLCV directly from yfinance and slice defensively.

  Wave 0 uses yf.Ticker(...).history(...) directly (see module C-9 NOTE).
  Wave 1 switchover point lives in 04-02-PLAN.md Task 2.

  Note (2026-04-22, Rule 3 deviation from 04-01-PLAN.md): the plan-specified
  `period='400d'` returns ~399 bars for ^AXJO and ~395 bars for AUDUSD=X
  (yfinance treats `period='Nd'` as calendar days, and weekends/holidays
  are excluded from daily bars). We use `period='600d'` here to guarantee
  `len(df) >= 400` — Pitfall 2 requires loud aborting on short fixtures so
  a fixture that silently under-delivers is never committed. Production
  `fetch_ohlcv(days=400)` (Wave 1) still uses `period='400d'` as specified;
  the DATA-04 `len < 300 -> ShortFrameError` check there is tuned for that
  reality. This regenerator over-fetches by design — more history never
  harms the fixture's happy-path role.
  '''
  ticker = yf.Ticker(symbol)
  df = ticker.history(
    period='600d',
    interval='1d',
    auto_adjust=True,
    actions=False,
    timeout=10,
  )
  df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
  if len(df) < 400:
    raise RuntimeError(
      f'{symbol}: got {len(df)} bars, expected >= 400 '
      f'(yfinance may have silently returned empty on invalid symbol — '
      f'see 04-RESEARCH.md §Pitfall 2)',
    )
  return df


def main() -> None:
  FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
  for symbol, filename in SYMBOLS:
    df = fetch_one(symbol)
    out_path = FIXTURES_DIR / filename
    df.to_json(out_path, orient='split', date_format='iso')
    print(f'[regen] wrote {filename} ({len(df)} bars)')


if __name__ == '__main__':
  main()
