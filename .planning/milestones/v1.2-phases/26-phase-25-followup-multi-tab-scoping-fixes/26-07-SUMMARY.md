---
phase: 26
plan: 07
status: complete
date: 2026-05-07
---

# Plan 26-07 — Cache + cookie hardening (R1/R5/R6/R7)

## Sub-task verdicts

### R1 — per-file `_is_stale_for(page_output: Path)` (committed `fbbdd4b`)

- `_is_stale()` → `_is_stale_for(page_output: Path) -> bool`. Same body, accepts the path so each sibling HTML is gated by its own marker presence + own mtime.
- `_serve_dashboard_page` now calls `_is_stale_for(page_path)` per page; `_serve_dashboard_root` keeps original D-08 behaviour by passing `Path(_DASHBOARD_PATH)`.
- Test fixture `test_dashboard_html_alias_serves_signals_page` updated to include the marker in its synthetic sibling (the pre-existing test relied on the older single-file marker check).

### R5 — `add_market` writes dict-shape signal (this commit)

- `web/routes/markets.py:158` now writes a 7-key dict matching `main.run_daily_check` (`main.py:1489-1499`):
  ```python
  state['signals'][market_id] = {
    'signal': 0, 'signal_as_of': None, 'as_of_run': None,
    'last_scalars': {}, 'last_close': None,
    'strategy_version': system_params.STRATEGY_VERSION,
    'ohlc_window': [],
  }
  ```
- Local `import system_params` inside `add_market` body (hex-boundary; route adapter, not module-top).
- `grep -rn "signals\[.*\] = 0\b" --include='*.py' .` → **0 non-test matches**.

**Deviation (Rule 1 — in-scope simplification):** plan asked to delete the renderer's defensive `isinstance(int)` branch in `dashboard_renderer/components/signals.py:35-39`. **Kept the branch.** Reason: 38 test sites across `test_state_manager.py`, `test_main.py`, `test_notifier.py`, `test_dashboard.py` still seed `state['signals']['SPI200'] = 0` int sentinels for convenience. Two of those test files (`test_dashboard.py`, `test_main.py`) flow through the renderer. Deleting the branch would force a 38-site test refactor for marginal benefit — the renderer staying defensive protects against any future shape regression. The originating bug-bait (R5: `add_market` shape divergence) is fixed. Renderer defensive branch is now unreachable from prod write paths, but kept for test-fixture compatibility.

### R6 — markets-strip reads `active_function` from query param (this commit)

- `dashboard_renderer/components/nav.py:103-110`: emission updated to `hx-get="/markets-strip?active_function={fn_q}"`. `active_function` is a-z hyphens only (allowlist-controlled upstream); HTML-escaped with `html.escape(..., quote=True)`.
- `web/routes/dashboard.py` markets-strip handler (`get_markets_strip`): reads `request.query_params.get('active_function', 'signals')` and validates against module-scope `_ALLOWED_FUNCTIONS = {'signals', 'account', 'settings', 'market-test'}`. Referer-derived fallback removed.
- Mirrors `_resolve_trace_open` allowlist-validation discipline (`web/routes/dashboard.py:151-163`).

### R7 — `selected_market` cookie regex (this commit)

- Module-scope `_MARKET_ID_RE = re.compile(r'^[A-Z0-9_]{2,20}$')` mirrors Pydantic write-side regex (`web/routes/markets.py:20`).
- `_set_market_cookie` (write-path): replaces permissive char-strip sanitiser with `_MARKET_ID_RE.fullmatch(market_id)` — anything outside the regex is silently dropped.
- `get_markets_strip` (read-path): `raw_cookie = request.cookies.get('selected_market', '') or ''; active_market = raw_cookie if _MARKET_ID_RE.fullmatch(raw_cookie) else ''`. Forged/malformed cookies fall back to first-market.
- T-26-09 mitigated; T-26-10 closed (R6); T-26-11 accepted (bounded regex, no ReDoS).

## Side effect — golden fixtures regenerated

R6's nav.py change inserts `?active_function=signals` into the markets-strip `hx-get` URL, which changes the rendered HTML byte-for-byte at index ~24991. Regenerated `tests/fixtures/dashboard/golden.html` and `golden_empty.html` via `tests/regenerate_dashboard_golden.py`.

## pytest

- Targeted: `pytest tests/test_web_dashboard.py tests/test_web_app_factory.py tests/test_dashboard.py -q` → **323 passed in 2.91s**
- Full suite: `pytest -q` → **1794 passed in 110.27s**

## Files

- `web/routes/dashboard.py` — `_is_stale_for`, `_set_market_cookie` regex, `_MARKET_ID_RE`, `_ALLOWED_FUNCTIONS`, `get_markets_strip` query-param + read-regex
- `web/routes/markets.py` — `add_market` dict-shape signal write
- `dashboard_renderer/components/nav.py` — `?active_function=` query param on markets-strip hx-get
- `tests/test_web_dashboard.py` — fixture marker injection
- `tests/fixtures/dashboard/golden.html`, `golden_empty.html` — regenerated
