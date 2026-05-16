'''Phase 38 Plan 04 Task 3 — integration tests for news panel in live dashboard.

Verifies:
- /markets/{m}/signals includes news panel HTML
- Dismissed hashes are filtered (not shown)
- Stale dismiss bucket treated as empty at render time
- Collapsed pref renders without open attr
- First-visit users with no news state render without crash

TDD RED: fails before Task 3 wires render_news_panel into signals.py.
'''
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import VALID_SECRET, AUTH_HEADER_NAME

TODAY = date.today().isoformat()
_AUTH = {AUTH_HEADER_NAME: VALID_SECRET}

# ---------------------------------------------------------------------------
# Fixed headline list (monkeypatched to avoid yfinance)
# ---------------------------------------------------------------------------

_FIXED_HEADLINES = [
  {
    'title': 'RBA holds interest rate steady',
    'url': 'https://example.com/rba',
    'publisher': 'AFR',
    'pub_date': TODAY,
    'title_hash': 'aa001234567890bc',
  },
  {
    'title': 'Company quarterly earnings beat expectations',
    'url': 'https://example.com/earnings',
    'publisher': 'SMH',
    'pub_date': TODAY,
    'title_hash': 'bb001234567890bc',
  },
]


def _make_state(markets=None, users=None):
  '''Minimal state with SPI200 + AUDUSD markets for testing.'''
  return {
    'schema_version': 12,
    'admin_user_id': 'admin-uid',
    'last_run': TODAY,
    'signals': {
      'SPI200': {'signal': 0, 'signal_as_of': TODAY, 'last_scalars': {}},
      'AUDUSD': {'signal': 0, 'signal_as_of': TODAY, 'last_scalars': {}},
    },
    'markets': markets or {
      'SPI200': {'display_name': 'SPI 200', 'symbol': 'ES=F'},
      'AUDUSD': {'display_name': 'AUD/USD', 'symbol': 'AUDUSD=X'},
    },
    'strategy_settings': {},
    'warnings': [],
    '_resolved_contracts': {},
    'positions': {},
    'users': users or {},
  }


def _make_app(monkeypatch, state, uid='user_a'):
  sys.modules.pop('web.app', None)
  from web.app import create_app
  from web.dependencies import current_user_id

  app = create_app()
  app.dependency_overrides[current_user_id] = lambda: uid

  state_box = {'state': state}

  monkeypatch.setattr('state_manager.load_state', lambda *_a, **_kw: state_box['state'])
  monkeypatch.setattr('state_manager.mutate_user_state',
                      lambda u, m, *_a, **_kw: m(state_box['state']) or state_box['state'])
  monkeypatch.setattr('news_fetcher.fetch_news', lambda *_a, **_kw: list(_FIXED_HEADLINES))

  return TestClient(app, raise_server_exceptions=True, headers=_AUTH), state_box


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNewsOnDashboard:
  def test_market_signals_page_contains_news_panel_spi200(self, monkeypatch):
    state = _make_state()
    client, _ = _make_app(monkeypatch, state)
    resp = client.get('/markets/SPI200/signals')
    assert resp.status_code == 200
    assert 'news-panel-disclosure' in resp.text
    assert '<summary class="news-panel-summary">Market News</summary>' in resp.text

  def test_market_signals_page_contains_news_panel_audusd(self, monkeypatch):
    state = _make_state()
    client, _ = _make_app(monkeypatch, state)
    resp = client.get('/markets/AUDUSD/signals')
    assert resp.status_code == 200
    assert 'news-panel-disclosure' in resp.text
    assert 'Market News' in resp.text

  def test_news_panel_appears_after_signal_card(self, monkeypatch):
    state = _make_state()
    client, _ = _make_app(monkeypatch, state)
    resp = client.get('/markets/SPI200/signals')
    body = resp.text
    card_idx = body.find('class="card"')
    panel_idx = body.find('class="news-panel-disclosure"')
    assert card_idx >= 0, 'No card found'
    assert panel_idx >= 0, 'No news panel found'
    assert panel_idx > card_idx, 'News panel must appear after signal card'

  def test_dismissed_hash_hidden_from_dashboard(self, monkeypatch):
    state = _make_state(users={
      'user_a': {
        'news_dismissed': {
          'SPI200': {'date': TODAY, 'hashes': ['aa001234567890bc']},
        },
      },
    })
    client, _ = _make_app(monkeypatch, state)
    resp = client.get('/markets/SPI200/signals')
    assert resp.status_code == 200
    # First headline (aa00...) dismissed — its hash row must be absent
    assert 'aa001234567890bc' not in resp.text
    # Second headline must still appear
    assert 'bb001234567890bc' in resp.text

  def test_dismissed_hash_stale_date_treated_as_empty(self, monkeypatch):
    state = _make_state(users={
      'user_a': {
        'news_dismissed': {
          'SPI200': {'date': '2020-01-01', 'hashes': ['aa001234567890bc']},
        },
      },
    })
    client, _ = _make_app(monkeypatch, state)
    resp = client.get('/markets/SPI200/signals')
    assert resp.status_code == 200
    # Stale bucket (2020 != today) treated as empty — first headline visible
    assert 'aa001234567890bc' in resp.text

  def test_collapsed_pref_renders_without_open_attr(self, monkeypatch):
    state = _make_state(users={
      'user_a': {
        'news_panel_collapsed': {'SPI200': True},
      },
    })
    client, _ = _make_app(monkeypatch, state)
    resp = client.get('/markets/SPI200/signals')
    assert resp.status_code == 200
    assert '<details class="news-panel-disclosure">' in resp.text
    assert '<details class="news-panel-disclosure" open>' not in resp.text

  def test_dashboard_renders_when_no_news_state_present(self, monkeypatch):
    state = _make_state(users={'user_a': {}})
    client, _ = _make_app(monkeypatch, state)
    resp = client.get('/markets/SPI200/signals')
    assert resp.status_code == 200
    assert 'news-panel-disclosure' in resp.text

  def test_dashboard_renders_when_users_bucket_absent(self, monkeypatch):
    state = _make_state(users={})
    client, _ = _make_app(monkeypatch, state)
    resp = client.get('/markets/SPI200/signals')
    assert resp.status_code == 200
    assert 'news-panel-disclosure' in resp.text

  def test_news_panel_uses_authenticated_uid(self, monkeypatch):
    # user_a has dismissed aa00..., user_b has dismissed bb00...
    state = _make_state(users={
      'user_a': {
        'news_dismissed': {
          'SPI200': {'date': TODAY, 'hashes': ['aa001234567890bc']},
        },
      },
      'user_b': {
        'news_dismissed': {
          'SPI200': {'date': TODAY, 'hashes': ['bb001234567890bc']},
        },
      },
    })
    client, _ = _make_app(monkeypatch, state, uid='user_a')
    resp = client.get('/markets/SPI200/signals')
    assert resp.status_code == 200
    # user_a's dismiss filters aa00... but NOT bb00...
    assert 'aa001234567890bc' not in resp.text
    assert 'bb001234567890bc' in resp.text
