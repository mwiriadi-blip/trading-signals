# Phase 38: News Integration - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Adds a news feed panel to each market's `/markets/{m}` dashboard page. Fetches up to 5 yfinance headlines per market, caches per-market per-day in a sidecar file, renders XSS-safe with per-user dismiss state. A word-boundary regex classifier triggers a critical-event banner when keywords fire. Signal compute is AST-isolated from all news code.

Files: `news_fetcher.py` (I/O peer of `data_fetcher.py`), `news_filter.py` (pure, AST-hex eligible), `web/routes/news.py`, dashboard news-panel partial.

</domain>

<decisions>
## Implementation Decisions

### News Panel UI

- **D-01:** News panel placed at the **bottom of `/markets/{m}`**, below existing signal/calculator/drift panels. News is supplementary context — doesn't compete with the signal.

- **D-02:** Panel is **collapsible, open by default** — matching the trace panel collapsible pattern already in the codebase. Collapse state stored server-side (not localStorage), consistent with Phase 37 per-user state approach.

- **D-03:** Critical-event banner appears **inside the news panel, above the headlines list** — contextually tied to the news that triggered it. Not a full-width page-level banner.

### Cache Storage

- **D-04:** Daily news cache uses **per-market sidecar files** — e.g., `news_cache_SPI200.json`, `news_cache_AUDUSD.json`. Keeps `state.json` clean (no non-trading data inflating the atomic store). No fcntl contention with the trading state. TTL check: if file mtime date == today, skip fetch.

- **D-05:** Cache file structure: `{"date": "YYYY-MM-DD", "headlines": [...normalised NewsItem dicts]}`. Placed at repo root alongside `state.json` and `auth.json`. If file is missing or date != today, `news_fetcher.py` refetches and overwrites.

### Keyword Lists

- **D-06:** Per-market keyword lists and the dampener allowlist live in **`system_params.py`** — single source of truth per CLAUDE.md convention. `news_filter.py` imports them (e.g., `NEWS_KEYWORDS_SPI200`, `NEWS_KEYWORDS_AUDUSD`, `NEWS_DAMPENER_ALLOWLIST`) just as `signal_engine.py` imports ATR/ADX params.

- **D-07:** Banner threshold is **any single keyword match** (not N-of-M). Maximises recall to meet the ≥0.9 target. False positives are expected; banner copy already says "operator review recommended".

### Dismiss Expiry

- **D-08:** Dismissed headlines **auto-expire daily** — `news_dismissed` in `state['users'][uid]` is scoped to the current cache date. Structure: `{"date": "YYYY-MM-DD", "hashes": ["<title_hash>", ...]}`. On next day's fetch, the date changes and the dismissed set resets automatically. No stale dismissed items accumulate.

- **D-09:** Dismiss UX: **HTMX removes the row immediately** via empty HTML response (reuses the revoke-invite `HX-Reswap` / empty-200 pattern already in the codebase). Server route `POST /news/{market}/dismiss/{hash}` updates `state['users'][uid]['news_dismissed']` via `mutate_state` and returns empty 200.

### Claude's Discretion

- Exact yfinance fixture capture method for pre-0.2.55 vs post-0.2.55 schema normalisation (researcher should verify shape from pinned yfinance 1.2.0 at plan time — roadmap flags this as research-required).
- Whether `news_filter.py` exports a `classify_headline(text: str, market_id: str) -> bool` signature or a batch classifier.
- Exact keyword content for `NEWS_KEYWORDS_SPI200`, `NEWS_KEYWORDS_AUDUSD`, `NEWS_DAMPENER_ALLOWLIST` — researcher defines initial set and validates against 30-headline fixture to meet precision ≥0.7 / recall ≥0.9.
- Collapse state field name in `state['users'][uid]` (e.g., `news_panel_collapsed`).
- Whether the sidecar cache files are written atomically (tempfile + rename, mirroring `state_manager/io.py`) or simple `json.dump` — researcher should recommend given the shared-read / daily-write access pattern.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §NEWS-01–NEWS-04 — 4 requirements, acceptance criteria, and out-of-scope exclusions (news never influences signal vote)
- `.planning/ROADMAP.md` §Phase 38 — Goal, success criteria, plan-time verification flags (yfinance schema drift, both-shape fixtures)

### Architecture
- `CLAUDE.md` §Architecture — Hex-lite layer table; `news_fetcher.py` must be I/O peer of `data_fetcher.py`; `news_filter.py` must be in `_HEX_PATHS_STDLIB_ONLY`
- `CLAUDE.md` §Key Conventions — `system_params.py` single source of truth, `mutate_state()` only for state writes, 2-space indent
- `.planning/codebase/ARCHITECTURE.md` — Component responsibilities; hex boundary enforcement via AST regressions
- `data_fetcher.py` — Pattern reference for yfinance I/O adapter (retry loop, narrow-catch, lazy import via `_get_yf()`)

### Prior Phase Decisions (relevant carry-forwards)
- `.planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-CONTEXT.md` — D-16/D-17: `state['users'][uid]` sub-dict scoping pattern; `mutate_state` W3 invariant discipline

### Testing
- `.planning/codebase/TESTING.md` — AST import regression pattern; both-shape fixture pattern

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `web/routes/invite/` — HTMX empty-200 row-removal pattern (revoke invite returns empty HTML; HTMX removes row). Direct model for dismiss route.
- `data_fetcher.py::_get_yf()` — Lazy import pattern for yfinance. `news_fetcher.py` should use the same `_get_yf()` accessor to avoid duplicating the lazy-import boilerplate.
- `state_manager/io.py::_atomic_write` — Atomic tempfile + fsync + os.replace pattern. Cache file writes should mirror this if researcher deems it worth it.
- Trace panel collapsible — existing collapse/expand pattern with server-side state; researcher should identify the exact implementation to replicate for the news panel.

### Established Patterns
- **`mutate_state()` only** for `state.json` writes — `news_dismissed` update goes through `mutate_state`, never direct `save_state`.
- **`system_params.py` constants** — all new keyword/threshold constants go here.
- **Jinja2 `autoescape=True`** — already enforced app-wide; XSS protection is structural, not per-template.
- **`rel="noopener noreferrer"`** — must be on every outbound link (headline titles); no server-side link prefetch (SSRF closed by render-only).
- **`register(app)` route pattern** — `web/routes/news.py` registers via `register(app: FastAPI)` function, consistent with `healthz.py`, `markets.py` etc.

### Integration Points
- `/markets/{m}` route — news panel partial injected at bottom of market page template.
- `state['users'][uid]` — `news_dismissed` dict added to per-user sub-dict (alongside `paper_trades`, `email_enabled`, etc.).
- `main.py` / `daily_run.py` — no changes; news fetch is request-time, not daily-run-time.
- AST regression tests — `tests/test_signal_engine.py::TestDeterminism` forbids `news_fetcher`/`news_filter` imports from hex modules; researcher must add both new modules to the forbidden-import test.

</code_context>

<specifics>
## Specific Ideas

- The dismiss route reuses the revoke-invite empty-HTML pattern exactly: `POST /news/{market}/dismiss/{hash}` returns `Response(content="", media_type="text/html")` and the HTMX `hx-target` removes the row.
- Sidecar cache filenames follow `news_cache_{market_id}.json` (e.g., `news_cache_SPI200.json`) at repo root.
- `news_dismissed` shape: `{"date": "YYYY-MM-DD", "hashes": [str, ...]}` in `state['users'][uid]['news_dismissed']`.
- Banner copy (locked by ROADMAP): "Possible market-moving news — operator review recommended".

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 38-news-integration*
*Context gathered: 2026-05-15*
