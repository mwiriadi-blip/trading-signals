'''Phase 38 Plan 03 tests: news_fetcher.py — I/O adapter for yfinance news.

Tests cover: NewsItem TypedDict shape (including title_hash), both yfinance
schema normalisations (pre-0.2.55 and post-0.2.55), JSON-date-field TTL cache
semantics, market_id allowlist (path-traversal closed), URL scheme validation,
XSS pass-through (escape is render-time-only), SSRF closure (no server-side
link prefetch), dedup by title_hash, and AST hex-boundary gate.
'''
import ast
import hashlib
import json
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import news_fetcher
from news_fetcher import (
  NewsItem,
  _cache_path,
  _compute_title_hash,
  _is_valid_market_id,
  _load_cache,
  _normalise_item,
  _normalise_title_for_hash,
  _validate_url_scheme,
  _write_cache,
  fetch_news,
)

# Import the AST gate constant from test_signal_engine
from tests.test_signal_engine import FORBIDDEN_MODULES_NEWS_FETCHER, NEWS_FETCHER_PATH


# =========================================================================
# Helpers / fixtures
# =========================================================================

PRE055_FIXTURE = Path('tests/fixtures/news/news_fixture_pre055.json')
POST055_FIXTURE = Path('tests/fixtures/news/news_fixture_post055.json')


def _load_json(path: Path) -> list:
  with open(path, encoding='utf-8') as f:
    return json.load(f)


class FakeTicker:
  def __init__(self, news_items: list):
    self._news = news_items

  @property
  def news(self):
    return self._news


class FakeYF:
  def __init__(self, news_items: list):
    self._items = news_items

  def Ticker(self, symbol, **kwargs):
    return FakeTicker(self._items)


# =========================================================================
# Task 1 tests: NewsItem shape and title_hash
# =========================================================================

def test_newsitem_includes_title_hash_field():
  assert 'title_hash' in NewsItem.__annotations__
  assert NewsItem.__annotations__['title_hash'] is str


def test_title_hash_is_16_char_hex():
  items = _load_json(POST055_FIXTURE)
  for raw in items:
    result = _normalise_item(raw)
    if result is not None:
      assert re.match(r'^[0-9a-f]{16}$', result['title_hash']), (
        f"title_hash {result['title_hash']!r} is not 16 hex chars"
      )
      break
  else:
    pytest.fail('No items normalised from post055 fixture')


def test_title_hash_is_stable_across_whitespace_and_case():
  h1 = _compute_title_hash('  RBA Cuts Rates  ')
  h2 = _compute_title_hash('rba cuts rates')
  h3 = _compute_title_hash('RBA cuts  rates')
  assert h1 == h2 == h3, (
    f'title_hash not stable: {h1!r} vs {h2!r} vs {h3!r}'
  )


def test_title_hash_distinguishes_different_titles():
  assert _compute_title_hash('RBA cuts rates') != _compute_title_hash('Fed cuts rates')


# =========================================================================
# Schema normalisation
# =========================================================================

def test_normalise_post055_shape():
  items = _load_json(POST055_FIXTURE)
  found_one = False
  for raw in items:
    result = _normalise_item(raw)
    if result is None:
      continue
    found_one = True
    c = raw['content']
    assert isinstance(result['title'], str) and result['title'], 'title must be non-empty str'
    assert re.match(r'^[0-9a-f]{16}$', result['title_hash']), 'title_hash must be 16 hex chars'
    # url is valid scheme or empty
    assert result['url'] == '' or result['url'].startswith(('https://', 'http://')), (
      f"url has invalid scheme: {result['url']!r}"
    )
    assert result['publisher'] == c['provider']['displayName']
    assert result['pub_date'] == c['pubDate']
  assert found_one, 'at least one post055 item must normalise'


def test_normalise_pre055_shape():
  items = _load_json(PRE055_FIXTURE)
  found_one = False
  for raw in items:
    result = _normalise_item(raw)
    if result is None:
      continue
    found_one = True
    assert result['title'] == raw['title'].strip()
    # url: scheme-validated version of raw['link']
    link = raw.get('link', '')
    if link.startswith(('https://', 'http://')):
      assert result['url'] == link
    else:
      assert result['url'] == ''
    assert result['publisher'] == raw['publisher']
    # pub_date is ISO 8601 string from unix timestamp
    ts = raw.get('providerPublishTime', 0)
    expected = datetime.fromtimestamp(ts, UTC).strftime('%Y-%m-%dT%H:%M:%SZ') if ts else ''
    assert result['pub_date'] == expected
    assert 'title_hash' in result
  assert found_one, 'at least one pre055 item must normalise'


def test_normalise_returns_none_on_missing_title():
  assert _normalise_item({'content': {'title': ''}}) is None
  assert _normalise_item({'uuid': 'x', 'title': ''}) is None
  assert _normalise_item({}) is None


def test_normalise_dispatch_unknown_shape():
  assert _normalise_item({'foo': 'bar'}) is None


def test_title_hash_dedup(monkeypatch, tmp_path):
  monkeypatch.chdir(tmp_path)
  # Two items with identical title
  dup_items = [
    {
      'content': {
        'title': 'RBA cuts rates',
        'pubDate': '2026-05-07T10:00:00Z',
        'provider': {'displayName': 'AFR'},
        'canonicalUrl': {'url': 'https://example.com/1'},
        'clickThroughUrl': None,
      }
    },
    {
      'content': {
        'title': 'RBA cuts rates',
        'pubDate': '2026-05-07T11:00:00Z',
        'provider': {'displayName': 'Reuters'},
        'canonicalUrl': {'url': 'https://example.com/2'},
        'clickThroughUrl': None,
      }
    },
  ]
  monkeypatch.setattr('news_fetcher._get_yf', lambda: FakeYF(dup_items))
  result = fetch_news('SPI200', '^AXJO')
  hashes = [item['title_hash'] for item in result]
  assert len(hashes) == len(set(hashes)), 'Duplicate title_hash found — dedup failed'
  # exactly one entry for the duplicated title
  rba_items = [item for item in result if 'rba cuts rates' in item['title'].lower()]
  assert len(rba_items) == 1


# =========================================================================
# URL scheme validation (defence-in-depth)
# =========================================================================

def test_url_scheme_https_accepted():
  assert _validate_url_scheme('https://example.com/x') == 'https://example.com/x'


def test_url_scheme_http_accepted():
  assert _validate_url_scheme('http://example.com/x') == 'http://example.com/x'


def test_url_scheme_javascript_rejected():
  assert _validate_url_scheme('javascript:alert(1)') == ''


def test_url_scheme_data_rejected():
  assert _validate_url_scheme('data:text/html,<script>alert(1)</script>') == ''


def test_url_scheme_relative_rejected():
  assert _validate_url_scheme('/relative/path') == ''


def test_url_scheme_empty_rejected():
  assert _validate_url_scheme('') == ''


def test_normalise_strips_javascript_url():
  raw = {
    'content': {
      'title': 'Market news',
      'pubDate': '2026-05-07T10:00:00Z',
      'provider': {'displayName': 'Test Publisher'},
      'clickThroughUrl': {'url': 'javascript:alert(1)'},
      'canonicalUrl': {'url': 'https://fallback.example.com/'},
    }
  }
  result = _normalise_item(raw)
  assert result is not None
  # clickThroughUrl has javascript: → rejected; falls back to canonicalUrl
  # But plan spec says clickThroughUrl takes precedence, so rejected → ''
  # Actually per _normalise_post_055: url_obj = c.get('clickThroughUrl') or c.get('canonicalUrl')
  # If clickThroughUrl is truthy (a dict), it wins; validate_url_scheme rejects 'javascript:...'
  assert result['url'] == ''


# =========================================================================
# market_id allowlist (path-traversal closed)
# =========================================================================

def test_cache_path_rejects_unknown_market(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  with pytest.raises(ValueError):
    _cache_path('../../etc/passwd')
  # no file written under tmp_path
  assert list(tmp_path.iterdir()) == []


def test_cache_path_rejects_traversal_chars(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  with pytest.raises(ValueError):
    _cache_path('SPI200/../OTHER')


def test_fetch_news_unknown_market_returns_empty_no_fetch(monkeypatch, tmp_path):
  monkeypatch.chdir(tmp_path)
  # _get_yf should never be called for unknown market
  def _raise_if_called():
    raise AssertionError('_get_yf must not be called for unknown market')
  monkeypatch.setattr('news_fetcher._get_yf', _raise_if_called)
  result = fetch_news('UNKNOWN_MARKET', 'XXX')
  assert result == []


# =========================================================================
# Cache behaviour (JSON date field is authoritative TTL)
# =========================================================================

def test_cache_hit_uses_json_date_field_not_mtime(monkeypatch, tmp_path):
  monkeypatch.chdir(tmp_path)
  today = date.today().isoformat()
  sample = [
    {
      'title': 'Cached headline',
      'url': 'https://example.com/',
      'publisher': 'Test',
      'pub_date': '2026-05-07T10:00:00Z',
      'title_hash': 'a' * 16,
    }
  ]
  sidecar = tmp_path / 'news_cache_SPI200.json'
  envelope = {'date': today, 'headlines': sample}
  sidecar.write_text(json.dumps(envelope), encoding='utf-8')

  # Manipulate mtime to 30 days old — proves mtime is NOT the TTL check
  old_time = 0.0  # epoch — very old
  os.utime(str(sidecar), (old_time, old_time))

  # _get_yf must NOT be called (cache hit)
  def _fail():
    raise AssertionError('_get_yf must not be called on cache hit')
  monkeypatch.setattr('news_fetcher._get_yf', _fail)

  result = fetch_news('SPI200', '^AXJO')
  assert result == sample


def test_cache_stale_when_json_date_not_today(monkeypatch, tmp_path):
  monkeypatch.chdir(tmp_path)
  stale_date = '2020-01-01'
  today = date.today().isoformat()
  sample_stale = [{'title': 'Old', 'url': '', 'publisher': '', 'pub_date': '', 'title_hash': 'b' * 16}]
  sidecar = tmp_path / 'news_cache_SPI200.json'
  sidecar.write_text(json.dumps({'date': stale_date, 'headlines': sample_stale}), encoding='utf-8')

  fresh_items = [
    {
      'content': {
        'title': 'Fresh headline',
        'pubDate': '2026-05-16T10:00:00Z',
        'provider': {'displayName': 'Reuters'},
        'canonicalUrl': {'url': 'https://example.com/fresh'},
        'clickThroughUrl': None,
      }
    }
  ]
  monkeypatch.setattr('news_fetcher._get_yf', lambda: FakeYF(fresh_items))

  result = fetch_news('SPI200', '^AXJO')
  assert len(result) >= 1
  assert result[0]['title'] == 'Fresh headline'

  # sidecar rewritten with today's date
  rewritten = json.loads(sidecar.read_text())
  assert rewritten['date'] == today


def test_cache_load_envelope_returns_headlines_list(tmp_path):
  today = date.today().isoformat()
  sample = [{'title': 'T', 'url': '', 'publisher': '', 'pub_date': '', 'title_hash': 'c' * 16}]
  sidecar = tmp_path / 'news_cache_SPI200.json'
  sidecar.write_text(json.dumps({'date': today, 'headlines': sample}), encoding='utf-8')
  result = _load_cache(sidecar)
  assert result == sample


def test_cache_miss_writes_envelope_with_date_key(monkeypatch, tmp_path):
  monkeypatch.chdir(tmp_path)
  today = date.today().isoformat()
  items = [
    {
      'content': {
        'title': 'RBA meeting',
        'pubDate': '2026-05-07T10:00:00Z',
        'provider': {'displayName': 'AFR'},
        'canonicalUrl': {'url': 'https://example.com/rba'},
        'clickThroughUrl': None,
      }
    }
  ]
  monkeypatch.setattr('news_fetcher._get_yf', lambda: FakeYF(items))
  fetch_news('SPI200', '^AXJO')
  sidecar = tmp_path / 'news_cache_SPI200.json'
  assert sidecar.exists()
  envelope = json.loads(sidecar.read_text())
  assert set(envelope.keys()) == {'date', 'headlines'}
  assert envelope['date'] == today
  assert isinstance(envelope['headlines'], list)


def test_cache_write_is_atomic(monkeypatch, tmp_path):
  monkeypatch.chdir(tmp_path)
  today = date.today().isoformat()
  original_content = json.dumps({'date': today, 'headlines': [{'title': 'orig', 'url': '', 'publisher': '', 'pub_date': '', 'title_hash': 'd' * 16}]})
  sidecar = tmp_path / 'news_cache_AUDUSD.json'
  sidecar.write_text(original_content, encoding='utf-8')

  # Monkeypatch os.replace to raise after tempfile is written
  real_replace = os.replace
  tmp_files = []

  def _fail_replace(src, dst):
    tmp_files.append(src)
    raise OSError('simulated replace failure')

  monkeypatch.setattr(os, 'replace', _fail_replace)

  data = {'date': today, 'headlines': [{'title': 'new', 'url': '', 'publisher': '', 'pub_date': '', 'title_hash': 'e' * 16}]}
  try:
    _write_cache(sidecar, data)
  except OSError:
    pass

  # Original sidecar must be untouched
  assert sidecar.read_text() == original_content
  # No .tmp file should linger
  for tmp_file in tmp_files:
    assert not Path(tmp_file).exists(), f'.tmp file lingered: {tmp_file}'


def test_cache_corrupt_json_returns_none_and_refetches(monkeypatch, tmp_path):
  monkeypatch.chdir(tmp_path)
  sidecar = tmp_path / 'news_cache_SPI200.json'
  sidecar.write_text('NOT VALID JSON {{{', encoding='utf-8')

  fresh_items = [
    {
      'content': {
        'title': 'After corruption recovery',
        'pubDate': '2026-05-07T10:00:00Z',
        'provider': {'displayName': 'Reuters'},
        'canonicalUrl': {'url': 'https://example.com/fresh'},
        'clickThroughUrl': None,
      }
    }
  ]
  monkeypatch.setattr('news_fetcher._get_yf', lambda: FakeYF(fresh_items))

  result = fetch_news('SPI200', '^AXJO')
  assert result[0]['title'] == 'After corruption recovery'


# =========================================================================
# XSS / SSRF
# =========================================================================

def test_xss_headline_survives_normaliser():
  xss_title = '<script>alert(1)</script>'
  raw = {
    'content': {
      'title': xss_title,
      'pubDate': '2026-05-07T10:00:00Z',
      'provider': {'displayName': 'p'},
      'canonicalUrl': {'url': 'https://x.example.com/'},
      'clickThroughUrl': None,
    }
  }
  result = _normalise_item(raw)
  assert result is not None
  assert result['title'] == xss_title, (
    f"XSS title was mutated at fetch layer: got {result['title']!r}"
  )


def test_no_server_side_url_prefetch():
  source = Path('news_fetcher.py').read_text(encoding='utf-8')
  tree = ast.parse(source)
  bad_calls = []
  for node in ast.walk(tree):
    if isinstance(node, ast.Call):
      # Check for requests.get, requests.post, urllib.request.urlopen, httpx.*
      func = node.func
      if isinstance(func, ast.Attribute):
        if (
          isinstance(func.value, ast.Name)
          and func.value.id in ('requests', 'httpx')
          and func.attr in ('get', 'post', 'request', 'put', 'delete', 'patch')
        ):
          bad_calls.append(ast.unparse(func))
        elif (
          isinstance(func.value, ast.Attribute)
          and func.attr == 'urlopen'
        ):
          bad_calls.append(ast.unparse(func))
  assert not bad_calls, f'Server-side URL prefetch found in news_fetcher.py: {bad_calls}'


def test_news_fetcher_no_forbidden_imports():
  source = Path('news_fetcher.py').read_text(encoding='utf-8')
  tree = ast.parse(source)
  imported = set()
  for node in ast.walk(tree):
    if isinstance(node, ast.Import):
      for alias in node.names:
        imported.add(alias.name.split('.')[0])
    elif isinstance(node, ast.ImportFrom):
      if node.module:
        imported.add(node.module.split('.')[0])
  violations = imported & FORBIDDEN_MODULES_NEWS_FETCHER
  assert not violations, (
    f'news_fetcher.py imports forbidden modules: {violations}'
  )


# =========================================================================
# Network resilience
# =========================================================================

def test_fetch_news_returns_empty_on_retries_exhausted(monkeypatch, tmp_path):
  monkeypatch.chdir(tmp_path)
  import requests.exceptions

  call_count = {'n': 0}

  class _FailTicker:
    @property
    def news(self):
      call_count['n'] += 1
      raise requests.exceptions.ReadTimeout('timeout')

  class _FailYF:
    def Ticker(self, symbol, **kwargs):
      return _FailTicker()

  monkeypatch.setattr('news_fetcher._get_yf', lambda: _FailYF())
  result = fetch_news('SPI200', '^AXJO', retries=3, backoff_s=0.0)
  assert result == []
  assert call_count['n'] == 3


# =========================================================================
# URL fallback chain
# =========================================================================

def test_clickthrough_url_none_falls_back_to_canonical():
  raw = {
    'content': {
      'title': 'Test item',
      'pubDate': '2026-05-07T10:00:00Z',
      'provider': {'displayName': 'AFR'},
      'clickThroughUrl': None,
      'canonicalUrl': {'url': 'https://canonical.example.com/'},
    }
  }
  result = _normalise_item(raw)
  assert result is not None
  assert result['url'] == 'https://canonical.example.com/'


def test_clickthrough_and_canonical_missing_yields_empty_url():
  raw = {
    'content': {
      'title': 'Test item',
      'pubDate': '2026-05-07T10:00:00Z',
      'provider': {'displayName': 'AFR'},
      # neither clickThroughUrl nor canonicalUrl
    }
  }
  result = _normalise_item(raw)
  assert result is not None
  assert result['url'] == ''
