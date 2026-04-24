# Phase 3: State Persistence with Recovery - Pattern Map

**Mapped:** 2026-04-21
**Files analyzed:** 4 (2 new, 2 modified)
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `state_manager.py` | service/I/O-hex | file-I/O (read + atomic write) | `signal_engine.py` (module structure, docstring style, section headers) | role-contrast (opposite hex — I/O vs pure-math) |
| `tests/test_state_manager.py` | test | CRUD + file-I/O | `tests/test_sizing_engine.py` | exact (same class-per-concern pattern, same fixture helper pattern) |
| `system_params.py` | config | — | `system_params.py` (self — existing file, add 4 constants) | self-extension |
| `tests/test_signal_engine.py` | test | — | `tests/test_signal_engine.py` (self — extend existing AST blocklist test) | self-extension |

---

## Pattern Assignments

### `state_manager.py` (I/O hex, file-I/O)

**Primary analog:** `signal_engine.py` — for module-level docstring style, section header banners, private/public split, single-quotes, 2-space indent, imports block layout.

**CRITICAL ROLE DIFFERENCE:** `signal_engine.py` is a pure-math hex — no I/O, no os/json/datetime. `state_manager.py` is the I/O hex — it IS allowed to import `os`, `json`, `tempfile`, `datetime`, `zoneinfo`, `pathlib`, `sys`. These imports are FORBIDDEN in the pure-math hexes but REQUIRED here.

**Secondary analog:** `sizing_engine.py` — for the `from system_params import (...)` multi-line import block layout. `state_manager.py` also imports from `system_params`.

#### Module docstring pattern (signal_engine.py lines 1-21):
```python
'''State Manager — atomic JSON persistence, corruption recovery, schema migration.

Owns state.json at the repo root and exposes 6 public functions:
  load_state, save_state, record_trade, update_equity_history,
  reset_state, append_warning.

STATE-01..07 (REQUIREMENTS.md §Persistence). Atomic write via tempfile +
fsync + os.replace (STATE-02). Corruption = JSONDecodeError only (D-05);
on corrupt: backup + reinit + warn (STATE-03). Schema migration via MIGRATIONS
dict walk (STATE-04).

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. This is the ONE module
allowed to do filesystem I/O. Must NOT import signal_engine, sizing_engine,
notifier, dashboard, main, requests, numpy, or pandas.
'''
```

#### Import block pattern (sizing_engine.py lines 17-32 adapted for I/O hex):
```python
import json
import os
import sys
import tempfile
import zoneinfo
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from system_params import (
  AUDUSD_COST_AUD,
  INITIAL_ACCOUNT,          # Phase 3 constant (to be added)
  MAX_WARNINGS,             # Phase 3 constant (to be added)
  SPI_COST_AUD,
  STATE_FILE,               # Phase 3 constant (to be added)
  STATE_SCHEMA_VERSION,     # Phase 3 constant (to be added)
  Position,
)
```

#### Section header banner pattern (signal_engine.py lines 40-43, sizing_engine.py lines 34-35):
```python
# =========================================================================
# Private helpers
# =========================================================================
```
Use for: `# Private helpers`, `# Schema migration`, `# Public API`, `# Module-level constants`.

#### Private helper naming pattern (signal_engine.py lines 45, 58, 95...):
```python
def _true_range(df):   # leading underscore
def _wilder_smooth():  # leading underscore
```
Apply to: `_atomic_write`, `_migrate`, `_backup_corrupt`, `_validate_trade`.

#### Public function docstring pattern — one-liner + STATE-XX citation (signal_engine.py lines 171-181):
```python
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
  '''Return NEW DataFrame = input + 8 indicator columns.

  Guarantees:
    - Input DataFrame is NOT mutated (D-07).
  '''
```
Apply to each public function: cite STATE-XX + D-XX decisions in docstring. Keep docstrings concise (3-6 lines max).

#### Module-level constant block pattern (system_params.py lines 20-34):
```python
# =========================================================================
# Phase N constants — brief note (D-XX)
# =========================================================================

SOME_CONSTANT: float = 1.0   # inline comment citing spec/decision

_AWST = zoneinfo.ZoneInfo('Australia/Perth')  # module-level, private
_REQUIRED_TRADE_FIELDS = frozenset({...})     # module-level, private
```

#### Atomic write — core pattern (from RESEARCH.md Pattern 1, verified against stdlib):
```python
def _atomic_write(data: str, path: Path) -> None:
  '''STATE-02: tempfile + fsync(file) + fsync(parent dir) + os.replace.'''
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    os.replace(tmp_path_str, path)
    tmp_path_str = None  # success: do not delete in finally
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass
```

#### Corruption recovery — core pattern (from RESEARCH.md Pattern 2):
```python
def load_state(path: Path = Path(STATE_FILE), now=None) -> dict:
  '''STATE-01/STATE-03: load; recover on JSONDecodeError (D-05/D-06/D-07).'''
  if not path.exists():
    return reset_state()
  raw = path.read_bytes()
  try:
    state = json.loads(raw)
  except json.JSONDecodeError:
    if now is None:
      now = datetime.now(timezone.utc)
    ts = now.strftime('%Y%m%dT%H%M%SZ')
    backup_name = f'state.json.corrupt.{ts}'
    backup_path = path.parent / backup_name
    os.rename(str(path), str(backup_path))
    print(f'[State] WARNING: state.json was corrupt; backup at {backup_name}', file=sys.stderr)
    state = reset_state()
    state = append_warning(state, 'state_manager',
      f'recovered from corruption; backup at {backup_name}', now=now)
    save_state(state, path)
    return state
  return _migrate(state)
```

#### Schema migration pattern (from RESEARCH.md Pattern 3):
```python
MIGRATIONS: dict = {
  1: lambda s: s,  # no-op at v1; hook proves the walk-forward mechanism works
}

def _migrate(state: dict) -> dict:
  '''STATE-04: walk schema_version forward to STATE_SCHEMA_VERSION.'''
  version = state.get('schema_version', 0)
  while version < STATE_SCHEMA_VERSION:
    version += 1
    state = MIGRATIONS[version](state)
  state['schema_version'] = STATE_SCHEMA_VERSION
  return state
```

#### append_warning pattern — clock injection + FIFO bound (from RESEARCH.md Pattern 4):
```python
_AWST = zoneinfo.ZoneInfo('Australia/Perth')

def append_warning(state: dict, source: str, message: str, now=None) -> dict:
  '''D-09/D-10/D-11: append {date, source, message}; FIFO trim to MAX_WARNINGS.'''
  if now is None:
    now = datetime.now(timezone.utc)
  today_awst = now.astimezone(_AWST).strftime('%Y-%m-%d')
  entry = {'date': today_awst, 'source': source, 'message': message}
  state['warnings'] = state['warnings'][-(MAX_WARNINGS - 1):] + [entry]
  return state
```

Key points:
- `now=None` default → caller injects for tests; production uses `datetime.now(timezone.utc)`. All datetime-dependent functions (load_state, append_warning) follow this same pattern.
- AWST via `zoneinfo.ZoneInfo` (stdlib) — NOT `pytz` (third-party, would be flagged by AST guard).
- Returns mutated `state` dict — callers must capture the return value.

#### record_trade validation pattern (from RESEARCH.md Pattern 5):
```python
_REQUIRED_TRADE_FIELDS = frozenset({
  'instrument', 'direction', 'entry_date', 'exit_date',
  'entry_price', 'exit_price', 'gross_pnl', 'n_contracts',
  'exit_reason', 'multiplier', 'cost_aud',
})

def record_trade(state: dict, trade: dict) -> dict:
  '''STATE-05. D-15: validate; D-14: closing-half cost; D-13: position=None.'''
  missing = _REQUIRED_TRADE_FIELDS - trade.keys()
  if missing:
    raise ValueError(f'record_trade: missing required fields: {sorted(missing)}')
  if trade['instrument'] not in {'SPI200', 'AUDUSD'}:
    raise ValueError(f'record_trade: invalid instrument={trade["instrument"]!r}')
  if trade['direction'] not in {'LONG', 'SHORT'}:
    raise ValueError(f'record_trade: invalid direction={trade["direction"]!r}')
  if not isinstance(trade['n_contracts'], int) or trade['n_contracts'] <= 0:
    raise ValueError(f'record_trade: n_contracts must be int > 0, got {trade["n_contracts"]!r}')
  closing_cost_half = trade['cost_aud'] * trade['n_contracts'] / 2
  net_pnl = trade['gross_pnl'] - closing_cost_half
  state['account'] += net_pnl
  trade['net_pnl'] = net_pnl
  state['trade_log'].append(trade)
  state['positions'][trade['instrument']] = None
  return state
```

#### reset_state canonical shape (from RESEARCH.md Code Examples):
```python
def reset_state() -> dict:
  '''STATE-07: fresh state, $100k account, empty collections.'''
  return {
    'schema_version': STATE_SCHEMA_VERSION,
    'account': INITIAL_ACCOUNT,
    'last_run': None,
    'positions': {
      'SPI200': None,
      'AUDUSD': None,
    },
    'signals': {
      'SPI200': 0,
      'AUDUSD': 0,
    },
    'trade_log': [],
    'equity_history': [],
    'warnings': [],
  }
```

#### JSON serialisation convention (Claude's Discretion):
```python
# In save_state, before _atomic_write:
data = json.dumps(state, sort_keys=True, indent=2, allow_nan=False)
# sort_keys=True  → git-friendly diffs
# indent=2        → human-readable (matches 2-space project indent convention)
# allow_nan=False → NaN in state is a bug; surface it immediately as ValueError
```

---

### `tests/test_state_manager.py` (test, file-I/O + CRUD)

**Analog:** `tests/test_sizing_engine.py` — exact match for class-per-concern structure, `_make_*` helper pattern, fixture-based arithmetic assertions, docstring style.

**Secondary analog:** `tests/test_signal_engine.py` — for `tmp_path` fixture usage pattern (though Phase 1/2 tests don't need tmp_path, the module-level path constant pattern transfers).

#### Module docstring pattern (test_sizing_engine.py lines 1-11):
```python
'''Phase 3 test suite: state persistence, atomic writes, corruption recovery,
trade recording, equity history, reset, warnings, and schema migration.

Organized into classes per D-13 (one class per concern dimension):
  TestLoadSave, TestAtomicity, TestCorruptionRecovery, TestRecordTrade,
  TestEquityHistory, TestReset, TestWarnings, TestSchemaVersion.

All tests use tmp_path (pytest built-in) for isolated state files — never
touch the real ./state.json. Clock-dependent functions accept now= injection
so tests are deterministic without pytest-freezer.
'''
```

#### Imports block pattern (test_sizing_engine.py lines 11-27):
```python
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from state_manager import (
  append_warning,
  load_state,
  record_trade,
  reset_state,
  save_state,
  update_equity_history,
)
from system_params import INITIAL_ACCOUNT, MAX_WARNINGS, STATE_SCHEMA_VERSION
```

#### Module-level path constant pattern (test_sizing_engine.py lines 29-33):
```python
# Module-level path constants (mirrors test_signal_engine.py SIGNAL_ENGINE_PATH pattern)
STATE_MANAGER_PATH = Path('state_manager.py')
```

#### _make_trade helper pattern (mirrors test_sizing_engine.py _make_position lines 129-154):
```python
def _make_trade(
  instrument: str = 'SPI200',
  direction: str = 'LONG',
  entry_price: float = 7000.0,
  exit_price: float = 7100.0,
  n_contracts: int = 2,
  gross_pnl: float = 1000.0,
  cost_aud: float = 6.0,
  multiplier: float = 5.0,
  exit_reason: str = 'flat_signal',
  entry_date: str = '2026-01-02',
  exit_date: str = '2026-01-09',
) -> dict:
  '''Build a trade dict with sensible defaults. All required fields per D-15.'''
  return {
    'instrument': instrument,
    'direction': direction,
    'entry_price': entry_price,
    'exit_price': exit_price,
    'n_contracts': n_contracts,
    'gross_pnl': gross_pnl,
    'cost_aud': cost_aud,
    'multiplier': multiplier,
    'exit_reason': exit_reason,
    'entry_date': entry_date,
    'exit_date': exit_date,
  }
```

#### Class header + docstring pattern (test_sizing_engine.py lines 161-169, 400-416):
```python
class TestLoadSave:
  '''STATE-01/02: load_state and save_state round-trip + atomic write guarantee.

  All tests use tmp_path to avoid touching the real ./state.json.
  Arithmetic expectations verified against reset_state() canonical shape.
  '''

  def test_load_state_fresh_file_missing(self, tmp_path) -> None:
    '''STATE-01: load from non-existent path returns reset_state() shape.'''
    path = tmp_path / 'state.json'
    state = load_state(path=path)
    assert state['schema_version'] == STATE_SCHEMA_VERSION
    assert state['account'] == INITIAL_ACCOUNT
    assert state['positions'] == {'SPI200': None, 'AUDUSD': None}
```

#### Crash-mid-write test pattern (TestAtomicity):
```python
class TestAtomicity:
  '''STATE-02: crash simulation via mock os.replace.

  Patch target is 'state_manager.os.replace' so the mock intercepts the
  exact call made inside save_state's _atomic_write helper.
  '''

  def test_crash_on_os_replace_leaves_original_intact(self, tmp_path) -> None:
    '''STATE-02: if os.replace raises, original state.json is unchanged.'''
    path = tmp_path / 'state.json'
    original_state = reset_state()
    original_state['account'] = 99999.0
    save_state(original_state, path=path)
    original_bytes = path.read_bytes()

    new_state = reset_state()
    new_state['account'] = 50000.0

    with patch('state_manager.os.replace', side_effect=OSError('disk full')):
      with pytest.raises(OSError):
        save_state(new_state, path=path)

    assert path.read_bytes() == original_bytes, (
      'original state.json must be byte-identical after failed replace'
    )
```

#### Corruption recovery test pattern (TestCorruptionRecovery):
```python
class TestCorruptionRecovery:
  '''STATE-03: JSONDecodeError triggers backup + reinit + warning.'''

  def test_corrupt_file_triggers_backup_and_reset(self, tmp_path) -> None:
    '''STATE-03 / D-05/D-06/D-07: garbage bytes -> backup created, fresh state returned.'''
    path = tmp_path / 'state.json'
    path.write_bytes(b'\x00\xff\x00not json')
    fixed_now = datetime(2026, 4, 21, 9, 30, 45, tzinfo=timezone.utc)

    state = load_state(path=path, now=fixed_now)

    # Backup exists alongside state.json
    backup = tmp_path / 'state.json.corrupt.20260421T093045Z'
    assert backup.exists(), 'backup file must be created on corruption'

    # Returned state is a fresh reset (D-05: no silent clobber of valid state)
    assert state['account'] == INITIAL_ACCOUNT
    assert state['positions'] == {'SPI200': None, 'AUDUSD': None}

    # Warning appended (D-07)
    assert len(state['warnings']) == 1
    assert state['warnings'][0]['source'] == 'state_manager'
    assert 'state.json.corrupt.20260421T093045Z' in state['warnings'][0]['message']
```

#### record_trade arithmetic test pattern (test_sizing_engine.py TestSizing style):
```python
class TestRecordTrade:
  '''STATE-05 / D-13..D-16: validation, closing-half cost, account mutation.

  All arithmetic verified from first principles (no oracle files needed).
  '''

  def test_record_trade_adjusts_account_by_net_pnl(self, tmp_path) -> None:
    '''D-14: closing_cost_half = 6.0 * 2 / 2 = 6.0; net_pnl = 1000.0 - 6.0 = 994.0.

    Computed: cost_aud=6.0, n_contracts=2, gross_pnl=1000.0.
    closing_cost_half = 6.0 * 2 / 2 = 6.0
    net_pnl = 1000.0 - 6.0 = 994.0
    account = 100_000.0 + 994.0 = 100_994.0
    '''
    state = reset_state()
    # Simulate an open SPI200 LONG position (reset clears it; set it manually)
    state['positions']['SPI200'] = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-01-02',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 7100.0,
      'trough_price': None, 'atr_entry': 53.0,
    }
    trade = _make_trade(gross_pnl=1000.0, n_contracts=2, cost_aud=6.0)
    result = record_trade(state, trade)

    assert result['account'] == 100_994.0, result['account']
    assert result['positions']['SPI200'] is None, 'D-01/D-13: position must be cleared'
    assert len(result['trade_log']) == 1
    assert result['trade_log'][0]['net_pnl'] == 994.0

  def test_record_trade_raises_on_missing_field(self) -> None:
    '''D-15: ValueError on missing required field, naming the offending key.'''
    state = reset_state()
    trade = _make_trade()
    del trade['gross_pnl']
    with pytest.raises(ValueError, match='gross_pnl'):
      record_trade(state, trade)

  def test_record_trade_raises_on_invalid_instrument(self) -> None:
    '''D-15: ValueError on instrument not in {SPI200, AUDUSD}.'''
    state = reset_state()
    trade = _make_trade(instrument='NASDAQ')
    with pytest.raises(ValueError, match='instrument'):
      record_trade(state, trade)
```

#### append_warning bound test pattern (TestWarnings):
```python
class TestWarnings:
  '''D-09..D-11: warning shape, AWST date, FIFO bound.'''

  def test_append_warning_fifo_trims_oldest_entries(self) -> None:
    '''D-11: 105 appends -> len(warnings) == MAX_WARNINGS (=100); first 5 dropped.'''
    state = reset_state()
    fixed_now = datetime(2026, 4, 21, 9, 0, 0, tzinfo=timezone.utc)
    for i in range(105):
      state = append_warning(state, 'test', f'msg {i}', now=fixed_now)
    assert len(state['warnings']) == MAX_WARNINGS
    # Oldest 5 (msg 0..4) must be gone; msg 5 is the new first entry
    assert state['warnings'][0]['message'] == 'msg 5'

  def test_append_warning_date_uses_awst(self) -> None:
    '''D-09 + A1: warning.date is AWST (Australia/Perth), ISO YYYY-MM-DD.

    Inject a UTC datetime that corresponds to early morning UTC = same AWST date.
    2026-04-21 09:30 UTC = 2026-04-21 17:30 AWST (same date).
    '''
    state = reset_state()
    now_utc = datetime(2026, 4, 21, 9, 30, 0, tzinfo=timezone.utc)
    state = append_warning(state, 'state_manager', 'test msg', now=now_utc)
    assert state['warnings'][0]['date'] == '2026-04-21'
    assert state['warnings'][0]['source'] == 'state_manager'
    assert state['warnings'][0]['message'] == 'test msg'
```

#### Schema migration test pattern (TestSchemaVersion):
```python
class TestSchemaVersion:
  '''STATE-04: MIGRATIONS dict walk-forward; no-op at v1; handles missing key.'''

  def test_schema_v1_no_op_migration(self, tmp_path) -> None:
    '''STATE-04: v1 state loaded, MIGRATIONS[1] applied (no-op), schema_version stays 1.'''
    path = tmp_path / 'state.json'
    state = reset_state()
    assert state['schema_version'] == STATE_SCHEMA_VERSION  # = 1
    path.write_text(json.dumps(state, indent=2))
    loaded = load_state(path=path)
    assert loaded['schema_version'] == STATE_SCHEMA_VERSION
    assert loaded['account'] == INITIAL_ACCOUNT

  def test_load_state_without_schema_version_key_migrates_to_current(self, tmp_path) -> None:
    '''Pitfall 5: state without schema_version key defaults to 0, walks to current.'''
    path = tmp_path / 'state.json'
    bare_state = reset_state()
    del bare_state['schema_version']
    path.write_text(json.dumps(bare_state, indent=2))
    loaded = load_state(path=path)
    assert loaded['schema_version'] == STATE_SCHEMA_VERSION
```

---

### `system_params.py` (self-extension — add 4 Phase 3 constants)

**Analog:** `system_params.py` itself — extend the existing Phase 2 constants block pattern.

#### Existing Phase 2 constants block to mirror (system_params.py lines 36-67):
```python
# =========================================================================
# Phase 2 constants — sizing, exits, pyramid (D-01, SPEC.md §5/7/8)
# =========================================================================

# --- Position sizing (SIZE-01..04) ---
RISK_PCT_LONG: float = 0.01      # 1.0% account risk per LONG entry
```

#### New Phase 3 constants block to add (after the Phase 2 block, before the Position TypedDict):
```python
# =========================================================================
# Phase 3 constants — state persistence (STATE-01, STATE-07, D-11)
# =========================================================================

INITIAL_ACCOUNT: float = 100_000.0  # starting account balance (STATE-07, reset_state)
MAX_WARNINGS: int = 100             # FIFO bound on state['warnings'] (D-11)
STATE_SCHEMA_VERSION: int = 1       # bump on each schema change (STATE-04)
STATE_FILE: str = 'state.json'      # repo-root state file path (SPEC.md §FILE STRUCTURE)
```

Key conventions to follow:
- Inline comment on every constant citing the requirement or decision (matches `# 1.0% account risk per LONG entry` style at line 38).
- Type annotations on all constants (matches `RISK_PCT_LONG: float = 0.01` style).
- Underscore separator in number literals: `100_000.0` (Python convention, readable).
- Module docstring must be updated to mention Phase 3 — add `state_manager.py (Phase 3 I/O hex)` to the "shared by" sentence at line 4-5.

---

### `tests/test_signal_engine.py` (self-extension — AST blocklist for state_manager.py)

**Analog:** `tests/test_signal_engine.py` itself — extend the existing `TestDeterminism` class.

#### Existing pattern to extend (test_signal_engine.py lines 456-489):
```python
SIGNAL_ENGINE_PATH = Path('signal_engine.py')
SIZING_ENGINE_PATH = Path('sizing_engine.py')
SYSTEM_PARAMS_PATH = Path('system_params.py')

FORBIDDEN_MODULES = frozenset({
  'datetime', 'os', 'sys', 'subprocess', 'socket', 'time', 'pickle', 'json', 'pathlib', 'io',
  'requests', 'urllib', 'urllib2', 'urllib3', 'http', 'httpx',
  'state_manager', 'notifier', 'dashboard', 'main',
  'schedule', 'dotenv', 'pytz', 'yfinance',
})
FORBIDDEN_MODULES_STDLIB_ONLY = FORBIDDEN_MODULES | frozenset({'numpy', 'pandas'})

_HEX_PATHS_ALL = [SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH]
_HEX_PATHS_STDLIB_ONLY = [SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH]
```

#### New additions to splice in (after SYSTEM_PARAMS_PATH constant, before FORBIDDEN_MODULES):
```python
# Phase 3 Wave 0: add state_manager.py to AST guard
STATE_MANAGER_PATH = Path('state_manager.py')
TEST_STATE_MANAGER_PATH = Path('tests/test_state_manager.py')
```

#### New forbidden-module set for state_manager.py (I/O hex has DIFFERENT allowed imports):
```python
# state_manager.py IS the I/O hex — os/json/sys/tempfile/datetime/zoneinfo/pathlib ARE allowed.
# But it must NOT import: sibling hexes, numpy, pandas, requests, network modules.
FORBIDDEN_MODULES_STATE_MANAGER = frozenset({
  # Sibling hexes (hexagonal-lite boundary — state_manager is peers with these, never imports them)
  'signal_engine', 'sizing_engine', 'notifier', 'dashboard', 'main',
  # External network/data deps (I/O hex reads disk only; no network)
  'requests', 'urllib', 'urllib2', 'urllib3', 'http', 'httpx',
  # Heavy scientific stack (state_manager is pure stdlib + system_params)
  'numpy', 'pandas',
  # Scheduler and external service deps
  'schedule', 'dotenv', 'yfinance',
  # pytz is third-party; use zoneinfo (stdlib) instead
  'pytz',
})
```

#### Updated _HEX_PATHS_ALL and parametrize additions:
```python
# Extend the parametrize list to include state_manager.py
_HEX_PATHS_ALL = [SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH, STATE_MANAGER_PATH]
```

#### New parametrized test to add inside TestDeterminism:
```python
@pytest.mark.parametrize('module_path', [STATE_MANAGER_PATH])
def test_state_manager_no_forbidden_imports(self, module_path: Path) -> None:
  '''Phase 3 Wave 0: state_manager.py must not import sibling hexes, numpy, pandas,
  or network modules. It IS allowed to import stdlib I/O modules (os, json, tempfile,
  datetime, zoneinfo, pathlib, sys) — those are its PURPOSE as the I/O hex.

  Uses a SEPARATE forbidden set from FORBIDDEN_MODULES because I/O stdlib is
  explicitly permitted for state_manager but forbidden for pure-math hexes.
  '''
  imports = _top_level_imports(module_path)
  leaked = imports & FORBIDDEN_MODULES_STATE_MANAGER
  assert not leaked, (
    f'{module_path} illegally imports forbidden module(s): {sorted(leaked)}. '
    f'state_manager.py must not import sibling hexes (signal_engine, sizing_engine, '
    f'notifier, dashboard), numpy, pandas, or network/external modules. '
    f'Allowed: stdlib (os, json, tempfile, datetime, zoneinfo, pathlib, sys) + system_params.'
  )
```

#### test_no_four_space_indent extension (test_signal_engine.py lines 734-751):
Add `STATE_MANAGER_PATH` and `TEST_STATE_MANAGER_PATH` to the `covered_paths` list inside `test_no_four_space_indent`. This is an in-place list extension — no new test method needed.

---

## Shared Patterns

### Clock injection (now=None default)
**Source:** RESEARCH.md Pattern 4 (verified against Python 3.11 stdlib)
**Apply to:** `load_state`, `append_warning`, `_backup_corrupt` (any function that reads the current time)
```python
def some_function(state: dict, ..., now=None) -> ...:
  if now is None:
    now = datetime.now(timezone.utc)
  # use `now` exclusively — never call datetime.now() inside the body
```
This replaces `pytest-freezer` (not installed) with explicit injection. Every test that needs a fixed time passes `now=datetime(2026, 4, 21, 9, 30, 0, tzinfo=timezone.utc)`.

### 2-space indent + single quotes + PEP 8
**Source:** All existing source files — `signal_engine.py`, `sizing_engine.py`, `system_params.py`
**Apply to:** All new files
Violation is caught by `TestDeterminism::test_no_four_space_indent` (extended in Phase 3 to cover `state_manager.py` and `tests/test_state_manager.py`).

### Functions return mutated state (not None)
**Source:** RESEARCH.md Pattern 4-5 (all mutation functions return `state`)
**Apply to:** `record_trade`, `update_equity_history`, `append_warning`, `reset_state`, `load_state`
Every public function that mutates or builds a state dict returns it. Callers: `state = fn(state, ...)`. This mirrors the pure-function contract of the math hexes — no void returns that hide state.

### `[State]` log prefix
**Source:** CLAUDE.md §Conventions
**Apply to:** Every `print(..., file=sys.stderr)` in `state_manager.py`
```python
print(f'[State] WARNING: state.json was corrupt; backup at {backup_name}', file=sys.stderr)
print(f'[State] schema migrated: v{old_version} -> v{STATE_SCHEMA_VERSION}', file=sys.stderr)
```

### ISO YYYY-MM-DD date format
**Source:** CLAUDE.md §Conventions, CONTEXT.md Claude's Discretion
**Apply to:** `warning.date`, `equity_history[*].date`, `last_run` (set by Phase 4, but schema defined here)
Do NOT store time components in these fields. The backup filename suffix uses ISO 8601 BASIC with time (`%Y%m%dT%H%M%SZ`) for uniqueness — that is the ONLY place a time component appears in state_manager output.

### Explicit type annotations on all public functions
**Source:** `sizing_engine.py` (every public function has `-> ReturnType`)
**Apply to:** All public functions in `state_manager.py`
```python
def load_state(path: Path = Path(STATE_FILE), now=None) -> dict:
def save_state(state: dict, path: Path = Path(STATE_FILE)) -> None:
def record_trade(state: dict, trade: dict) -> dict:
def update_equity_history(state: dict, date: str, equity: float) -> dict:
def reset_state() -> dict:
def append_warning(state: dict, source: str, message: str, now=None) -> dict:
```

---

## No Analog Found

All files have close analogs. No gaps.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | — |

---

## Key Differences to Call Out (Planner Must Read)

### state_manager.py is OPPOSITE in role to signal_engine.py
The primary analog for module structure is `signal_engine.py`, but the role is the inverse:

| Property | signal_engine.py | state_manager.py |
|----------|-----------------|------------------|
| Role | pure-math hex | I/O hex |
| I/O allowed? | NO | YES (it's the whole point) |
| Can import `os`, `json`? | Forbidden | Required |
| Can import `datetime`? | Forbidden | Required |
| Can import `numpy`, `pandas`? | YES (indicator math) | Forbidden |
| Can import sibling hexes? | Forbidden | Forbidden |

### No dataclasses — plain dicts only
`sizing_engine.py` uses `@dataclasses.dataclass(frozen=True, slots=True)` for return types. `state_manager.py` returns plain `dict` objects. Do NOT introduce dataclasses in Phase 3. The state dict schema is documented by `reset_state()`'s return literal; the trade dict schema is documented by `_REQUIRED_TRADE_FIELDS`.

### Tests use `tmp_path` — not real state.json
Phase 1 and Phase 2 tests use fixture files at fixed paths (`tests/fixtures/`). Phase 3 tests use `pytest`'s built-in `tmp_path` fixture for isolated temporary directories. No test in `test_state_manager.py` touches the real `./state.json`.

### Crash-mid-write patch target
Patch target for `os.replace` mock must be `'state_manager.os.replace'` (not `'os.replace'`). Python's mock patches the name in the module's namespace, not in the stdlib.

### Phase 4 gross_pnl boundary (CRITICAL — flag in plan ACs)
`record_trade` expects `trade['gross_pnl']` = raw price-delta P&L only: `(exit - entry) * n_contracts * multiplier`. It does NOT accept `ClosedTrade.realised_pnl` from Phase 2 (which already has the closing cost deducted). Passing `realised_pnl` as `gross_pnl` causes double-counting of the closing cost. The `record_trade` docstring must make this explicit, and the Phase 4 plan must include an AC that verifies the correct field is passed.

---

## Metadata

**Analog search scope:** `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/` (root + `tests/`)
**Files read:** `signal_engine.py`, `system_params.py`, `sizing_engine.py` (lines 1-60), `tests/test_signal_engine.py`, `tests/test_sizing_engine.py`
**Pattern extraction date:** 2026-04-21
