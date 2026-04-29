'''Phase 16.1 Plan 03 Task 3 — /reset-totp + /enroll-totp?reset=1 tests.

Covers (F-02 + E-07 + T-16.1-19/20/24/25):
  - TestResetTotpValidToken: valid unconsumed unexpired token → consume +
    tsi_session set + 302 /enroll-totp?reset=1 + Referrer-Policy
  - TestResetTotpExpiredToken: expired token → 401 + generic page; row not flipped
  - TestResetTotpConsumedToken: already-consumed token → 401 + generic page
  - TestResetTotpTamperedToken: tampered signature → 401 + generic page
  - TestResetTotpUnknownToken: signed but no matching row → 401 + generic page
  - TestResetTotpReferrerPolicy: success + failure both have Referrer-Policy: no-referrer
  - TestResetTotpRateLimit: 11th GET /reset-totp per IP/hour → 429 (or 302)
  - TestEnrollTotpResetMode: GET ?reset=1 renders Keep/New buttons; POST keep → /;
    POST new → fresh QR + new totp_secret (totp_enrolled flipped to False)

Reference: 16.1-03-PLAN.md Task 3; 16.1-CONTEXT.md F-02 / E-07.
'''
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from itsdangerous.url_safe import URLSafeTimedSerializer


VALID_SECRET = 'a' * 32
VALID_USERNAME = 'marc'


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


@pytest.fixture(autouse=True)
def _reset_rate_limit_buckets():
  '''Clear in-memory rate-limit dict between tests.'''
  import web.middleware.auth as auth_mw
  auth_mw._RATE_LIMIT_BUCKETS.clear()
  yield
  auth_mw._RATE_LIMIT_BUCKETS.clear()


def _make_signed_token(payload: dict | None = None) -> str:
  '''Build a magic-link token signed with the same salt used by the route.'''
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='magic-link')
  return serializer.dumps(payload or {'purpose': 'totp-reset', 'iat': int(time.time())})


def _seed_unconsumed_row(path: Path, token: str, **overrides):
  '''Pre-seed auth.json with a pending_magic_links row matching token's hash.'''
  import auth_store
  import hashlib
  from datetime import datetime, timedelta, timezone
  expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
  token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
  auth_store.add_magic_link(
    token_hash=token_hash,
    action='totp-reset',
    expires_at=overrides.get('expires_at', expires_at),
    email=overrides.get('email', 'mwiriadi@gmail.com'),
    path=path,
  )


# =============================================================================
# GET /reset-totp — happy path + failure modes
# =============================================================================


class TestResetTotpValidToken:

  def test_valid_unconsumed_unexpired_token_consumes_and_sets_session(
    self, client, fresh_auth_path,
  ):
    token = _make_signed_token()
    _seed_unconsumed_row(fresh_auth_path, token)

    r = client.get(f'/reset-totp?token={token}', follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get('location') == '/enroll-totp?reset=1'
    set_cookie = r.headers.get('set-cookie', '')
    # Cookie creation attrs match the canonical tsi_session shape.
    assert 'tsi_session=' in set_cookie
    assert 'Max-Age=43200' in set_cookie
    assert 'Path=/' in set_cookie
    assert 'Secure' in set_cookie
    assert 'HttpOnly' in set_cookie
    assert 'SameSite=Strict' in set_cookie
    # Row flipped to consumed=True.
    import auth_store
    rows = auth_store.load_auth(path=fresh_auth_path)['pending_magic_links']
    assert rows[0]['consumed'] is True
    assert rows[0]['consumed_at'] is not None


class TestResetTotpExpiredToken:

  def test_expired_token_returns_generic_invalid_page(
    self, client, fresh_auth_path, freezer,
  ):
    '''Token signed > 1 hour ago → SignatureExpired raised by itsdangerous
    (max_age=3600). The 'Reset link is no longer valid' page renders
    without leaking which failure mode (E-07).

    Uses pytest-freezer: freeze 2 hours ago to sign, then advance to now
    so itsdangerous.loads sees an expired signature.
    '''
    from datetime import datetime, timedelta, timezone
    # Sign the token 2 hours in the past.
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    freezer.move_to(past)
    token = _make_signed_token()
    _seed_unconsumed_row(fresh_auth_path, token)
    # Move clock back to 'now' — token's max_age=3600 has elapsed.
    freezer.move_to(past + timedelta(hours=2))
    r = client.get(f'/reset-totp?token={token}', follow_redirects=False)
    assert r.status_code == 401
    assert 'Reset link is no longer valid' in r.text
    # Row NOT flipped (expired path didn't consume).
    import auth_store
    rows = auth_store.load_auth(path=fresh_auth_path)['pending_magic_links']
    assert rows[0]['consumed'] is False


class TestResetTotpConsumedToken:

  def test_consumed_token_returns_generic_invalid_page(
    self, client, fresh_auth_path,
  ):
    token = _make_signed_token()
    _seed_unconsumed_row(fresh_auth_path, token)
    # First consume succeeds.
    r1 = client.get(f'/reset-totp?token={token}', follow_redirects=False)
    assert r1.status_code == 302
    # Second consume fails with generic page.
    r2 = client.get(f'/reset-totp?token={token}', follow_redirects=False)
    assert r2.status_code == 401
    assert 'Reset link is no longer valid' in r2.text


class TestResetTotpTamperedToken:

  def test_signature_mismatch_returns_generic_invalid_page(
    self, client, fresh_auth_path,
  ):
    token = _make_signed_token()
    _seed_unconsumed_row(fresh_auth_path, token)
    # Flip last char to break the signature.
    tampered = token[:-1] + ('A' if token[-1] != 'A' else 'B')
    r = client.get(f'/reset-totp?token={tampered}', follow_redirects=False)
    assert r.status_code == 401
    assert 'Reset link is no longer valid' in r.text


class TestResetTotpUnknownToken:

  def test_signed_token_with_no_matching_row_returns_generic_invalid_page(
    self, client, fresh_auth_path,
  ):
    '''Perfectly-signed token but no matching row in auth.json — server
    sha256-hashes the token, hash isn't in pending_magic_links, returns
    generic page. Guards the consume_magic_link unknown-hash path.
    '''
    token = _make_signed_token({'purpose': 'totp-reset', 'iat': int(time.time())})
    # No _seed_unconsumed_row call — auth.json has no matching hash.
    r = client.get(f'/reset-totp?token={token}', follow_redirects=False)
    assert r.status_code == 401
    assert 'Reset link is no longer valid' in r.text


class TestResetTotpReferrerPolicy:

  def test_success_response_includes_no_referrer_header(
    self, client, fresh_auth_path,
  ):
    '''T-16.1-25: Referrer-Policy: no-referrer prevents downstream link leak.'''
    token = _make_signed_token()
    _seed_unconsumed_row(fresh_auth_path, token)
    r = client.get(f'/reset-totp?token={token}', follow_redirects=False)
    assert r.headers.get('referrer-policy') == 'no-referrer'

  def test_invalid_response_includes_no_referrer_header(self, client):
    r = client.get('/reset-totp?token=garbage', follow_redirects=False)
    assert r.headers.get('referrer-policy') == 'no-referrer'


class TestResetTotpRateLimit:

  def test_11th_attempt_per_ip_per_hour_returns_429_or_302(self, client):
    '''F-08: 10 GET /reset-totp per hour per IP. 11th over-budget.'''
    for _ in range(10):
      r = client.get('/reset-totp?token=garbage', follow_redirects=False)
      # All 10 attempts return 401 (bad token).
      assert r.status_code == 401
    # 11th — over budget.
    r = client.get('/reset-totp?token=garbage', follow_redirects=False)
    assert r.status_code in (429, 302)


class TestResetTotpEmptyToken:

  def test_missing_token_returns_generic_invalid_page(self, client):
    r = client.get('/reset-totp', follow_redirects=False)
    assert r.status_code == 401
    assert 'Reset link is no longer valid' in r.text


# =============================================================================
# GET / POST /enroll-totp?reset=1 — operator chooses Keep or New
# =============================================================================


def _make_session_cookie() -> str:
  '''Build a tsi_session token as if /reset-totp had just consumed magic-link.'''
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-session-cookie')
  return serializer.dumps({'u': VALID_USERNAME, 'iat': int(time.time())})


class TestEnrollTotpResetMode:

  def test_get_enroll_totp_reset_renders_keep_or_new_buttons(
    self, client, fresh_auth_path,
  ):
    '''GET /enroll-totp?reset=1 with valid tsi_session → 200 + 2 buttons.'''
    session_cookie = _make_session_cookie()
    r = client.get(
      '/enroll-totp?reset=1',
      cookies={'tsi_session': session_cookie},
      follow_redirects=False,
    )
    assert r.status_code == 200
    assert 'Keep current authenticator' in r.text
    assert 'Set up new authenticator' in r.text
    # Both submit values present.
    assert 'value="keep"' in r.text
    assert 'value="new"' in r.text

  def test_get_enroll_totp_reset_without_session_redirects_to_login(
    self, client, fresh_auth_path,
  ):
    r = client.get('/enroll-totp?reset=1', follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get('location') == '/login'

  def test_post_keep_action_redirects_to_dashboard_unchanged(
    self, client, fresh_auth_path,
  ):
    '''POST keep → 302 / ; auth.json totp_secret unchanged.'''
    import auth_store
    auth_store.set_totp_secret('JBSWY3DPEHPK3PXP', path=fresh_auth_path)
    auth_store.mark_enrolled(path=fresh_auth_path)
    pre_secret = auth_store.get_totp_secret(path=fresh_auth_path)

    session_cookie = _make_session_cookie()
    r = client.post(
      '/enroll-totp?reset=1',
      data={'action': 'keep'},
      cookies={'tsi_session': session_cookie},
      follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get('location') == '/'
    post_secret = auth_store.get_totp_secret(path=fresh_auth_path)
    assert post_secret == pre_secret

  def test_post_new_action_regenerates_secret_renders_qr(
    self, client, fresh_auth_path,
  ):
    '''POST new → 200 (re-renders enroll page); auth.json.totp_secret changed.'''
    import auth_store
    auth_store.set_totp_secret('JBSWY3DPEHPK3PXP', path=fresh_auth_path)
    auth_store.mark_enrolled(path=fresh_auth_path)
    pre_secret = auth_store.get_totp_secret(path=fresh_auth_path)

    session_cookie = _make_session_cookie()
    r = client.post(
      '/enroll-totp?reset=1',
      data={'action': 'new'},
      cookies={'tsi_session': session_cookie},
      follow_redirects=False,
    )
    assert r.status_code == 200
    # Body has fresh QR enrollment page (Set up 2FA).
    assert 'Set up 2FA' in r.text
    post_data = auth_store.load_auth(path=fresh_auth_path)
    post_secret = post_data['totp_secret']
    assert post_secret != pre_secret
    # totp_enrolled flipped to False — operator must verify the new code.
    assert post_data['totp_enrolled'] is False
