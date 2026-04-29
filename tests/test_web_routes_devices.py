'''Phase 16.1 Plan 02 Task 4 — /devices route tests.

Covers:
  - TestDevicesGet: list rendering, current marker, revoked styling, header-only
    auth → 403, no-auth → 302 /login, revoke buttons per active row, escape
  - TestDevicesRevoke: POST flips uuid + redirects, unknown uuid no-op, header
    only auth → 403
  - TestDevicesRevokeAll: flips all-except-current, header-only → 403
  - TestDevicesCurrentDeviceDetection: tsi_trusted uuid drives the "(this
    device)" marker; no tsi_trusted means no marker

Reference: 16.1-02-PLAN.md Task 4; 16.1-CONTEXT.md E-06 / E-08.
'''
import time as _time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from itsdangerous.url_safe import URLSafeTimedSerializer


def _stub_load_state(**overrides):
  from state_manager import reset_state

  def _fn(*_args, **_kwargs):
    state = reset_state()
    state.update(overrides)
    state.setdefault('_resolved_contracts', {})
    return state

  return _fn


@pytest.fixture
def fresh_auth_path(tmp_path, monkeypatch) -> Path:
  '''Per-test isolation for auth.json. Mirrors test_web_routes_totp.py.'''
  import auth_store
  path = tmp_path / 'auth.json'
  monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', path)
  return path


@pytest.fixture
def client(monkeypatch, fresh_auth_path):
  import sys

  import state_manager
  monkeypatch.setattr(state_manager, 'load_state', _stub_load_state())
  sys.modules.pop('web.app', None)
  from web.app import create_app
  return TestClient(create_app())


def _make_trusted_token(uuid_value: str, secret: str = 'a' * 32) -> str:
  ser = URLSafeTimedSerializer(secret, salt='tsi-trusted-cookie')
  return ser.dumps({'uuid': uuid_value, 'iat': int(_time.time())})


# =============================================================================
# GET /devices
# =============================================================================


class TestDevicesGet:

  def test_renders_table_with_all_devices(
    self, client, fresh_auth_path, valid_cookie_token,
  ):
    import auth_store
    uid_a = auth_store.add_trusted_device(label='iPhone Safari · 203.0.113.x · 2026-04-29')
    uid_b = auth_store.add_trusted_device(label='macOS Chrome · 203.0.113.x · 2026-04-28')
    uid_c = auth_store.add_trusted_device(label='Windows · 198.51.100.x · 2026-04-25')
    auth_store.revoke_device(uid_c)

    # Mark uid_a as the current device by attaching its tsi_trusted cookie
    trusted_token = _make_trusted_token(uid_a)
    r = client.get('/devices', cookies={
      'tsi_session': valid_cookie_token,
      'tsi_trusted': trusted_token,
    })
    assert r.status_code == 200, r.text[:200]
    body = r.text
    assert 'iPhone Safari' in body
    assert 'macOS Chrome' in body
    assert 'Windows' in body
    # Current device marker
    assert '(this device)' in body or 'this device' in body
    # Revoked row visually de-emphasised
    assert 'revoked' in body.lower()

  def test_header_only_auth_returns_403(
    self, client, fresh_auth_path, valid_secret,
  ):
    '''E-06: header path is curl/scripts only — no concept of device.'''
    r = client.get(
      '/devices',
      headers={'X-Trading-Signals-Auth': valid_secret},
    )
    assert r.status_code == 403, r.text[:200]
    assert 'forbidden' in r.text.lower()

  def test_no_auth_returns_302_to_login(self, client, fresh_auth_path):
    r = client.get(
      '/devices',
      follow_redirects=False,
      headers={'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'},
    )
    assert r.status_code == 302
    assert r.headers.get('location', '').startswith('/login')

  def test_renders_revoke_button_per_active_row(
    self, client, fresh_auth_path, valid_cookie_token,
  ):
    '''Each unrevoked row gets a Revoke button; revoked rows do NOT.'''
    import auth_store
    import re
    uid_a = auth_store.add_trusted_device(label='A')
    uid_b = auth_store.add_trusted_device(label='B')
    uid_c = auth_store.add_trusted_device(label='C')
    auth_store.revoke_device(uid_c)
    r = client.get('/devices', cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    revoke_buttons = re.findall(
      r'<button[^>]*name="uuid"[^>]*value="([^"]+)"', r.text,
    )
    assert uid_a in revoke_buttons
    assert uid_b in revoke_buttons
    assert uid_c not in revoke_buttons  # revoked → no button

  def test_renders_revoke_all_button_when_more_than_one_active(
    self, client, fresh_auth_path, valid_cookie_token,
  ):
    import auth_store
    auth_store.add_trusted_device(label='A')
    auth_store.add_trusted_device(label='B')
    r1 = client.get('/devices', cookies={'tsi_session': valid_cookie_token})
    assert 'Revoke all other' in r1.text or 'revoke-all' in r1.text.lower()

  def test_revoke_all_button_absent_when_only_one_active(
    self, client, fresh_auth_path, valid_cookie_token,
  ):
    import auth_store
    auth_store.add_trusted_device(label='only-one')
    r = client.get('/devices', cookies={'tsi_session': valid_cookie_token})
    # Only single active device — revoke-all is a no-op, hide the button.
    assert 'revoke-all' not in r.text.lower() or 'Revoke all other' not in r.text

  def test_html_escapes_device_label(
    self, client, fresh_auth_path, valid_cookie_token,
  ):
    '''Defensive XSS: even though real UAs don't contain <script>, escape anyway.'''
    import auth_store
    auth_store.add_trusted_device(label='<script>alert(1)</script>')
    r = client.get('/devices', cookies={'tsi_session': valid_cookie_token})
    assert '<script>alert(1)</script>' not in r.text
    assert '&lt;script&gt;' in r.text


# =============================================================================
# POST /devices/revoke
# =============================================================================


class TestDevicesRevoke:

  def test_post_revoke_flips_uuid_and_redirects(
    self, client, fresh_auth_path, valid_cookie_token,
  ):
    import auth_store
    uid = auth_store.add_trusted_device(label='to-revoke')
    auth_store.add_trusted_device(label='other')
    r = client.post(
      '/devices/revoke',
      cookies={'tsi_session': valid_cookie_token},
      data={'uuid': uid},
      follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get('location') == '/devices'
    assert auth_store.get_trusted_device(uid)['revoked'] is True

  def test_post_revoke_unknown_uuid_is_no_op_redirects(
    self, client, fresh_auth_path, valid_cookie_token,
  ):
    r = client.post(
      '/devices/revoke',
      cookies={'tsi_session': valid_cookie_token},
      data={'uuid': 'does-not-exist'},
      follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get('location') == '/devices'

  def test_post_revoke_header_only_auth_returns_403(
    self, client, fresh_auth_path, valid_secret,
  ):
    r = client.post(
      '/devices/revoke',
      headers={'X-Trading-Signals-Auth': valid_secret},
      data={'uuid': 'whatever'},
    )
    assert r.status_code == 403


# =============================================================================
# POST /devices/revoke-all
# =============================================================================


class TestDevicesRevokeAll:

  def test_post_revoke_all_flips_all_except_current(
    self, client, fresh_auth_path, valid_cookie_token,
  ):
    import auth_store
    uid_a = auth_store.add_trusted_device(label='A (current)')
    uid_b = auth_store.add_trusted_device(label='B')
    uid_c = auth_store.add_trusted_device(label='C')

    trusted_token = _make_trusted_token(uid_a)
    r = client.post(
      '/devices/revoke-all',
      cookies={
        'tsi_session': valid_cookie_token,
        'tsi_trusted': trusted_token,
      },
      follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get('location') == '/devices'
    assert auth_store.get_trusted_device(uid_a)['revoked'] is False
    assert auth_store.get_trusted_device(uid_b)['revoked'] is True
    assert auth_store.get_trusted_device(uid_c)['revoked'] is True

  def test_post_revoke_all_header_only_returns_403(
    self, client, fresh_auth_path, valid_secret,
  ):
    r = client.post(
      '/devices/revoke-all',
      headers={'X-Trading-Signals-Auth': valid_secret},
    )
    assert r.status_code == 403


# =============================================================================
# Current-device detection — driven by tsi_trusted payload
# =============================================================================


class TestDevicesCurrentDeviceDetection:

  def test_current_device_uuid_resolved_from_tsi_trusted_cookie(
    self, client, fresh_auth_path, valid_cookie_token,
  ):
    import auth_store
    uid_a = auth_store.add_trusted_device(label='AAA-CURRENT')
    auth_store.add_trusted_device(label='BBB-OTHER')
    trusted_token = _make_trusted_token(uid_a)
    r = client.get('/devices', cookies={
      'tsi_session': valid_cookie_token,
      'tsi_trusted': trusted_token,
    })
    body = r.text
    # The "(this device)" marker should appear adjacent to AAA-CURRENT row,
    # not BBB-OTHER. Since both rows mention their label, we need a position
    # check: the marker should appear AFTER AAA-CURRENT and before BBB-OTHER
    # in document order.
    assert 'AAA-CURRENT' in body
    assert 'BBB-OTHER' in body
    aaa_idx = body.index('AAA-CURRENT')
    bbb_idx = body.index('BBB-OTHER')
    # Find any "(this device)" or "this device" mention
    if '(this device)' in body:
      marker_idx = body.index('(this device)')
    else:
      marker_idx = body.lower().index('this device')
    # The current marker is for AAA-CURRENT — it should appear AFTER AAA's
    # label substring (in the same row) and BEFORE BBB-OTHER's label.
    assert aaa_idx < marker_idx < bbb_idx, (
      f'Marker not adjacent to current-device row: aaa={aaa_idx} '
      f'marker={marker_idx} bbb={bbb_idx}'
    )

  def test_no_tsi_trusted_means_no_current_marker(
    self, client, fresh_auth_path, valid_cookie_token,
  ):
    '''Operator authed via login form WITHOUT trust-device — session is
    cookie-only and not tied to any trusted_devices row, so no row should
    be marked as current.
    '''
    import auth_store
    auth_store.add_trusted_device(label='A')
    auth_store.add_trusted_device(label='B')
    r = client.get('/devices', cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    # No tsi_trusted cookie present → no row gets the "(this device)" marker.
    assert '(this device)' not in r.text
