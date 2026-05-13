'''Phase 35 Plan 03 — web/dependencies.py factories + admin gate tests.

TDD RED: tests for current_user_id and require_admin factories.
Tests assert BOTH HTTPException.status_code AND .detail (--reviews #5).

Wave-0 stub classes: TestAdminSubRouter, TestAdminGate403Sweep, TestAdminPing,
TestAdminRouteInvariant — filled by Plans 04 and 05.

Fixture strategy:
  The autouse fixture _set_web_auth_credentials_for_web_tests in tests/conftest.py
  pre-sets WEB_AUTH_SECRET for this file (name matches test_web_*.py).
  Tests mutating auth.json use the isolated_auth_json fixture from conftest.py.
'''
import types

import pytest
from fastapi import APIRouter, HTTPException
from fastapi.routing import APIRoute

from web.dependencies import (
  _DETAIL_ADMIN_REQUIRED,
  _DETAIL_NOT_AUTHENTICATED,
  current_user_id,
  require_admin,
)
from web.routes.admin import router


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


# ---------------------------------------------------------------------------
# TestCurrentUserId
# ---------------------------------------------------------------------------

class TestCurrentUserId:
  def test_returns_uid_when_set(self):
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
# Wave-0 stubs — filled by Plan 04 and Plan 05
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


class TestAdminGate403Sweep:
  pass


class TestAdminPing:
  pass


class TestAdminRouteInvariant:
  pass
