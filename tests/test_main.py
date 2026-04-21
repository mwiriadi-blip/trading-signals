'''Phase 4 test suite: orchestrator + CLI + logging bootstrap.

Organized into classes per D-13 (one class per concern dimension):
  TestCLI, TestOrchestrator, TestLoggerConfig.

All tests use tmp_path (pytest built-in) for isolated state files — never
touch the real ./state.json. Clock determinism via the `freezer` fixture
(pytest-freezer 0.4.9, pinned in Wave 0); log-line assertions via pytest's
built-in `caplog` fixture. fetch_ohlcv is monkeypatched at the
`data_fetcher.yf.Ticker` import site (NOT `yfinance.Ticker`) — same idiom
as tests/test_state_manager.py line 228 `patch('state_manager.os.replace', ...)`.

Wave 0 (this commit): empty skeletons with class docstrings. Waves 2-3 fill
in the test methods per the wave annotation in each class docstring
(04-03-PLAN.md + 04-04-PLAN.md).
'''
import logging  # noqa: F401 — used in Waves 2/3 caplog level assertions
import os  # noqa: F401 — used in Wave 3 CLI-01 mtime check
from pathlib import Path

import pandas as pd  # noqa: F401 — used in Waves 2/3 hand-built DataFrames
import pytest  # noqa: F401 — used across Waves 2/3 (raises, parametrize, monkeypatch)

import data_fetcher  # noqa: F401 — Waves 2/3 monkeypatch target
import main  # noqa: F401 — Waves 2/3 main.main() dispatch
import state_manager  # noqa: F401 — Waves 2/3 state seeding via reset_state / save_state
from data_fetcher import (  # noqa: F401 — Wave 3 ERR-01 raises DataFetchError / ShortFrameError
  DataFetchError,
  ShortFrameError,
)

# =========================================================================
# Module-level path + fixture-dir constants
# =========================================================================

MAIN_PATH = Path('main.py')
TEST_MAIN_PATH = Path('tests/test_main.py')
FETCH_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'fetch'


# =========================================================================
# Test classes — one per concern dimension (D-13)
# =========================================================================

class TestCLI:
  '''CLI-01 .. CLI-05: argparse dispatch + flag-combo validation.

  Wave 3 fills this in (04-04-PLAN.md). Wave 2 adds the --once + default
  smoke tests (04-03-PLAN.md).
  '''


class TestOrchestrator:
  '''D-11 9-step sequence + DATA-04/05/06 + ERR-01/06 + D-08 upgrade +
  D-12 translator + AC-1 reversal-ordering (2026-04-22 revision — see
  04-03-PLAN.md).

  Uses pytest-freezer `freezer` fixture for run_date determinism and
  `caplog` for [Prefix] log assertions. Waves 2-3 fill this in.
  '''


class TestLoggerConfig:
  '''Pitfall 4: main() configures logging via basicConfig(force=True).

  Wave 0 scaffolds; Wave 3 fills body (04-04-PLAN.md).
  '''
