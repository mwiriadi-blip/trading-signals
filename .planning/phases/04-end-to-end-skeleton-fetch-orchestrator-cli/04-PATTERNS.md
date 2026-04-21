# Phase 04 — End-to-End Skeleton — Fetch + Orchestrator + CLI — Pattern Map

**Mapped:** 2026-04-21
**Files analyzed:** 8 new/modified
**Analogs found:** 7 / 8 (main.py has no direct analog — it is the first multi-module orchestrator; mapped to state_manager.py for skeleton/exception/logging patterns, flagged structurally unique)

Scope derived from `04-CONTEXT.md` D-01..D-15 + `04-VALIDATION.md §Wave 0 Requirements` + `04-RESEARCH.md §Recommended Project Structure`.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `data_fetcher.py` | service (I/O hex) | request-response (HTTPS fetch) | `state_manager.py` | role-match (both are I/O hex modules with custom exceptions, narrow retry-eligible catches, module-level logger, one-concern discipline) |
| `main.py` | orchestrator (CLI + dispatcher) | batch (one-shot: load → fetch → compute → persist) | `state_manager.py` (for module skeleton + custom exception + logging) | partial — structurally unique; main is the ONLY module allowed to cross hex boundaries and import both sides |
| `tests/test_data_fetcher.py` | test (I/O module) | integration-style (recorded fixture) + unit (monkeypatch) | `tests/test_state_manager.py` | exact — both test I/O hex modules, both use class-based organisation with docstring contract references |
| `tests/test_main.py` | test (orchestrator) | unit (caplog + monkeypatch + frozen clock) | `tests/test_state_manager.py` | role-match — same class-per-concern discipline; adds `freezer` + `caplog` + `monkeypatch data_fetcher.yf.Ticker` |
| `tests/regenerate_fetch_fixtures.py` | utility (offline script) | batch (live yfinance → JSON on disk) | `tests/regenerate_goldens.py` | exact — both are offline regenerators, NEVER run in CI, committed as scaffolded helpers |
| `tests/fixtures/fetch/axjo_400d.json` + `audusd_400d.json` | fixture (binary/data) | — (input to integration tests) | `tests/fixtures/axjo_400bar.csv` | role-match — format differs (JSON via `to_json(orient='split', date_format='iso')` for DatetimeIndex preservation vs Phase 1 CSV via `to_csv`) |
| `tests/test_signal_engine.py::TestDeterminism` (MODIFIED) | test (AST blocklist guard) | transform (AST walk → frozenset intersection) | Existing `test_state_manager_no_forbidden_imports` method in the SAME file | exact — existing multi-path AST guard pattern, extended with two new entries |
| `requirements.txt` (MODIFIED) | config | — | `requirements.txt` itself | exact — single-line append of pinned dep |

---

## Pattern Assignments

### `data_fetcher.py` (service, I/O hex, request-response)

**Analog:** `state_manager.py` (Phase 3 I/O hex)

**Docstring + architecture banner pattern** (state_manager.py lines 1-33):

```python
'''State Manager — atomic JSON persistence, corruption recovery, schema migration.

Owns state.json at the repo root and exposes 6 public functions: ...

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. This is the ONE module
allowed to do filesystem I/O. Must NOT import signal_engine, sizing_engine,
notifier, dashboard, main, requests, numpy, or pandas. AST blocklist in
tests/test_signal_engine.py::TestDeterminism enforces this structurally.

All clock-dependent functions accept a `now=None` parameter (defaulting to
datetime.now(timezone.utc)) so tests are deterministic without pytest-freezer.
'''
```

Copy this structure verbatim for `data_fetcher.py`: purpose sentence, public-API function list, Architecture banner naming the forbidden imports (sibling hexes + numpy), and a line noting that `timeout=10` + `retries=3` are parameterised for test determinism.

**Imports pattern** (state_manager.py lines 34-53, with F401 noqa convention for Wave 0 stubs):

```python
import json  # noqa: F401 — used in save_state/load_state (Waves 1/2)
import math  # used in _validate_trade (D-19) + update_equity_history (B-4) finiteness checks
import os  # noqa: F401 — used in _atomic_write/_backup_corrupt (Waves 1/2)
import sys  # noqa: F401 — used in load_state stderr logging (Wave 2)
import tempfile  # noqa: F401 — used in _atomic_write (Wave 1)
import zoneinfo  # noqa: F401 — used in append_warning via _AWST (Wave 2)
from datetime import (  # noqa: F401 — used in append_warning/_backup_corrupt (Waves 1/2)
  UTC,
  datetime,
  timezone,
)
from pathlib import Path
from typing import Any  # noqa: F401 — retained for Waves 1-3 type hints

from system_params import (
  INITIAL_ACCOUNT,  # noqa: F401 — used in reset_state (Wave 2)
  ...
)
```

Key conventions executors MUST copy:
- Two-space indent on multi-line imports (see `from datetime import ( ... )`).
- `# noqa: F401 — used in <wave>` for Wave 0 stubs that are not yet referenced (ruff-compliant, documents intent).
- `from system_params import (...)` with one constant per line, trailing comma.

For `data_fetcher.py`, the concrete import block (from RESEARCH §Pattern 1) is:

```python
import logging
import time

import pandas as pd
import requests.exceptions
import yfinance as yf
from yfinance.exceptions import YFRateLimitError
```

Note: `data_fetcher.py` DOES import `pandas` + `yfinance` + `requests.exceptions` — those are its PURPOSE as the fetch hex, analogous to state_manager.py's `os/json/tempfile/zoneinfo` allow-list.

**Custom exception pattern** (state_manager.py implicit — state_manager raises bare `ValueError` with a specific message. Phase 4 gets a DEDICATED exception class per RESEARCH §Pattern 1):

```python
class DataFetchError(Exception):
  '''Raised when a symbol's fetch fails after all retries exhaust.

  Caught at the top of run_daily_check; aborts the whole run (D-03).
  '''
```

A sibling `ShortFrameError(Exception)` for DATA-04 lives alongside (RESEARCH §Pitfall 6 — "Cleaner: separate concerns"). Both subclass bare `Exception`. Orchestrator top-level handler distinguishes them.

**Module-level logger pattern** (state_manager.py does NOT use `logger = logging.getLogger(__name__)` — it prints to stderr directly. data_fetcher.py DEVIATES per D-15 and uses `logger.getLogger(__name__)` because Phase 4 introduces stdlib logging). Pattern source: RESEARCH §Pattern 1 line 286:

```python
logger = logging.getLogger(__name__)
```

**Core retry + narrow-catch pattern** (RESEARCH §Pattern 1, synthesised; STRUCTURALLY mirrors state_manager.py's `_atomic_write` try/finally discipline at state_manager.py lines 107-133):

```python
_RETRY_EXCEPTIONS = (
  YFRateLimitError,
  requests.exceptions.ReadTimeout,
  requests.exceptions.ConnectionError,
)


def fetch_ohlcv(
  symbol: str, days: int = 400, retries: int = 3, backoff_s: float = 10.0,
) -> pd.DataFrame:
  last_err: Exception | None = None
  for attempt in range(1, retries + 1):
    try:
      ticker = yf.Ticker(symbol)
      df = ticker.history(
        period=f'{days}d', interval='1d',
        auto_adjust=True, actions=False, timeout=10,
      )
      if df.empty:
        raise ValueError(f'yfinance returned empty DataFrame for {symbol}')
      return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except (*_RETRY_EXCEPTIONS, ValueError) as e:
      last_err = e
      logger.warning(
        '[Fetch] %s attempt %d/%d failed: %s: %s',
        symbol, attempt, retries, type(e).__name__, e,
      )
      if attempt < retries:
        time.sleep(backoff_s)
  raise DataFetchError(
    f'{symbol}: retries exhausted after {retries} attempts; last error: '
    f'{type(last_err).__name__}: {last_err}',
  ) from last_err
```

Design principles to preserve:
- Narrow catch tuple (CLAUDE.md Pitfall 4 / RESEARCH §Anti-Patterns line 452) — NEVER `except Exception`.
- `raise ... from last_err` preserves the causal chain (matches state_manager.py's corruption-recovery explicitness).
- Defensive column slice `df[['Open', 'High', 'Low', 'Close', 'Volume']]` (RESEARCH §Pitfall 1) — always include this, even though `actions=False` also strips extras.
- `time.sleep(backoff_s)` INSIDE the for-loop only when `attempt < retries` (avoids sleeping after the final failure).
- The `[Fetch]` log prefix (CLAUDE.md §Conventions) is VERBATIM — never `[fetch]`, never `[Data]`.

**Short-frame check lives in main.py, NOT data_fetcher.py** (RESEARCH §Pitfall 6): `fetch_ohlcv` returns a possibly-short DataFrame; orchestrator raises `ShortFrameError`. This keeps the retry loop single-purpose.

---

### `main.py` (orchestrator, batch, structurally unique)

**Analog:** `state_manager.py` for module skeleton + custom exception + logging setup. **NO direct analog for the orchestrator role** — main.py is the first module that imports from all sides of the hex (signal_engine + sizing_engine + state_manager + data_fetcher). Executors should treat main.py as greenfield; RESEARCH §Patterns 2/3/4 (lines 349-447) provide the concrete templates.

**Docstring pattern** (copy state_manager.py lines 1-33 structure):

```python
'''Main — daily orchestrator + CLI.

Wires data_fetcher + signal_engine + sizing_engine + state_manager behind
argparse. Implements run_daily_check(args) per D-11 step sequence.

Architecture (hexagonal-lite, CLAUDE.md): main.py is the ONLY module allowed
to import from all sides of the hex. Pure-math modules (signal_engine,
sizing_engine, system_params) and I/O hex modules (state_manager,
data_fetcher) remain isolated; main.py is the adapter that crosses boundaries.

Reads the wall clock via datetime.now(ZoneInfo('Australia/Perth')) — the ONLY
module permitted to do so per CLAUDE.md. Pure-math modules receive run_date
as a scalar argument.

run_date (AWST wall-clock) and signal_as_of (market-local last-bar date)
are NEVER substituted for each other — both logged on every run (D-13).
'''
```

**CLI + logging bootstrap pattern** (RESEARCH §Pitfall 4, line 536 — `force=True` is mandatory):

```python
import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

AWST = ZoneInfo('Australia/Perth')


def _build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(prog='trading-signals')
  p.add_argument('--test', action='store_true')
  p.add_argument('--reset', action='store_true')
  p.add_argument('--force-email', action='store_true')
  p.add_argument('--once', action='store_true')
  return p


def _validate_flags(args, parser) -> None:
  '''D-05: --reset is mutually exclusive with all other flags.'''
  if args.reset and (args.test or args.force_email or args.once):
    parser.error('--reset cannot be combined with other flags')


def main(argv: list[str] | None = None) -> int:
  parser = _build_parser()
  args = parser.parse_args(argv)
  _validate_flags(args, parser)
  logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stderr,
    force=True,  # Pitfall 4: pytest leaves root-logger handlers attached
  )
  ...
```

**Structural `--test` read-only pattern** (RESEARCH §Pattern 2, lines 349-368):

```python
# main.py — the critical last 3 lines of run_daily_check
if args.test:
  logger.info('[Sched] --test mode: skipping save_state (state.json unchanged)')
  _print_run_summary(run_date, result_summary, state_saved=False)
  return 0
state_manager.save_state(state)
logger.info('[State] state.json saved (account=$%.2f, trades=%d, positions=%d)',
             state['account'], len(state['trade_log']),
             sum(1 for v in state['positions'].values() if v is not None))
_print_run_summary(run_date, result_summary, state_saved=True)
return 0
```

**`run_date` + `signal_as_of` separation pattern** (RESEARCH §Pattern 3, lines 386-406 + D-13):

```python
AWST = ZoneInfo('Australia/Perth')

def _compute_run_date() -> datetime:
  '''CLAUDE.md: run_date always in Australia/Perth. No DST in Perth.
  Orchestrator is the only module allowed to read the wall clock.
  '''
  return datetime.now(tz=AWST)

# Usage inside run_daily_check:
run_date = _compute_run_date()
run_date_iso = run_date.strftime('%Y-%m-%d')
run_date_display = run_date.strftime('%Y-%m-%d %H:%M:%S AWST')

# signal_as_of is SEPARATE and market-local (D-13) — NO tz conversion:
signal_as_of = df.index[-1].strftime('%Y-%m-%d')
```

**`_closed_trade_to_record` translator pattern** (RESEARCH §Pattern 4, lines 408-447):

```python
from sizing_engine import ClosedTrade

def _closed_trade_to_record(
  ct: ClosedTrade, symbol: str, multiplier: float, cost_aud: float,
  entry_date: str, run_date_iso: str,
) -> dict:
  '''D-12: translate Phase 2 ClosedTrade → Phase 3 record_trade dict.

  CRITICAL (state_manager.py record_trade docstring lines 415-422):
    trade['gross_pnl'] MUST be raw price-delta P&L:
      (exit_price - entry_price) * n_contracts * multiplier  (LONG)
      (entry_price - exit_price) * n_contracts * multiplier  (SHORT)
    NOT ClosedTrade.realised_pnl (already deducted closing-half cost).
  '''
  direction_mult = 1.0 if ct.direction == 'LONG' else -1.0
  gross_pnl = direction_mult * (ct.exit_price - ct.entry_price) * ct.n_contracts * multiplier
  return {
    'instrument': symbol,
    'direction': ct.direction,
    'entry_date': entry_date,
    'exit_date': run_date_iso,
    'entry_price': ct.entry_price,
    'exit_price': ct.exit_price,
    'gross_pnl': gross_pnl,
    'n_contracts': ct.n_contracts,
    'exit_reason': ct.exit_reason,
    'multiplier': multiplier,
    'cost_aud': cost_aud,
  }
```

**Top-level exception mapping pattern** (RESEARCH §"Don't Hand-Roll" line 469):

```python
if __name__ == '__main__':
  try:
    sys.exit(main())
  except (DataFetchError, ShortFrameError) as e:
    logger.error('[Fetch] ERROR: %s', e)
    sys.exit(2)
  except Exception as e:
    logger.error('[Sched] ERROR: unexpected crash: %s: %s', type(e).__name__, e)
    sys.exit(1)
```

**`[Prefix]` log convention** (CLAUDE.md line 39 verbatim list). `[Fetch]` is NEW for Phase 4 — used in data_fetcher.py and any orchestrator log line about fetching. `[Sched] [Signal] [State]` are reused from Phases 1-3. `[Email]` is used only by the Phase 4 `--force-email` stub (D-06).

**Symbol mapping** (state.json uses `SPI200`/`AUDUSD`; yfinance uses `^AXJO`/`AUDUSD=X`). main.py owns this mapping:

```python
SYMBOL_MAP = {
  'SPI200': '^AXJO',
  'AUDUSD': 'AUDUSD=X',
}
```

---

### `tests/test_data_fetcher.py` (test, integration + unit)

**Analog:** `tests/test_state_manager.py`

**Module docstring pattern** (test_state_manager.py lines 1-15):

```python
'''Phase 4 test suite: yfinance fetch, retry policy, empty-frame handling,
400-bar shape validation.

Organized into classes per D-13 (one class per concern dimension):
  TestFetch, TestColumnShape.

All tests that touch real yfinance are marked @pytest.mark.integration and
skipped in CI; scenario/error tests monkeypatch data_fetcher.yf.Ticker
at the module-import site.

Wave 0 (this commit): empty skeletons with class docstrings. Waves 1-2 fill
in the test methods per the wave annotation in each class docstring.
'''
```

**Imports + F401 noqa convention** (test_state_manager.py lines 16-38):

```python
import json  # noqa: F401 — used in Wave 1 TestFetch (recorded-fixture load)
from pathlib import Path
from unittest.mock import patch  # noqa: F401 — used in Wave 1 TestFetch (monkeypatch)

import pandas as pd  # noqa: F401 — used in Wave 1 (hand-built DataFrames)
import pytest  # noqa: F401 — used across Waves 1/2

from data_fetcher import (
  DataFetchError,  # noqa: F401 — used in Wave 1 TestFetch
  fetch_ohlcv,      # noqa: F401 — used in Wave 1 TestFetch
)
```

**Path constant pattern** (test_state_manager.py lines 40-45):

```python
DATA_FETCHER_PATH = Path('data_fetcher.py')
TEST_DATA_FETCHER_PATH = Path('tests/test_data_fetcher.py')
FETCH_FIXTURE_DIR = Path('tests/fixtures/fetch')
```

**Class-per-concern pattern** (test_state_manager.py line 91 `TestLoadSave`, line 205 `TestAtomicity`, etc.). For data_fetcher.py:

```python
class TestFetch:
  '''DATA-01/02/03: happy path from recorded fixtures + retry/empty-frame scenarios.

  Happy-path tests load committed JSON fixtures from tests/fixtures/fetch/ via
  pd.read_json(path, orient='split') and monkeypatch data_fetcher.yf.Ticker to
  return them. NEVER call live yfinance in CI.

  Wave 1 fills this in.
  '''

  def test_happy_path_axjo_returns_400_bars(self, monkeypatch) -> None:
    '''DATA-01: ^AXJO fetch returns >= 400 bars with exact column order.'''
    ...


class TestColumnShape:
  '''Pitfall 1: returned DataFrame has EXACTLY [Open, High, Low, Close, Volume]
  in that order — NOT alphabetised, no Dividends/Stock Splits columns.

  Wave 1 fills this in.
  '''
```

**Monkeypatch strategy** (RESEARCH §Testing Patterns, lines 376-382):
Patch `data_fetcher.yf.Ticker` (NOT `yfinance.Ticker`) because data_fetcher.py already bound the `yf` name at module-import time. Pattern precedent: test_state_manager.py line 228 `patch('state_manager.os.replace', ...)` — same idiom.

```python
def test_retry_on_rate_limit_then_success(monkeypatch) -> None:
  '''DATA-03: 3x retry, succeed on attempt 2.'''
  call_count = {'n': 0}
  def fake_history(*args, **kwargs):
    call_count['n'] += 1
    if call_count['n'] == 1:
      raise YFRateLimitError('rate limited')
    return _load_recorded_fixture('axjo_400d.json')
  class FakeTicker:
    def __init__(self, symbol): pass
    def history(self, *a, **kw): return fake_history()
  monkeypatch.setattr('data_fetcher.yf.Ticker', FakeTicker)
  df = fetch_ohlcv('^AXJO', retries=3, backoff_s=0.01)
  assert len(df) >= 400
  assert call_count['n'] == 2
```

**Fixture loading helper** (analog of test_signal_engine.py `_load_fixture`, lines 69-75 in regenerate_goldens.py):

```python
def _load_recorded_fixture(name: str) -> pd.DataFrame:
  '''Load a committed JSON fixture preserving DatetimeIndex + float64 dtypes.'''
  path = FETCH_FIXTURE_DIR / name
  df = pd.read_json(path, orient='split')
  # D-13: keep market-local tz; strftime drops it for signal_as_of
  return df
```

---

### `tests/test_main.py` (test, orchestrator — role-match)

**Analog:** `tests/test_state_manager.py` class-per-concern pattern, plus new `freezer`/`caplog` fixtures.

**Class structure** (mirrors test_state_manager.py lines 91-985 — one class per concern):

```python
class TestCLI:
  '''CLI-01..CLI-05: argparse dispatch + flag-combo validation.

  Wave 3 fills this in. Wave 0 scaffolds skeletons.
  '''

class TestOrchestrator:
  '''D-11 sequence + DATA-04/05/06 + ERR-01/06 + D-08 upgrade + D-12 translator.

  Waves 2-3 fill this in. Uses `freezer` fixture (pytest-freezer) for run_date
  determinism and `caplog` fixture for [Prefix] log assertions.
  '''

class TestLoggerConfig:
  '''Pitfall 4: logging.basicConfig(force=True) applied.

  Wave 0 scaffolds; Wave 3 fills body.
  '''
```

**Monkeypatch precedent** (test_state_manager.py line 441-444 — monkeypatching a sibling module's internal attribute):

```python
# Scaffold pattern from test_state_manager.py applied to main.py tests:
def test_fetch_failure_exits_nonzero_no_save_state(monkeypatch, tmp_path) -> None:
  '''ERR-01 / D-03: DataFetchError after retries → exit non-zero; state.json unchanged.'''
  state_json = tmp_path / 'state.json'
  # Seed clean state
  state_manager.save_state(state_manager.reset_state(), path=state_json)
  mtime_before = state_json.stat().st_mtime_ns
  # Force data_fetcher.fetch_ohlcv to always raise
  def always_fail(*a, **kw):
    raise DataFetchError('simulated network down')
  monkeypatch.setattr('data_fetcher.fetch_ohlcv', always_fail)
  ...
```

**mtime-assertion pattern** (RESEARCH §Pattern 2 test, lines 371-382):

```python
def test_test_flag_leaves_state_json_mtime_unchanged(tmp_path, monkeypatch, freezer):
  '''CLI-01: --test must NOT mutate state.json (structural read-only proof).'''
  state_json = tmp_path / 'state.json'
  state_manager.save_state(state_manager.reset_state(), path=state_json)
  mtime_before = state_json.stat().st_mtime_ns
  # monkeypatch data_fetcher.yf.Ticker to return a recorded DataFrame
  # run main.main(['--test'])
  mtime_after = state_json.stat().st_mtime_ns
  assert mtime_before == mtime_after, 'CLI-01: --test must NOT mutate state.json'
```

**Frozen clock fixture pattern** (pytest-freezer 0.4.9 — added in Wave 0):

```python
@pytest.mark.freeze_time('2026-04-21 09:00:03+08:00')
def test_signal_as_of_and_run_date_logged_separately(caplog) -> None:
  '''DATA-06 / D-13: run_date=2026-04-21 and signal_as_of=<bar date> both logged.'''
  caplog.set_level(logging.INFO)
  # main.main(['--test']) with monkeypatched fetch
  ...
  assert 'signal_as_of=2026-04-17' in caplog.text
  assert 'Run 2026-04-21' in caplog.text
```

---

### `tests/regenerate_fetch_fixtures.py` (utility, offline)

**Analog:** `tests/regenerate_goldens.py` — **exact structural mirror**.

**Module docstring pattern** (regenerate_goldens.py lines 1-25, adapt for fetch):

```python
'''Offline recorded-fixture regenerator for Phase 4 data_fetcher tests.

Per D-02 (04-CONTEXT.md): this script is NEVER invoked by CI. Makes real
network calls to yfinance. Run manually when recorded fixtures need refresh:

  .venv/bin/python tests/regenerate_fetch_fixtures.py

Produces:
  - tests/fixtures/fetch/axjo_400d.json    (DATA-01 happy-path fixture)
  - tests/fixtures/fetch/audusd_400d.json  (DATA-02 happy-path fixture)

Format: pandas DataFrame.to_json(orient='split', date_format='iso') for lossless
DatetimeIndex round-trip (Phase 1 CSVs use to_csv, but CSV loses tz info).
'''
```

**Script structure pattern** (regenerate_goldens.py lines 26-36 + 170-188):

```python
import json
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


def fetch_one(symbol: str) -> 'pd.DataFrame':
  ticker = yf.Ticker(symbol)
  df = ticker.history(
    period='400d', interval='1d',
    auto_adjust=True, actions=False, timeout=10,
  )
  return df[['Open', 'High', 'Low', 'Close', 'Volume']]


def main() -> None:
  FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
  for symbol, filename in SYMBOLS:
    df = fetch_one(symbol)
    out_path = FIXTURES_DIR / filename
    df.to_json(out_path, orient='split', date_format='iso')
    print(f'[regen] wrote {filename} ({len(df)} bars)')


if __name__ == '__main__':
  main()
```

Key conventions copied from regenerate_goldens.py:
- `ROOT = Path(__file__).resolve().parent.parent` pattern (lines 34-36).
- `sys.path.insert(0, str(ROOT))` (line 36) — so `import data_fetcher` would resolve if the script grows to use the real `fetch_ohlcv` helper (currently bypasses to keep script minimal).
- `[regen] wrote ...` log prefix (line 177) — matches goldens script convention.
- `if __name__ == '__main__': main()` (line 187-188).
- Import constant list at module scope (lines 51-66).

---

### `tests/fixtures/fetch/axjo_400d.json` + `audusd_400d.json` (data)

**Analog:** `tests/fixtures/axjo_400bar.csv` — role-match, **FORMAT DIFFERS**.

Phase 1 fixtures use CSV because they are pure OHLCV with a clean ISO `Date` column. Phase 4 needs `df.to_json(orient='split', date_format='iso')` because:
- `to_csv` loses DatetimeIndex `.tz` attribute (RESEARCH §"Don't Hand-Roll" line 468).
- `orient='split'` is the only orient that losslessly round-trips a tz-aware DatetimeIndex. Verified pattern:

```python
df_r = pd.read_json(path, orient='split')
pd.testing.assert_frame_equal(df, df_r)  # lossless
```

No Python code in this file — the committed bytes are the pattern. Regeneration is via `tests/regenerate_fetch_fixtures.py`.

---

### `tests/test_signal_engine.py::TestDeterminism` (MODIFIED — AST blocklist extension)

**Analog:** The SAME file's existing `test_state_manager_no_forbidden_imports` method (test_signal_engine.py lines 719-742). **Exact pattern match** — we are extending a proven multi-module AST guard, not inventing a new one.

**Existing path constant block** (test_signal_engine.py lines 457-465):

```python
SIGNAL_ENGINE_PATH = Path('signal_engine.py')
TEST_SIGNAL_ENGINE_PATH = Path('tests/test_signal_engine.py')
SIZING_ENGINE_PATH = Path('sizing_engine.py')
SYSTEM_PARAMS_PATH = Path('system_params.py')
TEST_SIZING_ENGINE_PATH = Path('tests/test_sizing_engine.py')
STATE_MANAGER_PATH = Path('state_manager.py')
TEST_STATE_MANAGER_PATH = Path('tests/test_state_manager.py')
```

**Extension (Phase 4 Wave 0):** add two new paths ABOVE the existing blocks, with a Phase 4 banner comment:

```python
# Phase 4 Wave 0: add data_fetcher.py + main.py to AST guard
DATA_FETCHER_PATH = Path('data_fetcher.py')
TEST_DATA_FETCHER_PATH = Path('tests/test_data_fetcher.py')
MAIN_PATH = Path('main.py')
TEST_MAIN_PATH = Path('tests/test_main.py')
```

**Existing FORBIDDEN_MODULES_STATE_MANAGER frozenset** (test_signal_engine.py lines 494-505):

```python
# Phase 3 Wave 0: state_manager.py IS the I/O hex — os/json/sys/tempfile/datetime/zoneinfo/
# pathlib/math ARE allowed (those are its PURPOSE...). But it must NOT import sibling hexes,
# numpy, pandas, requests, network modules, scheduler, or third-party tz libs.
FORBIDDEN_MODULES_STATE_MANAGER = frozenset({
  'signal_engine', 'sizing_engine', 'notifier', 'dashboard', 'main',
  'requests', 'urllib', 'urllib2', 'urllib3', 'http', 'httpx',
  'numpy', 'pandas',
  'schedule', 'dotenv', 'yfinance',
  'pytz',
})
```

**Phase 4 extension:** TWO new frozensets following the same banner + rationale comment pattern:

```python
# Phase 4 Wave 0: data_fetcher.py IS the fetch I/O hex — yfinance/pandas/requests/time
# ARE allowed (those are its PURPOSE). But it must NOT import sibling hexes (signal_engine,
# sizing_engine, state_manager, notifier, dashboard, main) or numpy (pandas-only).
FORBIDDEN_MODULES_DATA_FETCHER = frozenset({
  # Sibling hexes — data_fetcher is peers, never imports them
  'signal_engine', 'sizing_engine', 'state_manager', 'notifier', 'dashboard', 'main',
  # numpy (pandas transitively uses numpy; direct import would indicate math leakage)
  'numpy',
  # Scheduler + env deps — data_fetcher is pure fetch, no orchestration
  'schedule', 'dotenv',
  # pytz — project uses zoneinfo (stdlib) via state_manager precedent
  'pytz',
})

# Phase 4 Wave 0: main.py IS the orchestrator — ALL sibling hexes are allowed
# (main is THE cross-hex importer per CLAUDE.md Architecture). But it must NOT
# import numpy directly — all numeric work lives in the engines.
FORBIDDEN_MODULES_MAIN = frozenset({
  'numpy',
})
```

**Existing test method** (test_signal_engine.py lines 719-742) to clone:

```python
@pytest.mark.parametrize('module_path', [STATE_MANAGER_PATH])
def test_state_manager_no_forbidden_imports(self, module_path: Path) -> None:
  '''Phase 3 Wave 0: state_manager.py must not import sibling hexes, numpy, pandas,
  or network modules. ...
  '''
  imports = _top_level_imports(module_path)
  leaked = imports & FORBIDDEN_MODULES_STATE_MANAGER
  assert not leaked, (
    f'{module_path} illegally imports forbidden module(s): {sorted(leaked)}. '
    f'state_manager.py must not import sibling hexes (...), numpy, pandas, ...'
    f'Allowed: stdlib (...) + system_params. State_manager IS the I/O hex — that is its PURPOSE.'
  )
```

**Clone for Phase 4** (identical structure — parametrize decorator, `_top_level_imports` helper, frozenset intersection, structured assert message explaining the role):

```python
@pytest.mark.parametrize('module_path', [DATA_FETCHER_PATH])
def test_data_fetcher_no_forbidden_imports(self, module_path: Path) -> None:
  '''Phase 4 Wave 0: data_fetcher.py must not import sibling hexes or numpy.
  yfinance/pandas/requests/time/logging ARE allowed — those are its PURPOSE as the fetch hex.
  '''
  imports = _top_level_imports(module_path)
  leaked = imports & FORBIDDEN_MODULES_DATA_FETCHER
  assert not leaked, (
    f'{module_path} illegally imports forbidden module(s): {sorted(leaked)}. '
    f'data_fetcher.py must not import sibling hexes (signal_engine, sizing_engine, '
    f'state_manager, notifier, dashboard, main) or numpy. '
    f'Allowed: yfinance, pandas, requests, logging, time, system_params. '
    f'data_fetcher IS the fetch hex — that is its PURPOSE.'
  )

@pytest.mark.parametrize('module_path', [MAIN_PATH])
def test_main_no_forbidden_imports(self, module_path: Path) -> None:
  '''Phase 4 Wave 0: main.py is the ONLY module allowed to import from both sides
  of the hex. Only numpy is blocked — all numeric work belongs in the engines.
  '''
  imports = _top_level_imports(module_path)
  leaked = imports & FORBIDDEN_MODULES_MAIN
  assert not leaked, (
    f'{module_path} illegally imports: {sorted(leaked)}. '
    f'main.py must not import numpy directly — push numeric work into signal_engine '
    f'or sizing_engine.'
  )
```

**2-space-indent guard extension** (test_signal_engine.py lines 779-788). The `covered_paths` list at line 780 must gain four new entries:

```python
covered_paths = [
  SIGNAL_ENGINE_PATH,
  TEST_SIGNAL_ENGINE_PATH,
  SIZING_ENGINE_PATH,
  SYSTEM_PARAMS_PATH,
  TEST_SIZING_ENGINE_PATH,
  STATE_MANAGER_PATH,
  TEST_STATE_MANAGER_PATH,
  DATA_FETCHER_PATH,        # Phase 4 Wave 0
  TEST_DATA_FETCHER_PATH,   # Phase 4 Wave 0
  MAIN_PATH,                # Phase 4 Wave 0
  TEST_MAIN_PATH,           # Phase 4 Wave 0
]
```

---

### `requirements.txt` (MODIFIED — config)

**Analog:** `requirements.txt` itself (exact-version-pin convention already established).

**Existing content** (requirements.txt lines 1-5):

```
numpy==2.0.2
pandas==2.3.3
pytest==8.3.3
yfinance==1.2.0
ruff==0.6.9
```

**Extension pattern:** single-line append with exact `==` pin, alphabetical order preserved (pytest-freezer sits between pytest and ruff since `p` < `r`):

```
numpy==2.0.2
pandas==2.3.3
pytest==8.3.3
pytest-freezer==0.4.9
yfinance==1.2.0
ruff==0.6.9
```

Rationale: CLAUDE.md "Exact version pins (no `>=`, no `~=`) are maintained in requirements.txt per STATE.md §Todos Carried Forward." Phase 1 D-15 deferred pytest-freezer to Phase 4. Version 0.4.9 verified on PyPI per RESEARCH §Standard Stack line 133.

---

## Shared Patterns

### Custom Exception Hierarchy (applies to data_fetcher.py)
**Source:** RESEARCH §Pattern 1 lines 296-301 + §Pitfall 6 lines 562-571
**Apply to:** `data_fetcher.py` module level
**Precedent:** state_manager.py does NOT define custom exception classes (uses bare `ValueError` with specific messages — lines 197-241). Phase 4 DEVIATES because `DataFetchError` / `ShortFrameError` are top-level boundary exceptions that drive exit codes; typed exceptions make the `try/except` mapping in `main.py` concrete:

```python
class DataFetchError(Exception):
  '''Raised when a symbol's fetch fails after all retries exhaust.
  Caught at the top of run_daily_check; aborts the whole run (D-03).
  '''

class ShortFrameError(Exception):
  '''Raised when a fetched DataFrame has len < 300.
  Permanent failure (Yahoo data gap); not retry-eligible (Pitfall 6).
  '''
```

### Logging Convention (applies to data_fetcher.py + main.py)
**Source:** CLAUDE.md §Conventions line 39 (log prefix list) + RESEARCH §Pitfall 4 (force=True)
**Apply to:** Every logger call in Phase 4 modules
**Excerpt:**

```python
# main.py ONCE at main() entry:
logging.basicConfig(
  level=logging.INFO,
  format='%(message)s',
  stream=sys.stderr,
  force=True,                 # Pitfall 4: pytest handler override
)

# Every module:
logger = logging.getLogger(__name__)

# Log line format (verbatim [Prefix]):
logger.info('[Fetch] %s ok: %d bars, last_bar=%s, fetched_in=%.1fs',
            symbol, len(df), signal_as_of, elapsed)
logger.warning('[Fetch] WARN %s stale: signal_as_of=%s is %dd old (threshold=3d)',
               symbol, signal_as_of, days_old)
logger.error('[Fetch] ERROR %s: retries exhausted — aborting run', symbol)
```

Prefixes in use: `[Fetch]` (NEW Phase 4), `[Signal]` (orchestrator wrap of signal_engine calls), `[State]` (orchestrator wrap of state_manager calls), `[Sched]` (run_date + mode log + footer), `[Email]` (ONLY for `--force-email` stub per D-06).

### Class-per-concern Test Organisation (applies to test_data_fetcher.py + test_main.py)
**Source:** test_state_manager.py lines 91-985 (8 classes) + CONTEXT.md §D-13 reference pattern
**Apply to:** Both new test files
**Excerpt:**

```python
class TestFetch:
  '''<requirement-IDs>: <one-line concern>.
  <how this class tests that concern — fixtures used, monkeypatch targets>.
  Wave N fills this in.
  '''

  def test_<concrete_scenario_name>(self, <fixtures>) -> None:
    '''<REQ-ID> / <D-XX>: <one-line assertion>.

    <arithmetic or setup from first principles if applicable>
    '''
    ...
```

Wave 0 commits EMPTY skeletons with docstrings; Waves 1-3 fill bodies. This matches the Phase 3 discipline (test_state_manager.py line 13-14: "Wave 0 (this commit): empty skeletons with class docstrings and _make_trade helper").

### AST Blocklist Frozenset Extension (applies to tests/test_signal_engine.py::TestDeterminism)
**Source:** test_signal_engine.py lines 490-510 (FORBIDDEN_MODULES_STATE_MANAGER + _HEX_PATHS_*)
**Apply to:** Phase 4 adds 2 new frozensets + 2 new parametrized test methods
**Pattern:** NEW frozenset per module (because each module has a different allow-list), NEW test method per frozenset, banner comment explaining the role's allow-list. DO NOT shoehorn new modules into existing frozensets — that loses the module-specific rationale that makes these blocklists maintainable.

### Two-Space Indent (applies to every new Python file)
**Source:** CLAUDE.md §Conventions + pyproject.toml §tool.ruff.format indent-style='space' + test_signal_engine.py `test_no_four_space_indent` guard
**Apply to:** data_fetcher.py, main.py, tests/test_data_fetcher.py, tests/test_main.py, tests/regenerate_fetch_fixtures.py
**Enforcement:** `test_no_four_space_indent` (test_signal_engine.py line 761) checks that every listed file contains at least one line matching `^  [^ ]` regex (the unambiguous signature of 2-space indent). Phase 4 MUST add its four new paths to the `covered_paths` list at line 780.

### F401-noqa Convention for Wave 0 Stubs (applies to data_fetcher.py + main.py + test files)
**Source:** state_manager.py lines 34-47 (every unused-in-Wave-0 import has `# noqa: F401 — used in <wave> <reason>`)
**Apply to:** Every import in Wave 0 scaffolds that is not yet referenced
**Pattern:**

```python
import time  # noqa: F401 — used in Wave 1 fetch_ohlcv retry loop
from yfinance.exceptions import YFRateLimitError  # noqa: F401 — Wave 1 _RETRY_EXCEPTIONS
```

Rationale: ruff B/F ruleset catches unused imports; noqa + inline comment documents intent for Wave 1+ executors.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `main.py` (partial) | orchestrator | batch | **Structurally unique.** main.py is the first module that imports from all sides of the hex (signal_engine + sizing_engine + state_manager + data_fetcher). No existing module has that shape. Executors should reference state_manager.py for module skeleton/docstring/custom-exception/logging patterns, but the orchestration logic (D-11 9-step sequence, `_closed_trade_to_record` translator, CLI dispatch, top-level exception mapping) has no prior-phase analog. RESEARCH §Patterns 2/3/4 (lines 349-447) are the authoritative templates. |

---

## Metadata

**Analog search scope:** repo root (`.`) + `tests/` — no subdirectories deeper than `tests/fixtures/` / `tests/oracle/` / `tests/determinism/`.
**Files scanned:** `signal_engine.py`, `sizing_engine.py`, `state_manager.py`, `system_params.py`, `requirements.txt`, `pyproject.toml`, `tests/test_signal_engine.py`, `tests/test_state_manager.py`, `tests/regenerate_goldens.py`, `tests/regenerate_scenarios.py`, `tests/regenerate_phase2_fixtures.py` (skimmed), `.planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-CONTEXT.md`, `04-RESEARCH.md`, `04-VALIDATION.md`.
**Pattern extraction date:** 2026-04-21
