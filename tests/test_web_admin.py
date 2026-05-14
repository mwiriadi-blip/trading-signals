'''Phase 35 Plan 03 — web/dependencies.py factories + admin gate tests.

TDD RED: tests for current_user_id and require_admin factories.
Tests assert BOTH HTTPException.status_code AND .detail (--reviews #5).

Wave-0 stub classes: TestAdminSubRouter, TestAdminGate403Sweep, TestAdminPing,
TestAdminRouteInvariant — filled by Plans 04 and 05.

Fixture strategy:
  The autouse fixture _set_web_auth_credentials_for_web_tests in tests/conftest.py
  pre-sets WEB_AUTH_SECRET for this file (name matches test_web_*.py).
  Tests mutating auth.json use the isolated_auth_json fixture from conftest.py.

# --reviews HIGH consensus #2: Phase 35 does NOT migrate existing
# authenticated non-admin route handlers to Depends(current_user_id).
# That migration is Phase 36 (per-user scoping). RBAC-01 is partially
# satisfied this phase -- factory exists, middleware populates user_id,
# admin-gated routes consume the factory. Tests in this file cover
# the admin gate only; tests for /trades, /journal, /dashboard, etc.
# using Depends(current_user_id) belong to Phase 36.
'''
import sys
import time
import types

import pytest
from fastapi import APIRouter, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from itsdangerous.url_safe import URLSafeTimedSerializer

from web.dependencies import (
  _DETAIL_ADMIN_REQUIRED,
  _DETAIL_NOT_AUTHENTICATED,
  current_user_id,
  require_admin,
)
from web.routes.admin import router

from tests.conftest import VALID_SECRET, VALID_USERNAME


def _fake_request(user_id_value, *, missing=False):
  '''Build a fake request-like object with request.state.user_id set.

  If missing=True, request.state has no user_id attribute at all
  (simulates PUBLIC_PATHS where middleware never ran).
  '''
  if missing:
    state = types.SimpleNamespace()
  else:
    state = types.SimpleNamespace(user_id=user_id_value)
  return types.SimpleNamespace(state=state)


def _build_session_cookie(uid, *, username=None, include_uid=True):
  '''Build a signed tsi_session cookie for tests.

  If include_uid=False, omits the uid key to simulate a pre-Phase-35
  legacy cookie shape (only 'u' and 'iat').
  '''
  username = username or VALID_USERNAME
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-session-cookie')
  payload = {'u': username, 'iat': int(time.time())}
  if include_uid:
    payload['uid'] = uid
  return serializer.dumps(payload)


def _walk_routes(routes):
  '''Recursively yield APIRoute objects. Today app.router.routes is flat,
  but this future-proofs the invariant against Phase 36+ Mount or nested
  APIRouter cases. --reviews OpenCode Plan 05 LOW.
  '''
  for r in routes:
    if isinstance(r, APIRoute):
      yield r
    elif hasattr(r, 'routes'):
      yield from _walk_routes(r.routes)


# ---------------------------------------------------------------------------
# TestCurrentUserId
# ---------------------------------------------------------------------------

class TestCurrentUserId:
  def test_returns_uid_when_set(self, monkeypatch):
    monkeypatch.setattr(
      'web.dependencies.get_user',
      lambda uid: {'uid': uid, 'disabled': False},
    )
    req = _fake_request('abc')
    result = current_user_id(req)
    assert result == 'abc'

  def test_raises_403_with_locked_detail_when_user_id_none(self):
    req = _fake_request(None)
    with pytest.raises(HTTPException) as exc:
      current_user_id(req)
    assert exc.value.status_code == 403
    assert exc.value.detail == _DETAIL_NOT_AUTHENTICATED

  def test_raises_403_with_locked_detail_when_user_id_attr_missing(self):
    req = _fake_request(None, missing=True)
    with pytest.raises(HTTPException) as exc:
      current_user_id(req)
    assert exc.value.status_code == 403
    assert exc.value.detail == _DETAIL_NOT_AUTHENTICATED


# ---------------------------------------------------------------------------
# TestRequireAdmin
# ---------------------------------------------------------------------------

class TestRequireAdmin:
  def test_raises_403_with_locked_detail_when_user_id_none(self, isolated_auth_json):
    req = _fake_request(None)
    with pytest.raises(HTTPException) as exc:
      require_admin(req)
    assert exc.value.status_code == 403
    assert exc.value.detail == _DETAIL_ADMIN_REQUIRED

  def test_raises_403_when_user_not_in_auth_json(self, isolated_auth_json):
    req = _fake_request('nonexistent-uid')
    with pytest.raises(HTTPException) as exc:
      require_admin(req)
    assert exc.value.status_code == 403
    assert exc.value.detail == _DETAIL_ADMIN_REQUIRED

  def test_raises_403_when_role_is_ff(self, isolated_auth_json):
    import auth_store
    user = auth_store.create_user({'email': 'ff@x.com', 'role': 'ff'})
    uid = user['uid']
    req = _fake_request(uid)
    with pytest.raises(HTTPException) as exc:
      require_admin(req)
    assert exc.value.status_code == 403
    assert exc.value.detail == _DETAIL_ADMIN_REQUIRED

  def test_returns_uid_when_role_admin(self, isolated_auth_json):
    import auth_store
    user = auth_store.create_user({'email': 'admin@x.com', 'role': 'admin'})
    uid = user['uid']
    req = _fake_request(uid)
    result = require_admin(req)
    assert result == uid

  def test_admin_role_change_takes_effect_immediately(self, isolated_auth_json):
    '''--reviews Codex: live-read property — role change reflected on next call.'''
    import json
    import auth_store
    user = auth_store.create_user({'email': 'admin2@x.com', 'role': 'admin'})
    uid = user['uid']
    req = _fake_request(uid)

    # First call: admin role — succeeds
    result = require_admin(req)
    assert result == uid

    # Mutate role directly in auth.json
    data = json.loads(isolated_auth_json.read_text())
    for row in data['users']:
      if row['uid'] == uid:
        row['role'] = 'ff'
    isolated_auth_json.write_text(json.dumps(data))

    # Second call: role demoted — raises 403
    with pytest.raises(HTTPException) as exc:
      require_admin(req)
    assert exc.value.status_code == 403
    assert exc.value.detail == _DETAIL_ADMIN_REQUIRED


# ---------------------------------------------------------------------------
# TestAdminSubRouter
# ---------------------------------------------------------------------------

class TestAdminSubRouter:
  def test_router_is_apirouter_instance(self):
    '''Verifies that web/routes/admin exposes an APIRouter object, not a plain
    FastAPI app or any other type. FastAPI only accepts APIRouter instances in
    include_router(); wrong type raises at startup.
    '''
    assert isinstance(router, APIRouter)

  def test_router_prefix_is_admin(self):
    '''Verifies APIRouter stores the prefix string verbatim at construction time.
    FastAPI prepends this to all route paths during include_router() — prefix is
    NOT reflected in router.routes entries (pre-include shape has no prefix).
    '''
    assert router.prefix == '/admin'

  def test_router_has_require_admin_dependency(self):
    '''Verifies FastAPI APIRouter(dependencies=...) stores Depends objects with
    .dependency attribute pointing at the callable — needed by Plan 05's startup
    invariant walker which checks `require_admin in [d.dependency for d in
    route.dependencies]` after include_router on the live app.
    '''
    dep_callables = [d.dependency for d in router.dependencies]
    assert require_admin in dep_callables

  def test_router_has_ping_route(self):
    '''Verifies the router carries a GET /admin/ping route. FastAPI bakes the
    router prefix into route.path at construction time (not at include_router
    time), so the pre-include shape is already '/admin/ping'. Plan 05's post-
    include invariant walker also sees '/admin/ping' in app.routes.
    '''
    ping_routes = [
      r for r in router.routes
      if isinstance(r, APIRoute) and r.path == '/admin/ping' and 'GET' in r.methods
    ]
    assert len(ping_routes) == 1

  def test_ping_handler_returns_ok_dict(self):
    '''Verifies the route handler function itself (D-09). Calling it directly
    bypasses FastAPI dependency injection — purely tests the return value.
    '''
    ping_routes = [
      r for r in router.routes
      if isinstance(r, APIRoute) and r.path == '/admin/ping'
    ]
    assert ping_routes
    result = ping_routes[0].endpoint()
    assert result == {'ok': True}

  def test_router_all_exports(self):
    '''Verifies web/routes/admin.__all__ == ['router'] so that
    `from web.routes.admin import *` yields exactly the router object.
    '''
    import web.routes.admin as admin_mod
    assert admin_mod.__all__ == ['router']


# ---------------------------------------------------------------------------
# TestAdminRouteInvariant
#
# Recursive route walker + ordering comment per --reviews OpenCode Plan 05 LOW.
# include_router-before-add_middleware order is a grep-auditability convention
# (Plan 04 comment documents why): middleware applies regardless of order, but
# keeping route-tree mutations before add_middleware groups them cleanly.
# ---------------------------------------------------------------------------

class TestAdminRouteInvariant:
  def test_admin_routes_nonempty(self):
    '''Guards vacuous invariant: at least one /admin/* route must exist.

    If this fails after a refactor, someone removed the admin router from
    create_app() — the require_admin gate is no longer enforced.
    '''
    sys.modules.pop('web.app', None)
    from web.app import create_app
    app = create_app()
    admin_routes = [
      r for r in _walk_routes(app.router.routes)
      if r.path.startswith('/admin/')
    ]
    assert len(admin_routes) >= 1, (
      'No /admin/* routes found — admin_router not wired into create_app()'
    )

  def test_admin_routes_have_require_admin_dependency(self):
    '''Walk app.router.routes recursively; for every /admin/* APIRoute assert
    that require_admin is in its .dependencies chain.

    Recursive walker (_walk_routes) handles APIRoute + Mount + nested router.
    Today app.routes is flat (verified RESEARCH.md), but the recursive form
    future-proofs the invariant against Phase 36+ where Mount wrapping may
    appear per --reviews OpenCode.

    Ordering note: include_router(admin_router) must appear BEFORE
    add_middleware(AuthMiddleware, ...) in create_app() — this is a
    grep-auditability convention, not a functional requirement (Starlette
    middleware wraps the whole dispatch stack regardless of route-registration
    order). The convention keeps route-tree mutations grouped before the
    middleware boundary for review clarity (Phase 35 D-08 + --reviews #4).
    '''
    sys.modules.pop('web.app', None)
    from web.app import create_app
    app = create_app()
    admin_routes = [
      r for r in _walk_routes(app.router.routes)
      if r.path.startswith('/admin/')
    ]
    assert admin_routes, 'No /admin/* routes found — invariant is vacuous'
    for route in admin_routes:
      dep_callables = [d.dependency for d in route.dependencies]
      assert require_admin in dep_callables, (
        f'{route.path} is missing require_admin in dependency chain: {dep_callables}'
      )


# ---------------------------------------------------------------------------
# TestAdminGate403SweepUnauthenticated
#
# No session cookie, no header. Middleware intercepts before require_admin
# (returns 401 for non-browser-navigation requests from TestClient).
# Split from header-auth sweep per --reviews OpenCode/Codex to prevent one
# suite masking regressions in the other.
# ---------------------------------------------------------------------------

class TestAdminGate403SweepUnauthenticated:
  @pytest.mark.parametrize('path', ['/admin/ping'])
  def test_admin_rejects_unauthenticated(self, path):
    '''GET /admin/* with no cookie and no header.

    TestClient does not send Sec-Fetch or Accept: text/html by default, so
    middleware E-02 step 3 returns 401 plain-text (non-browser path). The
    route never runs. Either 401 or 403 is acceptable — both mean "access
    denied". If somehow middleware allows through (regression), require_admin
    must return 403 + JSON body {'detail': _DETAIL_ADMIN_REQUIRED}.
    '''
    sys.modules.pop('web.app', None)
    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get(path)
    assert response.status_code in {401, 403, 302}, (
      f'Expected 401/403/302 for unauthenticated request, got {response.status_code}'
    )
    # If the gate is at require_admin level (403), enforce JSON body schema
    if response.status_code == 403:
      assert response.headers['content-type'].split(';')[0].strip() == 'application/json'
      assert response.json() == {'detail': _DETAIL_ADMIN_REQUIRED}


# ---------------------------------------------------------------------------
# TestAdminGate403SweepHeaderAuth
#
# X-Trading-Signals-Auth header set (no cookie). Middleware grants (header
# valid) but dispatch-top leaves user_id=None, so require_admin raises 403.
# Split from unauthenticated sweep per --reviews OpenCode/Codex.
# ---------------------------------------------------------------------------

class TestAdminGate403SweepHeaderAuth:
  @pytest.mark.parametrize('path', ['/admin/ping'])
  def test_admin_rejects_header_auth(self, path):
    '''GET /admin/* with valid X-Trading-Signals-Auth header, no session cookie.

    Middleware step 2 grants the request (header valid) but _try_header does
    NOT set request.state.user_id — the dispatch-top reset leaves it None.
    require_admin sees user_id=None and raises 403.

    Asserts: status_code == 403, Content-Type application/json,
    body == {'detail': 'Admin access required'} (locked per --reviews #5).
    '''
    sys.modules.pop('web.app', None)
    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get(
      path,
      headers={'X-Trading-Signals-Auth': VALID_SECRET},
    )
    assert response.status_code == 403
    assert response.headers['content-type'].split(';')[0].strip() == 'application/json'
    assert response.json() == {'detail': _DETAIL_ADMIN_REQUIRED}


# ---------------------------------------------------------------------------
# TestAdminGate403SweepNonAdminRole
#
# Valid session cookie for a user with role='ff'. Middleware grants (cookie
# valid), middleware sets user_id, require_admin reads auth.json → role != admin
# → 403.
# ---------------------------------------------------------------------------

class TestAdminGate403SweepNonAdminRole:
  @pytest.mark.parametrize('path', ['/admin/ping'])
  def test_admin_rejects_non_admin_role(self, path, isolated_auth_json):
    '''GET /admin/* with valid session cookie for a non-admin user.

    Seed a user with role='ff'. Build signed session cookie with that uid.
    Middleware grants (valid cookie, uid set). require_admin reads auth.json
    and sees role != 'admin' → 403 + JSON body.
    '''
    import auth_store
    user = auth_store.create_user({'email': VALID_USERNAME, 'role': 'ff'})
    uid = user['uid']
    cookie = _build_session_cookie(uid)

    sys.modules.pop('web.app', None)
    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get(path, cookies={'tsi_session': cookie})
    assert response.status_code == 403
    assert response.headers['content-type'].split(';')[0].strip() == 'application/json'
    assert response.json() == {'detail': _DETAIL_ADMIN_REQUIRED}


# ---------------------------------------------------------------------------
# TestAdminPing
# ---------------------------------------------------------------------------

class TestAdminPing:
  def test_admin_session_returns_200(self, isolated_auth_json):
    '''Admin user with valid session cookie (post-Phase-35 shape with uid).

    Seed admin user; build signed cookie with uid; GET /admin/ping → 200,
    Content-Type application/json, body == {'ok': True}.
    '''
    import auth_store
    user = auth_store.create_user({'email': VALID_USERNAME, 'role': 'admin'})
    uid = user['uid']
    cookie = _build_session_cookie(uid)

    sys.modules.pop('web.app', None)
    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get('/admin/ping', cookies={'tsi_session': cookie})
    assert response.status_code == 200
    assert response.headers['content-type'].split(';')[0].strip() == 'application/json'
    assert response.json() == {'ok': True}

  def test_admin_session_with_legacy_cookie_no_uid_resolves_via_shim(
    self, isolated_auth_json,
  ):
    '''Admin user with legacy cookie (pre-Phase-35 shape, no uid key).

    D-04 backward-compat shim: middleware sees no uid in payload, looks up
    uid by email (payload['u'] = VALID_USERNAME), and sets request.state.user_id.
    require_admin then reads auth.json and confirms role='admin' → 200.

    Critical backward-compat regression guard.
    '''
    import auth_store
    auth_store.create_user({'email': VALID_USERNAME, 'role': 'admin'})
    # Build a legacy cookie without uid
    cookie = _build_session_cookie(uid=None, include_uid=False)

    sys.modules.pop('web.app', None)
    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get('/admin/ping', cookies={'tsi_session': cookie})
    assert response.status_code == 200
    assert response.json() == {'ok': True}

  def test_admin_session_when_user_not_in_auth_json_returns_403(
    self, isolated_auth_json,
  ):
    '''Bootstrap-gap: empty auth.json + cookie with uid=None.

    If the shim can't resolve a uid (no user row), require_admin sees
    user_id=None → 403 + JSON body. Documents the correct behavior during
    the first-boot window before any users are created.
    '''
    # empty auth.json — no users created
    serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-session-cookie')
    cookie = serializer.dumps({'u': VALID_USERNAME, 'uid': None, 'iat': int(time.time())})

    sys.modules.pop('web.app', None)
    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get('/admin/ping', cookies={'tsi_session': cookie})
    assert response.status_code == 403
    assert response.headers['content-type'].split(';')[0].strip() == 'application/json'
    assert response.json() == {'detail': _DETAIL_ADMIN_REQUIRED}

  def test_admin_with_uid_no_resolved_user_cannot_pass_require_admin(
    self, isolated_auth_json,
  ):
    '''--reviews Codex negative test: uid set in cookie but no matching auth.json row.

    A forged-but-signed cookie carrying a uid that does not appear in auth.json
    is still refused. The shim/cookie uid alone is insufficient — require_admin's
    get_user(uid) lookup is the authoritative gate. Even if the cookie signature
    is valid (operator accidentally leaked the secret), require_admin returns 403
    because the uid maps to no real row.
    '''
    # Build cookie with a plausible uid — but do NOT create the user in auth.json
    fake_uid = 'uid-that-does-not-exist-in-auth-json'
    cookie = _build_session_cookie(fake_uid)

    sys.modules.pop('web.app', None)
    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get('/admin/ping', cookies={'tsi_session': cookie})
    assert response.status_code == 403
    assert response.headers['content-type'].split(';')[0].strip() == 'application/json'
    assert response.json() == {'detail': _DETAIL_ADMIN_REQUIRED}


# ---------------------------------------------------------------------------
# TestPrePhase35RoutesStructuralParity
#
# Structural comparison, NOT byte-identical. Dynamic fields (Set-Cookie,
# timestamps, session tokens) are intentionally excluded. We assert:
#   (a) status code matches the pre-Phase-35 baseline,
#   (b) Content-Type matches,
#   (c) specific HTML landmark strings are present (page title, primary heading),
#   (d) no 500/stack-trace response body.
# Scope is narrowed to 4 critical routes:
#   GET /, GET /dashboard (does not exist — 404 is the baseline),
#   GET /paper-trades, POST /login.
# RBAC-01 "no observable behaviour change" is satisfied by THIS structural-parity
# test plus the full pytest suite passing.
# --reviews HIGH consensus #3.
# ---------------------------------------------------------------------------

class TestPrePhase35RoutesStructuralParity:
  '''Structural parity tests for the 4 pre-Phase-35 critical routes.

  Approach: send an admin session cookie (post-Phase-35 shape with uid).
  Assert: status code matches pre-Phase-35 baseline, Content-Type matches,
  key HTML landmark strings are present, no 500/Traceback in body.
  NOT byte-identical. NOT timestamp/cookie-value assertions.
  '''

  def _make_client_with_admin(self, isolated_auth_json):
    '''Build a TestClient + admin session cookie for structural parity tests.'''
    import auth_store
    user = auth_store.create_user({'email': VALID_USERNAME, 'role': 'admin'})
    uid = user['uid']
    cookie = _build_session_cookie(uid)
    sys.modules.pop('web.app', None)
    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    return client, {'tsi_session': cookie}

  def test_root_returns_expected_shape(self, isolated_auth_json):
    '''GET / with admin session cookie.

    Pre-Phase-35 baseline: returns 200 (dashboard HTML) or 503 (first-run
    before any signal run has written dashboard.html). Both are valid — the
    route never returns 500. No structural change expected from Phase 35.
    '''
    client, cookies = self._make_client_with_admin(isolated_auth_json)
    response = client.get('/', cookies=cookies)
    assert response.status_code in {200, 503}, (
      f'GET / expected 200 or 503, got {response.status_code}'
    )
    assert 'text/html' in response.headers.get('content-type', '') or \
           'text/plain' in response.headers.get('content-type', ''), (
      f'GET / unexpected content-type: {response.headers.get("content-type")}'
    )
    assert '<title>500' not in response.text
    assert 'Traceback' not in response.text

  def test_dashboard_route_not_found_is_baseline(self, isolated_auth_json):
    '''GET /dashboard with admin session cookie — route does not exist.

    Pre-Phase-35 baseline: /dashboard was never a registered route. The
    canonical dashboard is GET /. A 404 here is CORRECT structural parity —
    Phase 35 must not accidentally create a /dashboard route.
    '''
    client, cookies = self._make_client_with_admin(isolated_auth_json)
    response = client.get('/dashboard', cookies=cookies)
    assert response.status_code == 404, (
      f'GET /dashboard expected 404 (not a registered route), got {response.status_code}'
    )
    assert '<title>500' not in response.text
    assert 'Traceback' not in response.text

  def test_paper_trades_returns_expected_shape(self, isolated_auth_json, monkeypatch):
    '''GET /paper-trades with admin session cookie.

    Pre-Phase-35 baseline: returns 200 with HTML fragment containing the
    trades-region div. Landmark: 'trades-region' string in response body.
    No 500/Traceback.
    '''
    import state_manager
    from state_manager import reset_state
    def _stub(*_a, **_kw):
      s = reset_state()
      s.setdefault('paper_trades', [])
      s.setdefault('_resolved_contracts', {})
      return s
    monkeypatch.setattr(state_manager, 'load_state', _stub)

    client, cookies = self._make_client_with_admin(isolated_auth_json)
    response = client.get('/paper-trades', cookies=cookies)
    assert response.status_code == 200, (
      f'GET /paper-trades expected 200, got {response.status_code}'
    )
    assert 'text/html' in response.headers.get('content-type', '')
    assert 'trades-region' in response.text
    assert '<title>500' not in response.text
    assert 'Traceback' not in response.text

  def test_login_post_returns_expected_shape(self, isolated_auth_json):
    '''POST /login with valid credentials.

    Pre-Phase-35 baseline: returns 302 redirect (to /enroll-totp or /verify-totp
    depending on auth.json totp state). Location header matches one of those
    two paths. No 500/Traceback.
    '''
    sys.modules.pop('web.app', None)
    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False, follow_redirects=False)
    response = client.post(
      '/login',
      data={'username': VALID_USERNAME, 'password': VALID_SECRET},
    )
    assert response.status_code == 302, (
      f'POST /login expected 302, got {response.status_code}'
    )
    location = response.headers.get('location', '')
    assert location in {'/enroll-totp', '/verify-totp'}, (
      f'POST /login Location expected /enroll-totp or /verify-totp, got {location!r}'
    )
    assert 'Traceback' not in response.text
