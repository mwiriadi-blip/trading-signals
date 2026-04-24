# Phase 3: State Persistence with Recovery — Research

**Researched:** 2026-04-21
**Domain:** Python stdlib JSON persistence, atomic file I/O, schema migration, crash recovery
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Position schema (Area 1):**
- D-01: Inactive position = `positions[instrument] = None` (supersedes SPEC.md `{active: false}`)
- D-02: Derived fields (`trail_stop`, `unrealised_pnl`) are NOT persisted (supersedes SPEC.md)
- D-03: `signals` initialised to `{'SPI200': 0, 'AUDUSD': 0}` by `reset_state()`
- D-04: `update_equity_history(state, date, equity)` — equity is caller-computed

**Crash & corruption recovery (Area 2):**
- D-05: Corrupt = JSON parse error ONLY (`json.JSONDecodeError`)
- D-06: Backup file → same dir, named `state.json.corrupt.<ISO-timestamp>` (`20260421T093045Z`)
- D-07: Corruption recovery appends to `state['warnings']` with `source='state_manager'`
- D-08: Atomic write = `tempfile.NamedTemporaryFile + fsync(file) + fsync(parent dir) + os.replace`

**Warnings field (Area 3):**
- D-09: Each entry shape: `{date: 'YYYY-MM-DD', source: str, message: str}`
- D-10: `append_warning(state, source, message)` is the sole writer to `state['warnings']`
- D-11: Bounded to last 100 entries; `MAX_WARNINGS` constant in `system_params.py`
- D-12: Email filters to last 24h (Phase 5 concern; Phase 3 just stores all)

**`record_trade` boundaries (Area 4):**
- D-13: `record_trade` owns the position close (trade_log append + cost deduction + position=None)
- D-14: Closing-half cost computed inside `record_trade`: `closing_cost_half = trade['cost_aud'] * trade['n_contracts'] / 2; net_pnl = trade['gross_pnl'] - closing_cost_half`
- D-15: `record_trade` validates trade dict shape; raises `ValueError` on missing/wrong fields
- D-16: `record_trade` is NOT idempotent — caller responsible for calling exactly once

### Claude's Discretion

- Schema version mechanism: `schema_version: int = 1`, `MIGRATIONS = {1: lambda s: s}`, walk on load
- Test strategy: `tests/test_state_manager.py` with classes `TestLoadSave`, `TestAtomicity`, `TestCorruptionRecovery`, `TestRecordTrade`, `TestEquityHistory`, `TestReset`, `TestWarnings`, `TestSchemaVersion`
- State file location: `./state.json` (repo root per SPEC.md FILE STRUCTURE)
- AST blocklist extension: extend `TestDeterminism::test_forbidden_imports_absent` to cover `state_manager.py`
- Type hints: public API fully typed; `Position` TypedDict from `system_params.py`
- JSON formatting: `json.dumps(..., sort_keys=True, indent=2, allow_nan=False)`
- Date format: ISO `YYYY-MM-DD`; backup filename uses `%Y%m%dT%H%M%SZ`

### Deferred Ideas (OUT OF SCOPE)

- Phase 5: Email warning rendering (last-24h filter, format)
- Phase 4: `signals` dict population, `last_run` mutation, closed_trade→trade dict projection, equity computation
- Phase 6: Dashboard display of derived fields, warnings panel
- Phase 7: GitHub Actions commit-back of state.json
- v2: Multi-instrument dynamic position keys, trade log rotation, jsonschema validation
- Out-of-scope: state.json encryption, multi-process locking
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STATE-01 | State file `state.json` has top-level keys: `schema_version`, `account`, `last_run`, `positions`, `signals`, `trade_log`, `equity_history`, `warnings` | `reset_state()` canonical dict shape; D-01/D-03 override SPEC.md for positions/signals |
| STATE-02 | Writes are atomic via tempfile → fsync → `os.replace` | Verified stdlib idiom with POSIX parent-dir fsync; crash-mid-write test pattern documented |
| STATE-03 | Corrupt `state.json` backed up to `state.json.corrupt.<timestamp>` and reinitialised | Full recovery sequence verified; `json.JSONDecodeError` is the correct exception class |
| STATE-04 | `schema_version` enables forward migration path (no-op migration on v1 proves the hook) | `MIGRATIONS` dict pattern verified; `_migrate()` walk-forward loop documented |
| STATE-05 | `record_trade(state, trade)` appends to `trade_log` and adjusts `account` | Cost-split arithmetic verified: `closing_cost_half = cost_aud * n_contracts / 2`; validation pattern documented |
| STATE-06 | `update_equity_history(state, date)` appends `{date, equity}` with caller-computed equity | Caller passes equity scalar; state_manager is pure I/O hex (no sizing_engine import) |
| STATE-07 | `reset_state()` reinitialises account to $100,000 with empty positions/trades/history | Constants `INITIAL_ACCOUNT`, `STATE_SCHEMA_VERSION` to be added to `system_params.py` |
</phase_requirements>

---

## Summary

Phase 3 builds `state_manager.py` — the I/O hex of the hexagonal-lite architecture. It is the ONLY module in the system that performs filesystem I/O; all other modules are pure math. The module owns `state.json` at the repo root and exposes 6 public functions: `load_state`, `save_state`, `record_trade`, `update_equity_history`, `reset_state`, `append_warning`.

All research items were verified against the Python 3.11 stdlib and the existing Phase 1/2 codebase. Key findings: the atomic write protocol (tempfile + file fsync + parent-dir fsync + os.replace) is a well-understood POSIX idiom fully supported by Python 3.11 stdlib; `json.JSONDecodeError` is the correct and narrow exception class for corruption detection (it is a subclass of `ValueError` but more specific); the `Position` TypedDict round-trips through JSON without loss of type shape; the cost-split arithmetic is symmetric with Phase 2's `_close_position`; and clock-dependent functions (warning date, backup timestamp) should accept an injectable `now=` parameter to avoid `pytest-freezer` dependency.

A critical Phase 4 integration boundary was discovered: `record_trade` expects `trade['gross_pnl']` as the pure price-delta P&L (`(exit - entry) * n_contracts * multiplier`), NOT Phase 2's `ClosedTrade.realised_pnl` (which already deducted the closing cost). Phase 4 must project `ClosedTrade` to the correct gross before calling `record_trade` — otherwise closing cost is double-counted. This is flagged as an Open Question for the planner to surface as a planning note for Phase 4.

**Primary recommendation:** Implement `state_manager.py` as a pure stdlib module with no external dependencies. Use `now=` parameter injection for all datetime calls so tests are deterministic without `pytest-freezer`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| JSON state read/write | state_manager.py (I/O hex) | — | Only hex allowed to do filesystem I/O per hexagonal-lite |
| Atomic write durability | state_manager.py | OS (POSIX fsync semantics) | tempfile + fsync + os.replace is the canonical pattern |
| Corruption detection + recovery | state_manager.py | — | load_state catches JSONDecodeError and triggers backup + reinit |
| Schema migration | state_manager.py | system_params.py (version constant) | Walk MIGRATIONS dict on every load |
| Trade accounting (cost deduction) | state_manager.py (record_trade) | Phase 2 (gross_pnl produced) | Phase 3 applies closing half; Phase 2 already applied opening half |
| Warning generation | Caller subsystems | state_manager.append_warning | Subsystems raise the event; state_manager serialises + bounds |
| Equity computation | Phase 4 orchestrator | — | state_manager is I/O hex only; must not import sizing_engine |
| Position TypedDict definition | system_params.py | — | Shared by Phase 2 and Phase 3 (both read it) |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `json` (stdlib) | Python 3.11 built-in | JSON serialisation/deserialisation | Only dependency; no external package needed |
| `os` (stdlib) | Python 3.11 built-in | `os.replace`, `os.fsync`, `os.open`, `os.O_RDONLY` | Atomic rename + directory fsync |
| `tempfile` (stdlib) | Python 3.11 built-in | `NamedTemporaryFile(dir=parent, delete=False)` | Tempfile in same filesystem as target → atomic replace guaranteed |
| `datetime` (stdlib) | Python 3.11 built-in | `datetime.now(timezone.utc)`, backup filenames, warning dates | No external clock dependency |
| `zoneinfo` (stdlib, Python 3.9+) | Python 3.11 built-in | `ZoneInfo('Australia/Perth')` for AWST date in user-facing warning entries | Replaces `pytz` for stdlib-only modules |
| `pathlib` (stdlib) | Python 3.11 built-in | `Path` for state file path manipulation | Project convention |
| `typing` (stdlib) | Python 3.11 built-in | `TypedDict`, `Any`, `Literal` type hints | Matches Position TypedDict pattern from system_params.py |
| `system_params` (project) | Phase 2 deliverable | `Position` TypedDict, `SPI_COST_AUD`, `AUDUSD_COST_AUD` | state_manager MUST import system_params (it is the one allowed sibling) |

### Supporting (test-only)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | 8.3.3 (pinned) | Test runner with `tmp_path` fixture | All tests use `tmp_path` for isolated state files |
| `unittest.mock` (stdlib) | Python 3.11 built-in | `patch('os.replace', side_effect=OSError(...))` | Crash-mid-write simulation in `TestAtomicity` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `zoneinfo.ZoneInfo` | `pytz` | `pytz` is already in requirements.txt for notifier/Phase 5; but `zoneinfo` is stdlib on Python 3.9+. Use `zoneinfo` to keep state_manager pure stdlib (matches AST guard policy). |
| `json.JSONDecodeError` catch | `ValueError` catch | `ValueError` is too broad — would also catch non-JSON bugs in load code. `JSONDecodeError` is narrow and exactly right. |
| Inject `now=` parameter | `pytest-freezer` | `pytest-freezer` not in requirements.txt and not needed elsewhere. `now=None` defaulting to `datetime.now(timezone.utc)` is simpler and keeps functions pure. |
| `os.rename` for backup | `shutil.move` | `os.rename` is simpler and sufficient when backup and source are on the same filesystem (they are — both in repo root). `shutil.move` is needed for cross-device moves. |

**Installation:** No new packages needed. `state_manager.py` is stdlib-only. Add constants to `system_params.py`:

```bash
# No new pip installs — all stdlib
# system_params.py gets 4 new constants (no install needed)
```

**Version verification:** `[VERIFIED: pyenv exec python3 --version]` Python 3.11.8 — all stdlib modules referenced (`json`, `os`, `tempfile`, `datetime`, `zoneinfo`, `pathlib`, `typing`) are available.

---

## Architecture Patterns

### System Architecture Diagram

```
                        load_state()
                             │
              ┌──────────────▼──────────────┐
              │         state.json          │
              │         (repo root)         │
              └──────────────┬──────────────┘
                             │
                    ┌────────▼────────┐
                    │   _migrate()    │◄── MIGRATIONS dict
                    │  schema walk    │    {1: lambda s: s}
                    └────────┬────────┘
                             │ dict (fully valid state)
                    ┌────────▼────────┐
                    │  load_state()   │◄── json.JSONDecodeError
                    │   return dict   │    → backup + reset + warn
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
  record_trade()  update_equity_history()  append_warning()
         │                   │                   │
    cost split           list append         FIFO bound
    validate             {date, equity}      MAX_WARNINGS
    account +=           positions[X]=None   [State] log
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │  save_state()   │
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │   tempfile (same dir)        │
              │   write → fsync(file)        │
              │   → fsync(parent dir fd)     │
              │   → os.replace → state.json  │
              └─────────────────────────────┘
```

### Recommended Project Structure

```
/                              # repo root
├── state_manager.py           # I/O hex (Phase 3 deliverable)
├── system_params.py           # shared constants + Position TypedDict (amended)
├── state.json                 # runtime artifact (gitignored)
├── state.json.corrupt.<ts>    # backup (gitignored, appears on corruption)
└── tests/
    └── test_state_manager.py  # 8 test classes, all use tmp_path
```

### Pattern 1: Atomic Write with Cleanup-on-Failure

**What:** Write to a tempfile in the same directory, fsync the file, fsync the parent directory fd, then replace atomically. Clean up tempfile if the write fails.

**When to use:** Every `save_state()` call.

```python
# Source: [VERIFIED: Python 3.11 stdlib docs + direct testing]
import json, os, tempfile
from pathlib import Path

def save_state(state: dict, path: Path = Path('state.json')) -> None:
  '''STATE-02: atomic write via tempfile + fsync + os.replace.'''
  data = json.dumps(state, sort_keys=True, indent=2, allow_nan=False)
  parent = path.parent
  tmp_path = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    ) as tmp:
      tmp_path = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())  # durability: flush data to disk
    # fsync parent dir so the rename (directory entry update) is also durable
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    os.replace(tmp_path, path)  # atomic rename on POSIX; works on Windows too
    tmp_path = None  # success — don't clean up
  finally:
    if tmp_path is not None:
      try:
        os.unlink(tmp_path)   # cleanup on failure; ignore if already gone
      except FileNotFoundError:
        pass
```

### Pattern 2: Corruption Recovery Sequence

**What:** Catch `json.JSONDecodeError` on load, backup the corrupt file, return a fresh reset state with a warning entry already appended.

**When to use:** Inside `load_state()` when parsing `state.json`.

```python
# Source: [VERIFIED: direct testing in this session]
import json, os
from datetime import datetime, timezone
from pathlib import Path

def load_state(path: Path = Path('state.json'), now=None) -> dict:
  '''STATE-01/STATE-03: load state.json; recover from corruption.'''
  if not path.exists():
    return reset_state()
  raw = path.read_bytes()
  try:
    state = json.loads(raw)
  except json.JSONDecodeError:
    # D-05/D-06: backup + reinit + warn (D-07)
    if now is None:
      now = datetime.now(timezone.utc)
    ts = now.strftime('%Y%m%dT%H%M%SZ')        # UTC timestamp for filename uniqueness
    backup_name = f'state.json.corrupt.{ts}'
    backup_path = path.parent / backup_name
    os.rename(str(path), str(backup_path))      # same filesystem → rename is atomic
    import sys
    print(f'[State] WARNING: state.json was corrupt; backup at {backup_name}', file=sys.stderr)
    state = reset_state()
    state = append_warning(
      state, 'state_manager',
      f'recovered from corruption; backup at {backup_name}',
      now=now,
    )
    save_state(state, path)  # persist the fresh state before returning
    return state
  return _migrate(state)
```

### Pattern 3: Schema Migration Walk-Forward

**What:** Walk `state['schema_version']` up to `STATE_SCHEMA_VERSION` applying each migration in turn. No-op at v1.

**When to use:** Called by `load_state()` after successful JSON parse.

```python
# Source: [VERIFIED: direct testing in this session]
from system_params import STATE_SCHEMA_VERSION  # = 1

MIGRATIONS: dict = {
  1: lambda s: s,  # no-op at v1; proves the hook works
  # 2: lambda s: {**s, 'new_field': default_value},  # v2 stub
}

def _migrate(state: dict) -> dict:
  '''STATE-04: walk schema version forward, applying each migration.'''
  version = state.get('schema_version', 0)
  while version < STATE_SCHEMA_VERSION:
    version += 1
    state = MIGRATIONS[version](state)
  state['schema_version'] = STATE_SCHEMA_VERSION
  return state
```

### Pattern 4: Warning Append with FIFO Bound

**What:** Append a `{date, source, message}` entry, trim to last `MAX_WARNINGS` entries.

**When to use:** `append_warning()` is the canonical writer; corruption recovery, Phase 4, Phase 5 all call it.

```python
# Source: [VERIFIED: direct testing in this session]
import zoneinfo
from datetime import datetime, timezone
from system_params import MAX_WARNINGS  # = 100

_AWST = zoneinfo.ZoneInfo('Australia/Perth')

def append_warning(state: dict, source: str, message: str, now=None) -> dict:
  '''D-09/D-10/D-11: append {date, source, message}; FIFO bound to MAX_WARNINGS.'''
  if now is None:
    now = datetime.now(timezone.utc)
  today_awst = now.astimezone(_AWST).strftime('%Y-%m-%d')  # AWST per CLAUDE.md
  entry = {'date': today_awst, 'source': source, 'message': message}
  # FIFO trim: keep last (MAX_WARNINGS-1) + new entry = MAX_WARNINGS total
  state['warnings'] = state['warnings'][-(MAX_WARNINGS - 1):] + [entry]
  return state
```

### Pattern 5: record_trade Validation + Cost Split

**What:** Validate required fields, compute closing-half cost, adjust account, clear position, append to trade_log.

**When to use:** Called by Phase 4 orchestrator once per closed position.

```python
# Source: [VERIFIED: direct testing + D-13/D-14/D-15 from CONTEXT.md]
_REQUIRED_TRADE_FIELDS = frozenset({
  'instrument', 'direction', 'entry_date', 'exit_date',
  'entry_price', 'exit_price', 'gross_pnl', 'n_contracts',
  'exit_reason', 'multiplier', 'cost_aud',
})

def record_trade(state: dict, trade: dict) -> dict:
  '''STATE-05. D-15: validate; D-14: deduct closing half; D-13: set position=None.'''
  # D-15 validation
  missing = _REQUIRED_TRADE_FIELDS - trade.keys()
  if missing:
    raise ValueError(f'record_trade: missing required fields: {sorted(missing)}')
  if trade['instrument'] not in {'SPI200', 'AUDUSD'}:
    raise ValueError(f'record_trade: invalid instrument={trade["instrument"]!r}')
  if trade['direction'] not in {'LONG', 'SHORT'}:
    raise ValueError(f'record_trade: invalid direction={trade["direction"]!r}')
  if not isinstance(trade['n_contracts'], int) or trade['n_contracts'] <= 0:
    raise ValueError(f'record_trade: n_contracts must be int > 0, got {trade["n_contracts"]!r}')
  # D-14: closing-half cost deduction
  closing_cost_half = trade['cost_aud'] * trade['n_contracts'] / 2
  net_pnl = trade['gross_pnl'] - closing_cost_half
  state['account'] += net_pnl
  trade['net_pnl'] = net_pnl          # write back before appending
  state['trade_log'].append(trade)
  state['positions'][trade['instrument']] = None  # D-01/D-13: position closed
  return state
```

### Anti-Patterns to Avoid

- **Catching `ValueError` instead of `json.JSONDecodeError`:** Too broad — would mask non-JSON bugs in load code. Use `json.JSONDecodeError` specifically.
- **`datetime.utcnow()` usage:** Deprecated in Python 3.12+. Use `datetime.now(timezone.utc)` always.
- **`import pytz` in state_manager.py:** pytz is not a stdlib module. Use `zoneinfo.ZoneInfo` (Python 3.9+ stdlib). The AST guard would flag pytz as a non-stdlib import.
- **`os.fsync` of directory fd on non-POSIX:** `os.fsync(dir_fd)` of a directory fd is POSIX-only. Wrap in `if os.name == 'posix':`. Project deploys to Linux (GitHub Actions); macOS dev also passes.
- **Passing `ClosedTrade.realised_pnl` as `gross_pnl` to record_trade:** `ClosedTrade.realised_pnl` already has the closing cost deducted by Phase 2 `_close_position`. Phase 4 MUST recompute `gross_pnl = (exit_price - entry_price) * n_contracts * multiplier` (for LONG) and pass that — NOT `realised_pnl`. Passing `realised_pnl` causes double-counting of the closing cost. See Open Questions.
- **Calling `save_state` inside `record_trade` or `append_warning`:** These functions return a mutated `state` dict. The orchestrator (Phase 4) calls `save_state` once after all mutations. State_manager functions must NOT auto-save — that couples I/O decisions to mutation operations.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic file rename | Custom lock-file scheme | `os.replace` + tempfile | OS-guaranteed atomicity on POSIX |
| Parent-dir fsync | Custom directory sync | `os.fsync(os.open(dir, O_RDONLY))` | Standard POSIX durability idiom |
| JSON parse error | Custom parser validation | `json.JSONDecodeError` | Stdlib exception with column/line info built in |
| Timezone conversion (AWST) | Manual UTC+8 arithmetic | `zoneinfo.ZoneInfo('Australia/Perth')` | Handles DST-free correctly; stdlib on Python 3.9+ |
| FIFO bounded list | Custom ring-buffer class | `list[-(N-1):] + [new]` | One-liner; no class needed for 100-entry bound |

**Key insight:** The entire state_manager.py is stdlib. No external package is needed for any of its capabilities.

---

## Runtime State Inventory

This is a greenfield phase — `state_manager.py` and `state.json` do not exist yet. Not a rename/refactor phase.

**None — verified by direct filesystem check (`ls state_manager.py` → not found; `ls state.json` → not found).**

---

## Common Pitfalls

### Pitfall 1: Tempfile TOCTOU — Lingering `.tmp` Files on Failure

**What goes wrong:** If `save_state` raises between creating the tempfile and calling `os.replace`, the tempfile lingers at `./state.json.tmp.XXXXX`. On the next run, these accumulate and confuse forensics.

**Why it happens:** `NamedTemporaryFile(delete=False)` requires manual cleanup — the file is NOT cleaned up on exception.

**How to avoid:** `try/finally` with `os.unlink(tmp_path)` in the finally block. Ignore `FileNotFoundError` (already replaced = success case). Set `tmp_path = None` on successful `os.replace` so the finally clause knows not to delete.

**Warning signs:** Multiple `*.tmp` files in repo root after failed runs.

### Pitfall 2: Parent-Dir fsync Raises on Non-POSIX

**What goes wrong:** `os.fsync(dir_fd)` is undefined behavior on Windows. On Windows it raises `OSError: [Errno 9] Bad file descriptor`.

**Why it happens:** `fsync` of a directory fd is a POSIX-specific concept (no directory write cache on Windows — the OS handles it differently).

**How to avoid:** Guard with `if os.name == 'posix':`. Project deploys on Linux (GitHub Actions) and macOS dev machines — both pass. Windows is not a target, but guard prevents accidental CI failure if Windows runners are ever introduced.

**Warning signs:** `OSError` on `os.fsync` during dev on Windows.

### Pitfall 3: Double-Counted Closing Cost (Phase 4 Integration Boundary)

**What goes wrong:** Phase 4 passes `ClosedTrade.realised_pnl` as `trade['gross_pnl']` to `record_trade`. `realised_pnl` is Phase 2's `_close_position` output: `gross - close_cost`. Then `record_trade` deducts `closing_cost_half` AGAIN, making the account understated by `cost_aud * n_contracts / 2`.

**Why it happens:** `ClosedTrade.realised_pnl` sounds like "gross P&L" but is actually net-of-close-cost. Field naming confusion at the Phase 2/3 boundary.

**How to avoid:** Phase 4 must reconstruct `gross_pnl = (exit_price - entry_price) * n_contracts * multiplier` (LONG) or `(entry_price - exit_price) * n_contracts * multiplier` (SHORT) and pass that. Alternatively, `record_trade` accepts `realised_pnl` directly and skips its own cost deduction — but that breaks D-14 symmetry. The correct fix is Phase 4's responsibility: pass raw gross. Flag in the Phase 3 plan task ACs so Phase 4 picks it up.

**Warning signs:** After multiple trades, `state['account']` drops faster than expected by exactly `cost_aud * n_contracts / 2` per trade.

### Pitfall 4: `json.JSONDecodeError` Is a Subclass of `ValueError` — but NOT Vice Versa

**What goes wrong:** If the codebase does `except ValueError:` anywhere in the load path, it masks non-JSON errors (e.g., a `ValueError` raised by schema-validation code) as if they were parse errors, triggering a spurious corruption backup.

**Why it happens:** Developers reach for `ValueError` as the "parse error" type because they know `json.loads` raises it. `JSONDecodeError` (the subclass) is the correct minimal catch.

**How to avoid:** Always catch `json.JSONDecodeError`, never `ValueError`, in the load_state corruption handler. `except ValueError:` is banned inside `load_state`'s parse block.

**Warning signs:** Corruption backup files appearing when state.json is syntactically valid (test: write a valid JSON state, induce a non-JSON ValueError, observe spurious backup).

### Pitfall 5: Missing `schema_version` in Existing state.json

**What goes wrong:** A state.json written before Phase 3 (or manually) lacks `schema_version`. `_migrate()` calls `state.get('schema_version', 0)` → version=0. `MIGRATIONS[1]` runs (no-op) → state gets `schema_version=1`. This is actually safe for v1.

**Why it happens:** Greenfield deployment — state.json doesn't exist yet, so this case can't arise at Phase 3. But if Phase 7 (or a user) manually creates state.json without the key, `_migrate` handles it gracefully because `state.get('schema_version', 0)` defaults to 0 and walks up.

**How to avoid:** Document the default=0 behaviour in `_migrate` docstring. Add a named test `TestSchemaVersion::test_load_state_without_schema_version_key_migrates_to_current`.

**Warning signs:** Missing `schema_version` key in state.json after first run would be a bug in `save_state` (save must always write the current version).

### Pitfall 6: `allow_nan=False` Is Correct — But Verify Upstream

**What goes wrong:** If `state['account']` or a `positions[instrument]['entry_price']` somehow becomes `float('nan')`, `json.dumps(..., allow_nan=False)` raises `ValueError`. The run crashes and no state is saved.

**Why it happens:** NaN can leak from Phase 2 indicator math or sizing edge cases if the orchestrator doesn't guard.

**How to avoid:** `allow_nan=False` is the correct design — NaN in state is a bug. If `save_state` raises on NaN, the orchestrator (Phase 4) must catch this and treat it as a critical error, NOT silently swallow it. `record_trade` validation can defensively check `math.isfinite(trade['entry_price'])` etc., but this is Phase 4's responsibility, not Phase 3's.

**Warning signs:** `ValueError: Out of range float values are not JSON compliant` from `save_state`.

### Pitfall 7: Stale `os.name` Check — Always Use the Guard

**What goes wrong:** Parent-dir fsync guard is removed during "cleanup" or "simplification", and the code breaks on Windows.

**Why it happens:** The guard looks like defensive noise when developing on macOS only.

**How to avoid:** Keep the `if os.name == 'posix':` guard permanently. It is not dead code — it prevents breakage on any non-POSIX host.

---

## Code Examples

### Full reset_state() Return Shape

```python
# Source: [VERIFIED: cross-checked against D-01, D-03, STATE-01, system_params.py]
from system_params import INITIAL_ACCOUNT, STATE_SCHEMA_VERSION  # to be added

def reset_state() -> dict:
  '''STATE-07: fresh state, $100k account, empty collections.'''
  return {
    'schema_version': STATE_SCHEMA_VERSION,   # = 1
    'account': INITIAL_ACCOUNT,               # = 100_000.0
    'last_run': None,                         # Phase 4 sets this
    'positions': {                            # D-01: None = inactive
      'SPI200': None,
      'AUDUSD': None,
    },
    'signals': {                              # D-03: FLAT=0 for both
      'SPI200': 0,
      'AUDUSD': 0,
    },
    'trade_log': [],
    'equity_history': [],
    'warnings': [],
  }
```

### Position Round-Trip Verification

```python
# Source: [VERIFIED: direct testing in this session]
# Position TypedDict round-trips cleanly through JSON:
# - Literal['LONG', 'SHORT'] → str (preserved)
# - float | None → float or null (preserved as None after loads)
# - int → int (preserved)
# json.dumps({'trough_price': None}) → '{"trough_price": null}'
# json.loads(...) → {'trough_price': None}  (Python None, not 'null' string)
```

### AST Blocklist Extension for state_manager.py

```python
# Source: [VERIFIED: tests/test_signal_engine.py TestDeterminism::test_forbidden_imports_absent]
# Extend _HEX_PATHS_ALL to include state_manager.py:
STATE_MANAGER_PATH = Path('state_manager.py')
_HEX_PATHS_ALL = [SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH, STATE_MANAGER_PATH]

# state_manager.py ALLOWED imports: stdlib (json, os, tempfile, datetime, zoneinfo,
#   pathlib, sys, math, typing) + system_params
# state_manager.py FORBIDDEN imports (from existing FORBIDDEN_MODULES):
#   signal_engine, sizing_engine, notifier, dashboard, main, requests, schedule, yfinance
# state_manager.py ALSO FORBIDDEN: numpy, pandas (I/O hex has no indicator math)
# NOTE: state_manager.py IS the I/O hex — it IS allowed to import os, json, sys,
#       tempfile, datetime, zoneinfo, pathlib. These are REMOVED from FORBIDDEN_MODULES
#       for state_manager's parametrize slot.
# The simplest approach: create a separate FORBIDDEN_MODULES_STATE_MANAGER set
# that excludes I/O stdlib but keeps numpy/pandas/sibling hexes forbidden.
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `datetime.utcnow()` | `datetime.now(timezone.utc)` | Python 3.12 deprecation | `utcnow()` emits DeprecationWarning in 3.12; avoid in new code |
| `import pytz; pytz.timezone(...)` | `import zoneinfo; ZoneInfo(...)` | Python 3.9 (PEP 615) | `zoneinfo` is stdlib; `pytz` is third-party. Use zoneinfo for stdlib-only modules |
| `json.dumps(..., allow_nan=True)` (default) | `json.dumps(..., allow_nan=False)` | Explicit project decision | Default silently emits non-standard `NaN` token rejected by many JSON parsers |
| Manual lock files for atomic writes | `tempfile + os.replace` | Many years ago | Lock files have race conditions; os.replace is atomic on POSIX |

**Deprecated/outdated:**
- `datetime.utcnow()`: deprecated Python 3.12+; use `datetime.now(timezone.utc)` — Phase 1/2 already use the correct form; Phase 3 must match.
- `f.write + f.close + os.rename`: Non-atomic if any step fails mid-write. The `tempfile + fsync + os.replace` pattern is the correct replacement.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | warning.date should use AWST (not UTC) per CLAUDE.md "Times always AWST in user-facing output" | Pattern 4 code, append_warning | If UTC is preferred, change `now.astimezone(_AWST)` to `now` for the date format. Low risk — both produce the same date at 08:00 AWST run time (UTC midnight = AWST 08:00, same calendar date). |
| A2 | Phase 4 will pass `gross_pnl` (raw price-delta P&L) not `ClosedTrade.realised_pnl` to `record_trade` | Pitfall 3, Common Pitfalls | If Phase 4 passes realised_pnl, closing cost is double-counted. Must be an explicit Phase 4 AC. |
| A3 | `state_manager.py` constants (`INITIAL_ACCOUNT`, `MAX_WARNINGS`, `STATE_SCHEMA_VERSION`) belong in `system_params.py` | Standard Stack | If planner prefers them at module-level in `state_manager.py`, the AST guard and import patterns are unaffected. Only matters for which file gets them. |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed. (Table has 3 low-risk assumptions; A2 is the highest priority.)

---

## Open Questions

1. **Phase 4 gross_pnl vs realised_pnl boundary**
   - What we know: `record_trade` expects `trade['gross_pnl']` = raw price-delta P&L. `ClosedTrade.realised_pnl` (Phase 2 output) = gross - closing_cost. They differ by `cost_aud * n_contracts / 2`.
   - What's unclear: Phase 4 has not been planned yet. The Phase 4 orchestrator must project `ClosedTrade` → trade dict with the correct gross. This is not Phase 3's responsibility, but Phase 3's `record_trade` docstring must make the distinction explicit.
   - Recommendation: Add a named AC in the `record_trade` task that verifies `trade['gross_pnl']` is the raw price-delta P&L and that the AC includes an example value. Flag in Phase 3 PLAN as "Phase 4 must read this AC before wiring."

2. **save_state OSError on os.replace — swallow or re-raise?**
   - What we know: CONTEXT.md doesn't specify. D-08 says "atomic write" but doesn't address failure modes.
   - What's unclear: If `os.replace` fails (disk full, permissions), should `save_state` log + return silently, or re-raise?
   - Recommendation: Re-raise. `save_state` failing silently means the next `load_state` reads stale data — silent data loss is worse than a crash. Let Phase 4 orchestrator handle the exception (CLAUDE.md: "Email sends NEVER crash the workflow — Resend failure is logged and skipped"; state saves are different — data integrity matters). Planner may override.

3. **Warning date: AWST vs UTC**
   - What we know: CLAUDE.md says "Times always AWST in user-facing output"; D-09 says "the run date". Run time is 08:00 AWST = 00:00 UTC — same calendar date for both. The edge case (dates diverging) only occurs at 00:00-07:59 AWST (16:00-23:59 UTC prior day) — the system never runs then.
   - What's unclear: Whether tests should use UTC or AWST for `now=` injection.
   - Recommendation: Use AWST (via `zoneinfo`) for `warning.date` (user-facing). UTC for the backup filename suffix (ordering/uniqueness, not user-facing). Tests inject a fixed UTC `datetime` and the function converts internally — tests see the AWST-derived date string.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All of state_manager.py | ✓ | 3.11.8 (pyenv) | — |
| `zoneinfo` stdlib | `append_warning` AWST date | ✓ | Python 3.11 built-in | `pytz` (already in req.txt for later phases) |
| `os.replace` | `save_state` atomic rename | ✓ | stdlib, POSIX + Windows | — |
| `os.fsync` of dir fd | `save_state` rename durability | ✓ | POSIX only (macOS/Linux) | Skip on Windows: `if os.name == 'posix':` |
| `tempfile.NamedTemporaryFile` | `save_state` | ✓ | stdlib | — |
| `json.JSONDecodeError` | `load_state` corruption handler | ✓ | stdlib (Python 3.5+) | — |
| `pytest` 8.3.3 | test_state_manager.py | ✓ | 8.3.3 (pinned) | — |
| `pytest-freezer` | clock-dependent tests | ✗ | Not installed | `now=` parameter injection (recommended) |
| `unittest.mock.patch` | `TestAtomicity` crash simulation | ✓ | stdlib | — |
| `tmp_path` fixture | All test classes | ✓ | pytest built-in | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** `pytest-freezer` is not installed and not in requirements.txt. The fallback (inject `now=` as a parameter into all datetime-reading functions) is actually the preferred approach — cleaner than `@freeze_time` decorators and keeps functions purely testable without monkeypatching.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 |
| Config file | none — uses pytest defaults (pyproject.toml not present) |
| Quick run command | `pyenv exec python3 -m pytest tests/test_state_manager.py -x -q` |
| Full suite command | `pyenv exec python3 -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Class |
|--------|----------|-----------|-------------------|-------|
| STATE-01 | reset_state() returns dict with all 8 required top-level keys | unit | `pytest tests/test_state_manager.py::TestReset -x -q` | TestReset |
| STATE-01 | load_state() on fresh state has all 8 keys + correct types | unit | `pytest tests/test_state_manager.py::TestLoadSave -x -q` | TestLoadSave |
| STATE-02 | Atomic write: crash on os.replace leaves original intact | unit | `pytest tests/test_state_manager.py::TestAtomicity -x -q` | TestAtomicity |
| STATE-02 | Atomic write: tempfile cleaned up on failure | unit | `pytest tests/test_state_manager.py::TestAtomicity -x -q` | TestAtomicity |
| STATE-02 | Successful save: state.json readable and matches input | unit | `pytest tests/test_state_manager.py::TestLoadSave -x -q` | TestLoadSave |
| STATE-03 | Corrupt state.json triggers JSONDecodeError recovery | unit | `pytest tests/test_state_manager.py::TestCorruptionRecovery -x -q` | TestCorruptionRecovery |
| STATE-03 | Backup file `state.json.corrupt.<ts>` created in same dir | unit | `pytest tests/test_state_manager.py::TestCorruptionRecovery -x -q` | TestCorruptionRecovery |
| STATE-03 | Fresh state returned with corruption warning entry | unit | `pytest tests/test_state_manager.py::TestCorruptionRecovery -x -q` | TestCorruptionRecovery |
| STATE-04 | Schema v1 → no-op migration preserves all fields | unit | `pytest tests/test_state_manager.py::TestSchemaVersion -x -q` | TestSchemaVersion |
| STATE-04 | State without schema_version key migrates to current | unit | `pytest tests/test_state_manager.py::TestSchemaVersion -x -q` | TestSchemaVersion |
| STATE-05 | record_trade appends to trade_log with net_pnl | unit | `pytest tests/test_state_manager.py::TestRecordTrade -x -q` | TestRecordTrade |
| STATE-05 | record_trade adjusts account by net_pnl (closing-cost deducted) | unit | `pytest tests/test_state_manager.py::TestRecordTrade -x -q` | TestRecordTrade |
| STATE-05 | record_trade sets positions[instrument] = None | unit | `pytest tests/test_state_manager.py::TestRecordTrade -x -q` | TestRecordTrade |
| STATE-05 | record_trade raises ValueError on missing/invalid fields | unit | `pytest tests/test_state_manager.py::TestRecordTrade -x -q` | TestRecordTrade |
| STATE-06 | update_equity_history appends {date, equity} entry | unit | `pytest tests/test_state_manager.py::TestEquityHistory -x -q` | TestEquityHistory |
| STATE-07 | reset_state() account == 100_000.0 | unit | `pytest tests/test_state_manager.py::TestReset -x -q` | TestReset |
| STATE-07 | reset_state() positions all None, trade_log/history/warnings empty | unit | `pytest tests/test_state_manager.py::TestReset -x -q` | TestReset |
| Hex guard | state_manager.py imports only stdlib + system_params | arch | `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x -q` | TestDeterminism (extended) |
| Warnings | append_warning FIFO bound: 105 entries → 100 | unit | `pytest tests/test_state_manager.py::TestWarnings -x -q` | TestWarnings |
| Warnings | append_warning date uses AWST format | unit | `pytest tests/test_state_manager.py::TestWarnings -x -q` | TestWarnings |

### Sampling Rate

- **Per task commit:** `pyenv exec python3 -m pytest tests/test_state_manager.py -x -q`
- **Per wave merge:** `pyenv exec python3 -m pytest tests/ -q`
- **Phase gate:** Full suite green (248 baseline + Phase 3 new tests) before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_state_manager.py` — entire file (greenfield; covers STATE-01..07)
- [ ] `system_params.py` amendment — add `INITIAL_ACCOUNT = 100_000.0`, `MAX_WARNINGS = 100`, `STATE_SCHEMA_VERSION = 1`, `STATE_FILE = 'state.json'` as Phase 3 constants
- [ ] `tests/test_signal_engine.py` — extend `_HEX_PATHS_ALL` and add `STATE_MANAGER_PATH` to parametrize list for the AST blocklist test; add `FORBIDDEN_MODULES_STATE_MANAGER` set that allows I/O stdlib but blocks numpy/pandas/sibling hexes

---

## Security Domain

`security_enforcement` key is absent from config.json — treating as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | state_manager.py is local filesystem only; single-operator system |
| V3 Session Management | no | no sessions |
| V4 Access Control | no | single-operator local tool |
| V5 Input Validation | yes | `record_trade` validates all required fields; raises `ValueError` on invalid values |
| V6 Cryptography | no | state.json is local-only; encryption is explicitly out of scope (CONTEXT.md deferred) |
| V10 Malicious Code | partial | `allow_nan=False` prevents NaN injection into state; `json.JSONDecodeError` narrows the parse surface |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed trade dict from Phase 4 bug | Tampering | `record_trade` field-set validation raises ValueError before state mutation |
| NaN propagation from Phase 2 into state | Tampering | `allow_nan=False` on `json.dumps` surfaces NaN as ValueError rather than silently persisting |
| Corrupt state.json from mid-write crash | Denial of Service | Atomic write (tempfile + os.replace) prevents partial writes |
| Stale state.json persisted after crash | Denial of Service | Tempfile cleanup-on-failure in `save_state` try/finally |

---

## Sources

### Primary (HIGH confidence)

- `[VERIFIED: direct Python 3.11 testing in this session]` — All stdlib idioms (tempfile, os.replace, os.fsync, json.JSONDecodeError, zoneinfo, datetime) tested and confirmed working
- `[VERIFIED: /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/system_params.py]` — Position TypedDict definition, confirmed JSON round-trip
- `[VERIFIED: /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/sizing_engine.py]` — Phase 2 `_close_position` formula verified for gross_pnl boundary
- `[VERIFIED: /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_signal_engine.py::TestDeterminism]` — AST blocklist pattern, `FORBIDDEN_MODULES`, `_top_level_imports` helper
- `[VERIFIED: pyenv exec python3 -m pytest tests/ -q]` — 248 baseline tests passing; greenfield confirmed

### Secondary (MEDIUM confidence)

- `[CITED: CONTEXT.md D-01..D-16]` — All decisions are locked operator choices; treated as HIGH
- `[CITED: REQUIREMENTS.md STATE-01..07]` — Phase scope confirmed

### Tertiary (LOW confidence)

- `[ASSUMED: A1]` — Warning date AWST vs UTC (runtime behaviour identical at 08:00 AWST run time)
- `[ASSUMED: A2]` — Phase 4 gross_pnl projection responsibility (Phase 4 not yet planned)
- `[ASSUMED: A3]` — Constants location (`system_params.py` vs `state_manager.py`)

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — all stdlib, all verified against Python 3.11
- Architecture: HIGH — hexagonal-lite pattern established and verified in Phase 1/2
- Pitfalls: HIGH — verified via direct testing (tempfile cleanup, fsync guard, cost arithmetic)
- Phase 4 integration boundary: MEDIUM — gross_pnl vs realised_pnl distinction verified mathematically but Phase 4 planner must act on it

**Research date:** 2026-04-21
**Valid until:** 2026-05-21 (stdlib is stable; 30-day window is conservative)
