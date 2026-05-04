'''Phase 16.1 Plan 01 Task 3b — /enroll-totp + /verify-totp route tests.

Covers:
  - TestEnrollTotpGetGated: cookie-required gate; valid cookie renders QR + secret
  - TestEnrollTotpPostValidCode: TOTP code verifies → mark_enrolled + tsi_session
  - TestEnrollTotpPostInvalidCode: bad code re-renders with generic error
  - TestVerifyTotpGetGated / TestVerifyTotpPostValidCode / Invalid: same shape
  - TestVerifyTotpPostHasTrustDeviceCheckbox: markup stable for Plan 02
  - TestQrCodeRendered: QR data-URI present + manual secret string also rendered

Reference: 16.1-01-PLAN.md Task 3b; 16.1-CONTEXT.md E-03/E-04/F-04/F-05.
'''
from pathlib import Path

import pyotp
import pytest
from fastapi.testclient import TestClient


def _request_with_cookies(client, method, url, **kwargs):
  cookies = kwargs.pop('cookies', None)
  if cookies:
    headers = dict(kwargs.pop('headers', {}) or {})
    cookie_parts = [f'{name}={value}' for name, value in cookies.items()]
    existing_cookie = headers.get('cookie') or headers.get('Cookie')
    if existing_cookie:
      cookie_parts.insert(0, existing_cookie)
    headers['cookie'] = '; '.join(cookie_parts)
    kwargs['headers'] = headers
  return client.request(method, url, **kwargs)

KNOWN_SECRET = 'JBSWY3DPEHPK3PXP'  # Fixed for determinism + freezer compat


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


@pytest.fixture
def enroll_secret_seeded(fresh_auth_path):
  '''Pre-seed auth.json with KNOWN_SECRET, totp_enrolled=False (enroll path).'''
  import auth_store
  auth_store.set_totp_secret(KNOWN_SECRET, path=fresh_auth_path)
  return fresh_auth_path


@pytest.fixture
def verify_secret_seeded(fresh_auth_path):
  '''Pre-seed auth.json with KNOWN_SECRET, totp_enrolled=True (verify path).'''
  import auth_store
  auth_store.set_totp_secret(KNOWN_SECRET, path=fresh_auth_path)
  auth_store.mark_enrolled(path=fresh_auth_path)
  return fresh_auth_path


# =============================================================================
# /enroll-totp
# =============================================================================


class TestEnrollTotpGetGated:

  def test_no_tsi_enroll_cookie_returns_302_to_login(self, client):
    '''No tsi_enroll cookie → bounce back to /login (cookie's the gate).'''
    r = client.get('/enroll-totp', follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get('location', '').startswith('/login')

  def test_with_valid_tsi_enroll_renders_qr_and_secret(
    self, client, enroll_secret_seeded, valid_enroll_token,
  ):
    r = _request_with_cookies(client, 'GET', 
      '/enroll-totp', cookies={'tsi_enroll': valid_enroll_token},
    )
    assert r.status_code == 200
    body = r.text
    assert 'data:image/png;base64,' in body
    # Manual-entry fallback
    assert KNOWN_SECRET in body
    # 6-digit input
    assert 'inputmode="numeric"' in body
    assert 'autocomplete="one-time-code"' in body
    assert 'pattern="[0-9]{6}"' in body
    assert 'required' in body


class TestEnrollTotpPostValidCode:

  def test_valid_code_marks_enrolled_and_sets_session_cookie(
    self, client, enroll_secret_seeded, valid_enroll_token,
  ):
    import auth_store
    code = pyotp.TOTP(KNOWN_SECRET).now()
    r = _request_with_cookies(client, 'POST', 
      '/enroll-totp',
      cookies={'tsi_enroll': valid_enroll_token},
      data={'code': code},
      follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get('location') == '/'
    set_cookie = r.headers.get('set-cookie', '')
    assert 'tsi_session=' in set_cookie
    assert 'Max-Age=43200' in set_cookie
    assert 'Path=/' in set_cookie
    assert 'Secure' in set_cookie
    assert 'HttpOnly' in set_cookie
    assert 'SameSite=Strict' in set_cookie
    # tsi_enroll deleted (attrs match creation)
    assert 'tsi_enroll=;' in set_cookie or 'tsi_enroll=,' in set_cookie or 'tsi_enroll=' in set_cookie
    # auth.json now totp_enrolled=True
    assert auth_store.load_auth(path=enroll_secret_seeded)['totp_enrolled'] is True


class TestEnrollTotpPostInvalidCode:

  def test_invalid_code_re_renders_with_generic_error(
    self, client, enroll_secret_seeded, valid_enroll_token,
  ):
    import auth_store
    r = _request_with_cookies(client, 'POST', 
      '/enroll-totp',
      cookies={'tsi_enroll': valid_enroll_token},
      data={'code': '000000'},
      follow_redirects=False,
    )
    assert r.status_code == 200
    assert "Code didn" in r.text and 'try again' in r.text
    # auth.json still NOT enrolled
    assert auth_store.load_auth(path=enroll_secret_seeded)['totp_enrolled'] is False


# =============================================================================
# /verify-totp
# =============================================================================


class TestVerifyTotpGetGated:

  def test_no_tsi_pending_cookie_returns_302_to_login(self, client):
    r = client.get('/verify-totp', follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get('location', '').startswith('/login')

  def test_with_valid_tsi_pending_renders_form(
    self, client, verify_secret_seeded, valid_pending_token,
  ):
    r = _request_with_cookies(client, 'GET', 
      '/verify-totp', cookies={'tsi_pending': valid_pending_token},
    )
    assert r.status_code == 200
    body = r.text
    assert 'inputmode="numeric"' in body
    assert 'autocomplete="one-time-code"' in body


class TestVerifyTotpPostValidCode:

  def test_valid_code_sets_session_cookie(
    self, client, verify_secret_seeded, valid_pending_token,
  ):
    code = pyotp.TOTP(KNOWN_SECRET).now()
    r = _request_with_cookies(client, 'POST', 
      '/verify-totp',
      cookies={'tsi_pending': valid_pending_token},
      data={'code': code},
      follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get('location') == '/'
    set_cookie = r.headers.get('set-cookie', '')
    assert 'tsi_session=' in set_cookie
    assert 'Max-Age=43200' in set_cookie


class TestVerifyTotpPostInvalidCode:

  def test_invalid_code_re_renders(
    self, client, verify_secret_seeded, valid_pending_token,
  ):
    r = _request_with_cookies(client, 'POST', 
      '/verify-totp',
      cookies={'tsi_pending': valid_pending_token},
      data={'code': '000000'},
      follow_redirects=False,
    )
    assert r.status_code == 200
    assert "Code didn" in r.text and 'try again' in r.text


class TestVerifyTotpPostHasTrustDeviceCheckbox:

  def test_form_has_trust_checkbox_default_unchecked(
    self, client, verify_secret_seeded, valid_pending_token,
  ):
    '''Plan 02 wires the checkbox; Plan 01 just renders stable markup.'''
    r = _request_with_cookies(client, 'GET', 
      '/verify-totp', cookies={'tsi_pending': valid_pending_token},
    )
    body = r.text
    assert 'type="checkbox"' in body
    assert 'name="trust_device"' in body
    # Default UNCHECKED — must NOT have a `checked` attribute on the input
    # (string-level grep is fine; we constructed the markup ourselves).
    import re
    checkbox_match = re.search(
      r'<input[^>]*name="trust_device"[^>]*>', body,
    )
    assert checkbox_match is not None
    assert ' checked' not in checkbox_match.group(0)


# =============================================================================
# Phase 16.1 Plan 02 — trust_device checkbox issues tsi_trusted cookie
# =============================================================================


class TestVerifyTotpTrustDeviceFlow:
  '''POST /verify-totp + trust_device='on' issues tsi_trusted cookie + persists
  trusted_devices row in auth.json. Unchecked path is unchanged from Plan 01.
  '''

  def _extract_set_cookies(self, response):
    '''Return list of all Set-Cookie header values (Starlette's TestClient
    consolidates multi-Set-Cookie via response.headers.raw).'''
    raw = getattr(response, 'raw_headers', None)
    if raw is None:
      raw = getattr(response.headers, 'raw', None)
    cookies = []
    if raw is not None:
      for name, value in raw:
        if name.lower() == b'set-cookie':
          cookies.append(value.decode('latin-1'))
    if not cookies:
      # Fallback to combined string
      combined = response.headers.get('set-cookie', '')
      if combined:
        cookies = [combined]
    return cookies

  def test_trust_device_checked_issues_tsi_trusted_cookie(
    self, client, verify_secret_seeded, valid_pending_token,
  ):
    import auth_store
    code = pyotp.TOTP(KNOWN_SECRET).now()
    pre_devices = auth_store.load_auth(path=verify_secret_seeded)['trusted_devices']
    assert len(pre_devices) == 0

    r = _request_with_cookies(client, 'POST', 
      '/verify-totp',
      cookies={'tsi_pending': valid_pending_token},
      data={'code': code, 'trust_device': 'on'},
      follow_redirects=False,
    )
    assert r.status_code == 302
    set_cookies = self._extract_set_cookies(r)
    combined = '\n'.join(set_cookies)
    assert 'tsi_session=' in combined, f'Missing tsi_session: {set_cookies}'
    assert 'tsi_trusted=' in combined, f'Missing tsi_trusted: {set_cookies}'
    assert 'Max-Age=43200' in combined  # tsi_session
    assert 'Max-Age=2592000' in combined  # tsi_trusted (30 days)
    # Cookie attrs match E-05 verbatim
    trusted_line = next(s for s in set_cookies if s.startswith('tsi_trusted='))
    for attr in ('Max-Age=2592000', 'Path=/', 'Secure', 'HttpOnly', 'SameSite=Strict'):
      assert attr in trusted_line, (
        f'tsi_trusted missing {attr!r}: {trusted_line!r}'
      )

    # Persisted exactly one row
    post_devices = auth_store.load_auth(path=verify_secret_seeded)['trusted_devices']
    assert len(post_devices) == 1
    row = post_devices[0]
    assert row['revoked'] is False

  def test_trust_device_unchecked_does_NOT_issue_tsi_trusted(
    self, client, verify_secret_seeded, valid_pending_token,
  ):
    import auth_store
    code = pyotp.TOTP(KNOWN_SECRET).now()
    r = _request_with_cookies(client, 'POST', 
      '/verify-totp',
      cookies={'tsi_pending': valid_pending_token},
      data={'code': code},  # trust_device omitted (default '')
      follow_redirects=False,
    )
    assert r.status_code == 302
    set_cookies = self._extract_set_cookies(r)
    combined = '\n'.join(set_cookies)
    assert 'tsi_session=' in combined
    assert 'tsi_trusted=' not in combined, (
      f'Unchecked path must NOT issue tsi_trusted: {set_cookies}'
    )
    devices = auth_store.load_auth(path=verify_secret_seeded)['trusted_devices']
    assert devices == []

  def test_trust_device_label_includes_browser_ip_date(
    self, client, verify_secret_seeded,
  ):
    import auth_store
    import time as _time
    from freezegun import freeze_time
    from itsdangerous.url_safe import URLSafeTimedSerializer
    iphone_ua = (
      'Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) '
      'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 '
      'Mobile/15E148 Safari/604.1'
    )
    # Build the tsi_pending cookie under the same frozen clock so its iat
    # falls inside the 10-min max_age window when the POST runs.
    with freeze_time('2026-04-29T00:00:00+00:00'):
      ser = URLSafeTimedSerializer('a' * 32, salt='tsi-pending-cookie')
      pending_token = ser.dumps({
        'u': 'marc', 'iat': int(_time.time()), 'next': '/', 'pwd_ok': True,
      })
      code = pyotp.TOTP(KNOWN_SECRET).now()
      r = _request_with_cookies(client, 'POST', 
        '/verify-totp',
        cookies={'tsi_pending': pending_token},
        data={'code': code, 'trust_device': 'on'},
        headers={
          'User-Agent': iphone_ua,
          'X-Forwarded-For': '203.0.113.42',
        },
        follow_redirects=False,
      )
    assert r.status_code == 302
    devices = auth_store.load_auth(path=verify_secret_seeded)['trusted_devices']
    assert len(devices) == 1
    label = devices[0]['label']
    assert 'iPhone Safari' in label, f'Label missing iPhone Safari: {label!r}'
    assert '203.0.113.x' in label, f'Label missing IP first-3-octets: {label!r}'
    assert '2026-04-29' in label, f'Label missing date: {label!r}'

  def test_trust_device_unknown_user_agent_falls_back_to_unknown_device_label(
    self, client, verify_secret_seeded, valid_pending_token,
  ):
    import auth_store
    code = pyotp.TOTP(KNOWN_SECRET).now()
    r = _request_with_cookies(client, 'POST', 
      '/verify-totp',
      cookies={'tsi_pending': valid_pending_token},
      data={'code': code, 'trust_device': 'on'},
      headers={'User-Agent': 'weird-bot/1.0'},
      follow_redirects=False,
    )
    assert r.status_code == 302
    devices = auth_store.load_auth(path=verify_secret_seeded)['trusted_devices']
    assert devices[0]['label'].startswith('Unknown device')

  def test_trust_device_label_handles_missing_xff(
    self, client, verify_secret_seeded,
  ):
    import auth_store
    import time as _time
    from freezegun import freeze_time
    from itsdangerous.url_safe import URLSafeTimedSerializer
    with freeze_time('2026-04-29T00:00:00+00:00'):
      ser = URLSafeTimedSerializer('a' * 32, salt='tsi-pending-cookie')
      pending_token = ser.dumps({
        'u': 'marc', 'iat': int(_time.time()), 'next': '/', 'pwd_ok': True,
      })
      code = pyotp.TOTP(KNOWN_SECRET).now()
      r = _request_with_cookies(
        client,
        'POST',
        '/verify-totp',
        cookies={'tsi_pending': pending_token},
        data={'code': code, 'trust_device': 'on'},
        # No X-Forwarded-For; TestClient's client.host = 'testclient'
        follow_redirects=False,
      )
    assert r.status_code == 302
    devices = auth_store.load_auth(path=verify_secret_seeded)['trusted_devices']
    label = devices[0]['label']
    assert label  # non-empty
    assert '2026-04-29' in label, f'Label missing date: {label!r}'

  def test_tsi_trusted_cookie_payload_carries_uuid_only_no_username(
    self, client, verify_secret_seeded, valid_pending_token,
  ):
    import auth_store
    from itsdangerous.url_safe import URLSafeTimedSerializer
    code = pyotp.TOTP(KNOWN_SECRET).now()
    r = _request_with_cookies(
      client,
      'POST',
      '/verify-totp',
      cookies={'tsi_pending': valid_pending_token},
      data={'code': code, 'trust_device': 'on'},
      follow_redirects=False,
    )
    set_cookies = self._extract_set_cookies(r)
    trusted_line = next(s for s in set_cookies if s.startswith('tsi_trusted='))
    # Extract token between 'tsi_trusted=' and the next ';'
    token = trusted_line.split('tsi_trusted=', 1)[1].split(';', 1)[0]
    serializer = URLSafeTimedSerializer('a' * 32, salt='tsi-trusted-cookie')
    payload = serializer.loads(token, max_age=2592000)
    assert isinstance(payload, dict)
    assert 'uuid' in payload
    assert 'iat' in payload
    assert 'u' not in payload, (
      'tsi_trusted payload must NOT contain username — device is the trust unit'
    )
    # Persisted row's uuid matches the cookie payload
    devices = auth_store.load_auth(path=verify_secret_seeded)['trusted_devices']
    assert payload['uuid'] == devices[0]['uuid']


class TestQrCodeRenderedFromPyotpProvisioningUri:

  def test_qr_data_uri_present_and_secret_rendered_for_manual_entry(
    self, client, enroll_secret_seeded, valid_enroll_token,
  ):
    '''Lighter-weight than full QR-decode round-trip: assert the data-URI is
    a PNG-as-base64 prefix AND the manual-entry secret string is in the body.
    '''
    r = _request_with_cookies(
      client,
      'GET',
      '/enroll-totp',
      cookies={'tsi_enroll': valid_enroll_token},
    )
    body = r.text
    assert 'data:image/png;base64,' in body
    assert KNOWN_SECRET in body
    # Provisioning URI shape sanity: account@domain present somewhere on the
    # page (the QR encodes the otpauth URI; the manual fallback shows the
    # secret + issuer label as well).
    assert 'Trading Signals' in body
