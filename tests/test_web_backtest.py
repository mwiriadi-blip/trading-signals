"""Phase 23 — web/routes/backtest.py tests (BACKTEST-03/04 web routes).

Six test classes:
  TestGetBacktest       — 200 with cookie + happy paths (latest, empty, override form)
  TestPathTraversal     — ../../etc/passwd → 400; absolute path → 400; valid → 200
  TestPostRun           — 303 on valid form; 400 on negative cost / zero account
  TestCookieAuth        — GET without cookie → 302/401; POST without cookie → 401
  TestHistoryView       — ?history=true returns 200 + table; empty list → empty-state
  TestPerformanceBudget — 1ms stub proves synchronous path exercised (D-14 regression guard)
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import pytest


# ---------- Fixtures ----------

@pytest.fixture
def client():
  """Deferred import — conftest autouse sets WEB_AUTH_* env vars first,
  then we pop the cached module so create_app() re-reads credentials."""
  import sys
  sys.modules.pop('web.app', None)
  from fastapi.testclient import TestClient
  from web.app import create_app
  return TestClient(create_app())

def _request_with_cookies(client, method, url, **kwargs):
  cookies = kwargs.pop('cookies', None)
  if cookies:
    headers = dict(kwargs.pop('headers', {}) or {})
    cookie_parts = [f'{name}={value}' for name, value in cookies.items()]
    existing_cookie = headers.get('cookie') or headers.get('Cookie')
    if existing_cookie:
      cookie_parts.insert(0, existing_cookie)
    headers['cookie'] = '; '.join(cookie_parts)
    kwargs['headers'] = headers
  return client.request(method, url, **kwargs)

@pytest.fixture
def backtest_dir_seeded(tmp_path, monkeypatch):
  """Seed two valid report files into a tmp backtest dir + monkeypatch
  web/routes/backtest.py to use it."""
  d = tmp_path / 'backtests'
  d.mkdir()
  sample = json.loads(Path('tests/fixtures/backtest/golden_report.json').read_text())
  older = d / 'v1.1.0-20260430T080000.json'
  newer = d / 'v1.2.0-20260501T080000.json'
  older.write_text(json.dumps({
    **sample,
    'metadata': {**sample['metadata'], 'strategy_version': 'v1.1.0',
                 'run_dt': '2026-04-30T08:00:00+08:00'},
  }))
  newer.write_text(json.dumps(sample))
  # Explicit mtime so v1.2.0 is always "latest" regardless of write order
  os.utime(older, (1_000_000, 1_000_000))
  os.utime(newer, (2_000_000, 2_000_000))
  monkeypatch.setattr('web.routes.backtest._BACKTEST_DIR', d)
  return d


@pytest.fixture
def empty_backtest_dir(tmp_path, monkeypatch):
  d = tmp_path / 'empty_backtests'
  d.mkdir()
  monkeypatch.setattr('web.routes.backtest._BACKTEST_DIR', d)
  return d


# ---------- TestGetBacktest ----------

class TestGetBacktest:
  def test_get_returns_latest_report(self, client, valid_cookie_token, backtest_dir_seeded):
    r = _request_with_cookies(client, 'GET', '/backtest', cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    body = r.text
    assert 'equityChartCombined' in body
    assert 'equityChartSpi200' in body
    assert 'equityChartAudusd' in body
    assert 'v1.2.0' in body

  def test_get_empty_dir_returns_empty_state(self, client, valid_cookie_token,
                                             empty_backtest_dir):
    r = _request_with_cookies(client, 'GET', '/backtest', cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    assert 'No backtest runs yet' in r.text

  def test_get_includes_override_form(self, client, valid_cookie_token, backtest_dir_seeded):
    r = _request_with_cookies(client, 'GET', '/backtest', cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    assert 'name="initial_account_aud"' in r.text
    assert 'action="/backtest/run"' in r.text


# ---------- TestPathTraversal ----------

class TestPathTraversal:
  def test_traversal_dotdot_etc_passwd_returns_400(self, client, valid_cookie_token,
                                                   backtest_dir_seeded):
    r = _request_with_cookies(client, 'GET', '/backtest?run=../../etc/passwd',
                   cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 400
    assert 'Invalid backtest filename' in r.text

  def test_traversal_absolute_path_returns_400(self, client, valid_cookie_token,
                                               backtest_dir_seeded):
    r = _request_with_cookies(client, 'GET', '/backtest?run=/etc/passwd',
                   cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 400

  def test_traversal_with_slashes_returns_400(self, client, valid_cookie_token,
                                              backtest_dir_seeded):
    r = _request_with_cookies(client, 'GET', '/backtest?run=foo/bar.json',
                   cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 400

  def test_unknown_filename_returns_400(self, client, valid_cookie_token,
                                        backtest_dir_seeded):
    r = _request_with_cookies(client, 'GET', '/backtest?run=does-not-exist.json',
                   cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 400

  def test_valid_filename_returns_200(self, client, valid_cookie_token,
                                      backtest_dir_seeded):
    r = _request_with_cookies(client, 'GET', '/backtest?run=v1.1.0-20260430T080000.json',
                   cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    assert 'v1.1.0' in r.text


# ---------- TestPostRun ----------

class TestPostRun:
  @pytest.fixture
  def patched_run_backtest(self, monkeypatch):
    """Stub run_backtest so we don't actually fetch yfinance during web tests."""
    def _fake(args):
      return ({'metadata': {'pass': True}}, Path('/tmp/fake.json'), 0)
    monkeypatch.setattr('web.routes.backtest.run_backtest', _fake)
    return _fake

  def test_valid_post_redirects_303(self, client, valid_cookie_token,
                                     patched_run_backtest, backtest_dir_seeded):
    r = _request_with_cookies(client, 'POST', 
      '/backtest/run',
      data={'initial_account_aud': '10000', 'cost_spi_aud': '6.0',
            'cost_audusd_aud': '5.0'},
      cookies={'tsi_session': valid_cookie_token},
      follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers['location'] == '/backtest'

  def test_zero_account_returns_400(self, client, valid_cookie_token,
                                    patched_run_backtest, backtest_dir_seeded):
    r = _request_with_cookies(client, 'POST', 
      '/backtest/run',
      data={'initial_account_aud': '0', 'cost_spi_aud': '6.0',
            'cost_audusd_aud': '5.0'},
      cookies={'tsi_session': valid_cookie_token},
      follow_redirects=False,
    )
    assert r.status_code == 400
    assert 'greater than zero' in r.text

  def test_negative_account_returns_400(self, client, valid_cookie_token,
                                        patched_run_backtest, backtest_dir_seeded):
    r = _request_with_cookies(client, 'POST', 
      '/backtest/run',
      data={'initial_account_aud': '-100', 'cost_spi_aud': '6.0',
            'cost_audusd_aud': '5.0'},
      cookies={'tsi_session': valid_cookie_token},
      follow_redirects=False,
    )
    assert r.status_code == 400

  def test_negative_cost_spi_returns_400(self, client, valid_cookie_token,
                                          patched_run_backtest, backtest_dir_seeded):
    r = _request_with_cookies(client, 'POST', 
      '/backtest/run',
      data={'initial_account_aud': '10000', 'cost_spi_aud': '-1',
            'cost_audusd_aud': '5.0'},
      cookies={'tsi_session': valid_cookie_token},
      follow_redirects=False,
    )
    assert r.status_code == 400
    assert 'SPI 200 cost' in r.text

  def test_negative_cost_audusd_returns_400(self, client, valid_cookie_token,
                                             patched_run_backtest, backtest_dir_seeded):
    r = _request_with_cookies(client, 'POST', 
      '/backtest/run',
      data={'initial_account_aud': '10000', 'cost_spi_aud': '6.0',
            'cost_audusd_aud': '-0.01'},
      cookies={'tsi_session': valid_cookie_token},
      follow_redirects=False,
    )
    assert r.status_code == 400
    assert 'AUD/USD cost' in r.text

  def test_zero_cost_is_allowed(self, client, valid_cookie_token,
                                patched_run_backtest, backtest_dir_seeded):
    r = _request_with_cookies(client, 'POST', 
      '/backtest/run',
      data={'initial_account_aud': '10000', 'cost_spi_aud': '0',
            'cost_audusd_aud': '0'},
      cookies={'tsi_session': valid_cookie_token},
      follow_redirects=False,
    )
    assert r.status_code == 303


# ---------- TestCookieAuth ----------

class TestCookieAuth:
  def test_get_without_cookie_browser_redirects(self, client, backtest_dir_seeded):
    r = client.get('/backtest', headers={'Accept': 'text/html'},
                   follow_redirects=False)
    assert r.status_code in (302, 401)
    if r.status_code == 302:
      assert '/login' in r.headers.get('location', '')

  def test_get_without_cookie_curl_returns_401(self, client, backtest_dir_seeded):
    r = client.get('/backtest', headers={'Accept': '*/*'},
                   follow_redirects=False)
    assert r.status_code in (401, 302)

  def test_post_without_cookie_returns_401(self, client, backtest_dir_seeded):
    r = client.post(
      '/backtest/run',
      data={'initial_account_aud': '10000', 'cost_spi_aud': '6.0',
            'cost_audusd_aud': '5.0'},
      follow_redirects=False,
    )
    assert r.status_code == 401


# ---------- TestHistoryView ----------

class TestHistoryView:
  def test_history_returns_200_with_table(self, client, valid_cookie_token,
                                           backtest_dir_seeded):
    r = _request_with_cookies(client, 'GET', '/backtest?history=true',
                   cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    body = r.text
    assert 'history-table' in body or 'Backtest history' in body
    assert 'v1.2.0' in body
    assert 'v1.1.0' in body

  def test_history_empty_dir_returns_200_empty_state(self, client, valid_cookie_token,
                                                     empty_backtest_dir):
    r = _request_with_cookies(client, 'GET', '/backtest?history=true',
                   cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    assert 'No backtest history yet' in r.text

  def test_history_overlay_chart_present(self, client, valid_cookie_token,
                                          backtest_dir_seeded):
    r = _request_with_cookies(client, 'GET', '/backtest?history=true',
                   cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    assert 'equityChartHistory' in r.text


# ---------- TestPerformanceBudget (D-14 timeout regression guard) ----------

class TestPerformanceBudget:
  """D-14 + D-18: POST /backtest/run must succeed via the synchronous path.

  A 1ms stub proves the route is exercised end-to-end without timing out.
  The absolute 60s uvicorn bound is verified manually on the droplet
  (VALIDATION.md Manual-Only). This is the cheap regression guard.
  """

  def test_post_with_fast_stub_returns_303(self, client, valid_cookie_token,
                                            backtest_dir_seeded, monkeypatch):
    def _fast_stub(args):
      return ({'metadata': {'pass': True}}, Path('/tmp/fake.json'), 0)
    monkeypatch.setattr('web.routes.backtest.run_backtest', _fast_stub)

    r = _request_with_cookies(client, 'POST', 
      '/backtest/run',
      data={'initial_account_aud': '10000', 'cost_spi_aud': '6.0',
            'cost_audusd_aud': '5.0'},
      cookies={'tsi_session': valid_cookie_token},
      follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers['location'] == '/backtest'
