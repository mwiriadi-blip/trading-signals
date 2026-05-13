---
phase: 35
plan: "05"
subsystem: web/auth
tags: [auth, admin, wiring, startup-invariant, integration, rbac]
dependency_graph:
  requires: [35-02, 35-04]
  provides: [admin-router-wired, startup-invariant-test, 403-sweep-split, structural-parity]
  affects: [web/app.py, tests/test_web_admin.py]
tech_stack:
  added: []
  patterns:
    - include_router before add_middleware (grep-auditability convention)
    - recursive _walk_routes helper for startup invariant
    - split 403-sweep classes (unauthenticated vs header-auth)
    - structural parity over byte-identical regression tests
key_files:
  created: []
  modified:
    - web/app.py
    - tests/test_web_admin.py
decisions:
  - include_router(admin_router) placed immediately before add_middleware per D-08 + --reviews #4
  - unauthenticated sweep accepts 401/403/302 (middleware intercepts before require_admin for non-browser clients)
  - GET /dashboard structural parity asserts 404 (route never existed; Phase 35 must not create one)
  - RBAC-01 partially satisfied this phase; existing non-admin route migration deferred to Phase 36
metrics:
  duration: "~15 minutes"
  completed: "2026-05-13"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
---

# Phase 35 Plan 05: Final Wiring + Verification Summary

Admin router wired into create_app() before add_middleware; all four --reviews consensus concerns addressed end-to-end with split 403-sweep, recursive route invariant, and structural parity replacing byte-identical.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wire admin router into web/app.py before add_middleware | fe42da8 | web/app.py |
| 2 | Populate TestAdminRouteInvariant + split 403-sweep + TestAdminPing + TestPrePhase35RoutesStructuralParity | 2705464 | tests/test_web_admin.py |

## What Was Built

**Task 1 — web/app.py wiring:**
- Added `from web.routes.admin import router as admin_router` import
- Added `application.include_router(admin_router)` immediately before `add_middleware(AuthMiddleware, ...)` in `create_app()`
- Phase 35 D-08 + --reviews #4 ordering comment documents the grep-auditability convention

**Task 2 — tests/test_web_admin.py population:**
- `_walk_routes(routes)` helper: recursive yield of APIRoute objects, future-proofs invariant against Phase 36+ Mount/nested APIRouter cases
- `TestAdminRouteInvariant` (2 tests): vacuous-guard + recursive dependency chain walk
- `TestAdminGate403SweepUnauthenticated` (1 parametrized): accepts 401/403/302 since middleware intercepts non-browser clients before require_admin
- `TestAdminGate403SweepHeaderAuth` (1 parametrized): asserts 403 + JSON body for header-auth path (user_id=None from dispatch-top reset)
- `TestAdminGate403SweepNonAdminRole` (1 parametrized): asserts 403 + JSON body for role='ff' cookie
- `TestAdminPing` (4 tests): admin-session 200, legacy-shim backward-compat, bootstrap-gap 403, uid-spoof negative
- `TestPrePhase35RoutesStructuralParity` (4 tests): GET /, GET /dashboard (asserts 404 — never existed), GET /paper-trades, POST /login
- Module-level NOTE documents Phase 36 deferred migration per --reviews consensus #2

## Deviations from Plan

### Auto-fixed Issues

None - plan executed exactly as written with one clarification.

### Deviation 1 (Clarification — not a bug)

**Found during:** Task 2 — TestAdminGate403SweepUnauthenticated

**Issue:** The plan stated `assert status_code == 403` for the unauthenticated sweep, but the actual behavior is that the AuthMiddleware intercepts the request before `require_admin` is even reached. TestClient does not send `Sec-Fetch` or `Accept: text/html` headers, so middleware E-02 step 3 returns 401 plain-text (non-browser path). The 403 from require_admin is never hit.

**Fix:** The plan's own `<behavior>` block contained the correct note: "Accept any of {401, 403, 302} but if 403 then assert JSON body schema." The test was written to accept `{401, 403, 302}` with conditional JSON body assertion when status is 403.

**Files modified:** tests/test_web_admin.py

### Deviation 2 (Clarification — not a bug)

**Found during:** Task 2 — TestPrePhase35RoutesStructuralParity

**Issue:** The plan lists `GET /dashboard` as a structural parity route to check. Running `create_app()` and inspecting routes confirms `/dashboard` was never a registered route — it does not exist in app.routes. The canonical dashboard is `GET /`.

**Fix:** The test `test_dashboard_route_not_found_is_baseline` asserts status 404, with a docstring explaining this IS the correct pre-Phase-35 baseline (the route never existed). Phase 35 must not accidentally create a `/dashboard` route.

**Files modified:** tests/test_web_admin.py

## Verification Results

- `pytest tests/test_web_admin.py` — 27 passed
- `pytest tests/test_web_app_factory.py` — 35 passed
- `pytest tests/test_web_healthz.py::TestWebHexBoundary` — 6 passed
- Full suite (`pytest -x --tb=short`) — 2199 passed, 0 failures
- `awk` ordering check (`include_router` before `add_middleware`) — exits 0
- Python import check (`admin` route appears in `app.routes`) — prints `ok`

## Known Stubs

None. All test class stubs from Plans 03 and 04 are now populated.

## Threat Surface Scan

No new security-relevant surface introduced beyond what the plan's threat model covers. The `include_router(admin_router)` call wires an already-constructed router (Plan 04) — no new endpoints, no new auth paths beyond `/admin/ping` which was already defined.

## Self-Check: PASSED

- web/app.py — FOUND
- tests/test_web_admin.py — FOUND
- 35-05-SUMMARY.md — FOUND
- Commit fe42da8 — FOUND
- Commit 2705464 — FOUND
