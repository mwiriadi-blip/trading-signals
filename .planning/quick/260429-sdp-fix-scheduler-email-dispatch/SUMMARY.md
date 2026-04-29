---
quick_id: 260429-sdp
slug: fix-scheduler-email-dispatch
date: 2026-04-29
status: complete
type: bug-fix
severity: HIGH
commit: 879730d
files_modified:
  - main.py
  - tests/test_scheduler.py
  - tests/test_main.py
one_liner: "Fixed silent regression where the scheduler-loop daemon stopped sending daily 08:00 AWST emails after a 2026-04-23 refactor — `_run_daily_check_caught` discarded `run_daily_check`'s 4-tuple and never invoked `_dispatch_email_and_maintain_warnings`; restored dispatch + locked the contract with 4 regression tests + inverted a Phase-4 fossil test that was enforcing the bug."
---

# Fix scheduler-loop email dispatch regression

## Diagnosis

**Bug:** `main.py::_run_daily_check_caught` (last touched commit `3279c312`,
2026-04-23) discarded the 4-tuple from `run_daily_check(args)` via
`rc, _, _, _ = job(args)` and never called `_dispatch_email_and_maintain_warnings`.
Result: the production droplet daemon (default flags = scheduler loop) computed
signals, saved state, rendered the dashboard, but **never sent the daily 08:00
AWST email** on any run after the daemon was last started (Apr 26).

**Discovery path:**
1. Operator reported missing daily emails ~7 days
2. SSH check on droplet — `systemctl status trading-signals` showed daemon healthy, PID 50643 running since Apr 26
3. `journalctl -u trading-signals` showed clean runs Apr 27/28/29 with zero `[Email] ...` log lines (notifier logs on every code path — success, missing env, failure — so absence proves the function isn't called)
4. Read `_run_daily_check_caught` body — `rc, _, _, _ = job(args)` discard pattern dropped state/old_signals/run_date that downstream `_dispatch_email_and_maintain_warnings` needs
5. CLI paths `--force-email` / `--test` had been updated when `run_daily_check` was refactored to return a 4-tuple; the never-crash wrapper was missed

**Why tests didn't catch it:**
- `tests/test_scheduler.py:176` monkeypatches `_run_daily_check_caught` itself, so the loop tests never exercised its body
- `tests/test_main.py::TestCLI::test_default_mode_does_NOT_send_email` was a Phase-4 fossil whose docstring acknowledged "Phase 7 update: default mode now enters the schedule loop" but kept the original "no email" assertion — actively enforcing the bug

## Fix

**main.py::_run_daily_check_caught** (1 function):
```python
# Before: discard everything except rc
rc, _, _, _ = job(args)
if rc != 0:
    logger.warning(...)
# (silent end — no dispatch)

# After: unpack, dispatch on success
rc, state, old_signals, run_date = job(args)
if rc != 0:
    logger.warning(...)
    return
if state is None or old_signals is None or run_date is None:
    return  # weekend skip
_dispatch_email_and_maintain_warnings(
    state, old_signals, run_date,
    is_test=False, persist=True,
)
```

**tests/test_scheduler.py** (1 new class, 4 tests):
- `TestLoopHappyPathDispatch::test_happy_path_dispatches_email` — exactly one dispatch with persist=True / is_test=False
- `TestLoopHappyPathDispatch::test_weekend_skip_does_not_dispatch` — state=None branch
- `TestLoopHappyPathDispatch::test_nonzero_rc_does_not_dispatch` — rc=2 branch
- `TestLoopHappyPathDispatch::test_exception_path_does_not_dispatch` — exception branch

**tests/test_main.py::TestCLI** (1 inverted test):
- `test_default_mode_does_NOT_send_email` → `test_default_mode_DOES_send_email_via_immediate_first_run` — asserts exactly one `send_daily_email` invocation on default-mode path. `--once` and `--test` tests unchanged.

## Validation

| Check | Result |
|-------|--------|
| `pytest tests/test_scheduler.py::TestLoopHappyPathDispatch` | 4/4 green |
| `pytest tests/test_scheduler.py::TestLoopErrorHandling` | 3/3 green (regression-safe) |
| `pytest tests/test_main.py::TestCLI` | 11/11 green |
| `pytest -q` full suite | 1319 passing, 12 failing |
| Failures pre-existing? | Yes — 9 nginx drift + 2 ruff binary + 1 setup-https doc (all in Plan 16.1-01 `deferred-items.md`) |
| New failures from this fix? | 0 |

## Operator deploy steps

```bash
ssh trader@<droplet>
cd ~/trading-signals
git pull
.venv/bin/pip install -r requirements.txt   # no-op, no new deps
sudo systemctl restart trading-signals
journalctl -u trading-signals -n 20 --no-pager   # confirm scheduler entered
```

Next 08:00 AWST scheduled fire (or any `python main.py --force-email` test
run) will dispatch a real email. Look for `[Email] sent to <addr> subject=...`
in journalctl.

## Out of scope (untouched)

- Phase 16-05 UAT artifacts (operator UAT walk-through is a separate stream)
- Phase 16.1 plans/summaries
- ROADMAP.md
- notifier.py
