# Phase 35: Cookie + Depends(current_user) + Sub-Router Admin Gate — Research

**Researched:** 2026-05-13
**Domain:** FastAPI dependency injection, middleware state propagation, sub-router mounting
**Confidence:** HIGH — all findings verified against live codebase

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `get_user_by_email(email, path=None) -> dict | None` added to `auth_store/_users.py`, re-exported via `auth_store/__init__.py`. Login flow calls this immediately after TOTP verification.
- **D-02:** If `get_user_by_email` returns `None`, cookie issued with `uid=None`; shim resolves admin uid on next request.
- **D-03:** New session payload: `{'u': uname, 'uid': uid, 'iat': int(time.time())}`. Old cookies (no `uid` key) decode without error; shim checks `uid` presence/value.
- **D-04:** Shim lives in `AuthMiddleware._try_cookie`. After valid decode: if `payload.get('uid')` is absent or `None`, call `get_user_by_email(payload.get('u', ''))`. If that fails, `request.state.user_id = None`. If resolved, `request.state.user_id = resolved_uid`.
- **D-05:** Cookies carrying a valid `uid` set `request.state.user_id = payload['uid']` directly — no extra auth.json read on happy path.
- **D-06:** `AuthMiddleware._try_header` sets `request.state.user_id = None`. Header-auth callers hitting `/admin/*` get 403 from `require_admin` — intentional.
- **D-07:** `web/dependencies.py` exposes `current_user_id(request) -> str` (raises 403 if None) and `require_admin(request) -> str` (reads `get_user(request.state.user_id)`, checks `row['role'] == 'admin'`, raises 403 if None or non-admin, returns uid on success).
- **D-08:** `web/routes/admin/__init__.py` creates `router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])`. Registered on FastAPI app in `web/app.py` before `AuthMiddleware`.
- **D-09:** Phase 35 adds one concrete route: `GET /admin/ping → 200 {"ok": true}`.
- **D-10:** New test class `TestAdminRouteInvariant` (new file `tests/test_web_admin.py` or appended to `tests/test_web_app.py`). Walks `app.routes` and asserts (a) every `/admin/*` path has `require_admin` in its `Depends` chain; (b) parametrized `non_admin_gets_403` hits every `/admin/*` path with a non-admin session and asserts 403.

### Claude's Discretion

- Whether `require_admin` returns `str` (the uid) or `dict` (the full User row).
- Exact module name for the startup invariant test (new file vs appended to existing `test_web_app.py`).
- Whether `get_user_by_email` uses linear scan or index — linear scan is fine (tiny users[]).
- Whether `request.state.user_id` is typed as `str | None` or left untyped.

### Deferred Ideas (OUT OF SCOPE)

- `last_login` field on User row — Claude's discretion whether to add `update_last_login(uid)` call.
- `mutate_auth()` wrapper for all auth writes — deferred to Phase 36+.
- Caching `require_admin` results per-request — premature.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RBAC-01 | Authenticated user has `user_id` available via `Depends(current_user)` in every route; cookie session payload extends to include `uid`; admin is only user, no observable behaviour change | D-03/D-04/D-05 extend `_make_session_cookie` + `_try_cookie`; `web/dependencies.py` `current_user_id` factory |
| RBAC-02 | Admin-only routes under `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` sub-router; startup invariant test walks `app.routes` and asserts every `/admin/*` path has `require_admin` in dependency chain | Verified: `include_router` flattens routes into `app.routes` as flat `APIRoute` objects with `.dependencies`; no Mount wrapping |
</phase_requirements>

---

## Summary

Phase 35 is a pure infrastructure phase with zero observable behaviour change for the admin. It wires `user_id` into every authenticated request via `request.state.user_id` (set in middleware) and exposes it declaratively via `Depends(current_user_id)` in `web/dependencies.py`. Admin-only routes move to a sub-router with `require_admin` baked in at mount time.

The codebase is in a clean state for this work. The existing `AuthMiddleware._try_cookie` returns `True/False` but does NOT currently set `request.state.user_id` — that is the primary extension point. The `_make_session_cookie(uname)` function currently serializes `{'u': uname, 'iat': ...}` — it needs `uid` added. The `auth_store` package is fully split and exposes `get_user(uid)` as the lookup pattern for `require_admin`; `get_user_by_email` is new.

**Key architectural fact verified by live test:** `app.include_router(router)` flattens sub-router routes into `app.routes` as plain `APIRoute` objects — NOT wrapped in a `Mount`. Route-level `.dependencies` carries the router-level `dependencies=[Depends(require_admin)]` injected at registration time. The startup invariant test can walk `app.routes` in a flat loop; no recursion needed.

**Critical uid format note:** `auth_store` uses `uuid4().hex` UIDs (32-char hex strings). The state_manager uses `u_admin_marc` as the admin's state bucket key. These are DIFFERENT namespaces. The `require_admin` dependency reads from `auth_store.get_user(uid)` — the uid in the cookie payload must match what is stored in `auth.json users[]`. The admin is NOT in `auth.json users[]` yet (current `auth.json` is schema_version=1, no users). The backward-compat shim (D-04) handles the grace period.

**Primary recommendation:** Implement in strict dependency order — (1) `get_user_by_email` in auth_store, (2) extend `_make_session_cookie` + `_try_cookie`, (3) create `web/dependencies.py`, (4) create `web/routes/admin/`, (5) wire in `web/app.py`, (6) tests. No step depends on anything other than the previous.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `user_id` resolution from signed cookie | Middleware (`web/middleware/auth.py`) | — | Single enforcement chokepoint; D-01 comment in auth.py |
| `user_id` propagation to route handlers | FastAPI Depends (`web/dependencies.py`) | — | `request.state.*` is the standard FastAPI per-request context mechanism |
| Admin role verification | API/Backend (`web/dependencies.py` `require_admin`) | `auth_store` (reads role) | Live role check per request — not cached, authoritative |
| Admin route gate | Sub-router mount (`web/routes/admin/__init__.py`) | — | Gate set at mount time, not per-route; prevents future routes from missing it |
| `uid` lookup by email | auth_store (`_users.py`) | — | auth_store owns all auth.json reads |

---

## Standard Stack

### Core (all existing — no new packages)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | existing | `APIRouter`, `Depends`, `HTTPException` | Already the web framework |
| starlette | existing | `Request`, `BaseHTTPMiddleware` | FastAPI dependency |
| itsdangerous | existing | Cookie signing/verification | Already used in `auth.py` + `totp/` |
| auth_store | internal | `get_user`, new `get_user_by_email` | Internal auth registry |

No new packages required. [VERIFIED: codebase grep]

---

## Architecture Patterns

### System Architecture Diagram

```
Browser request
  |
  v
AuthMiddleware._try_cookie()
  | Decode tsi_session
  | D-05: payload has uid? → request.state.user_id = payload['uid']
  | D-04: uid absent/None? → get_user_by_email(payload['u'])
  |         resolved? → request.state.user_id = resolved_uid
  |         not found? → request.state.user_id = None
  v
Route Handler
  | Depends(current_user_id) → reads request.state.user_id
  |   None? → raise HTTPException(403)
  |   str? → return uid to handler
  |
  | (for /admin/* routes)
  | Depends(require_admin) [injected at router mount time]
  |   get_user(uid) → check role == 'admin'
  |   non-admin or None? → raise HTTPException(403)
  |   admin? → return uid
  v
Handler body executes with user_id available
```

### Recommended File Structure

```
web/
├── dependencies.py          # NEW — current_user_id + require_admin factories
├── routes/
│   ├── admin/
│   │   └── __init__.py     # NEW — APIRouter(prefix="/admin", ...) + GET /admin/ping
│   └── [existing routes unchanged]
├── middleware/
│   └── auth.py             # EXTEND — _try_cookie sets request.state.user_id
└── app.py                  # EXTEND — include_router(admin_router) before add_middleware

web/routes/totp/__init__.py  # EXTEND — _make_session_cookie adds uid
auth_store/
├── _users.py               # EXTEND — add get_user_by_email
└── __init__.py             # EXTEND — re-export get_user_by_email

tests/
└── test_web_admin.py        # NEW — TestAdminRouteInvariant + 403-sweep
```

### Pattern 1: `_try_cookie` extension (D-04/D-05)

Current shape (lines 228–276 of `web/middleware/auth.py`):
```python
def _try_cookie(self, request: Request) -> bool:
    token = request.cookies.get(_SESSION_COOKIE_NAME)
    if token:
        try:
            self._session_serializer.loads(token, max_age=_SESSION_MAX_AGE_SECONDS)
            return True  # <-- currently returns without setting user_id
        ...
```

Phase 35 extension:
```python
def _try_cookie(self, request: Request) -> bool:
    token = request.cookies.get(_SESSION_COOKIE_NAME)
    if token:
        try:
            payload = self._session_serializer.loads(token, max_age=_SESSION_MAX_AGE_SECONDS)
            uid = payload.get('uid') if isinstance(payload, dict) else None
            if uid is None:
                # Backward-compat shim (D-04): old cookie or uid=None
                from auth_store import get_user_by_email
                uname = payload.get('u', '') if isinstance(payload, dict) else ''
                row = get_user_by_email(uname)
                uid = row['uid'] if row else None
            request.state.user_id = uid  # D-05: direct on happy path
            return True
        except SignatureExpired:
            pass
        except BadSignature:
            pass
    # tsi_trusted path follows (no user_id on trusted path in this phase)
    ...
```

[VERIFIED: live codebase read of `web/middleware/auth.py`]

### Pattern 2: `_make_session_cookie` extension (D-03)

Current (line 98–100 of `web/routes/totp/__init__.py`):
```python
def _make_session_cookie(uname: str) -> str:
    token = session_serializer.dumps({'u': uname, 'iat': int(time.time())})
    return f'tsi_session={token}{_COOKIE_ATTRS_CREATE_SESSION}'
```

Phase 35 signature change:
```python
def _make_session_cookie(uname: str, uid: str | None = None) -> str:
    token = session_serializer.dumps({'u': uname, 'uid': uid, 'iat': int(time.time())})
    return f'tsi_session={token}{_COOKIE_ATTRS_CREATE_SESSION}'
```

Callers: `post_enroll` (line 204) and `post_verify` (line 248) — both pass `username` (the WEB_AUTH_USERNAME value). Phase 35 threads `uid` through from a `get_user_by_email(username)` lookup immediately prior.

[VERIFIED: live codebase read of `web/routes/totp/__init__.py`]

### Pattern 3: `web/dependencies.py` factories (D-07)

```python
# web/dependencies.py
from fastapi import Request, HTTPException
from auth_store import get_user

def current_user_id(request: Request) -> str:
    uid = getattr(request.state, 'user_id', None)
    if uid is None:
        raise HTTPException(status_code=403, detail='authentication required')
    return uid

def require_admin(request: Request) -> str:
    uid = getattr(request.state, 'user_id', None)
    if uid is None:
        raise HTTPException(status_code=403, detail='admin required')
    row = get_user(uid)
    if row is None or row.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='admin required')
    return uid
```

Hex boundary: `web/dependencies.py` imports `auth_store` — this is an adapter hex, not pure hex. `auth_store` is already imported in `web/middleware/auth.py` (local import pattern). [VERIFIED: `TestWebHexBoundary.FORBIDDEN_FOR_WEB` does NOT include `auth_store`]

### Pattern 4: Sub-router registration (D-08/D-09)

```python
# web/routes/admin/__init__.py
from fastapi import APIRouter, Depends
from web.dependencies import require_admin

router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])

@router.get('/ping')
def ping():
    return {'ok': True}
```

```python
# web/app.py — inside create_app(), BEFORE add_middleware line
from web.routes.admin import router as admin_router
application.include_router(admin_router)
```

[VERIFIED: `include_router` flattens routes into `app.routes` as `APIRoute` with `.dependencies` carrying the router-level gate — confirmed via live Python execution]

### Pattern 5: Startup invariant test — walking `app.routes` (D-10)

**Key verified fact:** After `include_router`, admin routes appear as flat `APIRoute` objects in `app.routes`. No `Mount` wrapping. Route-level `.dependencies` carries the router-level `dependencies` list injected at registration.

```python
# tests/test_web_admin.py
def test_admin_routes_have_require_admin_dependency():
    from web.app import create_app
    from web.dependencies import require_admin
    from fastapi.routing import APIRoute
    app = create_app()
    admin_routes = [
        r for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith('/admin/')
    ]
    assert admin_routes, 'no /admin/* routes found'
    for route in admin_routes:
        dep_fns = [d.dependency for d in route.dependencies]
        assert require_admin in dep_fns, (
            f'{route.path} missing require_admin in {dep_fns}'
        )
```

[VERIFIED: live Python execution — `app.routes` after `include_router` contains flat `APIRoute` objects with `.dependencies`]

### Pattern 6: `get_user_by_email` implementation (D-01)

Mirror of existing `get_user(uid)` — linear scan, same pattern:

```python
def get_user_by_email(email: str, path: Path | None = None) -> dict | None:
    '''Return the User dict matching email, or None if not found.'''
    data = load_auth(path=path)
    for row in data.get('users', []):
        if row.get('email') == email:
            return row
    return None
```

[VERIFIED: `get_user` at line 125 of `auth_store/_users.py`]

### Anti-Patterns to Avoid

- **Reading `request.cookies` directly in route handlers:** Phase 35 explicitly removes this — all user context comes from `request.state.user_id` via middleware. No route handler should call `request.cookies.get('tsi_session')`.
- **Per-route `dependencies=` lists for admin gates:** Defeats the point of sub-router mounting. New admin routes go on `router`, not on `application`.
- **Calling `get_user()` in `_try_cookie` on happy path:** D-05 explicitly forbids extra auth.json reads on the happy path — only the shim (D-04) does a lookup.
- **Importing `web.dependencies` at module top-level in `web/middleware/auth.py`:** Circular import risk. Auth middleware sets state; dependencies read it. Dependencies should never be imported by middleware.
- **Registering admin router AFTER `add_middleware`:** Won't cause a bug (middleware runs regardless of registration order) but contradicts the established pattern and may confuse future readers.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request-scoped auth context | Thread-local / global cache | `request.state.user_id` | Starlette's per-request state is the correct mechanism |
| Router-level auth gate | Manual `if not is_admin: raise` in every handler | `dependencies=[Depends(require_admin)]` at router mount | Gate set once; future routes inherit automatically |
| Role checking | String comparison in route handlers | `require_admin` dependency | Centralised; authoritative; live-reads role on every request |

---

## Common Pitfalls

### Pitfall 1: `_try_cookie` currently returns bool only — extension must also handle `tsi_trusted` path

**What goes wrong:** The `_try_cookie` function handles BOTH `tsi_session` AND `tsi_trusted` cookies (lines 246–276). Currently neither path sets `request.state.user_id`. The Phase 35 extension must set it in the `tsi_session` path. The `tsi_trusted` path does NOT have a uid in the payload — it has a device uuid. D-04/D-05 only specify the session cookie path.

**Why it happens:** The trusted-device cookie was designed before user_id propagation was needed. Its payload is `{'uuid': ..., 'iat': ...}` — no `u` or `uid`.

**How to avoid:** For `tsi_trusted` path: either (a) look up the user via `get_trusted_device(uuid_value)` to get any associated user fields, or (b) leave `request.state.user_id` at `None` for trusted-device sessions in Phase 35 (since admin is the only user, and require_admin will read their uid from auth.json anyway — but `current_user_id` will raise 403). The CONTEXT.md decisions only specify session-cookie behaviour; trusted-device uid propagation is Claude's discretion.

**Warning signs:** Tests for `/admin/ping` pass via session cookie but fail via trusted-device cookie even though admin is logged in.

### Pitfall 2: WEB_AUTH_USERNAME is NOT necessarily the admin's email in auth.json

**What goes wrong:** `get_user_by_email(payload.get('u', ''))` — the `'u'` field carries `WEB_AUTH_USERNAME` (e.g. `'marc'`). But `auth.json users[]` stores users by `email` field (e.g. `'marc@example.com'`). Until the admin is bootstrapped into `users[]`, this lookup will always return `None` (shim sets `user_id=None`).

**Why it happens:** The session cookie was designed before multi-user. `WEB_AUTH_USERNAME` is a login-form credential, not an email address. Phase 36 will likely enforce email-shaped usernames or a separate bootstrapping step.

**How to avoid:** The shim (D-04) already handles this: `None` is set, and `require_admin` raises 403. The admin cannot use admin-gated routes until they are bootstrapped into `auth.json users[]` with `role='admin'`. This is the intentional design. Document this as expected behaviour in the test setup (use `isolated_auth_json` + `create_user({'email': VALID_USERNAME, 'role': 'admin'})` in tests that exercise the happy path).

**Warning signs:** `require_admin` always raises 403 in integration tests even with a valid session cookie.

### Pitfall 3: `_try_cookie` sets `request.state.user_id` but only on success paths — middleware must not clobber it on later paths

**What goes wrong:** `_try_cookie` returns early on success. If the session token is expired/invalid and falls through to `_try_trusted`, and then `_try_trusted` grants access, `request.state.user_id` may not be set (because the session path failed before setting it).

**How to avoid:** Set `request.state.user_id = None` at the top of `dispatch()` as a default before any auth path runs. Then each path that resolves a uid sets it. Absence is unambiguous.

### Pitfall 4: Hex boundary — `web/dependencies.py` importing `auth_store` is allowed, but must use local import if there's any circular-import risk

**What goes wrong:** `web/dependencies.py` is a new file. If it imports `auth_store` at module top-level AND `auth_store` transitively imports anything from `web/`, you have a circular import.

**How to avoid:** `auth_store` does NOT import from `web/` (verified — it only imports stdlib, fcntl, json, etc.). Top-level import of `auth_store` in `web/dependencies.py` is safe. Confirmed by existing pattern: `web/middleware/auth.py` already imports `auth_store` inside method bodies as a style choice (local import for hex boundary clarity), not due to circular-import necessity.

**TestWebHexBoundary impact:** `web/dependencies.py` will be scanned by `test_web_modules_do_not_import_hex_core`. It MUST NOT import `signal_engine`, `data_fetcher`, or `main`. `auth_store` is not in `FORBIDDEN_FOR_WEB`. No change to the boundary guard set required.

### Pitfall 5: `APIRouter` vs `app.include_router` — which `dependencies` list appears on the route

**What goes wrong:** Confusion about whether `router = APIRouter(dependencies=[...])` puts dependencies on the router object OR on each registered `APIRoute` object after `include_router`.

**Verified fact:** After `app.include_router(router)`, each `APIRoute` in `app.routes` carries the router-level dependencies in its `.dependencies` list. The invariant test can check `route.dependencies` directly. [VERIFIED: live Python execution]

### Pitfall 6: `last_login` field — User TypedDict does not have it yet

**What goes wrong:** If `update_last_login(uid)` is added to the session-issue path and calls `save_auth(data)` where `data['users'][i]` is a `User` TypedDict, mypy/pyright will flag `last_login` as an unknown field.

**How to avoid:** Either extend the `User` TypedDict in `auth_store/_schema.py` to include `last_login: str | None` before calling it, or leave it deferred (CONTEXT.md marks it as Claude's discretion).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (see CLAUDE.md) |
| Config file | `pytest.ini` or `pyproject.toml` (existing) |
| Quick run command | `.venv/bin/pytest -x --tb=short tests/test_web_admin.py tests/test_web_auth_middleware.py tests/test_auth_store_users.py` |
| Full suite command | `.venv/bin/pytest -x --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RBAC-01 | Session cookie payload includes `uid` field | unit | `.venv/bin/pytest -x tests/test_web_routes_totp.py -k "session_cookie"` | exists (extend) |
| RBAC-01 | `_try_cookie` sets `request.state.user_id` from payload | unit | `.venv/bin/pytest -x tests/test_web_auth_middleware.py -k "user_id"` | exists (extend) |
| RBAC-01 | Shim: old cookie (no uid) resolves via `get_user_by_email` | unit | `.venv/bin/pytest -x tests/test_web_auth_middleware.py -k "shim"` | create |
| RBAC-01 | `current_user_id` raises 403 when `request.state.user_id` is None | unit | `.venv/bin/pytest -x tests/test_web_dependencies.py` | create Wave 0 |
| RBAC-02 | Every `/admin/*` route has `require_admin` in dependency chain | unit (startup invariant) | `.venv/bin/pytest -x tests/test_web_admin.py -k "invariant"` | create Wave 0 |
| RBAC-02 | Non-admin session gets 403 on every `/admin/*` path | integration | `.venv/bin/pytest -x tests/test_web_admin.py -k "403"` | create Wave 0 |
| RBAC-02 | Admin session gets 200 on `GET /admin/ping` | integration | `.venv/bin/pytest -x tests/test_web_admin.py -k "ping"` | create Wave 0 |
| RBAC-01 | `get_user_by_email` finds user by email field | unit | `.venv/bin/pytest -x tests/test_auth_store_users.py -k "by_email"` | create |

### Unit Tests (pure logic)

- `test_get_user_by_email_returns_row` — matching email found
- `test_get_user_by_email_returns_none_when_not_found` — empty users[]
- `test_get_user_by_email_returns_none_wrong_email` — no match
- `test_make_session_cookie_includes_uid` — payload deserializes with `uid` key
- `test_make_session_cookie_uid_none` — `uid=None` round-trips cleanly
- `test_current_user_id_raises_403_when_user_id_none` — dependency raises
- `test_current_user_id_returns_uid_when_set` — happy path
- `test_require_admin_raises_403_when_user_id_none`
- `test_require_admin_raises_403_when_role_is_ff`
- `test_require_admin_returns_uid_when_admin`

### Integration Tests (route/middleware behaviour)

- `test_try_cookie_sets_user_id_from_payload` — new uid in cookie → `request.state.user_id` set
- `test_try_cookie_shim_resolves_via_email` — old cookie (no uid) → shim lookup
- `test_try_cookie_shim_sets_none_when_email_not_found` — shim fallback
- `test_admin_ping_returns_200_with_admin_session`
- `test_admin_ping_returns_403_with_no_session`
- `test_admin_ping_returns_403_with_header_auth` (D-06)
- Parametrized `test_non_admin_gets_403_on_all_admin_paths`
- `test_admin_routes_have_require_admin_dependency` (startup invariant)
- `test_header_auth_sets_user_id_none` (D-06 regression)

### Coverage Gaps (what could easily be missed)

1. **`tsi_trusted` cookie + `user_id`:** The trusted-device path grants access but its uid propagation is unspecified in CONTEXT.md decisions. If left as `user_id=None`, admin using trusted device cannot hit `/admin/ping` — likely wrong. Test this explicitly.

2. **Old cookie (no `uid` key, valid `u`) when `auth.json users[]` is empty:** The shim must return `user_id=None`, not crash. Test with isolated empty auth.json.

3. **`current_user_id` called on PUBLIC_PATHS routes:** Public paths bypass AuthMiddleware entirely — `request.state.user_id` will be unset (AttributeError on `request.state.user_id`). `getattr(request.state, 'user_id', None)` in the dependency handles this, but must be tested.

4. **`TestWebHexBoundary` still passes after adding `web/dependencies.py`:** The new file must not import from `FORBIDDEN_FOR_WEB`. Run the boundary test explicitly after adding the file.

5. **`web/routes/admin/__init__.py` must NOT import `signal_engine`, `data_fetcher`, or `main`:** Self-evident but easy to miss if copying boilerplate.

### Landmines (non-obvious gotchas)

1. **`_try_cookie` returns True on `tsi_trusted` path even when `user_id` is not set:** Currently the trusted-device path calls `update_last_seen(uuid_value)` and returns `True` without any uid resolution. After Phase 35, the code that calls `Depends(require_admin)` will find `request.state.user_id = None` (from the default set at dispatch top) and raise 403 — even for a valid admin trusted-device session. This is a behaviour change that tests may not catch if `tsi_trusted` tests are not updated.

2. **`session_serializer.loads()` returns the raw payload — type varies:** `_validate_session_cookie` already handles this (line 77: `return payload if isinstance(payload, dict) else {'_': payload}`). The `_try_cookie` extension must do the same isinstance check before calling `.get('uid')`.

3. **`include_router` order vs `add_middleware` order:** The CONTEXT.md says "registered BEFORE AuthMiddleware". This is correct — `add_middleware` is LAST. Admin router must be `include_router`'d before the `add_middleware(AuthMiddleware, ...)` line. Middleware and route registration are independent; the order comment in `web/app.py` (D-06) already explains this correctly.

4. **`require_admin` calls `get_user(uid)` with `uid=None` if the admin has a legacy cookie and `users[]` is empty:** `get_user(None)` — the linear scan checks `row.get('uid') == None`. If any row has a None uid (shouldn't happen per schema), this would be a false positive. `get_user` is safe — it returns `None` if no match found. `require_admin` must handle `get_user(None)` returning `None` gracefully (it does, since `row is None` → 403).

5. **`VALID_USERNAME = 'marc'` in conftest.py is NOT an email address.** Tests that exercise `get_user_by_email(VALID_USERNAME)` on an isolated auth.json with a user created as `create_user({'email': VALID_USERNAME, 'role': 'admin'})` will work. But if the test creates the user with `email='marc@example.com'` and then looks up by `'marc'`, the lookup returns `None`. Test fixtures must align username with email.

---

## Runtime State Inventory

> Phase 35 is not a rename/refactor phase — this section is SKIPPED.

---

## Environment Availability

> Step 2.6: SKIPPED — Phase 35 is purely code/config changes. No external tools, services, or CLIs beyond the project's own virtualenv.

---

## Open Questions (RESOLVED)

1. **`tsi_trusted` + `user_id` propagation**
   - What we know: `tsi_trusted` payload is `{'uuid': ..., 'iat': ...}` — no `u` or `uid` field. Currently `_try_cookie` returns `True` on trusted path without setting any user state.
   - What's unclear: Should Phase 35 also propagate uid for trusted-device sessions? If so, how (look up device → user mapping)?
   - Recommendation: Trusted devices are not user-specific in Phase 34 (only one user). For Phase 35, set `request.state.user_id = None` on the trusted path (same as header auth D-06). Admin trusting a device will need to re-log-in after Phase 35 deploys if they want to hit `/admin/ping`. This is acceptable for the grace period.
   - **RESOLVED (cross-AI review consensus + Plan 02):** Option B adopted — trusted-device path intentionally leaves `user_id=None`; `logger.warning` emitted on each trusted-device dispatch; `test_trusted_device_admin_access_returns_403` regression test documents the intentional 403 as accepted behaviour. Trusted-device→admin access is a known limitation for the Phase 35 grace period (see 35-02-PLAN.md).

2. **Admin bootstrap timing**
   - What we know: `auth.json` currently has `schema_version=1` and no `users[]`. The admin user must be in `users[]` for `require_admin` to return their uid from `get_user()`.
   - What's unclear: Is there a bootstrap mechanism to create the admin user in `auth.json users[]`? Phase 34 added `create_user()` but no automatic admin bootstrap.
   - Recommendation: Phase 35 plan should include a note that the admin CANNOT access `/admin/ping` until they (a) log in once after Phase 35 deploys (creates a session with `uid=None`), AND (b) are bootstrapped into `auth.json users[]` (via `create_user({'email': WEB_AUTH_USERNAME, 'role': 'admin'})`). The invariant test must be set up with a pre-populated `isolated_auth_json` fixture.
   - **RESOLVED (Plan 02 + Plan 05):** D-04 shim covers the bootstrap gap — existing cookies without `uid` resolve uid via `get_user_by_email(u)` and log the shim trigger. Plan 05's `test_admin_with_uid_no_resolved_user_cannot_pass_require_admin` verifies fail-closed behaviour when uid resolution fails. Test fixtures use `isolated_auth_json` with pre-populated admin user (see 35-05-PLAN.md).

---

## Sources

### Primary (HIGH confidence — verified by live codebase reads)

- `web/middleware/auth.py` — `_try_cookie` exact implementation (lines 228–276); `_try_header` (lines 290–297); `dispatch` flow (lines 168–226)
- `web/routes/totp/__init__.py` — `_make_session_cookie` (lines 98–100); `post_verify` cookie assembly (lines 247–276)
- `web/app.py` — `create_app()` full route registration order (lines 130–205); middleware registration comment
- `auth_store/_users.py` — `get_user(uid)` pattern (lines 125–131); `create_user` uid format (line 114)
- `auth_store/__init__.py` — full `__all__` export list; re-export conventions
- `auth_store/_schema.py` — `User` TypedDict fields; `SCHEMA_VERSION = 2`
- `tests/test_web_healthz.py` — `TestWebHexBoundary.FORBIDDEN_FOR_WEB` (lines 208–211)
- `tests/conftest.py` — `isolated_auth_json` fixture (lines 138–159); `valid_cookie_token` fixture (lines 92–101)

### Secondary (MEDIUM confidence — live Python execution)

- FastAPI `include_router` flattening behaviour: verified by running Python in-process — `app.routes` after `include_router` contains flat `APIRoute` objects (not `Mount`), each carrying router-level `.dependencies`
- Middleware ordering: verified — `request.state` is set by middleware BEFORE `Depends()` runs

### Tertiary (ASSUMED)

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `tsi_trusted` cookie path should set `user_id=None` in Phase 35 | Pitfall 1, Open Q 1 | Admin using trusted device cannot hit admin routes — user-facing issue, but short-lived during grace period |
| A2 | WEB_AUTH_USERNAME is not an email-shaped string in production (it's 'marc') | Pitfall 2 | If it IS email-shaped and matches auth.json user, the shim works on day 1 |

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages, all existing
- Architecture: HIGH — verified by live codebase reads and Python execution
- Pitfalls: HIGH — identified from direct code tracing, confirmed by execution

**Research date:** 2026-05-13
**Valid until:** 2026-06-12 (stable codebase, 30-day estimate)
