'''Phase 36 RBAC-04 — GET /admin/users + PATCH /admin/users/{uid}/disable tests.

Placed in a new file (not appended to test_web_admin.py) because test_web_admin.py
is 594 lines — adding classes would exceed the 500-LOC project cap (CLAUDE.md).

These are "red" stubs that Wave 1 (plan 02) makes green:
  TestAdminUsers  — GET /admin/users returns list[PublicUserSummary] shape
  TestAdminDisable — PATCH /admin/users/{uid}/disable toggles disabled flag

References: RBAC-04, D-07..D-11, T-36-02 (FastAPI response_model redaction).
'''
import time

import pytest
from fastapi.testclient import TestClient
from itsdangerous.url_safe import URLSafeTimedSerializer

from tests.conftest import VALID_SECRET, VALID_USERNAME


def _build_session_cookie(uid, *, username=None, include_uid=True):
  '''Build a signed tsi_session cookie for tests.

  Copied from tests/test_web_admin.py for use in admin-users tests.
  '''
  username = username or VALID_USERNAME
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-session-cookie')
  payload = {'u': username, 'iat': int(time.time())}
  if include_uid:
    payload['uid'] = uid
  return serializer.dumps(payload)


@pytest.fixture
def admin_client(isolated_auth_json, monkeypatch):
  '''TestClient with an admin user seeded in auth.json + state stubbed.

  Seeds one admin user. Returns (client, admin_uid).
  '''
  import sys
  sys.modules.pop('web.app', None)

  import auth_store
  from state_manager.migrations import _ADMIN_UID
  import state_manager

  admin_user = auth_store.create_user({'email': 'admin@example.com', 'role': 'admin'})
  uid = admin_user['uid']

  default_state = {
    'schema_version': 12,
    'admin_user_id': _ADMIN_UID,
    'signals': {},
    'markets': {},
    'strategy_settings': {},
    'warnings': [],
    'last_run': '2026-05-14',
    'users': {
      uid: {
        'account': 100_000.0,
        'initial_account': 100_000.0,
        'contracts': {},
        'positions': {'SPI200': None, 'AUDUSD': None},
        'trade_log': [],
        'equity_history': [],
        'paper_trades': [],
        'ui_prefs': {'tour_completed': True},
      },
    },
  }
  monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: default_state)
  monkeypatch.setattr(state_manager, 'load_user_state',
                      lambda u, *_a, **_kw: default_state['users'].get(u, {}))

  from web.app import create_app
  client = TestClient(create_app(), raise_server_exceptions=False)
  return client, uid


class TestAdminUsers:
  '''GET /admin/users returns list[PublicUserSummary] shape (RBAC-04 / D-07..D-11).

  Wave 1 makes these green by implementing the route.
  '''

  @pytest.mark.xfail(strict=False, reason='Wave 1: GET /admin/users not yet implemented')
  def test_returns_200_with_public_summary_shape(self, admin_client):
    '''GET /admin/users as admin returns 200 with correct PublicUserSummary keys.'''
    client, uid = admin_client
    cookie = _build_session_cookie(uid)
    resp = client.get('/admin/users', cookies={'tsi_session': cookie})
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    expected_keys = {'user_id', 'display_name', 'status', 'last_seen_date', 'has_active_position'}
    for row in rows:
      assert set(row.keys()) == expected_keys, f'Unexpected keys in row: {set(row.keys())}'

  @pytest.mark.xfail(strict=False, reason='Wave 1: GET /admin/users not yet implemented')
  def test_returns_403_for_non_admin(self, isolated_auth_json, monkeypatch):
    '''GET /admin/users as non-admin returns 403.'''
    import sys
    sys.modules.pop('web.app', None)

    import auth_store
    import state_manager
    ff_user = auth_store.create_user({'email': 'ff@example.com', 'role': 'ff'})
    uid = ff_user['uid']
    monkeypatch.setattr(state_manager, 'load_state',
                        lambda *_a, **_kw: {'schema_version': 12, 'users': {}})

    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    cookie = _build_session_cookie(uid)
    resp = client.get('/admin/users', cookies={'tsi_session': cookie})
    assert resp.status_code == 403


class TestAdminDisable:
  '''PATCH /admin/users/{uid}/disable toggles disabled flag (RBAC-04).

  Wave 1 makes these green by implementing the route.
  '''

  @pytest.mark.xfail(strict=False, reason='Wave 1: PATCH /admin/users/{uid}/disable not yet implemented')
  def test_disable_returns_ok(self, admin_client):
    '''PATCH /admin/users/{uid}/disable?disabled=true returns 200 with disabled=true.'''
    client, uid = admin_client
    cookie = _build_session_cookie(uid)
    resp = client.patch(
      f'/admin/users/{uid}/disable',
      params={'disabled': 'true'},
      cookies={'tsi_session': cookie},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get('disabled') is True

  @pytest.mark.xfail(strict=False, reason='Wave 1: PATCH /admin/users/{uid}/disable not yet implemented')
  def test_disable_unknown_uid_returns_404(self, admin_client):
    '''PATCH /admin/users/<unknown>/disable returns 404.'''
    client, uid = admin_client
    cookie = _build_session_cookie(uid)
    resp = client.patch(
      '/admin/users/nonexistent-uid-000/disable',
      params={'disabled': 'true'},
      cookies={'tsi_session': cookie},
    )
    assert resp.status_code == 404
