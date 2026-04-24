---
phase: 260425-7iw
plan: 01
subsystem: tests
tags: [test-hygiene, pytest-freezer, weekday-gate, phase-10-pattern]
requires: []
provides:
  - "tests/test_main.py suite is day-of-week independent on a real system clock"
  - "Phase 12 deferred-items.md §Pre-existing test failures can be checked off"
affects:
  - tests/test_main.py
tech_stack:
  added: []
  patterns:
    - "@pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')  # Mon 08:00 AWST as outermost decorator"
key_files:
  created: []
  modified:
    - tests/test_main.py
decisions: []
metrics:
  duration: ~8m
  completed: 2026-04-25
  tasks: 2
  files: 1
  commits: 1
---

# Quick Task 260425-7iw: Add freeze_time decorator to 16 weekend-flaky tests — Summary

Decorated 16 weekend-flaky `tests/test_main.py` tests with the Phase 10 exemplar pattern
(`@pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')  # Mon 08:00 AWST`) so the
`run_daily_check` weekday gate no longer short-circuits them on Sat/Sun local runs.

## One-liner

Test-only change (+16 / -0) that pins 16 previously-Sat/Sun-flaky tests to a frozen Monday
08:00 AWST clock, matching the existing Phase 10 exemplar at lines 104 / 2511 / 2540 / 2595.

## Tasks Completed

| # | Task | Commit |
|---|------|--------|
| 1 | Insert `@pytest.mark.freeze_time(...)` decorator above the 16 target `def` lines | 47f6979 |
| 2 | Cross-day suite verification (verification-only — no code change) | — |

## 16 Tests Decorated

| # | Class::Name |
|---|-------------|
| 1 | TestCLI::test_force_email_sends_live_email |
| 2 | TestCLI::test_force_email_captures_post_run_state |
| 3 | TestCLI::test_test_flag_sends_test_prefixed_email_no_state_mutation |
| 4 | TestCLI::test_force_email_and_test_combined |
| 5 | TestOrchestrator::test_short_frame_raises_and_no_state_written |
| 6 | TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape |
| 7 | TestOrchestrator::test_reversal_long_to_short_preserves_new_position |
| 8 | TestOrchestrator::test_fetch_failure_exits_nonzero_no_save_state |
| 9 | TestOrchestrator::test_dashboard_failure_never_crashes_run |
| 10 | TestOrchestrator::test_dashboard_import_time_failure_never_crashes_run |
| 11 | TestEmailNeverCrash::test_email_runtime_failure_never_crashes_run |
| 12 | TestEmailNeverCrash::test_email_import_time_failure_never_crashes_run |
| 13 | TestRunDailyCheckTupleReturn::test_run_daily_check_returns_4_tuple |
| 14 | TestRunDailyCheckTupleReturn::test_run_daily_check_test_mode_returns_in_memory_state |
| 15 | TestCrashEmailBoundary::test_crash_email_includes_last_loaded_state |
| 16 | TestWarningCarryOverFlow::test_happy_path_save_state_called_exactly_twice |

## Verification

### Baseline (before change, today = real Sat 2026-04-25)

```
$ .venv/bin/python -m pytest tests/test_main.py -q
16 failed, 70 passed in 2.34s
```

All 16 failures showed the identical root cause in captured logs:
`[Sched] weekend skip 2026-04-25 (weekday=5) — no fetch, no state mutation`

### After change (real Saturday clock — primary verification)

```
$ date
Sat Apr 25 05:30:44 AWST 2026
$ .venv/bin/python -m pytest tests/test_main.py -q
86 passed in 2.47s
```

Additionally, the full repo test tree is green on today's Saturday clock:

```
$ .venv/bin/python -m pytest tests/ -q
851 passed in 94.28s
```

### Targeted 16-test re-run (real Saturday clock)

All 16 previously-failing tests pass when invoked explicitly by node ID
(confirms the per-test decorator clock override is effective):

```
16 passed in 1.32s
```

### Sunday coverage

The Task 2 plan-specified command
`.venv/bin/python -c "import freezegun; freezegun.freeze_time('2026-04-26T12:00:00+00:00').start(); import pytest, sys; sys.exit(pytest.main(['tests/test_main.py', '-q']))"`
hangs indefinitely (reproduced with a 90s subprocess timeout, no output
produced). Root cause: calling `freezegun.freeze_time(...).start()` at
process-level BEFORE `pytest.main()` freezes `time.monotonic()`, which
pytest's collection/plugin machinery relies on — producing a deadlock
during test collection. This is a plan-command bug, not a regression in
the code under test.

Sunday coverage is instead provided by the symmetric production code
path. `main.py:1042` uses
`if run_date.weekday() >= system_params.WEEKDAY_SKIP_THRESHOLD:` — the
same comparison fires for `weekday=5` (Sat) and `weekday=6` (Sun). Since
each decorated test now pins its own clock to Mon 00:00 UTC (== Mon 08:00
AWST) via `@pytest.mark.freeze_time`, the system clock's weekday becomes
irrelevant inside the test body. The decorator fix is therefore
structurally guaranteed to work on both weekend days; today's Saturday
run is sufficient empirical proof.

## Success Criteria

- [x] 16 decorators added, 0 lines deleted, 0 other files modified
  (`git diff --numstat` → `16  0  tests/test_main.py`).
- [x] `.venv/bin/python -m pytest tests/test_main.py -q` passes on a Saturday (86 / 86).
- [x] Pattern matches Phase 10 exemplar byte-for-byte
  (`grep -c "@pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')  # Mon 08:00 AWST"` == 20).
- [x] For each of the 16 target tests, `grep -B1 "def <name>" tests/test_main.py` shows
  the decorator directly above the `def`.
- [x] Tech-debt item from
  `.planning/phases/12-https-domain-wiring/deferred-items.md` §Pre-existing test failures
  is now cleared and can be checked off.

## Deviations from Plan

### Auto-fixed issues

None — no Rule 1 / Rule 2 / Rule 3 fixes required during execution.

### Auth gates

None.

### Plan-command deviation (verification-only, no code impact)

**1. [Rule 3 — Blocking] Task 2's frozen-Sunday verify command hangs and was not run**
  - **Found during:** Task 2 (verification only, no file edits).
  - **Issue:** The Task 2 command
    `.venv/bin/python -c "import freezegun; freezegun.freeze_time('2026-04-26T12:00:00+00:00').start(); import pytest, sys; sys.exit(pytest.main(['tests/test_main.py', '-q']))"`
    hangs indefinitely during test collection. Reproduced under a 90-second
    subprocess timeout: three separate runs produced zero stdout/stderr and
    accumulated >10 min of CPU before being SIGKILL'd.
  - **Why:** `freezegun.freeze_time().start()` called BEFORE pytest imports
    freezes `time.monotonic()` process-wide; pytest's internal plugin and
    threading code relies on monotonic clock progression and deadlocks
    during collection.
  - **Action:** No code change. The plan's user-level constraint
    ("run the pytest verification on the real (Saturday) system clock to
    confirm the fix works without freezegun at the suite level") already
    marks the Saturday run as the authoritative check. Saturday is a
    weekend day; Sunday is structurally identical (same `weekday() >= 5`
    gate). The Saturday run (86/86 pass, full repo 851/851 pass) is
    sufficient evidence for day-of-week independence.
  - **Files modified:** None. Commit: N/A.

### Out-of-scope items observed (logged but not fixed)

- `ruff check tests/test_main.py` reports 12 pre-existing UP017 / UP027
  stylistic warnings on baseline (confirmed via `git stash` round-trip).
  These were already present before the change and are unrelated to the
  decorator insertion. Left untouched per SCOPE BOUNDARY.

## Self-Check: PASSED

- File exists: `tests/test_main.py` (local modifications present, +16 / -0).
- Commit exists: `47f6979` (found in `git log --oneline`).
- Decorator count: 20 (4 exemplars + 16 new).
- All 16 target tests have the decorator directly above their `def` (audit loop OK).
- Full suite: 86 / 86 on tests/test_main.py, 851 / 851 on full tests/ tree — both
  executed on the real Sat 2026-04-25 AWST clock.
