'''Phase 13 WEB-06 + D-12..D-15 — GET /api/state contract tests.

Reference: 13-CONTEXT.md D-12..D-15, 13-VALIDATION.md test-class
enumeration (lines 793-797), 13-UI-SPEC.md §GET /api/state byte-level contract,
13-REVIEWS.md §Codex MEDIUM #2 (SC-3 full top-level key-set lock).

Fixture strategy mirrors tests/test_web_auth_middleware.py — local helpers
duplicate-by-design rather than importing across test files. WEB_AUTH_SECRET
is preset by the autouse fixture in tests/conftest.py (Plan 13-01).
'''
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Plan 13-02 Rule 1 deviation pattern: constants inlined to avoid
# `from conftest import ...` ImportError (tests/ not on sys.path by default
# despite tests/__init__.py — pytest's autouse fixture in tests/conftest.py
# still runs, but module-level constants are not auto-importable). Mirrors
# tests/test_web_auth_middleware.py + tests/test_web_app_factory.py per
# 13-04-PLAN <action> "constants inlined" guidance.
AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'
VALID_SECRET = 'a' * 32  # matches tests/conftest.py D-17 sentinel


def _stub_load_state(state_payload):
  '''Return a load_state replacement that yields the supplied state dict.'''
  def _fn(*_args, **_kwargs):
    return state_payload
  return _fn


@pytest.fixture
def auth_headers():
  return {AUTH_HEADER_NAME: VALID_SECRET}


@pytest.fixture
def client_with_state(monkeypatch):
  '''Build a TestClient with a configurable load_state.

  WEB_AUTH_SECRET is preset by the autouse fixture in tests/conftest.py.
  Yields a (client, set_state_fn) tuple. Caller invokes set_state_fn(payload)
  to control what state_manager.load_state returns for that test.
  '''
  import sys
  sys.modules.pop('web.app', None)
  from web.app import create_app

  state_box = {'value': {'schema_version': 1, 'last_run': '2026-04-25'}}

  import state_manager
  monkeypatch.setattr(
    state_manager, 'load_state', lambda *_a, **_kw: state_box['value']
  )

  client = TestClient(create_app())

  def set_state(payload):
    state_box['value'] = payload

  return client, set_state


class TestStateResponse:
  '''D-12..D-15 + WEB-06: GET /api/state JSON shape, headers, key-strip, compactness.

  SC-3 (REVIEWS MEDIUM #2) is locked by test_full_top_level_key_set_preserved_except_runtime_keys
  which asserts the exact set of expected keys — any regression that drops
  `warnings`, `contracts`, or `equity_history` fires red immediately.
  '''

  def test_returns_200_with_auth(self, client_with_state, auth_headers):
    '''WEB-06: GET /api/state with valid auth → 200.'''
    client, set_state = client_with_state
    set_state({'schema_version': 1, 'last_run': '2026-04-25', 'positions': {}})
    r = client.get('/api/state', headers=auth_headers)
    assert r.status_code == 200, (
      f'Expected 200 with valid auth, got {r.status_code}: {r.text[:200]}'
    )

  def test_content_type_is_json(self, client_with_state, auth_headers):
    '''D-13: Content-Type header starts with "application/json".'''
    client, set_state = client_with_state
    set_state({'schema_version': 1})
    r = client.get('/api/state', headers=auth_headers)
    ct = r.headers.get('content-type', '')
    assert ct.startswith('application/json'), (
      f'Expected Content-Type starting with "application/json", got {ct!r}'
    )

  def test_strips_underscore_prefixed_top_level_keys(self, client_with_state, auth_headers):
    '''D-12: top-level keys starting with `_` are removed; other keys preserved.'''
    client, set_state = client_with_state
    set_state({
      'schema_version': 1,
      'account': 100000.0,
      'last_run': '2026-04-25',
      '_resolved_contracts': {'SPI200': 1, 'AUDUSD': 1},
      '_LAST_LOADED_STATE_HINT': 'should be stripped',
    })
    r = client.get('/api/state', headers=auth_headers)
    body = r.json()
    # Underscore-prefixed top-level keys must be ABSENT.
    assert '_resolved_contracts' not in body, (
      f'_resolved_contracts must be stripped (D-12), but found in body keys {list(body.keys())}'
    )
    assert '_LAST_LOADED_STATE_HINT' not in body, (
      f'Underscore-prefixed top-level keys must all be stripped, '
      f'found {[k for k in body if k.startswith("_")]}'
    )
    # Non-underscore keys must be PRESENT.
    assert body.get('schema_version') == 1
    assert body.get('account') == 100000.0
    assert body.get('last_run') == '2026-04-25'

  def test_full_top_level_key_set_preserved_except_runtime_keys(self, client_with_state, auth_headers):
    '''SC-3 lock (REVIEWS MEDIUM #2): every canonical top-level state.json key
    (except `_*` runtime-only keys) MUST appear in /api/state.

    Seeds state.json with the full canonical 9-key set PLUS a `_*` runtime
    key to exercise the strip. The response MUST contain exactly the 9
    canonical keys — no more, no fewer.

    A regression that silently drops `warnings`, `contracts`, or
    `equity_history` would pass the underscore-strip test but fire here.
    '''
    client, set_state = client_with_state
    set_state({
      'schema_version': 1,
      'account': 100000.0,
      'last_run': '2026-04-25',
      'positions': {},
      'signals': {},
      'trade_log': [],
      'equity_history': [],
      'warnings': [],
      'contracts': {'SPI200': {'multiplier': 5}, 'AUDUSD': {'notional': 10000}},
      '_resolved_contracts': {'SPI200': 1},  # runtime-only — must be stripped
    })
    r = client.get('/api/state', headers=auth_headers)
    assert r.status_code == 200, (
      f'Expected 200, got {r.status_code}: {r.text[:200]}'
    )
    expected = {
      'schema_version', 'account', 'last_run', 'positions', 'signals',
      'trade_log', 'equity_history', 'warnings', 'contracts',
    }
    actual = set(r.json().keys())
    assert actual == expected, (
      f'SC-3 violation: keys={actual}, expected={expected}. '
      f'Missing={expected - actual}, extra={actual - expected}. '
      f'(REVIEWS MEDIUM #2 — regression dropping warnings/contracts/equity_history would fire here.)'
    )

  def test_preserves_nested_underscore_keys(self, client_with_state, auth_headers):
    '''D-12: TOP LEVEL ONLY — nested dicts keep their underscore keys.'''
    client, set_state = client_with_state
    set_state({
      'schema_version': 1,
      'positions': {
        'SPI200': {
          'direction': 1,
          'contracts': 2,
          '_internal_marker': 'kept-because-nested',  # D-12: nested key preserved
        },
      },
    })
    r = client.get('/api/state', headers=auth_headers)
    body = r.json()
    assert 'positions' in body
    assert 'SPI200' in body['positions']
    assert body['positions']['SPI200'].get('_internal_marker') == 'kept-because-nested', (
      f'D-12 says nested underscore keys are preserved (top-level only); '
      f'found positions.SPI200 = {body["positions"]["SPI200"]}'
    )

  def test_cache_control_no_store(self, client_with_state, auth_headers):
    '''D-13: Cache-Control header equals "no-store".'''
    client, set_state = client_with_state
    set_state({'schema_version': 1})
    r = client.get('/api/state', headers=auth_headers)
    cc = r.headers.get('cache-control', '')
    assert cc == 'no-store', (
      f'Expected Cache-Control: no-store (D-13), got {cc!r}'
    )

  def test_response_is_compact_json(self, client_with_state, auth_headers):
    '''D-15: compact JSON — no indent / no extra whitespace patterns.'''
    client, set_state = client_with_state
    set_state({
      'schema_version': 1,
      'positions': {'SPI200': {'direction': 1, 'contracts': 2}},
    })
    r = client.get('/api/state', headers=auth_headers)
    raw = r.text
    # Pretty-printed JSON would contain "\n  " (newline + 2 spaces) for nested
    # objects. Compact JSON has neither newlines nor multi-space indents
    # between adjacent tokens.
    assert '\n  ' not in raw, (
      f'D-15: response must be compact JSON (no indented pretty-print), '
      f'but found newline+spaces in body: {raw[:200]!r}'
    )
    assert '\n' not in raw, (
      f'D-15: response must be single-line compact JSON, '
      f'found newlines: {raw[:200]!r}'
    )

  def test_unauthenticated_returns_401_not_state(self, client_with_state):
    '''AUTH-01 inheritance: GET /api/state without auth header → 401.'''
    client, _ = client_with_state
    r = client.get('/api/state')  # no headers
    assert r.status_code == 401, (
      f'Expected 401 without auth (AuthMiddleware blocks /api/state), '
      f'got {r.status_code}: {r.text[:120]}'
    )
    # Confirm body is NOT state JSON (no schema_version key in plain text).
    assert 'schema_version' not in r.text, (
      f'401 body must not contain state contents — body leaked: {r.text!r}'
    )
