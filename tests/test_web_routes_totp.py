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
    r = client.get(
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
    r = client.post(
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
    r = client.post(
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
    r = client.get(
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
    r = client.post(
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
    r = client.post(
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
    r = client.get(
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


class TestQrCodeRenderedFromPyotpProvisioningUri:

  def test_qr_data_uri_present_and_secret_rendered_for_manual_entry(
    self, client, enroll_secret_seeded, valid_enroll_token,
  ):
    '''Lighter-weight than full QR-decode round-trip: assert the data-URI is
    a PNG-as-base64 prefix AND the manual-entry secret string is in the body.
    '''
    r = client.get(
      '/enroll-totp', cookies={'tsi_enroll': valid_enroll_token},
    )
    body = r.text
    assert 'data:image/png;base64,' in body
    assert KNOWN_SECRET in body
    # Provisioning URI shape sanity: account@domain present somewhere on the
    # page (the QR encodes the otpauth URI; the manual fallback shows the
    # secret + issuer label as well).
    assert 'Trading Signals' in body
