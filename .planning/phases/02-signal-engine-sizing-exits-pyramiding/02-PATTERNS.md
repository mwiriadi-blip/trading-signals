# Phase 2: Signal Engine — Sizing, Exits, Pyramiding - Pattern Map

**Mapped:** 2026-04-21
**Files analyzed:** 9 (5 new source files/dirs + 4 modified)
**Analogs found:** 8 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `system_params.py` | config/constants | — | `signal_engine.py` (constants block, lines 25-39) | partial (constants-only, no math) |
| `sizing_engine.py` | service/pure-math | request-response | `signal_engine.py` (full file) | exact role-match |
| `tests/test_sizing_engine.py` | test | — | `tests/test_signal_engine.py` (full file) | exact |
| `tests/fixtures/phase2/*.json` (15 files) | fixture | — | `tests/oracle/goldens/scenario_*.json` + `tests/fixtures/scenario_*.csv` | format-change (CSV→JSON) |
| `tests/regenerate_phase2_fixtures.py` | utility/script | batch | `tests/regenerate_scenarios.py` (full file) | exact |
| `tests/determinism/phase2_snapshot.json` | fixture | — | `tests/determinism/snapshot.json` | exact |
| `signal_engine.py` (modify) | service/pure-math | request-response | itself | — |
| `tests/test_signal_engine.py` (modify) | test | — | itself | — |
| `SPEC.md` + `CLAUDE.md` (modify) | docs | — | no analog | — |

---

## Pattern Assignments

### `system_params.py` (config, no data flow)

**Analog:** `signal_engine.py` constants block (lines 25-39)

**Module docstring pattern** (from `signal_engine.py` lines 1-21):
```python
'''<One-line summary — module role>.

<Paragraph with hex boundary rule if applicable.>
Architecture (hexagonal-lite, CLAUDE.md): pure constants + types ONLY. No I/O,
no network, no math functions, no imports of state_manager / notifier / dashboard.
'''
```

**Constants block pattern** (`signal_engine.py` lines 25-39):
```python
# --- Signal constants (CLAUDE.md) ---
LONG: int = 1
SHORT: int = -1
FLAT: int = 0

# --- Indicator periods (locked) ---
ATR_PERIOD: int = 14
ADX_PERIOD: int = 20
MOM_PERIODS: tuple[int, int, int] = (21, 63, 252)
RVOL_PERIOD: int = 20
ANNUALISATION_FACTOR: int = 252

# --- Vote thresholds (SPEC.md) ---
ADX_GATE: float = 25.0
MOM_THRESHOLD: float = 0.02
```

**Replication instructions for `system_params.py`:**
- Copy the grouped-comment style (`# --- Group label ---`) for each block
- Group 1: Phase 1 policy constants migrated from `signal_engine.py` (ATR_PERIOD, ADX_PERIOD, MOM_PERIODS, RVOL_PERIOD, ANNUALISATION_FACTOR, ADX_GATE, MOM_THRESHOLD)
- Group 2: Phase 2 sizing constants (RISK_PCT_LONG, RISK_PCT_SHORT, TRAIL_MULT_LONG, TRAIL_MULT_SHORT, VOL_SCALE_TARGET, VOL_SCALE_MIN, VOL_SCALE_MAX, PYRAMID_TRIGGERS, MAX_PYRAMID_LEVEL, ADX_EXIT_GATE)
- Group 3: Contract specs per D-11 (SPI_MULT, SPI_COST_AUD, AUDUSD_NOTIONAL, AUDUSD_COST_AUD)
- Group 4: `Position` TypedDict (D-08) — use `from typing import TypedDict, Literal`
- UPPER_SNAKE for constants, no trailing commas on single-value type aliases
- 2-space indent, single quotes

**`Position` TypedDict to copy** (from RESEARCH.md Pattern 6):
```python
from typing import TypedDict, Literal

class Position(TypedDict):
  direction: Literal['LONG', 'SHORT']
  entry_price: float
  entry_date: str
  n_contracts: int
  pyramid_level: int
  peak_price: float | None    # LONG: highest HIGH since entry; None for SHORT
  trough_price: float | None  # SHORT: lowest LOW since entry; None for LONG
  atr_entry: float            # ATR at time of entry (pyramid thresholds)
```

---

### `sizing_engine.py` (service, request-response)

**Analog:** `signal_engine.py` (full file, 255 lines)

**Module docstring pattern** (`signal_engine.py` lines 1-21):
```python
'''Signal Engine — pure-math indicator library + 2-of-3 momentum vote.

Computes ATR(14), ADX(20) with +DI/-DI, Mom(21/63/252), RVol(20) on an OHLCV
DataFrame and derives a deterministic LONG/SHORT/FLAT signal gated by ADX >= 25.

SIG-01 formula interpretation (R-01): ...

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY. No I/O, no network,
no clock reads, no imports of state_manager / notifier / dashboard.
'''
```
Mirror this: first line = one-sentence summary, second paragraph = key decisions/interpretations, last paragraph = hex boundary rule. Reference D-07 and CONTEXT.md decisions.

**Import block pattern** (`signal_engine.py` lines 22-23):
```python
import numpy as np
import pandas as pd
```
For `sizing_engine.py`, the equivalent import block is stdlib-only (no numpy/pandas — enforced by AST blocklist):
```python
import dataclasses
import math

from signal_engine import FLAT, LONG, SHORT
from system_params import (
  ADX_EXIT_GATE,
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  MAX_PYRAMID_LEVEL,
  RISK_PCT_LONG,
  RISK_PCT_SHORT,
  SPI_COST_AUD,
  SPI_MULT,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
  VOL_SCALE_MAX,
  VOL_SCALE_MIN,
  VOL_SCALE_TARGET,
)
from system_params import Position
```

**Section divider pattern** (`signal_engine.py` lines 43-45):
```python
# =========================================================================
# Private helpers (per D-05)
# =========================================================================
```
Use the same `# === ... ===` 73-char dividers for: Private helpers, Dataclasses, Public API.

**Public function docstring pattern** (`signal_engine.py` lines 172-193 `compute_indicators`, lines 200-232 `get_signal`):
```python
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
  '''Return NEW DataFrame = input + 8 indicator columns.

  Columns appended (exact names, exact order):
    ATR, ADX, PDI, NDI, Mom1, Mom3, Mom12, RVol.

  Guarantees:
    - Input DataFrame is NOT mutated (D-07).
    - All added columns are float64 (Pitfall 5).
    - NaN for warmup bars per each indicator's period.
  '''
```
Mirror this: first line = what it returns, then blank line, then either a structured list (Guarantees / Rules / Boundary behaviour) or a paragraph. Reference requirement IDs (SIZE-01..05, EXIT-06/07, etc.) in the docstring.

**Frozen dataclass pattern** (from RESEARCH.md Example 3):
```python
@dataclasses.dataclass(frozen=True, slots=True)
class SizingDecision:
  contracts: int
  warning: str | None = None

@dataclasses.dataclass(frozen=True, slots=True)
class PyramidDecision:
  add_contracts: int
  new_level: int
```
Place these BEFORE the public functions that return them. Use `@dataclasses.dataclass` (not `from dataclasses import dataclass`) to keep the import block minimal. 2-space indent on field lines.

**NaN guard pattern** (`signal_engine.py` lines 218-232 for NaN policy; `wilder.py` lines 60-63 for `math.isnan`):
```python
# signal_engine.py get_signal lines 218-222:
  adx = row['ADX']
  if pd.isna(adx) or adx < ADX_GATE:
    return FLAT
```
For sizing_engine.py use `math.isnan` / `math.isfinite` (not `pd.isna`) since pandas is not imported:
```python
  if not math.isfinite(rvol) or rvol <= 1e-9:
    vol_scale = VOL_SCALE_MAX
  else:
    vol_scale = max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, VOL_SCALE_TARGET / rvol))
```

**Private helper naming** (`signal_engine.py` lines 46, 59, 96, 101, 124, 147, 152): prefix with `_`, snake_case, no type stubs for tiny one-liner helpers. For sizing_engine.py, private helpers include `_vol_scale(rvol)` and `_close_position(position, bar, reason)`.

---

### `tests/test_sizing_engine.py` (test)

**Analog:** `tests/test_signal_engine.py` (full file, 701 lines)

**File-level docstring pattern** (`test_signal_engine.py` lines 1-7):
```python
'''Phase 1 test suite: signal engine indicators + vote + edge cases + determinism.

Organized into classes per D-13. This file grows across Plans 04 (TestIndicators),
05 (TestVote, TestEdgeCases), and 06 (TestDeterminism + architectural guards).

This file is created in Plan 04 with TestIndicators only.
'''
```
For `test_sizing_engine.py`: reference Phase 2, list TestSizing, TestExits, TestTransitions, TestPyramid, TestEdgeCases, TestDeterminism, and which Wave each class appears in.

**Import block pattern** (`test_signal_engine.py` lines 8-18):
```python
import ast
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from signal_engine import compute_indicators
```
For `test_sizing_engine.py`: replace the production import with:
```python
import ast
import hashlib
import json
import math
from pathlib import Path

import pytest

from signal_engine import FLAT, LONG, SHORT
from sizing_engine import (
  PyramidDecision,
  SizingDecision,
  StepResult,
  calc_position_size,
  check_pyramid,
  check_stop_hit,
  compute_unrealised_pnl,
  get_trailing_stop,
  step,
)
from system_params import Position
```

**Module-level constants pattern** (`test_signal_engine.py` lines 20-25):
```python
CANONICAL_FIXTURES = ['axjo_400bar', 'audusd_400bar']
INDICATOR_COLUMNS = ['ATR', 'ADX', 'PDI', 'NDI', 'Mom1', 'Mom3', 'Mom12', 'RVol']
```
For `test_sizing_engine.py`:
```python
PHASE2_FIXTURES_DIR = Path('tests/fixtures/phase2')
PHASE2_SNAPSHOT_PATH = Path('tests/determinism/phase2_snapshot.json')
SIZING_ENGINE_PATH = Path('sizing_engine.py')
SYSTEM_PARAMS_PATH = Path('system_params.py')
```

**Fixture-loading helper pattern** (`test_signal_engine.py` lines 28-37 `_load_fixture`):
```python
def _load_fixture(stem: str) -> pd.DataFrame:
  '''Load an OHLCV fixture CSV, cast numeric columns to float64.'''
  df = pd.read_csv(
    f'tests/fixtures/{stem}.csv',
    parse_dates=['Date'],
    index_col='Date',
  )
  for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
    df[col] = df[col].astype('float64')
  return df
```
For Phase 2 JSON fixtures:
```python
def _load_phase2_fixture(name: str) -> dict:
  '''Load a Phase 2 JSON scenario fixture.'''
  path = PHASE2_FIXTURES_DIR / f'{name}.json'
  return json.loads(path.read_text())
```

**Named scenario test class pattern** (`test_signal_engine.py` lines 258-340 `TestVote`):
```python
SCENARIOS = [
  'scenario_adx_below_25_flat',
  ...
]

class TestVote:
  '''Per-scenario signal correctness (D-16). Each test name encodes the truth-table row.'''

  @pytest.mark.parametrize('stem', SCENARIOS)
  def test_scenario_produces_expected_signal(self, stem: str) -> None:
    from signal_engine import compute_indicators, get_signal
    fixture = _load_fixture(stem)
    expected = _load_scenario_expected(stem)['expected_signal']
    actual = get_signal(compute_indicators(fixture))
    assert actual == expected, f'{stem}: got {actual}, expected {expected}'

  # --- Named shortcut tests ---
  def test_adx_below_25_flat(self) -> None:
    '''SIG-05: ADX < 25 returns FLAT regardless of momentum.'''
```
Mirror this for `TestTransitions`: parametrize over the 9 transition fixture names, add a named shortcut method for each cell (`test_transition_long_to_short`, etc.). Each shortcut loads the fixture, calls `step()`, and asserts the `StepResult` fields.

**TestEdgeCases class pattern** (`test_signal_engine.py` lines 346-448):
```python
class TestEdgeCases:
  '''NaN and divide-by-zero policy per CONTEXT.md D-09..D-12, plus
  threshold-equality boundary tests per REVIEWS STRONGLY RECOMMENDED.'''

  def test_warmup_nan_adx_flat(self) -> None:
    '''D-09: NaN ADX (warmup) -> FLAT (no position taken).'''
```
Mirror for Phase 2: `TestEdgeCases` holds the 6 named edge-case fixture tests. Each test docstring cites the CONTEXT.md decision or requirement ID it tests.

**TestDeterminism / AST guard pattern** (`test_signal_engine.py` lines 549-701):
```python
SNAPSHOT_PATH = Path('tests/determinism/snapshot.json')
SIGNAL_ENGINE_PATH = Path('signal_engine.py')

FORBIDDEN_MODULES = frozenset({
  'datetime', 'os', 'sys', 'subprocess', 'socket', 'time', 'pickle', 'json', 'pathlib', 'io',
  'requests', 'urllib', 'urllib2', 'urllib3', 'http', 'httpx',
  'state_manager', 'notifier', 'dashboard', 'main',
  'schedule', 'dotenv', 'pytz', 'yfinance',
})

def _top_level_imports(source_path: Path) -> set[str]:
  tree = ast.parse(source_path.read_text())
  modules: set[str] = set()
  for node in ast.walk(tree):
    if isinstance(node, ast.Import):
      for alias in node.names:
        modules.add(alias.name.split('.')[0])
    elif isinstance(node, ast.ImportFrom):
      if node.module:
        modules.add(node.module.split('.')[0])
  return modules
```
The Wave 0 modification to `test_signal_engine.py` extends this existing `TestDeterminism` class by:
1. Changing `test_forbidden_imports_absent` to loop over `[SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH]` (or parametrize with `@pytest.mark.parametrize`)
2. Adding `test_phase2_snapshot_hash_stable` that loads `phase2_snapshot.json` and verifies SHA256 of each expected-decision dict

**2-space indent guard pattern** (`test_signal_engine.py` lines 688-700 `test_no_four_space_indent`):
The same helper functions `_has_two_space_indent_evidence` and `_string_literal_line_ranges` already exist in `test_signal_engine.py`. Wave 0 extends the files-checked list in `test_no_four_space_indent` to include `sizing_engine.py` and `system_params.py`.

---

### `tests/fixtures/phase2/*.json` (15 fixture files)

**Analog A (format shape):** `tests/oracle/goldens/scenario_adx_above_25_long_3_votes.json` (lines 1-13):
```json
{
  "expected_signal": 1,
  "last_row": {
    "adx": 92.63929736787412,
    "atr": 2.277493711993433,
    ...
  }
}
```
Phase 2 fixtures are a structural superset of this format: they carry `prev_position`, `bar` (OHLCV), `indicators`, `account`, `old_signal`, `new_signal`, `multiplier`, `instrument_cost_aud`, and `expected` (multi-field).

**Analog B (naming convention):** `tests/fixtures/scenario_*.csv` — fixture filenames are documentation. Phase 1 uses `scenario_adx_below_25_flat.csv`; Phase 2 uses `transition_long_to_short.json`, `pyramid_gap_crosses_both_levels_caps_at_1.json`. Same principle: filename encodes the truth-table cell or edge case.

**FORMAT CHANGE CALLOUT:** Phase 1 fixtures are CSV (Date-indexed OHLCV rows for running `compute_indicators`). Phase 2 fixtures are JSON because each scenario carries multiple dataclass-shaped objects: `prev_position` (TypedDict), `bar` (dict), `indicators` (dict), `expected` (multi-field dict). CSV would require awkward wide-row flattening. The JSON schema from RESEARCH.md §"15 Named Scenario Fixtures" is the canonical format:
```json
{
  "description": "LONG hold: price rises, pyramid level 0→1, stop not hit",
  "prev_position": {
    "direction": "LONG",
    "entry_price": 7000.0,
    "entry_date": "2026-01-02",
    "n_contracts": 2,
    "pyramid_level": 0,
    "peak_price": 7050.0,
    "trough_price": null,
    "atr_entry": 53.0
  },
  "bar": { "open": 7060.0, "high": 7120.0, "low": 7045.0, "close": 7110.0, "volume": 5000.0, "date": "2026-01-03" },
  "indicators": { "atr": 55.0, "adx": 30.0, "pdi": 35.0, "ndi": 15.0, "mom1": 0.04, "mom3": 0.05, "mom12": 0.06, "rvol": 0.15 },
  "account": 100000.0,
  "old_signal": 1,
  "new_signal": 1,
  "multiplier": 5.0,
  "instrument_cost_aud": 6.0,
  "expected": {
    "sizing_decision": null,
    "trail_stop": 6891.0,
    "stop_hit": false,
    "pyramid_decision": { "add_contracts": 1, "new_level": 1 },
    "unrealised_pnl": 1094.0,
    "position_after": { ... }
  }
}
```
All `null` where not applicable (e.g. `sizing_decision` is null for hold cells). NaN indicator values use `null` (not JSON NaN — matches `allow_nan=False` pattern from `regenerate_goldens.py` line 149).

---

### `tests/regenerate_phase2_fixtures.py` (utility, batch)

**Analog:** `tests/regenerate_scenarios.py` (full file, 206 lines)

**File-level docstring pattern** (`regenerate_scenarios.py` lines 1-28):
```python
'''Offline scenario-CSV regenerator.

Regenerates the 9 scenario fixtures under tests/fixtures/scenario_*.csv from the
recipes documented in tests/fixtures/scenarios.README.md. Mirrors the discipline
of tests/regenerate_goldens.py per D-04: offline-only, never runs in CI. Run
manually when scenario recipes change. Does NOT import from signal_engine.py or
tests/oracle/ -- pure fixture generation (recipes are the authoritative spec).

Usage:
  .venv/bin/python tests/regenerate_scenarios.py
...
'''
```
For `regenerate_phase2_fixtures.py`: same pattern — offline-only, never runs in CI, does NOT import `sizing_engine.py` (recipes are authoritative), usage block, determinism contract (running twice produces byte-identical JSON).

**Module-level path pattern** (`regenerate_scenarios.py` lines 36-39):
```python
ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(os.environ.get('SCENARIO_FIXTURES_DIR', str(ROOT / 'tests' / 'fixtures')))
START_DATE = '2020-01-01'
DEFAULT_VOLUME = 1000.0
```
For `regenerate_phase2_fixtures.py`:
```python
ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(os.environ.get('PHASE2_FIXTURES_DIR', str(ROOT / 'tests' / 'fixtures' / 'phase2')))
SNAPSHOT_PATH = ROOT / 'tests' / 'determinism' / 'phase2_snapshot.json'
```

**Recipe dict pattern** (`regenerate_scenarios.py` lines 80-150 `SEGMENT_RECIPES`):
```python
SEGMENT_RECIPES = {
  'scenario_adx_below_25_flat': {
    'n_bars': 80,
    'close_builder': lambda n: [100.0 + 0.1 * math.sin(i * 0.3) for i in range(n)],
  },
  ...
}
```
For Phase 2, replace with `FIXTURE_RECIPES` dict keyed by the 15 fixture names. Each entry is a plain dict of scenario inputs (prev_position, bar, indicators, account, old_signal, new_signal, multiplier, instrument_cost_aud) and a `compute_expected` callable that takes those inputs and returns the expected dict. The `compute_expected` function reimplements the math inline (it is the authoritative spec; does NOT call `sizing_engine.py`).

**Per-fixture writer + main pattern** (`regenerate_scenarios.py` lines 182-205):
```python
def regenerate_scenario(stem, recipe):
  '''Build and write one scenario CSV. Returns the bar count written.'''
  ...
  df.to_csv(out_path, float_format='%.17g', date_format='%Y-%m-%d')
  print(f'[regen-scn] {stem}: {n} bars written')
  return n

def main() -> None:
  for stem, recipe in SEGMENT_RECIPES.items():
    regenerate_scenario(stem, recipe)
  print(f'[regen-scn] wrote {len(SEGMENT_RECIPES)} scenario CSVs to {FIXTURES_DIR}')

if __name__ == '__main__':
  main()
```
For Phase 2: `write_fixture(name, data)` writes JSON with `json.dump(..., indent=2, sort_keys=True, allow_nan=False)`. `main()` iterates fixtures, calls `write_fixture`, then writes `phase2_snapshot.json` (SHA256 of each fixture's `expected` dict). The `[regen-p2]` log prefix (mirrors `[regen-scn]` pattern).

**SHA256 hash pattern** (`regenerate_goldens.py` lines 155-158 `_hash_series`):
```python
def _hash_series(values: list) -> str:
  '''SHA256 of float64 byte representation (Pitfall 5). NaN has stable bit pattern.'''
  s = pd.Series(values, dtype='float64').to_numpy(dtype='float64', copy=True)
  return hashlib.sha256(s.tobytes()).hexdigest()
```
For Phase 2 (no pandas in regenerator for simple case):
```python
def _hash_expected(expected: dict) -> str:
  '''SHA256 of JSON-serialized expected dict (sort_keys for stability).'''
  canonical = json.dumps(expected, sort_keys=True, separators=(',', ':'))
  return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

---

### `tests/determinism/phase2_snapshot.json` (fixture)

**Analog:** `tests/determinism/snapshot.json` (lines 1-22):
```json
{
  "audusd_400bar": {
    "ADX": "40b83b7225d5f3c9...",
    "ATR": "75a8af00665749...",
    ...
  },
  "axjo_400bar": {
    ...
  }
}
```
Phase 2 snapshot structure:
```json
{
  "transition_long_to_long": "sha256hexstring",
  "transition_long_to_short": "sha256hexstring",
  ...
  "n_contracts_zero_skip_warning": "sha256hexstring"
}
```
One key per fixture name, value is SHA256 of the `expected` dict serialized with `json.dumps(sort_keys=True, separators=(',', ':'))`. Generated by `regenerate_phase2_fixtures.py`, committed as a gold anchor. CI test in `TestDeterminism` re-hashes each fixture's `expected` and asserts against this snapshot.

---

### `signal_engine.py` (modify — Wave 0 constant migration)

**Pattern:** Add `from system_params import ...` at the top of the existing import block, remove the constant definitions that move to `system_params.py`.

**Current constants block to remove** (`signal_engine.py` lines 31-39):
```python
# --- Indicator periods (locked) ---
ATR_PERIOD: int = 14
ADX_PERIOD: int = 20
MOM_PERIODS: tuple[int, int, int] = (21, 63, 252)
RVOL_PERIOD: int = 20
ANNUALISATION_FACTOR: int = 252

# --- Vote thresholds (SPEC.md) ---
ADX_GATE: float = 25.0
MOM_THRESHOLD: float = 0.02
```

**Replacement import** (to insert after line 23 `import pandas as pd`):
```python
from system_params import (
  ADX_GATE,
  ADX_PERIOD,
  ANNUALISATION_FACTOR,
  ATR_PERIOD,
  MOM_PERIODS,
  MOM_THRESHOLD,
  RVOL_PERIOD,
)
```
Keep `LONG: int = 1 / SHORT: int = -1 / FLAT: int = 0` in `signal_engine.py` (D-01: signal-encoding primitives stay here). The function bodies in `signal_engine.py` reference these constants by name — the import makes them available identically.

**Safety check:** Run `.venv/bin/python -m pytest tests/test_signal_engine.py -q` immediately after migration. Zero test failures required before committing (Pitfall 5 from RESEARCH.md).

---

### `tests/test_signal_engine.py` (modify — Wave 0 AST guard extension)

**Pattern A — extend `test_forbidden_imports_absent`** (`test_signal_engine.py` lines 640-653):
```python
def test_forbidden_imports_absent(self) -> None:
  '''CLAUDE.md Architecture: signal_engine.py must not import any module in the blocklist.'''
  imports = _top_level_imports(SIGNAL_ENGINE_PATH)
  leaked = imports & FORBIDDEN_MODULES
  assert not leaked, (
    f'signal_engine.py illegally imports forbidden module(s): {sorted(leaked)}. '
    ...
  )
```
Extend by either: (a) converting to `@pytest.mark.parametrize('module_path', [SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH])` or (b) adding two new named test methods `test_sizing_engine_forbidden_imports_absent` and `test_system_params_forbidden_imports_absent` that call `_top_level_imports` on the new paths. Option (b) keeps the existing test name stable (no parametrize refactor breaking `-k` filters in CI).

**Pattern B — extend `test_no_four_space_indent`** (`test_signal_engine.py` lines 672-700):
```python
missing_2space_files = []
for path in [SIGNAL_ENGINE_PATH, TEST_SIGNAL_ENGINE_PATH]:
  if not _has_two_space_indent_evidence(path):
    missing_2space_files.append(str(path))
```
Extend the list to `[SIGNAL_ENGINE_PATH, TEST_SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH, Path('tests/test_sizing_engine.py')]`.

**Pattern C — extend `test_signal_engine_has_core_public_surface`** (`test_signal_engine.py` lines 655-665):
Add a parallel `test_sizing_engine_has_core_public_surface` method that imports `sizing_engine` and asserts all 6 public names exist: `calc_position_size`, `get_trailing_stop`, `check_stop_hit`, `check_pyramid`, `compute_unrealised_pnl`, `step`, `SizingDecision`, `PyramidDecision`, `StepResult`.

---

## Shared Patterns

### 2-Space Indent (CLAUDE.md)
**Source:** `signal_engine.py` and `tests/test_signal_engine.py` (entire files)
**Apply to:** ALL new Python files — `system_params.py`, `sizing_engine.py`, `tests/test_sizing_engine.py`, `tests/regenerate_phase2_fixtures.py`
**Guard:** `TestDeterminism::test_no_four_space_indent` (extended in Wave 0) will catch any file reflowed to 4-space by `ruff format`. Do NOT run `ruff format` — run only `ruff check`.

### Single-Quotes (CLAUDE.md)
**Source:** Every existing file in the repo
**Apply to:** ALL new Python files
**Pattern:** `'single quotes'` for string literals, `'''triple single quotes'''` for docstrings

### Hex Boundary / AST Blocklist
**Source:** `tests/test_signal_engine.py` lines 461-471 `FORBIDDEN_MODULES` + lines 480-496 `_top_level_imports`
**Apply to:** `sizing_engine.py` and `system_params.py` — both are pure-math/constants modules that MUST NOT import `datetime`, `os`, `sys`, `json`, `pathlib`, `requests`, `state_manager`, `notifier`, `dashboard`, `main`, `schedule`, `dotenv`, `pytz`, `yfinance`, `numpy`, `pandas`
**Enforcement:** Extended AST guard in `TestDeterminism` (Wave 0)

Note: `system_params.py` imports only `typing` (for `TypedDict`, `Literal`). `sizing_engine.py` imports only `dataclasses`, `math`, and the two project modules (`signal_engine`, `system_params`).

### `math.isnan` / `math.isfinite` instead of `pd.isna` / `numpy.isnan`
**Source:** `tests/oracle/wilder.py` lines 60, 120-121 (`math.isnan`); `tests/oracle/mom_rvol.py` line 59
**Apply to:** All NaN guards in `sizing_engine.py`
**Reason:** `numpy` and `pandas` must not be imported into `sizing_engine.py` (AST blocklist). `math.isnan` / `math.isfinite` are the stdlib equivalents.
```python
# oracle/wilder.py line 60:
if any(math.isnan(v) for v in window):
# oracle/wilder.py lines 120-121:
if math.isnan(tr_val) or tr_val == 0.0:
```

### `allow_nan=False` JSON serialization
**Source:** `tests/regenerate_goldens.py` lines 144-151:
```python
with out_path.open('w') as fh:
  json.dump(
    {'expected_signal': expected, 'last_row': last_row},
    fh,
    indent=2,
    allow_nan=False,
    sort_keys=True,
  )
  fh.write('\n')
```
**Apply to:** `tests/regenerate_phase2_fixtures.py` when writing fixture JSON and snapshot JSON. NaN indicator values serialized as `null` (not JSON NaN). Trailing newline after `json.dump`.

### Log Prefix Convention (CLAUDE.md)
**Source:** `tests/regenerate_scenarios.py` line 194 `[regen-scn]`, `tests/regenerate_goldens.py` line 176 `[regen]`
**Apply to:** `tests/regenerate_phase2_fixtures.py` — use `[regen-p2]` prefix on all `print()` statements.

### `ROOT = Path(__file__).resolve().parent.parent` path convention
**Source:** `tests/regenerate_scenarios.py` lines 36-38, `tests/regenerate_goldens.py` lines 35-36
**Apply to:** `tests/regenerate_phase2_fixtures.py` — use same `ROOT` derivation to avoid cwd-relative paths.

### `if __name__ == '__main__': main()` entry point
**Source:** `tests/regenerate_scenarios.py` lines 204-205, `tests/regenerate_goldens.py` lines 187-188
**Apply to:** `tests/regenerate_phase2_fixtures.py`

### `@pytest.mark.parametrize` class method pattern
**Source:** `tests/test_signal_engine.py` lines 79-93:
```python
@pytest.mark.parametrize('stem', CANONICAL_FIXTURES)
@pytest.mark.parametrize('col', INDICATOR_COLUMNS)
def test_indicator_matches_oracle(self, stem: str, col: str) -> None:
```
**Apply to:** `tests/test_sizing_engine.py::TestTransitions::test_scenario_produces_expected_step_result` — parametrize over 9 transition fixture names. Each test loads the JSON fixture and calls `step()`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `SPEC.md` + `CLAUDE.md` (Wave 0 amendments) | docs | — | Documentation amendments; no code analog. Follow Wave 0 task: amend SPEC.md §6 (SPI $5/pt, D-11), SPEC.md §signal_engine.py section (sizing functions moved to sizing_engine.py, D-07), CLAUDE.md §Stack (SPI multiplier), CLAUDE.md §Architecture (sizing_engine.py mention). |

---

## Key Differences Between Phase 1 and Phase 2 Patterns

| Dimension | Phase 1 | Phase 2 |
|-----------|---------|---------|
| Production module math | pandas/numpy vectorized | stdlib only: `math`, `dataclasses`, `typing` |
| NaN guard | `pd.isna()` | `math.isnan()` / `math.isfinite()` |
| Return types | bare `int` (signal), `pd.DataFrame` (indicators), `dict` (latest_indicators) | `@dataclass(frozen=True, slots=True)` for SizingDecision / PyramidDecision / StepResult; `float` and `bool` for stop functions |
| Fixture format | CSV (Date-indexed OHLCV rows) | JSON per-scenario (multiple structured objects) |
| Oracle pattern | Separate `tests/oracle/wilder.py` pure-loop (reused for determinism) | Skip oracle for pure arithmetic (D-04); `regenerate_phase2_fixtures.py` doubles as the reference implementation |
| Determinism hash target | Hashes oracle list[float] via `pd.Series.tobytes()` | Hashes `expected` dict via `json.dumps(sort_keys=True)` |
| State | Stateless DataFrame ops | Stateful `Position` TypedDict as input; functions never mutate it |

---

## Metadata

**Analog search scope:** `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/` (all `.py` and `.json` files)
**Files scanned:** `signal_engine.py`, `tests/test_signal_engine.py`, `tests/oracle/wilder.py`, `tests/oracle/mom_rvol.py`, `tests/regenerate_scenarios.py`, `tests/regenerate_goldens.py`, `tests/determinism/snapshot.json`, `tests/oracle/goldens/scenario_adx_above_25_long_3_votes.json`, `tests/fixtures/scenario_adx_above_25_long_3_votes.csv`, `pyproject.toml`, `tests/conftest.py`
**Pattern extraction date:** 2026-04-21
