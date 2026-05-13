# Phase 35: Cookie + Depends(current_user) + Sub-Router Admin Gate - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Infrastructure phase — extend the `tsi_session` cookie payload to carry `uid`; create `web/dependencies.py` exposing `current_user_id` and `require_admin` FastAPI `Depends()` factories; mount `web/routes/admin/` as an `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` sub-router with one concrete route (`/admin/ping`) so the startup invariant test and 403-sweep are non-vacuous. Admin is the only user; all v1.2 routes survive untouched semantically.

</domain>

<decisions>
## Implementation Decisions

### uid lookup at login time

- **D-01:** Add `get_user_by_email(email: str, path: Path | None = None) -> dict | None` to `auth_store/_users.py` (and re-export via `auth_store/__init__.py`). The login flow (`web/routes/totp/__init__.py` — `_make_session_cookie`) calls this with the username (which is the admin's email) immediately after TOTP verification to obtain the `uid` for the new session payload.

- **D-02:** If `get_user_by_email` returns `None` (admin not yet bootstrapped into `users[]`), the session cookie is still issued with `uid=None` in the payload. The backward-compat shim in `_try_cookie` detects `uid=None` and resolves the admin's `uid` via a secondary lookup (see D-04). Admin can still log in during the bootstrap gap.

### Session payload shape

- **D-03:** New session payload: `{'u': uname, 'uid': uid, 'iat': int(time.time())}`. Keep `'u'` alongside new `'uid'` — old cookies (no `'uid'` key) still decode without error; shim only checks `'uid'` presence and value. No re-login forced on deploy.

### Backward-compat shim

- **D-04:** Shim lives in `AuthMiddleware._try_cookie`. After a valid session cookie is decoded, if `payload.get('uid')` is absent or `None`, attempt `get_user_by_email(payload.get('u', ''))` to resolve the admin uid. If that also fails (empty users[]), set `request.state.user_id = None`. If resolved, set `request.state.user_id = resolved_uid`. This keeps the shim logic in one place.

- **D-05:** For cookies that carry a valid `uid`, set `request.state.user_id = payload['uid']` directly — no extra auth.json read on the happy path.

### Header auth uid

- **D-06:** `AuthMiddleware._try_header` (legacy `X-Trading-Signals-Auth` header path) sets `request.state.user_id = None`. Header auth is an operator/script-only path; those callers never use per-user routes or admin-gated routes. Header-auth callers hitting `/admin/*` get 403 from `require_admin` — intentional.

### web/dependencies.py

- **D-07:** `web/dependencies.py` exposes two factories:
  - `current_user_id(request: Request) -> str` — reads `request.state.user_id`; raises `HTTPException(403)` if `None`. All authenticated routes that need user scoping declare `user_id: str = Depends(current_user_id)`.
  - `require_admin(request: Request) -> str` — calls `get_user(request.state.user_id)`, checks `row['role'] == 'admin'`; raises `HTTPException(403)` if `None` or non-admin. Returns the uid on success. One `auth.json` read per admin-gated request — authoritative, role changes take effect immediately.

### Admin sub-router

- **D-08:** `web/routes/admin/__init__.py` creates `router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])`. Registered on the FastAPI app in `web/app.py` before `AuthMiddleware`.

- **D-09:** Phase 35 adds one concrete route: `GET /admin/ping → 200 {"ok": true}`. This gives the startup invariant test and the parametrized 403-sweep real paths to assert on (non-vacuous coverage). Future admin routes (e.g., `/admin/users` in Phase 36) register on the same router and inherit the gate automatically.

### Startup invariant test

- **D-10:** New test class `TestAdminRouteInvariant` in `tests/test_web_app.py` (or a new `tests/test_web_admin.py`). On startup, walks `app.routes` recursively (including sub-routers via `APIRouter.routes`) and asserts: (a) every path matching `/admin/*` has `require_admin` somewhere in its `Depends` chain; (b) parametrized `non_admin_gets_403` fixture hits every `/admin/*` path with a non-admin session and asserts 403.

### Claude's Discretion

- Whether `require_admin` returns `str` (the uid) or `dict` (the full User row) — either works for the gate; planner may prefer dict for future phases.
- Exact module name for the startup invariant test (new file vs appended to existing `test_web_app.py`).
- Whether `get_user_by_email` uses linear scan or adds an index — users[] is tiny (single admin at this phase), linear scan is fine.
- Whether `request.state.user_id` is typed as `str | None` on the request object or left untyped.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase goal + requirements
- `.planning/ROADMAP.md` — Phase 35 goal, success criteria §Phase 35 (lines ~222–237)
- `.planning/REQUIREMENTS.md` — RBAC-01 (Depends(current_user) wiring); RBAC-02 (admin sub-router gate + startup invariant)

### Auth middleware (where shim + state.user_id live)
- `web/middleware/auth.py` — `AuthMiddleware._try_cookie` (shim goes here, D-04/D-05); `_try_header` (D-06); read fully before editing
- `web/routes/totp/__init__.py` — `_make_session_cookie(uname)` at line ~98 (D-03: add uid to payload); `_validate_session_cookie` at line ~67 (reads payload — update if needed)

### Auth store (lookup helpers)
- `auth_store/_users.py` — `get_user(uid)` pattern to mirror for new `get_user_by_email`; `create_user` for uid generation reference
- `auth_store/__init__.py` — re-export list; add `get_user_by_email` here (D-01)

### Web app factory (sub-router registration)
- `web/app.py` — `create_app()` route registration order; `add_middleware(AuthMiddleware, ...)` is LAST; new admin router must register BEFORE AuthMiddleware line

### Prior phase decisions
- `.planning/phases/34-user-registry-invite-token-storage/34-CONTEXT.md` — D-01..D-12: uid format, get_user() API, auth_store package layout; `last_login` deferred to this phase (Phase 35)
- `.planning/phases/31-core-module-split/31-CONTEXT.md` — `__init__.py` re-export conventions

### Hex boundary guard
- `tests/test_web_healthz.py::TestWebHexBoundary` — AST guard; `web/dependencies.py` is an adapter hex (peer of `web/routes/`); allowed imports: fastapi, starlette, stdlib, auth_store

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `web/middleware/auth.py::_try_cookie` — the extension point for shim (D-04/D-05); currently returns `True` after signature check; must be extended to also set `request.state.user_id` from payload
- `web/routes/totp/__init__.py::_make_session_cookie(uname)` — calls `session_serializer.dumps({'u': uname, 'iat': ...})`; extend to `dumps({'u': uname, 'uid': uid, 'iat': ...})` (D-03)
- `auth_store/_users.py::get_user(uid)` — linear scan of `users[]`; `get_user_by_email` follows identical pattern scanning by `email` field
- `auth_store/__init__.py` — re-export pattern established; add `get_user_by_email` to `__all__` list

### Established Patterns
- `_make_session_cookie` / `_validate_session_cookie` live in `web/routes/totp/__init__.py` (not in middleware) — Phase 35 extends both
- `request.state.*` is the FastAPI mechanism for passing per-request context from middleware to route handlers — `user_id` follows this pattern
- `APIRouter` sub-router mounting: `app.include_router(router)` in `create_app()` before `add_middleware(AuthMiddleware, ...)`
- Hex boundary: `web/dependencies.py` may import `auth_store` (it's an I/O adapter, not pure hex); `web/middleware/auth.py` already imports `auth_store` via local imports inside methods (see `_try_cookie` → `from auth_store import update_last_seen`)

### Integration Points
- `web/app.py::create_app()` — add `from web.routes.admin import router as admin_router` + `application.include_router(admin_router)` before the `add_middleware` line
- `tests/` — new test for startup invariant + 403-sweep; existing `test_web_healthz.py::TestWebHexBoundary` AST guard must continue to pass after `web/dependencies.py` is added

</code_context>

<specifics>
## Specific Ideas

- `get_user_by_email` is the canonical Phase 35 helper — named cleanly, works for F&F users when they arrive in Phase 36+, not just admin.
- `/admin/ping` route returns `{"ok": true}` — minimal, unambiguous, easy to assert on in tests.
- `require_admin` reads role from `auth.json` live (one read per gated request) — authoritative; role changes take effect immediately without re-login. This is the right tradeoff at this scale (single droplet, few admin-gated requests).
- The backward-compat shim window is intentionally short: once admin is bootstrapped into `users[]` and logs in once, all subsequent sessions carry `uid` directly. The shim is a grace period for the first deploy after Phase 35.

</specifics>

<deferred>
## Deferred Ideas

- `last_login` field update on `User` row — deferred FROM Phase 34 to Phase 35 (noted in Phase 34 CONTEXT.md). Phase 35 can add `update_last_login(uid)` call after successful session issuance in `_make_session_cookie` or the TOTP route, but this is Claude's discretion — the startup invariant and RBAC-01/02 are the primary deliverables.
- `mutate_auth()` wrapper for all auth writes — deferred to Phase 36+ per Phase 34 D-01.
- Caching `require_admin` results per-request (e.g., via `lru_cache` or request-scoped state) — premature at this scale; single-admin, few gated routes.

</deferred>

---

*Phase: 35-cookie-depends-current-user-sub-router-admin-gate*
*Context gathered: 2026-05-13*
