'''Phase 38 Plan 04 — web/routes/news.py + dashboard_renderer/components/news.py tests.

Tests: POST route registration, auth gates, hash/market validation, f-string renderer
contract (no Jinja2, explicit html.escape, filter-before-banner, locked copies).

TDD RED: these tests FAIL before Tasks 2+3 land.
'''
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import VALID_SECRET, AUTH_HEADER_NAME

_AUTH_HEADERS = {AUTH_HEADER_NAME: VALID_SECRET}


# ---------------------------------------------------------------------------
# Local app fixture (matches test_web_healthz.py pattern)
# ---------------------------------------------------------------------------

@pytest.fixture
def app_instance():
  sys.modules.pop('web.app', None)
  from web.app import create_app
  return create_app()


@pytest.fixture
def client(app_instance):
  return TestClient(app_instance, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

_state_box = {}


def _stub_mutate_user_state(uid, mutator, *_a, **_kw):
  if 'state' not in _state_box:
    _state_box['state'] = {}
  mutator(_state_box['state'])
  return _state_box['state']


# ---------------------------------------------------------------------------
# Route registration tests
# ---------------------------------------------------------------------------

class TestRouteRegistration:
  def test_register_attaches_dismiss_route(self, app_instance):
    routes = [str(r.path) for r in app_instance.routes]
    assert '/news/{market}/dismiss/{title_hash}' in routes

  def test_register_attaches_collapse_toggle_route_is_POST(self, app_instance):
    from fastapi.routing import APIRoute
    toggle_routes = [
      r for r in app_instance.routes
      if isinstance(r, APIRoute) and r.path == '/news/{market}/toggle-collapse'
    ]
    assert toggle_routes, 'No route found at /news/{market}/toggle-collapse'
    methods = {m for r in toggle_routes for m in (r.methods or [])}
    assert 'POST' in methods, 'POST not registered for toggle-collapse'
    # GET must NOT mutate
    assert 'GET' not in methods, 'GET must NOT be registered for toggle-collapse'

  def test_dismiss_route_requires_auth(self, client, monkeypatch):
    monkeypatch.setattr('state_manager.mutate_user_state', _stub_mutate_user_state)
    # No auth header — AuthMiddleware blocks before Depends fires (401)
    resp = client.post('/news/SPI200/dismiss/abc1234567890def', follow_redirects=False)
    assert resp.status_code in (401, 403)

  def test_dismiss_route_authenticated_returns_200_empty_html(self, app_instance, monkeypatch):
    from web.dependencies import current_user_id
    app_instance.dependency_overrides[current_user_id] = lambda: 'user_a'
    monkeypatch.setattr('state_manager.mutate_user_state', _stub_mutate_user_state)
    c = TestClient(app_instance, raise_server_exceptions=True)
    resp = c.post('/news/SPI200/dismiss/abc1234567890def', headers=_AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.text == ''
    assert 'text/html' in resp.headers.get('content-type', '')

  def test_dismiss_route_rejects_unknown_market(self, app_instance, monkeypatch):
    from web.dependencies import current_user_id
    app_instance.dependency_overrides[current_user_id] = lambda: 'user_a'
    monkeypatch.setattr('state_manager.mutate_user_state', _stub_mutate_user_state)
    c = TestClient(app_instance, raise_server_exceptions=False)
    resp = c.post('/news/UNKNOWN/dismiss/abc1234567890deff', headers=_AUTH_HEADERS)
    assert resp.status_code == 404

  def test_dismiss_route_rejects_invalid_hash(self, app_instance, monkeypatch):
    from web.dependencies import current_user_id
    app_instance.dependency_overrides[current_user_id] = lambda: 'user_a'
    monkeypatch.setattr('state_manager.mutate_user_state', _stub_mutate_user_state)
    c = TestClient(app_instance, raise_server_exceptions=False)
    resp = c.post('/news/SPI200/dismiss/not-a-valid-hash', headers=_AUTH_HEADERS)
    assert resp.status_code == 422

  def test_collapse_toggle_returns_empty_200(self, app_instance, monkeypatch):
    from web.dependencies import current_user_id
    app_instance.dependency_overrides[current_user_id] = lambda: 'user_a'
    monkeypatch.setattr('state_manager.mutate_user_state', _stub_mutate_user_state)
    c = TestClient(app_instance, raise_server_exceptions=True)
    resp = c.post('/news/SPI200/toggle-collapse', headers=_AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.text == ''

  def test_collapse_toggle_rejects_get_verb(self, app_instance):
    # GET is not registered — must result in 405 Method Not Allowed.
    # Middleware fires first (401 without auth), so pass auth headers to ensure
    # the method-check is exercised by FastAPI rather than short-circuited by auth.
    from fastapi.routing import APIRoute
    toggle_routes = [
      r for r in app_instance.routes
      if isinstance(r, APIRoute) and r.path == '/news/{market}/toggle-collapse'
    ]
    for r in toggle_routes:
      methods = r.methods or set()
      assert 'GET' not in methods, 'GET must NOT be registered for toggle-collapse'
    # Also verify via HTTP: with auth, GET on this path returns 405
    c = TestClient(app_instance, raise_server_exceptions=False)
    resp = c.get('/news/SPI200/toggle-collapse', headers=_AUTH_HEADERS, follow_redirects=False)
    assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Renderer contract tests
# ---------------------------------------------------------------------------

class TestNewsRenderer:
  def _make_headline(self, title='RBA Cuts Rates', url='https://example.com/article',
                     publisher='AFR', pub_date='2026-05-16',
                     title_hash='abc1234567890deff'):
    return {
      'title': title,
      'url': url,
      'publisher': publisher,
      'pub_date': pub_date,
      'title_hash': title_hash,
    }

  def test_renderer_does_not_use_jinja2(self):
    src = Path('dashboard_renderer/components/news.py').read_text()
    # No Jinja2 import (import Jinja2Templates or from fastapi.templating import ...)
    assert 'import Jinja2Templates' not in src
    assert 'fastapi.templating' not in src
    assert 'render_template' not in src
    assert src.count('html.escape') >= 4

  def test_xss_headline_renders_escaped(self):
    from dashboard_renderer.components.news import render_news_panel
    h = self._make_headline(title='<script>alert(1)</script>')
    html = render_news_panel('SPI200', [h], set(), False)
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html

  def test_headline_anchor_carries_rel_noopener(self):
    from dashboard_renderer.components.news import render_news_panel
    h = self._make_headline(url='https://example.com/x')
    html = render_news_panel('SPI200', [h], set(), False)
    assert 'rel="noopener noreferrer"' in html

  def test_news_panel_open_by_default(self):
    from dashboard_renderer.components.news import render_news_panel
    h = self._make_headline()
    html = render_news_panel('SPI200', [h], set(), False)
    assert '<details class="news-panel-disclosure" open>' in html

  def test_news_panel_collapsed_when_pref_true(self):
    from dashboard_renderer.components.news import render_news_panel
    h = self._make_headline()
    html = render_news_panel('SPI200', [h], set(), True)
    assert '<details class="news-panel-disclosure">' in html
    assert '<details class="news-panel-disclosure" open>' not in html

  def test_banner_renders_with_locked_copy(self):
    from dashboard_renderer.components.news import render_news_panel
    # Use a headline that triggers SPI200 critical event (rba keyword)
    h = self._make_headline(
      title='RBA raises interest rate by 25 basis points',
      title_hash='crit1234567890ab',
    )
    html = render_news_panel('SPI200', [h], set(), False)
    assert 'Possible market-moving news — operator review recommended' in html

  def test_banner_absent_when_no_critical_event(self):
    from dashboard_renderer.components.news import render_news_panel
    h = self._make_headline(title='Company reports quarterly earnings')
    html = render_news_panel('SPI200', [h], set(), False)
    assert 'Possible market-moving news' not in html

  def test_dismissed_hash_filters_out_row(self):
    from dashboard_renderer.components.news import render_news_panel
    h = self._make_headline(title_hash='abc1234567890deff')
    html = render_news_panel('SPI200', [h], {'abc1234567890deff'}, False)
    assert 'abc1234567890deff' not in html

  def test_banner_disappears_when_only_critical_headline_dismissed(self):
    from dashboard_renderer.components.news import render_news_panel
    # Critical headline that matches SPI200 keyword
    critical = self._make_headline(
      title='RBA raises interest rate by 50 basis points',
      title_hash='crit1234567890ab',
    )
    benign = self._make_headline(
      title='Company reports quarterly earnings',
      title_hash='beni1234567890ab',
    )
    # Dismiss the critical one — banner must disappear
    html = render_news_panel('SPI200', [critical, benign], {'crit1234567890ab'}, False)
    assert 'Possible market-moving news' not in html

  def test_summary_label_is_market_news(self):
    from dashboard_renderer.components.news import render_news_panel
    h = self._make_headline()
    html = render_news_panel('SPI200', [h], set(), False)
    assert '<summary class="news-panel-summary">Market News</summary>' in html

  def test_dismiss_button_label_is_dismiss_headline(self):
    from dashboard_renderer.components.news import render_news_panel
    h = self._make_headline()
    html = render_news_panel('SPI200', [h], set(), False)
    assert 'Dismiss Headline' in html
