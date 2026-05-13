'''Phase 36 D-14 — 404-for-other-users ownership tests for paper trade entity routes.

Placed in a new file (not appended to test_web_paper_trades.py) because
test_web_paper_trades.py is 936 lines — exceeds the 500-LOC project cap (CLAUDE.md).
D-14 originally specified appending to existing files; CLAUDE.md constraint takes
precedence (deferred_decisions in 36-01-PLAN.md frontmatter).

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
def two_user_paper_client(isolated_auth_json, monkeypatch):
  '''TestClient with uid_a (has 1 paper trade) and uid_b (empty).

  Returns (client, uid_a, uid_b, uid_a_trade_id).
  '''
  sys.modules.pop('web.app', None)

  import auth_store
  import state_manager

  user_a = auth_store.create_user({'email': 'alice@example.com', 'role': 'admin'})
  user_b = auth_store.create_user({'email': 'bob@example.com', 'role': 'ff'})
  uid_a = user_a['uid']
  uid_b = user_b['uid']

  trade_id = 'SPI200-20260501-001'

  seeded_state = {
    'schema_version': 12,
    'admin_user_id': uid_a,
    'signals': {
      'SPI200': {'last_close': 8000.0, 'last_scalars': {'atr': 50.0}},
      'AUDUSD': {'last_close': 0.6520, 'last_scalars': {'atr': 0.005}},
    },
    'markets': {},
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
        'contracts': {},
        'positions': {'SPI200': None, 'AUDUSD': None},
        'trade_log': [],
        'equity_history': [],
        'paper_trades': [
          {
            'id': trade_id,
            'instrument': 'SPI200',
            'side': 'LONG',
            'entry_dt': '2026-05-01T08:00:00+08:00',
            'entry_price': 8000.0,
            'contracts': 1,
            'stop_price': 7900.0,
            'entry_cost_aud': 3.0,
            'status': 'open',
            'exit_dt': None,
            'exit_price': None,
            'realised_pnl': None,
            'strategy_version': 'v1.2.0',
            'last_alert_state': None,
            'n_contracts': 1,
          }
        ],
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

  # Stub load_state and load_user_state for both GET and POST paths.
  monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: seeded_state)
  monkeypatch.setattr(
    state_manager, 'load_user_state',
    lambda u, *_a, **_kw: seeded_state['users'].get(u, {}),
  )

  # Stub mutate_user_state: invoke mutator on seeded_state but return it.
  # For 404-for-other-users tests: uid_b has no trade with uid_a's trade_id
  # so _apply raises _PaperTradeNotFound → route returns 404.
  def _mutate_stub(uid, mutator, *_a, **_kw):
    mutator(seeded_state)
    return seeded_state
  monkeypatch.setattr(state_manager, 'mutate_user_state', _mutate_stub)

  from web.app import create_app
  client = TestClient(create_app(), raise_server_exceptions=False)
  return client, uid_a, uid_b, trade_id


class TestEntityIdOwnership:
  '''404-for-other-users tests for paper-trade entity-ID routes (D-14).

  Each test seeds uid_a with a paper trade, authenticates as uid_b, and asserts
  that uid_b gets a 404 (not uid_a's data). This verifies the ownership check
  added in Phase 36: routes navigate state['users'][user_id] so another user's
  trade_id is simply not found in the requesting user's bucket.
  '''

  def test_edit_paper_trade_returns_404_for_other_users_entity(
    self, two_user_paper_client,
  ):
    '''PATCH /paper-trade/{trade_id} returns 404 when trade_id belongs to uid_a but
    request is authenticated as uid_b.

    Isolation proof: uid_b's state['users'][uid_b]['paper_trades'] is empty, so
    the route's `[r for r in rows if r['id'] == trade_id]` yields no matches
    and _PaperTradeNotFound is raised → 404.
    '''
    client, uid_a, uid_b, trade_id = two_user_paper_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.patch(
      f'/paper-trade/{trade_id}',
      data={'side': 'SHORT'},
      cookies={'tsi_session': cookie_b},
    )
    assert resp.status_code == 404, (
      f'Expected 404 for uid_b accessing uid_a paper trade; got {resp.status_code}'
    )

  def test_delete_paper_trade_returns_404_for_other_users_entity(
    self, two_user_paper_client,
  ):
    '''DELETE /paper-trade/{trade_id} returns 404 when trade_id belongs to uid_a.

    Isolation proof: uid_b's bucket has no paper_trades — not-found check fires.
    '''
    client, uid_a, uid_b, trade_id = two_user_paper_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.delete(
      f'/paper-trade/{trade_id}',
      cookies={'tsi_session': cookie_b},
    )
    assert resp.status_code == 404, (
      f'Expected 404 for uid_b deleting uid_a paper trade; got {resp.status_code}'
    )

  def test_close_paper_trade_returns_404_for_other_users_entity(
    self, two_user_paper_client,
  ):
    '''POST /paper-trade/{trade_id}/close returns 404 when trade_id belongs to uid_a.

    Isolation proof: uid_b's bucket is empty — _PaperTradeNotFound fires → 404.
    '''
    client, uid_a, uid_b, trade_id = two_user_paper_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.post(
      f'/paper-trade/{trade_id}/close',
      data={'exit_price': '8100.0', 'exit_dt': '2026-05-02T08:00'},
      cookies={'tsi_session': cookie_b},
    )
    assert resp.status_code == 404, (
      f'Expected 404 for uid_b closing uid_a paper trade; got {resp.status_code}'
    )

  def test_get_close_form_returns_404_for_other_users_entity(
    self, two_user_paper_client,
  ):
    '''GET /paper-trade/{trade_id}/close-form returns 404 when trade_id belongs to uid_a.

    Isolation proof: close-form uses load_user_state(uid_b) → empty paper_trades
    → not-found check fires → 404.
    '''
    client, uid_a, uid_b, trade_id = two_user_paper_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.get(
      f'/paper-trade/{trade_id}/close-form',
      cookies={'tsi_session': cookie_b},
    )
    assert resp.status_code == 404, (
      f'Expected 404 for uid_b accessing uid_a close-form; got {resp.status_code}'
    )
