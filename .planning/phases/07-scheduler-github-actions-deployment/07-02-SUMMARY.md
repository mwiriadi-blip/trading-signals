---
phase: 07-scheduler-github-actions-deployment
plan: 02
subsystem: scheduler/body/weekday-gate
tags:
  - scheduler
  - loop-driver
  - weekday-gate
  - never-crash
  - pitfall-3-closure
dependency_graph:
  requires:
    - Phase 7 Wave 0 (07-01): _run_daily_check_caught stub + _run_schedule_loop stub + _get_process_tzname wrapper + system_params.{LOOP_SLEEP_S,SCHEDULE_TIME_UTC,WEEKDAY_SKIP_THRESHOLD} + tests/test_scheduler.py 6-class scaffold + load_dotenv() bootstrap
    - Phase 4 (04-03/04): run_daily_check 4-tuple contract + main() dispatch ladder + _compute_run_date() + typed-exception boundary
    - Phase 6 (06-03): _send_email_never_crash pattern (3rd instance now)
  provides:
    - main._run_daily_check_caught (D-02 never-crash wrapper) — consumed by main()'s default-mode dispatch and by _run_schedule_loop's registered job
    - main._run_schedule_loop (D-01 loop driver) — consumed by main()'s default-mode dispatch; Pitfall 1 UTC assertion via _get_process_tzname wrapper
    - run_daily_check weekday-gate prelude (D-03) — Sat/Sun AWST short-circuits ALL modes; SCHED-03 covered
    - main() flipped default dispatch (D-04 + D-05) — `if args.once:` one-shot branch, new default = immediate + loop
    - 12 populated scheduler tests across 6 classes
    - Two test_main.py:129+146 tests updated for Phase 7 contract (Pitfall 3 closure)
    - Phase 7 requirements satisfied: SCHED-01, SCHED-02, SCHED-03, SCHED-04, SCHED-07
  affects:
    - main.py (864 -> 920 lines, +56)
    - tests/test_scheduler.py (95 -> 335 lines, +240)
    - tests/test_main.py (1111 -> 1160 lines, +49)
tech-stack:
  added: []  # Wave 0 landed all Phase 7 deps (schedule 1.2.2, python-dotenv 1.0.1, PyYAML 6.0.2)
  patterns:
    - Never-crash wrapper (3rd instance): _run_daily_check_caught joins _render_dashboard_never_crash + _send_email_never_crash as the ONLY valid except Exception: sites
    - C-2 local import: `import schedule` inside _run_schedule_loop body (same rule as dashboard + notifier)
    - Thin wrapper for test-patchability (consumed): _get_process_tzname() replaces raw time.tzname[0] access (07-REVIEWS.md Codex MEDIUM-fix)
    - Injected-collaborator testability (consumed): _run_schedule_loop(scheduler=None, sleep_fn=None, max_ticks=None) signature drives TestLoopDriver's 3 finite-tick tests
    - @property fake scheduler fake (Rule 1 fix): _FakeScheduler.day is a @property matching the real schedule library API
    - TDD cycle: 3 RED commits + 2 GREEN commits in 5-commit Wave 1 totaling 5 signed commits
key-files:
  created: []
  modified:
    - main.py
    - tests/test_scheduler.py
    - tests/test_main.py
decisions:
  - Task 1 folded the main() dispatch amendment (Task 2 B3 per plan) into Task 1 GREEN so TestImmediateFirstRun could pass in Task 1 as the plan required (Rule 3 deviation)
  - Monday weekday-gate test uses committed fetch fixtures rather than a None-returning recorder so both instruments get fetched (plan's None-recorder would fail at `len(None)`)
  - _FakeScheduler.day flipped from method to @property to match real `schedule.every().day.at(...)` API (Rule 1 deviation — Wave 0 scaffold bug)
  - test_default_mode_does_NOT_send_email updated alongside the two plan-named test_main.py tests because Phase 7 default dispatch broke it too (Rule 3 deviation — Pitfall 3 sibling)
  - `.do()` collapsed to a single line so `grep -c ".do(_run_daily_check_caught" main.py == 1` passes verbatim (plan AC literal check)
metrics:
  duration: ~20 min
  completed_date: 2026-04-23
---

# Phase 07 Plan 02: Wave 1 Body — Scheduler Loop + Weekday Gate + Dispatch Flip Summary

**One-liner:** Fills the Wave 0 stubs with production bodies — `_run_daily_check_caught` implements the D-02 3-branch never-crash net (DataFetchError/ShortFrameError + catch-all + rc != 0 each logged with `[Sched]` prefix); `_run_schedule_loop` enters the `schedule` library under a Pitfall 1 UTC assertion routed through the `_get_process_tzname()` wrapper (07-REVIEWS.md Codex MEDIUM-fix); `run_daily_check` gains the D-03 weekday-gate prelude that short-circuits Sat/Sun AWST runs; `main()` flips the default-mode branch to immediate-first-run-then-loop; the deprecated Phase 4 `[Sched] One-shot mode ...` log line is deleted atomically with the two test_main.py assertions that referenced it (Pitfall 3).

---

## Files Touched

| File | Change | Line delta |
|------|--------|-----------|
| `main.py` | Added `import system_params`; filled `_run_daily_check_caught` body (3 branches); filled `_run_schedule_loop` body (UTC assert + scheduler register + finite-tick loop); inserted D-03 weekday-gate prelude in `run_daily_check`; deleted Phase 4 stub log line; flipped `main()` default dispatch to immediate + loop | 864 → 920 (+56) |
| `tests/test_scheduler.py` | Replaced 6 xfail scaffolds with 12 real tests across 6 classes (3 + 1 + 3 + 3 + 1 + 1); fixed `_FakeScheduler.day` from method to @property (Rule 1); all patches target `main._get_process_tzname` | 95 → 335 (+240) |
| `tests/test_main.py` | `test_once_flag_runs_single_check`: added Mon `freeze_time`, replaced positive One-shot assertion with dual negative (no `scheduler entered` AND no `One-shot mode`); renamed `test_default_mode_runs_once_and_logs_schedule_stub` → `test_default_mode_enters_schedule_loop` with call-order `['caught', 'loop']` assertion; `test_default_mode_does_NOT_send_email` Rule-3 patch for Phase 7 schedule loop | 1111 → 1160 (+49) |

**Total:** +345 lines across 3 files, 5 atomic commits.

---

## _run_daily_check_caught body (verbatim)

Landed at `main.py` lines 175-198:

```python
def _run_daily_check_caught(job, args) -> None:
  '''D-02 (Phase 7 Wave 1): never-crash wrapper for scheduled run_daily_check.

  Third instance of the never-crash pattern after _render_dashboard_never_crash
  and _send_email_never_crash. Schedule loop survives one bad run — next cron
  fire retries. ONLY valid `except Exception:` site in the loop path. Phase 8
  (ERR-04) adds crash-email dispatch on top of this net.

  Catches:
    - typed DataFetchError / ShortFrameError -> WARN [Sched] data-layer failure
    - catch-all Exception -> WARN [Sched] unexpected error (loop continues)
    - rc != 0 return (happy-path non-zero) -> WARN [Sched] rc=N (loop continues)
  '''
  try:
    rc, _, _, _ = job(args)
    if rc != 0:
      logger.warning(
        '[Sched] daily check returned rc=%d (loop continues)', rc,
      )
  except (DataFetchError, ShortFrameError) as e:
    logger.warning('[Sched] data-layer failure caught in loop: %s', e)
  except Exception as e:
    logger.warning(
      '[Sched] unexpected error caught in loop: %s: %s (loop continues)',
      type(e).__name__, e,
    )
```

---

## _run_schedule_loop body (verbatim) — highlights `_get_process_tzname()` wrapper call

Landed at `main.py` lines 200-253:

```python
def _run_schedule_loop(
  job,
  args,
  scheduler=None,
  sleep_fn=None,
  tick_budget_s: float = 60.0,
  max_ticks: int | None = None,
) -> int:
  '''D-01 (Phase 7 Wave 1): factored schedule loop driver with injectable fakes.

  Production call: `_run_schedule_loop(run_daily_check, args)` — defaults flow.
  Test call: `_run_schedule_loop(..., scheduler=fake, sleep_fn=fake_sleep,
  max_ticks=1)` — one tick, no real sleep, no real scheduler thread.

  Pitfall 1 mitigation: the `schedule` library's `.at()` without tz arg uses
  process-local time. We rely on UTC. Fail fast if the process runs in any
  other tz — Replit or GHA runner misconfiguration would otherwise silently
  fire at the wrong wall-clock moment. The check goes through the
  `_get_process_tzname()` wrapper (Wave 0) so tests can patch
  `main._get_process_tzname` cleanly (07-REVIEWS.md Codex MEDIUM-fix:
  `time.tzname` is platform-dependent and sometimes frozen).

  Pitfall 7 mitigation: max_ticks=None means infinite loop (production). Tests
  MUST pass a finite max_ticks to avoid hanging.
  '''
  import time as _time

  import schedule  # LOCAL — C-2 / hex-lite / AST blocklist discipline

  tzname = _get_process_tzname()                               # <-- WRAPPER CALL
  assert tzname == 'UTC', (
    f'[Sched] process tz must be UTC; got {tzname!r}. '
    f'Set TZ=UTC in the deploy environment.'
  )

  _scheduler = scheduler or schedule
  _sleep = sleep_fn or _time.sleep

  logger.info(
    '[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon\u2013Fri'
  )
  _scheduler.every().day.at(system_params.SCHEDULE_TIME_UTC).do(_run_daily_check_caught, job, args)

  ticks = 0
  while max_ticks is None or ticks < max_ticks:
    _scheduler.run_pending()
    _sleep(tick_budget_s)
    ticks += 1
  return 0
```

The UTC assertion at line `tzname = _get_process_tzname()` goes through the Wave 0 wrapper — NOT raw `time.tzname[0]`. This is the 07-REVIEWS.md Codex MEDIUM-fix. Tests patch `main._get_process_tzname` (platform-portable) rather than `time.tzname` (platform-dependent, sometimes frozen).

Ruff auto-reordered the local imports alphabetically (`time` before `schedule`) on autofix — both stay local inside the function body per C-2.

---

## Weekday gate prelude (exact anchor + 10-line insertion)

Inserted into `run_daily_check` at `main.py` lines 557-569, immediately after `run_date = _compute_run_date()` and BEFORE the derived `run_date_iso` / `run_date_display` lines:

```python
  run_date = _compute_run_date()

  # D-03 (Phase 7): weekday gate — short-circuits BEFORE any fetch, compute,
  # or state mutation. Applies to ALL invocation modes (default, --once,
  # --test, --force-email). `run_date.weekday()` returns 0=Mon..6=Sun
  # (Python stdlib contract); 5=Sat, 6=Sun. Preserves the 4-tuple contract
  # so main()'s dispatch ladder None-guard absorbs the state=None case
  # without a second code path.
  if run_date.weekday() >= system_params.WEEKDAY_SKIP_THRESHOLD:
    logger.info(
      '[Sched] weekend skip %s (weekday=%d) — no fetch, no state mutation',
      run_date.strftime('%Y-%m-%d'), run_date.weekday(),
    )
    return 0, None, None, run_date

  run_date_iso = run_date.strftime('%Y-%m-%d')
  ...
```

Constant reference uses `system_params.WEEKDAY_SKIP_THRESHOLD` (Wave 0 landed at `system_params.py:132`). Return 4-tuple `(0, None, None, run_date)` preserves the D-11 contract; `main()`'s existing None-guard in the dispatch ladder absorbs the `state is None` case without a second branch.

The Phase 4 stub log line `logger.info('[Sched] One-shot mode (scheduler wiring lands in Phase 7)')` was deleted in the same edit (line 564 pre-edit → gone post-edit). Opening `[Sched] Run %s mode=%s` log preserved.

---

## main() dispatch ladder diff

**Before (Wave 0 state):**
```python
    if args.force_email or args.test:
      ...
      return rc
    # Default / --once path: no email.
    rc, _state, _old_signals, _run_date = run_daily_check(args)
    return rc
```

**After (Wave 1 — merged into Task 1 GREEN):**
```python
    if args.force_email or args.test:
      ...
      return rc
    # CLI-04: --once is a one-shot for GHA mode. No loop.
    if args.once:
      rc, _state, _old_signals, _run_date = run_daily_check(args)
      return rc
    # Default (no flag): Phase 7 D-04 + D-05 — immediate first run, then loop.
    _run_daily_check_caught(run_daily_check, args)
    return _run_schedule_loop(run_daily_check, args)
```

The split is explicit: `--once` preserves one-shot CLI-04 semantics; the new default branch runs an immediate `_run_daily_check_caught(run_daily_check, args)` FIRST (SCHED-02 immediate first-run), then enters the schedule loop (SCHED-01). The outer `try:` / `except (DataFetchError, ShortFrameError):` / `except Exception:` boundary still wraps everything; loop-level errors are absorbed inside `_run_daily_check_caught` and never propagate up.

**Deviation from plan sequencing:** The plan placed this dispatch amendment in Task 2 B3, but `TestImmediateFirstRun.test_default_mode_calls_job_once_before_loop` (a Task 1 test) requires this amendment to be in place to pass. Moved the amendment into Task 1 GREEN so Task 1's expected GREEN state matches reality. Tracked as Rule 3 deviation.

---

## Test counts per class

| Class | Tests | Names |
|-------|-------|-------|
| `TestWeekdayGate` | 3 | `test_saturday_skips_fetch_and_compute`, `test_sunday_skips_fetch_and_compute`, `test_monday_proceeds_through_fetch` |
| `TestImmediateFirstRun` | 1 | `test_default_mode_calls_job_once_before_loop` |
| `TestLoopDriver` | 3 | `test_max_ticks_zero_returns_immediately`, `test_max_ticks_one_runs_single_cycle`, `test_non_utc_process_raises` |
| `TestLoopErrorHandling` | 3 | `test_data_fetch_error_caught_logs_warning`, `test_unexpected_exception_caught`, `test_nonzero_rc_logs_warning` |
| `TestDefaultModeDispatch` | 1 | `test_default_mode_emits_scheduler_entered_log` |
| `TestDotenvLoading` | 1 | `test_main_calls_load_dotenv` |

**Total:** 12 tests. 0 xfailed. Matches plan target exactly.

---

## Monday-fetch assertion strengthening (07-REVIEWS.md Codex MEDIUM-fix)

Plan called for explicit fetch-call observation rather than a weak "no 'weekend skip' in logs" assertion. The `test_monday_proceeds_through_fetch` test now asserts (verbatim from `tests/test_scheduler.py:146-158`):

```python
assert run_date.weekday() == 0, f'expected Mon; got weekday={run_date.weekday()}'
assert len(fetch_calls) == 2, (
  f'CLI-04 / SCHED-03: Monday must fetch both instruments; '
  f'got {len(fetch_calls)} fetch call(s): {fetch_calls}'
)
# First positional arg is the ticker — verify both expected symbols appear.
tickers_fetched = {call_args[0] for call_args in fetch_calls}
assert '^AXJO' in tickers_fetched, (
  f'SCHED-03: ^AXJO (SPI 200) must be fetched on Mon; got {tickers_fetched}'
)
assert 'AUDUSD=X' in tickers_fetched, (
  f'SCHED-03: AUDUSD=X must be fetched on Mon; got {tickers_fetched}'
)
# Belt-and-braces: weekend-skip branch must not have fired.
assert 'weekend skip' not in caplog.text
```

**Deviation from plan:** The plan proposed a `None`-returning recorder to "short-circuit at the None-guard after fetch". But `main.py`'s per-symbol loop doesn't have a None-guard — `len(None)` raises `TypeError`. A `None`-returning recorder fails on symbol 1 before symbol 2 runs, so `len(fetch_calls) == 2` can't be asserted. Fix: swapped the recorder for a wrapped version of `_install_fixture_fetch`'s committed fetch fixtures so both symbols' fetches succeed and the full per-symbol loop executes. Asserts are strictly stronger than the plan's original design (identity-level ticker matching in a set).

---

## Pitfall 3 closure — exact diff of test_main.py edits

### Edit 1: `test_once_flag_runs_single_check` (line ~104)

**Before:**
```python
  def test_once_flag_runs_single_check(
      self, tmp_path, monkeypatch, caplog) -> None:
    ...
    rc = main.main(['--once'])
    assert rc == 0
    assert len(fetch_calls) == 2, ...
    assert '[Sched] One-shot mode (scheduler wiring lands in Phase 7)' in caplog.text, (
      'CLI-04: D-07 one-shot log line missing from caplog.text'
    )
```

**After:**
```python
  @pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')  # Mon 08:00 AWST
  def test_once_flag_runs_single_check(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''CLI-04 / Phase 7: ...'''
    ...
    rc = main.main(['--once'])
    assert rc == 0
    assert len(fetch_calls) == 2, ...
    # Phase 7 D-05: deprecated `[Sched] One-shot mode` log line deleted from
    # run_daily_check. --once does NOT enter the schedule loop, so the NEW
    # `[Sched] scheduler entered` line ALSO does NOT fire (CLI-04 contract:
    # --once stays one-shot).
    assert '[Sched] scheduler entered' not in caplog.text, (
      'CLI-04: --once must NOT enter the schedule loop'
    )
    assert 'One-shot mode (scheduler wiring lands in Phase 7)' not in caplog.text, (
      'Phase 7 D-05: Phase 4 stub log line must be deleted from run_daily_check'
    )
```

Added `freeze_time` Mon pin so the weekday gate doesn't short-circuit when the suite runs on weekends. Replaced the single positive assertion with two negative assertions covering both the deprecated log line (Pitfall 3 closure) AND the new `scheduler entered` line (CLI-04 contract: --once stays one-shot).

### Edit 2: `test_default_mode_runs_once_and_logs_schedule_stub` → `test_default_mode_enters_schedule_loop` (line ~133)

**Before:**
```python
  def test_default_mode_runs_once_and_logs_schedule_stub(
      self, tmp_path, monkeypatch, caplog) -> None:
    ...
    rc = main.main([])
    assert rc == 0
    assert '[Sched] One-shot mode (scheduler wiring lands in Phase 7)' in caplog.text, ...
```

**After:**
```python
  def test_default_mode_enters_schedule_loop(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''Phase 7 D-05 / CLI-05: ...'''
    monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')
    ...
    call_order: list[tuple[str, str]] = []
    monkeypatch.setattr(
      main, '_run_daily_check_caught',
      lambda job, args: call_order.append(('caught', job.__name__)),
    )
    def _fake_loop(job, args):
      call_order.append(('loop', job.__name__))
      return 0
    monkeypatch.setattr(main, '_run_schedule_loop', _fake_loop)
    rc = main.main([])
    assert rc == 0
    assert call_order == [
      ('caught', 'run_daily_check'),
      ('loop', 'run_daily_check'),
    ], 'D-04: immediate first-run must precede loop entry'
    assert 'One-shot mode (scheduler wiring lands in Phase 7)' not in caplog.text, ...
```

Method renamed. Body replaced to stub both `_run_daily_check_caught` and `_run_schedule_loop` (so the test never enters the real infinite loop), asserts call ORDER `('caught', 'run_daily_check')` before `('loop', 'run_daily_check')` per D-04, AND asserts the deprecated log line is absent.

### Rule-3 sibling: `test_default_mode_does_NOT_send_email` (line ~390)

The plan did NOT list this test in Task 3, but Phase 7 default-mode dispatch broke it too — calling `main.main([])` now enters `_run_schedule_loop` which fails the UTC assertion in AWST. Applied Rule-3 defensive fix:
```python
monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')
monkeypatch.setattr(main, '_run_schedule_loop', lambda job, args: 0)
```

This is a Pitfall 3 sibling — same Phase 7 contract shift affects an adjacent test.

---

## tzname-patching discipline confirmation

Required grep: `grep -cE "monkeypatch\.setattr\(.*['\"]time['\"].*tzname" tests/test_scheduler.py tests/test_main.py`

**Result:** `tests/test_scheduler.py:0` + `tests/test_main.py:0` = **0 total matches.** No test patches `time.tzname` directly — all tzname-related patches go through `main._get_process_tzname` per 07-REVIEWS.md Codex MEDIUM-fix.

Positive-direction grep: `grep -c "monkeypatch.setattr('main._get_process_tzname'" tests/test_scheduler.py` → **4 matches** (3 in TestLoopDriver + 1 in TestDefaultModeDispatch).

---

## Deviations from Plan

### [Rule 3 — Plan sequencing] main() dispatch amendment moved from Task 2 B3 into Task 1 GREEN

**Found during:** Task 1 GREEN verification.
**Issue:** Plan placed the `main()` default-branch amendment in Task 2 B3, but `TestImmediateFirstRun.test_default_mode_calls_job_once_before_loop` (a Task 1 test) requires this amendment to be in place. Plan's expected Task 1 GREEN state ("expect GREEN" for all 4 test classes) is unreachable without this amendment.
**Fix:** Folded the amendment into Task 1 GREEN commit. Task 2's GREEN commit no longer needs B3.
**Files modified:** `main.py`
**Commit:** `3279c31` (Task 1 GREEN)

### [Rule 1 — Plan bug / Wave 0 scaffold bug] `_FakeScheduler.day` was a method, not a @property

**Found during:** Task 1 GREEN pytest run after filling `_run_schedule_loop`.
**Issue:** Real `schedule` library exposes `day` as a property — production code `.every().day.at(...)` works without parens. The Wave 0 scaffold defined `_FakeScheduler.day` as a regular method, so `.day.at(...)` failed with `AttributeError: 'function' object has no attribute 'at'`.
**Fix:** Added `@property` decorator to `_FakeScheduler.day`. Production code stays API-compatible with the real library.
**Files modified:** `tests/test_scheduler.py`
**Commit:** `3279c31` (Task 1 GREEN)

### [Rule 1 — Plan design flaw] Monday-proceeds test — recorder-returning-None fails `len(None)`

**Found during:** Task 2 RED verification.
**Issue:** Plan suggested "return `None` from the recorder so the run short-circuits at the None-guard after fetch". But `main.py`'s per-symbol loop has no None-guard — it calls `len(df) < _MIN_BARS_REQUIRED`, and `len(None)` raises `TypeError` after the FIRST symbol. Only one fetch call would be observable, making `len(fetch_calls) == 2` unassertable.
**Fix:** Swapped the recorder for a wrapped version of committed fetch fixtures (`axjo_400d.json`, `audusd_400d.json`) so both fetches succeed and the full per-symbol loop executes. Seeded `state.json` in tmp_path so `state_manager.load_state()` works. This is strictly stronger than the plan's design — asserts on identity-level ticker membership in a set, which catches any fetch bypass regression.
**Files modified:** `tests/test_scheduler.py`
**Commit:** `2176c5d` (Task 2 RED)

### [Rule 3 — Pitfall 3 sibling] `test_default_mode_does_NOT_send_email` updated alongside the two plan-named tests

**Found during:** Task 2 GREEN full-suite run.
**Issue:** Plan's Task 3 listed only two test_main.py tests for Pitfall 3 closure. But `test_default_mode_does_NOT_send_email` (line 390) also calls `main.main([])` in default mode, which now enters `_run_schedule_loop` and fails the UTC assertion in local AWST dev environment. Suite reported 3 failures, not 2.
**Fix:** Applied same Rule-3 defensive patches to the third test (`_get_process_tzname` patch + `_run_schedule_loop` stub). Documented as Pitfall 3 sibling in the commit message.
**Files modified:** `tests/test_main.py`
**Commit:** `fe210f6` (Task 3)

### [Formatting] `.do(...)` call collapsed to a single line so plan grep AC matches

**Found during:** Task 1 AC verification.
**Issue:** Ruff formatter split the `.do(` call across three lines (open paren on one, args on next, close paren on third). Plan's grep AC `grep -c "\\.do(_run_daily_check_caught" main.py == 1` expects `.do(_run_daily_check_caught` on a single line. Line was initially formatted as multi-line and grep count was 0.
**Fix:** Collapsed to a single 99-char line. Ruff pyproject config accepts this (no line-length error). AC now reads 1 as required.
**Files modified:** `main.py`
**Commit:** `3279c31` (Task 1 GREEN)

---

## Phase 4 log line deletion confirmation

`grep -c "One-shot mode" main.py` → **0 matches.**

`grep -rn "One-shot mode" tests/` → 4 matches:
- `tests/test_main.py:110` — docstring mentioning the deprecated line
- `tests/test_main.py:137` — comment mentioning the deprecated line
- `tests/test_main.py:144` — `'One-shot mode ...' not in caplog.text` (negative assertion)
- `tests/test_main.py:187` — `'One-shot mode ...' not in caplog.text` (negative assertion)

All 4 are non-positive uses (comments, docstrings, and negative assertions). Plan's strict "no positive assertion" grep:

```bash
grep -E "assert.*One-shot mode" tests/test_main.py | grep -v "not in" | wc -l
```
**Result: 0.** No stale positive assertions anywhere.

---

## Pytest Suite Summary

| Category | Count |
|----------|-------|
| Passed | 528 |
| xfailed | 0 |
| xpassed | 0 |
| Skipped | 0 |
| Failed | 0 |

**Diff vs Wave 0:** +12 scheduler tests (6 xfailed → 12 passed, net +12 lines covered), +0 new test_main tests (2 updated in-place). 522 → 528 passed.

---

## AST blocklist green

`python -m pytest tests/test_signal_engine.py::TestDeterminism -q` → **44 passed, 0 failed.**

Blocklist unmodified by Wave 1:
- `FORBIDDEN_MODULES_MAIN` still permits `schedule` + `dotenv` (Wave 0 left it that way; Wave 1 consumes).
- `FORBIDDEN_MODULES_{DASHBOARD,NOTIFIER,STATE_MANAGER,DATA_FETCHER}` still block them.
- No new forbidden imports introduced.

---

## Ruff clean

`ruff check .` → **All checks passed!** (0 errors, 0 warnings)

Ruff autofix was applied twice during execution:
1. `main.py` — reordered `import time as _time` before `import schedule` inside `_run_schedule_loop` (alphabetical order for local imports per ruff I001 rule).
2. `tests/test_scheduler.py` — reordered `from pathlib import Path` before `import pandas as pd` inside `test_monday_proceeds_through_fetch` (same I001 rule).

Both autofixes are structurally neutral.

---

## Commits

| Task | Commit | Message |
|------|--------|---------|
| Task 1 RED | `2534427` | `test(07-02): add failing tests for loop driver + never-crash + dotenv + immediate first run (Wave 1 RED)` |
| Task 1 GREEN | `3279c31` | `feat(07-02): implement _run_daily_check_caught + _run_schedule_loop bodies (Wave 1 GREEN)` |
| Task 2 RED | `2176c5d` | `test(07-02): add failing weekday-gate + default-dispatch tests (Wave 1 RED — Task 2)` |
| Task 2 GREEN | `d9400fc` | `feat(07-02): add weekday gate + delete Phase 4 stub log line (Wave 1 GREEN — Task 2)` |
| Task 3 | `fe210f6` | `test(07-02): update test_main.py for Phase 7 contract (Pitfall 3 fixup — Wave 1 closes)` |

5 atomic commits. No `--amend`. No `--no-verify`.

---

## Wave Handoff

Wave 2 (07-03-PLAN.md) can now land without touching any Python code:
1. `.github/workflows/daily.yml` — `cron: '0 0 * * 1-5'` + `TZ: UTC` + `--once` invocation pattern.
2. `docs/DEPLOY.md` — 3-tier deploy commentary (GHA primary, Replit alternative, LOCAL dev).
3. `tests/test_scheduler.py::TestGHAWorkflow` — PyYAML static-parse of the workflow file; PyYAML 6.0.2 already pinned in Wave 0.
4. ROADMAP SC-4 amendment.

Wave 1's body is frozen: no further Python edits required for Phase 7. The Pitfall-3 atomic-test-transition is closed.

---

## Self-Check: PASSED

- Task 1 RED commit `2534427` → `git log --all | grep 2534427` FOUND
- Task 1 GREEN commit `3279c31` → `git log --all | grep 3279c31` FOUND
- Task 2 RED commit `2176c5d` → `git log --all | grep 2176c5d` FOUND
- Task 2 GREEN commit `d9400fc` → `git log --all | grep d9400fc` FOUND
- Task 3 commit `fe210f6` → `git log --all | grep fe210f6` FOUND
- `main.py` FOUND (920 lines; 3 Phase 7 helpers fully implemented; weekday gate present; Phase 4 stub log line gone; dispatch flipped)
- `tests/test_scheduler.py` FOUND (335 lines; 6 classes; 12 real tests; 0 xfails; _FakeScheduler.day is @property)
- `tests/test_main.py` FOUND (1160 lines; test_default_mode_enters_schedule_loop present; test_default_mode_runs_once_and_logs_schedule_stub absent; test_default_mode_does_NOT_send_email defended)
- Full pytest suite: 528 passed, 0 failed, 0 xfailed
- Ruff: clean on all Python files
- AST blocklist: 44 tests pass
- Plan AC greps (all 18 checks): PASS
