'''Shared pytest fixtures for tests/.

Phase 13 introduces the WEB_AUTH_SECRET requirement at create_app() time
(D-16/D-17 fail-closed). All web-tier tests need a sentinel secret set
BEFORE create_app() is invoked, otherwise create_app() raises RuntimeError.

The `_set_web_auth_secret_for_web_tests` autouse fixture (REVIEWS HIGH fix)
runs before every test in any file matching test_web_*.py and sets the env
var. This covers:
  - The Phase 11 `app_instance` fixture at tests/test_web_healthz.py:22
  - The 11 direct create_app() invocations in tests/test_web_healthz.py
    test bodies at lines 70, 83, 90, 105, 115, 126, 133, 148, 159, 172
  - All Phase 13 web test files (auth_middleware, dashboard, state, app_factory)

Tests that INTENTIONALLY test the missing-secret path (e.g. TestSecretValidation
in tests/test_web_app_factory.py) call `monkeypatch.delenv('WEB_AUTH_SECRET',
raising=False)` themselves — pytest's function-scoped monkeypatch applies
finalizers in LIFO order, so the test's delenv runs after the autouse setenv
(same-scope teardown), effectively overriding the autouse default.

Single source of truth (REVIEWS LOW #6):
  VALID_SECRET is defined ONCE here. Test files import it from conftest
  rather than redefining the constant.
'''
import pytest

# Phase 13 D-17: 32 chars meets the minimum-length check
# (≈128 bits of entropy via openssl rand -hex 16).
VALID_SECRET = 'a' * 32

# Phase 13 AUTH-01: header name (single source of truth across all web tests).
AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'


@pytest.fixture(autouse=True)
def _set_web_auth_secret_for_web_tests(monkeypatch, request):
  '''Phase 13 D-16/D-17 REVIEWS HIGH fix.

  create_app() raises RuntimeError if WEB_AUTH_SECRET is missing/short
  (Plan 13-02). This autouse fixture runs before every test in ANY file
  matching test_web_*.py and supplies a valid 32-char sentinel secret,
  so existing Phase 11 healthz tests (which call create_app() directly
  in test bodies) and new Phase 13 tests all see the env var set.

  Tests that intentionally test the missing-secret path (e.g.
  TestSecretValidation in tests/test_web_app_factory.py) call
  monkeypatch.delenv('WEB_AUTH_SECRET', raising=False) themselves to
  override the autouse default — pytest's monkeypatch teardown is
  function-scoped and LIFO, so delenv after setenv within a single test
  behaves as expected.
  '''
  if 'test_web_' in str(request.node.fspath):
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)


@pytest.fixture
def valid_secret() -> str:
  '''Phase 13: 32-char sentinel that passes D-17 minimum-length check.'''
  return VALID_SECRET


@pytest.fixture
def auth_headers(valid_secret) -> dict:
  '''Phase 13 AUTH-01: header dict for authorized TestClient requests.'''
  return {AUTH_HEADER_NAME: valid_secret}
