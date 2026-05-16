# Codebase Concerns

**Analysis Date:** 2026-05-16

## Tech Debt

**INITIAL_ACCOUNT declared as `float` in system_params:**
- Issue: `system_params.INITIAL_ACCOUNT: float = 10_000.0` — monetary value typed as float, violating the `Decimal` rule.
- Files: `system_params.py:282`, `interactive.py:235` (`fresh_state['account'] = float(initial_account)`)
- Impact: Accumulation of rounding errors if ever used in Decimal arithmetic chains.
- Fix: Change type to `Decimal`, update `interactive.py` and any cast sites.

**`dashboard.py` shim kept alive via local import in `daily_run_helpers.py`:**
- Issue: `dashboard.py` is a 74-line re-export shim. The real code lives in `dashboard_renderer/`. `daily_run_helpers.py:53` does `import dashboard` inside a try block to isolate import errors, coupling two abstraction layers.
- Files: `dashboard.py`, `daily_run_helpers.py:41-60`
- Impact: Any rename of `dashboard_renderer` internals must also update the shim. The shim silently keeps the old module name alive in `sys.modules`.
- Fix: Eliminate shim; import `dashboard_renderer` directly from `daily_run_helpers`.

**`dashboard_legacy/` tombstone module still installed:**
- Issue: `dashboard_legacy/__init__.py` installs a meta-path finder that intercepts `dashboard_legacy.*` imports and re-directs them — exists purely to catch residual usages after Phase 32 migration. No production code imports it.
- Files: `dashboard_legacy/__init__.py`
- Impact: Adds startup overhead (meta-path hook installed at import); stale code left to rot.
- Fix: Remove once all tests confirm zero `from dashboard_legacy import` references.

**`_LAST_LOADED_STATE` stored in `main` module attribute, read via `getattr`:**
- Issue: `state_actions.py:36-44` reads `main._LAST_LOADED_STATE` via `getattr(_main_pkg, ...)` to allow tests to inject state by assigning `main._LAST_LOADED_STATE = X`. This is a testing seam implemented as a module-level global shared between production and test code.
- Files: `state_actions.py:10-44`, `main.py`
- Impact: Any import-order change or `importlib.reload` can reset the singleton. Fragile in concurrent test runs.
- Fix: Replace with a proper injectable dependency (e.g., `StateCache` class passed at construction).

**Mutually recursive `mutate_state` is non-reentrant (documented but unfixed):**
- Issue: `state_manager/__init__.py::mutate_state` uses `fcntl.LOCK_EX`. A closure that calls `mutate_state` again deadlocks forever. The constraint is documented but not enforced.
- Files: `state_manager/__init__.py:mutate_state`, `CLAUDE.md`
- Impact: Any new feature that (1) reads state, (2) calls external action, (3) writes state inside a single callback will deadlock silently.
- Fix: Add a thread-local re-entrancy guard that raises immediately on nested call; prevents silent deadlock.

## Security Considerations

**No CSRF protection on mutating POST/PATCH/DELETE routes:**
- Risk: HTMX sends mutations via POST/PATCH/DELETE. No CSRF token or Double-Submit-Cookie pattern is enforced. Cookies use `SameSite=Strict` (mitigates most CSRF), but `SameSite=Lax` is used on the market-switcher cookie (`web/routes/dashboard/__init__.py:149`).
- Files: `web/routes/markets.py:228,233,238,255`, `web/routes/paper_trades/__init__.py:153,214`, `web/routes/admin/__init__.py:123,192`, `web/routes/news.py:48,92`
- Current mitigation: `SameSite=Strict` on session cookie blocks cross-site form submission on all modern browsers.
- Risk: Subresource attacks from same-site (but different-origin) iframes are not blocked by `SameSite`.
- Recommendation: Add `Origin` or `Referer` header check in middleware for state-mutating routes.

**`selected_market` cookie lacks `HttpOnly` (intentional but documented risk):**
- Issue: `web/routes/dashboard/__init__.py:147-149` — `SameSite=Lax`, no `HttpOnly`. JS-readable by design but increases XSS blast radius.
- Files: `web/routes/dashboard/__init__.py:147-149`
- Risk: If XSS is achieved (e.g., via unsanitized news headline), attacker can read/modify market selection cookie.
- Mitigation: News headline XSS path is guarded by `html.escape` in renderer. Title hashes are validated via `_HASH_RE`. Low practical risk but worth noting.

**Crash-email state body not redacted for multi-user state (deferred):**
- Risk: `notifier/templates.py::render_crash_email` sends full `state` dict to operator email. In multi-user scenario, all users' trade data is in the email body.
- Files: `notifier/templates.py`, `crash_boundary.py`
- Current mitigation: None. Test at `tests/test_tenant_isolation.py::test_crash_email_body_redacts_other_users` is skipped.
- Priority: HIGH — blocks safe F&F deployment.

## Performance Bottlenecks

**News fetched synchronously on every dashboard render:**
- Problem: `dashboard_renderer/components/signals.py:273-296` calls `fetch_news` (HTTP to Yahoo Finance) inside the render path on every page load. No cache.
- Files: `dashboard_renderer/components/signals.py:273-296`, `news_fetcher.py`
- Cause: Phase 38 deferred caching. Current fetch adds ~500ms–1s per market per page load.
- Impact: At >5 concurrent users, Yahoo rate-limit risk. Page TTFB degrades linearly with market count.
- Fix: Write fetched news to per-market JSON cache with 24h TTL; serve stale on fetch failure; refresh out-of-band in `scheduler_driver.py`.

**Trade log grows unbounded in state.json:**
- Problem: `state['trade_log']` has no pagination or pruning. Dashboard embeds full log as HTML rows.
- Files: `dashboard_renderer/components/positions.py`, `web/routes/dashboard/__init__.py`
- Cause: No truncation logic implemented.
- Impact: At >1000 trades, dashboard HTML grows proportionally. TTFB degrades noticeably.
- Fix: Embed last 200 trades; expose `/trades/full` for admin download.

**`state.json` flock serialization limits concurrent write throughput:**
- Problem: Every paper-trade PATCH, news dismiss, and settings change acquires `LOCK_EX` on `state.json`.
- Files: `state_manager/__init__.py::mutate_state`, `state_manager/__init__.py::mutate_user_state`
- Limit: Adequate for <20 F&F users. At 100+ concurrent users, lock wait time dominates.
- Fix path: In-memory cache with TTL for reads; eventually per-user state files.

## Missing Error Handling

**`state_actions.py` swallows `Exception` without logging on two paths:**
- Files: `state_actions.py:42`, `state_actions.py:58`
- Both `except Exception: pass` blocks (or equivalent) around `getattr` fallback logic suppress unexpected errors silently.
- Fix: At minimum log at DEBUG level to aid diagnosis.

**`news_fetcher.py` retry exhaustion returns empty list (silent degradation):**
- Files: `news_fetcher.py:408`
- After all retries fail, returns `[]`. Callers cannot distinguish "no news today" from "network failure". Alert-filtering logic in `news_filter.py` treats both identically.
- Risk: If Yahoo Finance is down, `has_critical_event` will always return False — news-gating on signals is silently bypassed.
- Fix: Return a typed result (`NewsResult(items, error)`) so callers can surface fetch failures in UI.

## Outdated / At-Risk Dependencies

**`ruff==0.6.9` — 2-space indent convention breaks `ruff format`:**
- Issue: CLAUDE.md forbids running `ruff format` because it reflows to 4-space indent. The ruff version is pinned but the formatter is unusable as-is.
- Files: `requirements.txt`, `CLAUDE.md`
- Risk: Any CI step that runs `ruff format` would break the entire codebase style gate. This is a latent footgun for new contributors.
- Fix: Either add `ruff.toml` with `indent-width = 2` so `ruff format` is safe, or add a CI guard that asserts `ruff format` is never called.

**`pyarrow==24.0.0` — major version gap from current (20.x) upstream:**
- Files: `requirements.txt`
- Pyarrow 24.0.0 is significantly ahead of the mainline 18.x LTS stream (as of analysis date). Binary ABI compatibility with other Arrow ecosystem tools is version-sensitive.
- Risk: If pandas or numpy drops Arrow IPC compatibility for this version, backtest parquet cache silently breaks.
- Fix: Pin to a stable release; run `pytest tests/test_backtest_data_fetcher.py` after any pyarrow change.

**`yfinance==1.2.0` + lazy `curl_cffi` bootstrap:**
- Files: `data_fetcher.py:87-95`, `requirements.txt`
- Lazy resolver `_get_yf_rate_limit_error()` re-imports `yfinance.exceptions` on every retry loop. If yfinance moves the exception class, the resolver fails at runtime, not import time.
- Fix: Eagerly resolve the exception class at first `fetch_ohlcv` call and cache; add a startup smoke-test.

## Architectural Violations

**`signal_engine.py` uses `float` for indicator values (intentional but inconsistent with Decimal rule):**
- Issue: `signal_engine.py:285-292` explicitly casts numpy scalars to `float`. The hex-layer rule says "Decimal for all AUD amounts" — signal indicators (ATR, ADX, etc.) are not AUD amounts, so float is correct here. However, the boundary between "indicator float" and "monetary Decimal" is not type-enforced.
- Files: `signal_engine.py:278-295`, `sizing_engine/sizing.py:128`
- Risk: A future developer may pass a signal float directly into a monetary calculation, introducing precision loss.
- Fix: Add type annotations (`IndicatorFloat = float`, `MoneyDecimal = Decimal`) and enforce via mypy.

**`dashboard_renderer/assets.py` at 904 lines — exceeds 500-line convention:**
- Files: `dashboard_renderer/assets.py` (904 lines)
- Contains CSS, JS, and HTML asset strings inline. Splits into logical sections but the file is a maintenance liability.
- Fix: Extract CSS, JS, and HTML fragments to `dashboard_renderer/static/` directory; load at build time.

**`web/routes/dashboard/__init__.py` at 682 lines — exceeds 500-line convention:**
- Files: `web/routes/dashboard/__init__.py` (682 lines)
- Multiple route handlers, cache logic, and rendering helpers mixed in one file.
- Fix: Split into `_cache.py`, `_routes.py`, `_helpers.py` submodules.

## Test Coverage Gaps

**Crash-email multi-user redaction not tested:**
- Files: `tests/test_tenant_isolation.py::test_crash_email_body_redacts_other_users` (skipped)
- `render_crash_email` receives raw state dict; no filtering applied. Skip marker hides the gap.
- Priority: HIGH.

**News fetch failure → signal gating bypass not tested:**
- No test asserts that `has_critical_event` returns a sentinel or raises when `fetch_news` returns `[]` due to network error vs. genuinely empty news day.
- Files: `news_filter.py`, `dashboard_renderer/components/signals.py:296`
- Priority: MEDIUM.

**`toggle-collapse` route has no test for concurrent toggle (race):**
- Files: `tests/test_web_news_routes.py`, `web/routes/news.py:92-120`
- The `mutate_user_state` callback flips a bool atomically under flock, but no test exercises two simultaneous toggles to verify final state is consistent.
- Priority: LOW.

**Legacy signal-shape backward-compat path untested:**
- Files: `daily_run.py:325`, `notifier/formatters.py:306-319`
- Formatters handle both int (legacy) and dict signal shapes. No explicit test of the int-shape fallback path with a live state file.
- Priority: LOW.

---

*Concerns audit: 2026-05-16*
