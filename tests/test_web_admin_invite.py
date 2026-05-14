'''Phase 37 Plan 05 — RBAC-03 admin invite surface tests.

TestAdminInviteIssue  — POST /admin/invites mints token + sends invite email
TestAdminInviteRevoke — DELETE /admin/invites/{token_hash} revokes invite
TestLastCycle         — GET /healthz/last-cycle returns 7-key schema (admin-gated)
TestAdminUsersNegotiation — HX-Request > Accept:json > Accept:html precedence (review #8)
TestLastSeenDate      — PublicUserSummary.last_seen_date populated from trusted devices
'''
import os
import sys
import json
import hashlib

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_admin_client(monkeypatch, tmp_auth_path, tmp_state_path=None):
  '''Build a TestClient with admin auth dependency override + isolated auth.json.'''
  from fastapi.testclient import TestClient
  sys.modules.pop('web.app', None)
  from web.app import create_app
  import auth_store
  import state_manager
  monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', tmp_auth_path)
  app = create_app()
  # Override require_admin to return 'admin-uid' unconditionally
  from web.dependencies import require_admin, current_user_id
  app.dependency_overrides[require_admin] = lambda: 'admin-uid'
  app.dependency_overrides[current_user_id] = lambda: 'admin-uid'
  if tmp_state_path is not None:
    monkeypatch.setenv('STATE_FILE', str(tmp_state_path))
    monkeypatch.setattr('state_manager.STATE_FILE', str(tmp_state_path), raising=False)
  client = TestClient(app)
  return client


def _make_nonadmin_client(monkeypatch, tmp_auth_path):
  '''Build a TestClient WITHOUT require_admin override (tests 403 path).'''
  from fastapi.testclient import TestClient
  sys.modules.pop('web.app', None)
  from web.app import create_app
  import auth_store
  monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', tmp_auth_path)
  app = create_app()
  # No dependency override → require_admin raises 403
  client = TestClient(app, raise_server_exceptions=False)
  return client


# ---------------------------------------------------------------------------
# TestAdminInviteIssue
# ---------------------------------------------------------------------------

class TestAdminInviteIssue:
  '''RBAC-03 admin: POST /admin/invites mints token + sends email (review #10).'''

  def test_post_admin_invites_mints_token(
    self, monkeypatch, pending_invite_auth_json, tmp_path,
  ):
    '''POST /admin/invites → new row in list_pending_invites with email + consumed=False.'''
    import auth_store

    monkeypatch.setenv('BASE_URL', 'https://signals.example.com')
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')
    # Stub send_invite_email — no actual network call
    import per_user_fanout
    monkeypatch.setattr(per_user_fanout, 'send_invite_email', lambda **kw: None)

    client = _make_admin_client(
      monkeypatch, pending_invite_auth_json['auth_path'],
    )
    resp = client.post(
      '/admin/invites',
      data={'email': 'new@x.com'},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    invites = auth_store.list_pending_invites(path=pending_invite_auth_json['auth_path'])
    new_ones = [i for i in invites if i.get('email') == 'new@x.com']
    assert len(new_ones) == 1
    assert new_ones[0]['consumed'] is False

  def test_post_admin_invites_sends_invite_email(
    self, monkeypatch, pending_invite_auth_json,
  ):
    '''POST /admin/invites → send_invite_email called with correct args (review #10).'''
    import per_user_fanout

    monkeypatch.setenv('BASE_URL', 'https://signals.example.com')
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')

    calls = []
    def _fake_send(to_email, invite_url):
      calls.append({'to_email': to_email, 'invite_url': invite_url})
    monkeypatch.setattr(per_user_fanout, 'send_invite_email', _fake_send)

    client = _make_admin_client(
      monkeypatch, pending_invite_auth_json['auth_path'],
    )
    resp = client.post(
      '/admin/invites',
      data={'email': 'new@x.com'},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0]['to_email'] == 'new@x.com'
    assert '/accept-invite?token=' in calls[0]['invite_url']

  def test_post_admin_invites_returns_inline_invite_url_fragment(
    self, monkeypatch, pending_invite_auth_json,
  ):
    '''POST /admin/invites → response body contains <code> element + invite URL.'''
    import per_user_fanout

    monkeypatch.setenv('BASE_URL', 'https://signals.example.com')
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')
    monkeypatch.setattr(per_user_fanout, 'send_invite_email', lambda **kw: None)

    client = _make_admin_client(
      monkeypatch, pending_invite_auth_json['auth_path'],
    )
    resp = client.post(
      '/admin/invites',
      data={'email': 'new@x.com'},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    body = resp.text
    assert '<code' in body
    assert '/accept-invite?token=' in body

  def test_post_admin_invites_requires_admin_role(
    self, monkeypatch, pending_invite_auth_json,
  ):
    '''POST /admin/invites without admin role → 403.'''
    from fastapi.testclient import TestClient
    sys.modules.pop('web.app', None)
    from web.app import create_app
    import auth_store
    monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', pending_invite_auth_json['auth_path'])
    app = create_app()
    # No dependency override → require_admin raises 403 for non-admin
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
      '/admin/invites',
      data={'email': 'new@x.com'},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestAdminInviteRevoke
# ---------------------------------------------------------------------------

class TestAdminInviteRevoke:
  '''RBAC-03 admin: DELETE /admin/invites/{token_hash} revokes invite.'''

  def test_delete_admin_invite_marks_consumed(
    self, monkeypatch, pending_invite_auth_json,
  ):
    '''DELETE /admin/invites/{token_hash} → row has consumed=True.'''
    import auth_store

    client = _make_admin_client(
      monkeypatch, pending_invite_auth_json['auth_path'],
    )
    token_hash = pending_invite_auth_json['token_hash']
    resp = client.delete(
      f'/admin/invites/{token_hash}',
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    invites = auth_store.list_pending_invites(path=pending_invite_auth_json['auth_path'])
    matching = [i for i in invites if i.get('token_hash') == token_hash]
    assert len(matching) == 1
    assert matching[0]['consumed'] is True

  def test_delete_admin_invite_404_for_unknown_hash(
    self, monkeypatch, pending_invite_auth_json,
  ):
    '''DELETE /admin/invites/{unknown_hash} → 404.'''
    client = _make_admin_client(
      monkeypatch, pending_invite_auth_json['auth_path'],
    )
    resp = client.delete(
      '/admin/invites/sha256:nonexistent',
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 404

  def test_delete_admin_invite_requires_admin_role(
    self, monkeypatch, pending_invite_auth_json,
  ):
    '''DELETE /admin/invites/{token_hash} without admin → 403.'''
    from fastapi.testclient import TestClient
    sys.modules.pop('web.app', None)
    from web.app import create_app
    import auth_store
    monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', pending_invite_auth_json['auth_path'])
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    token_hash = pending_invite_auth_json['token_hash']
    resp = client.delete(f'/admin/invites/{token_hash}')
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestLastCycle
# ---------------------------------------------------------------------------

class TestLastCycle:
  '''UMAIL-02 + D-15: GET /healthz/last-cycle returns 7-key schema (admin-gated).'''

  def _make_state_client(self, monkeypatch, state_dict):
    '''Build TestClient with admin override + monkeypatched load_state.'''
    from fastapi.testclient import TestClient
    sys.modules.pop('web.app', None)
    from web.app import create_app
    import state_manager
    monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: state_dict)
    app = create_app()
    from web.dependencies import require_admin, current_user_id
    app.dependency_overrides[require_admin] = lambda: 'admin-uid'
    app.dependency_overrides[current_user_id] = lambda: 'admin-uid'
    return TestClient(app)

  def test_last_cycle_returns_empty_when_no_cycle(self, monkeypatch):
    '''GET /healthz/last-cycle with no last_cycle in state → 7-key empty schema.'''
    client = self._make_state_client(monkeypatch, {})
    resp = client.get(
      '/healthz/last-cycle',
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'ok'
    assert data['date'] is None
    assert data['total'] == 0
    assert data['ok'] == 0
    assert data['failed'] == 0
    assert data['users'] == []
    assert data['errors'] == []
    assert data['crash'] is None

  def test_last_cycle_returns_per_user_outcomes(self, monkeypatch):
    '''GET /healthz/last-cycle with populated last_cycle → returns all 7 keys.'''
    lc = {
      'date': '2026-05-11',
      'total': 2,
      'ok': 2,
      'failed': 0,
      'users': [
        {'uid': 'u1', 'ok': True, 'reason': None},
        {'uid': 'u2', 'ok': True, 'reason': None},
      ],
      'errors': [],
      'crash': None,
    }
    client = self._make_state_client(monkeypatch, {'last_cycle': lc})
    resp = client.get(
      '/healthz/last-cycle',
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data['date'] == '2026-05-11'
    assert data['total'] == 2
    assert data['ok'] == 2
    assert data['failed'] == 0
    assert len(data['users']) == 2
    assert data['crash'] is None

  def test_last_cycle_requires_admin_role(self, monkeypatch):
    '''GET /healthz/last-cycle without admin → 403.'''
    from fastapi.testclient import TestClient
    sys.modules.pop('web.app', None)
    from web.app import create_app
    import state_manager
    monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: {})
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get('/healthz/last-cycle')
    assert resp.status_code == 403

  def test_last_cycle_returns_crash_field_on_total_fanout_failure(self, monkeypatch):
    '''GET /healthz/last-cycle with crash → returns crash field intact (review #5).'''
    lc = {
      'date': '2026-05-11',
      'total': 0,
      'ok': 0,
      'failed': 0,
      'users': [],
      'errors': [],
      'crash': 'RuntimeError: total fan-out failure',
    }
    client = self._make_state_client(monkeypatch, {'last_cycle': lc})
    resp = client.get(
      '/healthz/last-cycle',
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data['crash'] == 'RuntimeError: total fan-out failure'


# ---------------------------------------------------------------------------
# TestAdminUsersNegotiation — review #8 HX-Request precedence
# ---------------------------------------------------------------------------

class TestAdminUsersNegotiation:
  '''Review #8: explicit HX-Request > Accept:json > Accept:html precedence.'''

  def _make_client(self, monkeypatch):
    from fastapi.testclient import TestClient
    sys.modules.pop('web.app', None)
    from web.app import create_app
    import state_manager
    import auth_store
    monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: {})
    monkeypatch.setattr(auth_store, 'list_users', lambda *_a, **_kw: [])
    monkeypatch.setattr(auth_store, 'list_pending_invites', lambda *_a, **_kw: [])
    app = create_app()
    from web.dependencies import require_admin, current_user_id
    app.dependency_overrides[require_admin] = lambda: 'admin-uid'
    app.dependency_overrides[current_user_id] = lambda: 'admin-uid'
    return TestClient(app)

  def test_hx_request_returns_html_fragment(self, monkeypatch):
    '''GET /admin/users with HX-Request: true → HTML fragment (not full page).'''
    client = self._make_client(monkeypatch)
    resp = client.get(
      '/admin/users',
      headers={
        'X-Trading-Signals-Auth': 'a' * 32,
        'HX-Request': 'true',
        'Accept': 'application/json',  # HX-Request takes precedence
      },
    )
    assert resp.status_code == 200
    ct = resp.headers.get('content-type', '')
    assert 'text/html' in ct
    # Fragment should NOT contain <html> tag (it's a fragment not full page)
    assert '<html' not in resp.text.lower() or resp.text.lower().count('<html') == 0

  def test_accept_json_returns_json_list(self, monkeypatch):
    '''GET /admin/users with Accept: application/json (no HX-Request) → JSON list.'''
    client = self._make_client(monkeypatch)
    resp = client.get(
      '/admin/users',
      headers={
        'X-Trading-Signals-Auth': 'a' * 32,
        'Accept': 'application/json',
      },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

  def test_accept_html_returns_full_page(self, monkeypatch):
    '''GET /admin/users with Accept: text/html (no HX-Request) → full HTML page.'''
    client = self._make_client(monkeypatch)
    resp = client.get(
      '/admin/users',
      headers={
        'X-Trading-Signals-Auth': 'a' * 32,
        'Accept': 'text/html',
      },
    )
    assert resp.status_code == 200
    ct = resp.headers.get('content-type', '')
    assert 'text/html' in ct


# ---------------------------------------------------------------------------
# TestLastSeenDate — last_seen_date populated from trusted devices
# ---------------------------------------------------------------------------

class TestLastSeenDate:
  '''PublicUserSummary.last_seen_date populated from max TrustedDevice.last_seen.'''

  def test_last_seen_date_from_trusted_devices(self, monkeypatch):
    '''User with 2 trusted devices → last_seen_date = most recent.'''
    from web.routes.admin._models import PublicUserSummary, _compute_last_seen_date

    devices = [
      {'last_seen': '2026-05-10T00:00:00Z', 'revoked': False},
      {'last_seen': '2026-05-13T00:00:00Z', 'revoked': False},
    ]
    result = _compute_last_seen_date(devices)
    assert result == '2026-05-13'

  def test_last_seen_date_none_when_no_devices(self, monkeypatch):
    '''User with no trusted devices → last_seen_date = None.'''
    from web.routes.admin._models import _compute_last_seen_date

    result = _compute_last_seen_date([])
    assert result is None
