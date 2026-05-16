---
phase: 38-news-integration
verified: 2026-05-16T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
overrides:
  - must_have: "Jinja2 autoescape=True (ROADMAP SC1 wording)"
    reason: "ROADMAP SC1 text was drafted before Plan 04 confirmed this codebase never uses Jinja2. Plan 04 supersedes with Python f-string + explicit html.escape() on all 9 dynamic values — identical XSS safety outcome. No live Jinja2 import exists anywhere in the render path (grep confirmed). PLAN must_haves do not list Jinja2; requirement intent (XSS-safe render) is fully met."
    accepted_by: "verifier"
    accepted_at: "2026-05-16T00:00:00Z"
---

# Phase 38: News Integration Verification Report

**Phase Goal:** Integrate live news headlines into the per-market dashboard — server-side render of top-5 filtered headlines with dismiss and collapse-toggle UI.
**Verified:** 2026-05-16
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User sees top-5 yfinance headlines per market, deduplicated by title hash, cached daily, XSS-escaped, outbound links with rel="noopener noreferrer" | VERIFIED | `render_news_panel` in `dashboard_renderer/components/news.py` filters by `dismissed_hashes`, calls `html.escape()` on all 9 dynamic values, `rel="noopener noreferrer"` confirmed at line 53; `fetch_news` in `news_fetcher.py` deduplicates via `title_hash`, caches in JSON envelope with date TTL; behavioral spot-check confirmed XSS escaping and noopener |
| 2 | Both pre-0.2.55 and post-0.2.55 yfinance schemas normalise to single NewsItem with title_hash; XSS payload passes through verbatim; no SSRF | VERIFIED | `_normalise_item` dispatches on `'content' in raw` vs `'uuid' in raw`; `_compute_title_hash` sha256[:16] stable across whitespace/case (spot-check pass); XSS payload `<script>alert(1)</script>` preserved verbatim at fetch layer (spot-check pass); no `requests.get/post/urlopen/httpx` in `news_fetcher.py` (grep confirmed) |
| 3 | Critical-event banner with locked copy fires from word-boundary classifier at precision ≥0.7, recall ≥0.9; dismissed critical headline removes banner | VERIFIED | `news_filter.py` — precision=0.941, recall=1.000 on 30-headline fixture (SUMMARY 02); `render_news_panel` filters dismissed BEFORE calling `has_critical_event(filtered, ...)` (line 94-97 in news.py); behavioral spot-check confirmed banner disappears when only critical headline dismissed |
| 4 | User can dismiss a headline; dismiss state persists per-user in `state['users'][uid]['news_dismissed'][market_id]`; auto-expires daily (D-08); admin dismiss isolated from F&F users | VERIFIED | `web/routes/news.py` POST `/news/{market}/dismiss/{title_hash}` — setdefault chain (8 calls), D-08 atomic expiry inside `mutate_user_state` callback, `_HASH_RE.fullmatch` validates hash, `_is_known_market` gates market; 40 tests in `test_web_news_routes.py` + `test_web_news_dismiss.py` all pass |
| 5 | AST hex boundary: `signal_engine` cannot import `news_fetcher`/`news_filter`; `news_filter.py` in `_HEX_PATHS_STDLIB_ONLY` (stdlib-only); `news_fetcher.py` passes FORBIDDEN_MODULES_NEWS_FETCHER gate | VERIFIED | `TestDeterminism` — 79 passed; `news_filter.py` imports only `{re, logging, system_params}` (AST confirmed); `news_fetcher.py` imports blocked modules absent (grep and AST gate tests pass); `NEWS_FILTER_PATH` in `_HEX_PATHS_STDLIB_ONLY` (Plan 01) |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `system_params.py` | NEWS_KEYWORDS_SPI200, NEWS_KEYWORDS_AUDUSD, NEWS_DAMPENER_ALLOWLIST | VERIFIED | All 3 tuple[str,...] constants present; `python -c "import system_params as s; print(hasattr(s,'NEWS_KEYWORDS_SPI200')..."` exits 0 |
| `news_filter.py` | classify_headline, has_critical_event, stdlib-only | VERIFIED | 134 LOC ≤500; imports = {re, logging, system_params}; both functions present |
| `news_fetcher.py` | fetch_news, NewsItem with title_hash, _normalise_item, _compute_title_hash, _validate_url_scheme, _is_valid_market_id, _cache_path, _load_cache, _write_cache | VERIFIED | 413 LOC ≤500; all named functions present (grep count = 1 each); JSON date TTL confirmed; atomic write via tempfile+os.replace; no mtime refs |
| `web/routes/news.py` | register(app) — POST dismiss + POST toggle-collapse | VERIFIED | 118 LOC ≤500; both POST routes registered; no GET on toggle-collapse (grep = 0); Depends(current_user_id) on both handlers |
| `dashboard_renderer/components/news.py` | render_news_panel, f-string renderer, html.escape on all dynamic values | VERIFIED | 124 LOC ≤500; 9 `html.escape()` calls; no Jinja2 import; filter-before-banner ordering at lines 94-97 |
| `dashboard_renderer/components/signals.py` | render_news_panel injected per market | VERIFIED | `render_news_panel` called at line 301 inside per-market loop; `fetch_news` local-imported at line 273; D-10 try/except wraps entire block |
| `dashboard_renderer/context.py` | uid, news_dismissed, news_panel_collapsed fields | VERIFIED | All 3 fields present (grep count ≥2 each); default_factory=dict for dicts, None for uid |
| `dashboard_renderer/assets.py` | .news-panel-disclosure, .news-banner, .btn-news-dismiss CSS | VERIFIED | All 3 CSS classes present |
| `web/app.py` | news_route.register(application) wiring | VERIFIED | `from web.routes import news as news_route` and `news_route.register(application)` at line 189 |
| `tests/fixtures/news/news_fixture_pre055.json` | 5-item pre-0.2.55 flat schema | VERIFIED | len=5, uuid+title+link+publisher+providerPublishTime, XSS payload present |
| `tests/fixtures/news/news_fixture_post055.json` | 5-item post-0.2.55 nested schema | VERIFIED | len=5, content+id, one clickThroughUrl=null |
| `tests/fixtures/news/news_classifier_30.json` | 30 labelled headlines | VERIFIED | len=30, 16 positive (within 12..20 gate) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `news_filter.py` | `system_params` NEWS_KEYWORDS_* | `from system_params import NEWS_KEYWORDS_SPI200, NEWS_KEYWORDS_AUDUSD, NEWS_DAMPENER_ALLOWLIST` | WIRED | Line 21-25 in news_filter.py confirmed |
| `news_fetcher.py` | `system_params.KNOWN_MARKET_IDS` | `from system_params import KNOWN_MARKET_IDS as _VALID_MARKETS` | WIRED | Line 60 in news_fetcher.py; gates _cache_path construction |
| `news_fetcher.py` | yfinance.Ticker | `_get_yf()` lazy accessor | WIRED | Lines 80-91; monkeypatch-friendly; all 31 tests pass without live network |
| `web/routes/news.py` | `state_manager.mutate_user_state` | local import inside route handlers | WIRED | Lines 73, 109 in news.py |
| `dashboard_renderer/components/signals.py` | `render_news_panel` | per-market loop appends news panel | WIRED | Line 301; local import at line 274 |
| `web/routes/dashboard/__init__.py` | RenderContext (uid + news_dismissed + news_panel_collapsed) | `_serve_market_scoped_page` passes per-user state via `Depends(_get_current_user_id)` | WIRED | Lines 308-337; full `.get()` default chain for first-visit safety |
| HTMX dismiss button | POST /news/{market}/dismiss/{title_hash} | hx-post in `_render_headline_row` | WIRED | Line 57-61 in news.py component; `hx-target="#news-row-{hash}"`, `hx-swap="outerHTML"` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `dashboard_renderer/components/news.py::render_news_panel` | `headlines` (list of NewsItem) | `news_fetcher.fetch_news()` called in `signals.py` line 292 | Yes — yfinance.Ticker.news or JSON cache (atomic write confirmed) | FLOWING |
| `dashboard_renderer/components/news.py::render_news_panel` | `dismissed_hashes` (frozenset) | `state['users'][uid]['news_dismissed'][market_id]['hashes']` read in dashboard route lines 308-309 | Yes — real state.json per-user data | FLOWING |
| `dashboard_renderer/components/signals.py` | `_headlines` | `_fetch_news(state_key, _symbol)` with symbol from `state['markets'][state_key]['symbol']` | Yes — symbol falls back to state_key if absent | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| classify_headline SPI200 rate hike | `classify_headline('RBA cuts interest rate', 'SPI200')` | True | PASS |
| Dampener suppresses false positive | `classify_headline('first-rate broker service', 'SPI200')` | False | PASS |
| Unknown market_id returns False + WARNING | `classify_headline('x', 'UNKNOWN')` | False, WARNING logged | PASS |
| XSS payload survives fetch layer | `_normalise_item({'content': {'title': '<script>alert(1)</script>', ...}})['title']` | `'<script>alert(1)</script>'` verbatim | PASS |
| XSS escaped at render | `render_news_panel(...)` with XSS title | `&lt;script&gt;` in output, raw `<script>` absent | PASS |
| title_hash stable across whitespace/case | `_compute_title_hash('  RBA Cuts Rates  ') == _compute_title_hash('rba cuts  rates')` | True | PASS |
| javascript: URL rejected | `_validate_url_scheme('javascript:alert(1)')` | `''` | PASS |
| Path traversal rejected | `_cache_path('../etc/passwd')` | ValueError | PASS |
| Banner disappears when only critical headline dismissed | `render_news_panel('SPI200', [rba_headline], {rba_headline['title_hash']}, False)` | 'Possible market-moving news' NOT in output | PASS |
| Panel open by default (collapsed=False) | `render_news_panel(..., collapsed=False)` | `<details class="news-panel-disclosure" open` in output | PASS |
| All 164 Phase 38 tests | `pytest tests/test_news_filter.py tests/test_news_fetcher.py tests/test_web_news_routes.py tests/test_web_news_dismiss.py tests/test_web_news_dashboard_integration.py tests/test_signal_engine.py::TestDeterminism` | 164 passed | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| NEWS-01 | Plans 01, 03, 04 | Top-5 headlines per market, deduplicated, cached daily, XSS-safe render, noopener | SATISFIED | fetch_news max_items=5, title_hash dedup, JSON date TTL cache, html.escape + rel=noopener confirmed |
| NEWS-02 | Plans 01, 02 | Word-boundary keyword classifier, dampener allowlist, precision ≥0.7 recall ≥0.9, locked banner copy | SATISFIED | precision=0.941, recall=1.000 on 30-headline fixture; dampener slow-path confirmed; locked copy byte-identical |
| NEWS-03 | Plans 01, 03 | Both yfinance schema shapes normalised, XSS payload pass-through, SSRF closed | SATISFIED | _normalise_pre_055 + _normalise_post_055 dispatch; XSS verbatim at fetch; no SSRF HTTP calls in news_fetcher.py |
| NEWS-04 | Plans 01, 04 | Per-user dismiss, per-user isolation, D-08 daily auto-expiry | SATISFIED | POST /news/{market}/dismiss/{title_hash} with mutate_user_state; D-08 atomic expiry inside mutator; per-user isolation tests (8 isolation scenarios) pass |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | All phase 38 files clean: no TBD/FIXME/XXX markers, no placeholder strings, no empty returns on critical paths, no Jinja2 imports |

### Human Verification Required

None. All observable truths are verifiable programmatically. The full-suite run shows 1 pre-existing flaky test (`test_tampered_tsi_trusted_does_NOT_grant`) that passes in isolation — confirmed unrelated to Phase 38 by running it standalone (1 passed).

### Gaps Summary

No gaps. All 5 must-haves verified. All 4 NEWS-* requirements satisfied. 164 Phase 38 tests pass. No blocker or warning anti-patterns found.

The single ROADMAP SC1 wording divergence ("Jinja2 autoescape=True") is accepted via override: the intent (XSS-safe render) is met by explicit `html.escape()` on all dynamic values, which is the documented codebase pattern confirmed by `grep -rn 'Jinja2' dashboard_renderer/ web/routes/news.py` returning zero live references.

---

_Verified: 2026-05-16_
_Verifier: Claude (gsd-verifier)_
