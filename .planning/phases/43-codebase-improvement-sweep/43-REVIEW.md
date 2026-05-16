---
phase: 43-codebase-improvement-sweep
reviewed: 2026-05-16T10:00:00Z
depth: standard
files_reviewed: 29
files_reviewed_list:
  - .github/workflows/ci.yml
  - .gitignore
  - crash_boundary.py
  - daily_run.py
  - daily_run_helpers.py
  - dashboard_renderer/assets.py
  - dashboard_renderer/components/signals.py
  - dashboard_renderer/components/trades.py
  - dashboard_renderer/static/dashboard.css
  - dashboard_renderer/static/handle_trades_error.js
  - dashboard_renderer/static/trace_toggle.js
  - dashboard_renderer/stats.py
  - interactive.py
  - main.py
  - news_fetcher.py
  - news_filter.py
  - notifier/templates.py
  - notifier/templates_sections.py
  - ruff.toml
  - scheduler_driver.py
  - signal_engine.py
  - sizing_engine/sizing.py
  - state_manager/__init__.py
  - system_params.py
  - web/routes/admin/__init__.py
  - web/routes/dashboard/__init__.py
  - web/routes/dashboard/_cache.py
  - web/routes/dashboard/_helpers.py
  - web/routes/dashboard/_routes.py
findings:
  critical: 2
  warning: 4
  info: 3
  total: 9
status: issues_found
---

# Phase 43: Code Review Report

**Reviewed:** 2026-05-16T10:00:00Z
**Depth:** standard
**Files Reviewed:** 29
**Status:** issues_found

## Summary

Phase 43 introduces: news cache out-of-band refresh, mutate_state re-entrancy guard, trade log cap 20 to 200, /admin/trades/full download endpoint, CSS/JS extraction to static files, dashboard route split, allowlist-based crash-email redaction, and a GitHub Actions CI pipeline.

The most critical finding is a dual-schema cache incompatibility in news_fetcher.py: fetch_news and refresh_news_cache write incompatible JSON envelopes to the same cache file. A secondary critical finding is an XSS vector in handle_trades_error.js that injects raw server response text via innerHTML. Four warnings cover: Path.with_suffix('.json.tmp') raising ValueError on Python 3.13, module-level mkdir at import time, news_filter.has_critical_event failing open for unknown market IDs, and Content-Disposition header injection.

---

## Critical Issues

### CR-01: Dual-schema cache envelope — fetch_news and load_news_cache are incompatible

**File:** `news_fetcher.py:433` and `news_fetcher.py:542`

**Issue:** fetch_news (via _write_cache) writes `{'date': '...', 'headlines': [...]}`. load_news_cache reads `payload.get('items', [])`. refresh_news_cache writes `{'items': [...], 'error': ..., 'fetched_at': ..., 'stale': ...}`. _load_cache (used inside fetch_news) reads `envelope.get('headlines')`.

Two incompatible schemas exist for the same cache file:

- fetch_news writes 'headlines'; load_news_cache reads 'items' — dashboard always gets []
- refresh_news_cache writes 'items'; _load_cache reads 'headlines' — cache always misses for daily gate, live HTTP on every run

After refresh_news_cache writes the scheduler-format file, every subsequent fetch_news call (daily gate) misses the cache and makes a live HTTP call. After fetch_news writes the _write_cache-format file, load_news_cache returns items=[] (dashboard shows no news).

**Fix:** Unify on a single envelope schema. Use the richer refresh_news_cache schema in _write_cache:

```python
# In fetch_news, replace _write_cache with the unified schema:
envelope = {
  'items': items,           # rename from 'headlines'
  'error': None,
  'fetched_at': datetime.now(UTC).isoformat(),
  'stale': False,
  'date': date.today().isoformat(),  # keep for _load_cache TTL check
}
_write_cache(cache_path, envelope)

# Update _load_cache to read 'items':
items = envelope.get('items') or envelope.get('headlines')
if not isinstance(items, list):
    return None
```

---

### CR-02: XSS via innerHTML with unescaped server response and JSON fields

**File:** `dashboard_renderer/static/handle_trades_error.js:20` and `dashboard_renderer/static/handle_trades_error.js:24`

**Issue:** Line 24 assigns `evt.detail.xhr.responseText` directly to `errorBox.innerHTML` for 409 responses. Line 20 interpolates `e.field` and `e.reason` from JSON-parsed server response into innerHTML without escaping. Any future 409 response body containing HTML would be injected. Although current server paths produce plain-text, this is an unguarded pattern that creates an XSS foothold.

**Fix:** Use textContent for plain text or escape before innerHTML:

```js
function _escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Line 20:
return '<div class="error-row"><code>' + _escapeHtml(e.field) + '</code>: '
  + _escapeHtml(e.reason) + '</div>';

// Line 24 — use textContent instead of innerHTML:
var p = document.createElement('p');
p.className = 'error-heading';
p.textContent = evt.detail.xhr.responseText;
errorBox.innerHTML = '';
errorBox.appendChild(p);
```

---

## Warnings

### WR-01: Path.with_suffix('.json.tmp') raises ValueError on Python 3.13

**File:** `news_fetcher.py:620`

**Issue:** Python 3.12+ changed Path.with_suffix() to raise ValueError for suffixes that are not a single dot-segment (i.e., do not match the pattern of a single extension like '.tmp'). The suffix '.json.tmp' contains two dots and will raise ValueError on Python 3.13 (the CI and production target per ci.yml line 12). This crash occurs inside refresh_news_cache on every write attempt, silently swallowed by the except block (line 624) — meaning the cache is never written by the scheduler refresh path, but the exception is logged as a warning only.

**Fix:** Use path concatenation instead of with_suffix:

```python
# news_fetcher.py:620 — replace:
tmp_path = cache_file.with_suffix('.json.tmp')

# with:
tmp_path = cache_file.parent / (cache_file.name + '.tmp')
```

---

### WR-02: _CACHE_DIR.mkdir() at module import time breaks test isolation

**File:** `news_fetcher.py:107`

**Issue:** `_CACHE_DIR.mkdir(parents=True, exist_ok=True)` runs unconditionally at module import time. Any test that imports news_fetcher (directly or transitively) creates `.cache/news/` in the project root immediately, before any test fixtures can redirect paths. Running from a read-only filesystem raises PermissionError at import time, crashing the entire process before any test isolation runs.

**Fix:** Move mkdir into _cache_path (lazy creation):

```python
def _cache_path(market_id: str) -> Path:
  if not _is_valid_market_id(market_id):
    raise ValueError(f'invalid market_id: {market_id!r}')
  path = _CACHE_DIR / f'news_{market_id}.json'
  path.parent.mkdir(parents=True, exist_ok=True)
  return path
```

Remove the module-level `_CACHE_DIR.mkdir(...)` call at line 107.

---

### WR-03: has_critical_event returns gate_status='clear' for unknown market_id — fails open

**File:** `news_filter.py:137-174`

**Issue:** When market_id is not in _PATTERNS, classify_headline logs WARNING and returns False for every headline. has_critical_event interprets no True matches as gate_status='clear' — signals are allowed through. The D-02 BLOCK_ON_FAILURE principle requires unknown market_id to block (gate_status='unknown'), not pass through. A new market added to state['markets'] but not yet in _MARKET_KEYWORDS silently passes the news gate.

**Fix:** Check market_id membership in _PATTERNS before iterating headlines:

```python
def has_critical_event(result: Any, market_id: str) -> CriticalEventResult:
  if result.error is not None:
    return CriticalEventResult(triggered=False, fetch_error=result.error, gate_status='unknown')

  # Unknown market_id — no keyword list; fail-closed per D-02.
  if market_id not in _PATTERNS:
    _LOGGER.warning('has_critical_event unknown market_id=%r; failing closed', market_id)
    return CriticalEventResult(triggered=False, fetch_error=None, gate_status='unknown')

  for item in result.items:
    title = item.get('title', '') if hasattr(item, 'get') else ''
    if classify_headline(title, market_id):
      return CriticalEventResult(triggered=True, fetch_error=None, gate_status='blocked')

  return CriticalEventResult(triggered=False, fetch_error=None, gate_status='clear')
```

---

### WR-04: Content-Disposition filename embeds unvalidated user_id — header injection risk

**File:** `web/routes/admin/__init__.py:75`

**Issue:** The Content-Disposition header is built as:

```python
f'attachment; filename="trades-{user_id}-{date_str}.json"'
```

user_id is a string from the session; no format validation is applied before embedding it in the header value. If user_id contains `"`, `;`, or CRLF characters, it can break the header structure or inject additional headers. require_admin gates the route, but defence-in-depth requires sanitising values embedded in HTTP headers.

**Fix:** Sanitise user_id before header interpolation:

```python
import re as _re
safe_uid = _re.sub(r'[^\w.-]', '_', user_id)
headers = {'Content-Disposition': f'attachment; filename="trades-{safe_uid}-{date_str}.json"'}
```

---

## Info

### IN-01: CI pipeline has no pip dependency cache — slow cold builds on every run

**File:** `.github/workflows/ci.yml:13-14`

**Issue:** Dependencies are reinstalled from scratch on every CI run. For numpy, pandas, yfinance, this costs 2-3 minutes per run.

**Fix:** Use setup-python's built-in pip cache:

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.13"
    cache: "pip"
```

---

### IN-02: CI triggers on every push to every branch — no branch filter

**File:** `.github/workflows/ci.yml:2-4`

**Issue:** `on: push` with no `branches` filter runs CI on all pushes including tags, bots, and maintenance branches. Standard practice is to gate on main plus all PRs.

**Fix:**

```yaml
on:
  push:
    branches: [main]
  pull_request:
```

---

### IN-03: ruff.toml defines format config only — no lint rules enforced and not wired to CI

**File:** `ruff.toml:1-4`

**Issue:** ruff.toml sets indent-width and format.indent-style but no select/ignore/lint rules. ruff check is not in the CI pipeline. The config exists but provides no lint enforcement.

**Fix:** Either add lint rules and wire ruff check to CI, or add a comment clarifying format-only intent:

```toml
# Format only — lint not enforced (pytest + type annotations cover correctness)
indent-width = 2

[format]
indent-style = "space"
```

---

_Reviewed: 2026-05-16T10:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
