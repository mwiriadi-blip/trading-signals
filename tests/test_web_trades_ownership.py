'''Phase 36 D-14 — 404-for-other-users ownership tests for trades entity routes.

Placed in a new file (not appended to test_web_trades.py) because
test_web_trades.py is 1,270 lines — exceeds the 500-LOC project cap (CLAUDE.md).
D-14 originally specified appending to existing files; CLAUDE.md constraint takes
precedence (deferred_decisions in 36-01-PLAN.md frontmatter).

Semantics note (RESEARCH Pitfall 5):
  - GET read-path handlers (close_form, modify_form, cancel_row): Phase 36 added
    explicit 404 when position is None. When uid_b has no SPI200 position,
    load_user_state(uid_b)['positions']['SPI200'] is None → 404.
  - POST mutation handlers (close, modify): existing _OpenConflict (409) behavior
    is preserved. uid_b has no SPI200 position → "no open position" → 409.
    The 409 proves isolation: uid_b gets an error, NOT uid_a's trade data.

References: D-14, TENANT-03 (IDOR prevention — T-36-01).
'''
import sys
import time

import pytest
from fastapi.testclient import TestClient
from itsdangerous.url_safe import URLSafeTimedSerializer

from tests.conftest import VALID_SECRET, VALID_USERNAME


def _build_session_cookie(uid, *, username=None):
  '''Build a signed tsi_session cookie for the given uid.'''
  username = username or VALID_USERNAME
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-session-cookie')
  return serializer.dumps({'u': username, 'iat': int(time.time()), 'uid': uid})


@pytest.fixture
def two_user_trades_client(isolated_auth_json, monkeypatch):
  '''TestClient with uid_a (has SPI200 LONG position) and uid_b (no positions).

  uid_a's position is seeded in the state. uid_b's positions are all None.
  Returns (client, uid_a, uid_b).
  '''
  sys.modules.pop('web.app', None)

  import auth_store
  import state_manager

  user_a = auth_store.create_user({'email': 'alice@example.com', 'role': 'admin'})
  user_b = auth_store.create_user({'email': 'bob@example.com', 'role': 'ff'})
  uid_a = user_a['uid']
  uid_b = user_b['uid']

  spi200_position = {
    'direction': 'LONG',
    'entry_price': 7800.0,
    'entry_date': '2026-05-01',
    'n_contracts': 2,
    'pyramid_level': 0,
    'peak_price': 7850.0,
    'trough_price': None,
    'atr_entry': 50.0,
    'manual_stop': None,
  }

  seeded_state = {
    'schema_version': 12,
    'admin_user_id': uid_a,
    'signals': {
      'SPI200': {'last_close': 7820.0, 'last_scalars': {'atr': 50.0}},
      'AUDUSD': {'last_close': 0.6520, 'last_scalars': {'atr': 0.005}},
    },
    'markets': {'SPI200': {}, 'AUDUSD': {}},
    'strategy_settings': {},
    'warnings': [],
    'last_run': '2026-05-14',
    '_resolved_contracts': {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
    },
    'users': {
      uid_a: {
        'account': 100_000.0,
        'initial_account': 100_000.0,
        'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
        'positions': {'SPI200': spi200_position, 'AUDUSD': None},
        'trade_log': [],
        'equity_history': [],
        'paper_trades': [],
        'ui_prefs': {'tour_completed': True},
      },
      uid_b: {
        'account': 100_000.0,
        'initial_account': 100_000.0,
        'contracts': {},
        'positions': {'SPI200': None, 'AUDUSD': None},
        'trade_log': [],
        'equity_history': [],
        'paper_trades': [],
        'ui_prefs': {'tour_completed': True},
      },
    },
  }

  monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: seeded_state)
  monkeypatch.setattr(
    state_manager, 'load_user_state',
    lambda u, *_a, **_kw: seeded_state['users'].get(u, {}),
  )

  # Stub mutate_user_state: invoke mutator on seeded_state and return it.
  # For uid_b: positions['SPI200'] is None → _OpenConflict fires → 409.
  # Assert uid == uid_b so a regression where the route resolves the wrong user
  # is caught immediately rather than producing a subtly wrong result.
  def _mutate_stub(uid, mutator, *_a, **_kw):
    assert uid == uid_b, f'route passed wrong uid: expected {uid_b!r}, got {uid!r}'
    mutator(seeded_state)
    return seeded_state
  monkeypatch.setattr(state_manager, 'mutate_user_state', _mutate_stub)

  from web.app import create_app
  client = TestClient(create_app(), raise_server_exceptions=False)
  return client, uid_a, uid_b


class TestTradeOwnership:
  '''404/409-for-other-users tests for trades entity-ID routes (D-14).

  POST mutation handlers return 409 when uid_b has no position (proves isolation:
  uid_b gets an error, NOT uid_a's data). GET read-path handlers return 404.
  '''

  def test_close_trade_returns_404_for_other_users_position(
    self, two_user_trades_client,
  ):
    '''POST /trades/close as uid_b when uid_a owns SPI200 LONG position.

    Isolation: uid_b's state['users'][uid_b]['positions']['SPI200'] is None.
    Route raises _OpenConflict("no open position") → 409.
    409 proves uid_b gets an error, not uid_a's trade data (RESEARCH Pitfall 5).
    '''
    client, uid_a, uid_b = two_user_trades_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.post(
      '/trades/close',
      json={'instrument': 'SPI200', 'exit_price': 8000.0},
      cookies={'tsi_session': cookie_b},
    )
    # 409 proves isolation: uid_b has no SPI200 position → conflict error.
    # uid_b does not see uid_a's position data in the response.
    assert resp.status_code == 409, (
      f'Expected 409 (no position) for uid_b on uid_a SPI200; got {resp.status_code}: {resp.text}'
    )

  def test_modify_trade_returns_404_for_other_users_position(
    self, two_user_trades_client,
  ):
    '''POST /trades/modify as uid_b when uid_a owns SPI200 LONG position.

    Isolation: uid_b has no SPI200 position → _OpenConflict → 409.
    Proves uid_b cannot see or modify uid_a's position.
    '''
    client, uid_a, uid_b = two_user_trades_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.post(
      '/trades/modify',
      json={'instrument': 'SPI200', 'new_stop': 7700.0},
      cookies={'tsi_session': cookie_b},
    )
    assert resp.status_code == 409, (
      f'Expected 409 (no position) for uid_b on uid_a SPI200; got {resp.status_code}: {resp.text}'
    )

  def test_close_form_returns_404_for_other_users_position(
    self, two_user_trades_client,
  ):
    '''GET /trades/close-form?instrument=SPI200 as uid_b returns 404.

    Isolation: load_user_state(uid_b)['positions']['SPI200'] is None.
    Phase 36 added explicit 404 for GET read-paths when position is None.
    '''
    client, uid_a, uid_b = two_user_trades_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.get(
      '/trades/close-form',
      params={'instrument': 'SPI200'},
      cookies={'tsi_session': cookie_b},
    )
    assert resp.status_code == 404, (
      f'Expected 404 for uid_b close-form on uid_a SPI200; got {resp.status_code}'
    )

  def test_modify_form_returns_404_for_other_users_position(
    self, two_user_trades_client,
  ):
    '''GET /trades/modify-form?instrument=SPI200 as uid_b returns 404.

    Isolation: uid_b has no SPI200 position → 404.
    '''
    client, uid_a, uid_b = two_user_trades_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.get(
      '/trades/modify-form',
      params={'instrument': 'SPI200'},
      cookies={'tsi_session': cookie_b},
    )
    assert resp.status_code == 404, (
      f'Expected 404 for uid_b modify-form on uid_a SPI200; got {resp.status_code}'
    )

  def test_cancel_row_returns_404_for_other_users_position(
    self, two_user_trades_client,
  ):
    '''GET /trades/cancel-row?instrument=SPI200 as uid_b returns 404.

    Isolation: uid_b has no SPI200 position → 404.
    '''
    client, uid_a, uid_b = two_user_trades_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.get(
      '/trades/cancel-row',
      params={'instrument': 'SPI200'},
      cookies={'tsi_session': cookie_b},
    )
    assert resp.status_code == 404, (
      f'Expected 404 for uid_b cancel-row on uid_a SPI200; got {resp.status_code}'
    )
