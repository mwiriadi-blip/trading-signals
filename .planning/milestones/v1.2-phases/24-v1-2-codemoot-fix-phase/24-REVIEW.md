---
phase: 24-codemoot-fix
reviewed: 2026-05-01T10:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - auth_store.py
  - main.py
  - alert_engine.py
  - web/routes/totp.py
  - web/routes/reset.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 24: Code Review Report

**Reviewed:** 2026-05-01T10:00:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 24 fixes landed correctly for BUG-01 (`_ensure_aware` helper), BUG-02 (assert to raise), CLEAN-04 (dedup `_is_safe_next`), and CLEAN-06 (dedup `_get_client_ip`). `alert_engine.py` is clean -- pure math with proper NaN guards.

One critical bug was introduced in the BUG-03 fix (`--once` post-push warning persistence): the new code path crashes on weekends when `run_daily_check` returns `None` for state. Three warnings on code quality and convention issues.

## Critical Issues

### CR-01: --once weekend crash -- AttributeError on NoneType.get()

**File:** `main.py:1877`
**Issue:** The BUG-03 fix added `once_state.get('warnings')` at line 1877, but `run_daily_check` returns `(0, None, None, run_date)` on weekends (line 1220). When `--once` runs on a weekend, `once_state` is `None` and `.get('warnings')` raises `AttributeError: 'NoneType' object has no attribute 'get'`. This crashes the `--once` path every Saturday/Sunday, which is the GHA cron path.

The `--force-email` and `--test` branches (line 1858-1863) handle the `None` case with an explicit `state is not None` guard. The `--once` branch does not.

**Fix:**
```python
# main.py line 1875-1879
if args.once:
    rc, once_state, _old_signals, _run_date = run_daily_check(args)
    if not args.test and once_state is not None and once_state.get('warnings'):
        state_manager.save_state(once_state)
    return rc
```

## Warnings

### WR-01: --once saves state via save_state, bypassing mutate_state lock

**File:** `main.py:1878`
**Issue:** The BUG-03 fix uses `state_manager.save_state(once_state)` directly, but the rest of the codebase migrated to `state_manager.mutate_state()` (Phase 14 REVIEWS HIGH #1) to hold `fcntl.LOCK_EX` across read-modify-write. This save_state call is a lock-free write that can race with a concurrent web POST handler's mutate_state call, causing a lost-update. The daily-run path (step 9, line 1534) and the `_dispatch_email_and_maintain_warnings` path (line 582) both use `mutate_state`. The `--once` path should too.

**Fix:**
```python
if not args.test and once_state is not None and once_state.get('warnings'):
    _final_once = once_state
    def _apply_once_warnings(fresh_state: dict) -> None:
        fresh_state['warnings'] = _final_once['warnings']
    state_manager.mutate_state(_apply_once_warnings)
```

### WR-02: Dead guard -- `not args.test` is always True in --once branch

**File:** `main.py:1877`
**Issue:** The `not args.test` check on line 1877 is always `True` in the `--once` branch. The dispatch ladder reaches `--once` only after the `args.force_email or args.test` branch (line 1850) has already returned. If both `--once` and `--test` are passed, `--test` is handled first. The guard is misleading dead code that suggests `--test --once` reaches this branch.

**Fix:** Remove the `not args.test` check for clarity, or add a comment documenting why it's structurally unreachable but kept as defense-in-depth.

### WR-03: Importing underscore-prefixed functions across module boundaries

**File:** `web/routes/totp.py:43`, `web/routes/reset.py:46`
**Issue:** `_is_safe_next` and `_get_client_ip` are prefixed with underscore (Python private-by-convention), but are now imported cross-module. This violates the naming contract -- underscore prefix signals "internal to this module, not part of the public API." Consumers may not expect these to be stable. The CLEAN-04/CLEAN-06 dedup is correct in intent (single source of truth), but the names should reflect their new cross-module role.

**Fix:** Rename to `is_safe_next` in `login.py` and `get_client_ip` in `auth.py` (drop the leading underscore) since they are now part of the module's public interface. Update all import sites.

## Info

### IN-01: error parameter in HTML templates not escaped

**File:** `web/routes/totp.py:246`
**Issue:** The `error` parameter in `_render_enroll_page` and `_render_verify_page` is inserted into HTML without `html_escape()`. Currently all callers pass hardcoded strings ("Code didn't match -- try again"), so no XSS risk exists today. But the pattern is fragile -- a future caller passing user-controlled data would create a stored XSS.

**Fix:** Apply `html_escape(error)` in both render functions for defense-in-depth (login.py already imports and uses `html_escape` for the same pattern).

### IN-02: Redundant `_push_state_to_git` warning persistence gap

**File:** `main.py:1567`
**Issue:** `_push_state_to_git` appends warnings to the in-memory `state` dict (via `state_manager.append_warning`) when git operations fail, but these warnings are never persisted. The function runs after `mutate_state` (step 9, line 1534) and before the run summary footer. The BUG-03 fix at line 1877-1878 attempts to close this gap for `--once`, but the default scheduler path (`_run_daily_check_caught` at line 1881) also has the gap -- post-push warnings from the scheduler-loop daemon are lost until the next run's `mutate_state` captures them. This is a known design limitation but worth documenting.

---

_Reviewed: 2026-05-01T10:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
