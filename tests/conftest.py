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

from state_manager.migrations import _ADMIN_UID

# Phase 13 D-17: 32 chars meets the minimum-length check
# (≈128 bits of entropy via openssl rand -hex 16).
VALID_SECRET = 'a' * 32

# Phase 16.1 D-08: sentinel username — non-empty, no ':' character.
VALID_USERNAME = 'marc'

# Phase 16.1 Plan 03 F-06: sentinel recovery email — matches the regex
# ^[^@]+@[^@]+\.[^@]+$ and equals the default literal in web/app.py so any
# test that doesn't override it sees the documented default value.
VALID_RECOVERY_EMAIL = 'mwiriadi@gmail.com'

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
    # Phase 16.1 Plan 03 F-06: OPERATOR_RECOVERY_EMAIL is boot-validated in
    # web/app.py::_read_auth_credentials. Tests that intentionally exercise
    # the missing/malformed-email path call setenv/delenv themselves; LIFO
    # finalizer ordering means their override beats this autouse setenv.
    monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', VALID_RECOVERY_EMAIL)


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

  # Phase 36: v12-shaped state — user data lives under state['users'][uid].
  # top-level 'positions' is a legacy compat shim for pre-migration routes
  # (e.g. dashboard/_renderers.py::_forward_stop_fragment_response line 118)
  # that still call state.get('positions', {}). Wave 1 plan 02 migrates those
  # reads to load_user_state; until then the shim prevents test breakage.
  _open_spi_position = {
    'direction': 'LONG', 'entry_price': 7800.0, 'entry_date': '2026-04-20',
    'n_contracts': 2, 'pyramid_level': 0,
    'peak_price': 7850.0, 'trough_price': None, 'atr_entry': 50.0,
    'manual_stop': None,
  }
  default_state = {
    'schema_version': 12,
    'admin_user_id': _ADMIN_UID,
    'last_run': '2026-04-25',
    # Legacy compat: pre-v12 reads (e.g. forward-stop fragment, dashboard) still
    # expect top-level positions. Removed when Wave 1 migrates those routes.
    'positions': {
      'SPI200': _open_spi_position,
      'AUDUSD': None,
    },
    'signals': {
      'SPI200': {'last_scalars': {'atr': 50.0}, 'last_close': 7820.0},
      'AUDUSD': {'last_close': 0.6520, 'last_scalars': {'atr': 0.005}},
    },
    'markets': {},
    'strategy_settings': {},
    'warnings': [],
    '_resolved_contracts': {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
    },
    'users': {
      _ADMIN_UID: {
        'account': 100_000.0,
        'initial_account': 100_000.0,
        'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
        'positions': {
          'SPI200': _open_spi_position,
          'AUDUSD': None,
        },
        'trade_log': [],
        'equity_history': [],
        'paper_trades': [],
        'ui_prefs': {'tour_completed': True},
      },
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
  # Phase 36: stub load_user_state so routes calling it get the user bucket.
  # Falls back to the flat top-level state for pre-v12 set_state() callers (G-75).
  def _load_user_state_stub(uid, *_a, **_kw):
    state = state_box['value']
    if 'users' in state and uid in state['users']:
      return state['users'][uid]
    # Pre-v12 flat state: synthesize user bucket from flat keys
    return {k: state.get(k) for k in (
      'paper_trades', 'positions', 'trade_log', 'equity_history',
      'account', 'initial_account', 'contracts', 'ui_prefs',
    ) if k in state}
  monkeypatch.setattr(state_manager, 'load_user_state', _load_user_state_stub)

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

  # Phase 36: also stub mutate_user_state so routes calling it use same
  # state_box and captured_saves (uid param ignored — single-user test).
  # Compat shim A: if state was seeded with pre-v12 flat shape (no 'users' key),
  #   auto-construct state['users'][uid] from the flat keys so _apply bodies that
  #   navigate state['users'][uid] work (G-75). Tests using set_state() with old
  #   flat shape don't need updating.
  # Compat shim B: after mutation, propagate user-bucket keys to top-level so
  #   pre-Wave-1 test assertions on captured_saves[-1]['paper_trades'] still pass.
  # Both shims are removed in Wave 2 when tests reference user bucket directly.
  _USER_BUCKET_KEYS = ('paper_trades', 'positions', 'trade_log', 'equity_history',
                       'account', 'initial_account', 'contracts', 'ui_prefs')
  # Keys propagated back to top-level after mutation for legacy test assertions
  _PROPAGATE_KEYS = ('paper_trades', 'positions', 'trade_log', 'account', 'equity_history')
  def _mutate_user_state_stub(uid, mutator, *_a, **_kw):
    state = state_box['value']
    if 'users' not in state:
      # Shim A: promote flat state to v12 user-bucket shape
      user_bucket = {k: state.get(k) for k in _USER_BUCKET_KEYS if k in state}
      state['users'] = {uid: user_bucket}
    elif uid not in state['users']:
      state['users'][uid] = {k: state.get(k) for k in _USER_BUCKET_KEYS if k in state}
    mutator(state)
    # Shim B: propagate user-bucket keys back to top-level for legacy assertions
    for _key in _PROPAGATE_KEYS:
      if _key in state['users'].get(uid, {}):
        state[_key] = state['users'][uid][_key]
    captured_saves.append(dict(state))
    return state
  monkeypatch.setattr(state_manager, 'mutate_user_state', _mutate_user_state_stub)

  # Phase 36: override current_user_id dependency so routes using
  # Depends(current_user_id) get _ADMIN_UID without a real session cookie.
  # Tests pass htmx_headers (X-Trading-Signals-Auth), not cookies — this
  # override bridges the gap for the single-user test scenario.
  from web.dependencies import current_user_id
  app = create_app()
  app.dependency_overrides[current_user_id] = lambda: _ADMIN_UID
  client = TestClient(app)

  def set_state(payload):
    state_box['value'] = payload

  return client, set_state, captured_saves


def _open_row_v7(
  trade_id: str = 'SPI200-20260430-001',
  instrument: str = 'SPI200',
  side: str = 'LONG',
  stop_price: float | None = 8100.0,
  last_alert_state: str | None = None,
) -> dict:
  '''Phase 20 D-08: v7-schema open paper-trade row with last_alert_state field.
  Used by test_dashboard.py::TestRenderAlertBadge and other Phase 20 tests.
  '''
  return {
    'id': trade_id,
    'instrument': instrument,
    'side': side,
    'entry_dt': '2026-04-30T08:00:00+08:00',
    'entry_price': 8200.0,
    'contracts': 1,
    'stop_price': stop_price,
    'entry_cost_aud': 3.0,
    'status': 'open',
    'exit_dt': None,
    'exit_price': None,
    'realised_pnl': None,
    'strategy_version': 'v1.2.0',
    'last_alert_state': last_alert_state,
  }


@pytest.fixture
def client_with_state_v6(monkeypatch):
  '''Phase 19/20 web test fixture — yields (client, set_state, captured_saves).
  Default seed: v7-schema state with paper_trades=[]. Tests adjust via set_state.
  Named v6 for backward compat with existing tests; default schema is now v7.
  Reuses Phase 14 mutate_state kernel-stub semantic.
  '''
  from fastapi.testclient import TestClient
  import sys
  sys.modules.pop('web.app', None)
  from web.app import create_app

  # Phase 36: v12-shaped state — user data lives under state['users'][uid].
  default_state = {
    'schema_version': 12,
    'admin_user_id': _ADMIN_UID,
    'last_run': '2026-04-30',
    'signals': {
      'SPI200': {'last_close': 7820.0, 'last_scalars': {'atr': 50.0}},
      'AUDUSD': {'last_close': 0.6520, 'last_scalars': {'atr': 0.005}},
    },
    'markets': {},
    'strategy_settings': {},
    'warnings': [],
    '_resolved_contracts': {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
    },
    'users': {
      _ADMIN_UID: {
        'account': 100_000.0,
        'initial_account': 100_000.0,
        'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
        'positions': {'SPI200': None, 'AUDUSD': None},
        'trade_log': [],
        'equity_history': [],
        'paper_trades': [],
        'ui_prefs': {'tour_completed': True},
      },
    },
  }
  state_box = {'value': default_state}
  captured_saves = []

  import state_manager
  monkeypatch.setattr(state_manager, 'load_state',
                      lambda *_a, **_kw: state_box['value'])
  monkeypatch.setattr(state_manager, 'save_state',
                      lambda state, *_a, **_kw: captured_saves.append(dict(state)))
  # Phase 36: stub load_user_state (same compat logic as client_with_state_v3).
  def _load_user_state_stub_v6(uid, *_a, **_kw):
    state = state_box['value']
    if 'users' in state and uid in state['users']:
      return state['users'][uid]
    return {k: state.get(k) for k in (
      'paper_trades', 'positions', 'trade_log', 'equity_history',
      'account', 'initial_account', 'contracts', 'ui_prefs',
    ) if k in state}
  monkeypatch.setattr(state_manager, 'load_user_state', _load_user_state_stub_v6)

  def _mutate_state_stub(mutator, *_a, **_kw):
    state = state_box['value']
    mutator(state)
    captured_saves.append(dict(state))
    return state

  monkeypatch.setattr(state_manager, 'mutate_state', _mutate_state_stub)

  # Phase 36: also stub mutate_user_state so routes calling it use same
  # state_box and captured_saves (uid param ignored — single-user test).
  # Same shim A+B logic as client_with_state_v3 — see inline comment there.
  _USER_BUCKET_KEYS_V6 = ('paper_trades', 'positions', 'trade_log', 'equity_history',
                           'account', 'initial_account', 'contracts', 'ui_prefs')
  _PROPAGATE_KEYS_V6 = ('paper_trades', 'positions', 'trade_log', 'account', 'equity_history')
  def _mutate_user_state_stub_v6(uid, mutator, *_a, **_kw):
    state = state_box['value']
    if 'users' not in state:
      state['users'] = {uid: {k: state.get(k) for k in _USER_BUCKET_KEYS_V6 if k in state}}
    elif uid not in state['users']:
      state['users'][uid] = {k: state.get(k) for k in _USER_BUCKET_KEYS_V6 if k in state}
    mutator(state)
    for _key in _PROPAGATE_KEYS_V6:
      if _key in state['users'].get(uid, {}):
        state[_key] = state['users'][uid][_key]
    captured_saves.append(dict(state))
    return state
  monkeypatch.setattr(state_manager, 'mutate_user_state', _mutate_user_state_stub_v6)

  # Phase 36: override current_user_id dependency (same as client_with_state_v3).
  from web.dependencies import current_user_id
  app = create_app()
  app.dependency_overrides[current_user_id] = lambda: _ADMIN_UID
  client = TestClient(app)

  def set_state(payload):
    state_box['value'] = payload

  return client, set_state, captured_saves


# =============================================================================
# Phase 37 Wave 0 — shared fixtures (review consensus #11)
# =============================================================================


@pytest.fixture
def pending_invite_auth_json(tmp_path, monkeypatch, isolated_auth_json):
  '''Phase 37 Wave 0 shared fixture (review consensus #11).

  Provides auth.json with admin row + ONE unconsumed PendingInvite.
  Used by Plan 03 (auth_store) and Plan 04 (invite wizard) tests.

  Yields a dict:
    auth_path  — Path to the tmp auth.json (same as isolated_auth_json)
    raw_token  — deterministic sentinel token ('a' * 43)
    token_hash — 'sha256:' + sha256(raw_token).hexdigest()
    email      — 'invitee@x.com'
    admin_uid  — 'admin-uid'

  The fixture synthesises rows directly from the documented v2 schema WITHOUT
  calling mint_invite_token so it remains stable if Plan 03 refactors helpers.
  Downstream tests that need to call consume_and_create_user can use raw_token.
  '''
  import hashlib
  import json
  from datetime import datetime, timezone, timedelta

  raw_token = 'a' * 43
  token_hash = 'sha256:' + hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
  now = datetime.now(timezone.utc)
  created_at = now.isoformat()
  expires_at = (now + timedelta(days=7)).isoformat()

  auth_data = {
    'schema_version': 2,
    'totp_secret': None,
    'totp_enrolled': False,
    'totp_enrolled_at': None,
    'users': [
      {
        'uid': 'admin-uid',
        'email': 'admin@x.com',
        'role': 'admin',
        'created_at': created_at,
        'disabled': False,
      },
    ],
    'pending_invites': [
      {
        'token_hash': token_hash,
        'email': 'invitee@x.com',
        'invited_by': 'admin-uid',
        'created_at': created_at,
        'expires_at': expires_at,
        'consumed': False,
        'consumed_at': None,
      },
    ],
    'trusted_devices': [],
    'pending_magic_links': [],
  }

  isolated_auth_json.write_text(json.dumps(auth_data))

  yield {
    'auth_path': isolated_auth_json,
    'raw_token': raw_token,
    'token_hash': token_hash,
    'email': 'invitee@x.com',
    'admin_uid': 'admin-uid',
  }


@pytest.fixture
def multi_user_state_json(tmp_path, monkeypatch):
  '''Phase 37 Wave 0 shared fixture (review consensus #11).

  state.json with 3 users (active/paused/disabled) for fan-out skip-rule tests.

  Users:
    u_active   — role='ff', disabled=False, email_enabled=True, pause_until=None
    u_paused   — role='ff', disabled=False, email_enabled=True, pause_until=today+7d
    u_disabled — role='ff', disabled=True,  email_enabled=True, pause_until=None

  Yields a dict:
    state_path — Path to the tmp state.json
    uids       — {'active': 'u_active', 'paused': 'u_paused', 'disabled': 'u_disabled'}
  '''
  import json
  from datetime import date, timedelta

  import state_manager

  try:
    schema_version = state_manager.STATE_SCHEMA_VERSION
  except AttributeError:
    schema_version = 12

  pause_until = (date.today() + timedelta(days=7)).isoformat()

  state_data = {
    'schema_version': schema_version,
    'positions': {},
    'signals': {},
    'last_cycle': None,
    'users': {
      'u_active': {
        'role': 'ff',
        'disabled': False,
        'email': 'active@x.com',
        'email_enabled': True,
        'pause_until': None,
      },
      'u_paused': {
        'role': 'ff',
        'disabled': False,
        'email': 'paused@x.com',
        'email_enabled': True,
        'pause_until': pause_until,
      },
      'u_disabled': {
        'role': 'ff',
        'disabled': True,
        'email': 'disabled@x.com',
        'email_enabled': True,
        'pause_until': None,
      },
    },
  }

  state_path = tmp_path / 'state.json'
  state_path.write_text(json.dumps(state_data))
  monkeypatch.setenv('STATE_FILE', str(state_path))
  monkeypatch.setattr('state_manager.STATE_FILE', str(state_path), raising=False)

  yield {
    'state_path': state_path,
    'uids': {
      'active': 'u_active',
      'paused': 'u_paused',
      'disabled': 'u_disabled',
    },
  }
