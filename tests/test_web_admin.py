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
from fastapi import HTTPException

from web.dependencies import (
  _DETAIL_ADMIN_REQUIRED,
  _DETAIL_NOT_AUTHENTICATED,
  current_user_id,
  require_admin,
)


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
  pass


class TestAdminGate403Sweep:
  pass


class TestAdminPing:
  pass


class TestAdminRouteInvariant:
  pass
