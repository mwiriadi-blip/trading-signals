---
phase: 37
plan: "02"
subsystem: fan-out-orchestrator
tags: [wave-1, per-user-fanout, email-dispatch, rfc8058, semaphore, w3-invariant, umail]
dependency_graph:
  requires:
    - 37-01 (Wave 0 test scaffolding)
  provides:
    - per_user_fanout.py (top-level orchestrator + dispatch helpers)
    - system_params.FANOUT_SEMAPHORE_LIMIT
    - notifier.transport._post_to_resend email_headers kwarg
  affects:
    - main.py (Plan 05 will wire per_user_fanout.run here)
tech_stack:
  added:
    - asyncio.Semaphore throttle pattern for outbound Resend calls
    - RFC 8058 List-Unsubscribe / List-Unsubscribe-Post header injection
  patterns:
    - Never-raise dispatch helpers co-located with orchestrator (review #10)
    - Per-user crash boundary via asyncio.gather with self-catching tasks
    - W3 invariant: exactly one terminal mutate_state call per fan-out run
    - Overwrite-only single-dict last_cycle schema (review #5/#7)
key_files:
  created:
    - per_user_fanout.py (385 lines — orchestrator + 3 dispatch helpers)
    - tests/test_per_user_fanout.py (Wave 0 stubs replaced — 24 real tests)
  modified:
    - system_params.py (FANOUT_SEMAPHORE_LIMIT = 2 added)
    - notifier/transport.py (_post_to_resend gains email_headers kwarg)
    - tests/test_notifier.py (TestFanoutSemaphoreLimit + TestPostToResendEmailHeaders added)
decisions:
  - "send_per_user_email / send_invite_email / send_cycle_summary_email co-located in per_user_fanout.py per review #10 — keeps notifier/dispatch.py under 500-line limit"
  - "Semaphore slot held across entire asyncio.to_thread call (including retry backoff) to prevent Resend 429 burst"
  - "Skipped users (email_enabled=False or pause_until>=today) count as ok=True in last_cycle schema so they don't inflate failed count"
metrics:
  duration: "~12 minutes"
  completed: "2026-05-14"
  tasks: 2
  files_modified: 5
---

# Phase 37 Plan 02: Fan-Out Orchestrator + Dispatch Helpers Summary

**One-liner:** per_user_fanout.py — async fan-out with Semaphore(2) throttle, RFC 8058 headers, per-user crash boundary, W3-invariant single terminal mutate_state, and three co-located dispatch helpers.

---

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Add FANOUT_SEMAPHORE_LIMIT + _post_to_resend email_headers kwarg | `2e8234a` | system_params.py, notifier/transport.py, tests/test_notifier.py |
| 2 | Create per_user_fanout.py + all test stubs turned GREEN | `49a6a09` | per_user_fanout.py, tests/test_per_user_fanout.py |

---

## New Module: per_user_fanout.py

**Line count:** 385

**Public surface:**

| Name | Type | Description |
|------|------|-------------|
| `run(state, run_date)` | sync function | Entry point; asyncio.run + single terminal mutate_state |
| `send_per_user_email(uid, user_state, shared_signals, run_date)` | dispatch | RFC 8058 headers; per-user log; never-raise |
| `send_invite_email(to_email, invite_url)` | dispatch | Invite acceptance email; never logs raw token |
| `send_cycle_summary_email(outcomes, run_date, crash=None)` | dispatch | Admin end-of-cycle summary; crash kwarg (review #5) |
| `_fan_out_all(users, shared_signals, run_date)` | async coroutine | asyncio.gather over all F&F users |
| `_send_one(sem, uid, user_row, shared_signals, run_date)` | async coroutine | Per-user crash boundary + semaphore throttle |

**Co-location rationale (review #10):** all three dispatch helpers live in `per_user_fanout.py` (not `notifier/dispatch.py`) so the orchestrator is self-contained AND `notifier/dispatch.py` stays at 465 lines (under the 500-line CLAUDE.md limit).

---

## Key Implementation Details

### _post_to_resend email_headers kwarg

`notifier/transport._post_to_resend` gained a keyword-only parameter:

```python
email_headers: dict[str, str] | None = None
```

When provided and non-empty, `payload['headers'] = dict(email_headers)` is injected before the Resend POST. All existing callers unaffected (default None).

### FANOUT_SEMAPHORE_LIMIT = 2

Added to `system_params.py` near `HTTP_TIMEOUT_S`. Value 2 matches Resend free-tier rate limit (2 req/sec). Operator can bump to 5 for newer Resend accounts.

### W3 Invariant — Proven by Test

`TestW3Invariant.test_exactly_one_mutate_state_call` counts `mutate_state` calls via a counting monkeypatch. Result: exactly 1 call on every `per_user_fanout.run()` invocation with 3 active users. The W3 invariant (daily_run = #1, per_user_fanout terminal = #2) is maintained.

### last_cycle Schema — Explicit Overwrite-Only

```python
s['last_cycle'] = {
  'date': run_date,
  'total': len(outcomes),
  'ok': ok_count,
  'failed': failed_count,
  'users': outcomes,
  'errors': errors,
  'crash': None,  # populated by main.py wrapper on total fan-out crash
}
```

Schema is a single dict (NOT a list — review #7). All 7 keys present. `crash` field supported by `send_cycle_summary_email(crash=...)` (review #5).

### Per-User Logging — Review #13

Every `send_per_user_email` call emits exactly one `logger.info` line before returning:

```
[Fan-out] uid=%s ok=%s reason=%s
```

Verified by `TestPerUserLogging`: 2-user fan-out produces 2 log records.

### Per-User Crash Boundary — Review #5

`_send_one` wraps the `asyncio.to_thread(send_per_user_email, ...)` call in `try/except Exception  # noqa: BLE001`. One user's crash returns `{'uid': uid, 'ok': False, 'reason': 'RuntimeError: ...'}` and the gather continues. `TestCrashBoundary` verifies the healthy users complete normally.

### Semaphore Throttle — 50-User Test Wall-Clock

`TestSemaphoreThrottle.test_50_user_completes_under_30s` ran 50 users with 10ms simulated latency each. Completed well under 30s. `max_active <= 2` invariant verified via thread counter.

---

## Test Classes Summary

| Class | Tests | Status |
|-------|-------|--------|
| TestRFC8058Headers | 3 | GREEN |
| TestFanOutEmail | 2 | GREEN |
| TestCrashBoundary | 1 | GREEN |
| TestW3Invariant | 1 | GREEN |
| TestSemaphoreThrottle | 1 | GREEN |
| TestEmailPrefsSkip | 4 | GREEN |
| TestUnicodeDisplayName | 1 | GREEN |
| TestLastCycleSchema | 2 | GREEN |
| TestPerUserLogging | 3 | GREEN |
| TestDispatchHelpers | 5 | GREEN |
| **Total** | **24** | **ALL GREEN** |

---

## notifier/dispatch.py Line Count Delta

Pre-plan: 465 lines. Post-plan: 465 lines. **Delta: 0.** No new functions added to `notifier/dispatch.py` (review #10 strictly observed).

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test Design] TestPerUserLogging two-user test used mocked send_per_user_email**
- **Found during:** Task 2 GREEN phase
- **Issue:** Initial test mocked `send_per_user_email` entirely, so the `logger.info('[Fan-out] uid=...')` call inside the real function never executed. Test reported 0 log records.
- **Fix:** Changed test to mock `_post_to_resend` instead, letting the real `send_per_user_email` run (and emit its log line). Uses `monkeypatch.setattr('per_user_fanout._post_to_resend', _mock_post)`.
- **Files modified:** tests/test_per_user_fanout.py
- **Commit:** 49a6a09

None beyond the above.

---

## Main.py Wiring Deferred

`per_user_fanout.run(state, run_date)` is NOT yet wired into `main.py`. Per plan D-14 and the plan spec: "Plan 05 wires this into main.py (atomic with admin + dashboard surface)." The module is fully importable and callable from tests via `asyncio.run(per_user_fanout._fan_out_all(...))`.

---

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes were introduced in this plan. `per_user_fanout.py` is invoked synchronously from `main.py` (not from any HTTP route) per D-14 design.

Threat mitigations from the plan's threat register:

| Threat ID | Status |
|-----------|--------|
| T-37-02-01 | Mitigated — existing `redact_secret` in `_post_to_resend` covers all dispatch paths |
| T-37-02-02 | Mitigated — `send_invite_email` only logs `to_email`, never invite_url/token |
| T-37-02-03 | Mitigated — `send_per_user_email` accepts only (uid, user_state, shared_signals, run_date) |
| T-37-02-04 | Mitigated — per-user BLE001 catch in `_send_one`; TestCrashBoundary verifies |
| T-37-02-05 | Mitigated — Semaphore(2) acquired BEFORE `to_thread`; slot held across retry |
| T-37-02-06 | Mitigated — `mutate_state` called only in `run()` AFTER `asyncio.run()` returns |
| T-37-02-07 | Mitigated — recipient from `load_user_state(uid)['email']`; empty → missing_recipient |
| T-37-02-08 | Mitigated — `state['last_cycle']` records all outcomes; per-user log on every attempt |
| T-37-02-09 | Deferred — main.py crash wrapper (Plan 05) will set `last_cycle.crash` |
| T-37-02-10 | Mitigated — `_batch_write` overwrites with single dict; docstring enforces; test verifies |

---

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| per_user_fanout.py exists | FOUND |
| per_user_fanout.run callable | PASS |
| per_user_fanout._fan_out_all coroutine | PASS |
| per_user_fanout._send_one coroutine | PASS |
| system_params.FANOUT_SEMAPHORE_LIMIT == 2 | PASS |
| _post_to_resend has email_headers param | PASS |
| notifier/dispatch.py line count delta == 0 | PASS (465 pre = 465 post) |
| All 24 test_per_user_fanout.py tests GREEN | PASS |
| Full suite (2240 passed) | PASS |
| Commit 2e8234a exists | FOUND |
| Commit 49a6a09 exists | FOUND |
