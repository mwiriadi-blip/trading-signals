---
phase: 35-cookie-depends-current-user-sub-router-admin-gate
plan: 04
subsystem: auth
tags: [fastapi, admin, sub-router, apirouter, depends, require_admin]

requires:
  - phase: 35-03
    provides: web/dependencies.py with require_admin factory

provides:
  - web/routes/admin/__init__.py — APIRouter(prefix='/admin', dependencies=[Depends(require_admin)]) per D-08
  - GET /admin/ping route returning {'ok': True} per D-09
  - TestAdminSubRouter with 6 router-shape introspection tests (pre-wiring shape)

affects: [35-05, future admin route additions in Phase 36+]

tech-stack:
  added: []
  patterns:
    - "Admin sub-router gate: inject Depends(require_admin) at APIRouter construction, not per-route"
    - "FastAPI bakes router prefix into route.path at construction time (not at include_router time)"
    - "Pre-include introspection tests: router.dependencies, router.routes, router.prefix are all stable before app wiring"

key-files:
  created:
    - web/routes/admin/__init__.py
  modified:
    - tests/test_web_admin.py

key-decisions:
  - "FastAPI bakes prefix into route.path at APIRouter construction, not at include_router time — test checks '/admin/ping' not '/ping'"
  - "Gate injected at router level (not per-route) so future admin routes inherit it automatically without per-contributor discipline"
  - "Kept OpenCode-flagged introspection tests as regression detectors — first APIRouter sub-router in codebase warrants this"

patterns-established:
  - "AdminSubRouter pattern: APIRouter(prefix='/admin', dependencies=[Depends(require_admin)]) is the single chokepoint"
  - "New admin routes go on router, not application — Plan 05's startup invariant test catches violations"

requirements-completed: [RBAC-02]

duration: 8min
completed: 2026-05-13
---

# Phase 35 Plan 04: Admin Sub-Router Summary

**APIRouter sub-router for /admin with require_admin gate baked in at construction (D-08) and GET /admin/ping probe route (D-09), plus 6 pre-wiring introspection tests in TestAdminSubRouter**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-13T00:00:00Z
- **Completed:** 2026-05-13T00:08:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `web/routes/admin/` package with `APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])` — gate is at mount time, inherited by all future routes
- Registered `GET /admin/ping` returning `{'ok': True}` as the D-09 probe target for Plan 05's startup invariant test
- Populated `TestAdminSubRouter` with 6 introspection tests; each docstring documents the FastAPI behaviour verified (addresses OpenCode LOW review note)
- Full suite green: 2185 passed, 1 skipped (pre-existing Plan 03 skip)

## Task Commits

1. **Task 1: Create web/routes/admin/__init__.py** — `6a634a2` (feat)
2. **Task 2: Populate TestAdminSubRouter** — `bddedc2` (feat)

## Files Created/Modified

- `web/routes/admin/__init__.py` — new package; APIRouter with require_admin gate; GET /ping route
- `tests/test_web_admin.py` — replaced `class TestAdminSubRouter: pass` stub with 6 introspection tests; added `from fastapi import APIRouter`, `from fastapi.routing import APIRoute`, `from web.routes.admin import router` imports

## Decisions Made

- **FastAPI prefix baking:** The PLAN.md context note said `router.routes` entries carry `/ping` (no prefix) before `include_router`. Actual FastAPI behaviour (verified) bakes the prefix into `route.path` at router construction time — path is `/admin/ping` even pre-include. Updated test assertion accordingly. Documented in test docstring.
- **Gate at router level (not per-route):** Consistent with D-08. All future routes added to `router` inherit `require_admin` without per-contributor action.
- **Kept introspection tests:** OpenCode noted they "test the framework more than the application" — kept as regression detectors since this is the first `APIRouter` sub-router in the codebase.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FastAPI route path includes prefix at construction, not include_router time**
- **Found during:** Task 2 (TestAdminSubRouter test_router_has_ping_route)
- **Issue:** Plan context stated pre-include path would be `/ping`; actual FastAPI stores `/admin/ping` in `route.path` immediately at `APIRouter` construction
- **Fix:** Updated test to assert `r.path == '/admin/ping'`; updated docstring to document actual FastAPI behaviour
- **Files modified:** tests/test_web_admin.py
- **Verification:** `.venv/bin/pytest -x tests/test_web_admin.py::TestAdminSubRouter` — 6 passed
- **Committed in:** bddedc2 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — framework behaviour mismatch in plan context note)
**Impact on plan:** Minor. Only affected the test assertion path string. Implementation unchanged.

## Issues Encountered

None beyond the path-baking deviation above.

## User Setup Required

None.

## Next Phase Readiness

- `web/routes/admin/__init__.py` is importable and exports `router`
- Plan 05 can now call `app.include_router(admin_router)` in `web/app.py` and run the startup invariant test
- `TestAdminGate403Sweep`, `TestAdminPing`, `TestAdminRouteInvariant` stubs remain in `tests/test_web_admin.py` — filled by Plan 05

## Self-Check

- `web/routes/admin/__init__.py` exists: FOUND
- `tests/test_web_admin.py` populated: FOUND
- Commit `6a634a2` exists: FOUND
- Commit `bddedc2` exists: FOUND

## Self-Check: PASSED

---
*Phase: 35-cookie-depends-current-user-sub-router-admin-gate*
*Completed: 2026-05-13*
