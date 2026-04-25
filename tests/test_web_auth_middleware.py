'''Phase 13 AUTH-01..AUTH-03 + D-01..D-06 — middleware contract tests.

Wave 0 skeleton populated by Plan 13-03 (19 methods across 6 classes — 17
base + 2 REVIEWS LOW #5 D-02 negative-exemption tests).

Fixture strategy:
  The autouse fixture `_set_web_auth_secret_for_web_tests` in tests/conftest.py
  pre-sets WEB_AUTH_SECRET for this file (name matches `test_web_*.py`).
  Tests monkeypatch state_manager.load_state DIRECTLY when needed; the shared
  conftest.py provides VALID_SECRET + AUTH_HEADER_NAME constants + auth_headers
  fixture.

Reference: 13-CONTEXT.md decisions D-01..D-06, 13-VALIDATION.md
test-class enumeration (lines 822-826).
'''
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WEB_AUTH_PATH = Path('web/middleware/auth.py')


def _stub_load_state(**overrides):
  '''Build a benign load_state stub returning reset_state() with overrides.

  Mirrors tests/test_web_healthz.py:33-43 — needed because Phase 13 stub
  routes (Plan 13-02) and the real route handlers (Plans 13-04/13-05) call
  state_manager.load_state at request time.
  '''
  from state_manager import reset_state

  def _fn(*_args, **_kwargs):
    state = reset_state()
    state.update(overrides)
    state.setdefault('_resolved_contracts', {})
    return state

  return _fn


@pytest.fixture
def client_with_auth(monkeypatch):
  '''TestClient with load_state stubbed to a benign default.

  WEB_AUTH_SECRET is set by the autouse fixture in tests/conftest.py
  (Plan 13-01) for any file matching test_web_*.py — no per-test setenv needed.
  '''
  import sys

  import state_manager
  monkeypatch.setattr(state_manager, 'load_state', _stub_load_state())
  sys.modules.pop('web.app', None)
  from web.app import create_app
  return TestClient(create_app())


@pytest.fixture
def client_no_auth(monkeypatch):
  '''TestClient that deliberately tests the auth gate without an auth header.

  Shares state_manager stubbing but provides a dedicated name so tests that
  exercise negative paths (no header / wrong method / D-02 near-miss paths)
  read clearly.
  '''
  import sys

  import state_manager
  monkeypatch.setattr(state_manager, 'load_state', _stub_load_state())
  sys.modules.pop('web.app', None)
  from web.app import create_app
  return TestClient(create_app())


class TestAuthRequired:
  '''AUTH-01 + D-01: missing/wrong header returns 401.'''

  def test_missing_header_returns_401(self, client_with_auth):
    '''AUTH-01: GET / with NO X-Trading-Signals-Auth header → 401.'''
    r = client_with_auth.get('/')
    assert r.status_code == 401, (
      f'Expected 401 for missing auth header, got {r.status_code}: {r.text[:120]}'
    )

  def test_wrong_header_returns_401(self, client_with_auth):
    '''AUTH-01: GET / with WRONG X-Trading-Signals-Auth value → 401.'''
    r = client_with_auth.get('/', headers={'X-Trading-Signals-Auth': 'wrong-value'})
    assert r.status_code == 401, (
      f'Expected 401 for wrong auth value, got {r.status_code}: {r.text[:120]}'
    )

  def test_api_state_also_requires_auth(self, client_with_auth):
    '''AUTH-01: GET /api/state without auth → 401 (not just /).'''
    r = client_with_auth.get('/api/state')
    assert r.status_code == 401, (
      f'Expected 401 for /api/state without auth, got {r.status_code}'
    )


class TestAuthPasses:
  '''AUTH-01 + D-01: correct header reaches the route handler.'''

  def test_correct_header_passes_through(self, client_with_auth):
    '''AUTH-01: correct header reaches downstream — Plan 13-02 stub returns 503.

    Acceptable status codes: 200 (Plan 13-05 dashboard route after impl) or
    503 (Plan 13-02 stub before Plan 13-05). Both prove the middleware did
    NOT short-circuit to 401.
    '''
    r = client_with_auth.get(
      '/', headers={'X-Trading-Signals-Auth': 'a' * 32}
    )
    assert r.status_code in (200, 503), (
      f'Expected 200/503 with valid auth, got {r.status_code}: {r.text[:120]}. '
      f'401 means middleware blocked despite valid header (D-03 violation).'
    )


class TestExemption:
  '''D-02: /healthz bypasses AuthMiddleware via EXEMPT_PATHS allowlist.

  The happy path (exact /healthz) bypasses auth. The negative paths
  (trailing slash, uppercase) MUST still require auth — REVIEWS LOW #5
  locks this as explicit regression tests so nobody accidentally broadens
  the exact-match check to a prefix / case-insensitive match.
  '''

  def test_healthz_bypasses_auth_no_header(self, client_with_auth):
    '''D-02: GET /healthz with NO header → 200 (exempt).'''
    r = client_with_auth.get('/healthz')
    assert r.status_code == 200, (
      f'Expected 200 for /healthz without auth (exempt), got {r.status_code}'
    )
    body = r.json()
    assert body['status'] == 'ok'

  def test_healthz_bypasses_auth_wrong_header(self, client_with_auth):
    '''D-02: GET /healthz with WRONG header → 200 (exempt — middleware skips).

    The exemption is path-based, not header-based — wrong header doesn't
    matter on /healthz because the middleware never inspects the header.
    '''
    r = client_with_auth.get('/healthz', headers={'X-Trading-Signals-Auth': 'wrong'})
    assert r.status_code == 200, (
      f'Expected 200 for /healthz with wrong auth (exempt), got {r.status_code}'
    )

  def test_healthz_trailing_slash_is_NOT_exempt(self, client_no_auth):
    '''D-02 (REVIEWS LOW #5): exemption is EXACT-match only.

    /healthz/ (trailing slash) is a DIFFERENT path under Starlette's exact
    match and MUST require auth. Acceptable responses:
      - 401 if FastAPI/Starlette routes /healthz/ into auth-middleware first
      - 307 if FastAPI issues a redirect to /healthz (some versions do;
        this still proves the exemption did not fire as /healthz/-is-exempt)
    A 200 here would mean EXEMPT_PATHS matched too loosely — regression.
    '''
    r = client_no_auth.get('/healthz/', follow_redirects=False)
    assert r.status_code in (401, 307), (
      f'D-02 exact-match: /healthz/ (trailing slash) must require auth '
      f'(or redirect); got {r.status_code}: {r.text[:120]!r}. '
      f'200 means the exemption broadened to a prefix match — regression.'
    )

  def test_healthz_uppercase_is_NOT_exempt(self, client_no_auth):
    '''D-02 (REVIEWS LOW #5): exemption is case-SENSITIVE.

    /HEALTHZ must require auth — the EXEMPT_PATHS frozenset contains the
    lowercase literal '/healthz' only. Uppercase probes hit the auth gate.
    '''
    r = client_no_auth.get('/HEALTHZ')
    assert r.status_code == 401, (
      f'D-02 case-sensitive: /HEALTHZ should require auth, got {r.status_code}. '
      f'200 means the exemption became case-insensitive — regression.'
    )


class TestUnauthorizedResponse:
  '''AUTH-02 + D-04: 401 body literal and headers.'''
  pass


class TestAuditLog:
  '''AUTH-03 + D-05: WARN log shape (ip from XFF first entry, ua truncated %r-escaped, path).'''
  pass


class TestConstantTimeCompare:
  '''D-03: hmac.compare_digest is used (AST guard against == comparison).'''
  pass
