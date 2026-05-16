---
phase: 38-news-integration
reviewed: 2026-05-16T00:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - news_filter.py
  - news_fetcher.py
  - system_params.py
  - web/routes/news.py
  - web/app.py
  - dashboard_renderer/components/news.py
  - dashboard_renderer/components/signals.py
  - dashboard_renderer/context.py
  - dashboard_renderer/api.py
  - dashboard_renderer/assets.py
  - dashboard_renderer/shell.py
  - web/routes/dashboard/__init__.py
  - tests/test_news_filter.py
  - tests/test_news_fetcher.py
  - tests/test_web_news_routes.py
  - tests/test_web_news_dismiss.py
  - tests/test_web_news_dashboard_integration.py
  - tests/test_signal_engine.py
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Phase 38: Code Review Report

**Reviewed:** 2026-05-16T00:00:00Z
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 38 introduces a news-fetcher I/O adapter, a pure-math keyword classifier, a news-panel renderer, two POST routes (dismiss + toggle-collapse), and integration into the signals component. The security posture is generally sound: XSS escaping is render-time, URL scheme validation is thorough, path-traversal is blocked by an allowlist, and auth is gated via `Depends(current_user_id)`.

One critical bug was found: the toggle-collapse route is registered and the state-write logic is correct, but no HTML trigger is wired to call it. The `<summary>` element in `render_news_panel` has no `hx-post` attribute, making the collapse preference permanently unsaveable from the UI. The state write is dead code from the user's perspective.

Four warnings cover: triplicated market-allowlist definitions that will drift, a non-dict URL silently yielding an empty link, unbounded growth of the dismissed-hashes list, and broad exception swallowing in the signals component news block. Three info items cover the `render_dashboard_files` function not receiving news context, missing guard for an empty dampener list, and test hash literals that exceed 16 chars.

## Critical Issues

### CR-01: toggle-collapse POST route wired in server but never triggered from UI

**File:** `dashboard_renderer/components/news.py:110-111`
**Issue:** `render_news_panel` emits a `<summary>` tag with no `hx-post`, `hx-trigger`, or JavaScript event listener. The `POST /news/{market}/toggle-collapse` route and its `mutate_user_state` writer are correctly implemented, but there is no mechanism in the rendered HTML that calls them. When a user clicks to collapse the `<details>` panel, no request is sent. The `collapsed` preference read from state at render time is therefore always the default (`False`), making the feature non-functional end-to-end.

**Fix:**
```python
# In render_news_panel, replace the bare <summary> with one that fires hx-post:
return (
    f'<details class="news-panel-disclosure"{open_attr}'
    f' hx-post="/news/{mkt_esc}/toggle-collapse"'
    f' hx-trigger="toggle"'
    f' hx-swap="none">\n'
    f'<summary class="news-panel-summary">Market News</summary>\n'
    ...
)
```

`hx-trigger="toggle"` fires on the native `toggle` event that `<details>` emits when opened or closed. `hx-swap="none"` prevents HTMX from trying to swap anything in response. Without this, every render correctly reads `collapsed` from state, but the state is never updated because the POST is never sent.

## Warnings

### WR-01: Three independent copies of the valid-markets set — guaranteed to drift

**File:** `web/routes/news.py:27`, `news_fetcher.py:62`, `system_params.py:168`
**Issue:** `system_params.KNOWN_MARKET_IDS`, `news_fetcher._VALID_MARKETS`, and `web/routes/news._VALID_MARKETS` are three separate `frozenset({'SPI200', 'AUDUSD'})` definitions. When a new market is added to `KNOWN_MARKET_IDS`, both `news_fetcher._VALID_MARKETS` and `web/routes/news._VALID_MARKETS` must be manually updated or dismiss/toggle routes will return 404 for the new market, and fetch_news will silently return `[]`. The comments in both files acknowledge `system_params` doesn't have a constant yet — but it does (`KNOWN_MARKET_IDS`, line 168).

**Fix:**
```python
# news_fetcher.py — replace module-local definition:
from system_params import KNOWN_MARKET_IDS as _VALID_MARKETS

# web/routes/news.py — replace module-local definition:
from system_params import KNOWN_MARKET_IDS as _VALID_MARKETS

def _is_known_market(market: str) -> bool:
    return market in _VALID_MARKETS
```

### WR-02: Non-dict URL value in yfinance response silently yields empty URL

**File:** `news_fetcher.py:188-189`
**Issue:** `_normalise_post_055` resolves the URL object with `url_obj = c.get('clickThroughUrl') or c.get('canonicalUrl') or {}`, then guards with `isinstance(url_obj, dict)` before calling `.get('url', '')`. If `clickThroughUrl` or `canonicalUrl` is a raw string (e.g. `'https://example.com/article'`) rather than a dict wrapping a `url` key, the `isinstance` check returns `False` and `raw_url` is set to `''`. The URL is silently discarded and the rendered headline has an empty `href`. Since yfinance schema is user-controlled third-party data, string-form URL values are plausible.

**Fix:**
```python
url_obj = c.get('clickThroughUrl') or c.get('canonicalUrl') or {}
if isinstance(url_obj, dict):
    raw_url = url_obj.get('url', '')
elif isinstance(url_obj, str):
    raw_url = url_obj  # handle string-form URL directly
else:
    raw_url = ''
url = _validate_url_scheme(raw_url)
```

### WR-03: Dismissed-hashes list grows without bound within a single day

**File:** `web/routes/news.py:85-86`
**Issue:** `bucket['hashes'].append(title_hash)` inside `dismiss_headline` has no size cap. D-08 auto-expiry resets the list daily, so state growth is bounded across days. However, within a single day a user could craft repeated POST requests with different (forged) 16-char hex strings and grow `bucket['hashes']` arbitrarily large before midnight reset. Each entry is 16 bytes of state, so this is a low-severity DoS on the per-user state rather than a crash risk, but it contradicts the project's `MAX_WARNINGS: int = 50` pattern for bounding list growth.

**Fix:**
```python
# Cap to a reasonable maximum (e.g. 50 dismissals per market per day):
_MAX_DISMISSED_HASHES = 50

if title_hash not in bucket['hashes']:
    if len(bucket['hashes']) < _MAX_DISMISSED_HASHES:
        bucket['hashes'].append(title_hash)
```

### WR-04: Broad `except Exception` swallows render errors silently in signals component

**File:** `dashboard_renderer/components/signals.py:291-306`
**Issue:** The inner `try/except Exception` block around `_fetch_news` (lines 291-299) and the outer `try/except Exception` block around the entire news panel injection (lines 270-306) both log at WARNING level with no re-raise. This is the stated "never-crash D-10" discipline. However, the outer block catches `ImportError` for `news_fetcher` and `dashboard_renderer.components.news` — if either module fails to import (e.g. syntax error introduced in a future patch), the signals page silently renders without a news panel and the operator has no visible indication beyond a log entry. More critically, `exc_info=True` is only passed in the outer catch (line 305), so inner-block exceptions from `fetch_news` are logged without a traceback, making debugging harder.

**Fix:**
```python
# In the inner except block, add exc_info=True:
except Exception:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        '[Signals] fetch_news failed for %s — empty fallback (D-10)',
        state_key,
        exc_info=True,   # add this
    )
    _headlines = []
```

## Info

### IN-01: `render_dashboard_files` does not propagate news context to on-disk render

**File:** `dashboard_renderer/api.py:70-93`
**Issue:** `render_dashboard_files` (used by `main.run_daily_check` to pre-render `dashboard.html`) does not accept or pass `uid`, `news_dismissed`, or `news_panel_collapsed`. The on-disk `dashboard.html` therefore always renders the news panel with empty dismissed hashes and `collapsed=False`, regardless of any user's preferences. This is the correct design choice (the on-disk file is not per-user), but it is not documented. The sibling re-render path in the same function also omits these. No functional bug since HTMX-driven market-scoped pages use `render_dashboard_as_str` which does pass news context, but the on-disk fallback path shows stale/unfiltered headlines to any user who lands on it.

**Fix:** Add a comment in `render_dashboard_files` documenting this intentional omission:
```python
# NOTE: on-disk render intentionally omits uid/news_dismissed/news_panel_collapsed —
# dashboard.html is not per-user. HTMX market-scoped pages use render_dashboard_as_str
# which threads per-user news context through _serve_market_scoped_page.
```

### IN-02: Empty `NEWS_DAMPENER_ALLOWLIST` would silently degrade classifier performance

**File:** `news_filter.py:58-61`
**Issue:** `_DAMPENER_RE` is compiled from `'|'.join(re.escape(d) for d in NEWS_DAMPENER_ALLOWLIST)`. If `NEWS_DAMPENER_ALLOWLIST` is ever set to an empty tuple (accidental or during testing), `'|'.join(())` produces `''`, and `re.compile('')` compiles a pattern that matches the empty string at every position. This means `_DAMPENER_RE.search(text_lower)` always returns a match, so `classify_headline` always takes the slow path (sub + re-run). Since `re.sub('', '', text)` returns `text` unchanged, the LOGIC is still correct — no false positives or negatives — but the fast-path optimisation is completely bypassed. There is no guard or assertion to detect this.

**Fix:**
```python
if NEWS_DAMPENER_ALLOWLIST:
    _DAMPENER_RE: re.Pattern = re.compile(
        '|'.join(re.escape(d) for d in NEWS_DAMPENER_ALLOWLIST),
        re.IGNORECASE,
    )
else:
    _DAMPENER_RE = re.compile(r'(?!)')  # never-matching pattern
```

### IN-03: Test fixture hash literals are 17 characters, not the required 16

**File:** `tests/test_web_news_routes.py:136`, `tests/test_web_news_dismiss.py:various`
**Issue:** Several test fixture headline dicts use `title_hash='abc1234567890deff'` (17 hex chars). The production `_HASH_RE = re.compile(r'^[0-9a-f]{16}$')` requires exactly 16 chars. These test fixtures would be rejected by the dismiss route's hash validation (422) if the hash were submitted as a URL path segment, yet the renderer tests pass them through `render_news_panel` which does not validate hash length. This means the renderer tests use malformed test data that would be rejected by the real route. The mismatch does not cause test failures (renderer doesn't validate hashes) but makes the fixture misleading.

**Fix:** Update all test fixtures to use exactly 16-character hex hashes:
```python
# Change 'abc1234567890deff' (17 chars) to 'abc1234567890def' (16 chars)
def _make_headline(self, ..., title_hash='abc1234567890def'):
```

---

_Reviewed: 2026-05-16T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
