---
phase: 37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac
plan: 05
subsystem: api
tags: [fastapi, htmx, fanout, email, invite, admin, idempotency, tdd]

requires:
  - phase: 37-02
    provides: per_user_fanout.run + send_invite_email + send_cycle_summary_email + send_per_user_email
  - phase: 37-03
    provides: auth_store mint_invite_token / revoke_invite / list_pending_invites
  - phase: 37-04
    provides: /accept-invite wizard + consume_and_create_user

provides:
  - POST /admin/invites — mints invite token + emails invitee via per_user_fanout.send_invite_email + HTMX inline URL fragment
  - DELETE /admin/invites/{token_hash} — revokes pending invite
  - GET /admin/users — HX-Request-aware: fragment / JSON / full-page (review #8 precedence)
  - GET /healthz/last-cycle — admin-gated 7-key schema incl. crash field (review #5)
  - PATCH /settings/email-prefs — persists email_enabled + pause_until via mutate_user_state
  - per_user_fanout.run wired on all 3 orchestration paths (force/test, once, scheduler-loop)
  - per_user_fanout cycle-date idempotency guard (review #4)
  - per_user_fanout.record_cycle_crash helper — writes last_cycle.crash + sends CRASH-tagged admin email (review #5)
  - W3 end-to-end invariant proven cross-module (review #3)
  - PendingInviteSummary Pydantic model + last_seen_date population from trusted devices

affects: [gsd-verify-work-37, phase-38, any-plan-reading-last_cycle]

tech-stack:
  added: []
  patterns:
    - HX-Request > Accept:application/json > Accept:text/html explicit precedence (review #8)
    - Cycle-date idempotency guard at per_user_fanout.run entry (review #4)
    - Fan-out crash isolator: try/except → record_cycle_crash → rc unchanged (review #5)
    - send_invite_email imported from per_user_fanout NOT notifier (review #10)
    - Late-bind per_user_fanout via _main_pkg.per_user_fanout for monkeypatch compatibility
    - mutate_user_state for per-user state writes; never raw mutate_state for user data

key-files:
  created:
    - web/routes/admin/_renderers.py
    - tests/test_web_admin_invite.py
    - tests/test_web_dashboard_email_prefs.py
  modified:
    - web/routes/admin/__init__.py
    - web/routes/admin/_models.py
    - web/routes/healthz.py
    - web/routes/dashboard/__init__.py
    - per_user_fanout.py
    - main.py
    - scheduler_driver.py
    - tests/test_main.py

key-decisions:
  - "send_invite_email imported from per_user_fanout (not notifier) — co-location discipline per review #10"
  - "Explicit HX-Request > Accept:json > Accept:html precedence order per review #8 — three tests pin each branch"
  - "Cycle-date idempotency guard in per_user_fanout.run prevents duplicate sends on retry — early-return if state.last_cycle.date == run_date (review #4)"
  - "record_cycle_crash writes 7-key last_cycle schema + sends CRASH-tagged admin email — admin always gets cycle visibility even on total fan-out crash (review #5)"
  - "Fan-out wired in scheduler_driver.py (not daily_run_helpers.py) — _run_daily_check_caught lives there; plan referenced daily_run_helpers but implementation correctly targets scheduler_driver"
  - "--test flag gate added: per_user_fanout.run skipped when args.test — preserves CLI-01 structural read-only contract"
  - "Monkeypatching mutate_user_state in email-prefs tests avoids StateV12 validation + flock dependency in test isolation"

patterns-established:
  - "Fan-out on all orchestration paths: force/test (main.py), once (main.py), scheduler-loop (scheduler_driver.py)"
  - "record_cycle_crash: independent try/except around mutate_state and send_cycle_summary_email — secondary failure cannot mask primary"
  - "_counting_mutate(fn, **kw) kwargs passthrough pattern — avoids path=None explosion when caller passes no path"

requirements-completed: [UMAIL-01, UMAIL-02, UMAIL-04, RBAC-03]

duration: ~90min (across two sessions; second session continued after context compaction)
completed: 2026-05-14
---

# Phase 37 Plan 05: Admin Invite Routes + Email Prefs + Fan-out Wiring Summary

**HX-Request-aware admin invite routes, /healthz/last-cycle 7-key endpoint, PATCH /settings/email-prefs, and per_user_fanout.run wired on all three orchestration paths with idempotency guard, crash handler, and W3 cross-module invariant test**

## Performance

- **Duration:** ~90 min (two sessions, context compaction between Task 2 GREEN and SUMMARY creation)
- **Started:** 2026-05-14
- **Completed:** 2026-05-14
- **Tasks:** 3 (all TDD — RED commit then GREEN commit per task)
- **Files modified:** 12

## Accomplishments

- Admin can issue and revoke invites via POST/DELETE /admin/invites; invite email dispatched via per_user_fanout.send_invite_email (review #10 — not notifier)
- GET /admin/users now serves HTML fragment (HX-Request), JSON list (Accept: application/json), or full HTML page — explicit precedence per review #8; three tests pin each branch
- GET /healthz/last-cycle returns 7-key schema (date, total, ok, failed, users, errors, crash) including crash field for total fan-out failures; admin-gated via require_admin Depends
- PATCH /settings/email-prefs persists email_enabled (bool) + pause_until (ISO date or None) via mutate_user_state; invalid pause_until silently coerces to None
- per_user_fanout.run wired on all three orchestration paths (force-email, once, scheduler-loop in scheduler_driver.py); each path wrapped in try/except → record_cycle_crash on failure
- Cycle-date idempotency guard prevents duplicate sends on path retry (review #4)
- record_cycle_crash writes 7-key last_cycle.crash + sends CRASH-tagged admin summary email (review #5); admin always gets cycle visibility
- W3 end-to-end invariant proven: TestW3InvariantEndToEnd confirms per_user_fanout.run called exactly once per cycle and mutate_state called exactly twice total (W3 #1 in daily_run, W3 #2 in per_user_fanout)
- Full suite: 2324 passed, 2 skipped, 13 deselected, 1 xfailed, 3 xpassed

## Task Commits

Each task was committed atomically (TDD: RED then GREEN):

1. **Task 1 RED: Admin invite/healthz/HX-Request tests** — `dfb1bef` (test)
2. **Task 1 GREEN: Admin invite routes, healthz last-cycle, HX-Request negotiation** — `36fef95` (feat)
3. **Task 2 RED: PATCH /settings/email-prefs test stubs** — `3db8b9d` (test)
4. **Task 2 GREEN: PATCH /settings/email-prefs persists email_enabled + pause_until** — `28245f9` (feat)
5. **Task 3 RED: W3 e2e, idempotency, crash handling tests** — `62fa24d` (test)
6. **Task 3 GREEN: Wire per_user_fanout.run; idempotency guard; crash handler; W3 e2e tests** — `6796eb2` (feat)

## Files Created/Modified

- `web/routes/admin/_renderers.py` — NEW: `_render_admin_users_page`, `_render_admin_users_html_fragment`, `_render_invite_url_fragment` with `html.escape(quote=True)` on all interpolations
- `web/routes/admin/_models.py` — Added `PendingInviteSummary` Pydantic model; `_compute_last_seen_date` helper; `PublicUserSummary.last_seen_date` populated from max trusted device last_seen
- `web/routes/admin/__init__.py` — Modified `admin_list_users` with HX-Request > json > html precedence (review #8); added `admin_issue_invite` POST + `admin_revoke_invite` DELETE; `send_invite_email` imported from `per_user_fanout` (review #10)
- `web/routes/healthz.py` — Added `GET /healthz/last-cycle` with explicit `Depends(require_admin)`; 7-key schema with defensive `.get()` for legacy data; never crashes (D-19)
- `web/routes/dashboard/__init__.py` — Added `PATCH /settings/email-prefs` handler wired inside `register()` closure; uses `mutate_user_state`
- `per_user_fanout.py` — Added cycle-date idempotency guard at `run()` entry (review #4); added `record_cycle_crash()` public function (review #5)
- `main.py` — Added `import per_user_fanout` module-level re-export; fan-out call + crash wrapper on force/test path and once path; `--test` gate (CLI-01 read-only contract)
- `scheduler_driver.py` — Fan-out call + crash wrapper in `_run_daily_check_caught` after dispatch; late-bind via `_main_pkg.per_user_fanout` for monkeypatch compatibility
- `tests/test_web_admin_invite.py` — NEW (replaced Wave 0 stubs): 16 tests across TestAdminInviteIssue, TestAdminInviteRevoke, TestLastCycle, TestAdminUsersNegotiation, TestLastSeenDate
- `tests/test_web_dashboard_email_prefs.py` — NEW (replaced Wave 0 stubs): 5 tests in TestPatchEmailPrefs using monkeypatched mutate_user_state
- `tests/test_main.py` — Added TestFetchCountInvariant, TestW3InvariantEndToEnd (3 tests), TestCycleDateIdempotency (2 tests), TestCycleCrashHandling (2 tests); all use freeze_time

## Decisions Made

- **Fan-out in scheduler_driver.py, not daily_run_helpers.py**: plan referenced `daily_run_helpers.py` as the scheduler-loop wrapper, but the actual implementation of `_run_daily_check_caught` lives in `scheduler_driver.py`. The fan-out was placed there correctly.
- **`--test` flag gate**: fan-out skipped when `args.test` to preserve CLI-01 structural read-only contract. Test `test_test_flag_leaves_state_json_mtime_unchanged` confirmed correct behavior.
- **mutate_user_state monkeypatching in email-prefs tests**: StateV12 validation requires `admin_user_id`, `last_run`, `signals`, `markets`, `strategy_settings`, `warnings`, `users` — seeding all these in tests is fragile. Monkeypatching `mutate_user_state` directly with an in-memory capturing stub avoids schema coupling entirely.
- **_counting_mutate(fn, **kw) kwargs passthrough**: first attempt used `def _counting_mutate(fn, path=None)` which passed `path=None` explicitly to `orig_mutate`, causing `None.exists()`. Changed to `**kw` passthrough.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_tenant_isolation.py JSONDecodeError on GET /admin/users**
- **Found during:** Task 1 GREEN (admin content negotiation)
- **Issue:** Existing test `test_admin_users_response_has_no_trade_content` called GET /admin/users without `Accept: application/json` header. New content negotiation returns HTML for that case; `resp.json()` then fails with JSONDecodeError.
- **Fix:** Added `headers={'Accept': 'application/json'}` to that GET call in `tests/test_tenant_isolation.py`
- **Files modified:** tests/test_tenant_isolation.py
- **Verification:** Full suite green after fix
- **Committed in:** `36fef95`

**2. [Rule 1 - Bug] Task 2 email-prefs route returning 500 — StateV12 missing required fields**
- **Found during:** Task 2 GREEN (PATCH /settings/email-prefs)
- **Issue:** Test state dict missing `admin_user_id` and `last_run` fields required by StateV12.model_validate inside load_state; route crashed with 500
- **Fix:** Completely rewrote tests using `monkeypatch.setattr(state_manager, 'mutate_user_state', _fake_mutate_user_state)` — an in-memory capturing stub, avoiding real state loading entirely
- **Files modified:** tests/test_web_dashboard_email_prefs.py
- **Verification:** 5 tests GREEN
- **Committed in:** `28245f9`

**3. [Rule 1 - Bug] Task 2 still 500 — KeyError: 'SPI200' in load_state**
- **Found during:** Task 2 GREEN (after first fix)
- **Issue:** load_state() tried to resolve `_resolved_contracts` from `state['users']['u_admin_marc']['contracts']['SPI200']` where `_ADMIN_UID = 'u_admin_marc'` is hardcoded; test state used a different uid
- **Fix:** Encompassed by above rewrite — monkeypatching mutate_user_state bypasses load_state entirely
- **Files modified:** tests/test_web_dashboard_email_prefs.py
- **Verification:** 5 tests GREEN
- **Committed in:** `28245f9`

**4. [Rule 1 - Bug] Task 3 test_test_flag_leaves_state_json_mtime_unchanged regression**
- **Found during:** Task 3 GREEN (fan-out wiring in main.py)
- **Issue:** First implementation of fan-out wiring ran `per_user_fanout.run()` even on `--test` path, mutating state.json — violating CLI-01 structural read-only contract
- **Fix:** Added `not args.test` gate: `if rc == 0 and run_date is not None and not args.test:`
- **Files modified:** main.py
- **Verification:** Existing test passed
- **Committed in:** `6796eb2`

**5. [Rule 1 - Bug] Task 3 _counting_mutate(fn, path=None) causing NoneType.exists()**
- **Found during:** Task 3 GREEN (W3 invariant tests)
- **Issue:** Counting stub passed `path=None` explicitly to `orig_mutate`; `load_state(path=None)` then called `None.exists()`, crashing with AttributeError
- **Fix:** Changed stub signature to `def _counting_mutate(fn, **kw)` to pass kwargs through unchanged
- **Files modified:** tests/test_main.py
- **Verification:** W3 invariant tests GREEN
- **Committed in:** `6796eb2`

---

**Total deviations:** 5 auto-fixed (5 bugs — all in tests or gate logic, no functional regressions)
**Impact on plan:** All fixes required for correctness. One content-negotiation regression (deviation #1) was a direct consequence of the new admin route behavior; the rest were test isolation issues. No scope creep.

## Issues Encountered

- StateV12 validation complexity in tests: the real state schema has 7+ required fields and resolves contract config on load; direct state injection into tests is fragile. Pattern established: monkeypatch `mutate_user_state` / `load_user_state` at the boundary for per-user state tests.
- Context window compaction between Task 2 GREEN commit and SUMMARY creation; resumed cleanly from git log + session summary.

## Known Stubs

None — all tests use real (monkeypatched) implementations, not placeholder assertions. `_render_per_user_email_html` returns a minimal but functional HTML body (per plan spec: "full template wired in a future plan") — this is intentional and documented in the module docstring, not a hidden stub.

## Threat Flags

None — all threat mitigations from the plan's STRIDE register were implemented:
- T-37-05-01/02/06: require_admin Depends on all admin routes + /healthz/last-cycle; uid from current_user_id only
- T-37-05-04: no raw token in logs (`grep` gate passes)
- T-37-05-07: try/except around date.fromisoformat; coerces to None
- T-37-05-10/11/12: try/except wrapper on every fan-out call site; idempotency guard; record_cycle_crash
- T-37-05-13: three tests pin HX-Request > json > html precedence

## Self-Check

**Commits exist:**
- `dfb1bef` test(37-05): RED — admin invite issue/revoke, healthz last-cycle, HX-Request negotiation
- `36fef95` feat(37-05): admin invite routes, healthz last-cycle, HX-Request negotiation
- `3db8b9d` test(37-05): RED — PATCH /settings/email-prefs test stubs (Task 2)
- `28245f9` feat(37-05): PATCH /settings/email-prefs persists email_enabled + pause_until
- `62fa24d` test(37-05): RED — W3 e2e, idempotency, crash handling tests (Task 3)
- `6796eb2` feat(37-05): wire per_user_fanout.run; idempotency guard; crash handler; W3 e2e tests

## Self-Check: PASSED

All 6 task commits verified in git log. All 3 tasks GREEN. Full suite green (2324 passed).

## Next Phase Readiness

- Phase 37 end-to-end wiring complete: UMAIL-01 (fan-out), UMAIL-02 (crash/admin visibility), UMAIL-04 (email prefs), RBAC-03 (admin invite) all satisfied
- Ready for `/gsd-verify-work 37`
- Dashboard Settings section renders email-prefs form; admin nav has Users link (conditional on admin role)
- Any future plan reading `state['last_cycle']` should expect the 7-key schema with optional `crash` field

---
*Phase: 37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac*
*Completed: 2026-05-14*
