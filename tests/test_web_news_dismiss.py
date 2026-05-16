'''Phase 38 Plan 04 — dismiss + collapse-toggle state-write contract tests.

Tests D-08 auto-expiry, per-market isolation, first-visit setdefault safety,
per-user isolation, collapse toggle per-market bool flip.

TDD RED: these tests FAIL before Task 2 lands web/routes/news.py.
'''
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.conftest import VALID_SECRET, AUTH_HEADER_NAME

_AUTH = {AUTH_HEADER_NAME: VALID_SECRET}


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

TODAY = date.today().isoformat()


def _make_app(monkeypatch, state, uid='user_a'):
  '''Build an app + TestClient with:
    - current_user_id overridden to uid
    - state_manager stubs pointing at the provided state dict
    - auth headers pre-configured
  Returns (client, state_box) where state_box['state'] is mutated in place.
  '''
  sys.modules.pop('web.app', None)
  from web.app import create_app
  from web.dependencies import current_user_id
  app = create_app()
  app.dependency_overrides[current_user_id] = lambda: uid

  state_box = {'state': state}

  def _load(*_a, **_kw):
    return state_box['state']

  def _mutate_user(u, mutator, *_a, **_kw):
    mutator(state_box['state'])
    return state_box['state']

  monkeypatch.setattr('state_manager.load_state', _load)
  monkeypatch.setattr('state_manager.mutate_user_state', _mutate_user)

  # TestClient wraps all requests so we can use client-level headers arg
  client = TestClient(app, raise_server_exceptions=True, headers=_AUTH)
  return client, state_box


# ---------------------------------------------------------------------------
# Dismiss writes + D-08 auto-expiry
# ---------------------------------------------------------------------------

class TestDismissWrites:
  def test_dismiss_writes_user_news_dismissed(self, monkeypatch):
    state = {}
    client, sb = _make_app(monkeypatch, state)
    resp = client.post('/news/SPI200/dismiss/abc1234567890def')
    assert resp.status_code == 200
    bucket = sb['state']['users']['user_a']['news_dismissed']['SPI200']
    assert bucket['date'] == TODAY
    assert 'abc1234567890def' in bucket['hashes']

  def test_dismiss_first_visit_user_does_not_crash(self, monkeypatch):
    state = {'users': {'user_a': {}}}
    client, sb = _make_app(monkeypatch, state)
    resp = client.post('/news/SPI200/dismiss/abc1234567890def')
    assert resp.status_code == 200
    bucket = sb['state']['users']['user_a']['news_dismissed']['SPI200']
    assert bucket['date'] == TODAY
    assert 'abc1234567890def' in bucket['hashes']

  def test_dismiss_first_visit_user_without_users_bucket(self, monkeypatch):
    state = {}
    client, sb = _make_app(monkeypatch, state)
    resp = client.post('/news/SPI200/dismiss/abc1234567890def')
    assert resp.status_code == 200
    assert 'users' in sb['state']
    assert 'user_a' in sb['state']['users']
    bucket = sb['state']['users']['user_a']['news_dismissed']['SPI200']
    assert bucket['date'] == TODAY
    assert 'abc1234567890def' in bucket['hashes']

  def test_dismiss_appends_distinct_hashes_same_day(self, monkeypatch):
    state = {
      'users': {
        'user_a': {
          'news_dismissed': {
            'SPI200': {'date': TODAY, 'hashes': ['aaaa1234567890ab']},
          },
        },
      },
    }
    client, sb = _make_app(monkeypatch, state)
    resp = client.post('/news/SPI200/dismiss/bbbb1234567890ab')
    assert resp.status_code == 200
    hashes = sb['state']['users']['user_a']['news_dismissed']['SPI200']['hashes']
    assert len(hashes) == 2
    assert 'aaaa1234567890ab' in hashes
    assert 'bbbb1234567890ab' in hashes

  def test_dismiss_dedupes_same_hash_same_day(self, monkeypatch):
    state = {
      'users': {
        'user_a': {
          'news_dismissed': {
            'SPI200': {'date': TODAY, 'hashes': ['abc1234567890def']},
          },
        },
      },
    }
    client, sb = _make_app(monkeypatch, state)
    resp = client.post('/news/SPI200/dismiss/abc1234567890def')
    assert resp.status_code == 200
    hashes = sb['state']['users']['user_a']['news_dismissed']['SPI200']['hashes']
    assert len(hashes) == 1

  def test_dismiss_d08_auto_expiry_resets_on_date_change(self, monkeypatch):
    state = {
      'users': {
        'user_a': {
          'news_dismissed': {
            'SPI200': {'date': '2020-01-01', 'hashes': ['cc001234567890ab', 'dd001234567890ab']},
          },
        },
      },
    }
    client, sb = _make_app(monkeypatch, state)
    resp = client.post('/news/SPI200/dismiss/ee001234567890ff')
    assert resp.status_code == 200
    bucket = sb['state']['users']['user_a']['news_dismissed']['SPI200']
    assert bucket['date'] == TODAY
    assert 'cc001234567890ab' not in bucket['hashes']
    assert 'dd001234567890ab' not in bucket['hashes']
    assert 'ee001234567890ff' in bucket['hashes']
    assert len(bucket['hashes']) == 1

  def test_dismiss_d08_expiry_is_per_market(self, monkeypatch):
    state = {
      'users': {
        'user_a': {
          'news_dismissed': {
            'SPI200': {'date': '2020-01-01', 'hashes': ['aa00234567890abc']},
            'AUDUSD': {'date': TODAY, 'hashes': ['bb00234567890abc']},
          },
        },
      },
    }
    client, sb = _make_app(monkeypatch, state)
    resp = client.post('/news/SPI200/dismiss/ee001234567890ff')
    assert resp.status_code == 200
    spi_bucket = sb['state']['users']['user_a']['news_dismissed']['SPI200']
    aud_bucket = sb['state']['users']['user_a']['news_dismissed']['AUDUSD']
    assert 'aa00234567890abc' not in spi_bucket['hashes']
    assert 'bb00234567890abc' in aud_bucket['hashes']

  def test_dismiss_isolation_user_a_vs_user_b(self, monkeypatch):
    state_a = {}
    state_b = {}

    # Two separate apps with different uids
    sys.modules.pop('web.app', None)
    from web.app import create_app
    from web.dependencies import current_user_id

    # User A app
    app_a = create_app()
    app_a.dependency_overrides[current_user_id] = lambda: 'user_a'
    sa_box = {'state': state_a}
    # User B app
    sys.modules.pop('web.app', None)
    from web.app import create_app as create_app_b
    app_b = create_app_b()
    app_b.dependency_overrides[current_user_id] = lambda: 'user_b'
    sb_box = {'state': state_b}

    def _mutate_a(u, mutator, *_a, **_kw):
      mutator(sa_box['state'])
      return sa_box['state']

    def _mutate_b(u, mutator, *_a, **_kw):
      mutator(sb_box['state'])
      return sb_box['state']

    monkeypatch.setattr('state_manager.mutate_user_state', _mutate_a)
    c_a = TestClient(app_a, raise_server_exceptions=True, headers=_AUTH)
    c_a.post('/news/SPI200/dismiss/aaaa1234567890ab')

    monkeypatch.setattr('state_manager.mutate_user_state', _mutate_b)
    c_b = TestClient(app_b, raise_server_exceptions=True, headers=_AUTH)
    c_b.post('/news/SPI200/dismiss/bbbb1234567890ab')

    a_hashes = sa_box['state']['users']['user_a']['news_dismissed']['SPI200']['hashes']
    b_hashes = sb_box['state']['users']['user_b']['news_dismissed']['SPI200']['hashes']
    assert a_hashes == ['aaaa1234567890ab']
    assert b_hashes == ['bbbb1234567890ab']

  def test_dismiss_does_not_corrupt_other_user_state(self, monkeypatch):
    state = {
      'users': {
        'user_a': {'paper_trades': [{'id': 'pt-001'}]},
        'user_b': {'paper_trades': [{'id': 'pt-002'}]},
      },
    }
    client, sb = _make_app(monkeypatch, state)
    resp = client.post('/news/SPI200/dismiss/abc1234567890def')
    assert resp.status_code == 200
    # user_b's paper_trades must be untouched
    assert sb['state']['users']['user_b']['paper_trades'] == [{'id': 'pt-002'}]


# ---------------------------------------------------------------------------
# Collapse toggle
# ---------------------------------------------------------------------------

class TestCollapseToggle:
  def test_collapse_toggle_flips_per_market_bool(self, monkeypatch):
    state = {}
    client, sb = _make_app(monkeypatch, state)

    resp = client.post('/news/SPI200/toggle-collapse')
    assert resp.status_code == 200
    assert sb['state']['users']['user_a']['news_panel_collapsed']['SPI200'] is True

    resp = client.post('/news/SPI200/toggle-collapse')
    assert resp.status_code == 200
    assert sb['state']['users']['user_a']['news_panel_collapsed']['SPI200'] is False

  def test_collapse_toggle_first_visit_safe(self, monkeypatch):
    state = {}
    client, sb = _make_app(monkeypatch, state)
    resp = client.post('/news/SPI200/toggle-collapse')
    assert resp.status_code == 200
    assert sb['state']['users']['user_a']['news_panel_collapsed']['SPI200'] is True

  def test_collapse_toggle_is_per_market(self, monkeypatch):
    state = {}
    client, sb = _make_app(monkeypatch, state)
    resp = client.post('/news/SPI200/toggle-collapse')
    assert resp.status_code == 200
    spi_collapsed = sb['state']['users']['user_a']['news_panel_collapsed']['SPI200']
    aud_collapsed = sb['state']['users']['user_a']['news_panel_collapsed'].get('AUDUSD', False)
    assert spi_collapsed is True
    assert aud_collapsed is False
