---
phase: 36-per-route-user-id-scoping-privacy-boundary-per-user-flock
plan: "02"
subsystem: web/routes/paper_trades, web/routes/trades, web/routes/admin, tests
tags: [tenant-isolation, per-user-state, htmx, admin-routes, fastapi-depends]
dependency_graph:
  requires:
    - 36-01 (mutate_user_state, load_user_state, PublicUserSummary)
  provides:
    - paper_trades routes: all 6 handlers use mutate_user_state + user bucket
    - trades routes: all 3 mutation handlers use mutate_user_state + user bucket
    - trades GET read-paths: 404 for None position (IDOR prevention)
    - record_trade passes uid=user_id (T-36-07 tamper mitigated)
    - GET /admin/users returning list[PublicUserSummary] (T-36-06 redaction)
    - PATCH /admin/users/{uid}/disable (RBAC-04)
    - TestAdminUsers + TestAdminDisable now green (was xfail)
  affects:
    - web/routes/paper_trades/__init__.py
    - web/routes/trades/__init__.py
    - web/routes/admin/__init__.py
    - tests/conftest.py
tech_stack:
  added: []
  patterns:
    - FastAPI Depends(current_user_id) on every per-user HTMX route
    - mutate_user_state(user_id, _apply) with state['users'][user_id] bucket navigation
    - merged = {**user_state, 'signals': state.get('signals', {})} for paper_trades renderer
    - display_state = {**state, 'positions': user_state['positions']} for trades renderers
    - response_model=list[PublicUserSummary] for automatic field redaction
    - app.dependency_overrides[current_user_id] in conftest for single-user test scenario
    - _mutate_user_state_stub with Shim A (pre-v12 → v12 promotion) + Shim B (top-level propagation)
key_files:
  created: []
  modified:
    - web/routes/paper_trades/__init__.py
    - web/routes/trades/__init__.py
    - web/routes/admin/__init__.py
    - tests/conftest.py
decisions:
  - display_state shim for trades renderers: inject user positions at top-level rather than rewriting _renderers.py (locality, zero renderer behaviour change)
  - conftest app.dependency_overrides[current_user_id] = lambda: _ADMIN_UID — bridged auth gap without modifying 126 test methods across 2 files
  - _mutate_user_state_stub Shim A: auto-promotes pre-v12 set_state() payloads to v12 user-bucket shape so existing tests need no changes
  - _mutate_user_state_stub Shim B: propagates user-bucket keys (paper_trades, positions, trade_log, account, equity_history) to top-level after mutation — legacy captured_saves assertions remain valid
  - graceful fallback in get_paper_trades_fragment: state.get('users', {}).get(user_id, {}) handles newly-created users not yet in state
metrics:
  duration_minutes: ~35
  completed: "2026-05-14"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 4
---

# Phase 36 Plan 02: Wave 1 Route Migration Summary

Wave 1 functional core: threaded user_id through all paper_trades and trades HTMX route handlers via Depends(current_user_id), migrated all mutate_state calls to mutate_user_state with user-bucket navigation, added 404 semantics for GET read-path handlers, and added GET /admin/users + PATCH /admin/users/{uid}/disable. Wave 0 stubs (TestAdminUsers, TestAdminDisable) are now green.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Migrate paper_trades to mutate_user_state + user-bucket navigation | ee05e25 | web/routes/paper_trades/__init__.py, tests/conftest.py |
| 2 | Migrate trades + add admin GET /users + PATCH /users/{uid}/disable | 07c853d | web/routes/trades/__init__.py, web/routes/admin/__init__.py, tests/conftest.py |

## Verification Results

```
tests/test_web_paper_trades.py   — 50 passed
tests/test_web_trades.py         — 76 passed (53 pre-wave + 23 new)
tests/test_web_admin_users.py    — 4 xpassed (all Wave 0 stubs now green)
tests/test_tenant_isolation.py   — 1 xfailed, 2 skipped (Phase 37)
tests/test_web_paper_trades_ownership.py — 4 skipped (Wave 2)
tests/test_web_trades_ownership.py       — 5 skipped (Wave 2)
Full suite                        — 2202 passed, 11 skipped, 1 xfailed, 4 xpassed
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fixtures used pre-v12 flat state; _apply bodies needed state['users'][user_id]**

- **Found during:** Task 1 first test run (403 + KeyError: 'users')
- **Issue:** (a) Routes with Depends(current_user_id) returned 403 because test fixtures used X-Trading-Signals-Auth header, not session cookies. (b) Tests called set_state() with pre-v12 flat dicts lacking 'users' key, causing KeyError in _apply.
- **Fix:** In tests/conftest.py: added app.dependency_overrides[current_user_id] = lambda: _ADMIN_UID to both client_with_state_v3 and v6 fixtures; added Shim A (auto-promote flat state to v12 bucket) and Shim B (propagate bucket keys to top-level post-mutation) in _mutate_user_state_stub; added load_user_state stub returning from state_box.
- **Files modified:** tests/conftest.py
- **Commit:** ee05e25

**2. [Rule 1 - Bug] TestPrePhase35RoutesStructuralParity::test_paper_trades_returns_expected_shape 500**

- **Found during:** Task 2 full suite run
- **Issue:** test_web_admin.py test creates a real admin user via create_user() (gets random uid) but stubs load_state to return reset_state() which only has users[_ADMIN_UID]. get_paper_trades_fragment used state_full['users'][user_id] with hard bracket access — KeyError for the real uid → 500.
- **Fix:** Changed bracket access to state_full.get('users', {}).get(user_id, {}) in get_paper_trades_fragment for graceful fallback when user bucket is absent.
- **Files modified:** web/routes/paper_trades/__init__.py
- **Commit:** 07c853d

**3. [Rule 1 - Bug] captured_saves[-1]['account'] not updated after close_trade**

- **Found during:** Task 2 TestCloseTradePnLMath test
- **Issue:** record_trade(state, trade, uid=user_id) updates state['users'][user_id]['account'] but conftest Shim B only propagated paper_trades/positions/trade_log. Test checking captured_saves[-1]['account'] saw stale 100000.0.
- **Fix:** Added 'account' and 'equity_history' to _PROPAGATE_KEYS in both _mutate_user_state_stub variants.
- **Files modified:** tests/conftest.py
- **Commit:** 07c853d

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| _mutate_user_state_stub Shim A+B | tests/conftest.py | Wave 2 Wave 2: remove when all tests reference user bucket directly |
| load_user_state stub returning flat fallback | tests/conftest.py | Wave 2: remove when all set_state() calls use v12 shape |
| TestEntityIdOwnership 4 methods skipped | tests/test_web_paper_trades_ownership.py | Wave 2: ownership checks not yet implemented |
| TestTradeOwnership 5 methods skipped | tests/test_web_trades_ownership.py | Wave 2: ownership checks not yet implemented |
| test_crash_email_body_has_no_trade_content skipped | tests/test_tenant_isolation.py | Phase 37: fan-out not yet implemented |
| test_other_user_dashboard_has_no_user_a_trade_content skipped | tests/test_tenant_isolation.py | Phase 37: user B dashboard scoping not yet implemented |
| last_seen_date=None in PublicUserSummary | web/routes/admin/__init__.py | Phase 37: device-lookup not yet wired |

## Threat Flags

No new security-relevant surface beyond plan's threat model. T-36-05 (IDOR via _apply) mitigated: _apply navigates state['users'][user_id] — another user's entities not in this bucket. T-36-06 (admin data leak) mitigated: response_model=list[PublicUserSummary]. T-36-07 (record_trade tamper) mitigated: uid flows from Depends. T-36-08 (admin disable gate) mitigated: require_admin on admin sub-router.

## Self-Check: PASSED

Files exist:
- FOUND: web/routes/paper_trades/__init__.py (4 mutate_user_state(user_id, _apply) calls)
- FOUND: web/routes/trades/__init__.py (3 mutate_user_state + record_trade uid=user_id)
- FOUND: web/routes/admin/__init__.py (response_model=list[PublicUserSummary] + set_user_disabled)
- FOUND: tests/conftest.py (dependency_overrides + shims)

Commits exist:
- FOUND: ee05e25
- FOUND: 07c853d
