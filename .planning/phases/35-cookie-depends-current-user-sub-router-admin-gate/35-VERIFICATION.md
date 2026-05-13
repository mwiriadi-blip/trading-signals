---
phase: 35-cookie-depends-current-user-sub-router-admin-gate
verified: 2026-05-13T00:00:00Z
status: human_needed
score: 9/10 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Verify RBAC-01 partial satisfaction is acceptable — existing non-admin authenticated routes (/trades, /journal, /paper-trades) do NOT yet use Depends(current_user_id)"
    expected: "Phase owner confirms Phase 36 will complete the migration; partial RBAC-01 is intentional for this phase"
    why_human: "RBAC-01 full text requires dependency injection in EVERY route. Phase 35 only satisfies the admin-gated route portion. The deferral is documented in test source (consensus #2 NOTE) but no Phase 36 roadmap entry exists yet to formally accept the gap."
deferred:
  - truth: "pre-v1.3 routes get scoped via the dependency, not per-route boilerplate (RBAC-01 full text)"
    addressed_in: "Phase 36 (planned, not yet created)"
    evidence: "tests/test_web_admin.py line 14: '# --reviews HIGH consensus #2: Phase 35 does NOT migrate existing authenticated non-admin route handlers to Depends(current_user_id). That migration is Phase 36 (per-user scoping).'"
---

# Phase 35: RBAC Foundations Verification Report

**Phase Goal:** Establish RBAC foundations — cookie carries uid, middleware populates request.state.user_id, FastAPI Depends factories gate admin routes, admin sub-router mounted before middleware.
**Verified:** 2026-05-13
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | auth_store.get_user_by_email(email) implemented with case-insensitive comparison, re-exported from auth_store top-level | VERIFIED | `auth_store/_users.py` line 134: `def get_user_by_email(email: str, path: Path | None = None) -> dict | None`; `auth_store/__init__.py` line 66 re-export; `.venv/bin/python -c "from auth_store import get_user_by_email; print(callable(get_user_by_email))"` → True |
| 2 | _make_session_cookie payload includes uid field; both TOTP call sites resolve uid via get_user_by_email | VERIFIED | `web/routes/totp/__init__.py` line 98: `def _make_session_cookie(uname: str, uid: str | None = None) -> str`; line 101: `{'u': uname, 'uid': uid, 'iat': ...}`; 2 occurrences of `auth_store.get_user_by_email(username)` at post_enroll and post_verify call sites (lines 205–209, 250–256) |
| 3 | request.state.user_id = None set at TOP of AuthMiddleware.dispatch before PUBLIC_PATHS, rate-limit, _try_cookie | VERIFIED | `web/middleware/auth.py` line 172: `request.state.user_id = None` is the first executable statement in dispatch |
| 4 | _try_cookie Path 1 sets request.state.user_id from payload uid (D-05 happy path) or D-04 shim fallback with logger.info | VERIFIED | `web/middleware/auth.py` line 269: `request.state.user_id = uid`; lines 260–265: D-04 shim with local import of get_user_by_email and logger.info('[Auth] D-04 cookie shim ...') |
| 5 | tsi_trusted path (Option B): user_id stays None, logger.warning emitted | VERIFIED | `web/middleware/auth.py` lines 276–295: Option B path does not set user_id; logger.warning contains 'Trusted-device session active — user_id not resolved; /admin/* routes will return 403 (Phase 35 Option B accepted limitation)' |
| 6 | web/dependencies.py exposes current_user_id and require_admin factories with locked 403 detail constants | VERIFIED | File exists; `_DETAIL_NOT_AUTHENTICATED = 'Not authenticated'` (line 18), `_DETAIL_ADMIN_REQUIRED = 'Admin access required'` (line 19); both factories implemented; importable: `.venv/bin/python -c "from web.dependencies import current_user_id, require_admin, _DETAIL_NOT_AUTHENTICATED, _DETAIL_ADMIN_REQUIRED; print(_DETAIL_NOT_AUTHENTICATED, _DETAIL_ADMIN_REQUIRED)"` → `Not authenticated Admin access required` |
| 7 | web/routes/admin/__init__.py exposes router as APIRouter(prefix='/admin', dependencies=[Depends(require_admin)]) with GET /admin/ping | VERIFIED | `web/routes/admin/__init__.py` line 15: `router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])`; line 18: `@router.get('/ping')`; line 19–20: `def ping(): return {'ok': True}`; importable with correct shape |
| 8 | web/app.py includes admin router via include_router(admin_router) BEFORE add_middleware(AuthMiddleware, ...) | VERIFIED | `web/app.py` line 198: `application.include_router(admin_router)`; line 203: `application.add_middleware(AuthMiddleware, ...)`; awk ordering check exits 0 |
| 9 | Startup invariant test walks app.router.routes recursively and asserts every /admin/* path has require_admin in dependency chain | VERIFIED | `tests/test_web_admin.py` line 70: `def _walk_routes(routes)`; line 239: `class TestAdminRouteInvariant`; 27 tests in test_web_admin.py all pass |
| 10 | RBAC-01 full text: "pre-v1.3 routes get scoped via the dependency" — existing non-admin authenticated routes use Depends(current_user_id) | UNCERTAIN (deferred to Phase 36) | Phase 35 explicitly defers migration of /trades, /journal, /paper-trades to Depends(current_user_id) per --reviews HIGH consensus #2. Documented in test source. Phase 36 not yet created in roadmap. |

**Score:** 9/10 truths verified (1 deferred/uncertain)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `auth_store/_users.py` | get_user_by_email with case-insensitive comparison | VERIFIED | Line 134 definition; needle/stored lowercased; docstring confirms 'case-insensitive' |
| `auth_store/__init__.py` | Re-export of get_user_by_email + __all__ entry | VERIFIED | Line 66 in import block; line 135 in __all__; DEFAULT_AUTH_PATH ordering invariant (lines 1–22) preserved |
| `tests/test_auth_store.py` | TestGetUserByEmail — 9 named tests | VERIFIED | Line 789: class TestGetUserByEmail; 9 tests collected and passing |
| `web/routes/totp/__init__.py` | _make_session_cookie extended with uid; both call sites use get_user_by_email | VERIFIED | Signature at line 98; payload dict at line 101; 2 call sites (post_enroll, post_verify) |
| `web/middleware/auth.py` | dispatch-top user_id=None; _try_cookie happy/shim/trusted-device paths; logger.info/warning | VERIFIED | Line 172 default; lines 260–295 Path 1 shim + logger.info; lines 276–295 Path 2 logger.warning |
| `tests/test_web_auth_middleware.py` | TestCookieUidExtension — 9 tests | VERIFIED | Line 805: class TestCookieUidExtension; 9 passed |
| `tests/test_web_routes_totp.py` | TestMakeSessionCookieUidPayload — uid round-trip tests | VERIFIED | Line 464: class TestMakeSessionCookieUidPayload; 3 tests in class |
| `web/dependencies.py` | current_user_id + require_admin factories + locked detail constants | VERIFIED | File exists; all 4 symbols importable; hex boundary preserved (no signal_engine/data_fetcher/main imports) |
| `tests/test_web_admin.py` | TestCurrentUserId (3) + TestRequireAdmin (5) + TestAdminSubRouter (6) + TestAdminRouteInvariant (2) + sweep classes + TestAdminPing (4) + TestPrePhase35RoutesStructuralParity (4) | VERIFIED | 27 tests collected; all pass; all required classes present |
| `web/routes/admin/__init__.py` | APIRouter(prefix='/admin', dependencies=[Depends(require_admin)]) + GET /ping | VERIFIED | Line 15 router construction; line 18–20 ping route; `__all__ = ['router']` |
| `web/app.py` | include_router(admin_router) before add_middleware | VERIFIED | Lines 198 + 203; ordering confirmed by awk check |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| auth_store.__init__ | auth_store._users.get_user_by_email | from auth_store._users import (...) block | WIRED | auth_store/__init__.py line 66 |
| web/routes/totp/__init__.py::post_verify | auth_store.get_user_by_email + _make_session_cookie(username, uid=uid) | local auth_store import inside method | WIRED | totp/__init__.py lines 205–209, 250–256 |
| web/middleware/auth.py::_try_cookie | request.state.user_id | assignment from payload uid (D-05) or shim (D-04) | WIRED | auth.py line 269 |
| web/middleware/auth.py::dispatch | request.state.user_id = None default | first statement of dispatch | WIRED | auth.py line 172 |
| web/dependencies.py::require_admin | auth_store.get_user(uid) | top-level from auth_store import get_user | WIRED | dependencies.py line 15 |
| web/routes/admin/__init__.py | web.dependencies.require_admin | from web.dependencies import require_admin | WIRED | admin/__init__.py line 13 |
| web/app.py::create_app | web.routes.admin.router | from web.routes.admin import router as admin_router + include_router | WIRED | app.py lines 41, 198 |
| tests/test_web_admin.py::TestAdminRouteInvariant | app.router.routes (recursive walk) | _walk_routes helper; create_app() then filter /admin/* paths | WIRED | test_web_admin.py lines 70, 239–295 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| web/middleware/auth.py::_try_cookie | request.state.user_id | payload['uid'] from signed itsdangerous cookie, OR D-04 shim via auth_store.get_user_by_email | Yes — live auth.json read on shim path; cookie payload on happy path | FLOWING |
| web/dependencies.py::require_admin | row (user record) | auth_store.get_user(uid) — live auth.json read | Yes — live read per request | FLOWING |
| web/routes/admin/__init__.py::ping | (no state needed) | static return {'ok': True} | N/A | VERIFIED |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| get_user_by_email importable and callable | `.venv/bin/python -c "from auth_store import get_user_by_email; print(callable(get_user_by_email))"` | True | PASS |
| get_user_by_email in __all__ | `.venv/bin/python -c "import auth_store; print('get_user_by_email' in auth_store.__all__)"` | True | PASS |
| web/dependencies.py factories importable | `.venv/bin/python -c "from web.dependencies import current_user_id, require_admin, _DETAIL_NOT_AUTHENTICATED, _DETAIL_ADMIN_REQUIRED; print(_DETAIL_NOT_AUTHENTICATED, _DETAIL_ADMIN_REQUIRED)"` | Not authenticated Admin access required | PASS |
| admin router shape | `.venv/bin/python -c "from web.routes.admin import router; from fastapi import APIRouter; assert isinstance(router, APIRouter); assert router.prefix == '/admin'; print('router ok')"` | router ok | PASS |
| admin/ping route in app.routes | WEB_AUTH_* env + `create_app(); r.path == '/admin/ping'` | admin ping route found | PASS |
| include_router before add_middleware ordering | awk pattern check on web/app.py | exit 0 | PASS |
| Full pytest suite | `.venv/bin/pytest --tb=short -q` | 2199 passed, 0 failures | PASS |
| TestGetUserByEmail (9 cases) | `.venv/bin/pytest tests/test_auth_store.py::TestGetUserByEmail` | 9 passed | PASS |
| TestCookieUidExtension (9 cases) | `.venv/bin/pytest tests/test_web_auth_middleware.py::TestCookieUidExtension` | 9 passed | PASS |
| TestWebHexBoundary | `.venv/bin/pytest tests/test_web_healthz.py::TestWebHexBoundary` | 6 passed | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| RBAC-01 | Plans 01, 02, 03, 05 | cookie session payload includes uid; user_id available via Depends(current_user_id) in every route; admin-only change with no observable behaviour change | PARTIAL | Cookie uid: VERIFIED. Middleware populates user_id: VERIFIED. current_user_id factory exists: VERIFIED. Admin gate routes consume factory: VERIFIED. Existing non-admin authenticated routes NOT yet migrated per --reviews HIGH consensus #2; deferred to Phase 36. |
| RBAC-02 | Plans 03, 04, 05 | Admin-only routes under APIRouter(prefix="/admin", dependencies=[Depends(require_admin)]); startup invariant test | SATISFIED | Admin sub-router at web/routes/admin/__init__.py with gate at construction; TestAdminRouteInvariant walks app.router.routes recursively; all 27 admin tests pass |

**Traceability table note:** REQUIREMENTS.md traceability table (line 106–107) maps RBAC-01 and RBAC-02 to "Phase 33" — this is a pre-renumbering artefact. The PLAN frontmatter for all 5 Phase 35 plans explicitly claims these requirement IDs, and the implementation lives entirely in Phase 35. Phase 33 (schema migration) claimed no requirements. The table is stale documentation; the implementation mapping is correct.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TBD/FIXME/XXX markers found in any modified file | — | — |

No debt markers, placeholder returns, or empty implementations found across: `auth_store/_users.py`, `auth_store/__init__.py`, `web/routes/totp/__init__.py`, `web/middleware/auth.py`, `web/dependencies.py`, `web/routes/admin/__init__.py`, `web/app.py`, `tests/test_auth_store.py`, `tests/test_web_auth_middleware.py`, `tests/test_web_admin.py`.

---

### Human Verification Required

#### 1. RBAC-01 Partial Satisfaction Sign-Off

**Test:** Confirm that the Phase 36 deferral of non-admin route migration is intentional and accepted.

**Expected:** Phase owner acknowledges RBAC-01 is partially satisfied in Phase 35 (factory exists, cookie carries uid, middleware populates user_id, admin routes consume factory), and that full migration of /trades, /journal, /paper-trades to Depends(current_user_id) is scheduled for Phase 36 before RBAC-01 is marked complete.

**Why human:** RBAC-01 full text reads "Depends(current_user) in every route." Phase 35 satisfies admin routes only. The deferral is documented in test source (`tests/test_web_admin.py` lines 14–20) and all five plan files, but no Phase 36 roadmap entry yet exists. A human decision is required on whether to mark RBAC-01 as partially closed now or leave it open until Phase 36 lands.

---

### Gaps Summary

No hard blockers. The phase goal — "cookie carries uid, middleware populates request.state.user_id, FastAPI Depends factories gate admin routes, admin sub-router mounted before middleware" — is fully achieved. All four parts of the goal statement are verified in the codebase.

The single human-needed item is a documentation/acceptance decision on RBAC-01 partial satisfaction (existing non-admin route migration deferred to Phase 36 by design).

---

_Verified: 2026-05-13_
_Verifier: Claude (gsd-verifier)_
