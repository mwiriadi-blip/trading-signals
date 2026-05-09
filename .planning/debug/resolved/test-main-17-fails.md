---
slug: test-main-17-fails
status: resolved
trigger: |
  17 pre-existing failures in tests/test_main.py discovered during phase 27-16
  verification (2026-05-10). Verified by `git stash -u` to be pre-existing on
  HEAD before phase 27-15 commit ba4e56a — i.e. they did NOT regress in 27-15
  or 27-16. Both phases were comment/doc-only and don't touch main.py code.
  Failures span 6 test classes spread across CLI, orchestrator,
  email-never-crash, run_daily_check tuple return, crash-email boundary, and
  warning carry-over flows. Likely connected to phase 27-13 main.py split
  (cli_parser + daily_loop + interactive + scheduler_driver) — tests that
  patched `main.<name>` may be silently no-op'ing because the symbol moved
  to a daughter module.
created: 2026-05-10
updated: 2026-05-10
---

# Debug: test_main.py 17 failures (post-27-13 split likely)

## Symptoms

- **Expected behavior:** Full test suite green. Phase 27-13 SUMMARY claims "main.py <150 LOC entry+shim; CLI surface unchanged"; phase 27-14 SUMMARY claims "2003/2003 full suite green" (2026-05-08).
- **Actual behavior:** 17 failures, all in `tests/test_main.py`. Suite total: 2013 passed, 17 failed.
- **Error messages:** Mixed shapes. Sample: `assert '[Email] send failed' in caplog.text` where `caplog.text == ''` — log emission seems missing OR the test's monkeypatch target is no longer reached at runtime.
- **Timeline:** Discovered 2026-05-10 during phase 27-16 verification. Verified pre-existing via stash-test (same 17 failures on HEAD `ba4e56a` before any 27-15/27-16 changes). Phase 27-14 SUMMARY claims 2003/2003 green on 2026-05-08, so the regression introduced between 27-14 commit and current HEAD. Candidates: 27-IN-* / 27-WR-* fix commits (`fix(27-IN-06)` hoist time import, `fix(27-IN-04)` reduce dashboard_legacy/__init__.py, `fix(27-IN-03)` notifier CLI logging.basicConfig force=True, `fix(27-IN-02)` state_manager docstring, `fix(27-IN-01)` math.isnan, `fix(27-WR-08..01)` various). Most likely culprit: `fix(27-WR-08)` collapse redundant isinstance check in renderer, or one of the IN-* fixes that ran AFTER 27-14 verification.
- **Reproduction:** `.venv/bin/pytest tests/test_main.py --tb=short`. Stable repro — same 17 fail every run.

## Failing tests (17)

```
TestCLI:
  - test_force_email_sends_live_email
  - test_force_email_captures_post_run_state
  - test_test_flag_sends_test_prefixed_email_no_state_mutation
  - test_force_email_and_test_combined
  - test_default_mode_DOES_send_email_via_immediate_first_run

TestOrchestrator:
  - test_short_frame_raises_and_no_state_written
  - test_orchestrator_reads_both_int_and_dict_signal_shape
  - test_reversal_long_to_short_preserves_new_position
  - test_fetch_failure_exits_nonzero_no_save_state
  - test_dashboard_failure_never_crashes_run
  - test_dashboard_import_time_failure_never_crashes_run

TestEmailNeverCrash:
  - test_email_runtime_failure_never_crashes_run
  - test_email_import_time_failure_never_crashes_run

TestRunDailyCheckTupleReturn:
  - test_run_daily_check_returns_4_tuple
  - test_run_daily_check_test_mode_returns_in_memory_state

TestCrashEmailBoundary:
  - test_crash_email_includes_last_loaded_state

TestWarningCarryOverFlow:
  - test_happy_path_save_state_called_exactly_twice
```

## Evidence

- timestamp: 2026-05-10
  observation: All 17 failures share identical pattern — `caplog.text == ''` or `state is None` or
  assertion fires against an unpatched stub when expecting a patched one.
  Running one failure inline shows: `[Sched] weekend skip 2026-05-10 (weekday=6) — no fetch, no state mutation`.
  The weekend gate in `_run_daily_check_impl` returns `(0, None, None, run_date)` before any
  fetch/signal/email/dashboard logic executes. Since 2026-05-10 is Saturday and the tests have no
  `@pytest.mark.freeze_time` pins to a weekday, the gate short-circuits every test that exercises
  the run body.
- timestamp: 2026-05-10
  observation: Root cause NOT the 27-13 monkeypatch-path hypothesis. Patches on `notifier.send_daily_email`
  are correct (local `import notifier` inside body reuses cached sys.modules entry). The real cause is
  calendar-dependent test brittleness — no freeze_time decorator = tests pass Mon-Fri, fail Sat-Sun.
  This explains why phase 27-14 SUMMARY claimed 2003/2003 green (ran on a weekday) and the failures
  appeared only when verification ran on Saturday 2026-05-10.

## Eliminated

- Hypothesis: 27-13 monkeypatch path shift (main.X vs daughter.X). ELIMINATED. Patches on `notifier`,
  `main.data_fetcher`, `main.signal_engine` etc. are correctly targeted. The issue is purely the
  weekend gate firing before patched code is reached.
- Hypothesis: 27-IN-* / 27-WR-* commits as regression source. ELIMINATED. The root cause is
  calendar-sensitive tests lacking freeze_time — the weekend gate has always existed; these tests
  never had the decorator.

## Resolution

- **root_cause:** 17 tests in `tests/test_main.py` that exercise `run_daily_check` (directly or via
  `main.main`) lacked `@pytest.mark.freeze_time` pinning to a weekday. `_run_daily_check_impl` has a
  hard weekday gate that returns `(0, None, None, run_date)` on Saturday/Sunday. When these tests run
  on a weekend the gate short-circuits before any fetch, signal, email, or dashboard logic executes,
  causing every downstream assertion to fail. Tests passed when run on weekdays (hence the 2003/2003
  green claim from 27-14 which ran on a Thursday).
- **fix:** Added `@pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')` (Monday 08:00 AWST) to all
  17 failing test methods in `tests/test_main.py`. No production code changed.
- **files_touched:** `tests/test_main.py` (17 decorator insertions)
- **suite_result:** 2030 passed (full suite), 0 failed.
