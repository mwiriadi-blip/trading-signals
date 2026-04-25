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
