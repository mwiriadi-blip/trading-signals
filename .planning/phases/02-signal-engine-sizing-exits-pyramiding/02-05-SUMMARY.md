---
phase: 02-signal-engine-sizing-exits-pyramiding
plan: '05'
subsystem: testing
tags: [step-orchestrator, exit-logic, pyramid, sha256-snapshot, determinism, sizing-engine]

# Dependency graph
requires:
  - phase: 02-04
    provides: 15 phase2 JSON fixtures with expected fields (stop_hit, trail_stop, unrealised_pnl, pyramid_decision, sizing_decision)
provides:
  - step() orchestrator integrating peak/trough update, exit detection, sizing, pyramiding, and unrealised PnL in one call
  - _step() inline oracle in regenerate_phase2_fixtures.py that matches production step() logic (B-4)
  - 15 JSON fixtures enriched with position_after (all transitions and edge cases)
  - tests/determinism/phase2_snapshot.json with 15 SHA256 hashes locking fixture goldens
  - TestStep class (43 tests) covering D-16/D-17/D-18/D-19/B-5/B-6/A2/SIZE-05
  - test_phase2_snapshot_hash_stable parametrized over all 15 phase2 fixtures
affects: [03-main-orchestrator, future-backtesting, phase-2-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - 'D-16: peak/trough update via shallow copy BEFORE exit logic in step()'
    - 'D-18: pyramid dict spread {**position_after, n_contracts:..., pyramid_level:...} (grep-auditable)'
    - 'D-19: reversal sizing uses INPUT account, no account mutation in Phase 2'
    - 'B-5: _close_position() exit_price kwarg — stop-hit passes stop level not bar.close'
    - 'B-6: unrealised_pnl computed AFTER pyramid add (final n_contracts)'
    - 'A2: no new entry on forced-exit day (ADX drop or stop hit sets is_forced_exit=True)'
    - 'B-4 oracle: regenerator reimplements sizing math inline without importing sizing_engine'
    - 'D-06: SHA256 determinism gate using json.dumps(sort_keys=True, separators=(",",":"))'
    - 'is_new_entry_this_bar guard: prevents pyramid firing on brand-new entries'

key-files:
  created:
    - tests/determinism/phase2_snapshot.json
  modified:
    - sizing_engine.py
    - tests/regenerate_phase2_fixtures.py
    - tests/fixtures/phase2/transition_long_to_long.json
    - tests/fixtures/phase2/transition_long_to_short.json
    - tests/fixtures/phase2/transition_long_to_flat.json
    - tests/fixtures/phase2/transition_short_to_long.json
    - tests/fixtures/phase2/transition_short_to_short.json
    - tests/fixtures/phase2/transition_short_to_flat.json
    - tests/fixtures/phase2/transition_none_to_long.json
    - tests/fixtures/phase2/transition_none_to_short.json
    - tests/fixtures/phase2/transition_none_to_flat.json
    - tests/fixtures/phase2/pyramid_gap_crosses_both_levels_caps_at_1.json
    - tests/fixtures/phase2/adx_drop_below_20_while_in_trade.json
    - tests/fixtures/phase2/long_trail_stop_hit_intraday_low.json
    - tests/fixtures/phase2/short_trail_stop_hit_intraday_high.json
    - tests/fixtures/phase2/long_gap_through_stop.json
    - tests/fixtures/phase2/n_contracts_zero_skip_warning.json
    - tests/test_sizing_engine.py
    - tests/test_signal_engine.py

key-decisions:
  - 'D-16: peak/trough update via shallow copy happens at phase 0, before any exit check — ensures stop level uses updated peak'
  - 'D-18: pyramid application uses dict spread pattern to satisfy grep AC and produce new position_after dict'
  - 'A2: is_forced_exit flag prevents new sizing on ADX-drop or stop-hit days (exit-only day)'
  - 'B-5: _close_position() exit_price kwarg passes computed stop level for stop-hit exits, not bar.close'
  - 'B-4: regenerator oracle reimplements step() inline to avoid importing production code (dual-maintenance by design)'
  - 'D-19: account balance passed as INPUT to step(), no mutation — Phase 3 handles PnL settlement'
  - 'is_new_entry_this_bar guard: (closed_trade is not None and position_after is not None) OR (position is None and position_after is not None) prevents pyramid on fresh entries'

patterns-established:
  - 'Grep AC verification: all D-number decisions have corresponding grep checks that must pass before commit'
  - 'Fixture re-emission via inline oracle: fixtures are both goldens (for step()) and seeds (for oracle verification)'
  - 'SHA256 snapshot covers expected dict only — canonical serialization with sort_keys=True, no allow_nan'
  - 'TestStep uses _call_step(fix) helper to reduce boilerplate across 43 test methods'

requirements-completed: [EXIT-01, EXIT-02, EXIT-03, EXIT-04, EXIT-05, PYRA-05]

# Metrics
duration: 14min
completed: '2026-04-21'
---

# Phase 02 Plan 05: step() Orchestrator + Determinism Gate Summary

**`step()` orchestrator integrating 5-phase sequential logic (peak update, exits, sizing, pyramiding, unrealised PnL) with SHA256 determinism gate across all 15 phase2 fixtures**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-04-21T00:28:37Z
- **Completed:** 2026-04-21T00:42:40Z
- **Tasks:** 3
- **Files modified:** 20

## Accomplishments

- `step()` body fully implemented in `sizing_engine.py` (NotImplementedError removed) — 5 sequential phases: D-16 peak/trough, exits (ADX/stop/FLAT/reversal), D-19 sizing, D-18 pyramid, B-6 PnL
- All 15 phase2 JSON fixtures enriched with `position_after` via inline `_step()` oracle in `regenerate_phase2_fixtures.py` (B-4 dual-maintenance pattern)
- `tests/determinism/phase2_snapshot.json` created with 15 SHA256 hashes; `test_phase2_snapshot_hash_stable` parametrized gate added to `TestDeterminism`
- `TestStep` class with 43 tests added to `test_sizing_engine.py` covering all D-numbers, B-numbers, and A2 rules
- 248 tests total, 0 failures, ruff passes on all modified files

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement step() orchestrator** - `6c24b3e` (feat)
2. **Task 2: Re-emit 15 fixtures with position_after** - `3c5bc3b` (feat)
3. **Task 3: TestStep + phase2 SHA256 determinism snapshot** - `9e8b4ba` (test)

## Files Created/Modified

- `sizing_engine.py` - step() orchestrator + _close_position() with exit_price kwarg (B-5)
- `tests/regenerate_phase2_fixtures.py` - Added _step() oracle + _enrich_position_after(), ADX_EXIT_GATE constant
- `tests/determinism/phase2_snapshot.json` - 15 SHA256 hashes for all phase2 fixture expected dicts
- `tests/test_sizing_engine.py` - Added step import, ALL_PHASE2_FIXTURES list, _call_step() helper, TestStep (43 tests)
- `tests/test_signal_engine.py` - Added PHASE2_SNAPSHOT_PATH, test_phase2_snapshot_hash_stable (15 parametrized cases)
- All 15 `tests/fixtures/phase2/*.json` - position_after fields populated from null to correct dict values

## Decisions Made

- **D-16 first**: Peak/trough update via shallow copy at phase 0 ensures stop level uses bar's updated high/low before checking whether stop was hit
- **D-18 dict spread**: `{**position_after, 'n_contracts': ..., 'pyramid_level': pyramid_decision.new_level}` chosen over subscript assignment to satisfy grep AC check requiring the literal pattern `'pyramid_level': pyramid_decision.new_level`
- **A2 forced-exit guard**: `is_forced_exit` flag set on ADX-drop and stop-hit paths; sizing branch skipped when True — no new entry on exit-only days
- **is_new_entry_this_bar guard**: Two conditions (reversal: `closed_trade is not None and position_after is not None`; fresh entry: `position is None and position_after is not None`) prevent pyramid from firing on the same bar as a new entry

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] D-18 grep AC required dict spread, not subscript assignment**
- **Found during:** Task 1 (implement step() orchestrator)
- **Issue:** Initial implementation used `position_after['pyramid_level'] = pyramid_decision.new_level` (subscript assignment) which did not match the plan's required grep acceptance criterion `"'pyramid_level': pyramid_decision.new_level"`
- **Fix:** Rewrote pyramid application as dict spread: `position_after = {**position_after, 'n_contracts': position_after['n_contracts'] + pyramid_decision.add_contracts, 'pyramid_level': pyramid_decision.new_level}`
- **Files modified:** `sizing_engine.py`
- **Verification:** `grep -n "'pyramid_level': pyramid_decision.new_level" sizing_engine.py` returned match
- **Committed in:** `6c24b3e` (Task 1 commit)

**2. [Rule 1 - Bug] Ruff F401 — ClosedTrade unused import in test_sizing_engine.py**
- **Found during:** Task 3 (add TestStep)
- **Issue:** `ClosedTrade` added to import block but never used as a type annotation (attribute access `result.closed_trade` doesn't count)
- **Fix:** Removed `ClosedTrade` from the import statement
- **Files modified:** `tests/test_sizing_engine.py`
- **Verification:** `ruff check tests/test_sizing_engine.py` returned no errors
- **Committed in:** `9e8b4ba` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes necessary for correctness (grep AC) and clean builds (ruff). No scope creep.

## Issues Encountered

- Idempotency check on first run appeared to show "FAIL" because `git diff` compared against committed state (all fixtures had `position_after: null` in git). True idempotency confirmed via disk-to-disk diff (copy → run regenerator → diff): zero change.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `step()` is the complete Phase 2 interface; Phase 3 (main.py orchestrator) can now call it directly
- All 15 fixture goldens are locked via SHA256 — any drift in step() logic will immediately break `test_phase2_snapshot_hash_stable`
- No blockers for Phase 3

---
*Phase: 02-signal-engine-sizing-exits-pyramiding*
*Completed: 2026-04-21*
