---
phase: 14-trade-journal-mutation-endpoints
plan: 02
subsystem: state-manager
tags: [fcntl, cross-process, schema-migration, mutate-state, lost-update-fix, hex-boundary, tdd]

# Dependency graph
requires:
  - phase: 14-trade-journal-mutation-endpoints
    plan: 01
    provides: 'TestFcntlLock + TestSchemaMigrationV2ToV3 skeletons; tests/fixtures/state_v2_no_manual_stop.json (v2 fixture for round-trip)'
  - phase: 8-config-conf-cli
    provides: 'STATE_SCHEMA_VERSION = 2 v1->v2 migration framework + W3 invariant ("2 saves per run")'
provides:
  - 'state_manager.mutate_state(mutator, path) — public helper holds fcntl.LOCK_EX across the FULL load -> mutate -> save critical section (REVIEWS HIGH #1 fix; T-14-01 lost-update race -> FULLY MITIGATED)'
  - 'state_manager._atomic_write — wrapped with fcntl.LOCK_EX advisory lock on destination file (D-13)'
  - 'state_manager._migrate_v2_to_v3 + MIGRATIONS[3] — backfills manual_stop=None on every non-None Position dict'
  - 'state_manager._atomic_write_unlocked + _save_state_unlocked — internal helpers used by mutate_state to avoid intra-process flock-on-different-fd deadlock'
  - 'system_params.STATE_SCHEMA_VERSION = 3; Position TypedDict gains manual_stop: float | None'
  - 'main.py daily loop migrates 3 save_state sites (run_daily_check step 9 + dispatch helper + --reset) to mutate_state'
  - 'TestFcntlLock + TestMutateState + TestSchemaMigrationV2ToV3 — 15 new tests; full test_state_manager.py 82 passed'
affects: [14-03, 14-04, 14-05]

# Tech tracking
tech-stack:
  added: []  # fcntl is stdlib; no new dependencies
  patterns:
    - 'fcntl.LOCK_EX advisory lock on the DESTINATION file (not tempfile, not parent dir): preserves the os.replace inode-swap semantics correctly'
    - 'Locked vs unlocked I/O kernel pair (_atomic_write + _atomic_write_unlocked, save_state + _save_state_unlocked): caller selects based on whether they already hold the lock'
    - 'mutate_state(mutator, path) cross-process critical-section helper: replaces "load_state -> mutate -> save_state" pattern that admits stale-read lost updates'
    - 'Mutator key-replay closure (main.py daily loop): captured-snapshot mutator re-applies the run''s accumulated mutations onto a fresh-loaded state under lock (preserves W3 invariant: 2 mutate_state calls per daily run)'
    - 'spawn-context multiprocessing fixtures for cross-process flock contention testing (macOS-safe; no fork-related state inheritance issues)'

key-files:
  created: []
  modified:
    - 'state_manager.py — fcntl import; module docstring Phase 14 D-13 + REVIEWS HIGH #1 amendment paragraph; _migrate_v2_to_v3 + MIGRATIONS[3]; _atomic_write_unlocked + _atomic_write split; _save_state_unlocked + mutate_state public API; load_state gains private _under_lock parameter (566 -> 726 lines)'
    - 'system_params.py — STATE_SCHEMA_VERSION 2 -> 3; Position TypedDict gains manual_stop: float | None field with docstring (167 -> 172 lines)'
    - 'main.py — 3 save_state call sites migrated to mutate_state (run_daily_check step 9, _dispatch_email_and_maintain_warnings, _handle_reset); _LAST_LOADED_STATE cache updated post-mutate; REVIEWS HIGH #1 audit comments at every migrated site (1619 -> 1674 lines)'
    - 'tests/test_state_manager.py — TestFcntlLock + TestMutateState + TestSchemaMigrationV2ToV3 fully populated (15 tests); STATE_SCHEMA_VERSION literal in test_migrate_walks_schema_version_to_current bumped 2 -> 3 (1423 -> 1779 lines)'
    - 'tests/test_main.py — TestSoleWriterW3 test (test_happy_path_save_state_called_exactly_twice) + 2 dispatch-helper tests migrated to monkey-patch state_manager.mutate_state (was: state_manager.save_state); W3 invariant counted at mutate_state layer (2623 -> 2644 lines)'

key-decisions:
  - 'mutate_state is the REVIEWS HIGH #1 fix for the cross-process lost-update race (T-14-01: ACCEPTED RESIDUAL -> FULLY MITIGATED). Holds fcntl.LOCK_EX across the FULL load -> mutate -> save critical section, not just save.'
  - 'Locked + unlocked I/O kernel pair: _atomic_write (acquires lock + delegates) and _atomic_write_unlocked (no lock, used by callers that already hold it). save_state preserves its public lock-acquiring contract; _save_state_unlocked is the in-lock partner.'
  - 'load_state gains a PRIVATE _under_lock parameter (underscore-prefixed) so the corruption-recovery save uses _save_state_unlocked when called from inside mutate_state. Public callers see no behavior change.'
  - '--reset migrated to mutate_state for cross-process safety even though it''s outside the daily-run W3 contract (operator-initiated CLI; ensures coordination with web POSTs that may be in flight when --reset is run).'

patterns-established:
  - 'I/O kernel pair pattern (locked + unlocked): split atomic-write (and any future locked write helper) into a LOCK_EX-acquiring shell and a no-lock body; let mutate_state-style callers reuse their already-acquired lock by calling the unlocked body directly.'
  - 'POSIX flock has SAME-PROCESS-DIFFERENT-FD non-reentrancy: documented via _atomic_write docstring + _save_state_unlocked existence rationale. RESEARCH §Pattern 9''s "reentrant within a single process" claim corrected — only the SAME fd is reentrant on POSIX flock.'
  - 'spawn-context multiprocessing.Process holder fixture for cross-process contention testing: macOS-safe (no fork-inherited state); Linux droplet equivalent via the default mp context.'

requirements-completed: [TRADE-06]

# Metrics
duration: 67min
completed: 2026-04-25
---

# Phase 14 Plan 02: state_manager fcntl + v2->v3 migration + mutate_state Summary

**fcntl.LOCK_EX advisory lock on state.json plus a new cross-process critical-section helper `state_manager.mutate_state(mutator, path)` that closes the lost-update race; v2 -> v3 schema migration backfilling `manual_stop=None` on every Position; main.py daily loop migrated to mutate_state, preserving Phase 8 W3 invariant (2 saves per run).**

## Performance

- **Duration:** 67 min
- **Started:** 2026-04-25T08:46:00Z
- **Completed:** 2026-04-25T09:53:15Z
- **Tasks:** 3
- **Files modified:** 5
- **Files created:** 0

## Accomplishments

- **REVIEWS HIGH #1 closed.** The cross-process lost-update race (T-14-01) is now FULLY MITIGATED. `mutate_state(mutator, path)` holds `fcntl.LOCK_EX` across the full `load -> mutate -> save` critical section. Verified by `TestMutateState.test_concurrent_writers_no_lost_update` — two spawn-context processes both call `mutate_state` with non-conflicting mutations on the same state file; both mutations land. The previous `fcntl`-on-save-only design would have lost one of them.
- **Schema migration v2 -> v3 (D-09).** `_migrate_v2_to_v3` walks `state['positions']` and backfills `manual_stop=None` on every non-None Position dict. Migration is idempotent (dict-spread preserves existing values), silent (D-15: no append_warning, no log), and round-trip-safe (load v2 fixture -> save -> reload yields `schema_version=3` + `manual_stop=None` on both seed positions).
- **fcntl.LOCK_EX wraps `_atomic_write` (D-13).** The destination state.json is opened with `O_RDWR|O_CREAT|0o600`, locked via `fcntl.flock(LOCK_EX)`, the existing tempfile -> fsync -> os.replace -> dir-fsync sequence runs inside the lock window, and the lock is released via `LOCK_UN + os.close` in the outer finally. Lock is also released if `os.replace` fails (verified by `test_save_state_releases_lock_after_failed_os_replace`).
- **W3 invariant preserved.** main.py's daily loop now calls `mutate_state` exactly twice per run (run_daily_check step 9 + _dispatch_email_and_maintain_warnings post-dispatch). The W3 regression test (`test_happy_path_save_state_called_exactly_twice` in TestWarningCarryOverFlow) was migrated to monkey-patch `state_manager.mutate_state` instead of `state_manager.save_state`; the assertion `len(mutate_calls) == 2` is structurally identical to the previous `len(save_calls) == 2` modulo the API layer change.

## Task Commits

Each task was committed atomically:

1. **Task 1: state_manager fcntl lock + mutate_state helper + v2->v3 migration; system_params Position field + schema bump** — `f440188` (feat)
2. **Task 2: main.py daily loop migrates from save_state to mutate_state(mutator); W3 invariant preserved** — `a6d3a51` (feat)
3. **Task 3: TestFcntlLock + TestMutateState + TestSchemaMigrationV2ToV3 populated; bump STATE_SCHEMA_VERSION literal; W3 regression count migrated** — `1f3c4bc` (test)

## MIGRATIONS dict literal (proves the v2 -> v3 dispatch wiring)

```python
MIGRATIONS: dict = {
  1: lambda s: s,                # no-op at v1; hook proves the walk-forward mechanism works
  2: _migrate_v1_to_v2,          # Phase 8 IN-06: named function for future migrations
  3: _migrate_v2_to_v3,          # Phase 14 D-09: backfill manual_stop on existing Positions
}
```

## _atomic_write critical-section structure (proves lock placement)

`_atomic_write` is now a thin wrapper that acquires `fcntl.LOCK_EX` and delegates to `_atomic_write_unlocked`:

```python
def _atomic_write(data: str, path: Path) -> None:
  lock_fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
  try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX)  # blocks until exclusive lock acquired
    try:
      _atomic_write_unlocked(data, path)
    finally:
      fcntl.flock(lock_fd, fcntl.LOCK_UN)
  finally:
    os.close(lock_fd)
```

`_atomic_write_unlocked` performs the existing tempfile -> fsync -> os.replace -> dir-fsync durability sequence with NO lock acquisition.

## mutate_state helper signature + body (proves REVIEWS HIGH #1 fix shape)

```python
def mutate_state(
  mutator: Callable[[dict], None],
  path: Path = Path(STATE_FILE),
) -> dict:
  fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
  try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
      state = load_state(path=path, _under_lock=True)
      mutator(state)
      _save_state_unlocked(state, path=path)
      return state
    finally:
      fcntl.flock(fd, fcntl.LOCK_UN)
  finally:
    os.close(fd)
```

Critical detail: the inner `_save_state_unlocked` (NOT `save_state`) avoids the intra-process flock-on-different-fd deadlock that would arise on POSIX if the inner `save_state` -> `_atomic_write` chain tried to acquire a SECOND `LOCK_EX` on the same file from a different fd. See "Deviations from Plan" §1 for the deadlock root cause and refactor.

## main.py save site count BEFORE vs AFTER

**Before Plan 14-02:**
```bash
$ grep -c 'state_manager\.save_state(' main.py
3   # run_daily_check step 9 (line 1271), _dispatch_email_and_maintain_warnings (line 571), _handle_reset (line 1499)

$ grep -c 'state_manager\.mutate_state(' main.py
0
```

**After Plan 14-02:**
```bash
$ grep -c 'state_manager\.save_state(' main.py
0   # zero direct save_state calls; all 3 sites migrated

$ grep -c 'state_manager\.mutate_state(' main.py
5   # 3 actual call sites + 2 docstring/comment references
```

Three actual call sites:
1. `main.py:589` (was 571) — `_dispatch_email_and_maintain_warnings` post-dispatch save (W3 #2)
2. `main.py:1310` (was 1271) — `run_daily_check` step 9 primary save (W3 #1)
3. `main.py:1554` (was 1499) — `_handle_reset` operator-initiated reset

`grep -c 'REVIEWS HIGH #1' main.py` returns 5 (audit trail at every migrated site + 2 docstring references).

## Test counts (TestFcntlLock + TestMutateState + TestSchemaMigrationV2ToV3 = 15 new tests)

```bash
$ pytest tests/test_state_manager.py --tb=no -q
82 passed in 0.83s

# Breakdown vs Plan 14-01 baseline (67 passed + 2 skip placeholders = 69 collected):
#   +4  TestFcntlLock methods (was: 1 skip placeholder)
#   +5  TestMutateState methods (NEW class — REVIEWS HIGH #1 fix verification)
#   +6  TestSchemaMigrationV2ToV3 methods (was: 1 skip placeholder)
#   = +15 new tests; 82 - 67 = 15 ✓
#   = 0 skip placeholders remain (Plan 14-01 skeletons fully replaced)
```

Wall-clock runtime for the multiprocess test classes (TestFcntlLock + TestMutateState combined): ~1.4s — well under the 10s budget the plan specified.

## W3 regression test migration evidence

**Original test name (line 1909 in pre-Plan-14-02 tests/test_main.py):**
`TestWarningCarryOverFlow::test_happy_path_save_state_called_exactly_twice`

**Before:**
```python
save_calls: list = []
def _recording_save(state, path=None):
  save_calls.append(dict(state))
  ...
monkeypatch.setattr('state_manager.save_state', _recording_save)
...
assert len(save_calls) == 2, f'W3: expected 2 saves per run, got {len(save_calls)}'
```

**After:**
```python
mutate_calls: list = []
def _recording_mutate(mutator, path=None):
  ...
  mutate_calls.append(dict(result))
  return result
monkeypatch.setattr('state_manager.mutate_state', _recording_mutate)
...
assert len(mutate_calls) == 2, f'W3 (Phase 14): expected 2 mutate_state calls per run, got {len(mutate_calls)}'
```

Test name kept as-is (would require a fixture rename cascade if changed; the docstring explicitly notes Phase 14 REVIEWS HIGH #1 layer migration). Same goes for `test_stale_info_popped_before_save` and `test_dispatch_status_none_appends_warning` in the same class — both monkey-patched `state_manager.save_state` previously and were migrated to `state_manager.mutate_state` in this plan (they would have broken under Task 2's main.py migration without the test-side update).

## Multiprocess test elapsed time observations

- `test_save_state_blocks_when_external_lock_held`: spawn-process holder sleeps 0.5s under LOCK_EX; main test asserts elapsed `>= 0.4s` and `< 1.5s`. Observed ~0.5–0.7s on macOS dev machine (within window).
- `test_concurrent_writers_no_lost_update`: two spawn processes both call `mutate_state` with simultaneous-go events. Total wall-clock ~0.6–1.0s including process spawn overhead. Both mutations land in the final state (no lost update).
- Total runtime for TestFcntlLock + TestMutateState combined: 1.4s — well within the plan's "<10s" bound.

## Files Modified

**Modified:**
- `state_manager.py` — fcntl import, module docstring amendment, `_migrate_v2_to_v3` + MIGRATIONS[3], `_atomic_write_unlocked` + `_atomic_write` split, `_save_state_unlocked` + `mutate_state` public API, `load_state` `_under_lock` parameter (566 -> 726 lines, +160)
- `system_params.py` — STATE_SCHEMA_VERSION 2 -> 3; Position.manual_stop field + docstring (167 -> 172 lines, +5)
- `main.py` — 3 save_state -> mutate_state migrations; REVIEWS HIGH #1 audit comments; `_LAST_LOADED_STATE` cache update post-mutate (1619 -> 1674 lines, +55)
- `tests/test_state_manager.py` — TestFcntlLock + TestMutateState + TestSchemaMigrationV2ToV3 fully populated (15 new tests); literal bump 2 -> 3 (1423 -> 1779 lines, +356)
- `tests/test_main.py` — 3 W3-related tests migrated to monkey-patch mutate_state (was: save_state) (2623 -> 2644 lines, +21)

## Decisions Made

- **REVIEWS HIGH #1 fix shape:** `mutate_state(mutator, path)` holds the lock across the FULL READ-MODIFY-WRITE rather than just save. Documented in state_manager.py module docstring with explicit cross-reference to Phase 14 D-13 amendment of D-15.
- **POSIX flock-on-different-fd is NOT reentrant within a single process.** RESEARCH §Pattern 9 + 14-02-PLAN explicitly claimed it was; that's wrong. POSIX flock locks the open-file-description, NOT the inode/path. Two fds in the same process to the same file do not share lock ownership; the second LOCK_EX acquire blocks indefinitely. Documented in `_atomic_write` docstring; structurally avoided via `_save_state_unlocked` inside `mutate_state`.
- **`load_state` gains a private `_under_lock=False` parameter.** Underscore-prefixed (private convention). Set to True ONLY by mutate_state; the corruption-recovery save uses `_save_state_unlocked` when True. Public callers see no behavior change.
- **--reset migrated to mutate_state.** Operator-initiated CLI; outside W3 daily-run contract but coordinated with web POSTs via the same lock. The mutator clears the freshly-loaded state and replaces it with the operator-supplied fresh state.
- **W3 invariant counted at mutate_state layer.** test_happy_path_save_state_called_exactly_twice now monkey-patches state_manager.mutate_state (was: state_manager.save_state) and asserts `len(mutate_calls) == 2`. Test name preserved.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] POSIX flock-on-different-fd reentrancy claim was incorrect; the planned mutate_state -> save_state -> _atomic_write chain deadlocked on the second LOCK_EX acquire**

- **Found during:** Task 2 (main.py migration); first triggered when running `pytest tests/test_main.py::TestCLI::test_once_flag_runs_single_check` after the initial Task 2 edits — the test hung indefinitely. `sample` on the stuck pytest process showed the entire stack ending in `flock` syscall (libsystem_kernel.dylib).
- **Issue:** Both `mutate_state` (Task 1 implementation) and the inner `save_state` (called from inside `mutate_state`) acquire `fcntl.LOCK_EX` on `state.json` via separate `os.open` calls. The plan + RESEARCH §Pattern 9 claimed `fcntl.flock` is "reentrant within a single process". This is WRONG on POSIX (Linux + macOS): flock locks the open-file-description, NOT the inode/path. Two fds in the same process to the same file are independent lock contexts; the second `LOCK_EX` acquire blocks forever waiting for the first to release.
- **Fix:** Refactored `state_manager.py` to introduce a locked + unlocked I/O kernel pair:
  - `_atomic_write_unlocked(data, path)` — extracted body of `_atomic_write` minus the lock acquisition
  - `_atomic_write(data, path)` — thin wrapper that acquires `fcntl.LOCK_EX` and delegates to `_atomic_write_unlocked`
  - `_save_state_unlocked(state, path)` — JSON encode + `_atomic_write_unlocked` for callers already holding the lock
  - `mutate_state` calls `_save_state_unlocked` directly inside its locked window (NOT `save_state`)
  - `load_state` gains a private `_under_lock=False` parameter; mutate_state passes True so the corruption-recovery save uses `_save_state_unlocked` when called from inside mutate_state's locked window.
- **Files modified:** `state_manager.py` (Task 2 commit, included in `a6d3a51`)
- **Verification:**
  - `pytest tests/test_main.py::TestCLI::test_once_flag_runs_single_check` runs in 0.51s (no longer hangs)
  - Full `pytest tests/test_state_manager.py` — 82 passed (existing TestAtomicity / TestSaveStateExcludesUnderscoreKeys / TestLoadStateResolvesContracts unchanged; 15 new tests including TestMutateState round-trip)
  - `TestMutateState.test_reentrancy_save_state_within_mutate_state` exercises the legitimate cross-file nesting case (different inodes -> different flock namespaces -> works); the same-path nesting deadlock is structurally avoided inside mutate_state via `_save_state_unlocked`.
- **Committed in:** `a6d3a51` (Task 2 commit narrative explicitly documents the bug + refactor)

**2. [Rule 1 - Bug] `_LAST_LOADED_STATE` module-level cache became stale after mutate_state migration**

- **Found during:** Task 2 (main.py migration); spotted while reviewing the `run_daily_check` step 9 site.
- **Issue:** `mutate_state` returns the post-mutation/post-save state dict (which is a freshly-loaded-then-mutated dict, NOT the in-memory accumulated state). The crash-email path reads `_LAST_LOADED_STATE` to build a state summary; if `_LAST_LOADED_STATE` were left pointing at the pre-mutate accumulated state, a crash AFTER the save would surface a state summary that didn't match disk.
- **Fix:** Updated `_LAST_LOADED_STATE = state` AFTER the `state = state_manager.mutate_state(_apply_daily_run)` line, so the cache always points at the post-save dict. The earlier `global _LAST_LOADED_STATE` declaration at the top of `run_daily_check` makes this assignment the module-level write.
- **Files modified:** `main.py` (run_daily_check step 9 site)
- **Verification:** `test_crash_email_includes_last_loaded_state` is in the 16-failure baseline (weekend-skip, pre-existing); the fix is structural — the assignment is in the post-save path. Plan 14-04's web routes will inherit this cache discipline.
- **Committed in:** `a6d3a51` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bug fixes; both surfaced during integration of plan-as-written)
**Impact on plan:** Critical — Deviation #1 was a fundamental flaw in the plan's flock-reentrancy claim that would have shipped a deadlocking codebase. The refactor preserves all external API contracts (save_state, load_state, mutate_state) and adds 3 new internal helpers. Deviation #2 is a 1-line fix that prevents stale crash-email summaries.

## Issues Encountered

- **Pre-existing baseline failures unchanged.** `tests/test_main.py` continues to show 16 failures (deferred-items.md weekend-skip baseline; today is Saturday 2026-04-25). Two of those (`test_dispatch_status_none_appends_warning`, `test_stale_info_popped_before_save`) were temporarily NEW failures after the Task 2 main.py migration (they monkey-patched `save_state` which was no longer called from the dispatch helper); Task 3 migrated them to monkey-patch `mutate_state` and they returned to GREEN. Net delta: 0 new failures, 0 fewer failures vs baseline.
- **Web tests unchanged baseline.** `tests/test_web_*` collection ERRORs on missing `fastapi` module are pre-existing (verified by `git stash` + reproduce on the parent commit). Out of Plan 14-02 scope.

## TDD Gate Compliance

This plan's frontmatter is `type: execute` (not `type: tdd`), but Task 3 has `tdd="true"` for the test class population. Gate sequence in git log:
1. Task 1 (`f440188` feat): production code first — fcntl lock, mutate_state, migration. (Existing tests fail at the literal-bump assertion only; documented as expected.)
2. Task 2 (`a6d3a51` feat): main.py migration. Auto-fixed deadlock bug surfaced and resolved.
3. Task 3 (`1f3c4bc` test): test class population + literal bump + W3 migration.

The Task 3 `tdd="true"` annotation is structurally satisfied because the test classes were SCAFFOLDED in Plan 14-01 (RED-equivalent placeholders) and POPULATED here in Task 3 (full GREEN against the Task 1+2 production code). No separate "RED" commit was made because the test bodies depend on the Task 1 + 2 production APIs (mutate_state, _migrate_v2_to_v3) which had to land first.

## User Setup Required

None — Plan 14-02 is internal state-manager + main.py + tests. No environment variables, no external services.

## Self-Check

**Files exist:**
- FOUND: state_manager.py (modified — fcntl, mutate_state, _migrate_v2_to_v3, locked/unlocked I/O pair)
- FOUND: system_params.py (modified — STATE_SCHEMA_VERSION=3, Position.manual_stop)
- FOUND: main.py (modified — 3 save_state -> mutate_state migrations)
- FOUND: tests/test_state_manager.py (modified — 15 new tests across 3 classes; literal bump)
- FOUND: tests/test_main.py (modified — 3 tests migrated to monkey-patch mutate_state)

**Commits exist:**
- FOUND: f440188 (Task 1)
- FOUND: a6d3a51 (Task 2)
- FOUND: 1f3c4bc (Task 3)

## Self-Check: PASSED

## Next Phase Readiness

Plan 14-03 (sizing_engine manual_stop precedence) can now spawn. Its dependency surface is satisfied:
- `system_params.Position.manual_stop` field exists with the correct `float | None` annotation.
- v3 state files load with `manual_stop=None` backfilled on every existing Position (so sizing_engine's `get_trailing_stop` won't see KeyError on legacy positions).
- The `mutate_state` helper exists and is the canonical write API for the upcoming web/routes/trades.py mutations (Plan 14-04).

Plan 14-04 (web/routes/trades.py POST endpoints) inherits the `mutate_state` API for all three handlers (`/trades/open`, `/trades/close`, `/trades/modify`). The cross-process lost-update race (T-14-01) is FULLY MITIGATED — web POSTs concurrent with the daily loop will now serialize correctly and both mutations will land.

Plan 14-05 (dashboard manual_stop badge + HTMX form rendering) inherits the v3 schema; the dashboard's `_compute_trail_stop_display` will need the same `manual_stop` precedence as `sizing_engine.get_trailing_stop` (Plan 14-03 + 14-05 lockstep parity test).

No blockers, no concerns.

---
*Phase: 14-trade-journal-mutation-endpoints*
*Plan: 02*
*Completed: 2026-04-25*
