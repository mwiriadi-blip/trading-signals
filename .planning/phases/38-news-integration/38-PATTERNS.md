# Phase 38: News Integration - Pattern Map

**Mapped:** 2026-05-15
**Files analyzed:** 13
**Analogs found:** 12 / 13

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `news_fetcher.py` | I/O adapter | request-response | `data_fetcher.py` | exact |
| `news_filter.py` | pure-math hex | transform | `alert_engine.py` / `system_params.py` | role-match |
| `web/routes/news.py` | route | request-response | `web/routes/healthz.py` + `web/routes/admin/__init__.py` | exact |
| `dashboard_renderer/components/news.py` | component | transform | `dashboard_renderer/components/trace.py` | exact |
| `dashboard_renderer/assets.py` | config | — | self (modify) | exact |
| `system_params.py` | config | — | self (modify) | exact |
| `web/app.py` | config | — | self (modify) | exact |
| `tests/test_signal_engine.py` | test | — | self (modify) | exact |
| `tests/test_news_fetcher.py` | test | — | `tests/test_signal_engine.py` (AST pattern) | role-match |
| `tests/test_news_filter.py` | test | — | `tests/test_signal_engine.py` | role-match |
| `tests/fixtures/news/news_fixture_pre055.json` | fixture | — | hand-crafted | none |
| `tests/fixtures/news/news_fixture_post055.json` | fixture | — | live capture | none |
| `tests/fixtures/news/news_classifier_30.json` | fixture | — | hand-crafted | none |

---

## Pattern Assignments

### `news_fetcher.py` (I/O adapter, request-response)

**Analog:** `data_fetcher.py`

**Module docstring pattern** (data_fetcher.py lines 1-25):
```python
'''News Fetcher — yfinance I/O hex for per-market headline cache.

NEWS-01/NEWS-03 (REQUIREMENTS.md). Owns all yfinance news calls and exposes
one public function: fetch_news.

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. This is the ONE module
allowed to call yfinance.Ticker.news. Must NOT import signal_engine,
sizing_engine, state_manager, notifier, dashboard, or numpy directly.
AST blocklist in tests/test_news_fetcher.py::test_news_fetcher_no_forbidden_imports
enforces this structurally via FORBIDDEN_MODULES_NEWS_FETCHER.
'''
```

**Imports pattern** (data_fetcher.py lines 26-40):
```python
import hashlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime, date
from pathlib import Path
from typing import TypedDict

from system_params import HTTP_TIMEOUT_S

logger = logging.getLogger(__name__)
```

**Lazy yfinance import pattern** (data_fetcher.py lines 70-83):
```python
_yf = None  # memoized yfinance module reference; populated by _get_yf()


def _get_yf():
  '''Lazy-import accessor for the yfinance module (Phase 27 #14).

  Returns the imported `yfinance` module. Memoized — first call pays the
  import cost; subsequent calls are O(1).
  '''
  global _yf
  if _yf is None:
    import yfinance as yf_  # local import — first call only
    _yf = yf_
  return _yf
```

NOTE: `news_fetcher.py` must define its OWN `_get_yf()` — do NOT import from `data_fetcher`. Cross-I/O-peer imports are forbidden.

**Narrow-catch retry pattern** (data_fetcher.py lines 137-238 — abridged):
```python
_RETRY_EXCEPTIONS = (
  requests.exceptions.ReadTimeout,
  requests.exceptions.ConnectionError,
)

def fetch_news(
  market_id: str,
  symbol: str,
  max_items: int = 5,
  retries: int = 3,
  backoff_s: float = 5.0,
) -> list[NewsItem]:
  last_err: Exception | None = None
  yf_mod = _get_yf()
  for attempt in range(1, retries + 1):
    try:
      ticker = yf_mod.Ticker(symbol)
      raw_items = ticker.news or []
      # normalise + deduplicate + slice
      ...
      return items[:max_items]
    except (*_RETRY_EXCEPTIONS, Exception) as e:
      # NARROW CATCH — only transient errors retry
      last_err = e
      logger.warning(
        '[News] %s attempt %d/%d failed: %s: %s',
        market_id, attempt, retries, type(e).__name__, e,
      )
      if attempt < retries:
        time.sleep(backoff_s)
  logger.error('[News] %s: retries exhausted; returning []', market_id)
  return []
```

**Atomic cache write pattern** (mirrors state_manager/io.py lines 118-169):
```python
def _write_cache(path: Path, data: dict) -> None:
  '''Atomic tempfile + os.replace (mirrors state_manager/io.py::_atomic_write_unlocked).'''
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    ) as tmp:
      tmp_path_str = tmp.name
      json.dump(data, tmp, sort_keys=True)
      tmp.flush()
      os.fsync(tmp.fileno())
    os.replace(tmp_path_str, path)
    tmp_path_str = None
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass
```

**Cache hit/miss pattern** (to be authored — no direct analog):
```python
def _cache_path(market_id: str) -> Path:
  return Path(f'news_cache_{market_id}.json')

def _load_cache(path: Path) -> list[dict] | None:
  '''Return cached headlines if file exists and date == today, else None.'''
  try:
    with open(path, encoding='utf-8') as f:
      data = json.load(f)
    if data.get('date') == date.today().isoformat():
      return data.get('headlines', [])
  except (FileNotFoundError, json.JSONDecodeError, OSError):
    pass
  return None
```

---

### `news_filter.py` (pure-math hex, transform)

**Analog:** `system_params.py` (stdlib-only hex pattern), `alert_engine.py` (pure transform module)

**Module docstring + imports** (only re + system_params allowed):
```python
'''news_filter.py — pure-math hex keyword classifier for Phase 38.

Pure stdlib-only module: re + system_params imports only. Eligible for
_HEX_PATHS_STDLIB_ONLY in tests/test_signal_engine.py.

FORBIDDEN: datetime, os, json, yfinance, requests — any non-stdlib import
will fail the AST boundary test (test_forbidden_imports_absent).
'''
import re
from system_params import (
  NEWS_KEYWORDS_SPI200,
  NEWS_KEYWORDS_AUDUSD,
  NEWS_DAMPENER_ALLOWLIST,
)
```

**Pattern compile at module-load** (avoids recompile per call):
```python
_MARKET_KEYWORDS: dict[str, tuple[str, ...]] = {
  'SPI200': NEWS_KEYWORDS_SPI200,
  'AUDUSD': NEWS_KEYWORDS_AUDUSD,
}

def _build_pattern(keywords: tuple[str, ...]) -> re.Pattern:
  parts = [r'\b' + re.escape(kw) + r'\b' for kw in keywords]
  return re.compile('|'.join(parts), re.IGNORECASE)

_PATTERNS: dict[str, re.Pattern] = {
  m: _build_pattern(kws) for m, kws in _MARKET_KEYWORDS.items()
}
_DAMPENER_RE = re.compile(
  '|'.join(re.escape(d) for d in NEWS_DAMPENER_ALLOWLIST), re.IGNORECASE
)
```

**Public API** (single function + convenience wrapper):
```python
def classify_headline(text: str, market_id: str) -> bool:
  pat = _PATTERNS.get(market_id)
  if pat is None:
    return False
  text_lower = text.lower()
  if not _DAMPENER_RE.search(text_lower):
    return bool(pat.search(text_lower))
  scrubbed = _DAMPENER_RE.sub('', text_lower)
  return bool(pat.search(scrubbed))


def has_critical_event(headlines: list[dict], market_id: str) -> bool:
  return any(classify_headline(h.get('title', ''), market_id) for h in headlines)
```

---

### `web/routes/news.py` (route, request-response)

**Analog:** `web/routes/healthz.py` (register pattern) + `web/routes/admin/__init__.py` lines 192-205 (HTMX empty-200 dismiss pattern)

**Register pattern** (healthz.py lines 39-41):
```python
def register(app: FastAPI) -> None:
  '''Register news routes on the given FastAPI instance.'''

  @app.post('/news/{market}/dismiss/{title_hash}')
  def dismiss_headline(
    market: str,
    title_hash: str,
    request: Request,
  ) -> Response:
    ...
```

**Auth dependency pattern** (healthz.py lines 28-36 — local import discipline C-2):
```python
def _get_current_uid(request: Request) -> str:
  from web.dependencies import current_user_id
  return current_user_id(request)
```

**Dismiss route — HTMX empty-200 pattern** (admin/__init__.py lines 192-205):
```python
@router.delete('/invites/{token_hash}')
def admin_revoke_invite(token_hash: str):
  # HTMX swaps this into the <tr> with outerHTML — empty string removes the row.
  return HTMLResponse('', status_code=200)
```

News dismiss mirrors this exactly:
```python
@app.post('/news/{market}/dismiss/{title_hash}')
def dismiss_headline(market: str, title_hash: str, request: Request) -> Response:
  from state_manager import mutate_user_state
  from datetime import date

  uid = _get_current_uid(request)
  # Validate market and title_hash at entry (security — path traversal, injection)
  if not _is_known_market(market):
    raise HTTPException(status_code=404, detail='unknown market')
  if not _is_valid_hash(title_hash):
    raise HTTPException(status_code=422, detail='invalid hash')

  def _apply(state: dict) -> None:
    users = state.setdefault('users', {})
    user = users.setdefault(uid, {})
    today = date.today().isoformat()
    nd = user.get('news_dismissed', {})
    if nd.get('date') != today:
      nd = {'date': today, 'hashes': []}
    if title_hash not in nd['hashes']:
      nd['hashes'].append(title_hash)
    user['news_dismissed'] = nd

  mutate_user_state(uid, _apply)
  # Empty 200 — HTMX removes the row via hx-target + hx-swap="outerHTML"
  return Response(content='', media_type='text/html')
```

**Panel-toggle route** (mirrors dismiss pattern with different mutator):
```python
@app.post('/news/panel-toggle')
def news_panel_toggle(request: Request) -> Response:
  from state_manager import mutate_user_state
  uid = _get_current_uid(request)

  def _apply(state: dict) -> None:
    user = state.setdefault('users', {}).setdefault(uid, {})
    user['news_panel_collapsed'] = not user.get('news_panel_collapsed', False)

  mutate_user_state(uid, _apply)
  return Response(content='', media_type='text/html')
```

---

### `dashboard_renderer/components/news.py` (component, transform)

**Analog:** `dashboard_renderer/components/trace.py`

**Module header pattern** (trace.py lines 1-18):
```python
'''dashboard_renderer.components.news — Phase 38 news panel.'''
import html
import logging

logger = logging.getLogger(__name__)
```

**Collapsible `<details>` pattern** (trace.py lines 256-261):
```python
# trace.py render:
return (
  f'<details class="trace-disclosure" data-instrument="{inst_esc}"{placeholder}>\n'
  '  <summary class="trace-summary">Show calculations</summary>\n'
  + inner
  + '</details>\n'
)

# news.py replication — open_attr is ' open' or '' from per-user state:
def _render_news_panel(
  market_id: str,
  headlines: list[dict],
  has_critical: bool,
  dismissed_hashes: set[str],
  collapsed: bool,
) -> str:
  open_attr = '' if collapsed else ' open'
  mkt_esc = html.escape(market_id, quote=True)
  inner = (
    (_render_news_banner() if has_critical else '')
    + _render_headlines(market_id, headlines, dismissed_hashes)
  )
  return (
    f'<details class="news-panel-disclosure"{open_attr}>\n'
    f'  <summary class="news-panel-summary">Market News</summary>\n'
    + inner
    + '</details>\n'
  )
```

**Row render with HTMX dismiss** (no direct analog — see HTMX template from RESEARCH.md §4):
```python
def _render_headline_row(market_id: str, item: dict) -> str:
  title_hash = html.escape(item['title_hash'], quote=True)
  title = html.escape(item['title'])        # Jinja2 autoescape=True is structural
  url = html.escape(item.get('url', ''), quote=True)
  publisher = html.escape(item.get('publisher', ''))
  mkt_esc = html.escape(market_id, quote=True)
  return (
    f'<tr id="news-row-{title_hash}">\n'
    f'  <td><a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
    f'  <span class="news-publisher">{publisher}</span></td>\n'
    f'  <td><button type="button"'
    f'    hx-post="/news/{mkt_esc}/dismiss/{title_hash}"'
    f'    hx-target="#news-row-{title_hash}"'
    f'    hx-swap="outerHTML">Dismiss</button></td>\n'
    '</tr>\n'
  )
```

**Banner render** (banner copy locked by ROADMAP — D-07):
```python
def _render_news_banner() -> str:
  return (
    '<div class="news-critical-banner">'
    'Possible market-moving news — operator review recommended'
    '</div>\n'
  )
```

---

### `system_params.py` (modify — add NEWS_* constants)

**Analog:** `system_params.py` (self — existing section pattern)

**Section header + tuple constant pattern** (system_params.py lines 50-77, 100-101):
```python
# =========================================================================
# Phase 38 constants — news integration keyword classifier (D-06)
# =========================================================================
# Per-market keyword lists for critical-event banner. Word-boundary regex
# (\b prefix/suffix) applied by news_filter.py (_build_pattern). Operator-
# tunable; do NOT bump STRATEGY_VERSION for keyword-only changes.

NEWS_KEYWORDS_SPI200: tuple[str, ...] = (
  'rba', 'reserve bank', 'rate cut', 'rate hike', 'interest rate',
  'recession', 'gdp', 'inflation', 'cpi', 'stagflation',
  'asx halt', 'trading halt', 'market halt', 'circuit breaker',
  'crash', 'sell-off', 'rout', 'collapse', 'plunge',
  'fed', 'federal reserve', 'ecb', 'bank of japan',
  'tariff', 'trade war', 'sanctions', 'pandemic', 'lockdown',
)

NEWS_KEYWORDS_AUDUSD: tuple[str, ...] = (
  'rba', 'reserve bank', 'rate cut', 'rate hike', 'interest rate',
  'aud', 'aussie dollar', 'australian dollar',
  'china gdp', 'iron ore', 'commodity', 'terms of trade',
  'fed', 'federal reserve', 'fomc', 'us cpi', 'us gdp',
  'dollar', 'dxy', 'greenback',
  'recession', 'stagflation', 'tariff', 'trade war', 'sanctions',
  'pandemic', 'lockdown', 'geopolitical',
)

NEWS_DAMPENER_ALLOWLIST: tuple[str, ...] = (
  'first-rate', 'second-rate', 'first rate', 'second rate',
  'flat-rate', 'flat rate', 'pro-rate', 'pro rate',
  'interest in', 'rate your', 'interest and',
)
```

Constraint: `system_params.py` is in `FORBIDDEN_MODULES_STDLIB_ONLY`. Only `re`, `decimal`, `typing` imports allowed. `tuple[str, ...]` uses stdlib typing — valid.

---

### `web/app.py` (modify — register news routes)

**Analog:** `web/app.py` itself (lines 181-203 — existing register pattern)

**Registration pattern** (web/app.py lines 181-203):
```python
# Existing pattern:
healthz_route.register(application)
markets_route.register(application)
invite_route.register(application)

# Add for Phase 38 — at top of file, with other route imports:
from web.routes import news as news_route

# In create_app(), alongside other register() calls:
news_route.register(application)
```

---

### `tests/test_signal_engine.py` (modify — extend `_HEX_PATHS_STDLIB_ONLY`)

**Analog:** `tests/test_signal_engine.py` itself (lines 619-624)

**Current pattern** (lines 619-624):
```python
_HEX_PATHS_ALL = [SIGNAL_ENGINE_PATH, *SIZING_ENGINE_PKG_FILES, SYSTEM_PARAMS_PATH,
                  PNL_ENGINE_PATH, ALERT_ENGINE_PATH,
                  BACKTEST_SIMULATOR_PATH, BACKTEST_METRICS_PATH]
_HEX_PATHS_STDLIB_ONLY = [*SIZING_ENGINE_PKG_FILES, SYSTEM_PARAMS_PATH, PNL_ENGINE_PATH,
                           ALERT_ENGINE_PATH]
```

**Phase 38 addition** — add path constant near existing path constants, then extend list:
```python
# Add near existing path constants (e.g., after ALERT_ENGINE_PATH = ...):
NEWS_FILTER_PATH = Path('news_filter.py')

# Extend _HEX_PATHS_STDLIB_ONLY:
_HEX_PATHS_STDLIB_ONLY = [*SIZING_ENGINE_PKG_FILES, SYSTEM_PARAMS_PATH, PNL_ENGINE_PATH,
                           ALERT_ENGINE_PATH, NEWS_FILTER_PATH]
```

Also add `FORBIDDEN_MODULES_NEWS_FETCHER` near the existing `FORBIDDEN_MODULES_DATA_FETCHER` (lines 537-546):
```python
NEWS_FETCHER_PATH = Path('news_fetcher.py')
FORBIDDEN_MODULES_NEWS_FETCHER = frozenset({
  'signal_engine', 'sizing_engine', 'state_manager', 'notifier', 'dashboard', 'main',
  'numpy',
  'schedule', 'dotenv',
  'pytz',
})
```

---

### `tests/test_news_fetcher.py` (create)

**Analog:** `tests/test_signal_engine.py` (AST import test pattern, lines 490-546)

**AST import test pattern** (test_signal_engine.py — abridged structure):
```python
import ast
from pathlib import Path

def test_news_fetcher_no_forbidden_imports():
  src = Path('news_fetcher.py').read_text(encoding='utf-8')
  tree = ast.parse(src)
  found = set()
  for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
      for alias in getattr(node, 'names', []):
        root = alias.name.split('.')[0]
        if root in FORBIDDEN_MODULES_NEWS_FETCHER:
          found.add(root)
      if isinstance(node, ast.ImportFrom) and node.module:
        root = node.module.split('.')[0]
        if root in FORBIDDEN_MODULES_NEWS_FETCHER:
          found.add(root)
  assert not found, f'news_fetcher.py imports forbidden modules: {sorted(found)}'
```

**Cache + normaliser tests pattern** (pytest fixture + monkeypatch):
```python
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def post055_raw():
  import json
  return json.loads(Path('tests/fixtures/news/news_fixture_post055.json').read_text())

def test_normalise_post055_shape(post055_raw):
  from news_fetcher import _normalise_item
  for raw in post055_raw:
    item = _normalise_item(raw)
    assert item is not None
    assert 'title' in item and 'url' in item and 'title_hash' in item

def test_cache_hit_skips_fetch(tmp_path, monkeypatch):
  from news_fetcher import fetch_news
  monkeypatch.chdir(tmp_path)
  # Pre-write cache file
  cache = tmp_path / 'news_cache_SPI200.json'
  from datetime import date
  cache.write_text(json.dumps({
    'date': date.today().isoformat(),
    'headlines': [{'title': 'cached', 'url': '', 'publisher': '', 'pub_date': '', 'title_hash': 'abc123'}],
  }))
  # yfinance should NOT be called
  called = []
  monkeypatch.setattr('news_fetcher._get_yf', lambda: (_ for _ in ()).throw(AssertionError('yf called on cache hit')))
  result = fetch_news('SPI200', '^AXJO')
  assert result[0]['title'] == 'cached'
```

---

### `tests/test_news_filter.py` (create)

**Analog:** `tests/test_signal_engine.py` precision/recall gate pattern

**Classifier precision/recall gate**:
```python
import json
from news_filter import classify_headline, has_critical_event

def test_classifier_precision_recall():
  with open('tests/fixtures/news/news_classifier_30.json') as f:
    items = json.load(f)
  tp = fp = fn = 0
  for item in items:
    pred = classify_headline(item['title'], item['market'])
    actual = item['label']
    if pred and actual: tp += 1
    elif pred and not actual: fp += 1
    elif not pred and actual: fn += 1
  precision = tp / (tp + fp) if (tp + fp) else 1.0
  recall = tp / (tp + fn) if (tp + fn) else 0.0
  assert precision >= 0.7, f'precision {precision:.2f} < 0.7'
  assert recall >= 0.9, f'recall {recall:.2f} < 0.9'

def test_dampener_suppresses_false_positive():
  assert not classify_headline('first-rate service from ASX', 'SPI200')

def test_unknown_market_returns_false():
  assert not classify_headline('RBA cuts rates', 'UNKNOWN_MKT')
```

---

### `dashboard_renderer/assets.py` (modify — add news CSS)

**Analog:** `dashboard_renderer/assets.py` (existing trace CSS pattern)

**Trace CSS pattern** (assets.py — find existing `.trace-disclosure` CSS and mirror):
```python
# Add after existing trace-related CSS entries:
# .news-panel-disclosure / .news-panel-summary — mirrors trace panel styles
# .news-critical-banner — amber/warning colour for critical-event
# .news-publisher — muted colour, small text
```

---

## Shared Patterns

### mutate_user_state (state write)
**Source:** `state_manager/__init__.py` lines 385-411
**Apply to:** `web/routes/news.py` dismiss route and panel-toggle route

```python
def mutate_user_state(
  uid: str,
  mutator: Callable[[dict], None],
  path: Path = Path(STATE_FILE),
) -> dict:
  lock_dir = Path('state/users')
  lock_dir.mkdir(parents=True, exist_ok=True)
  lock_path = lock_dir / f'{uid}.lock'
  with open(lock_path, 'a+') as lock_file:
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    try:
      return mutate_state(mutator, path=path)
    finally:
      fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
```

CRITICAL: NEVER call `save_state()` inside a `mutate_user_state` callback — flock deadlock.

### register(app) route pattern
**Source:** `web/routes/healthz.py` lines 39-41
**Apply to:** `web/routes/news.py`

```python
def register(app: FastAPI) -> None:
  @app.post('/news/{market}/dismiss/{title_hash}')
  def route_fn(...):
    ...
```

### Local import discipline (C-2)
**Source:** `web/routes/healthz.py` lines 35-36, 49-50
**Apply to:** `web/routes/news.py` for all state_manager and auth imports

```python
# All state_manager, auth_store imports inside the route function body:
def dismiss_headline(...):
  from state_manager import mutate_user_state  # local import — C-2
  ...
```

### HTMX empty-200 row-removal
**Source:** `web/routes/admin/__init__.py` lines 204-205
**Apply to:** `web/routes/news.py` dismiss route return

```python
return HTMLResponse('', status_code=200)
# or equivalently:
return Response(content='', media_type='text/html')
```

### Atomic file write
**Source:** `state_manager/io.py` lines 118-169 (`_atomic_write_unlocked`)
**Apply to:** `news_fetcher.py::_write_cache`

Pattern: `tempfile.NamedTemporaryFile(dir=parent, delete=False)` → `json.dump` → `flush` → `fsync` → `os.replace` → cleanup in `finally`.

### html.escape for all user-controlled strings
**Source:** `dashboard_renderer/components/trace.py` line 242, signals.py line 4
**Apply to:** `dashboard_renderer/components/news.py` — all title, url, publisher, market_id values

```python
import html
title = html.escape(item['title'])
url = html.escape(item.get('url', ''), quote=True)
```

Note: `autoescape=True` is structural in the Jinja2 setup, but the news panel is assembled as Python string concatenation (not a Jinja2 template), so `html.escape()` must be called explicitly.

### `rel="noopener noreferrer"` on outbound links
**Source:** CONTEXT.md §Code Context
**Apply to:** `dashboard_renderer/components/news.py::_render_headline_row`

```python
f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `tests/fixtures/news/news_fixture_pre055.json` | fixture | — | Hand-crafted; no existing pre-0.2.55 yfinance fixture in codebase |
| `tests/fixtures/news/news_fixture_post055.json` | fixture | — | Live-capture; no existing yfinance news fixture in codebase |
| `tests/fixtures/news/news_classifier_30.json` | fixture | — | Labelled precision/recall fixture; no existing classifier fixture |

Use RESEARCH.md §1 (yfinance schema findings) and §6 (keyword classifier) for these.

---

## Metadata

**Analog search scope:** repo root, `data_fetcher.py`, `state_manager/`, `web/routes/`, `dashboard_renderer/components/`, `tests/test_signal_engine.py`, `system_params.py`, `web/app.py`
**Files scanned:** 10
**Pattern extraction date:** 2026-05-15
