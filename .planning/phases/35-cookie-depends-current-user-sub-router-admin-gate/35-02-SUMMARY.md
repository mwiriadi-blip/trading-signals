---
phase: 35
plan: 02
subsystem: auth
tags: [auth, cookie, middleware, user_id, shim, tdd]
dependency_graph:
  requires: [35-01]
  provides: [request.state.user_id, cookie-uid-payload, D-04-shim, Option-B-trusted-device]
  affects: [web/middleware/auth.py, web/routes/totp/__init__.py]
tech_stack:
  added: []
  patterns:
    - local-import-inside-method-body (auth_store in middleware)
    - AST-backed ordering assertion in test
    - TDD RED/GREEN per task
key_files:
  created: []
  modified:
    - web/routes/totp/__init__.py
    - web/middleware/auth.py
    - tests/test_web_routes_totp.py
    - tests/test_web_auth_middleware.py
decisions:
  - "Option B accepted: tsi_trusted path leaves user_id=None; admin on trusted device gets 403 on /admin/* — intentional, logged via warning, tested with skip gate"
  - "Dispatch-top reset: request.state.user_id=None is first statement in dispatch, before EXEMPT_PATHS, PUBLIC_PATHS, rate-limit, _try_cookie — eliminates stale-leak race"
  - "Shim logger.info: D-04 backward-compat shim emits one INFO line per trigger with resolved/miss status + uname — operator observability"
metrics:
  duration: ~18min
  completed: 2026-05-13
  tasks_completed: 2
  files_modified: 4
---

# Phase 35 Plan 02: Cookie uid payload extension + AuthMiddleware user_id population Summary

Wire `user_id` into the tsi_session cookie payload and into `request.state.user_id` via AuthMiddleware, with backward-compat shim for old cookies and Option B accepted limitation for trusted-device sessions.

## Tasks Completed

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 RED | b7b67ab | Failing tests for _make_session_cookie uid payload (TestMakeSessionCookieUidPayload) |
| Task 1 GREEN | f6d8ef1 | _make_session_cookie(uname, uid=None) + get_user_by_email at both call sites |
| Task 2 RED | 64bf1d6 | Failing tests for TestCookieUidExtension (9 tests) |
| Task 2 GREEN | 4d52a3f | dispatch-top user_id=None + _try_cookie shim + trusted-device warning |

## What Was Implemented

### Task 1 — `_make_session_cookie` uid payload extension (D-03)

`web/routes/totp/__init__.py`:
- `_make_session_cookie(uname: str, uid: str | None = None) -> str` — new signature
- Payload now: `{'u': uname, 'uid': uid, 'iat': int(time.time())}`
- `post_enroll` call site: `row = auth_store.get_user_by_email(username); uid = row['uid'] if row else None`
- `post_verify` call site: same pattern
- `_validate_session_cookie` unchanged — its isinstance guard handles new payload shape

`tests/test_web_routes_totp.py`:
- `TestMakeSessionCookieUidPayload` class — 3 tests:
  - `test_make_session_cookie_uid_none_default`: no user in auth.json → uid=None in cookie
  - `test_make_session_cookie_includes_uid`: admin user in auth.json → uid=user.uid in cookie
  - `test_make_session_cookie_round_trip_via_validate`: uid-bearing cookie decodes correctly

### Task 2 — AuthMiddleware user_id population

`web/middleware/auth.py`:
- `dispatch`: `request.state.user_id = None` added as FIRST statement (before EXEMPT_PATHS, PUBLIC_PATHS, rate-limit, _try_cookie)
- `_try_cookie` Path 1 (tsi_session):
  - Captures `payload = self._session_serializer.loads(...)`
  - Happy path: `uid = payload.get('uid')` → `request.state.user_id = uid`
  - D-04 shim: if `uid is None` → `from auth_store import get_user_by_email; row = get_user_by_email(uname); uid = row['uid'] if row else None`
  - Shim emits `logger.info('[Auth] D-04 cookie shim %s uname=%s', 'resolved'/'miss', uname)`
- `_try_cookie` Path 2 (tsi_trusted, Option B):
  - `user_id` stays at dispatch-top default (None)
  - `logger.warning('[Auth] Trusted-device session active — user_id not resolved; /admin/* routes will return 403 (Phase 35 Option B accepted limitation)')`
- `_try_header`: no body change — dispatch-top default covers D-06

`tests/test_web_auth_middleware.py`:
- `TestCookieUidExtension` class — 9 tests:
  - `test_happy_path_sets_user_id_from_payload` (D-05)
  - `test_shim_path_resolves_via_get_user_by_email` (D-04)
  - `test_shim_returns_none_when_users_empty`
  - `test_shim_logs_info_when_triggered`
  - `test_header_auth_leaves_user_id_none` (D-06)
  - `test_default_user_id_is_none_at_dispatch_top` (AST-level ordering check)
  - `test_default_user_id_is_none_on_public_path`
  - `test_trusted_device_admin_access_returns_403` (Option B — skipped until Plan 03 registers /admin/*)
  - `test_trusted_device_logs_warning` (Option B observability)

## Test Results

- `tests/test_web_routes_totp.py`: 19 passed
- `tests/test_web_auth_middleware.py`: 50 passed, 1 skipped (admin route gate — expected, Plan 03 scope)
- `tests/test_web_healthz.py::TestWebHexBoundary`: 6 passed
- Full worktree suite: 2171 passed, 1 skipped, 13 deselected

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AST dispatch-top test used main-repo relative path**
- **Found during:** Task 2 GREEN
- **Issue:** `WEB_AUTH_PATH = Path('web/middleware/auth.py')` is a relative path resolved from pytest's CWD (main repo root), so the AST check read the UNMODIFIED main-repo auth.py and found no `user_id = None` statement
- **Fix:** Changed AST test to use `Path(__file__).parent.parent / 'web' / 'middleware' / 'auth.py'` — resolves relative to the test file's location, which is always in the worktree
- **Files modified:** `tests/test_web_auth_middleware.py`
- **Commit:** 4d52a3f (included in GREEN commit)

**2. [Rule 1 - Bug] test_make_session_cookie_uid_none_default had dead import**
- **Found during:** Task 1 RED
- **Issue:** Test had `from web.routes.totp import _make_session_cookie` — function is a closure inside `register()`, not importable at module level
- **Fix:** Removed dead import line; test already tested via route handler flow
- **Files modified:** `tests/test_web_routes_totp.py`
- **Commit:** b7b67ab

## Known Stubs

None. All implementation is functional — both call sites resolve uid from auth.json, middleware populates request.state.user_id on every authenticated request.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes beyond those documented in the plan's threat model (T-35-02-01 through T-35-02-08).

## Self-Check: PASSED
