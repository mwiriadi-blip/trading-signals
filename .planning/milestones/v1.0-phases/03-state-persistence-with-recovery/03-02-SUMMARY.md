---
phase: 03-state-persistence-with-recovery
plan: 02
subsystem: state-persistence
tags:
  - state-persistence
  - atomic-write
  - schema-migration
  - load-save
  - d-17-ordering-proof
  - b-3-no-persist-on-read
dependency_graph:
  requires:
    - 03-01 (state_manager I/O hex scaffold with 11 stubs; system_params Phase 3 constants)
  provides:
    - _atomic_write with D-17 post-replace dir fsync ordering (STATE-02 durability)
    - _migrate walk-forward via MIGRATIONS dict (STATE-04)
    - save_state (sort_keys=True, indent=2, allow_nan=False, OSError re-raise)
    - load_state happy path (file exists + parse + migrate) and missing-file path (B-3 no-persist contract)
    - 12 test methods structurally locking STATE-01 / STATE-02 / STATE-04 + D-17 + B-3
  affects:
    - 03-03 (corruption recovery, reset_state, append_warning, _backup_corrupt, _validate_loaded_state D-18 — will refactor load_state's missing-file literal to call reset_state())
    - 03-04 (record_trade, update_equity_history, _validate_trade D-15/D-19, B-4 finiteness)
tech-stack:
  added: []
  patterns:
    - "tempfile.NamedTemporaryFile(dir=parent, delete=False, mode='w', suffix='.tmp') for same-FS atomic write"
    - "post-replace parent-dir fsync on POSIX (D-17 ordering) for rename durability against power loss"
    - "json.dumps(sort_keys=True, indent=2, allow_nan=False) for byte-deterministic git-friendly persistence"
    - "MIGRATIONS dict walk-forward with state.get('schema_version', 0) default for legacy keyless state"
    - "MagicMock parent with recording wrapper functions to capture cross-module call ORDER (distinguishing file-fsync from dir-fsync via sentinel _DIR_FD)"
    - "raise ... from exc chaining on wave-deferred NotImplementedError inside except blocks (ruff B904 compliance)"
key-files:
  created:
    - .planning/phases/03-state-persistence-with-recovery/03-02-SUMMARY.md
  modified:
    - state_manager.py (4 stubs → implementations; net -3 NotImplementedError stubs + 1 inline Wave 2 stub in corruption branch)
    - tests/test_state_manager.py (3 classes populated with 12 tests; other 5 classes remain `pass`)
decisions:
  - "D-17 ordering implemented and structurally proven: `os.replace` runs BEFORE parent-dir `os.fsync` (contrary to RESEARCH.md §Pattern 1). Test method test_atomic_write_fsyncs_parent_dir_after_os_replace uses a MagicMock parent + sentinel _DIR_FD=99999 to capture the cross-call order and assert replace_idx < dir_fsync_idx."
  - "B-3 contract documented in load_state docstring AND enforced by test (`assert not path.exists()` after `load_state(missing_path)`). load_state on a missing path returns a fresh-state literal and DOES NOT call save_state — the orchestrator (Phase 4) owns file materialization."
  - "Recording wrappers in the D-17 ordering test use `*args, **kwargs` rather than fixed-arity signatures because NamedTemporaryFile internally calls `os.open(path, flags, mode)` with 3 positional args — the original plan wording (2-arg signatures) would have produced a TypeError. Documented inline; no plan deviation because the test still proves the D-17 contract as specified."
  - "B904 chained-raise on the Wave 2 corruption-branch stub: `except json.JSONDecodeError as exc: raise NotImplementedError(...) from exc`. Rule 3 auto-fix (ruff blocked commit otherwise)."
  - "NotImplementedError count landed at 9 grep-hits (8 actual raises + 1 docstring mention), not 7 as the plan AC claimed. Plan AC math assumed 10 Wave-0 stubs; 03-01-SUMMARY confirms 11 stubs landed. Correct math: 11 Wave-0 stubs - 4 replaced + 1 new inline = 8 raises; grep also catches the docstring reference (line 216) for a total of 9 matches. Plan AC was an arithmetic error, not a code defect; stub accounting matches 03-01's actual output."
metrics:
  duration_minutes: ~22
  completed: 2026-04-21
  tasks_total: 2
  tasks_completed: 2
  files_created: 0 (SUMMARY.md is planning artifact, not code)
  files_modified: 2
  tests_before: 249
  tests_after: 261
  new_tests: 12
  stub_count_before: 11
  stub_count_after: 8
---

# Phase 3 Plan 02: Wave 1 — Atomic Write + Load/Save Happy Path Summary

Wave 1 fills in the four Wave 0 stubs that land the atomic-write durability
foundation for Phase 3: `_atomic_write`, `_migrate`, `save_state`, and the
happy + missing-file branches of `load_state`. Two commits, 12 new test
methods, a structural proof of the D-17 post-replace fsync ordering, and
the B-3 "no side-effect on read" contract documented + test-locked.

## One-liner

Atomic `save_state` + `load_state` (happy + missing-file) implemented with
D-17 post-replace parent-dir fsync and B-3 no-persist-on-read contract;
12 tests structurally enforce STATE-01 / STATE-02 / STATE-04 + D-17 + B-3.

## Functions Implemented

### `_atomic_write(data: str, path: Path) -> None`  (STATE-02 / D-08 amended by D-17)

Canonical durable-write sequence:

```
1. write data to tempfile (same dir as target, suffix='.tmp')
2. flush + fsync(tempfile.fileno())
3. close tempfile (NamedTemporaryFile context exit)
4. os.replace(tempfile, target)      <-- atomic rename
5. fsync(parent dir fd) on POSIX     <-- D-17: post-replace for rename durability
```

Key correctness properties:

- **D-17 ordering enforced in code:** `os.replace` call appears at a lower
  source-line offset than `os.fsync(dir_fd)` inside the `_atomic_write`
  function body. A one-shot AST-style grep in the plan AC proves this; the
  structural test in `tests/test_state_manager.py` proves it at runtime.
- **POSIX guard** (`if os.name == 'posix':`) preserved per Pitfall 2 so
  Windows environments don't crash on parent-dir fsync (Windows' rename
  durability is handled differently by NTFS).
- **Tempfile cleanup** via try/finally: if any step before `os.replace`
  raises, `os.unlink(tmp_path_str)` removes the half-written tempfile.
  `FileNotFoundError` swallowed (Pitfall 1) because a concurrent
  NamedTemporaryFile cleanup can race the explicit unlink. On success,
  `tmp_path_str = None` makes the finally block a no-op.

### `_migrate(state: dict) -> dict`  (STATE-04)

```python
version = state.get('schema_version', 0)
while version < STATE_SCHEMA_VERSION:
  version += 1
  state = MIGRATIONS[version](state)
state['schema_version'] = STATE_SCHEMA_VERSION
return state
```

- Missing `schema_version` defaults to 0 (Pitfall 5), walking
  `MIGRATIONS[1..STATE_SCHEMA_VERSION]` in order.
- At STATE_SCHEMA_VERSION=1 with MIGRATIONS[1]=lambda s:s, this is an
  identity pass for v1 state AND a single-step walk for keyless state.
- Re-setting `state['schema_version']` at the end is the idempotent
  contract — tests verify loaded.schema_version == STATE_SCHEMA_VERSION
  even when starting from a keyless dict.

### `save_state(state: dict, path: Path) -> None`  (STATE-02 / D-08 amended by D-17)

```python
data = json.dumps(state, sort_keys=True, indent=2, allow_nan=False)
_atomic_write(data, path)
```

- **sort_keys=True** produces git-friendly byte-deterministic output.
- **indent=2** matches project convention.
- **allow_nan=False** makes NaN a ValueError at the boundary, not a
  silent `NaN` token in JSON (Pitfall 6).
- **OSError re-raise:** not caught inside save_state. Per RESEARCH §Open
  Question 2 and CLAUDE.md "data integrity > silent failure", the
  orchestrator (Phase 4) handles the exception. Test
  `test_crash_on_os_replace_leaves_original_intact` verifies both the
  OSError propagation AND that state.json is byte-identical to the
  pre-call original.

### `load_state(path: Path, now=None) -> dict`  (partial — STATE-01 / STATE-04)

Branches:

1. **Missing file (B-3 contract):** returns a fresh-state literal dict
   with all 8 top-level keys at default values (`schema_version=1`,
   `account=100_000.0`, `last_run=None`, `positions={SPI200:None,
   AUDUSD:None}`, `signals={SPI200:0, AUDUSD:0}`, empty lists for the
   three sequences). Does **NOT** call `save_state` — the file is not
   created on read. Orchestrator (Phase 4) must call
   `save_state(state)` explicitly after first-run `load_state()` to
   materialize `state.json`. Wave 2 will refactor this literal to call
   `reset_state()` once that stub is filled.
2. **Happy path (file exists + valid JSON):** reads bytes, parses via
   `json.loads`, walks `_migrate` forward, returns. Wave 2 will insert
   a `_validate_loaded_state(state)` call (D-18) between `_migrate` and
   the return.
3. **Corruption (JSONDecodeError):** raises
   `NotImplementedError('Wave 2: implement corruption recovery branch')`
   with `from exc` chaining for ruff B904. Wave 2 implements the
   backup + reinit + warning flow.

## Tests Added (12 methods, 3 classes)

### `TestLoadSave` (5 tests)

| Test | Proves |
|------|--------|
| `test_save_state_creates_readable_file` | STATE-02: file created; JSON parses; content equals input |
| `test_save_state_is_deterministic_byte_identical` | sort_keys + indent=2 → byte-identical re-save; contains `b'\n  '` |
| `test_save_state_raises_on_nan` | allow_nan=False → ValueError on NaN (Pitfall 6) |
| `test_load_state_missing_file_returns_fresh_shape` | STATE-01 default shape + **B-3 `assert not path.exists()` post-call** |
| `test_save_load_round_trip_preserves_state` | Full populated state survives save→load bit-for-bit (nested Position, trade_log, equity_history, warnings) |

### `TestAtomicity` (4 tests — includes D-17 ordering proof)

| Test | Proves |
|------|--------|
| `test_crash_on_os_replace_leaves_original_intact` | STATE-02: mocked OSError on os.replace → state.json bytes unchanged |
| `test_tempfile_cleaned_up_on_failure` | Pitfall 1: try/finally unlinks tempfile after OSError (no leftover `*.tmp`) |
| `test_save_state_on_clean_disk_leaves_no_tempfile` | Success path also cleans up (NamedTemporaryFile context exit) |
| `test_atomic_write_fsyncs_parent_dir_after_os_replace` | **D-17: `os.replace` call recorded BEFORE `os.fsync(dir_fd)` call in parent-mock `mock_calls` order** |

The D-17 ordering proof is worth expanding on: a single `MagicMock`
parent captures all four wrapped operations (`os.replace`, `os.fsync`,
`os.open`, `os.close`) in one ordered `mock_calls` list. To distinguish
the parent-dir fsync from the file fsync (both call `os.fsync` on real
file descriptors), `recording_open` returns a sentinel `_DIR_FD =
99999` for `O_RDONLY` opens (which is the pattern `_atomic_write` uses
for the parent dir). `recording_fsync` then tags dir-fsync calls as
`os_fsync_dir` and file-fsync calls as `os_fsync_file` in the parent
mock's call history. The assertion checks that
`call_names.index('os_replace') < call_names.index('os_fsync_dir')`.
If Wave 1's `_atomic_write` is ever reverted to RESEARCH.md §Pattern 1's
pre-replace ordering, this test fails with a readable error citing D-17.

### `TestSchemaVersion` (3 tests)

| Test | Proves |
|------|--------|
| `test_migrations_dict_has_v1_no_op` | MIGRATIONS[1] is identity (pure unit test on the module-level dict) |
| `test_schema_v1_no_op_migration` | A v1 state on disk round-trips through save→load with every field preserved |
| `test_load_state_without_schema_version_key_migrates_to_current` | Keyless state (Pitfall 5) migrates to STATE_SCHEMA_VERSION via `state.get(..., 0)` |

## Functions Still Stubbed (7 stubs remain)

| Function | Wave | Purpose |
|----------|------|---------|
| `reset_state` | 2 | Canonical fresh-state shape — Wave 2 will also refactor load_state's missing-file literal to call this |
| `append_warning` | 2 | D-09/D-10/D-11 FIFO warnings with AWST date |
| `_backup_corrupt` | 2 | D-06 + B-1 + B-2 corrupt-state rename with microsecond timestamp |
| `_validate_loaded_state` | 2 | D-18 post-parse key-presence validation (ValueError on missing required keys) |
| `_validate_trade` | 3 | D-15 + D-19 all-11-field trade dict validation |
| `record_trade` | 3 | D-13/D-14/D-15/D-16/D-19/D-20 closing-half cost deduction + account adjust |
| `update_equity_history` | 3 | STATE-06 + D-04 + B-4 equity-history append with boundary validation |

And the inline `NotImplementedError` in `load_state`'s JSONDecodeError
branch (Wave 2 replaces with backup+reinit+warn+save flow).

## Requirements Covered

- **STATE-01 partial** — `load_state` happy path + missing-file path with
  B-3 no-persist contract. Corruption recovery deferred to Wave 2.
- **STATE-02 complete** — atomic write durability with D-17 ordering
  structurally locked; crash safety + tempfile cleanup proven.
- **STATE-04 complete** — MIGRATIONS dict walk-forward with keyless
  default; v1 no-op verified.

## D-17 Enforcement — Structural Receipts

Two independent artifacts prove D-17 ordering:

1. **Source-level:** the plan's line-order grep AC
   (`pyenv exec python3 -c "src=open('state_manager.py').read(); body=src.split('def _atomic_write')[1].split('def ')[0]; replace_idx=body.find('os.replace('); fsync_dir_idx=body.find('os.fsync(dir_fd)'); assert replace_idx > 0 and fsync_dir_idx > 0 and replace_idx < fsync_dir_idx"`)
   exits 0. This checks the `_atomic_write` function body text for D-17
   at plan-gate time — a reviewer-only defense.
2. **Runtime:** the `test_atomic_write_fsyncs_parent_dir_after_os_replace`
   test captures the actual call sequence at runtime. This is the test
   that fails if a future refactor reverts the ordering.

## B-3 Contract — Documented + Proven

The `load_state` docstring explicitly says:
> "If path does not exist: returns a fresh state dict. The file is NOT
> created on this call (B-3 — no side-effect on read; state_manager.py
> never auto-saves on load). The orchestrator (Phase 4) must explicitly
> call save_state(state) after load_state on first run to materialize
> state.json."

And `test_load_state_missing_file_returns_fresh_shape` includes:
> `assert not path.exists(), 'B-3: load_state on missing path must NOT create state.json; orchestrator owns file materialization via explicit save_state(state)'`

Both grep ACs pass.

## Commits

| Task | Hash     | Commit Message |
|-----:|----------|----------------|
| 1    | 2f11db8  | feat(03-02): implement _atomic_write (D-17 ordering), _migrate, save_state, load_state happy+missing-file |
| 2    | 630c8b3  | test(03-02): populate TestLoadSave + TestAtomicity (D-17 proof) + TestSchemaVersion — 12 tests |

## Test Count Delta

| Metric | Before | After | Delta |
|--------|-------:|------:|------:|
| Full suite pass count | 249 | 261 | +12 |
| `tests/test_state_manager.py` passing | 0 | 12 | +12 |
| `state_manager.py` NotImplementedError raises | 11 | 8 | -3 |
| `state_manager.py` NotImplementedError grep hits | 11 | 9 | -2 (9 = 8 raises + 1 docstring mention) |
| `tests/test_state_manager.py` populated classes | 0 | 3 | +3 |
| `tests/test_state_manager.py` `pass`-stub classes | 8 | 5 | -3 |

## Verification Gate Results

| Gate | Result |
|------|--------|
| `pytest tests/test_state_manager.py::TestLoadSave TestAtomicity TestSchemaVersion -x -q` | 12/12 PASS |
| `pytest tests/test_state_manager.py::TestAtomicity::test_atomic_write_fsyncs_parent_dir_after_os_replace -x -v` | 1/1 PASS (D-17 ordering) |
| `pytest tests/test_state_manager.py::TestLoadSave::test_load_state_missing_file_returns_fresh_shape -x -v` | 1/1 PASS (B-3 contract) |
| `pytest tests/test_signal_engine.py tests/test_sizing_engine.py -q` | 232/232 PASS (Phase 1+2 regression) |
| `pytest tests/test_signal_engine.py::TestDeterminism::test_state_manager_no_forbidden_imports -x -q` | 1/1 PASS (AST guard) |
| `pytest tests/ -q` | 261/261 PASS (full suite) |
| `ruff check state_manager.py tests/test_state_manager.py` | All checks passed |

## Deviations from Plan

### Rule 1 - Bug (auto-fixed during Task 2)

**1. Recording-wrapper signatures in D-17 ordering test**

- **Found during:** Task 2 first test run
- **Issue:** The plan's recording wrappers used fixed 2-arg / 1-arg
  signatures (`def recording_open(name, flags)`, `def recording_close(fd)`,
  etc.). But `NamedTemporaryFile` internally calls
  `os.open(path, flags, mode=0o600)` with 3 positional args, which
  produced `TypeError: recording_open() takes 2 positional arguments but
  3 were given` and the test failed.
- **Fix:** Changed all four recording wrappers to `*args, **kwargs`
  signatures that forward extra arguments to the real stdlib functions.
  The D-17 contract proof is unchanged — only the wrappers' arity was
  generalized.
- **Files modified:** `tests/test_state_manager.py`
  `test_atomic_write_fsyncs_parent_dir_after_os_replace` method body
- **Commit:** `630c8b3` (same commit as the test-population work; caught
  and fixed before commit)

### Rule 3 - Blocking fix (auto-fixed during Task 1)

**2. Ruff B904 on Wave 2 corruption stub**

- **Found during:** Task 1 ruff gate
- **Issue:** `except json.JSONDecodeError: raise NotImplementedError(...)`
  triggered B904 because the re-raise didn't chain the original exception.
- **Fix:** `except json.JSONDecodeError as exc: raise
  NotImplementedError(...) from exc`.
- **Files modified:** `state_manager.py` load_state body
- **Commit:** `2f11db8`

### Non-deviation documented for clarity

**3. NotImplementedError grep-count math**

The plan's acceptance criterion stated `grep -F 'NotImplementedError'
state_manager.py` returns 7. The actual count is 9 (8 real raises + 1
docstring mention on line 216 where the docstring says "Wave 1:
corruption branch raises NotImplementedError('Wave 2: ...')"). Plan AC
math assumed Wave 0 had 10 stubs; 03-01-SUMMARY confirms 11 stubs
landed (5 private + 6 public, not 5 + 5). Correct math: 11 Wave-0
raises - 4 replaced by this plan + 1 new inline corruption stub = 8
remaining raises; grep additionally catches the docstring reference for
9 total hits. **Code matches the plan's intent** (4 stubs replaced,
corruption branch stays for Wave 2); only the AC arithmetic was off by
one baseline. No code change needed.

## Wave 2 Hand-off Notes

Wave 2 (plan 03-03) must:

1. **Implement `reset_state`** — canonical fresh-state shape. Then refactor
   `load_state`'s missing-file branch from the literal dict to
   `return reset_state()`. Update the TestLoadSave default-shape test
   fixture to keep using the literal dict (already matches reset_state()
   output by construction, but document the structural equivalence).
2. **Implement corruption-recovery branch** in `load_state`:
   `_backup_corrupt(path, now)` + `reset_state()` + `append_warning(state,
   'state_manager', 'loaded corrupt state; backed up to {backup_name}',
   now=now)` + `save_state(state, path)` + `return state`. Note: this
   branch DOES persist (unlike the missing-file branch) because recovery
   must rewrite state.json.
3. **Implement `_validate_loaded_state`** (D-18) and call it in
   `load_state`'s happy path AFTER `_migrate(state)` but BEFORE return.
   Runs OUTSIDE the JSONDecodeError except block so semantic bugs raise
   ValueError cleanly rather than masquerading as corruption.
4. **Implement `append_warning`** (D-09/D-10/D-11) with AWST date and
   MAX_WARNINGS FIFO bound.

## Self-Check: PASSED

**File existence:**
- `state_manager.py` (modified): FOUND
- `tests/test_state_manager.py` (modified): FOUND
- `.planning/phases/03-state-persistence-with-recovery/03-02-SUMMARY.md` (this file): FOUND

**Commit existence (in worktree branch history):**
- `2f11db8` feat(03-02): FOUND
- `630c8b3` test(03-02): FOUND

**Verification gates (all green):**
- Full test suite: 261/261 PASS
- Phase 3 targeted: 12/12 PASS
- D-17 ordering test: PASS (structural proof)
- B-3 contract test: PASS (assert not path.exists)
- Phase 1/2 regression: 232/232 PASS
- AST guard: PASS
- Ruff: clean on both touched files
