# Phase 30: File-Size Pre-Split - Context

**Gathered:** 2026-05-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Two workstreams, both must complete before any multi-tenant `user_id` injection lands in Phase 31+:

1. **OPS-01 — File splits.** Behaviour-preserving package splits of the 5 pre-existing 500-LOC violators in `web/routes/`: `trades.py` (746), `dashboard.py` (650), `totp.py` (614), `login.py` (608), `paper_trades.py` (493). Each becomes a package with sub-modules, each daughter ≤500 LOC. Full route + template + test parity verified.

2. **OPS-03 — AST hex blocklist extension.** Extend `FORBIDDEN_MODULES` (and `FORBIDDEN_MODULES_BACKTEST_PURE`) in `tests/test_signal_engine.py` with v1.3 I/O module names: `'web'`, `'news_fetcher'`, `'news_filter'`, `'auth_store'`. Forward-looking guard; none of these modules exist yet so no hex files currently import them — the test passes immediately and guards against future contamination.

**Out of scope:** Any functional changes to route logic. No user_id injection. No new routes. No test rewrites beyond updating imports where packages replace flat files.

</domain>

<decisions>
## Implementation Decisions

### OPS-01: Split structure

- **D-01:** **Package per route file.** `web/routes/trades.py` → `web/routes/trades/` package with `__init__.py`. Matches v1.2 D-09 package precedent (notifier/main/dashboard splits).
- **D-02:** **`register(app: FastAPI)` lives in `__init__.py`.** Callers — `web/app.py` uses `from web.routes import trades as trades_route` then `trades_route.register(app)` — are unchanged. Python package lookup handles `trades` as either module or package transparently.
- **D-03:** **Import surface preserved.** `__init__.py` re-exports everything currently imported by callers and tests. Zero test import path changes required.

### OPS-01: Daughter file naming (by concept)

- **D-04:** `web/routes/trades/` → `_models.py` (Pydantic models + `_OpenConflict` + other exceptions), `_renderers.py` (all render-partial helpers: `_render_position_row_partial`, `_render_close_form_partial`, etc.), `__init__.py` (`register()` + thin glue calling `_renderers.*`).
- **D-05:** `web/routes/login/` → `_renderers.py` (all render helpers: `_render_login_form`, `_render_forgot_2fa_form`, `_render_check_email_page`, `_render_logout_confirmation`, `_log_login_failure`, etc.), `__init__.py` (`register()`).
- **D-06:** `web/routes/totp/` → `_renderers.py` (all render helpers: `_render_qr_data_uri`, `_render_enroll_page`, `_render_enroll_reset_choice_page`, `_render_verify_page`, `_log_totp_failure`, `_derive_device_label`, etc.), `__init__.py` (`register()`).
- **D-07:** `web/routes/dashboard/` → `_renderers.py` (HTML-building sub-functions extracted from inside `register()`; `_is_stale_for` moves here too), `__init__.py` (`register()` calls `_renderers.*` for each section).
- **D-08:** `web/routes/paper_trades/` → `_models.py` (Pydantic models + exceptions: `OpenPaperTradeRequest`, `EditPaperTradeRequest`, `ClosePaperTradeRequest`, `_PaperTradeNotFound`, etc.), `_renderers.py` (render helpers), `__init__.py` (`register()`).

### OPS-01: paper_trades.py (493 LOC)

- **D-09:** **Split now, same package pattern.** It's 7 lines under the cap but OPS-01 explicitly scopes it. Phase 31+ will inject `user_id` into every route, growing it beyond 500. Preemptive split avoids mid-refactor surgery.

### OPS-03: AST blocklist extension

- **D-10:** Add `'web'`, `'news_fetcher'`, `'news_filter'`, `'auth_store'` to the existing `FORBIDDEN_MODULES` frozenset in `tests/test_signal_engine.py`. `_top_level_imports()` already extracts root module names (`from web.routes.dashboard import X` → `'web'`), so adding `'web'` catches the entire `web.*` namespace.
- **D-11:** Also extend `FORBIDDEN_MODULES_BACKTEST_PURE` with the same 4 names. Extend the base `FORBIDDEN_MODULES` frozenset first; `FORBIDDEN_MODULES_BACKTEST_PURE = FORBIDDEN_MODULES | frozenset({'pyarrow'})` picks up the additions automatically — no separate change needed for the backtest set.
- **D-12:** No new frozenset. Extend existing sets in place. The guard fires immediately (none of the v1.3 modules exist yet, so hex files don't import them) — the test passes green from the moment the constants are updated.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and roadmap
- `.planning/ROADMAP.md` — Phase 30 goal, success criteria, and v1.2 D-09 package-split precedent (under Key Decisions)
- `.planning/REQUIREMENTS.md` — OPS-01 (file splits), OPS-03 (AST blocklist); full acceptance criteria

### Files to split (read before planning split boundaries)
- `web/routes/trades.py` — 746 LOC; models + helpers + renderers + `register()` at line 458
- `web/routes/dashboard.py` — 650 LOC; `_is_stale_for` helper + `register()` at line 150 (500 LOC function body)
- `web/routes/totp.py` — 614 LOC; render helpers + `register()` at line 360
- `web/routes/login.py` — 608 LOC; render helpers + `register()` at line 363
- `web/routes/paper_trades.py` — 493 LOC; models + render helpers + `register()` at line 228

### Caller import surface (must remain unchanged)
- `web/app.py` — imports all 5 route modules as `from web.routes import trades as trades_route` etc.; calls `.register(app)`. Package conversion must not break this.
- `web/services/trades_service.py`, `web/services/paper_trades_service.py`, `web/services/dashboard_service.py`, `web/services/totp_service.py` — also import the route modules directly.

### AST test (read before extending blocklists)
- `tests/test_signal_engine.py` — `FORBIDDEN_MODULES` frozenset at line 493; `FORBIDDEN_MODULES_BACKTEST_PURE` at line 605; `_top_level_imports()` at line 626; `test_forbidden_imports_absent` at line 787.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_top_level_imports(source_path)` in `tests/test_signal_engine.py:626` — already extracts root module names from AST; no changes needed to this function for D-10.
- `FORBIDDEN_MODULES` frozenset at line 493 — extend in place with 4 new names.
- `FORBIDDEN_MODULES_BACKTEST_PURE` at line 605 — defined as `FORBIDDEN_MODULES | frozenset({'pyarrow'})`; extending the base set is sufficient, no change to the backtest constant's definition needed.

### Established Patterns
- v1.2 D-09 package splits (notifier/, main/, dashboard/) — largest daughter was 347 LOC. Same approach here: `__init__.py` owns `register()`, sub-modules hold private helpers.
- `register(app: FastAPI)` convention in every route file — all callers use `module.register(app)`. Package `__init__.py` must export this function at the same path.
- `_private` prefix convention for internal helpers — all private functions already use `_` prefix; daughter files follow the same convention.

### Integration Points
- `web/app.py:40-51` — the 5 route modules are imported and registered here; Python package import is transparent when `__init__.py` exports `register`.
- `web/services/*.py` — 4 service files also import route modules directly; same package transparency applies.
- Existing test files (e.g., `tests/test_routes_trades.py`) import from these modules; `__init__.py` re-exports preserve import paths.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches within the package-per-route pattern decided above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 30-File-Size-Pre-Split*
*Context gathered: 2026-05-10*
