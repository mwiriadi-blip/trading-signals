'''Phase 36 TENANT-03 — cross-tenant isolation quality gate.

TestTenantIsolation verifies that user A's trade content is ABSENT from:
  (a) GET /admin/users response (Wave 1 makes green)
  (b) crash-email body (Phase 37 deferred — stubbed/skipped)
  (c) user B's dashboard / market page (Phase 37 deferred — stubbed/skipped)

TRADE_CONTENT_RE matches any of the PII trade fields that must never leak
across tenant boundaries. Zero matches in the response body is the pass condition.

References: TENANT-03, D-13, T-36-01, T-36-02.
'''
import re
import sys
import time

import pytest
from fastapi.testclient import TestClient
from itsdangerous.url_safe import URLSafeTimedSerializer

from tests.conftest import VALID_SECRET, VALID_USERNAME

# Regex that matches any trade-content field that must never appear in
# cross-tenant responses (TENANT-03 / D-13).
TRADE_CONTENT_RE = re.compile(
  r'(entry_price|n_contracts|"direction":\s*"(LONG|SHORT)")',
  re.IGNORECASE,
)


def _build_session_cookie(uid, *, username=None):
  '''Build a signed tsi_session cookie for tests.'''
  username = username or VALID_USERNAME
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-session-cookie')
  return serializer.dumps({'u': username, 'iat': int(time.time()), 'uid': uid})


@pytest.fixture
def two_user_client(isolated_auth_json, monkeypatch):
  '''TestClient with two users: uid_a (has 5 paper trades), uid_b (none).

  Monkeypatches load_state and mutate_user_state to inject seeded state.
  Returns (client, uid_a, uid_b).
  '''
  # test_tenant_isolation.py does not match test_web_* pattern so the autouse
  # fixture in conftest.py does not set these env vars. Set them here so
  # create_app() does not raise RuntimeError (D-16/D-17 fail-closed check).
  monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
  monkeypatch.setenv('WEB_AUTH_USERNAME', VALID_USERNAME)
  monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', 'mwiriadi@gmail.com')

  sys.modules.pop('web.app', None)

  import auth_store
  import state_manager

  user_a = auth_store.create_user({'email': 'alice@example.com', 'role': 'admin'})
  user_b = auth_store.create_user({'email': 'bob@example.com', 'role': 'ff'})
  uid_a = user_a['uid']
  uid_b = user_b['uid']

  # 5 paper trades for user A — all with trade-content fields.
  paper_trades_a = [
    {
      'id': f'SPI200-20260501-00{i}',
      'instrument': 'SPI200',
      'side': 'LONG',
      'entry_dt': '2026-05-01T08:00:00+08:00',
      'entry_price': 8000.0 + i * 10,
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
    for i in range(5)
  ]

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
    'users': {
      uid_a: {
        'account': 100_000.0,
        'initial_account': 100_000.0,
        'contracts': {},
        'positions': {'SPI200': None, 'AUDUSD': None},
        'trade_log': [],
        'equity_history': [],
        'paper_trades': paper_trades_a,
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

  from web.app import create_app
  client = TestClient(create_app(), raise_server_exceptions=False)
  return client, uid_a, uid_b


class TestTenantIsolation:
  '''Cross-tenant isolation gate (TENANT-03 / D-13).

  test_admin_users_response_has_no_trade_content: Wave 1 makes this green.
  The other two tests are Phase 37 stubs (fan-out + user-B dashboard).
  '''

  def test_admin_users_response_has_no_trade_content(self, two_user_client):
    '''GET /admin/users JSON body must contain zero TRADE_CONTENT_RE matches.

    User A has 5 paper trades with entry_price / n_contracts. The admin list
    endpoint must strip all such fields via response_model=list[PublicUserSummary].
    '''
    client, uid_a, uid_b = two_user_client
    cookie = _build_session_cookie(uid_a)
    resp = client.get(
      '/admin/users',
      cookies={'tsi_session': cookie},
      headers={'Accept': 'application/json'},
    )
    assert resp.status_code == 200
    body_text = str(resp.json())
    matches = TRADE_CONTENT_RE.findall(body_text)
    assert matches == [], (
      f'Trade content leaked into /admin/users response: {matches}'
    )

  @pytest.mark.skip(reason='SC-5 deferred: crash-email body assertions not yet written')
  def test_crash_email_body_has_no_trade_content(self, two_user_client):
    '''Crash-email body must contain zero TRADE_CONTENT_RE matches.

    Deferred to Phase 37 when crash_boundary.py per-user logging path lands
    and explicit redaction filter is added (CONTEXT D-12).
    '''

  def test_other_user_dashboard_has_no_user_a_trade_content(self, two_user_client):
    '''User B's served dashboard must contain zero matches for user A's trade fields.

    Setup: user A has 5 paper trades with entry_price/n_contracts/LONG direction.
    Authenticate as user B, GET /account, assert no trade content from user A
    appears in the response HTML.

    Phase 32 retired /dashboard; /account is where render_paper_trades_region
    renders. SC-5 closed: per-user state scoping lands on /account via
    _serve_account_page_scoped (D-16, D-17, D-18).
    '''
    client, uid_a, uid_b = two_user_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.get('/account', cookies={'tsi_session': cookie_b})
    body_text = resp.text
    matches = TRADE_CONTENT_RE.findall(body_text)
    assert matches == [], (
      f'User A trade content leaked into user B dashboard: {matches}'
    )
