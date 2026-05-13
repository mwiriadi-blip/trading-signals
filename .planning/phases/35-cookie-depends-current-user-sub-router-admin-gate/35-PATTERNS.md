# Phase 35: Cookie + Depends(current_user) + Sub-Router Admin Gate — Pattern Map

**Mapped:** 2026-05-13
**Files analyzed:** 8
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `auth_store/_users.py` | service / auth store | CRUD (read) | `auth_store/_users.py::get_user` | exact — same file, same linear scan pattern |
| `auth_store/__init__.py` | config / re-export | — | `auth_store/__init__.py` existing `__all__` + import blocks | exact — same file, same re-export convention |
| `web/routes/totp/__init__.py` | route handler | request-response | `web/routes/totp/__init__.py::_make_session_cookie` | exact — same function, extend signature |
| `web/middleware/auth.py` | middleware | request-response | `web/middleware/auth.py::_try_cookie` + `_try_header` | exact — same functions, extend bodies |
| `web/dependencies.py` | middleware / dependency | request-response | `web/routes/devices.py::_require_cookie_session_or_403` pattern | role-match — same guard+403 idiom |
| `web/routes/admin/__init__.py` | route / sub-router | request-response | `web/routes/totp/__init__.py` (package `__init__`) | role-match — same package-init router pattern |
| `web/app.py` | config / wiring | — | `web/app.py::create_app` existing `include_router` / `register` calls | exact — same file, same registration order |
| `tests/test_web_admin.py` | test | — | `tests/test_web_auth_middleware.py`, `tests/test_auth_store_users.py` | role-match — same class-per-concern + fixture style |

---

## Pattern Assignments

### `auth_store/_users.py` — add `get_user_by_email`

**Analog:** `auth_store/_users.py::get_user` (lines 125–131)

**Exact pattern to mirror** (lines 125–131):
```python
def get_user(uid: str, path: Path | None = None) -> dict | None:
  '''Return the User dict for uid, or None if not found.'''
  data = load_auth(path=path)
  for row in data.get('users', []):
    if row.get('uid') == uid:
      return row
  return None
```

**New function — copy pattern exactly, change field name:**
```python
def get_user_by_email(email: str, path: Path | None = None) -> dict | None:
  '''Return the User dict matching email, or None if not found.'''
  data = load_auth(path=path)
  for row in data.get('users', []):
    if row.get('email') == email:
      return row
  return None
```

Place immediately after `get_user` (line 131). No imports needed — `load_auth` already imported at top of file (line 18).

---

### `auth_store/__init__.py` — re-export `get_user_by_email`

**Analog:** `auth_store/__init__.py` lines 60–68 (`from auth_store._users import ...`) and lines 99–137 (`__all__`).

**Import block to extend** (lines 60–68):
```python
from auth_store._users import (  # noqa: E402
  InviteAlreadyConsumed,
  InviteExpired,
  create_user,
  consume_and_create_user,
  get_user,
  list_users,
  mint_invite_token,
  set_user_disabled,
)
```
Add `get_user_by_email,` to this import block.

**`__all__` to extend** — add `'get_user_by_email'` alongside `'get_user'` in the `__all__` list (currently line 130 area).

**Critical ordering note:** `DEFAULT_AUTH_PATH` must remain bound BEFORE any daughter-module import — do not reorder the top of this file (documented in the module docstring, lines 1–14).

---

### `web/routes/totp/__init__.py` — extend `_make_session_cookie`

**Analog:** `web/routes/totp/__init__.py::_make_session_cookie` (lines 98–100).

**Current function** (lines 98–100):
```python
def _make_session_cookie(uname: str) -> str:
  token = session_serializer.dumps({'u': uname, 'iat': int(time.time())})
  return f'tsi_session={token}{_COOKIE_ATTRS_CREATE_SESSION}'
```

**Phase 35 extension — new signature:**
```python
def _make_session_cookie(uname: str, uid: str | None = None) -> str:
  token = session_serializer.dumps({'u': uname, 'uid': uid, 'iat': int(time.time())})
  return f'tsi_session={token}{_COOKIE_ATTRS_CREATE_SESSION}'
```

**Callers to update:**
- `post_enroll` (line 204): `_make_session_cookie(username)` → add `get_user_by_email(username)` lookup immediately prior, pass uid.
- `post_verify` (line 248): same pattern.

**Import to add** at the call site (local import, matching the existing local-import style in this file, e.g. lines 128–129, 184):
```python
import auth_store
row = auth_store.get_user_by_email(username)
uid = row['uid'] if row else None
```
Then call `_make_session_cookie(username, uid=uid)`.

**`_validate_session_cookie`** (lines 67–81) already handles isinstance check (`return payload if isinstance(payload, dict) else {'_': payload}`) — no change needed.

---

### `web/middleware/auth.py` — extend `_try_cookie` and `_try_header`

**Analog:** `web/middleware/auth.py::_try_cookie` (lines 228–276) and `_try_header` (lines 290–297).

**dispatch() — add default at top of auth section** (after PUBLIC_PATHS check, before `_try_cookie` call, current line 207):
```python
# D-04/D-05/D-06: default user_id before any auth path. Each path that
# resolves a uid overwrites this. Absence is unambiguous.
request.state.user_id = None
```
Insert this immediately before `if self._try_cookie(request):` (line 207).

**_try_cookie Path 1 — tsi_session extension** (lines 246–255, current):
```python
# Path 1 — tsi_session (Plan 01)
token = request.cookies.get(_SESSION_COOKIE_NAME)
if token:
  try:
    self._session_serializer.loads(token, max_age=_SESSION_MAX_AGE_SECONDS)
    return True
  except SignatureExpired:
    pass  # fall through to tsi_trusted
  except BadSignature:
    pass  # fall through to tsi_trusted
```

**Replace with Phase 35 extension:**
```python
# Path 1 — tsi_session (Phase 35 D-04/D-05)
token = request.cookies.get(_SESSION_COOKIE_NAME)
if token:
  try:
    payload = self._session_serializer.loads(token, max_age=_SESSION_MAX_AGE_SECONDS)
    uid = payload.get('uid') if isinstance(payload, dict) else None
    if uid is None:
      # D-04: backward-compat shim — old cookie or uid=None
      from auth_store import get_user_by_email
      uname = payload.get('u', '') if isinstance(payload, dict) else ''
      row = get_user_by_email(uname)
      uid = row['uid'] if row else None
    request.state.user_id = uid  # D-05: direct on happy path
    return True
  except SignatureExpired:
    pass  # fall through to tsi_trusted
  except BadSignature:
    pass  # fall through to tsi_trusted
```

**Local import pattern** (`from auth_store import get_user_by_email`) mirrors the existing local import on line 268 (`from auth_store import update_last_seen`) — same hex-boundary style, inside method body.

**_try_header** (lines 290–297) — no body change needed. The `request.state.user_id = None` default set in `dispatch()` before `_try_cookie` covers the header-auth path automatically (D-06). `_try_header` does not set user_id.

---

### `web/dependencies.py` — NEW FILE

**Analog:** `web/routes/devices.py` guard pattern (helper raises 403 on non-cookie session). Also mirrors the local-import style in `web/middleware/auth.py`.

**Imports pattern** — top-level import is safe (`auth_store` does not import from `web/`):
```python
from fastapi import HTTPException, Request
from auth_store import get_user
```

**`current_user_id` factory (D-07):**
```python
def current_user_id(request: Request) -> str:
  uid = getattr(request.state, 'user_id', None)
  if uid is None:
    raise HTTPException(status_code=403, detail='authentication required')
  return uid
```
`getattr` with default handles public-path requests where `request.state.user_id` was never set by middleware (coverage gap noted in RESEARCH.md).

**`require_admin` factory (D-07):**
```python
def require_admin(request: Request) -> str:
  uid = getattr(request.state, 'user_id', None)
  if uid is None:
    raise HTTPException(status_code=403, detail='admin required')
  row = get_user(uid)
  if row is None or row.get('role') != 'admin':
    raise HTTPException(status_code=403, detail='admin required')
  return uid
```

**Hex boundary:** `web/dependencies.py` is an adapter hex. `auth_store` is NOT in `FORBIDDEN_FOR_WEB` (verified — `tests/test_web_healthz.py::TestWebHexBoundary.FORBIDDEN_FOR_WEB` lines 208–211 only forbids `signal_engine`, `data_fetcher`, `main`). Do NOT import `signal_engine`, `data_fetcher`, or `main`.

---

### `web/routes/admin/__init__.py` — NEW FILE

**Analog:** `web/routes/totp/__init__.py` for package `__init__` structure. No existing `APIRouter` sub-router in the codebase — this is the first. Pattern from RESEARCH.md is authoritative.

**Full file pattern:**
```python
'''Phase 35 — admin sub-router.

All routes on this router require admin role via require_admin dependency
injected at mount time (D-08). New admin routes: register on `router`,
not on `application` directly. The gate is inherited automatically.
'''
from fastapi import APIRouter, Depends
from web.dependencies import require_admin

router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])


@router.get('/ping')
def ping():
  '''D-09: non-vacuous startup invariant target. Returns 200 {"ok": true}.'''
  return {'ok': True}


__all__ = ['router']
```

**2-space indent** — matches CLAUDE.md convention throughout.

---

### `web/app.py` — register admin router

**Analog:** `web/app.py::create_app()` lines 163–181 (existing route registration block).

**Import to add** at top of file with other route imports (lines 40–50):
```python
from web.routes.admin import router as admin_router
```

**Registration to add** inside `create_app()`, immediately before the `application.add_middleware(AuthMiddleware, ...)` line (line 194). Following the established comment pattern:
```python
# Phase 35 D-08: admin sub-router. Registered before add_middleware per D-06
# comment above. Gate (require_admin) is injected at mount time — all future
# routes on this router inherit it automatically.
application.include_router(admin_router)
```

**Critical:** must be BEFORE the `add_middleware(AuthMiddleware, ...)` line. The existing comment on line 192 documents this ordering principle — follow it.

---

### `tests/test_web_admin.py` — NEW FILE

**Analog:** `tests/test_web_auth_middleware.py` for fixture + client patterns; `tests/test_auth_store_users.py` for isolated_auth_json usage; `tests/conftest.py` for `valid_cookie_token` fixture shape.

**File-level imports pattern** (from `test_web_auth_middleware.py` lines 1–20):
```python
import pytest
from fastapi.testclient import TestClient
```

**`_request_with_cookies` helper** — copy verbatim from `tests/test_web_auth_middleware.py` lines 22–32 (sets Cookie header manually, needed because TestClient cookie jar doesn't always propagate). Use or import from that module.

**`isolated_auth_json` fixture** — use from `conftest.py` (line 138). All tests hitting `require_admin` need this to pre-populate `auth.json users[]` with the admin row.

**Admin user setup helper pattern** (mirrors `test_auth_store_users.py::TestUserRegistry` style):
```python
def _make_admin_user(email: str = VALID_USERNAME) -> dict:
  '''Create admin user in isolated auth.json. email must match what the
  session cookie carries as payload["u"] for the shim to resolve.'''
  from auth_store import create_user
  return create_user({'email': email, 'role': 'admin'})
```

**Cookie token with uid pattern** (extend `conftest.py::valid_cookie_token` lines 91–101):
```python
import time
from itsdangerous.url_safe import URLSafeTimedSerializer
# VALID_SECRET, VALID_USERNAME from conftest
serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-session-cookie')
uid = _make_admin_user()['uid']
token = serializer.dumps({'u': VALID_USERNAME, 'uid': uid, 'iat': int(time.time())})
```

**Startup invariant test class (D-10):**
```python
class TestAdminRouteInvariant:
  def test_admin_routes_have_require_admin_dependency(self):
    from fastapi.routing import APIRoute
    from web.app import create_app
    from web.dependencies import require_admin
    app = create_app()
    admin_routes = [
      r for r in app.routes
      if isinstance(r, APIRoute) and r.path.startswith('/admin/')
    ]
    assert admin_routes, 'no /admin/* routes found — invariant is vacuous'
    for route in admin_routes:
      dep_fns = [d.dependency for d in route.dependencies]
      assert require_admin in dep_fns, (
        f'{route.path} missing require_admin in {dep_fns}'
      )
```

**Parametrized 403-sweep class (D-10):**
```python
class TestAdminGate403Sweep:
  @pytest.mark.parametrize('path', ['/admin/ping'])
  def test_non_admin_gets_403_no_session(self, path, monkeypatch):
    ...  # GET path with no cookie → 401 (middleware) or 403 (gate) depending on path
  @pytest.mark.parametrize('path', ['/admin/ping'])
  def test_non_admin_gets_403_header_auth(self, path, monkeypatch):
    ...  # header auth → user_id=None → require_admin raises 403
  @pytest.mark.parametrize('path', ['/admin/ping'])
  def test_ff_user_gets_403(self, path, isolated_auth_json, monkeypatch):
    ...  # ff-role session cookie → require_admin raises 403
```

**Happy path class:**
```python
class TestAdminPing:
  def test_admin_ping_200(self, isolated_auth_json, monkeypatch):
    ...  # admin session cookie + uid in auth.json → 200 {"ok": True}
  def test_admin_ping_403_header_auth(self, isolated_auth_json, monkeypatch):
    ...  # D-06: header auth → user_id=None → 403
```

**`sys.modules.pop('web.app', None)` before `create_app()`** — required pattern for any test creating a fresh app instance (see `conftest.py` line 218, `test_web_auth_middleware.py` line 66). Without it, a previous test's cached module leaks state.

---

## Shared Patterns

### Local import for auth_store inside web/middleware
**Source:** `web/middleware/auth.py` lines 268, 287–288
```python
from auth_store import update_last_seen
# ...
from auth_store import is_uuid_active
```
**Apply to:** `_try_cookie` shim import of `get_user_by_email` — use same local-import-inside-method-body style.

### isinstance guard on cookie payload
**Source:** `web/routes/totp/__init__.py::_validate_session_cookie` (lines 76–77) and `web/middleware/auth.py::_try_cookie` Path 2 (lines 262–263):
```python
payload = self._trusted_serializer.loads(trusted, max_age=_TRUSTED_MAX_AGE_SECONDS)
if isinstance(payload, dict):
  uuid_value = str(payload.get('uuid', ''))
```
**Apply to:** `_try_cookie` Path 1 extension — always guard `payload.get(...)` with `isinstance(payload, dict)`.

### HTTPException(403) guard pattern
**Source:** `web/routes/devices.py` guard helper (E-06 pattern, lines 1–40 docstring describes it).
**Apply to:** `web/dependencies.py` — both `current_user_id` and `require_admin` raise `HTTPException(status_code=403)`, not 401, not 500.

### isolated_auth_json + create_user fixture setup
**Source:** `tests/conftest.py::isolated_auth_json` (lines 138–159); `tests/test_auth_store_users.py::TestUserRegistry` (lines 42–48).
**Apply to:** All `tests/test_web_admin.py` tests that exercise the happy path. Must pre-populate `auth.json users[]` with the admin row BEFORE making the request — `require_admin` reads from auth.json live.

### sys.modules.pop before create_app
**Source:** `tests/test_web_auth_middleware.py` line 66; `tests/conftest.py` line 218.
```python
import sys
sys.modules.pop('web.app', None)
from web.app import create_app
```
**Apply to:** Every test fixture in `test_web_admin.py` that calls `create_app()`.

### autouse credential fixture scope
**Source:** `tests/conftest.py` lines 45–78 (`_set_web_auth_credentials_for_web_tests`).
Files matching `test_web_*.py` get `WEB_AUTH_SECRET`, `WEB_AUTH_USERNAME`, and `OPERATOR_RECOVERY_EMAIL` set automatically. `test_web_admin.py` will match this pattern — no manual `monkeypatch.setenv` calls needed for credentials.

---

## No Analog Found

All files have analogs. No entries.

---

## Metadata

**Analog search scope:** `auth_store/`, `web/middleware/`, `web/routes/`, `web/app.py`, `tests/`
**Files read:** 10
**Pattern extraction date:** 2026-05-13
