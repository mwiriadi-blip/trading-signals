# Phase 13 — Deferred Items

Out-of-scope discoveries during plan execution. Not addressed in Phase 13;
recorded here for future investigation.

---

## Pre-existing tests/test_main.py failures (16 tests)

**Discovered during:** Plan 13-01 final verification (`pytest -q`)
**Verified pre-existing:** Reproduced on parent commit `b1f9b8f` (the v1.0
cleanup head, before Phase 13 work began) by checking out
`tests/conftest.py` and `tests/test_web_healthz.py` from `b1f9b8f` and
running `pytest tests/test_main.py::TestOrchestrator::test_fetch_failure_exits_nonzero_no_save_state -x` — the test failed with the same `AssertionError: ERR-01: expected exit 2 for DataFetchError, got 0` even before any 13-01 changes.

**Failing tests:**

- `tests/test_main.py::TestOrchestrator::test_fetch_failure_exits_nonzero_no_save_state`
- `tests/test_main.py::TestOrchestrator::test_dashboard_failure_never_crashes_run`
- `tests/test_main.py::TestOrchestrator::test_dashboard_import_time_failure_never_crashes_run`
- `tests/test_main.py::TestEmailNeverCrash::test_email_runtime_failure_never_crashes_run`
- `tests/test_main.py::TestEmailNeverCrash::test_email_import_time_failure_never_crashes_run`
- `tests/test_main.py::TestRunDailyCheckTupleReturn::test_run_daily_check_returns_4_tuple`
- `tests/test_main.py::TestRunDailyCheckTupleReturn::test_run_daily_check_test_mode_returns_in_memory_state`
- `tests/test_main.py::TestCrashEmailBoundary::test_crash_email_includes_last_loaded_state`
- `tests/test_main.py::TestWarningCarryOverFlow::test_happy_path_save_state_called_exactly_twice`
- (7 additional `tests/test_main.py` failures rolled up under the same `pytest -q` summary — `16 failed, 898 passed`)

**Symptom:** First failing test reports `rc == 0` instead of expected `rc == 2`
when `DataFetchError` is raised by `data_fetcher.fetch_ohlcv`. This indicates
`main.main(['--once'])` is no longer mapping `DataFetchError` → exit 2 (ERR-01)
the way the test expects.

**Possible causes (not investigated in 13-01 — out of scope):**
- main.py orchestrator was refactored in Phase 9/10 and the typed-exception
  boundary may have shifted.
- Test fixtures may have been updated without main.py being kept in sync.

**Scope decision:** Plan 13-01 ships test infrastructure (autouse fixture,
hex-boundary update, skeleton test files, doc section). It does NOT modify
`main.py` or `tests/test_main.py`. Per execute-plan.md scope-boundary rule,
out-of-scope failures are logged here and not auto-fixed.

**Suggested next step:** Spawn a `/gsd-debug` session (or fold into Phase 16
hardening) to reconcile main.py's exception mapping with the test
expectations, OR update the test expectations to match the current main.py
behavior — whichever reflects the intended ERR-01 contract.

**Verification commands:**

```bash
.venv/bin/pytest tests/test_main.py -q
# Current: 16 failed, lots passed
.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_fetch_failure_exits_nonzero_no_save_state -x
# Confirm pre-existing: AssertionError 'expected exit 2 for DataFetchError, got 0'
```

## tests/test_main.py::TestCLI::test_force_email_sends_live_email — date-dependent failure

**Discovered by:** Plan 13-04 executor (worktree agent-acc5a2a55897f266f)
**Date:** 2026-04-25
**Status:** Pre-existing on plan base c7f5c76 — confirmed with stash + checkout test.

The test invokes `main.main(['--force-email'])` and expects `send_daily_email` to be called once. On 2026-04-25 (Saturday, weekday=5) main hits the weekend-skip branch at main.py:1043 and short-circuits before sending email, so `len(sent) == 0` and the assertion fires.

Out of scope for Phase 13 (web/routes only). Not introduced by Phase 13 changes — reproduced cleanly with state.py + test_web_state.py reverted to base. Likely a pytest-freezer freeze missing or a `--force-email` design that should bypass the weekday gate.

Suggested follow-up: a Phase 13.x or Phase 16 hardening task to either (a) freeze the test to a weekday, or (b) make `--force-email` bypass the weekend-skip per its name.
