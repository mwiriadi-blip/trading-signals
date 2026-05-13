---
phase: 36-per-route-user-id-scoping-privacy-boundary-per-user-flock
plan: "01"
subsystem: state_manager, web/routes/admin, tests
tags: [per-user-flock, state-manager, pydantic, conftest, test-stubs, tenant-isolation]
dependency_graph:
  requires: []
  provides:
    - mutate_user_state (state_manager public API)
    - load_user_state (state_manager public API)
    - record_trade uid parameter (backward-compatible)
    - PublicUserSummary Pydantic model (web/routes/admin/_models.py)
    - v12-shaped conftest fixtures (client_with_state_v3, client_with_state_v6)
    - TestMutateUserState (3 passing unit tests)
    - TestAdminUsers + TestAdminDisable (xfail stubs; Wave 1 greens)
    - TestTenantIsolation (xfail + skipped stubs)
    - TestEntityIdOwnership + TestTradeOwnership (skipped stubs; Wave 2)
  affects:
    - state_manager/__init__.py
    - state_manager/trades.py
    - tests/conftest.py
tech_stack:
  added: []
  patterns:
    - outer per-user fcntl.flock (state/users/{uid}.lock) wrapping inner mutate_state flock
    - FastAPI response_model=list[PublicUserSummary] for automatic field redaction
    - top-level positions compat shim in conftest for legacy dashboard reads
key_files:
  created:
    - web/routes/admin/_models.py
    - tests/test_state_manager_per_user.py
    - tests/test_web_admin_users.py
    - tests/test_web_paper_trades_ownership.py
    - tests/test_web_trades_ownership.py
    - tests/test_tenant_isolation.py
  modified:
    - state_manager/__init__.py
    - state_manager/trades.py
    - tests/conftest.py
    - .planning/phases/36-per-route-user-id-scoping-privacy-boundary-per-user-flock/36-VALIDATION.md
decisions:
  - mutate_user_state uses open(lock_path, 'a+') + fileno() flock pattern (not os.open) — lock file carries no content, 'a+' is idiomatic create-if-absent
  - record_trade fallback: users_map.get(uid) or _admin_user(state) preserves pre-v12 test state backward compat
  - client_with_state_v3 includes top-level positions compat shim alongside users[uid].positions — legacy dashboard routes still read state.get('positions') until Wave 1 migration
  - TestAdminUsers/TestAdminDisable in new file (not test_web_admin.py) — 594-line file would exceed 500-LOC CLAUDE.md cap
  - D-14 ownership tests in new files — test_web_paper_trades.py (936 lines) and test_web_trades.py (1270 lines) both exceed 500-LOC cap
  - wave_0_complete: true set in 36-VALIDATION.md; admin-users test refs updated to new file locations
metrics:
  duration_minutes: ~25
  completed: "2026-05-14"
  tasks_completed: 3
  tasks_total: 3
  files_created: 6
  files_modified: 4
---

# Phase 36 Plan 01: Wave 0 Foundation Summary

Wave 0 foundation: per-user flock wrapper, record_trade uid param, PublicUserSummary model, v12 conftest fixtures, and all test stubs that Wave 1 and Wave 2 implementations will make green.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add mutate_user_state + load_user_state; fix record_trade uid gap | 15f86e8 | state_manager/__init__.py, state_manager/trades.py |
| 2 | Create PublicUserSummary model; update conftest to v12 shape | 60dc792 | web/routes/admin/_models.py, tests/conftest.py |
| 3 | Scaffold test stubs — TestMutateUserState, admin users, ownership, isolation | 88665ce | 5 new test files, tests/conftest.py, 36-VALIDATION.md |

## Verification Results

```
tests/test_state_manager_per_user.py  — 3 passed
tests/test_web_admin_users.py         — 4 xfailed, 1 xpassed (strict=False)
tests/test_tenant_isolation.py        — 1 xfailed, 2 skipped (Phase 37)
tests/test_web_paper_trades_ownership.py — 4 skipped (Wave 2)
tests/test_web_trades_ownership.py    — 5 skipped (Wave 2)
tests/test_web_paper_trades.py        — 73 passed (pre-Wave 1 fixtures green)
tests/test_web_trades.py              — 53 passed (pre-Wave 1 fixtures green)
tests/test_state_manager.py           — 130 passed (no regressions)
tests/test_web_dashboard.py           — 51 passed (compat shim applied)
Full suite                            — 1901 passed, 2 skipped, 13 deselected, 4 xfailed, 1 xpassed
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] conftest v12 update broke dashboard forward-stop fragment test**

- **Found during:** Task 3 full suite run
- **Issue:** `client_with_state_v3` default state moved `positions` under `state['users'][uid]`. The dashboard `_forward_stop_fragment_response` route still reads `state.get('positions', {})` at top-level — returned `{}` → em-dash response → `test_long_z_above_peak_updates_w` failed.
- **Root cause:** Pre-v12 dashboard route reads top-level `positions`; v12 fixture no longer has that key. Wave 1 plan 02 migrates these reads to `load_user_state`.
- **Fix:** Added `'positions': _open_spi_position` at top level of `client_with_state_v3` default state as a compat shim alongside `users[uid].positions`. The shim is explicitly commented for removal when Wave 1 migrates the dashboard route.
- **Files modified:** tests/conftest.py
- **Commit:** 88665ce

**2. [Rule 1 - Bug] test_mutate_user_state_writes_to_user_bucket seed state missing valid contracts**

- **Found during:** Task 3 first full suite run
- **Issue:** `_seed_state` used `contracts: {}`. `load_state` materialises `_resolved_contracts` by looking up `_user_contracts['SPI200']` in `SPI_CONTRACTS` — `KeyError: 'SPI200'` because contracts was empty.
- **Fix:** Added `'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'}` to `_seed_state` in test_state_manager_per_user.py.
- **Files modified:** tests/test_state_manager_per_user.py
- **Commit:** 88665ce

## Known Stubs

The following stubs are intentional and tracked:

| Stub | File | Reason |
|------|------|--------|
| `test_admin_users_response_has_no_trade_content` xfail | tests/test_tenant_isolation.py | Wave 1: GET /admin/users route not yet implemented |
| `TestAdminUsers`, `TestAdminDisable` xfail | tests/test_web_admin_users.py | Wave 1: admin user routes not yet implemented |
| `TestEntityIdOwnership` 4 methods skipped | tests/test_web_paper_trades_ownership.py | Wave 2: ownership checks not yet implemented |
| `TestTradeOwnership` 5 methods skipped | tests/test_web_trades_ownership.py | Wave 2: ownership checks not yet implemented |
| `test_crash_email_body_has_no_trade_content` skipped | tests/test_tenant_isolation.py | Phase 37: fan-out not yet implemented |
| `test_other_user_dashboard_has_no_user_a_trade_content` skipped | tests/test_tenant_isolation.py | Phase 37: user B dashboard scoping not yet implemented |

## Threat Flags

No new security-relevant surface introduced beyond what the plan's threat model covers. `PublicUserSummary` is output-only with FastAPI response_model enforcement (T-36-02). `mutate_user_state` lock file path is CWD-relative — no path traversal concern since uid is sourced from validated session cookie.

## Self-Check: PASSED

Files exist:
- FOUND: state_manager/__init__.py (mutate_user_state defined)
- FOUND: state_manager/trades.py (uid param present)
- FOUND: web/routes/admin/_models.py
- FOUND: tests/test_state_manager_per_user.py
- FOUND: tests/test_web_admin_users.py
- FOUND: tests/test_web_paper_trades_ownership.py
- FOUND: tests/test_web_trades_ownership.py
- FOUND: tests/test_tenant_isolation.py

Commits exist:
- FOUND: 15f86e8
- FOUND: 60dc792
- FOUND: 88665ce
