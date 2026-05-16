---
phase: 38-news-integration
plan: "03"
subsystem: news-fetcher-io-adapter
tags: [news-fetcher, yfinance, tdd, cache, security, hex-boundary, wave-2]
dependency_graph:
  requires:
    - FORBIDDEN_MODULES_NEWS_FETCHER in tests/test_signal_engine.py (Plan 01)
    - tests/fixtures/news/news_fixture_pre055.json (Plan 01)
    - tests/fixtures/news/news_fixture_post055.json (Plan 01)
    - HTTP_TIMEOUT_S in system_params.py (Plan 27-02)
  provides:
    - news_fetcher.fetch_news(market_id, symbol) -> list[NewsItem]
    - news_fetcher.NewsItem TypedDict with title_hash: str
    - news_fetcher._normalise_item (dispatches both schemas)
    - news_fetcher._compute_title_hash (sha256[:16] of normalised title)
    - news_fetcher._validate_url_scheme (javascript:/data:/relative rejected)
    - news_fetcher._is_valid_market_id (allowlist + regex gate)
    - news_fetcher._cache_path (raises ValueError on unknown market_id)
    - news_fetcher._load_cache (JSON date field TTL, no mtime)
    - news_fetcher._write_cache (atomic tempfile+os.replace)
    - tests/test_news_fetcher.py — 31-test suite
  affects: [Plan 04 (web banner wiring — fetch_news + title_hash consumer)]
tech_stack:
  added: []
  patterns:
    - lazy yfinance import via _get_yf() (mirrors data_fetcher.py Phase 27 #14)
    - JSON envelope date-field TTL (not mtime — T-38-03-09)
    - atomic tempfile+os.replace write (mirrors state_manager/io.py _atomic_write_unlocked)
    - market_id allowlist + [A-Z0-9_]{2,16} regex dual gate (T-38-03-04)
    - narrow-catch retry loop with backoff (mirrors data_fetcher.py)
    - title_hash = sha256(normalise(title))[:16] for dedup + dismiss-by-hash
key_files:
  created:
    - news_fetcher.py
    - tests/test_news_fetcher.py
  modified: []
decisions:
  - "JSON envelope date field (not filesystem mtime) is sole TTL authority — eliminates timezone/restart edge cases (T-38-03-09)."
  - "Module-local _VALID_MARKETS frozenset {'SPI200','AUDUSD'} — system_params has no VALID_MARKETS constant as of Plan 03; avoid touching it per CLAUDE.md scope constraint."
  - "clickThroughUrl takes precedence over canonicalUrl per post-0.2.55 schema; if clickThroughUrl is truthy dict but scheme is rejected, url falls to '' (not to canonicalUrl). Matches plan spec item 11."
  - "Broad except in retry loop catches non-network yfinance errors (e.g. unexpected dict shape); narrow _RETRY_EXCEPTIONS covers transient network; both logged as WARNING then retry."
metrics:
  duration: "~9min"
  completed: "2026-05-16"
  tasks: 2
  files: 2
---

# Phase 38 Plan 03: news_fetcher.py — I/O Adapter Summary

yfinance news I/O adapter with dual-schema normalisation, title_hash for dedup and dismiss-by-hash, JSON-date-field daily cache, market_id allowlist path-traversal gate, URL scheme validation, XSS pass-through (render-time-only escape), and SSRF closure (zero server-side link prefetch).

## What Was Built

### news_fetcher.py (Task 2 — GREEN)

410 LOC, 2-space indent. Peer of `data_fetcher.py`.

**NewsItem TypedDict:**
```
title: str       — verbatim from yfinance (no html.escape at fetch layer)
url: str         — scheme-validated (https/http) or '' (javascript:/data: rejected)
publisher: str   — displayName (post) or publisher field (pre)
pub_date: str    — pubDate string (post) or ISO 8601 UTC from unix ts (pre)
title_hash: str  — sha256(normalise(title))[:16] — 16 hex chars, always present
```

**Title hash normalisation (`_normalise_title_for_hash`):**
`title.strip().lower()` then `re.sub(r'\s+', ' ', ...)`. Stable across leading/trailing whitespace, internal whitespace collapsing, and case. Input to `hashlib.sha256(...).hexdigest()[:16]`.

**Schema dispatch (`_normalise_item`):**
- `'content' in raw` → `_normalise_post_055` (post-0.2.55 content envelope)
- `'uuid' in raw` (and no `'content'`) → `_normalise_pre_055` (flat uuid schema)
- Otherwise → `None`

**URL fallback chain (post-0.2.55):**
`c.get('clickThroughUrl') or c.get('canonicalUrl') or {}` — if clickThroughUrl is a truthy dict, it wins; scheme validation then runs on its `url` field.

**Cache TTL semantics:**
Sidecar: `news_cache_{market_id}.json`. Envelope: `{'date': 'YYYY-MM-DD', 'headlines': [...]}`. `_load_cache` checks `envelope.get('date') != date.today().isoformat()` — filesystem mtime is NEVER consulted. `_write_cache` uses `tempfile.NamedTemporaryFile(dir=parent, ...) + os.fsync + os.replace` (mirrors `state_manager/io.py::_atomic_write_unlocked`).

**market_id allowlist gate:**
`_is_valid_market_id`: `market_id in _VALID_MARKETS and re.fullmatch(r'[A-Z0-9_]{2,16}', market_id)`. `_cache_path` raises `ValueError` on miss — called BEFORE any `Path` construction. `fetch_news` logs WARNING and returns `[]` for unknown market without touching yfinance.

**Dedup:** seen-set on `title_hash` in `fetch_news`; first occurrence preserved; slice to `max_items` after dedup.

**Retry loop:** narrow-catch `(requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError)` plus broad `Exception` for unexpected yfinance errors; `backoff_s` sleep between attempts; returns `[]` after retries exhausted.

### tests/test_news_fetcher.py (Task 1 — RED)

31 tests covering the full contract:

| Group | Tests |
|-------|-------|
| NewsItem shape + title_hash | 4 (field present, 16-hex, whitespace/case stable, distinguishes titles) |
| Schema normalisation | 5 (post055 shape, pre055 shape, None on empty title, unknown shape, dedup) |
| URL scheme validation | 7 (https/http accepted, javascript/data/relative/empty rejected, normalise strips js url) |
| market_id allowlist | 3 (rejects traversal, rejects traversal chars, unknown market no yfinance call) |
| Cache TTL (JSON date field) | 6 (cache hit ignores old mtime, stale date refetches, envelope unpacked, miss writes envelope, atomic write, corrupt JSON refetches) |
| XSS / SSRF | 3 (xss survives normaliser, no server-side prefetch AST, no forbidden imports AST) |
| Network resilience | 1 (retries exhausted → []) |
| URL fallback chain | 2 (None clickThrough → canonical, both missing → '') |

## Security Properties

| Threat | Mitigation | Test |
|--------|-----------|------|
| T-38-03-01 XSS via title | Title verbatim at fetch; html.escape at render (Plan 04) | test_xss_headline_survives_normaliser |
| T-38-03-02 SSRF via URL | Zero HTTP calls to headline URLs in news_fetcher.py | test_no_server_side_url_prefetch (AST) |
| T-38-03-03 javascript:/data: in href | _validate_url_scheme rejects; Plan 04 escapes href | test_url_scheme_javascript_rejected + test_normalise_strips_javascript_url |
| T-38-03-04 Path traversal via market_id | _is_valid_market_id allowlist + regex; _cache_path raises ValueError | test_cache_path_rejects_unknown_market + test_cache_path_rejects_traversal_chars |
| T-38-03-05 Hung yfinance call | ReadTimeout narrow-catch + backoff retry | test_fetch_news_returns_empty_on_retries_exhausted |
| T-38-03-07 Cache poisoning | _normalise_item only persists typed NewsItem fields | (structural — unknown raw keys discarded) |
| T-38-03-08 Concurrent cache write | tempfile + os.replace atomic | test_cache_write_is_atomic |
| T-38-03-09 Stale cache via mtime | JSON date field sole authority; mtime never read | test_cache_hit_uses_json_date_field_not_mtime |

## Verification

1. `.venv/bin/pytest -x --tb=short tests/test_news_fetcher.py` — 31 passed
2. `.venv/bin/pytest -x --tb=short tests/test_signal_engine.py::TestDeterminism` — 79 passed (test_news_modules_exist_after_wave2 now PASSES; AST hex guard green)
3. Full suite: 2373 passed, 1 skipped, 1 xfailed, 3 xpassed, 0 failures
4. `wc -l news_fetcher.py` → 410 (≤500)
5. No `st_mtime`, `os.path.getmtime`, `requests.get/post`, `urllib.request.urlopen`, `httpx.*` in news_fetcher.py
6. `_compute_title_hash('  RBA Cuts Rates  ') == _compute_title_hash('rba cuts  rates')` — stable
7. `_validate_url_scheme('javascript:alert(1)') == ''` — rejected
8. `_cache_path('../etc/passwd')` raises `ValueError` — traversal closed

## Deviations from Plan

None — plan executed exactly as written.

The one clarification needed (not in plan spec): when `clickThroughUrl` is a truthy dict but its `url` field fails scheme validation, the result is `''` — canonicalUrl is NOT tried as fallback in that case. This matches the plan's `url_obj = c.get('clickThroughUrl') or c.get('canonicalUrl')` logic (the `or` short-circuits on the truthy dict), and the test `test_normalise_strips_javascript_url` documents this behaviour explicitly.

## Known Stubs

None. news_fetcher.py is a pure I/O adapter — no UI rendering, no placeholder data.

## Threat Flags

None beyond the plan's declared threat model (all T-38-03-* mitigated above).

## Self-Check: PASSED

- `news_fetcher.py` — exists, 410 LOC ≤500, all named functions present (grep verified)
- `tests/test_news_fetcher.py` — exists, 31 tests collected and passed
- `test_news_modules_exist_after_wave2` — PASSED (both news_filter.py + news_fetcher.py now on disk)
- `test_forbidden_imports_absent` (parametrized NEWS_FETCHER_PATH) — PASSED
- `test_phase2_hex_modules_no_numpy_pandas` (parametrized NEWS_FILTER_PATH) — PASSED
- Commits: a50afcc (Task 1 RED), 6438190 (Task 2 GREEN) — both in git log
