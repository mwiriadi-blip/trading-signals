# Phase 12 — Deferred Items

Out-of-scope discoveries logged during execution. These are NOT caused by
Phase 12 work and MUST NOT be fixed in this phase per SCOPE BOUNDARY.

## Pre-existing test failures (2026-04-24, during Plan 01 execution)

**Observed:** 16 failures in `tests/test_main.py` against baseline commit
`ca84315` (before any Phase 12 code). Re-confirmed after Plan 01 GREEN —
same 16 failures, no new ones.

**Cause:** Failures appear related to the `weekend skip` date branch
triggering on 2026-04-25 (Saturday) in run-daily-check tests — the
orchestrator short-circuits before invoking the mocks the tests assert on.

Pytest signature (one representative failure):
```
tests/test_main.py::TestCLI::test_force_email_sends_live_email
AssertionError: --force-email must invoke send_daily_email exactly once
assert 0 == 1 (where 0 = len([]))
Captured log: [Sched] weekend skip 2026-04-25 (weekday=5) — no fetch, no state mutation
```

**Full list:**
- tests/test_main.py::TestCLI::test_force_email_sends_live_email
- tests/test_main.py::TestCLI::test_force_email_captures_post_run_state
- tests/test_main.py::TestCLI::test_test_flag_sends_test_prefixed_email_no_state_mutation
- tests/test_main.py::TestCLI::test_force_email_and_test_combined
- tests/test_main.py::TestOrchestrator::test_short_frame_raises_and_no_state_written
- tests/test_main.py::TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape
- tests/test_main.py::TestOrchestrator::test_reversal_long_to_short_preserves_new_position
- tests/test_main.py::TestOrchestrator::test_fetch_failure_exits_nonzero_no_save_state
- tests/test_main.py::TestOrchestrator::test_dashboard_failure_never_crashes_run
- tests/test_main.py::TestOrchestrator::test_dashboard_import_time_failure_never_crashes_run
- tests/test_main.py::TestEmailNeverCrash::test_email_runtime_failure_never_crashes_run
- tests/test_main.py::TestEmailNeverCrash::test_email_import_time_failure_never_crashes_run
- tests/test_main.py::TestRunDailyCheckTupleReturn::test_run_daily_check_returns_4_tuple
- tests/test_main.py::TestRunDailyCheckTupleReturn::test_run_daily_check_test_mode_returns_in_memory_state
- tests/test_main.py::TestCrashEmailBoundary::test_crash_email_includes_last_loaded_state
- tests/test_main.py::TestWarningCarryOverFlow::test_happy_path_save_state_called_exactly_twice

**Disposition:** Deferred to a separate bug-fix plan in a future phase
(likely needs pytest-freezer or fixture date-mocking on test_main.py suite
to avoid wall-clock Saturday bleed-through). Not a Phase 12 concern.

**Delta from Phase 12 Plan 01:** +34 new tests added, all GREEN.
Baseline: 787 passed / 16 failed. After Plan 01: 821 passed / 16 failed.
No regressions introduced.
