'''Phase 4 test suite: yfinance fetch, retry policy, empty-frame handling,
400-bar shape validation.

Organized into classes per D-13 (one class per concern dimension):
  TestFetch, TestColumnShape.

All tests are OFFLINE. Happy-path tests load committed JSON fixtures from
tests/fixtures/fetch/*.json via pd.read_json(orient='split') and monkeypatch
`data_fetcher.yf.Ticker` (NOT `yfinance.Ticker`) at the import site — the
patch target is `data_fetcher.yf` because `import yfinance as yf` binds `yf`
as an attribute of `data_fetcher` at module-import time. Scenario / error
tests use the same monkeypatch idiom. NEVER calls live yfinance in CI.

Wave 0 (this commit): empty skeletons with class docstrings. Wave 1 fills
in the test methods per the wave annotation in each class docstring
(04-02-PLAN.md).
'''
import json  # noqa: F401 — used in Wave 1 TestFetch (recorded-fixture load)
from pathlib import Path

import pandas as pd  # noqa: F401 — used in Wave 1 TestFetch (hand-built DataFrames + fixture loader)
import pytest  # noqa: F401 — used in Wave 1 TestFetch (raises, parametrize, monkeypatch)
from yfinance.exceptions import YFRateLimitError  # noqa: F401 — Wave 1 TestFetch retry scenarios

import data_fetcher  # noqa: F401 — Wave 1 monkeypatch target ('data_fetcher.yf.Ticker')
from data_fetcher import (  # noqa: F401 — Wave 1 TestFetch imports
  DataFetchError,
  ShortFrameError,
  fetch_ohlcv,
)

# =========================================================================
# Module-level path + fixture-dir constants (mirrors test_state_manager.py
# STATE_MANAGER_PATH / TEST_STATE_MANAGER_PATH pattern)
# =========================================================================

DATA_FETCHER_PATH = Path('data_fetcher.py')
TEST_DATA_FETCHER_PATH = Path('tests/test_data_fetcher.py')
FETCH_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'fetch'


# =========================================================================
# Fixture loader helper — Wave 1 TestFetch uses this to replay recorded JSON
# =========================================================================

def _load_recorded_fixture(name: str) -> pd.DataFrame:
  '''Load a committed JSON fixture preserving DatetimeIndex + float64 dtypes.

  D-13: keep market-local tz (exchange-local DatetimeIndex); strftime drops
  the tz for signal_as_of downstream. orient='split' is the only pandas
  orient that losslessly round-trips a tz-aware DatetimeIndex.
  '''
  path = FETCH_FIXTURE_DIR / name
  df = pd.read_json(path, orient='split')
  return df


# =========================================================================
# Test classes — one per concern dimension (D-13)
# =========================================================================

class TestFetch:
  '''DATA-01 / DATA-02 / DATA-03: happy path + retry + empty-frame-exhausts-retries.

  Happy paths load tests/fixtures/fetch/axjo_400d.json + audusd_400d.json
  via _load_recorded_fixture and monkeypatch data_fetcher.yf.Ticker at the
  import site (per Pitfall 3 / 04-PATTERNS.md §Monkeypatch strategy).
  NEVER calls live yfinance in CI.

  Wave 1 fills this in (04-02-PLAN.md).
  '''


class TestColumnShape:
  '''Pitfall 1 / DATA-01: returned DataFrame has EXACTLY
  [Open, High, Low, Close, Volume] in that order — not alphabetised, no
  Dividends/Stock Splits columns, DatetimeIndex preserved.

  Wave 1 fills this in (04-02-PLAN.md), including the C-6 revision test
  `test_missing_required_columns_raises_clear_fetch_error`.
  '''
