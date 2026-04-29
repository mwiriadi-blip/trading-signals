---
quick_id: 260429-sdp
slug: fix-scheduler-email-dispatch
date: 2026-04-29
type: bug-fix
severity: HIGH
files_modified:
  - main.py
  - tests/test_scheduler.py
---

# Fix scheduler-loop email dispatch regression

## Bug

`main.py::_run_daily_check_caught` (introduced commit `3279c312`, 2026-04-23) discards
the 4-tuple from `run_daily_check(args)` via `rc, _, _, _ = job(args)` and never invokes
`_dispatch_email_and_maintain_warnings`. The scheduler-loop path (production droplet
daemon) computes signals, saves state, renders the dashboard — but **never sends the
daily 08:00 AWST email**.

CLI flag paths `--force-email` and `--test` work because they call dispatch directly
in `main()` (lines 1633-1648). Only the default scheduler path is broken.

## Evidence

- Operator droplet `journalctl -u trading-signals` Apr 27/28/29: `[Sched] Run` →
  `[Fetch]` → `[Signal]` → `[State] saved` → `[Dashboard] wrote ...` → `[Sched] done`,
  zero `[Email] ...` log lines on any run.
- `notifier.py` logs `[Email] sent to ...` (line 1495), `[Email] SIGNALS_EMAIL_FROM
  not set ...` (line 1450), `[Email] WARN ...` (1499/1506) — none of these appear in
  7 days of journalctl, proving the function isn't being called.
- 1234-test suite green because `tests/test_scheduler.py:176` monkeypatches
  `_run_daily_check_caught` itself in the loop test, never exercising its body.

## Fix

1. **main.py::_run_daily_check_caught** — unpack the 4-tuple, dispatch email after
   `rc==0` check; skip dispatch on weekend-skip path (`state is None`).
2. **tests/test_scheduler.py** — extend `TestLoopErrorHandling` with new test class
   `TestLoopHappyPathDispatch` asserting `_dispatch_email_and_maintain_warnings` is
   called once with the right args when the wrapped job returns a successful 4-tuple.
   Add weekend-skip case (no dispatch) and rc != 0 case (no dispatch).

## Validation

- `pytest tests/test_scheduler.py -x -q` → all green incl. new tests.
- `pytest -x -q` → ≥ 1234 passing (no regressions).
- `grep _run_daily_check_caught main.py` → one definition, dispatch call present.

## Out of scope

- Phase 16-05 UAT artifacts
- Phase 16.1 plans/summaries
- STATE.md / ROADMAP.md (other than Quick Tasks Completed table)
- notifier.py
- Any other module
