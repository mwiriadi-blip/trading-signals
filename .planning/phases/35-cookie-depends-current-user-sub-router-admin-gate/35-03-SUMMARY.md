---
phase: 35
plan: 03
subsystem: web/auth
tags: [auth, fastapi-depends, dependency-injection, rbac]
dependency_graph:
  requires: [35-01]
  provides: [web/dependencies.py current_user_id + require_admin factories]
  affects: [web/routes/admin, tests/test_web_admin.py]
tech_stack:
  added: []
  patterns: [FastAPI Depends factory, locked 403 detail constants, TDD RED-GREEN]
key_files:
  created:
    - web/dependencies.py
    - tests/test_web_admin.py
  modified: []
decisions:
  - 403 detail strings locked as module-level constants (_DETAIL_NOT_AUTHENTICATED, _DETAIL_ADMIN_REQUIRED) per --reviews #5
  - require_admin reads auth.json live on every call (no caching) for immediate role-revocation semantics
  - test_web_admin.py created in Task 1 TDD cycle; Task 2 added no further changes (file was already complete)
metrics:
  duration: ~8min
  completed: 2026-05-13
  tasks_completed: 2
  files_created: 2
requirements: [RBAC-01, RBAC-02]
---

# Phase 35 Plan 03: web/dependencies.py Factories Summary

**One-liner:** FastAPI Depends factories current_user_id + require_admin with locked 403 JSON detail constants per --reviews #5.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create web/dependencies.py with current_user_id + require_admin | cdbfada | web/dependencies.py |
| 1 (TDD) | Add TestCurrentUserId + TestRequireAdmin + Wave-0 stubs | 9a48068 | tests/test_web_admin.py |
| 2 | Wave-0 stub tests (complete via Task 1 TDD cycle) | 9a48068 | tests/test_web_admin.py |

## What Was Built

### web/dependencies.py

New adapter hex module providing two FastAPI `Depends()` factories (D-07):

- `current_user_id(request: Request) -> str` — reads `getattr(request.state, 'user_id', None)`, raises `HTTPException(403, detail='Not authenticated')` when absent.
- `require_admin(request: Request) -> str` — reads uid, calls `get_user(uid)` live from auth.json, raises `HTTPException(403, detail='Admin access required')` when uid is None, user not found, or role != 'admin'. Returns uid on admin path.
- Module-level constants `_DETAIL_NOT_AUTHENTICATED` and `_DETAIL_ADMIN_REQUIRED` per --reviews consensus #5, ensuring FastAPI's default exception handler returns `{"detail": "<string>"}` JSON body.
- Hex boundary preserved: imports only `fastapi`, `starlette`, `stdlib`, and `auth_store`. No `signal_engine`, `data_fetcher`, or `main`.

### tests/test_web_admin.py

Wave-0 test file with:
- `TestCurrentUserId` — 3 tests (happy path, None user_id, missing attr)
- `TestRequireAdmin` — 5 tests (None uid, unknown uid, ff role, admin happy path, role-change-takes-effect-immediately)
- Every 403 assertion checks both `status_code == 403` AND `detail == _DETAIL_*` constant
- Wave-0 stub classes: `TestAdminSubRouter`, `TestAdminGate403Sweep`, `TestAdminPing`, `TestAdminRouteInvariant`

## Verification

- `tests/test_web_admin.py` — 8 passed
- `tests/test_web_healthz.py::TestWebHexBoundary` — 6 passed
- Full suite — 2168 passed, 0 failed

## Deviations from Plan

None — plan executed exactly as written. Task 2's test file was created during Task 1's TDD RED cycle, so Task 2 had no additional changes to make; acceptance criteria verified complete.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. `web/dependencies.py` is a pure in-process dependency factory; it adds no new HTTP routes. All threat mitigations from the plan's threat register are implemented:

- T-35-03-01: role read live from auth.json on every gated request (no cookie role trust)
- T-35-03-02: request.state is server-side only; middleware is sole setter
- T-35-03-03: detail strings are constants; neither reveals user existence
- T-35-03-04: `getattr(request.state, 'user_id', None)` defends against AttributeError on PUBLIC_PATHS
- T-35-03-06: TestWebHexBoundary AST walker scans dependencies.py

## Self-Check

- [x] web/dependencies.py exists and imports cleanly
- [x] tests/test_web_admin.py exists with 8 tests
- [x] Commits cdbfada and 9a48068 exist in git log
- [x] Full suite green (2168 passed)
