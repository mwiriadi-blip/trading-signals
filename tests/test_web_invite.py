'''Phase 37 Plan 04 — Invite acceptance wizard tests (RBAC-03).

Full TDD implementation replacing Wave 0 stubs.

Test classes:
  TestExpiredToken          — Error page (200) for expired/consumed/missing tokens
  TestStep1Password         — Step 1: password form GET + POST validation
  TestStep3Device           — Step 3: trust-device cookie + redirect
  TestRouteRegistration     — Review #1: route registered before AuthMiddleware
  TestPartialEnrollmentRecovery — Review #2: partial-enrollment degraded path
  TestNextFieldForTOTPHandoff   — Review #6: tsi_enroll carries next='/accept-invite/device'
'''
import hashlib
import json
import os
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_SECRET = 'a' * 32  # matches conftest.py VALID_SECRET
VALID_USERNAME = 'marc'

# Deterministic raw token (same format as Phase 34 tokens — 43 chars urlsafe)
RAW_TOKEN = 'a' * 43
TOKEN_HASH = 'sha256:' + hashlib.sha256(RAW_TOKEN.encode()).hexdigest()
INVITE_EMAIL = 'invitee@example.com'


def _make_auth_json(tmp_path: Path, *, consumed: bool = False, expired: bool = False) -> Path:
  '''Synthesise a minimal v2 auth.json with one pending invite.'''
  from datetime import datetime, timezone, timedelta
  from auth_store._schema import SCHEMA_VERSION

  if expired:
    expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
  else:
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

  data = {
    'schema_version': SCHEMA_VERSION,
    'totp_secret': 'BASE32SECRET',
    'totp_enrolled': True,
    'totp_enrolled_at': '2026-01-01T00:00:00+00:00',
    'pending_magic_links': [],
    'pending_invites': [
      {
        'token_hash': TOKEN_HASH,
        'email': INVITE_EMAIL,
        'invited_by_uid': 'admin-uid-0000',
        'created_at': '2026-05-14T00:00:00+00:00',
        'expires_at': expires_at,
        'consumed': consumed,
        'consumed_at': '2026-05-14T01:00:00+00:00' if consumed else None,
      }
    ],
    'users': [
      {
        'uid': 'admin-uid-0000',
        'email': VALID_USERNAME,
        'role': 'admin',
        'created_at': '2026-01-01T00:00:00+00:00',
        'disabled': False,
        'password_hash': None,
      }
    ],
    'trusted_devices': [],
  }
  p = tmp_path / 'auth.json'
  p.write_text(json.dumps(data))
  return p


def _make_app_with_auth(tmp_path: Path, auth_path: Path, monkeypatch):
  '''Build a TestClient with an isolated auth.json.'''
  import sys
  import auth_store
  from fastapi.testclient import TestClient
  monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
  monkeypatch.setenv('WEB_AUTH_USERNAME', VALID_USERNAME)
  monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', 'mwiriadi@gmail.com')
  monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', auth_path)
  sys.modules.pop('web.app', None)
  from web.app import create_app
  return TestClient(create_app(), raise_server_exceptions=True)


def _wizard_cookie(payload: dict, max_age: int = 3600) -> str:
  '''Build a signed tsi_invite_wizard cookie value.'''
  from itsdangerous.url_safe import URLSafeTimedSerializer
  s = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-invite-wizard')
  return s.dumps(payload)


def _enroll_cookie(payload: dict) -> str:
  from itsdangerous.url_safe import URLSafeTimedSerializer
  s = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-enroll-cookie')
  return s.dumps(payload)


# ---------------------------------------------------------------------------
# TestExpiredToken
# ---------------------------------------------------------------------------

class TestExpiredToken:
  '''Expired/consumed/missing tokens render a 200 HTML error page (D-07).'''

  def test_no_token_param_renders_error_page_200_status(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    resp = client.get('/accept-invite', follow_redirects=False)
    assert resp.status_code == 200
    assert 'expired or has already been used' in resp.text.lower() \
      or 'link expired' in resp.text.lower()
    assert 'location' not in resp.headers

  def test_expired_token_renders_error_page_200_status(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path, expired=True)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    resp = client.get(f'/accept-invite?token={RAW_TOKEN}', follow_redirects=False)
    assert resp.status_code == 200
    assert 'expired or has already been used' in resp.text.lower() \
      or 'link expired' in resp.text.lower()
    assert 'location' not in resp.headers

  def test_consumed_token_renders_error_page_200_status(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path, consumed=True)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    resp = client.get(f'/accept-invite?token={RAW_TOKEN}', follow_redirects=False)
    assert resp.status_code == 200
    assert 'expired or has already been used' in resp.text.lower() \
      or 'link expired' in resp.text.lower()
    assert 'location' not in resp.headers

  def test_unknown_token_renders_error_page_200_status(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    resp = client.get('/accept-invite?token=unknown-token-xyz', follow_redirects=False)
    assert resp.status_code == 200
    assert 'expired or has already been used' in resp.text.lower() \
      or 'link expired' in resp.text.lower()

  def test_public_access_no_auth_required(self, tmp_path, monkeypatch):
    '''GET /accept-invite without any session cookie returns 200 (not 401).'''
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    resp = client.get('/accept-invite?token=whatever', follow_redirects=False)
    assert resp.status_code == 200
    # NOT 401 unauthorized
    assert 'unauthorized' not in resp.text.lower()


# ---------------------------------------------------------------------------
# TestStep1Password
# ---------------------------------------------------------------------------

class TestStep1Password:
  '''Step 1: GET renders password form; POST validates + hashes + creates user.'''

  def test_get_valid_token_renders_password_form(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    resp = client.get(f'/accept-invite?token={RAW_TOKEN}', follow_redirects=False)
    assert resp.status_code == 200
    assert 'Set your password' in resp.text
    assert 'Step 1 of 3' in resp.text
    # Wizard cookie set
    assert 'tsi_invite_wizard' in resp.cookies

  def test_password_too_short_returns_400(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    wizard_val = _wizard_cookie({'step': 'password', 'raw_token': RAW_TOKEN, 'email': INVITE_EMAIL})
    resp = client.post(
      '/accept-invite',
      data={'password': 'short', 'password2': 'short'},
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 400
    assert 'at least 12' in resp.text.lower()

  def test_passwords_do_not_match_returns_400(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    wizard_val = _wizard_cookie({'step': 'password', 'raw_token': RAW_TOKEN, 'email': INVITE_EMAIL})
    resp = client.post(
      '/accept-invite',
      data={'password': 'ValidPassword123', 'password2': 'DifferentPassword456'},
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 400
    assert 'match' in resp.text.lower()

  def test_password_over_72_bytes_returns_400(self, tmp_path, monkeypatch):
    '''Review #9: route catches ValueError from hash_password, returns 400 not 500.'''
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    wizard_val = _wizard_cookie({'step': 'password', 'raw_token': RAW_TOKEN, 'email': INVITE_EMAIL})
    long_password = 'a' * 73
    resp = client.post(
      '/accept-invite',
      data={'password': long_password, 'password2': long_password},
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 400
    # NOT 500 server error
    assert resp.status_code != 500
    # Error message contains "72" or "too long" or "exceeds"
    body = resp.text.lower()
    assert '72' in body or 'too long' in body or 'exceeds' in body

  def test_valid_password_bcrypt_hashed_and_user_created(self, tmp_path, monkeypatch):
    '''POST with valid password: consume_and_create_user called, 302 to /enroll-totp,
    wizard cookie updated to step=totp, tsi_enroll cookie issued.'''
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    wizard_val = _wizard_cookie({'step': 'password', 'raw_token': RAW_TOKEN, 'email': INVITE_EMAIL})
    resp = client.post(
      '/accept-invite',
      data={'password': 'ValidPassword123!', 'password2': 'ValidPassword123!'},
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers.get('location') == '/enroll-totp'
    # Verify user created in auth.json
    data = json.loads(auth_path.read_text())
    users = data.get('users', [])
    new_users = [u for u in users if u.get('email') == INVITE_EMAIL]
    assert len(new_users) == 1
    pw_hash = new_users[0].get('password_hash', '')
    assert pw_hash.startswith('$2b$12$')
    # wizard cookie updated
    assert 'tsi_invite_wizard' in resp.cookies
    # tsi_enroll cookie issued
    assert 'tsi_enroll' in resp.cookies

  def test_post_without_wizard_cookie_redirects_to_login(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    resp = client.post(
      '/accept-invite',
      data={'password': 'ValidPassword123!', 'password2': 'ValidPassword123!'},
      follow_redirects=False,
    )
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('location', '')

  def test_post_with_wrong_step_in_cookie_redirects_to_login(self, tmp_path, monkeypatch):
    '''Cookie at step=device → 302 /login (step-skipping defense).'''
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    wizard_val = _wizard_cookie({'step': 'device', 'uid': 'some-uid', 'email': INVITE_EMAIL})
    resp = client.post(
      '/accept-invite',
      data={'password': 'ValidPassword123!', 'password2': 'ValidPassword123!'},
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('location', '')

  def test_tsi_enroll_carries_next_field_for_invite_wizard(self, tmp_path, monkeypatch):
    '''Review #6: POST step-1 success → decode tsi_enroll cookie → payload.next == /accept-invite/device.'''
    from itsdangerous.url_safe import URLSafeTimedSerializer
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    wizard_val = _wizard_cookie({'step': 'password', 'raw_token': RAW_TOKEN, 'email': INVITE_EMAIL})
    resp = client.post(
      '/accept-invite',
      data={'password': 'ValidPassword123!', 'password2': 'ValidPassword123!'},
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 302
    enroll_cookie_val = resp.cookies.get('tsi_enroll')
    assert enroll_cookie_val is not None
    s = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-enroll-cookie')
    payload = s.loads(enroll_cookie_val, max_age=600)
    assert payload.get('next') == '/accept-invite/device'


# ---------------------------------------------------------------------------
# TestStep3Device
# ---------------------------------------------------------------------------

class TestStep3Device:
  '''Step 3: trust device → optionally sets tsi_trusted, clears wizard cookie, 302 /.'''

  def test_trust_device_checkbox_sets_tsi_trusted_cookie(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    # First create a user in auth.json with a uid (simulate partial enrollment)
    data = json.loads(auth_path.read_text())
    test_uid = 'test-uid-abc123'
    data['users'].append({
      'uid': test_uid,
      'email': INVITE_EMAIL,
      'role': 'ff',
      'created_at': '2026-05-14T00:00:00+00:00',
      'disabled': False,
      'password_hash': '$2b$12$fakehash',
    })
    auth_path.write_text(json.dumps(data))
    wizard_val = _wizard_cookie({'step': 'device', 'uid': test_uid, 'email': INVITE_EMAIL})
    resp = client.post(
      '/accept-invite/device',
      data={'trust_device': '1'},
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers.get('location') == '/'
    # tsi_trusted cookie set
    assert 'tsi_trusted' in resp.cookies
    # tsi_invite_wizard deleted (Max-Age=0)
    set_cookies = resp.headers.get('set-cookie', '')
    # wizard cookie should be deleted (Max-Age=0 or absent from cookies)
    assert 'Max-Age=0' in set_cookies or 'tsi_invite_wizard' not in resp.cookies

  def test_no_trust_device_redirects_to_dashboard_only(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    test_uid = 'test-uid-abc123'
    data = json.loads(auth_path.read_text())
    data['users'].append({
      'uid': test_uid, 'email': INVITE_EMAIL, 'role': 'ff',
      'created_at': '2026-05-14T00:00:00+00:00', 'disabled': False, 'password_hash': '$2b$12$x',
    })
    auth_path.write_text(json.dumps(data))
    wizard_val = _wizard_cookie({'step': 'device', 'uid': test_uid, 'email': INVITE_EMAIL})
    resp = client.post(
      '/accept-invite/device',
      data={},
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers.get('location') == '/'
    # tsi_trusted NOT set
    assert 'tsi_trusted' not in resp.cookies

  def test_device_step_without_cookie_redirects_to_login(self, tmp_path, monkeypatch):
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    resp = client.post(
      '/accept-invite/device',
      data={'trust_device': '1'},
      follow_redirects=False,
    )
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('location', '')

  def test_get_device_step_with_totp_step_cookie_renders_step3(self, tmp_path, monkeypatch):
    '''GET /accept-invite/device with step=totp cookie → transition to step=device and render step-3 page.'''
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    test_uid = 'test-uid-abc123'
    wizard_val = _wizard_cookie({'step': 'totp', 'uid': test_uid, 'email': INVITE_EMAIL})
    resp = client.get(
      '/accept-invite/device',
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 200
    assert 'Trust this device' in resp.text
    assert 'Step 3 of 3' in resp.text


# ---------------------------------------------------------------------------
# TestRouteRegistration — Review #1
# ---------------------------------------------------------------------------

class TestRouteRegistration:
  '''Review #1: /accept-invite routes exist in the app route table.'''

  def test_accept_invite_routes_registered_on_app(self, tmp_path, monkeypatch):
    import sys
    import auth_store
    auth_path = _make_auth_json(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', VALID_USERNAME)
    monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', 'mwiriadi@gmail.com')
    monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', auth_path)
    sys.modules.pop('web.app', None)
    from web.app import create_app
    app = create_app()
    # Collect all route paths
    paths = []
    for route in app.routes:
      path = getattr(route, 'path', None)
      if path:
        paths.append(path)
    assert '/accept-invite' in paths, f'Missing /accept-invite in {paths}'
    assert '/accept-invite/device' in paths, f'Missing /accept-invite/device in {paths}'

  def test_invite_route_registered_before_auth_middleware(self):
    '''Review #1: invite_route.register line appears before add_middleware in web/app.py.'''
    src = open('web/app.py').read()
    import re
    reg = [m.start() for m in re.finditer(r'invite_route\.register', src)]
    mw = [m.start() for m in re.finditer(r'application\.add_middleware\(AuthMiddleware', src)]
    assert reg, 'invite_route.register not found in web/app.py'
    assert mw, 'application.add_middleware(AuthMiddleware not found in web/app.py'
    assert reg[0] < mw[0], (
      f'invite_route.register at pos {reg[0]} must precede add_middleware at pos {mw[0]}'
    )


# ---------------------------------------------------------------------------
# TestPartialEnrollmentRecovery — Review #2
# ---------------------------------------------------------------------------

class TestPartialEnrollmentRecovery:
  '''Review #2: partial enrollment (User row created, no TOTP) — documented degraded path.'''

  def test_reused_invite_token_after_user_created_renders_error_page(self, tmp_path, monkeypatch):
    '''Simulate partial enrollment: POST creates user but TOTP not completed.
    GET /accept-invite with same token returns 200 error page (token consumed).
    '''
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)

    # Step A: POST step-1 to create user
    wizard_val = _wizard_cookie({'step': 'password', 'raw_token': RAW_TOKEN, 'email': INVITE_EMAIL})
    resp = client.post(
      '/accept-invite',
      data={'password': 'ValidPassword123!', 'password2': 'ValidPassword123!'},
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 302  # user created

    # Verify user row exists in auth.json
    data = json.loads(auth_path.read_text())
    users = data.get('users', [])
    new_users = [u for u in users if u.get('email') == INVITE_EMAIL]
    assert len(new_users) == 1, 'User row should exist after step 1'
    # Verify user has password_hash but (simulated) no TOTP secret — that's handled by TOTP module
    pw_hash = new_users[0].get('password_hash')
    assert pw_hash and pw_hash.startswith('$2b$')

    # Step B: Skip TOTP enrollment (partial enrollment state)
    # Step C: GET /accept-invite again with same token — token is now consumed
    resp2 = client.get(f'/accept-invite?token={RAW_TOKEN}', follow_redirects=False)
    assert resp2.status_code == 200, 'Consumed token should return 200 error page'
    assert 'expired or has already been used' in resp2.text.lower() \
      or 'link expired' in resp2.text.lower()
    assert 'location' not in resp2.headers


# ---------------------------------------------------------------------------
# TestNextFieldForTOTPHandoff — Review #6
# ---------------------------------------------------------------------------

class TestNextFieldForTOTPHandoff:
  '''Review #6: tsi_enroll cookie carries next='/accept-invite/device' — zero TOTP coupling.'''

  def test_tsi_enroll_carries_next_field_for_invite_wizard(self, tmp_path, monkeypatch):
    '''POST step-1 success → decode tsi_enroll → assert payload['next'] == '/accept-invite/device'.'''
    from itsdangerous.url_safe import URLSafeTimedSerializer
    auth_path = _make_auth_json(tmp_path)
    client = _make_app_with_auth(tmp_path, auth_path, monkeypatch)
    wizard_val = _wizard_cookie({'step': 'password', 'raw_token': RAW_TOKEN, 'email': INVITE_EMAIL})
    resp = client.post(
      '/accept-invite',
      data={'password': 'ValidPassword123!', 'password2': 'ValidPassword123!'},
      cookies={'tsi_invite_wizard': wizard_val},
      follow_redirects=False,
    )
    assert resp.status_code == 302
    enroll_cookie_val = resp.cookies.get('tsi_enroll')
    assert enroll_cookie_val is not None, 'tsi_enroll cookie must be set'
    s = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-enroll-cookie')
    payload = s.loads(enroll_cookie_val, max_age=600)
    assert isinstance(payload, dict), 'tsi_enroll payload must be a dict'
    assert payload.get('next') == '/accept-invite/device', (
      f"tsi_enroll.next must be '/accept-invite/device', got {payload.get('next')!r}"
    )
    # Verify uid and email are present too
    assert 'uid' in payload
    assert payload.get('email') == INVITE_EMAIL

  def test_no_changes_to_totp_module(self):
    '''Review #6 acceptance: web/routes/totp/__init__.py NOT modified in this plan.'''
    import subprocess
    result = subprocess.run(
      ['git', 'diff', '--name-only', 'HEAD'],
      capture_output=True, text=True,
    )
    changed = result.stdout.strip().split('\n') if result.stdout.strip() else []
    totp_changes = [f for f in changed if 'web/routes/totp/__init__.py' in f]
    assert not totp_changes, (
      f'web/routes/totp/__init__.py should NOT be modified (review #6 zero-coupling). '
      f'Changed files: {totp_changes}'
    )
