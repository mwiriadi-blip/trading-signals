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
import time

import pytest

# Phase 13 D-17: 32 chars meets the minimum-length check
# (≈128 bits of entropy via openssl rand -hex 16).
VALID_SECRET = 'a' * 32

# Phase 16.1 D-08: sentinel username — non-empty, no ':' character.
VALID_USERNAME = 'marc'

# Phase 13 AUTH-01: header name (single source of truth across all web tests).
AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'


@pytest.fixture(autouse=True)
def _set_web_auth_credentials_for_web_tests(monkeypatch, request):
  '''Phase 13 D-16/D-17 + Phase 16.1 D-08 REVIEWS HIGH fix.

  create_app() raises RuntimeError if WEB_AUTH_SECRET or WEB_AUTH_USERNAME is
  missing/short (Plan 13-02 + Plan 16.1-01). This autouse fixture runs before
  every test in any file matching test_web_*.py OR test_auth_store_*.py and
  supplies the valid sentinel credentials. This covers:
    - The Phase 11 `app_instance` fixture at tests/test_web_healthz.py:22
    - The 11 direct create_app() invocations in tests/test_web_healthz.py
    - All Phase 13/14/16.1 web test files (auth_middleware, dashboard, state,
      app_factory, trades, routes_login, routes_totp)
    - Phase 16.1 auth_store tests (rely on env vars only via fixture flow-through)

  Tests that intentionally test the missing-credential path (e.g.
  TestSecretValidation, TestUsernameValidation in tests/test_web_app_factory.py)
  call `monkeypatch.delenv(...)` themselves — pytest's function-scoped
  monkeypatch applies finalizers in LIFO order, so the test's delenv runs
  AFTER the autouse setenv (same-scope teardown), effectively overriding
  the autouse default.

  Single source of truth (REVIEWS LOW #6):
    VALID_SECRET and VALID_USERNAME are defined ONCE here. Test files import
    them from conftest rather than redefining the constants.
  '''
  fspath = str(request.node.fspath)
  if 'test_web_' in fspath or 'test_auth_store' in fspath:
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', VALID_USERNAME)


# =============================================================================
# Phase 16.1 — signed-cookie token fixtures (Plan 16.1-01)
# =============================================================================
#
# Build tokens via the SAME serializer the production middleware uses
# (URLSafeTimedSerializer with the matching salt and the VALID_SECRET).
# Salts mirror system_params.TSI_*_SALT verbatim — alignment per LEARNING
# 2026-04-27 (grep-discoverability of cookie name + cookie salt as a unit).


@pytest.fixture
def valid_cookie_token() -> str:
  '''Phase 16.1: tsi_session-shaped signed token built with VALID_SECRET.

  Mirrors the production cookie payload {'u': username, 'iat': now} per
  Plan 16.1-01 D-10 / E-04. Use in tests that need a cookie that the
  middleware's _try_cookie helper will accept as valid.
  '''
  from itsdangerous.url_safe import URLSafeTimedSerializer
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-session-cookie')
  return serializer.dumps({'u': VALID_USERNAME, 'iat': int(time.time())})


@pytest.fixture
def valid_pending_token() -> str:
  '''Phase 16.1: tsi_pending-shaped signed token (post-/login pre-/verify-totp).

  Payload includes {'pwd_ok': True} so /verify-totp can short-circuit on the
  cookie alone. 10-min TTL via system_params.TSI_PENDING_TTL_SECONDS.
  '''
  from itsdangerous.url_safe import URLSafeTimedSerializer
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-pending-cookie')
  return serializer.dumps({
    'u': VALID_USERNAME, 'iat': int(time.time()), 'next': '/', 'pwd_ok': True,
  })


@pytest.fixture
def valid_enroll_token() -> str:
  '''Phase 16.1: tsi_enroll-shaped signed token (post-/login pre-/enroll-totp).

  10-min TTL via system_params.TSI_ENROLL_TTL_SECONDS. Plan 16.1-01 E-03.
  '''
  from itsdangerous.url_safe import URLSafeTimedSerializer
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-enroll-cookie')
  return serializer.dumps({
    'u': VALID_USERNAME, 'iat': int(time.time()), 'next': '/',
  })


@pytest.fixture
def valid_secret() -> str:
  '''Phase 13: 32-char sentinel that passes D-17 minimum-length check.'''
  return VALID_SECRET


@pytest.fixture
def isolated_auth_json(tmp_path, monkeypatch):
  '''Phase 16.1 Plan 02: per-test isolation for auth.json mutations.

  Plan 16.1-01's autouse fixture sets WEB_AUTH_USERNAME / WEB_AUTH_SECRET env
  vars but does NOT redirect auth_store.DEFAULT_AUTH_PATH. Tests that mutate
  auth.json (trusted_devices, pending_magic_links, totp_secret) MUST opt into
  this fixture to avoid clobbering the real repo-root auth.json.

  Reused by:
    - tests/test_auth_store.py::TestTrustedDevices (Plan 02 Task 1)
    - tests/test_web_auth_middleware.py::TestTrustedDeviceCookie (Plan 02 Task 2)
    - tests/test_web_routes_totp.py::TestVerifyTotpTrustDeviceFlow (Plan 02 Task 3)
    - tests/test_web_routes_devices.py (Plan 02 Task 4)
    - tests/test_auth_store.py::TestMagicLinks (Plan 03 — future)

  Returns the per-test tmp auth.json Path so the test can read/write it directly
  for assertions without going through the auth_store module.
  '''
  tmp_auth = tmp_path / 'auth.json'
  import auth_store
  monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', tmp_auth)
  return tmp_auth


@pytest.fixture
def auth_headers(valid_secret) -> dict:
  '''Phase 13 AUTH-01: header dict for authorized TestClient requests.'''
  return {AUTH_HEADER_NAME: valid_secret}


# =============================================================================
# Phase 14 — HTMX-aware fixtures (Plan 14-01 Wave 0)
# =============================================================================
#
# These fixtures support tests/test_web_trades.py (skeleton in Plan 14-01,
# populated in Plan 14-04). Two pieces:
#
#   htmx_headers          — auth_headers + 'HX-Request': 'true' so handlers
#                           can detect HTMX-originated requests (UI-SPEC
#                           §Decision 3 — banner OOB swap on success).
#
#   client_with_state_v3  — TestClient + state-stub + save-capture tuple.
#                           Default seed state is post-Plan-14-02 v3 shape:
#                           schema_version=3 with manual_stop=None on every
#                           open Position. Phase 14 D-07 reads
#                           _resolved_contracts directly so we MUST seed it
#                           (load_state would normally rematerialize it but
#                           we monkeypatch load_state — see RESEARCH §Pitfall 6).
#
# Save-capture closure: every state passed to save_state lands in
# captured_saves so D-11 atomic-single-save tests can assert
# `len(captured_saves) == 1`. Tests use lambda *_a, **_kw: ... rather than
# positional-only stubs so callers passing path=... kwarg don't break.
#
# CRITICAL: `sys.modules.pop('web.app', None)` runs BEFORE create_app() so a
# previous test's app instance can't leak into this fixture's TestClient
# (RESEARCH §Pitfall 4 — autouse fixture in this file already sets
# WEB_AUTH_SECRET, but the imported app module caches its own state).


@pytest.fixture
def htmx_headers(auth_headers) -> dict:
  '''Phase 14: auth headers + HX-Request signal so handlers can detect
  HTMX-originated requests (UI-SPEC §Decision 3 — banner OOB swap on success).'''
  return {**auth_headers, 'HX-Request': 'true'}


@pytest.fixture
def client_with_state_v3(monkeypatch):
  '''Phase 14 mirror of tests/test_web_state.py::client_with_state — yields
  a TestClient + (set_state, captured_saves) tuple. captured_saves accumulates
  every state dict that save_state was called with (no disk I/O).

  Default seed: a v3-schema state with one open SPI200 LONG position whose
  manual_stop is None (post-migration shape per Phase 14 D-09). Tests adjust
  via set_state.

  Returns: (client, set_state, captured_saves) tuple.
  '''
  from fastapi.testclient import TestClient
  import sys
  sys.modules.pop('web.app', None)
  from web.app import create_app

  default_state = {
    'schema_version': 3,
    'account': 100_000.0,
    'last_run': '2026-04-25',
    'positions': {
      'SPI200': {
        'direction': 'LONG', 'entry_price': 7800.0, 'entry_date': '2026-04-20',
        'n_contracts': 2, 'pyramid_level': 0,
        'peak_price': 7850.0, 'trough_price': None, 'atr_entry': 50.0,
        'manual_stop': None,  # Phase 14 D-09
      },
      'AUDUSD': None,
    },
    # Phase 14 REVIEWS MEDIUM #7: signals nested under last_scalars
    # (matches main.py:1225 daily-loop write shape).
    'signals': {
      'SPI200': {'last_scalars': {'atr': 50.0}, 'last_close': 7820.0},
      'AUDUSD': {},
    },
    'trade_log': [], 'equity_history': [], 'warnings': [],
    'initial_account': 100_000.0,
    'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
    '_resolved_contracts': {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
    },
  }
  state_box = {'value': default_state}
  captured_saves = []

  import state_manager
  monkeypatch.setattr(
    state_manager, 'load_state', lambda *_a, **_kw: state_box['value']
  )
  monkeypatch.setattr(
    state_manager, 'save_state',
    lambda state, *_a, **_kw: captured_saves.append(dict(state))
  )

  # Phase 14 Plan 14-04 + REVIEWS HIGH #1: handlers use mutate_state.
  # The fixture must mirror the load -> mutate -> save semantic so test
  # bodies can assert on captured_saves. Mutator is invoked on the live
  # state_box['value'] dict (mutates in place per state_manager.mutate_state
  # contract); the post-mutation snapshot is appended to captured_saves
  # exactly like the save_state stub above. _OpenConflict raised inside
  # the mutator propagates back to the handler (caught + converted to 409).
  def _mutate_state_stub(mutator, *_a, **_kw):
    state = state_box['value']
    mutator(state)  # may raise; propagates out (handler catches _OpenConflict)
    captured_saves.append(dict(state))
    return state
  monkeypatch.setattr(state_manager, 'mutate_state', _mutate_state_stub)

  client = TestClient(create_app())

  def set_state(payload):
    state_box['value'] = payload

  return client, set_state, captured_saves
