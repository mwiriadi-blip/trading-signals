# Phase 43: Codebase Improvement Sweep — Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Addresses 12 improvement items surfaced by the 2026-05-16 codebase map review. Grouped into four waves:

- **Wave A (HIGH — F&F blockers):** crash-email data leak, news-fetch failure bypass, float monetary type
- **Wave B (MEDIUM — reliability/performance):** news caching, mutate_state re-entrancy guard, trade-log truncation
- **Wave C (LOW — housekeeping):** dashboard_legacy removal, dashboard shim elimination, oversized file splits
- **Wave D (LOW — CI/quality):** CI pipeline, ruff indent config, IndicatorFloat/MoneyDecimal type aliases

Waves A and B are blockers for F&F deployment. Waves C and D are standalone cleanup.

</domain>

<decisions>
## Implementation Decisions

### Wave A

- **D-01:** `render_crash_email` in `notifier/templates.py` must redact all per-user trade data from the state dict before serialising to email body. Unskip `test_crash_email_body_redacts_other_users` as the acceptance gate.

- **D-02:** `news_fetcher.py` retry exhaustion must return a typed `NewsResult(items: list, error: str | None)` rather than bare `[]`. All callers updated. `has_critical_event` must propagate error sentinel so UI can surface fetch failures.

- **D-03:** `system_params.INITIAL_ACCOUNT` changes from `float` to `Decimal`. Cast site in `interactive.py:235` updated accordingly.

### Wave B

- **D-04:** News caching: per-market JSON sidecar files (`news_cache_<market>.json`) already exist from Phase 38. Phase 43 adds out-of-band refresh in `scheduler_driver.py` and serves stale on fetch failure. Renderer serves cached data; live fetch only on cache miss.

- **D-05:** `mutate_state` re-entrancy guard: thread-local flag raises `RuntimeError('mutate_state is not re-entrant')` immediately on nested call. Better than silent deadlock.

- **D-06:** Trade log truncation: dashboard renders last 200 rows; full log accessible via `/admin/trades/full` endpoint.

### Wave C

- **D-07:** `dashboard_legacy/` — grep confirms zero production imports before deletion. Remove entire directory.

- **D-08:** `dashboard.py` shim — replace `import dashboard` in `daily_run_helpers.py:53` with direct `dashboard_renderer` import.

- **D-09:** `dashboard_renderer/assets.py` (904L) — extract CSS/JS/HTML fragments to `dashboard_renderer/static/` directory. Load at module init.

- **D-10:** `web/routes/dashboard/__init__.py` (682L) — split into `_cache.py`, `_routes.py`, `_helpers.py`.

### Wave D

- **D-11:** Add `.github/workflows/ci.yml` running `pytest -x --tb=short` on push/PR. Python 3.13.

- **D-12:** Add `ruff.toml` with `indent-width = 2` so `ruff format` is safe to run. Remove ban from CLAUDE.md.

- **D-13:** Add `IndicatorFloat = float` and `MoneyDecimal = Decimal` type aliases in `system_params.py`. Annotate `signal_engine.py` boundary. Enforce via mypy in CI.

</decisions>
