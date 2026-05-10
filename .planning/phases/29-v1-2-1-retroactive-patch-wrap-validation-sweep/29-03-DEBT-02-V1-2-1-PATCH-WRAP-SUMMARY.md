---
phase: 29
plan: 03
plan_id: 29-03-DEBT-02-V1-2-1-PATCH-WRAP
subsystem: milestones, tests
tags: [debt-closure, regression-tests, scheduler-tz, signal-status-ladder, trace-vote-params, v1.2.1]
requirements: [DEBT-02]

dependency_graph:
  requires: []
  provides:
    - v1.2.1 sub-section in .planning/MILESTONES.md with 5-row commit table
    - TestSchedulerTimezone regression suite (AEST/AEDT/DST)
    - TestSignalStatusLadder regression suite (trigger ladder + trailing stop)
    - TestTraceVoteParams regression suite (engine-resolved params + stale fallback)
  affects:
    - .planning/MILESTONES.md
    - tests/test_scheduler.py
    - tests/test_signals_status_ladder.py
    - tests/test_trace_vote_params.py

tech_stack:
  added: []
  patterns:
    - freeze_time pattern extended to tz-sensitive scheduler tests
    - zoneinfo.ZoneInfo used for UTC offset ground-truth assertions
    - _render_trace_vote / _render_trace_panels tested via direct import

key_files:
  created:
    - tests/test_signals_status_ladder.py
    - tests/test_trace_vote_params.py
  modified:
    - .planning/MILESTONES.md
    - tests/test_scheduler.py

decisions:
  - Gate text in _render_trace_vote is HTML-escaped (">=" -> "&gt;="); tests assert escaped form
  - TestSchedulerTimezone asserts zoneinfo UTC offsets directly rather than schedule.Job.next_run (library stores naive local time, not UTC)
  - TestSchedulerTimezone added to existing test_scheduler.py (867 lines pre-task); new class is 130 lines

metrics:
  duration: ~25min
  completed: "2026-05-10"
  tasks: 3
  files: 4
---

# Phase 29 Plan 03: DEBT-02 v1.2.1 Patch Wrap Summary

**One-liner:** Formalised 5 post-v1.2 polish commits as a MILESTONES.md v1.2.1 sub-section with behaviour-locking regression tests for scheduler tz, signal status ladder, and trace vote_params locality.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Append v1.2.1 sub-section to MILESTONES.md | e9d5f20 | .planning/MILESTONES.md |
| 2 | Regression test for scheduler tz fix (05a4c0c) | b73ef08 | tests/test_scheduler.py |
| 3 | Regression tests for status ladder + trace vote_params | ec7b325 | tests/test_signals_status_ladder.py, tests/test_trace_vote_params.py |

## What Was Built

### Task 1 — MILESTONES.md v1.2.1 entry

Inserted `### v1.2.1 — Retroactive Patch Wrap (2026-05-10)` under the v1.2 entry (after "Known Deferred Items", before "### Audit"). A 5-row `| Commit | Behaviour | Test | Note |` table covers all 5 post-ship commits per D-11/D-13. No duplication to `milestones/v1.2-ROADMAP.md`.

### Task 2 — TestSchedulerTimezone (6 tests)

Added to `tests/test_scheduler.py`. Class verifies:
- `system_params.SCHEDULE_TZ == 'Australia/Sydney'` and `SCHEDULE_TIME_LOCAL == '08:00'`
- `_run_schedule_loop` passes the tz argument to `schedule.at()` (spy scheduler)
- AEST UTC offset: 08:00 Sydney AEST = 22:00 UTC prior day
- AEDT UTC offset: 08:00 Sydney AEDT = 21:00 UTC prior day
- DST transition (Oct 4 2026): offset flips AEST+10h → AEDT+11h at 08:00

Uses `zoneinfo.ZoneInfo('Australia/Sydney')` for ground-truth UTC offset assertions rather than `schedule.Job.next_run` (which stores naive local time).

### Task 3 — TestSignalStatusLadder (6 tests) + TestTraceVoteParams (5 tests)

**test_signals_status_ladder.py** locks da31412:
- Trigger-ladder `<p class="triggers">` appears for FLAT signal with ADX below gate
- Trailing-stop `<p class="stop-line">` appears with positive momentum votes
- Trigger ladder absent for active LONG signal (guard tested)
- ADX gap text "+5.0" present when ADX=15.0, gate=20.0
- Hypothetical stop labels "(if LONG ...)" for FLAT signal

**test_trace_vote_params.py** locks 587b6f0 + bb780af per project LEARNING 2026-05-10:
- Persisted `adx_gate=20.0` renders `&gt;= 20` not `&gt;= 25` in gate text
- Stale state row (no `vote_params` key) falls back to `resolve_vote_params({})` without crash
- `Mom1=0.0074` does NOT count as a positive vote when `momentum_threshold=0.02`
- End-to-end `_render_trace_panels` with missing key renders Vote panel without crash

## Verification

```
pytest tests/test_scheduler.py::TestSchedulerTimezone tests/test_signals_status_ladder.py tests/test_trace_vote_params.py -q
# 17 passed in 0.45s
```

All 7 acceptance criteria for Tasks 1-3 met:
- `grep -q "### v1.2.1"` ✓, all 6 commit SHAs present ✓, no v1.2-ROADMAP.md duplication ✓
- `test_daily_run_fires_at_0800_sydney` present ✓, AEST/AEDT/DST coverage ✓
- Both new test files present ✓, all 8 named test functions present ✓

## Deviations from Plan

**1. [Rule 1 — Bug] HTML-escaped gate text in trace tests**
- **Found during:** Task 3 test authoring
- **Issue:** `_render_trace_vote` passes gate text through `html.escape(f'>= {threshold:g}', quote=True)` before embedding in HTML. First-pass tests asserted `>= 20` but the actual string is `&gt;= 20`.
- **Fix:** Test assertions updated to check `&gt;= 20` and `&gt;= 25` (escaped form).
- **Files modified:** tests/test_trace_vote_params.py
- **Commit:** ec7b325 (fixed inline before commit)

**2. [Note] test_scheduler.py pre-existed at 867 lines**
- The plan AC `wc -l tests/test_scheduler.py ≤ 500` refers to a newly-created file. The existing file is already 867 lines (pre-existing state; not introduced by this plan). The new `TestSchedulerTimezone` class adds 130 lines. No remediation warranted — this is accumulated technical depth in the test file, not a new violation.

## Known Stubs

None. All 5 commits are documented in MILESTONES.md with real test pointers or explicit "none — UX" / "pointer only" annotations. No placeholders or TODOs left.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan adds only documentation and tests.

## Self-Check: PASSED

- `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-03-DEBT-02-V1-2-1-PATCH-WRAP-SUMMARY.md` — this file
- `tests/test_signals_status_ladder.py` ✓ (206 lines)
- `tests/test_trace_vote_params.py` ✓ (212 lines)
- `tests/test_scheduler.py` — TestSchedulerTimezone appended ✓
- `.planning/MILESTONES.md` — v1.2.1 section present ✓
- Commits: e9d5f20, b73ef08, ec7b325 ✓
