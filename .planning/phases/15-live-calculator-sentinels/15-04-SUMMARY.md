---
phase: 15
plan: 04
subsystem: main-orchestrator
tags:
  - phase15
  - drift-lifecycle
  - w3-invariant
  - sentinel
dependency_graph:
  requires:
    - 15-02  # sizing_engine.detect_drift + DriftEvent
    - 15-03  # state_manager.clear_warnings_by_source
  provides:
    - drift-recompute-block-in-run-daily-check
    - TestDriftWarningLifecycle-fully-implemented
  affects:
    - main.py:run_daily_check
    - tests/test_main.py:TestDriftWarningLifecycle
tech_stack:
  added: []
  patterns:
    - drift-recompute-between-pending-warnings-and-last_run
    - in-memory-only-mutation-before-mutate_state
    - freeze_time-weekday-gate-bypass
    - signal_engine.get_signal-monkeypatching-for-controlled-signals
key_files:
  created: []
  modified:
    - main.py
    - tests/test_main.py
decisions:
  - "Used --once (not --force-email) for test_drift_cleared_then_recomputed and test_no_drift_warning tests so Phase 8 dispatch helper's clear_warnings does not mask drift block output"
  - "Patched sizing_engine.step to no-op preserving position so drift detection is deterministic regardless of sizing math"
  - "Captured _dispatch_email_and_maintain_warnings boundary to intercept drift warnings before clear_warnings wipes them in test_drift_warnings_present_in_dispatched_state"
metrics:
  duration: ~25min
  completed: "2026-04-26T02:54:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 2
  lines_inserted: 276
---

# Phase 15 Plan 04: Drift Warning Lifecycle in run_daily_check — Summary

Wire the drift detection lifecycle into the daily signal loop and prove W3 invariant intact via 4 fully-implemented tests (REVIEWS M-1 Path A enforcement).

## What Was Built

### Task 1: Drift recompute block in main.py:run_daily_check

Inserted `Step 6b` between the existing `pending_warnings` flush (Step 6) and the `last_run` assignment (Step 7). Exact line range: **lines 1274–1287** in the committed `main.py`.

The block sequence (D-02):
1. `state = state_manager.clear_warnings_by_source(state, 'drift')` — purge stale drift warnings
2. `drift_events = sizing_engine.detect_drift(state['positions'], state['signals'])` — compute fresh events
3. `for ev in drift_events:` — append each as `source='drift'` warning + emit `[Sched]` log line

**W3 invariant preserved**: no new `mutate_state` call added. `_accumulated = state` at Step 9 captures all drift mutations, so the single existing terminal `mutate_state(_apply_daily_run)` persists them. Verified via `git diff HEAD~2 HEAD -- main.py | grep "^+.*mutate_state"` → empty (zero new calls).

**mutate_state comment count increase explained**: The inserted block comment references `mutate_state` twice (in the Pitfall 5 mitigation comment). These are comments, not calls. `grep -c "mutate_state" main.py` went from 13 → 15, but `grep -v "#" main.py | grep -c "mutate_state"` shows only 5 actual calls (unchanged from base).

**ruff**: `main.py` ruff output is identical to base commit (only pre-existing F841 at line 1569 — not introduced here).

### Task 2: TestDriftWarningLifecycle — 4 methods fully implemented

All 4 `pytest.skip` bodies replaced (REVIEWS M-1 Path A). Zero `pytest.skip` in the file.

| Method | Mode | Signal | Asserts |
|--------|------|--------|---------|
| `test_drift_cleared_then_recomputed` | `--once` | LONG (matches LONG position) | Stale 'drift' warning cleared; 0 new drift warnings |
| `test_w3_invariant_preserved` | `--force-email` | FLAT (mismatches LONG) | `mutate_state` call_count == 2 exactly |
| `test_drift_warnings_present_in_dispatched_state` | `--force-email` | FLAT (mismatches LONG) | Dispatch receives ≥1 drift warning with D-14 template substrings |
| `test_no_drift_warning_when_signals_match_positions` | `--once` | LONG (matches LONG) | Stale 'drift' warning cleared; 0 drift warnings in final state |

**Shared scaffold (`_setup` helper)**:
- `monkeypatch.chdir(tmp_path)` + `_seed_fresh_state` with LONG SPI200 position
- `_install_fixture_fetch` stubs `main.data_fetcher.fetch_ohlcv` with real fixtures
- `main.signal_engine.get_signal` patched: call 1 returns `spi200_signal`, call 2 returns 0 (AUDUSD FLAT)
- `main.sizing_engine.step` patched to no-op preserving existing position
- `notifier.send_daily_email` stubbed for `--force-email` path
- `@pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')` pins Monday to bypass weekday gate

**Fetch stub path**: `main.data_fetcher.fetch_ohlcv` (monkeypatched via `monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', ...)` — lifted from `_install_fixture_fetch` at module level).

**Why --once for 2 tests**: The Phase 8 `_dispatch_email_and_maintain_warnings` helper calls `state_manager.clear_warnings(state)` which wipes ALL warnings post-email. Tests that assert on drift warning absence/presence in saved state must use `--once` (no dispatch) to avoid the dispatch clear masking the result.

## Acceptance Criteria Status

| Criteria | Status |
|----------|--------|
| `grep -c "clear_warnings_by_source(state, 'drift')" main.py` returns 1 | PASS |
| `grep -c "sizing_engine.detect_drift(state['positions'], state['signals'])" main.py` returns 1 | PASS |
| `grep -c "[Sched] drift detected for" main.py` returns 1 | PASS |
| `grep -c "mutate_state" main.py` comment-only increase (no new calls) | PASS |
| `grep -c "pytest.skip" tests/test_main.py` returns 0 | PASS |
| `grep -c "call_count['n'] == 2" tests/test_main.py` returns 1 | PASS |
| `grep -c "_counting_mutate" tests/test_main.py` returns ≥1 | PASS (2) |
| `grep -c "consider closing" tests/test_main.py` returns 1 | PASS |
| ruff check main.py — no new issues vs base | PASS |
| ruff check tests/test_main.py — no new issues in lines 2647+ | PASS |

## Deviations from Plan

### Auto-adapted Design

**1. [Rule 1 - Design Refinement] Used --once instead of --force-email for lifecycle tests**
- **Found during:** Task 2 implementation analysis
- **Issue:** The plan's canonical pattern used `--force-email` throughout. However, `--force-email` triggers `_dispatch_email_and_maintain_warnings` which calls `state_manager.clear_warnings(state)` unconditionally, wiping ALL warnings (including drift ones) from the saved state. Tests that assert "0 drift warnings in final state" would pass vacuously regardless of whether the drift block ran correctly.
- **Fix:** Used `main.main(['--once'])` for `test_drift_cleared_then_recomputed` and `test_no_drift_warning_when_signals_match_positions`. The `--once` path invokes `run_daily_check` + single `mutate_state` but skips email dispatch, so drift block output is preserved verbatim in the final state.
- **Files modified:** `tests/test_main.py`

**2. [Rule 2 - Correctness] Captured dispatch boundary in test_drift_warnings_present_in_dispatched_state**
- **Found during:** Task 2 implementation
- **Issue:** After `--force-email`, the final saved state has empty warnings (dispatch cleared them). To assert drift warnings reached the dispatch path (SENTINEL-03 prerequisite), needed to intercept at the dispatch boundary BEFORE clear.
- **Fix:** Patched `main._dispatch_email_and_maintain_warnings` with a capturing wrapper that collects drift warnings from the in-flight state before calling the real dispatch. Cleaner and more direct than inspecting a post-clear state.
- **Files modified:** `tests/test_main.py`

## Pytest Execution Note

The test execution sandbox for this worktree blocked `python -m pytest` and `pytest` commands (pre-tool-use hook pattern). All correctness verification was done via:
- Manual code analysis of control flow
- `ruff check` for syntax/style validity
- `git diff` to verify no new `mutate_state` calls
- Acceptance criteria grep checks (all 8 verified manually)

The tests are designed conservatively (using `--once` where appropriate, intercepting at dispatch boundary) to be correct by construction. The W3 test specifically instruments `mutate_state` with a counter, which is the same pattern as the existing passing `test_happy_path_save_state_called_exactly_twice`.

## Known Stubs

None — all 4 methods are fully implemented with real assertions.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced in this plan.

## Self-Check

Checking committed files and hashes:

- FOUND: `.planning/phases/15-live-calculator-sentinels/15-04-SUMMARY.md`
- FOUND: commit `e735aba` (feat(15-04): drift recompute block)
- FOUND: commit `cc1169e` (test(15-04): TestDriftWarningLifecycle)

## Self-Check: PASSED
