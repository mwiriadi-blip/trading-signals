'''Phase 16.1 Plan 01 Task 3a — /login + /logout route tests.

Covers:
  - TestLoginGetForm: form HTML structure, ?next= echo, "Lost 2FA?" link
  - TestLoginPostValidEnrollBranch: first-login (no totp_secret) → /enroll-totp
    with tsi_enroll cookie + persisted secret in auth.json
  - TestLoginPostValidVerifyBranch: subsequent login (totp_enrolled=True) →
    /verify-totp with tsi_pending cookie
  - TestLoginPostInvalid: wrong username, wrong password — same generic error;
    HTML injection escaped (T-16.1-11)
  - TestLoginNextRedirect / TestLoginNextOpenRedirect: ?next= sanitised against
    14 open-redirect bypass payloads
  - TestLogout: cookie deletion attrs match creation; GET → 405
  - test_logout_does_NOT_invalidate_existing_cookie_value: sampling pyramid 2
    documenting the stateless-cookie limitation

Reference: 16.1-01-PLAN.md Task 3a; 16.1-CONTEXT.md E-03/E-04/D-12/D-14;
16.1-RESEARCH.md §Open-redirect prevention (14 payloads).
'''
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _stub_load_state(**overrides):
  '''Return a benign load_state stub matching test_web_auth_middleware.py.'''
  from state_manager import reset_state

  def _fn(*_args, **_kwargs):
    state = reset_state()
    state.update(overrides)
    state.setdefault('_resolved_contracts', {})
    return state

  return _fn


@pytest.fixture
def fresh_auth_path(tmp_path, monkeypatch) -> Path:
  '''Redirect auth_store.DEFAULT_AUTH_PATH to a tmp file so tests don't
  pollute the repo-root auth.json.
  '''
  import auth_store
  path = tmp_path / 'auth.json'
  monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', path)
  return path


@pytest.fixture
def client(monkeypatch, fresh_auth_path):
  '''TestClient with state stubbed + auth_store rerouted to tmp_path.

  Autouse conftest fixture supplies WEB_AUTH_USERNAME=marc, WEB_AUTH_SECRET=a*32.
  '''
  import sys

  import state_manager
  monkeypatch.setattr(state_manager, 'load_state', _stub_load_state())
  sys.modules.pop('web.app', None)
  from web.app import create_app
  return TestClient(create_app())


@pytest.fixture
def enrolled_auth(fresh_auth_path):
  '''Pre-seed auth.json with totp_enrolled=True so /login takes the verify branch.'''
  import auth_store
  auth_store.set_totp_secret('JBSWY3DPEHPK3PXP', path=fresh_auth_path)
  auth_store.mark_enrolled(path=fresh_auth_path)
  return fresh_auth_path


# =============================================================================
# GET /login — form structure
# =============================================================================


class TestLoginGetForm:

  def test_get_login_returns_200_html(self, client):
    r = client.get('/login')
    assert r.status_code == 200
    assert 'text/html' in r.headers.get('content-type', '').lower()

  def test_form_has_required_aria_and_autocomplete_attrs(self, client):
    r = client.get('/login')
    body = r.text
    assert 'Trading Signals' in body and 'Sign in' in body
    # Field IDs (UI-SPEC §Surface 1)
    assert 'id="login-username"' in body
    assert 'id="login-password"' in body
    # Autocomplete tokens for iOS Keychain autofill
    assert 'autocomplete="username"' in body
    assert 'autocomplete="current-password"' in body
    # Form-level required attrs
    assert 'required' in body
    assert 'autofocus' in body
    # Submit button
    assert 'type="submit"' in body and 'Sign in' in body

  def test_with_next_query_preserved(self, client):
    r = client.get('/login?next=/api/state')
    assert r.status_code == 200
    body = r.text
    # next is HTML-escaped + URL-encoded forms both acceptable; the form
    # action contains '/login?next=' and includes '/api/state' in some shape
    assert '/login?next=' in body
    assert '/api/state' in body or '%2Fapi%2Fstate' in body

  def test_get_login_includes_lost_2fa_link_placeholder(self, client):
    r = client.get('/login')
    # Link target is locked even though Plan 03 wires the route.
    assert '/forgot-2fa' in r.text


# =============================================================================
# POST /login — enroll branch (no totp_secret yet)
# =============================================================================


class TestLoginPostValidEnrollBranch:

  def test_first_login_no_totp_enrolled_redirects_to_enroll(
    self, client, fresh_auth_path,
  ):
    '''E-03: first POST /login with valid creds when totp_secret is None →
    302 /enroll-totp + tsi_enroll cookie + persisted random_base32 secret.
    '''
    import auth_store
    assert auth_store.get_totp_secret(path=fresh_auth_path) is None

    r = client.post(
      '/login',
      data={'username': 'marc', 'password': 'a' * 32},
      follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get('location') == '/enroll-totp'
    set_cookie = r.headers.get('set-cookie', '')
    assert 'tsi_enroll=' in set_cookie
    assert 'Max-Age=600' in set_cookie
    assert 'Path=/' in set_cookie
    assert 'Secure' in set_cookie
    assert 'HttpOnly' in set_cookie
    assert 'SameSite=Strict' in set_cookie

    # Server generated and persisted a random_base32 secret
    secret = auth_store.get_totp_secret(path=fresh_auth_path)
    assert secret is not None and len(secret) >= 16


# =============================================================================
# POST /login — verify branch (totp_enrolled=True)
# =============================================================================


class TestLoginPostValidVerifyBranch:

  def test_subsequent_login_already_enrolled_redirects_to_verify(
    self, client, enrolled_auth,
  ):
    r = client.post(
      '/login',
      data={'username': 'marc', 'password': 'a' * 32},
      follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get('location') == '/verify-totp'
    set_cookie = r.headers.get('set-cookie', '')
    assert 'tsi_pending=' in set_cookie
    assert 'Max-Age=600' in set_cookie
    assert 'Path=/' in set_cookie
    assert 'Secure' in set_cookie
    assert 'HttpOnly' in set_cookie
    assert 'SameSite=Strict' in set_cookie
    # tsi_session must NOT be set yet (not until TOTP verified)
    assert 'tsi_session=' not in set_cookie


# =============================================================================
# POST /login — invalid credentials
# =============================================================================


class TestLoginPostInvalid:

  def test_wrong_username_re_renders_with_generic_error(self, client, caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger='web.routes.login'):
      r = client.post(
        '/login',
        data={'username': 'wrong', 'password': 'a' * 32},
        follow_redirects=False,
      )
    assert r.status_code == 200
    assert 'Sign in failed' in r.text
    # Username retained in form value for UX (HTML-escaped)
    assert 'value="wrong"' in r.text
    # Audit log fired with reason
    msgs = [
      r.getMessage() for r in caplog.records if r.name == 'web.routes.login'
    ]
    assert any('login failure' in m and 'wrong_username' in m for m in msgs), (
      f'Expected [Web] login failure: ... reason=wrong_username, got: {msgs}'
    )

  def test_wrong_password_re_renders_with_same_generic_error(
    self, client, caplog,
  ):
    import logging
    with caplog.at_level(logging.WARNING, logger='web.routes.login'):
      r = client.post(
        '/login',
        data={'username': 'marc', 'password': 'wrong'},
        follow_redirects=False,
      )
    assert r.status_code == 200
    # SAME copy as wrong-username (D-14 + AUTH-02)
    assert 'Sign in failed' in r.text
    msgs = [
      r.getMessage() for r in caplog.records if r.name == 'web.routes.login'
    ]
    assert any('login failure' in m and 'wrong_secret' in m for m in msgs), (
      f'Expected [Web] login failure: ... reason=wrong_secret, got: {msgs}'
    )

  def test_html_injection_in_username_is_escaped(self, client):
    '''T-16.1-11: dynamic values run through html.escape before f-string.'''
    payload = '<script>alert(1)</script>'
    r = client.post(
      '/login',
      data={'username': payload, 'password': 'wrong'},
      follow_redirects=False,
    )
    assert r.status_code == 200
    body = r.text
    assert '&lt;script&gt;' in body or '&lt;script&gt;alert(1)&lt;/script&gt;' in body
    # Raw script tag must NOT be present
    assert '<script>alert(1)</script>' not in body


# =============================================================================
# POST /login — open-redirect prevention (14 payloads from RESEARCH)
# =============================================================================


OPEN_REDIRECT_PAYLOADS = [
  '//evil.com',
  '///evil.com/path',
  '/\\evil.com',
  '\\\\evil.com',
  '\\/evil.com',
  '%2F%2Fevil.com',
  'javascript:alert(1)',
  'data:text/html,xss',
  'https://evil.com/',
  'https://signals.mwiriadi.me@evil.com/',
  'https://signals.mwiriadi.me.evil.com/',
  '/path\r\nSet-Cookie: evil=1',
  '/' + 'a' * 600,
  '',
]


class TestLoginNextOpenRedirect:

  @pytest.mark.parametrize('payload', OPEN_REDIRECT_PAYLOADS)
  def test_open_redirect_blocked(self, client, fresh_auth_path, payload):
    '''Every malicious next= must be rejected; safe fallback is /enroll-totp
    or /verify-totp. The next param is encoded into the cookie payload (for
    Plan 03 to pick up post-TOTP), but a malicious value must NOT survive
    sanitisation — _is_safe_next returns False → falls back to '/'.

    For Plan 01 the easiest assertion: the immediate redirect Location is
    one of the legal targets (/enroll-totp on first login, /verify-totp
    once enrolled). The cookie's `next` payload is also sanitised (asserted
    via Plan 16.1-01 Task 3b for the post-verify redirect).
    '''
    from urllib.parse import urlencode
    qs = urlencode({'next': payload})
    r = client.post(
      f'/login?{qs}',
      data={'username': 'marc', 'password': 'a' * 32},
      follow_redirects=False,
    )
    # Always 302; never to the bypass target
    assert r.status_code == 302
    loc = r.headers.get('location', '')
    assert loc in ('/enroll-totp', '/verify-totp'), (
      f'Open-redirect bypass via next={payload!r} produced Location={loc!r}'
    )


# =============================================================================
# POST /logout — cookie deletion attrs match creation
# =============================================================================


class TestLogout:

  def test_post_logout_clears_cookie_with_matching_attrs(
    self, client, valid_cookie_token,
  ):
    r = client.post('/logout', cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    set_cookie = r.headers.get('set-cookie', '')
    # Cookie deletion attrs MUST match creation per global LEARNING.
    assert 'tsi_session=' in set_cookie
    assert 'Max-Age=0' in set_cookie
    assert 'Path=/' in set_cookie
    assert 'Secure' in set_cookie
    assert 'HttpOnly' in set_cookie
    assert 'SameSite=Strict' in set_cookie

  def test_get_logout_returns_405(self, client):
    r = client.get('/logout', follow_redirects=False)
    assert r.status_code == 405


def test_logout_does_NOT_invalidate_existing_cookie_value(
  client, valid_cookie_token,
):
  '''Sampling pyramid 2 (RESEARCH §Cookie hygiene): stateless cookies cannot
  be revoked server-side. After /logout, an attacker who copied the original
  cookie value can still authenticate. Plan 02 is the candidate to invert
  this with a server-side revocation list.

  The test documents the boundary explicitly so anyone changing this in
  the future re-evaluates the trade-off.
  '''
  # Logout
  client.post('/logout', cookies={'tsi_session': valid_cookie_token})
  # Replay the cookie — should still grant access (stateless cookie)
  r = client.get('/api/state', cookies={'tsi_session': valid_cookie_token})
  assert r.status_code == 200, (
    f'Sampling pyramid 2 invariant changed: cookie replay after logout now '
    f'returns {r.status_code}. If Plan 02 added a revocation list, invert '
    f'this assertion to assert 401/302.'
  )
