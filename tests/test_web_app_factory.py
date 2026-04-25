'''Phase 13 D-16/D-17/D-21+/D-22 — create_app() factory contract tests.

Reference: 13-CONTEXT.md D-16..D-21, 13-RESEARCH.md §Pitfall 1
(openapi_url=None research extension D-22), 13-VALIDATION.md test-class
enumeration (lines 798-805).

Fixture strategy: tests use monkeypatch.setenv directly (not the shared
app_instance fixture) because TestSecretValidation needs to control the
env var BEFORE create_app() is called — the whole point of the test class
is asserting the failure modes.
'''
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Mirror conftest.py constants (single-source defined there for the autouse
# fixture; pytest's rootdir does NOT put tests/ on sys.path so we cannot
# `from conftest import ...`. The autouse fixture in conftest.py still runs
# before every test in this file because filename matches `test_web_*`).
VALID_SECRET = 'a' * 32  # mirror tests/conftest.py:VALID_SECRET (D-17 minimum)
AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'  # mirror tests/conftest.py:AUTH_HEADER_NAME


class TestSecretValidation:
  '''D-16/D-17: missing, empty, or <32-char WEB_AUTH_SECRET → RuntimeError at boot.'''

  def test_missing_secret_raises(self, monkeypatch):
    '''D-16: env var absent → RuntimeError mentioning WEB_AUTH_SECRET.'''
    monkeypatch.delenv('WEB_AUTH_SECRET', raising=False)
    # Reload web.app to retrigger create_app() at import — but factory tests
    # use direct create_app() invocation to avoid module-cache interference.
    import sys
    # Ensure web.app is freshly evaluated each call.
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='WEB_AUTH_SECRET'):
      from web.app import create_app
      create_app()

  def test_empty_secret_raises(self, monkeypatch):
    '''D-16: env var present but empty string → RuntimeError "missing or empty".'''
    monkeypatch.setenv('WEB_AUTH_SECRET', '')
    import sys
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='missing or empty'):
      from web.app import create_app
      create_app()

  def test_short_secret_raises(self, monkeypatch):
    '''D-17: env var shorter than 32 chars → RuntimeError mentioning 32.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 31)  # one char short of 32
    import sys
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='at least 32 characters'):
      from web.app import create_app
      create_app()

  def test_32_char_secret_accepted(self, monkeypatch):
    '''D-17: exactly 32 chars boots the app cleanly.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    import sys
    sys.modules.pop('web.app', None)
    from web.app import create_app
    app = create_app()
    assert app is not None
    # FastAPI exposes routes on .routes attribute — confirm the 3 we registered.
    paths = {r.path for r in app.routes if hasattr(r, 'path')}
    assert '/healthz' in paths
    assert '/' in paths
    assert '/api/state' in paths


class TestDocsDisabled:
  '''D-21 + D-22: /docs, /redoc, /openapi.json all suppressed.'''

  @pytest.fixture
  def client(self, monkeypatch):
    '''Local fixture (TestDocsDisabled-scoped) with valid secret pre-set.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    import sys
    sys.modules.pop('web.app', None)
    from web.app import create_app
    return TestClient(create_app())

  @pytest.fixture
  def auth_headers(self):
    return {AUTH_HEADER_NAME: VALID_SECRET}

  def test_docs_url_returns_404_with_auth(self, client, auth_headers):
    '''D-21: /docs is suppressed — even with valid auth, returns 404.'''
    r = client.get('/docs', headers=auth_headers)
    assert r.status_code == 404, (
      f'/docs should be 404 (D-21 suppression), got {r.status_code}'
    )

  def test_redoc_url_returns_404_with_auth(self, client, auth_headers):
    '''D-21: /redoc is suppressed — even with valid auth, returns 404.'''
    r = client.get('/redoc', headers=auth_headers)
    assert r.status_code == 404, (
      f'/redoc should be 404 (D-21 suppression), got {r.status_code}'
    )

  def test_openapi_json_returns_404_with_auth(self, client, auth_headers):
    '''D-22 (research extension to D-21): /openapi.json must be 404, not 200.

    Critical: docs_url=None + redoc_url=None alone DO NOT suppress
    /openapi.json — FastAPI keeps serving the schema there. The fix is
    openapi_url=None (passed at FastAPI() construction).
    '''
    r = client.get('/openapi.json', headers=auth_headers)
    assert r.status_code == 404, (
      f'/openapi.json should be 404 (D-22 suppression), got {r.status_code}. '
      'Without openapi_url=None, FastAPI keeps serving the full schema even '
      'when docs_url and redoc_url are disabled.'
    )

  def test_openapi_json_blocked_by_auth_when_unauthenticated(self, client):
    '''AuthMiddleware reaches /openapi.json BEFORE the 404 logic — proves order.

    Without auth header, the request gets 401 (from AuthMiddleware) rather
    than 404 (from FastAPI's missing-route). Confirms the middleware is
    registered correctly per D-06 (last-registered = first-dispatched).
    '''
    r = client.get('/openapi.json')  # no auth header
    assert r.status_code == 401, (
      f'/openapi.json without auth should be 401 (AuthMiddleware blocks first), '
      f'got {r.status_code}. If 404, the middleware is not reaching this path '
      f'(D-06 registration order issue).'
    )
