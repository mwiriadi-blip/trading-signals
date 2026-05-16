'''Phase 43 D-06 — /admin/trades/full endpoint tests.

Tenant-isolation and auth tests for GET /admin/trades/full.

Must-haves (43-06):
  - Anonymous (no session) → 403
  - Admin authenticated as A cannot see B's trades
  - Admin with 300 trades gets all 300 rows back (no truncation at API layer)
'''
import sys
import time

import pytest
from fastapi.testclient import TestClient
from itsdangerous.url_safe import URLSafeTimedSerializer

from tests.conftest import VALID_SECRET, VALID_USERNAME


def _build_session_cookie(uid, *, username=None):
  username = username or VALID_USERNAME
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-session-cookie')
  payload = {'u': username, 'iat': int(time.time()), 'uid': uid}
  return serializer.dumps(payload)


def _make_trade(i: int) -> dict:
  return {
    'instrument': 'SPI200',
    'direction': 'LONG',
    'entry_date': f'2026-01-{(i % 28) + 1:02d}',
    'exit_date': f'2026-01-{(i % 28) + 2:02d}',
    'entry_price': 7800.0 + i,
    'exit_price': 7810.0 + i,
    'gross_pnl': 10.0,
    'n_contracts': 1,
    'exit_reason': 'stop_hit',
    'multiplier': 6.0,
    'cost_aud': 5.0,
    'net_pnl': 8.0,
  }


@pytest.fixture
def _admin_client_factory(isolated_auth_json, monkeypatch):
  '''Return a factory(uid_to_trades) → (client, uid_map).

  uid_to_trades: dict mapping label → list[trade_dict].
  Returns (client, dict{label: uid}).
  Creates one admin user per label.
  '''
  def _factory(uid_to_trades: dict):
    sys.modules.pop('web.app', None)

    import auth_store
    import state_manager

    users_state = {}
    uid_map = {}
    for label, trades in uid_to_trades.items():
      user = auth_store.create_user({'email': f'{label}@example.com', 'role': 'admin'})
      uid = user['uid']
      uid_map[label] = uid
      users_state[uid] = {
        'account': 100_000.0,
        'initial_account': 100_000.0,
        'contracts': {},
        'positions': {'SPI200': None, 'AUDUSD': None},
        'trade_log': trades,
        'equity_history': [],
        'paper_trades': [],
        'ui_prefs': {'tour_completed': True},
      }

    state = {
      'schema_version': 12,
      'admin_user_id': list(uid_map.values())[0],
      'signals': {},
      'markets': {},
      'strategy_settings': {},
      'warnings': [],
      'last_run': '2026-05-16',
      'users': users_state,
    }
    monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: state)

    from web.app import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    return client, uid_map

  return _factory


class TestAdminTradesTotalIsolation:
  def test_admin_trades_full_anonymous_rejected(self, _admin_client_factory):
    '''No session cookie → 403 (require_admin on router).'''
    client, _ = _admin_client_factory({'a': []})
    resp = client.get('/admin/trades/full')
    assert resp.status_code in (401, 403)

  def test_admin_trades_full_tenant_isolation(self, _admin_client_factory):
    '''User A's session returns only A's trades; B's sentinel is absent.'''
    sentinel_a = {**_make_trade(0), 'exit_reason': 'SENTINEL_A'}
    sentinel_b = {**_make_trade(1), 'exit_reason': 'SENTINEL_B'}
    client, uid_map = _admin_client_factory({
      'userA': [sentinel_a],
      'userB': [sentinel_b],
    })
    uid_a = uid_map['userA']
    cookie = _build_session_cookie(uid_a)
    resp = client.get('/admin/trades/full', cookies={'tsi_session': cookie})
    assert resp.status_code == 200
    data = resp.json()
    assert data['user_id'] == uid_a
    reasons = [t['exit_reason'] for t in data['trade_log']]
    assert 'SENTINEL_A' in reasons
    assert 'SENTINEL_B' not in reasons

  def test_admin_trades_full_returns_all_user_rows(self, _admin_client_factory):
    '''Admin with 300 trades gets all 300 back (no dashboard truncation at API layer).'''
    trades = [_make_trade(i) for i in range(300)]
    client, uid_map = _admin_client_factory({'biguser': trades})
    uid = uid_map['biguser']
    cookie = _build_session_cookie(uid)
    resp = client.get('/admin/trades/full', cookies={'tsi_session': cookie})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data['trade_log']) == 300
