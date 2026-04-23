---
phase: 08
plan: 01
subsystem: state-schema-v2
tags: [phase-8, state-manager, system-params, migration, tier-vocabulary, clear-warnings]
requires: []
provides:
  - system_params.SPI_CONTRACTS (dict label→{multiplier,cost_aud})
  - system_params.AUDUSD_CONTRACTS (dict label→{multiplier,cost_aud})
  - system_params._DEFAULT_SPI_LABEL = 'spi-mini'
  - system_params._DEFAULT_AUDUSD_LABEL = 'audusd-standard'
  - STATE_SCHEMA_VERSION bumped from 1 → 2
  - state_manager.MIGRATIONS[2] silent v2 backfill (D-15)
  - state_manager._REQUIRED_STATE_KEYS extended with initial_account + contracts
  - state_manager.reset_state emits the two new top-level keys
  - state_manager.load_state materialises state['_resolved_contracts'] from tier labels (D-14)
  - state_manager.save_state strips all underscore-prefixed keys before json.dumps (D-14)
  - state_manager.clear_warnings helper (D-02, preserves D-10 sole-writer invariant)
affects: [state.json schema, state_manager API surface]
tech-stack:
  added: []
  patterns:
    - Runtime-only key convention via underscore-prefix filter (D-14)
    - Silent schema migration via s.get(..., default) idempotent lambda (D-15)
decisions:
  - "Locked label vocabulary baseline per D-11: SPI = {spi-mini, spi-standard, spi-full}, AUDUSD = {audusd-standard, audusd-mini}"
  - "Corrupt-recovery warning prefix 'recovered from corruption' left UNCHANGED per I1 — Plan 02 classifier matches this existing prefix; Plan 03 does NOT add a second append"
  - "reset_state now emits 10 top-level keys (was 8); existing test_reset_state_has_all_8_top_level_keys renamed to _has_all_10_ to reflect v2 schema reality"
  - "Two existing Phase 3 tests updated to include CONF-01/CONF-02 keys in their fixtures (round-trip + schema no-op migration tests) — schema v2 requires them to validate"
key-files:
  created: []
  modified:
    - system_params.py
    - state_manager.py
    - tests/test_state_manager.py
metrics:
  tasks: 3
  commits: 3
  test-suite-before: 552
  test-suite-after: 570
  new-tests: 18
  updated-existing-tests: 3
  duration-minutes: ~12
  completed: 2026-04-23
---

# Phase 8 Plan 01: State Schema v2 Foundation — Summary

Foundation for Phase 8 hardening: tier vocabulary, v2 schema migration, runtime-only `_resolved_contracts` materialisation, `clear_warnings` helper — all landed so Plans 02 and 03 can code against stable interfaces.

## What was built

### Task 1 — Tier dicts + MIGRATIONS[2] + schema bump (commit `c5f0361`)

**`system_params.py`**:
- Added `SPI_CONTRACTS` dict (lines 79-83):
  - `spi-mini`: `{multiplier: 5.0, cost_aud: 6.0}`
  - `spi-standard`: `{multiplier: 25.0, cost_aud: 30.0}`
  - `spi-full`: `{multiplier: 50.0, cost_aud: 50.0}`
- Added `AUDUSD_CONTRACTS` dict (lines 85-88):
  - `audusd-standard`: `{multiplier: 10000.0, cost_aud: 5.0}`
  - `audusd-mini`: `{multiplier: 1000.0, cost_aud: 0.5}`
- Added `_DEFAULT_SPI_LABEL = 'spi-mini'` (line 91)
- Added `_DEFAULT_AUDUSD_LABEL = 'audusd-standard'` (line 92)
- Bumped `STATE_SCHEMA_VERSION: int = 2` (line 100, was 1)
- Scalar constants `SPI_MULT`, `SPI_COST_AUD`, `AUDUSD_NOTIONAL`, `AUDUSD_COST_AUD` preserved unchanged (D-17 hex invariant for existing consumers in `main.py`, `notifier.py`, `dashboard.py`).

**`state_manager.py`**:
- Imports `SPI_CONTRACTS`, `AUDUSD_CONTRACTS`, `_DEFAULT_SPI_LABEL`, `_DEFAULT_AUDUSD_LABEL` from `system_params` (lines 53-57).
- `_REQUIRED_STATE_KEYS` extended with `'initial_account'` and `'contracts'` (line 79).
- `MIGRATIONS[2]` lambda (lines 92-99) silently backfills both keys via `s.get(..., default)` — no `append_warning`, no log (D-15).
- `reset_state` emits `'initial_account': INITIAL_ACCOUNT` and `'contracts': {'SPI200': _DEFAULT_SPI_LABEL, 'AUDUSD': _DEFAULT_AUDUSD_LABEL}` (lines 321-324) so corrupt-recovery fresh state validates under v2.

### Task 2 — load_state tier resolve + save_state underscore filter + clear_warnings helper (commit `bb355b3`)

**`state_manager.py`**:
- `load_state` happy-path (lines 379-385): after `_migrate` + `_validate_loaded_state`, materialises `state['_resolved_contracts']['SPI200'] = SPI_CONTRACTS[state['contracts']['SPI200']]` and the AUDUSD counterpart. KeyError on unknown label propagates.
- `save_state` (lines 411-414): `persisted = {k: v for k, v in state.items() if not k.startswith('_')}` — underscore-prefix filter excludes `_resolved_contracts`, `_stale_info` (Plan 03 transient), and any future runtime-only key. In-memory state is NOT mutated.
- `clear_warnings(state)` helper (lines 446-469): sets `state['warnings'] = []`, returns same dict. Full docstring documents the revised D-02 flow (clear → maybe-append → save).
- Corrupt-recovery branch at lines 343-348 (existing) left UNCHANGED — message prefix `'recovered from corruption; backup at '` stays locked per I1.

### Task 3 — 4 new test classes (commit `48c5265`)

**`tests/test_state_manager.py`**:
- Extended imports: `_migrate`, `_validate_loaded_state`, `clear_warnings` from `state_manager`; `SPI_CONTRACTS`, `AUDUSD_CONTRACTS`, `_DEFAULT_SPI_LABEL`, `_DEFAULT_AUDUSD_LABEL` from `system_params`.
- Appended `TestMigrateV2Backfill` (5 tests, line 1032): v0/v1/v2 backfill, idempotence, silent migration, schema walk to current.
- Appended `TestSaveStateExcludesUnderscoreKeys` (5 tests, line 1132): `_resolved_contracts`, arbitrary `_key`, `_stale_info` (Plan 03 regression guard), public keys persisted, in-memory non-mutation.
- Appended `TestLoadStateResolvesContracts` (4 tests, line 1218): spi-mini, spi-standard + audusd-mini, unknown-label KeyError, fresh-reset defaults.
- Appended `TestClearWarnings` (4 tests, line 1286): empties list, preserves other keys, in-place mutation, empty-list no-op.

## Acceptance evidence

### Task 1
- `grep -n "SPI_CONTRACTS" system_params.py` → 1 match (line 79)
- `grep -n "AUDUSD_CONTRACTS" system_params.py` → 1 match (line 85)
- `grep -n "_DEFAULT_SPI_LABEL: str = 'spi-mini'" system_params.py` → 1 match (line 91)
- `grep -n "_DEFAULT_AUDUSD_LABEL: str = 'audusd-standard'" system_params.py` → 1 match (line 92)
- `grep -n "STATE_SCHEMA_VERSION: int = 2" system_params.py` → 1 match (line 100)
- `grep -n "SPI_MULT: float = 5.0" system_params.py` → 1 match (line 63, preserved)
- `grep -n "'initial_account'" state_manager.py` → 4 matches (_REQUIRED_STATE_KEYS, MIGRATIONS[2] key + default, reset_state emit)
- `grep -n "2: lambda" state_manager.py` → 1 match (line 92)
- Silent migration verified:
  ```
  python -c "from state_manager import _migrate; s = {'schema_version': 0, ...}; m = _migrate(s); assert m['schema_version']==2 and m['warnings']==[]"
  → exits 0
  ```
- `grep "SPI_CONTRACTS\|AUDUSD_CONTRACTS" sizing_engine.py` → 0 matches (D-17 hex boundary preserved)
- `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` → PASSED
- `pytest tests/test_state_manager.py` → 45/45 passed (after updating 3 existing tests — see Deviations)
- `pytest tests/test_state_manager.py::TestCorruptionRecovery::test_invalid_json_triggers_backup_and_reinit_and_warning` → PASSED (prefix `'recovered from corruption'` still green)

### Task 2
- `grep -n "def clear_warnings" state_manager.py` → 1 match (line 446)
- `grep -n "_resolved_contracts" state_manager.py` → 4 matches (materialisation + docstring + comment)
- `grep -n "not k\.startswith" state_manager.py` → 1 match (line 412)
- `grep "SPI_CONTRACTS\|AUDUSD_CONTRACTS" state_manager.py` → 4 matches (imports + load_state lookups)
- `pytest tests/test_state_manager.py -q` → all green
- `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` → PASSED

### Task 3
- `grep -n "class TestMigrateV2Backfill"` → 1 match (line 1032)
- `grep -n "class TestSaveStateExcludesUnderscoreKeys"` → 1 match (line 1132)
- `grep -n "class TestLoadStateResolvesContracts"` → 1 match (line 1218)
- `grep -n "class TestClearWarnings"` → 1 match (line 1286)
- `grep -n "test_stale_info_not_persisted"` → 1 match (line 1166) — Plan 03 regression guard
- `grep -c "def test_" tests/test_state_manager.py` → 63 (was 45 baseline; +18 new tests)
- `pytest tests/test_state_manager.py::TestMigrateV2Backfill` → 5/5 PASSED
- `pytest tests/test_state_manager.py::TestSaveStateExcludesUnderscoreKeys` → 5/5 PASSED
- `pytest tests/test_state_manager.py::TestLoadStateResolvesContracts` → 4/4 PASSED
- `pytest tests/test_state_manager.py::TestClearWarnings` → 4/4 PASSED
- `pytest tests/test_state_manager.py::TestCorruptionRecovery` → 5/5 PASSED (prefix unchanged)
- `pytest -q` → **570 passed** (baseline was 552; +18 new tests, 0 regressions)

## Test coverage delta

| Class | New Tests | Lines (approx) |
|-------|-----------|----------------|
| TestMigrateV2Backfill | 5 | 1032-1130 |
| TestSaveStateExcludesUnderscoreKeys | 5 | 1132-1216 |
| TestLoadStateResolvesContracts | 4 | 1218-1284 |
| TestClearWarnings | 4 | 1286-1330 |
| **Total** | **18** | |

Baseline: 552 tests → After: 570 tests.

## Deviations from Plan

### Auto-fixed Issues (Rule 1 — pre-existing tests encoding obsolete schema)

**1. [Rule 1 - Bug] Updated 3 existing tests that encoded v1 schema assumptions**

- **Found during:** Task 1 verification (existing `pytest tests/test_state_manager.py` went from 45 green to 3 failing after the schema bump + _REQUIRED_STATE_KEYS extension).
- **Issue:** Three existing tests wrote v1-shaped states with `schema_version: STATE_SCHEMA_VERSION` (now 2) but without `initial_account` / `contracts`. Because `schema_version` already equalled `STATE_SCHEMA_VERSION`, `_migrate` skipped the backfill (version not < 2), and `_validate_loaded_state` then raised `ValueError` on the missing keys. One test explicitly asserted `set(state.keys()) == <8 keys>` which is wrong under v2.
- **Plan's acceptance criterion:** "`pytest tests/test_state_manager.py -x` exits 0 (existing Phase 3 tests still pass after _REQUIRED_STATE_KEYS extension)". The tests were incompatible as written under v2; the plan assumed extending `_REQUIRED_STATE_KEYS` would not break them, but it does.
- **Fix:** Updated 3 tests to include the CONF-01/CONF-02 keys in their fixtures. No logic change; just data-shape updates reflecting v2 reality:
  - `tests/test_state_manager.py::TestLoadSave::test_save_load_round_trip_preserves_state` — added `initial_account` + `contracts` to the fixture state dict; strip `_resolved_contracts` before equality (new runtime-only key materialised by load_state).
  - `tests/test_state_manager.py::TestReset::test_reset_state_has_all_8_top_level_keys` — renamed to `test_reset_state_has_all_10_top_level_keys`; expected_keys now includes `initial_account` and `contracts` per v2 schema.
  - `tests/test_state_manager.py::TestSchemaVersion::test_schema_v1_no_op_migration` — renamed to `test_current_schema_no_op_migration`; fixture now includes the two new keys; strip `_resolved_contracts` before equality.
- **Commit:** `c5f0361` (folded into Task 1's single commit per executor atomic-commit contract — the fix is inseparable from the schema bump).

No other deviations. No architectural decisions escalated. No auth gates encountered. Corrupt-recovery warning prefix `'recovered from corruption'` remains UNCHANGED as locked by I1.

## Confirmations

- **Locked label baseline:** `spi-mini` / `spi-standard` / `spi-full`; `audusd-standard` / `audusd-mini` (Phase 8 CONTEXT.md D-11 planner-judgment decision — no operator divergence required).
- **Corrupt-recovery warning prefix `'recovered from corruption'` is UNCHANGED** (I1 / B2 revision baseline preserved). Plan 02's classifier and Plan 03's orchestrator will match this existing prefix without modification.
- **D-17 hex boundary preserved:** `grep "SPI_CONTRACTS\|AUDUSD_CONTRACTS" sizing_engine.py` returns 0 matches. `sizing_engine.py` and `signal_engine.py` still receive explicit `multiplier` / `cost_aud_open` parameters from the orchestrator and have no label vocabulary dependency. `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` still green.
- **D-14 runtime-only rule enforced at the write boundary:** `_resolved_contracts`, `_stale_info`, and any future `_`-prefixed key are stripped by `save_state` before `json.dumps`. `TestSaveStateExcludesUnderscoreKeys::test_stale_info_not_persisted` acts as a regression guard for Plan 03's transient-signal mechanism.
- **D-15 silent migration invariant:** `TestMigrateV2Backfill::test_migrate_v2_appends_no_warning` asserts `_migrate` does not touch `state['warnings']`.

## Commits

- `c5f0361` — feat(08-01): add SPI/AUDUSD tier dicts + v2 schema migration
- `bb355b3` — feat(08-01): resolve tier labels in load_state, strip underscore keys in save_state
- `48c5265` — test(08-01): add 4 test classes for v2 migration, underscore filter, tier resolve, clear_warnings

## Self-Check: PASSED

- All 3 task commits exist in git log: confirmed
- `system_params.py` modified: confirmed (tier dicts + STATE_SCHEMA_VERSION=2)
- `state_manager.py` modified: confirmed (imports, MIGRATIONS[2], _REQUIRED_STATE_KEYS, reset_state, load_state, save_state, clear_warnings)
- `tests/test_state_manager.py` modified: confirmed (extended imports, 3 existing tests updated, 4 new classes with 18 tests appended)
- Full suite `pytest -q` exits 0: confirmed (570 passed)
- Corrupt-recovery prefix `'recovered from corruption'` unchanged: confirmed (test at line 469 still green)
- D-17 hex boundary preserved: confirmed (`sizing_engine.py` contains 0 `SPI_CONTRACTS`/`AUDUSD_CONTRACTS` references)
- No TODO/FIXME/HACK markers in delivered code: confirmed (grep returns 0 matches)
