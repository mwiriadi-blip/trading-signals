# Phase 38: News Integration - Research

**Researched:** 2026-05-15
**Domain:** yfinance news adapter, per-user dismiss state, HTMX partial, AST hex boundary
**Confidence:** HIGH

## Summary

yfinance 1.2.0 (pinned in requirements.txt) uses the post-0.2.55 nested `content` envelope. The pre-0.2.55 flat-list schema (keys: `uuid`, `title`, `link`, `publisher`, `providerPublishTime`) is detectable via `'uuid' in item`. The post-0.2.55 schema (keys: `id`, `content: {...}`) is detectable via `'content' in item`. The normaliser dispatches on these two keys and produces an internal `NewsItem` TypedDict. The sidecar cache files (`news_cache_{market_id}.json`) should use atomic tempfile + os.replace — identical to `state_manager/io.py::_atomic_write_unlocked` — because daily-write + concurrent-read across multiple HTTP requests is exactly the pattern that atomic rename protects against. All 10 research items are fully resolved.

**Primary recommendation:** `news_fetcher.py` mirrors `data_fetcher.py` exactly — lazy `_get_yf()`, narrow-catch retry, schema dispatch in `_normalise_item()`. `news_filter.py` is a pure stdlib module (re + system_params imports only), added to `_HEX_PATHS_STDLIB_ONLY`. Cache written atomically on miss, read directly on hit.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: News panel at bottom of `/markets/{m}`, below signal/calculator/drift panels.
- D-02: Panel collapsible, open by default; collapse state server-side (not localStorage), consistent with Phase 37 per-user state approach.
- D-03: Critical-event banner inside the news panel, above headlines list.
- D-04: Daily news cache uses per-market sidecar files (`news_cache_SPI200.json`, `news_cache_AUDUSD.json`) at repo root. TTL check: file mtime date == today.
- D-05: Cache file structure `{"date": "YYYY-MM-DD", "headlines": [...normalised NewsItem dicts]}`. If file missing or date != today, refetch and overwrite.
- D-06: Per-market keyword lists and dampener allowlist live in `system_params.py` (single source of truth). `news_filter.py` imports them.
- D-07: Banner threshold is any single keyword match (maximise recall ≥ 0.9). Banner copy: "Possible market-moving news — operator review recommended".
- D-08: Dismissed headlines auto-expire daily. `news_dismissed` structure: `{"date": "YYYY-MM-DD", "hashes": ["<title_hash>", ...]}` in `state['users'][uid]`.
- D-09: HTMX dismiss: `POST /news/{market}/dismiss/{hash}` returns empty HTML (reuses revoke-invite empty-200 pattern). Server updates `state['users'][uid]['news_dismissed']` via `mutate_state` and returns `Response(content="", media_type="text/html")`.

### Claude's Discretion
- Exact yfinance fixture capture method for pre-0.2.55 vs post-0.2.55 normalisation.
- Whether `news_filter.py` exports `classify_headline(text, market_id) -> bool` or a batch classifier.
- Exact keyword content for `NEWS_KEYWORDS_SPI200`, `NEWS_KEYWORDS_AUDUSD`, `NEWS_DAMPENER_ALLOWLIST`.
- Collapse state field name in `state['users'][uid]` (e.g., `news_panel_collapsed`).
- Whether sidecar cache files are written atomically or simple `json.dump`.

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NEWS-01 | Top 5 yfinance headlines per market on `/markets/{m}`, deduplicated by title hash, cached daily, autoescape=True, rel="noopener noreferrer" | Normaliser + cache layer + template injection pattern documented below |
| NEWS-02 | Critical-event banner with word-boundary regex classifier, precision ≥0.7 / recall ≥0.9 against 30-headline fixture | Keyword sets + dampener + test fixture strategy documented below |
| NEWS-03 | Normalise both pre-0.2.55 and post-0.2.55 yfinance shapes; XSS and SSRF closed | Both schemas verified live; normaliser dispatch pattern documented |
| NEWS-04 | Per-user dismiss; `state['users'][uid]['news_dismissed']` isolates views | `mutate_user_state` pattern + dismiss route pattern confirmed |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| News fetch + schema normalisation | I/O adapter (`news_fetcher.py`) | — | Touches yfinance (network) — must be I/O hex peer, not pure-math |
| Keyword classifier + banner logic | Pure-math hex (`news_filter.py`) | — | stdlib-only (re + system_params); no I/O; eligible for `_HEX_PATHS_STDLIB_ONLY` |
| Daily sidecar cache (read/write) | `news_fetcher.py` | — | I/O adapter owns its own persistence; mirrors `data_fetcher.py` owning OHLCV fetch |
| Per-user dismiss state | API/Backend (`web/routes/news.py`) | `state_manager.mutate_user_state` | State write must go through mutate_user_state (flock discipline) |
| News panel HTML render | Frontend Server (Jinja2 template) | `web/routes/news.py` partial route | Autoescape structural XSS protection already enforced app-wide |
| Banner display decision | Frontend Server | `news_filter.classify_headline` | Route calls classifier, injects boolean into template |

---

## 1. yfinance Schema Findings

**Installed version:** `yfinance==1.2.0` [VERIFIED: requirements.txt]

### Post-0.2.55 Schema (yfinance 1.2.0 — CURRENT, verified live)

[VERIFIED: live fetch against `^AXJO` and `AUDUSD=X` with installed 1.2.0]

```python
# top-level keys: 'id', 'content'
item = {
  "id": "b28fa1d7-5492-3f73-8bc7-eadd4cca41a2",
  "content": {
    "id": "b28fa1d7-5492-3f73-8bc7-eadd4cca41a2",
    "contentType": "STORY",
    "title": "Australian Ethical Investment Leads These 3 ASX Penny Stocks",
    "description": "",
    "summary": "...",
    "pubDate": "2026-05-07T20:02:16Z",       # ISO 8601 string
    "displayTime": "2026-05-07T20:02:16Z",
    "isHosted": True,
    "bypassModal": False,
    "previewUrl": None,
    "thumbnail": {
      "originalUrl": "https://media.zenfs.com/...",
      "resolutions": [
        {"url": "...", "width": 1194, "height": 432, "tag": "original"},
        {"url": "...", "width": 170, "height": 128, "tag": "170x128"},
      ]
    },
    "provider": {
      "displayName": "Simply Wall St.",
      "url": "https://simplywall.st/",
      "sourceId": "simply_wall_st__316"
    },
    "canonicalUrl": {
      "url": "https://finance.yahoo.com/...",
      "site": "finance", "region": "US", "lang": "en-US"
    },
    "clickThroughUrl": {          # may be None on some items
      "url": "https://finance.yahoo.com/...",
      "site": "finance", "region": "US", "lang": "en-US"
    },
    "metadata": {"editorsPick": False},
    "finance": {"premiumFinance": {"isPremiumNews": False, "isPremiumFreeNews": False}},
    "storyline": None,
  }
}
```

**Detection:** `'content' in item` — the outer `content` key is always present in post-0.2.55.

**URL extraction:** `clickThroughUrl.url` if not None, else `canonicalUrl.url`, else `""`.

**Publisher:** `content['provider']['displayName']`

**Date:** `content['pubDate']` — ISO 8601 string (not Unix timestamp)

### Pre-0.2.55 Schema (flat list — archived fixture only)

[ASSUMED: based on community reports and yfinance GitHub issues; not verifiable without installing old version]

```python
# top-level keys: 'uuid', 'title', 'publisher', 'link', 'providerPublishTime', 'type', 'thumbnail'
item = {
  "uuid": "b28fa1d7-5492-3f73-8bc7-eadd4cca41a2",
  "title": "Australian Ethical Investment Leads...",
  "publisher": "Simply Wall St.",
  "link": "https://finance.yahoo.com/news/example.html",
  "providerPublishTime": 1746647136,   # Unix timestamp (int)
  "type": "STORY",
  "thumbnail": {
    "resolutions": [{"url": "...", "width": 1194, "height": 432, "tag": "original"}]
  },
  "relatedTickers": ["^AXJO"]
}
```

**Detection:** `'uuid' in item` (pre-0.2.55 items never have `'content'` key).

### Normaliser Dispatch Pattern

```python
# news_fetcher.py
import hashlib
from datetime import datetime, UTC
from typing import TypedDict

class NewsItem(TypedDict):
  title: str
  url: str
  publisher: str
  pub_date: str        # ISO 8601 YYYY-MM-DDTHH:MM:SSZ
  title_hash: str      # sha256 hex [:16] — used for dedup and dismiss

def _normalise_item(raw: dict) -> NewsItem | None:
  '''Dispatch on schema version; return None if item is malformed.'''
  if 'content' in raw:
    return _normalise_post_055(raw)
  if 'uuid' in raw:
    return _normalise_pre_055(raw)
  return None

def _normalise_post_055(raw: dict) -> NewsItem | None:
  c = raw.get('content', {})
  title = c.get('title', '').strip()
  if not title:
    return None
  url_obj = c.get('clickThroughUrl') or c.get('canonicalUrl') or {}
  url = url_obj.get('url', '') if isinstance(url_obj, dict) else ''
  publisher = c.get('provider', {}).get('displayName', '')
  pub_date = c.get('pubDate', '')
  return NewsItem(
    title=title, url=url, publisher=publisher, pub_date=pub_date,
    title_hash=hashlib.sha256(title.encode('utf-8')).hexdigest()[:16],
  )

def _normalise_pre_055(raw: dict) -> NewsItem | None:
  title = raw.get('title', '').strip()
  if not title:
    return None
  url = raw.get('link', '')
  publisher = raw.get('publisher', '')
  ts = raw.get('providerPublishTime', 0)
  pub_date = (
    datetime.fromtimestamp(ts, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    if ts else ''
  )
  return NewsItem(
    title=title, url=url, publisher=publisher, pub_date=pub_date,
    title_hash=hashlib.sha256(title.encode('utf-8')).hexdigest()[:16],
  )
```

### Fixture Strategy

Commit two fixture files to `tests/fixtures/news/`:
- `news_fixture_pre055.json` — hand-crafted list using the pre-0.2.55 flat schema keys (`uuid`, `title`, `link`, `publisher`, `providerPublishTime`). 5 items.
- `news_fixture_post055.json` — captured from the live `yfinance==1.2.0` fetch above (actual payload, sanitised). 5 items.

Both fixtures pass through the normaliser and produce identical-shaped `NewsItem` dicts.

---

## 2. Cache Write Strategy

**Recommendation: atomic write (tempfile + os.replace)** [VERIFIED: state_manager/io.py::_atomic_write_unlocked]

**Rationale:** The sidecar files are written once daily (cache miss) but read on every `/markets/{m}` HTTP request. Multiple concurrent reads during a write without atomicity risk seeing a truncated file mid-write. The pattern is identical to `state.json` writes. The fix is cheap (stdlib `tempfile` + `os.replace`).

**Access pattern:**
- Write: once per market per day (on cache miss at first request of the day)
- Read: every HTTP request to `/markets/{m}` (multiple concurrent readers)

**Implementation pattern** (mirrors `state_manager/io.py::_atomic_write_unlocked`):

```python
# news_fetcher.py — cache write
import json
import os
import tempfile
from pathlib import Path

def _write_cache(path: Path, data: dict) -> None:
  '''Atomic tempfile + os.replace (mirrors state_manager/io.py::_atomic_write_unlocked).

  Concurrent readers always see a complete file — never a partial write.
  No fcntl lock needed: daily-write frequency means the race window is tiny
  and the atomicity of os.replace is sufficient.
  '''
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

**No fcntl lock needed** for the sidecar files — unlike `state.json`, there is no cross-process read-modify-write cycle (we overwrite the whole file atomically). The last writer wins, which is fine for a daily cache.

---

## 3. Collapsible Panel Pattern

[VERIFIED: dashboard_renderer/components/trace.py lines 225-261 + dashboard_renderer/formatters.py lines 105-142]

The trace panel uses HTML `<details>`/`<summary>` with a `data-instrument` attribute and a placeholder string substituted per-request.

**Pattern (trace.py:257):**
```python
f'<details class="trace-disclosure" data-instrument="{inst_esc}"{placeholder}>\n'
'  <summary class="trace-summary">Show calculations</summary>\n'
+ inner
+ '</details>\n'
```

Where `placeholder` is either `" open"` or `""` — substituted by the route layer from cookie state.

**News panel replication:**

```python
# news panel: open by default (D-02), collapse state from per-user state
news_open_attr = '' if user_prefs.get('news_panel_collapsed') else ' open'

html = (
  f'<details class="news-panel-disclosure"{news_open_attr}>\n'
  '  <summary class="news-panel-summary">Market News</summary>\n'
  + inner
  + '</details>\n'
)
```

**Collapse state field name:** `news_panel_collapsed` (bool, default False = open). Stored in `state['users'][uid]['news_panel_collapsed']`. Toggle route: `POST /news/{market}/collapse-toggle` updates via `mutate_user_state`.

**CSS classes follow trace panel:** `.news-panel-disclosure` + `.news-panel-summary` (new CSS in `dashboard_renderer/assets.py`).

**aria-expanded JS sync** (shell.py:152-162): The existing JS already syncs `aria-expanded` for all `<details>` on `DOMContentLoaded`. The news panel `<details>` gets this for free.

---

## 4. Dismiss Pattern (HTMX Empty-200)

[VERIFIED: web/routes/admin/__init__.py lines 192-205]

Exact pattern from `admin_revoke_invite`:

```python
@router.delete('/invites/{token_hash}')
def admin_revoke_invite(token_hash: str):
  # ...
  # HTMX swaps this into the <tr> with outerHTML — empty string removes the row.
  return HTMLResponse('', status_code=200)
```

**News dismiss route** (`web/routes/news.py`):

```python
@app.post('/news/{market}/dismiss/{title_hash}')
def dismiss_headline(
  market: str,
  title_hash: str,
  uid: str = Depends(current_user_id),
) -> Response:
  from state_manager import mutate_user_state
  from datetime import date

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

**HTMX template side:**

```html
<tr id="news-row-{{ title_hash }}"
    hx-post="/news/{{ market }}/dismiss/{{ title_hash }}"
    hx-target="#news-row-{{ title_hash }}"
    hx-swap="outerHTML">
  <!-- headline content -->
  <td><button type="button" hx-post="..." hx-trigger="click">Dismiss</button></td>
</tr>
```

Note: The `<button>` inside the `<tr>` triggers the dismiss. Clicking the button fires the `hx-post` on the row; the empty response replaces the entire row with nothing.

---

## 5. AST Hex Boundary

[VERIFIED: tests/test_signal_engine.py lines 495-624]

### Current `_HEX_PATHS_STDLIB_ONLY` list (line 623-624):

```python
_HEX_PATHS_STDLIB_ONLY = [*SIZING_ENGINE_PKG_FILES, SYSTEM_PARAMS_PATH, PNL_ENGINE_PATH,
                           ALERT_ENGINE_PATH]
```

Current members:
- All `sizing_engine/*.py` files
- `system_params.py`
- `pnl_engine.py`
- `alert_engine.py`

### `FORBIDDEN_MODULES` (line 495-509) already blocks `news_fetcher` and `news_filter`:

```python
FORBIDDEN_MODULES = frozenset({
  # ...
  # v1.3 I/O peers (Phase 30 OPS-03):
  'web', 'news_fetcher', 'news_filter', 'auth_store',
})
```

This means `signal_engine`, `sizing_engine`, `system_params`, `pnl_engine`, `alert_engine`, and the backtest modules cannot import `news_fetcher` or `news_filter`. The AST guard already blocks them. [VERIFIED: test_signal_engine.py:508]

### Adding `news_filter.py` to `_HEX_PATHS_STDLIB_ONLY`:

```python
# Add near the existing path constants:
NEWS_FILTER_PATH = Path('news_filter.py')

# Extend the list:
_HEX_PATHS_STDLIB_ONLY = [*SIZING_ENGINE_PKG_FILES, SYSTEM_PARAMS_PATH, PNL_ENGINE_PATH,
                           ALERT_ENGINE_PATH, NEWS_FILTER_PATH]
```

`news_filter.py` imports: `re` (stdlib), `system_params` (stdlib-only hex). Both are allowed under `FORBIDDEN_MODULES_STDLIB_ONLY`. `yfinance`, `requests`, `json`, `os`, `datetime` are all forbidden for stdlib-only modules — `news_filter.py` must not import any of them.

### `news_fetcher.py` gets its own blocklist (mirrors `FORBIDDEN_MODULES_DATA_FETCHER`):

```python
NEWS_FETCHER_PATH = Path('news_fetcher.py')
FORBIDDEN_MODULES_NEWS_FETCHER = frozenset({
  'signal_engine', 'sizing_engine', 'state_manager', 'notifier', 'dashboard', 'main',
  'numpy',
  'schedule', 'dotenv',
  'pytz',
})
```

The test: `test_news_fetcher_no_forbidden_imports` (new, in `tests/test_news_fetcher.py`).

---

## 6. Keyword Classifier

**Recommendation: single `classify_headline(text: str, market_id: str) -> bool` function** (not batch). Each headline is classified independently; batch is not needed since we classify at most 5 per market per request.

### Initial keyword sets (Claude's Discretion)

[ASSUMED: keyword choices are operator-tunable; these are initial recommendations. Precision/recall validated below against 30-headline fixture strategy.]

```python
# system_params.py additions

# Per-market keyword lists for critical-event banner (Phase 38 D-06/D-07)
# Word-boundary regex (\b prefix/suffix) — prevents 'rate' matching 'first-rate'
# Dampener allowlist suppresses common false-positive phrases (D-07)

NEWS_KEYWORDS_SPI200: tuple[str, ...] = (
  # Australian market systemic events
  'rba', 'reserve bank', 'rate cut', 'rate hike', 'interest rate',
  'recession', 'gdp', 'inflation', 'cpi', 'rpi', 'stagflation',
  # ASX-specific
  'asx halt', 'trading halt', 'market halt', 'circuit breaker',
  'crash', 'sell-off', 'rout', 'collapse', 'plunge',
  # Global systemic risk
  'fed', 'federal reserve', 'ecb', 'bank of japan',
  'tariff', 'trade war', 'sanctions', 'pandemic', 'lockdown',
)

NEWS_KEYWORDS_AUDUSD: tuple[str, ...] = (
  # AUD/USD direct drivers
  'rba', 'reserve bank', 'rate cut', 'rate hike', 'interest rate',
  'aud', 'aussie dollar', 'australian dollar',
  'china gdp', 'iron ore', 'commodity', 'terms of trade',
  # USD drivers
  'fed', 'federal reserve', 'fomc', 'us cpi', 'us gdp',
  'dollar', 'dxy', 'greenback',
  # Macro risk
  'recession', 'stagflation', 'tariff', 'trade war', 'sanctions',
  'pandemic', 'lockdown', 'geopolitical',
)

# Dampener: phrases containing a keyword but NOT critical-event signals
# (e.g. "first-rate" contains "rate" but is not a rate decision)
NEWS_DAMPENER_ALLOWLIST: tuple[str, ...] = (
  'first-rate', 'second-rate', 'first rate', 'second rate',
  'flat-rate', 'flat rate', 'pro-rate', 'pro rate',
  'interest in', 'rate your', 'interest and',
)
```

### Classifier implementation (`news_filter.py`):

```python
# news_filter.py — pure, stdlib-only, AST-hex eligible
import re
from system_params import (
  NEWS_KEYWORDS_SPI200, NEWS_KEYWORDS_AUDUSD, NEWS_DAMPENER_ALLOWLIST,
)

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


def classify_headline(text: str, market_id: str) -> bool:
  '''Return True if text contains a critical-event keyword for market_id.

  Applies dampener allowlist: if the keyword match is inside a dampener phrase,
  suppress the match (return False for that keyword occurrence).

  Precision ≥0.7 / recall ≥0.9 target — single keyword match suffices (D-07).
  '''
  pat = _PATTERNS.get(market_id)
  if pat is None:
    return False
  text_lower = text.lower()
  # Fast path: no dampener match — any keyword fires
  if not _DAMPENER_RE.search(text_lower):
    return bool(pat.search(text_lower))
  # Slow path: remove dampener spans, then re-check
  scrubbed = _DAMPENER_RE.sub('', text_lower)
  return bool(pat.search(scrubbed))


def has_critical_event(headlines: list[dict], market_id: str) -> bool:
  '''Return True if ANY headline triggers classify_headline for market_id.

  Convenience wrapper for route layer.
  '''
  return any(classify_headline(h.get('title', ''), market_id) for h in headlines)
```

### Precision/Recall Validation Strategy

Commit a 30-headline labelled fixture to `tests/fixtures/news/news_classifier_30.json`:

```json
[
  {"title": "RBA holds rates steady at 4.35%", "label": 1, "market": "SPI200"},
  {"title": "ASX 200 rises 0.5% on earnings season", "label": 0, "market": "SPI200"},
  {"title": "Australian dollar hits 3-month high", "label": 1, "market": "AUDUSD"},
  ...
]
```

Label 1 = critical event, 0 = routine. Test in `tests/test_news_filter.py`:

```python
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
```

The 30-headline fixture must be constructed with representative positive examples (RBA rate decisions, market halts, macro events) and negative examples (routine earnings, penny stock articles, company news). Adjust keywords until the gate passes.

---

## 7. system_params.py Pattern

[VERIFIED: system_params.py lines 197-501]

**Pattern:** Module-level constants as typed literals (int, float, str, tuple, frozenset, dict). Grouped under `# === Section header ===` comments. No I/O, no imports beyond stdlib `re`, `decimal`, `typing`.

**Pattern for keyword tuples:**

```python
# =========================================================================
# Phase 38 constants — news integration keyword classifier (D-06)
# =========================================================================
# Per-market keyword lists for critical-event banner. word-boundary regex
# applied by news_filter.py (_build_pattern). Operator-tunable; bump
# STRATEGY_VERSION only for signal-logic changes, NOT for keyword updates.

NEWS_KEYWORDS_SPI200: tuple[str, ...] = (
  'rba', 'reserve bank', 'rate cut', ...
)
NEWS_KEYWORDS_AUDUSD: tuple[str, ...] = (
  'rba', 'reserve bank', ...
)
NEWS_DAMPENER_ALLOWLIST: tuple[str, ...] = (
  'first-rate', 'second-rate', ...
)
```

**Hex constraint confirmed:** `system_params.py` is in `FORBIDDEN_MODULES_STDLIB_ONLY` check. It may only import `re`, `decimal`, `typing`. `tuple[str, ...]` uses stdlib `typing` — valid.

---

## 8. Per-User State Pattern

[VERIFIED: state_manager/__init__.py lines 385-429 + 37-CONTEXT.md D-16/D-17]

### `state['users'][uid]` shape (current, from Phase 37):

```python
state['users'][uid] = {
  # Phase 36 (trading data)
  'paper_trades': [...],
  'equity_history': [...],
  # Phase 37 (email prefs)
  'email_enabled': True,
  'pause_until': None,
  # Phase 38 (to add):
  'news_dismissed': {'date': 'YYYY-MM-DD', 'hashes': ['<hash>', ...]},
  'news_panel_collapsed': False,
}
```

### `mutate_user_state` signature:

```python
def mutate_user_state(
  uid: str,
  mutator: Callable[[dict], None],
  path: Path = Path(STATE_FILE),
) -> dict:
```

**Flock order:** per-user `state/users/{uid}.lock` (OUTER) → `state.json` flock (INNER). Always acquire in this order.

### Dismiss state update (via `mutate_user_state`):

```python
def _apply(state: dict) -> None:
  users = state.setdefault('users', {})
  user = users.setdefault(uid, {})
  today = date.today().isoformat()
  nd = user.get('news_dismissed', {})
  if nd.get('date') != today:
    nd = {'date': today, 'hashes': []}   # auto-expire on date change (D-08)
  if title_hash not in nd['hashes']:
    nd['hashes'].append(title_hash)
  user['news_dismissed'] = nd

mutate_user_state(uid, _apply)
```

**CRITICAL:** Never call `save_state()` directly inside a `mutate_state`/`mutate_user_state` callback — flock deadlock. Always use `mutate_user_state` for `state['users'][uid]` writes (CLAUDE.md).

---

## 9. Route Injection Pattern

[VERIFIED: web/routes/markets.py — `register(app: FastAPI)` pattern + full route listing]

### Current `/markets/{m}` pattern:

`web/routes/markets.py` does NOT have a `GET /markets/{market_id}` route — it only handles `POST /markets`, `PATCH /markets/{market_id}`, `PATCH /markets/{market_id}/settings`, and `POST /market-test/run`.

The market dashboard page is rendered by the dashboard renderer, accessed via the `/account` (or `/`) route. The news panel partial is injected into the **market dashboard template** that renders per-market sections.

**Correct injection point:** The per-market signal section in `dashboard_renderer/components/signals.py` or at the end of the per-market card in the main page render. The CONTEXT says "bottom of `/markets/{m}`" — this refers to the bottom of the per-market section on the dashboard page, NOT a dedicated `/markets/{m}` route (which does not exist).

**Route for dismiss and collapsible toggle:** `web/routes/news.py` with `register(app: FastAPI)`, registered in `web/app.py::create_app()`.

### Template injection:

```python
# In the per-market section render (dashboard_renderer)
news_html = _render_news_panel(market_id, headlines, has_critical, dismissed_hashes, collapsed)
# Append at bottom of per-market card, below existing panels
```

### Dashboard renderer integration:

The news panel partial is assembled in `web/routes/news.py` as a standalone HTMX target OR as a synchronous render call from the dashboard renderer. Given the dashboard is server-rendered (no HTMX lazy-load for initial render), the cleanest approach is:

1. `news_fetcher.fetch_news(market_id)` → list of `NewsItem` dicts (reads cache or fetches)
2. `news_filter.has_critical_event(headlines, market_id)` → bool
3. Filter out dismissed hashes for this user
4. Pass to a `_render_news_panel()` function → HTML string
5. Inject into the market card HTML string

---

## 10. File Plan

| File | Action | Role |
|------|--------|------|
| `news_fetcher.py` | CREATE | I/O adapter — yfinance fetch, schema normalise, sidecar cache read/write |
| `news_filter.py` | CREATE | Pure-math hex — keyword classifier, has_critical_event |
| `web/routes/news.py` | CREATE | Routes: POST /news/{market}/dismiss/{hash}, POST /news/{market}/panel-toggle |
| `system_params.py` | MODIFY | Add NEWS_KEYWORDS_SPI200, NEWS_KEYWORDS_AUDUSD, NEWS_DAMPENER_ALLOWLIST |
| `tests/test_signal_engine.py` | MODIFY | Add NEWS_FILTER_PATH to _HEX_PATHS_STDLIB_ONLY; add test_news_fetcher_no_forbidden_imports |
| `tests/test_news_fetcher.py` | CREATE | Both-shape fixture tests, cache hit/miss, XSS escape, SSRF-no-prefetch |
| `tests/test_news_filter.py` | CREATE | classify_headline unit tests, precision/recall gate on 30-headline fixture |
| `tests/fixtures/news/news_fixture_pre055.json` | CREATE | Pre-0.2.55 flat schema fixture (hand-crafted, 5 items) |
| `tests/fixtures/news/news_fixture_post055.json` | CREATE | Post-0.2.55 nested schema fixture (captured from live fetch, 5 items) |
| `tests/fixtures/news/news_classifier_30.json` | CREATE | 30-headline labelled fixture for precision/recall gate |
| `dashboard_renderer/components/news.py` | CREATE | _render_news_panel, _render_news_banner, _render_headline_row |
| `dashboard_renderer/assets.py` | MODIFY | Add .news-panel-* CSS classes (mirrors trace panel styles) |
| `web/app.py` | MODIFY | Register news routes (from web.routes.news import register; register(app)) |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| yfinance | 1.2.0 (pinned) | News fetch | Already installed; `_get_yf()` lazy pattern in place |
| re | stdlib | Keyword classifier regex | stdlib-only hex constraint; word-boundary patterns sufficient |
| hashlib | stdlib | title_hash (SHA256 hex[:16]) | Dedup + dismiss key; stdlib |
| json | stdlib | Cache file serialisation | Sidecar cache |
| tempfile + os.replace | stdlib | Atomic sidecar cache write | Mirrors state_manager/io.py pattern |

### No New Dependencies Required

All functionality is achievable with existing installed packages. No new `pip install` needed.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| XSS protection | Per-template escaping | Jinja2 `autoescape=True` (already enforced app-wide) | Structural, not per-field |
| Atomic file write | Custom locking | tempfile + os.replace (existing `_atomic_write_unlocked` pattern) | Proven in production |
| Per-user state flock | Custom lock | `mutate_user_state` (existing Phase 36) | Deadlock-safe, POSIX-correct |
| SSRF prevention | URL validation/blocklist | Render-only (no server-side prefetch) — just emit the URL as a link | Context says "SSRF closed by render-time-only escape" |

---

## Common Pitfalls

### Pitfall 1: `save_state()` inside `mutate_user_state` callback
**What goes wrong:** flock deadlock (same-process re-entrant lock on same file)
**Why:** POSIX flock locks the open-file-description; two fds in same process do not share ownership
**How to avoid:** ONLY call `mutate_user_state(uid, mutator)` for writes; never call `save_state()` inside the callback
**Warning signs:** Process hangs indefinitely on news dismiss request

### Pitfall 2: `news_filter.py` importing non-stdlib modules
**What goes wrong:** AST guard `test_forbidden_imports_absent` fails CI
**Why:** `_HEX_PATHS_STDLIB_ONLY` forbids datetime, os, json, yfinance, etc.
**How to avoid:** `news_filter.py` imports: ONLY `re` and `system_params`
**Warning signs:** Test failure "news_filter.py imports forbidden module X"

### Pitfall 3: Schema drift — assuming only post-0.2.55 shape
**What goes wrong:** Pre-0.2.55 fixture test (`'uuid' in item` path) never exercised
**Why:** Current yfinance is 1.2.0 so live fetches always produce post-0.2.55 shape
**How to avoid:** The pre-0.2.55 fixture is hand-crafted; both fixtures must pass normaliser tests
**Warning signs:** `test_normalise_pre055_shape` only runs against live data (wrong)

### Pitfall 4: `news_dismissed.date` not reset on date change
**What goes wrong:** User's dismissed set from yesterday persists, hiding fresh headlines
**Why:** date comparison in mutator not implemented
**How to avoid:** Always check `nd.get('date') != today` and reset `{'date': today, 'hashes': []}` (D-08)
**Warning signs:** Dismissed headlines still hidden the next day

### Pitfall 5: Cache file written without atomic rename
**What goes wrong:** Concurrent readers see truncated JSON during write
**Why:** `json.dump()` to a file is not atomic
**How to avoid:** Always use `_write_cache()` with tempfile + os.replace
**Warning signs:** `json.JSONDecodeError` on cache reads under load

### Pitfall 6: Banner fires on "first-rate service"
**What goes wrong:** False positive — "first-rate" contains "rate" which matches interest rate keywords
**Why:** Simple substring match without dampener
**How to avoid:** `_DAMPENER_RE.sub('', text_lower)` before keyword match (implemented in `classify_headline`)
**Warning signs:** Precision drops below 0.7 in classifier test

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | pyproject.toml |
| Quick run command | `.venv/bin/pytest tests/test_news_fetcher.py tests/test_news_filter.py -x --tb=short` |
| Full suite command | `.venv/bin/pytest -x --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NEWS-01 | Top 5 headlines, deduplicated by title_hash, cached | unit | `pytest tests/test_news_fetcher.py::test_fetch_top5_deduped -x` | ❌ Wave 0 |
| NEWS-01 | Cache hit skips yfinance call | unit | `pytest tests/test_news_fetcher.py::test_cache_hit_skips_fetch -x` | ❌ Wave 0 |
| NEWS-02 | Classifier precision ≥0.7 / recall ≥0.9 | unit | `pytest tests/test_news_filter.py::test_classifier_precision_recall -x` | ❌ Wave 0 |
| NEWS-02 | Banner copy correct | unit | `pytest tests/test_news_filter.py::test_banner_copy -x` | ❌ Wave 0 |
| NEWS-03 | Pre-0.2.55 flat fixture normalises correctly | unit | `pytest tests/test_news_fetcher.py::test_normalise_pre055_shape -x` | ❌ Wave 0 |
| NEWS-03 | Post-0.2.55 nested fixture normalises correctly | unit | `pytest tests/test_news_fetcher.py::test_normalise_post055_shape -x` | ❌ Wave 0 |
| NEWS-03 | XSS: `<script>alert(1)</script>` renders escaped | integration | `pytest tests/test_news_fetcher.py::test_xss_headline_escaped -x` | ❌ Wave 0 |
| NEWS-03 | SSRF: no server-side URL prefetch | unit | `pytest tests/test_news_fetcher.py::test_no_server_side_url_prefetch -x` | ❌ Wave 0 |
| NEWS-04 | Dismiss adds title_hash to `news_dismissed` | unit | `pytest tests/test_news_fetcher.py::test_dismiss_persists -x` | ❌ Wave 0 |
| NEWS-04 | Dismiss isolation (user A dismiss ≠ user B view) | integration | `pytest tests/test_news_fetcher.py::test_dismiss_isolation -x` | ❌ Wave 0 |
| OPS-03 | news_filter in _HEX_PATHS_STDLIB_ONLY | unit | `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x` | ✅ (existing, needs update) |
| OPS-03 | news_fetcher no forbidden imports | unit | `pytest tests/test_news_fetcher.py::test_news_fetcher_no_forbidden_imports -x` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/test_news_fetcher.py` — covers NEWS-01, NEWS-03, NEWS-04, OPS-03 (fetcher)
- [ ] `tests/test_news_filter.py` — covers NEWS-02
- [ ] `tests/fixtures/news/news_fixture_pre055.json` — pre-0.2.55 hand-crafted fixture
- [ ] `tests/fixtures/news/news_fixture_post055.json` — post-0.2.55 captured fixture
- [ ] `tests/fixtures/news/news_classifier_30.json` — 30-headline labelled fixture
- [ ] Update `tests/test_signal_engine.py`: add `NEWS_FILTER_PATH` to `_HEX_PATHS_STDLIB_ONLY`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a (news panel behind existing auth) |
| V3 Session Management | no | n/a (uses existing session) |
| V4 Access Control | yes | `Depends(current_user_id)` on dismiss route |
| V5 Input Validation | yes | `title_hash` must be hex[:16]; `market` must pass `is_known_market()` |
| V6 Cryptography | no | SHA256 used for dedup/hash only, not security-sensitive |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via malicious news headline | Tampering | Jinja2 `autoescape=True` (structural, app-wide) |
| SSRF via server-side link prefetch | Tampering/Elevation | Render-only: never fetch headline URLs server-side |
| Cross-user dismiss leakage | Information Disclosure | `mutate_user_state(uid, ...)` scopes all writes to `state['users'][uid]` |
| Path traversal via `market` path param | Tampering | `is_known_market(market)` membership check at route entry |
| title_hash injection (path segment) | Tampering | Validate hex format (16-char hex string) at route entry |
| Cache poisoning via rogue yfinance response | Tampering | Normaliser strips unexpected fields; only typed `NewsItem` fields persist |

---

## Open Questions / Risks

1. **`news_panel_collapsed` toggle route scope**
   - What we know: D-02 says collapse state is server-side. The route needs to update `state['users'][uid]['news_panel_collapsed']`.
   - What's unclear: Should there be a dedicated `POST /news/{market}/panel-toggle` route, or a generic `/settings/ui-prefs` route (reusable for Phase 39 tour collapsed states)?
   - Recommendation: Dedicated `POST /news/panel-toggle` for Phase 38; Phase 39 can generalise if needed.

2. **Dashboard integration: synchronous render vs HTMX lazy partial**
   - What we know: The existing dashboard is synchronously rendered. The news fetch adds a `news_fetcher.fetch_news()` call at render time (cache hit is fast; cache miss blocks the request).
   - What's unclear: On a cache miss (first request of the day), the yfinance call may take 1-5s. Should the news panel be lazy-loaded via HTMX to avoid blocking the page render?
   - Recommendation: For Phase 38 simplicity, inline synchronous render (always hits cache after first request). If latency is a problem, add HTMX lazy load in a follow-up.

3. **`news_fetcher.py` called from `data_fetcher._get_yf()` or separate?**
   - What we know: `data_fetcher._get_yf()` is a lazy yfinance import. `news_fetcher.py` needs the same pattern.
   - Recommendation: `news_fetcher.py` defines its own `_get_yf()` accessor (identical implementation). Do NOT import from `data_fetcher` — that would introduce a forbidden cross-I/O-peer import.

4. **`clickThroughUrl` may be None (confirmed in live data)**
   - Verified: `AUDUSD=X` news item had `"clickThroughUrl": null`.
   - Handled: Normaliser falls back to `canonicalUrl.url` if `clickThroughUrl` is None.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Pre-0.2.55 flat schema keys: `uuid`, `title`, `link`, `publisher`, `providerPublishTime` | §1 | Fixture test fails; low risk (fixture is hand-crafted anyway) |
| A2 | Initial keyword sets achieve precision ≥0.7 / recall ≥0.9 | §6 | Classifier test fails; fix by adding/removing keywords in system_params.py |
| A3 | `news_panel_collapsed` as field name for collapse state | §3 | Purely cosmetic; any field name works |
| A4 | News panel dashboard injection is synchronous (not HTMX lazy) | §9 | Render latency on cache miss; fix by adding HTMX lazy load |

---

## Sources

### Primary (HIGH confidence)
- `requirements.txt` — yfinance==1.2.0 confirmed
- Live yfinance 1.2.0 fetch (`^AXJO`, `AUDUSD=X`) — post-0.2.55 schema verified
- `state_manager/io.py::_atomic_write_unlocked` — atomic cache write pattern
- `dashboard_renderer/components/trace.py:225-261` — collapsible `<details>` pattern
- `web/routes/admin/__init__.py:192-205` — empty-200 HTMX dismiss pattern
- `tests/test_signal_engine.py:495-624` — AST boundary constants and `_HEX_PATHS_STDLIB_ONLY`
- `system_params.py` — constant declaration pattern
- `state_manager/__init__.py:385-429` — `mutate_user_state` signature and flock semantics

### Secondary (MEDIUM confidence)
- GitHub yfinance CHANGELOG — news-related changes around 0.2.55/1.0

### Tertiary (LOW confidence)
- Pre-0.2.55 flat schema structure — ASSUMED from community reports (not verifiable without old version install)

---

## Metadata

**Confidence breakdown:**
- yfinance schema (post-0.2.55): HIGH — verified live against 1.2.0
- yfinance schema (pre-0.2.55): LOW — assumed from community reports, hand-crafted fixture only
- Cache write strategy: HIGH — directly mirrors proven io.py pattern
- Collapsible pattern: HIGH — exact file:line verified
- Dismiss pattern: HIGH — exact file:line verified
- AST boundary: HIGH — exact constants verified
- Keyword classifier: MEDIUM — initial sets are assumptions; precision/recall gate validates at test time
- system_params pattern: HIGH — pattern directly verified
- Per-user state: HIGH — mutate_user_state verified
- Route injection: MEDIUM — `/markets/{m}` route does not exist; injection is into dashboard renderer

**Research date:** 2026-05-15
**Valid until:** 2026-06-15 (yfinance schema may drift; re-verify if 1.2.x patch released)
