---
phase: 03-state-persistence-with-recovery
plan: 01
subsystem: state-persistence
tags:
  - scaffolding
  - hexagonal-lite
  - ast-blocklist
  - i-o-hex
  - wave-0
dependency_graph:
  requires:
    - phase-02-sizing-engine-closed (Position TypedDict, cost constants)
  provides:
    - state_manager module surface (6 public + 5 private stubs) that Waves 1-3 fill in
    - system_params Phase 3 constants (INITIAL_ACCOUNT, MAX_WARNINGS, STATE_SCHEMA_VERSION, STATE_FILE)
    - FORBIDDEN_MODULES_STATE_MANAGER AST guard for the I/O hex
    - 8 dimension-named test class skeletons (TestLoadSave..TestSchemaVersion)
  affects:
    - 03-02 (load_state happy + missing-file, save_state, _atomic_write D-17, _migrate, TestSchemaVersion/TestLoadSave/TestAtomicity)
    - 03-03 (corruption recovery, reset_state, append_warning, _backup_corrupt, _validate_loaded_state D-18)
    - 03-04 (record_trade, update_equity_history, _validate_trade D-15/D-19, B-4 finiteness, import math)
tech-stack:
  added: []
  patterns:
    - "forward-declared imports with `# noqa: F401 — used in Wave X` comments (mirrors sizing_engine.py precedent)"
    - "frozenset module-level constants (_REQUIRED_TRADE_FIELDS, _REQUIRED_STATE_KEYS) populated in Wave 0 for downstream use"
    - "dedicated FORBIDDEN_MODULES_STATE_MANAGER set for I/O-hex allow-list (stdlib + system_params permitted; sibling hexes + numpy/pandas + network blocked)"
key-files:
  created:
    - state_manager.py
    - tests/test_state_manager.py
  modified:
    - system_params.py
    - tests/test_signal_engine.py
decisions:
  - "D-17 ordering surfaced in `_atomic_write` docstring (post-replace dir fsync) so Wave 1 implements it correctly"
  - "D-18 stub (`_validate_loaded_state`) added now even though Wave 2 implements it — avoids symbol churn mid-wave"
  - "`import math` deliberately deferred to Wave 3 (D-19/B-4) to avoid unused-import warnings in Waves 1-2; AST guard already permits it (stdlib)"
  - "Forward-declared imports use `# noqa: F401` comments per sizing_engine.py precedent — keeps the import block stable across waves so AST guard remains green"
  - "FORBIDDEN_MODULES_STATE_MANAGER is separate from FORBIDDEN_MODULES because the I/O hex's allow-list (os/json/datetime/tempfile/zoneinfo/pathlib/sys/math) would fail the pure-math blocklist — symmetric hex boundary enforced with asymmetric allow-lists"
metrics:
  duration_minutes: ~20
  completed: 2026-04-21
  tasks_total: 4
  tasks_completed: 4
  files_created: 2
  files_modified: 2
  tests_before: 248
  tests_after: 249  # +1 new AST guard
  new_stub_count: 11  # 6 public + 5 private NotImplementedError
---

# Phase 3 Plan 01: Wave 0 Scaffold Summary

Wave 0 BLOCKING scaffold for Phase 3 state persistence. Four files touched,
four commits, 11 NotImplementedError stubs landed, and the hexagonal-lite AST
blocklist is extended so Wave 1+ commits that accidentally import
signal_engine/sizing_engine/numpy/pandas/etc. into state_manager.py fail the
test suite immediately.

## Files Created

### `state_manager.py` (at repo root, I/O hex)

- Module docstring documents D-01..D-20 plus B-1..B-5 amendments and the
  CRITICAL Phase 4 boundary warning on `gross_pnl` (must be RAW price-delta
  P&L, NOT Phase 2's `ClosedTrade.realised_pnl` — double-counting of closing
  cost otherwise).
- 6 public function stubs: `load_state`, `save_state`, `record_trade`,
  `update_equity_history`, `reset_state`, `append_warning`. All bodies are
  `raise NotImplementedError(...)` with a wave annotation.
- 5 private helper stubs: `_atomic_write`, `_migrate`, `_backup_corrupt`,
  `_validate_trade`, and **`_validate_loaded_state`** (the D-18 addition
  landed in Wave 0 per the reviews-revision pass so Wave 2 doesn't have to
  introduce a new symbol mid-wave).
- Module-level constants populated NOW (pure data — no stubs):
  - `_AWST = zoneinfo.ZoneInfo('Australia/Perth')`
  - `_REQUIRED_TRADE_FIELDS` frozenset (11 fields per D-15)
  - `_REQUIRED_STATE_KEYS` frozenset (8 top-level keys for D-18)
  - `MIGRATIONS` dict with v1 → no-op lambda (proves the walk-forward hook)
- Import block covers Waves 1/2 needs (json, os, sys, tempfile, zoneinfo,
  datetime/timezone, pathlib, typing.Any) with `# noqa: F401` comments per
  `sizing_engine.py` precedent. **`import math` deliberately NOT added in
  Wave 0** — Wave 3 adds it when implementing D-19 (finiteness in
  `_validate_trade`) and B-4 (equity finiteness in
  `update_equity_history`). `math` is stdlib, so the AST allow-list already
  permits it.

### `tests/test_state_manager.py` (at `tests/`)

- 8 empty class skeletons (one per concern dimension per D-13):
  `TestLoadSave`, `TestAtomicity`, `TestCorruptionRecovery`,
  `TestRecordTrade`, `TestEquityHistory`, `TestReset`, `TestWarnings`,
  `TestSchemaVersion`. Each class docstring references the D-XX amendments
  (D-17/D-18/D-19/D-20/B-1/B-2/B-4/B-5) so downstream wave agents see the
  contract scope at the header.
- `_make_trade` helper fully populated (pure data; used across Wave 3
  `TestRecordTrade` tests). Docstring surfaces the D-14 `gross_pnl` formula
  and the Phase 4 boundary warning.
- Module-level path constants `STATE_MANAGER_PATH` + `TEST_STATE_MANAGER_PATH`
  mirror the `test_signal_engine.py` pattern — Task 4 wires them into the
  AST guard.
- pytest collects 0 tests (expected for Wave 0 skeletons, exit 5 on the
  bare file; collection shows all 8 classes without error).

## Files Modified

### `system_params.py`

- Added Phase 3 constants block between `AUDUSD_COST_AUD` (line ~67) and the
  `Position` TypedDict section header. Four constants added:
  - `INITIAL_ACCOUNT: float = 100_000.0` (STATE-07, reset_state seed)
  - `MAX_WARNINGS: int = 100` (D-11 FIFO bound)
  - `STATE_SCHEMA_VERSION: int = 1` (STATE-04 walk-forward)
  - `STATE_FILE: str = 'state.json'` (SPEC.md §FILE STRUCTURE)
- Module docstring updated to include `state_manager.py (Phase 3 I/O hex)` in
  the Architecture line and added a `D-XX (Phase 3)` docstring line pointing
  at the new constants.

### `tests/test_signal_engine.py`

Four in-place edits inside the `TestDeterminism` block — no other parts of the
file were altered:

1. Two new path constants after `TEST_SIZING_ENGINE_PATH`:
   `STATE_MANAGER_PATH = Path('state_manager.py')`,
   `TEST_STATE_MANAGER_PATH = Path('tests/test_state_manager.py')`.
2. New `FORBIDDEN_MODULES_STATE_MANAGER` frozenset after
   `FORBIDDEN_MODULES_STDLIB_ONLY`. Blocks sibling hexes, network libs,
   numpy/pandas, scheduler, dotenv, yfinance, pytz. Omits stdlib I/O
   (os/json/tempfile/datetime/zoneinfo/pathlib/sys) and `math` — those are
   the I/O hex's purpose.
3. New test method `test_state_manager_no_forbidden_imports` inside
   `TestDeterminism` (parametrized on `[STATE_MANAGER_PATH]`). Passes
   against the Task 2 stub.
4. Extended `test_no_four_space_indent.covered_paths` with `STATE_MANAGER_PATH`
   + `TEST_STATE_MANAGER_PATH` so the 2-space indent convention is enforced
   for Phase 3 files.

## New Public Constants / Symbols Exposed

**From `system_params.py`:**
- `INITIAL_ACCOUNT` (100_000.0)
- `MAX_WARNINGS` (100)
- `STATE_SCHEMA_VERSION` (1)
- `STATE_FILE` ('state.json')

**From `state_manager.py`:**
- `MIGRATIONS` dict (v1 no-op)
- 6 public function stubs (see above)

**From `tests/test_signal_engine.py`:**
- `STATE_MANAGER_PATH`, `TEST_STATE_MANAGER_PATH` (path constants)
- `FORBIDDEN_MODULES_STATE_MANAGER` (I/O-hex allow-list's denied set)

## D-18 Stub Helper Note

The D-18 amendment (from the 2026-04-21 reviews-revision pass) introduced
`_validate_loaded_state` as a Wave 2 helper. The stub signature is added
**in Wave 0** (this plan) so that Wave 2 does not need to introduce a new
module-level symbol mid-implementation. The `_REQUIRED_STATE_KEYS` frozenset
is populated NOW (not stubbed) because it is pure data — Wave 2's validator
implementation can reference it directly without import churn.

**Total stub count at end of Wave 0:** 11 (5 private + 6 public).

## Wave 3 Import Deferment Note

`import math` is NOT added in Wave 0 despite being needed by Wave 3
(`_validate_trade` D-19 finiteness checks + `update_equity_history` B-4
equity finiteness check). Adding it now would produce a ruff unused-import
warning during Waves 1-2 that would have to be suppressed via `# noqa: F401`
and later un-suppressed. Simpler: Wave 3 adds the import as part of its own
work. The AST blocklist already permits `math` because state_manager.py's
allow-list is "stdlib + system_params" rather than an enumerated whitelist,
so no AST-guard update is needed when Wave 3 adds it.

## Critical Phase 4 Boundary Warning Location

**File:** `state_manager.py`, `record_trade` docstring (lines ~220-238).

Exact text (verbatim):

> `trade['gross_pnl']` MUST be raw price-delta P&L:
>   (exit_price - entry_price) * n_contracts * multiplier  (LONG)
>   (entry_price - exit_price) * n_contracts * multiplier  (SHORT)
> It MUST NOT be Phase 2's `ClosedTrade.realised_pnl` — that already has the
> closing cost deducted by Phase 2 `_close_position`. Passing `realised_pnl`
> as `gross_pnl` causes double-counting of the closing cost. Phase 4
> orchestrator is responsible for this projection.

Mirrored in `tests/test_state_manager.py::_make_trade` docstring so Wave 3
test authors cannot miss it.

## Test Count Delta

| Metric                              | Before | After | Delta |
|-------------------------------------|-------:|------:|------:|
| Passing tests (full suite)          | 248    | 249   | +1    |
| New AST guards (TestDeterminism)    | —      | 1     | +1    |
| Empty test class skeletons          | —      | 8     | +8    |
| state_manager stubs (NotImplementedError) | —      | 11    | +11   |

## Commits

| Task | Hash    | Commit Message                                                                       |
|-----:|---------|--------------------------------------------------------------------------------------|
| 1    | 43be2a0 | feat(03-01): add Phase 3 constants block to system_params.py                         |
| 2    | d755d85 | feat(03-01): scaffold state_manager.py I/O hex with 11 stub signatures               |
| 3    | 233c050 | test(03-01): add tests/test_state_manager.py skeleton with 8 class stubs             |
| 4    | 3422657 | test(03-01): extend TestDeterminism AST blocklist to enforce state_manager.py hex    |

## Deviations from Plan

**None — plan executed exactly as written**, with two notable tactical
choices explicitly allowed by the plan:

1. **Ruff auto-fix on state_manager.py** (Task 2): after the initial write,
   ruff re-wrapped the `from datetime import datetime, timezone` line into a
   multi-line form because the `# noqa: F401 — used in ...` comment pushed
   the line past 100 chars. This is a pure formatting adjustment and does
   not change the imported symbols. Plan AC `pyenv exec python3 -m ruff check
   state_manager.py` exits 0 — satisfied.
2. **`# noqa: F401` comments on forward-declared imports** (Task 2): the
   plan's imports block (json/os/sys/tempfile/zoneinfo/datetime/pathlib/
   typing/system_params constants) all produce F401 warnings during Wave 0
   because every function body is `raise NotImplementedError(...)`. Applied
   the `# noqa: F401 — used in Wave X` pattern established by
   `sizing_engine.py` (see lines 20-27) so the plan's intent of "stable
   import block across waves" is achieved without ruff noise. Pure
   structural parity with Phase 2 Wave 0; no semantic change.

## Self-Check: PASSED

**File existence:**
- `state_manager.py`: FOUND
- `tests/test_state_manager.py`: FOUND
- `system_params.py` (modified): FOUND (pre-existing, edited)
- `tests/test_signal_engine.py` (modified): FOUND (pre-existing, edited)

**Commit existence (in current branch history):**
- 43be2a0 Task 1: FOUND
- d755d85 Task 2: FOUND
- 233c050 Task 3: FOUND
- 3422657 Task 4: FOUND

**Verification gates (all green):**
- Constants importable: OK
- Public surface stubbed: OK
- D-18 stub helper + _REQUIRED_STATE_KEYS: OK
- Test scaffold collects (0 tests, 8 classes, no errors): OK
- `test_state_manager_no_forbidden_imports` passes: OK
- `test_no_four_space_indent` passes with new paths: OK
- Full test suite: 249 passes
- Ruff: all four touched files clean
