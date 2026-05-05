---
phase: 25
plan: "04"
subsystem: web_routes
tags: [routes, cookie, htmx, market-scoped, wave-2]
dependency_graph:
  requires: [25-01, 25-02, 25-03]
  provides:
    - "GET /markets/{market_id}/signals|settings|market-test routes"
    - "GET /status-strip stub (Plan 25-06 fills body)"
    - "_MARKET_COOKIE_ATTRS: SameSite=Lax, Secure, Path=/, Max-Age=2592000, no HttpOnly"
    - "_is_htmx_request + _set_market_cookie helpers"
    - "render_dashboard_as_str() in dashboard_renderer/api.py (HTML string, no disk write)"
    - "market_id validated against state['markets']; 404 on miss"
    - "Cache-Control: no-store, private on all market-scoped responses"
  affects:
    - "25-05 (market tab strip now has real route targets)"
    - "25-06 (status-strip stub registered; Plan 06 fills body)"
tech_stack:
  added: []
  patterns:
    - "render_dashboard_as_str(): builds RenderContext + _render_header_and_body, returns HTML string without disk write"
    - "local imports (state_manager, dashboard_renderer.api) preserve hex boundary per Phase 11 C-2"
    - "cookie sanitiser strips ';' and '\"' from market_id before Set-Cookie emission (T-25-04-02)"
    - "HX-Request sniff delegates entirely to render_dashboard(htmx_panel_only=True) — no regex extraction (WARNING 4 resolved)"
key_files:
  created: []
  modified:
    - "web/routes/dashboard.py — 4 new GET routes + _serve_market_scoped_page + _MARKET_COOKIE_ATTRS + _is_htmx_request + _set_market_cookie"
    - "dashboard_renderer/api.py — render_dashboard_as_str() added"
    - "tests/test_web_app_factory.py — xfail removed from TestPhase25MarketRoutes (5 tests) + TestPhase25SelectedMarketCookie (2 tests)"
    - "tests/test_web_dashboard.py — xfail removed from TestPhase25StatusStripEndpoint::test_status_strip_endpoint_returns_200 and ::test_status_strip_endpoint_returns_html_fragment"
decisions:
  - "render_dashboard_as_str() added to dashboard_renderer/api.py instead of making render_dashboard() return string for full-doc case — cleaner contract: existing callers of render_dashboard() are unaffected; new route handler has explicit intent"
  - "Task 1 stub + Task 2 full implementation committed as single atomic commit — both tasks modify the same function in the same file; intermediate stub state would be invalid"
  - "test_status_strip_endpoint_returns_html_fragment xfail also removed — stub satisfies the id=status-strip + no-html assertion; plan said 'leave xfail' but XPASS(strict) = failure"
metrics:
  duration: ~20min
  completed: "2026-05-05"
  tasks: 2
  files: 4
---

# Phase 25 Plan 04: Routes + Cookie Summary

GET /markets/{market_id}/signals|settings|market-test routes registered with market_id validation (404 on miss), selected_market cookie emission (SameSite=Lax, no HttpOnly), HX-Request branching via render_dashboard(htmx_panel_only=True), and /status-strip stub.

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-05-05
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

**Task 1 + Task 2 — market-scoped routes + cookie + HX branching (combined):**

- 3 new GET routes registered in `web/routes/dashboard.py` under the existing `register()` function:
  - `GET /markets/{market_id}/signals`
  - `GET /markets/{market_id}/settings`
  - `GET /markets/{market_id}/market-test`
- `GET /status-strip` stub registered (returns `<div id="status-strip"><!-- Phase 25 Plan 06 implements --></div>`, status 200)
- `_MARKET_COOKIE_ATTRS = '; Max-Age=2592000; Path=/; Secure; SameSite=Lax'` constant (no HttpOnly per D-05)
- `_is_htmx_request(request)`: checks `HX-Request: true` header
- `_set_market_cookie(response, market_id)`: emits `Set-Cookie: selected_market=<safe>` with `_MARKET_COOKIE_ATTRS`; sanitises `;` and `"` from market_id (T-25-04-02)
- `_serve_market_scoped_page(request, market_id, function)`:
  - Validates market_id against `state_manager.load_state()['markets']`; 404 on miss (T-25-04-01)
  - HX-Request path: `render_dashboard(state, htmx_panel_only=True)` → panel-only HTML
  - Full-doc path: `render_dashboard_as_str(state, active_function=..., active_market=...)` → full `<!DOCTYPE html>` response
  - `Cache-Control: no-store, private` on every response (T-25-04-03)
- `render_dashboard_as_str()` added to `dashboard_renderer/api.py`: builds RenderContext + calls `_render_header_and_body` + `_render_single_page_dashboard`, returns HTML string without disk write

**Test gate status:**
- `TestPhase25MarketRoutes`: 5/5 PASS (xfail removed)
- `TestPhase25SelectedMarketCookie`: 2/2 PASS (xfail removed)
- `TestMarketRoutesRegistered`: 6/6 PASS (regression guard — unchanged)
- `TestPhase25StatusStripEndpoint::test_status_strip_endpoint_returns_200`: PASS (xfail removed)
- `TestPhase25StatusStripEndpoint::test_status_strip_endpoint_returns_html_fragment`: PASS (xfail removed)
- `TestPhase25StatusStripEndpoint::test_status_strip_unauthed_returns_401_or_403`: remains xfail (pre-existing NameError `r` vs `resp` in test body; Plan 06 scope)

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1+2 | Routes + cookie + HX branching (atomic) | 961f9f4 | web/routes/dashboard.py, dashboard_renderer/api.py, tests/test_web_app_factory.py, tests/test_web_dashboard.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] render_dashboard_as_str() added to dashboard_renderer/api.py**
- **Found during:** Task 1 implementation — `render_dashboard()` returns `None` for full-doc path (writes to disk via `_atomic_write_html`); route handler needs HTML as string
- **Issue:** Plan's Task 1/2 code expected `render_dashboard(..., htmx_panel_only=False)` to return a string, but the existing function signature has `-> None` for that path
- **Fix:** Added `render_dashboard_as_str()` to `dashboard_renderer/api.py` — builds `RenderContext` and returns HTML string via `_render_header_and_body` without disk write
- **Files modified:** dashboard_renderer/api.py
- **Commit:** 961f9f4

**2. [Rule 1 - Bug] Stray `assert settings['direction_mode'] == 'long_only'` in test**
- **Found during:** Task 2 xfail flip — `settings` undefined in `test_selected_market_cookie_has_lax_samesite_no_httponly` scope → NameError at runtime
- **Issue:** Copy-paste residue from another test; would cause XPASS(strict) failure after xfail removal
- **Fix:** Removed the stray assert line
- **Files modified:** tests/test_web_app_factory.py
- **Commit:** 961f9f4

**3. [Deviation from plan instructions] test_status_strip_endpoint_returns_html_fragment xfail also removed**
- **Plan said:** "Leave xfail on `test_status_strip_endpoint_returns_html_fragment` — Plan 06 ships the body"
- **Actual:** The stub (`<div id="status-strip">...`) satisfies the fragment test assertions (`id="status-strip"` present, no `<html>` tag) → XPASS(strict) = failure if left as xfail
- **Fix:** Removed xfail from both status-strip passing tests
- **Commit:** 961f9f4

## Threat Surface Scan

All five STRIDE mitigations in the plan's `<threat_model>` implemented:
- T-25-04-01 (path injection): market_id validated against `state['markets']`; 404 on miss
- T-25-04-02 (XSS in cookie): `_set_market_cookie` strips `"` and `;` from market_id
- T-25-04-03 (cache poisoning): `Cache-Control: no-store, private` on all market-scoped responses
- T-25-04-04 (auth bypass): routes registered under existing dashboard router gated by AuthMiddleware; no PUBLIC_PATHS additions
- T-25-04-05 (route shadowing): regression guard `test_existing_route_shadowing_regression_still_passes` remains green; new routes are GET (vs PATCH); two-segment paths don't shadow one-segment paths

No new trust boundaries introduced beyond those in the threat model.

## Known Stubs

- `GET /status-strip`: returns placeholder HTML fragment. Plan 25-06 implements the body with `last_run_at`, `last_run_status`, `next_run_at` fields and AWST countdown JS.

## Self-Check

Files exist:
- `web/routes/dashboard.py` — modified (4 new routes + 5 helpers) ✓
- `dashboard_renderer/api.py` — modified (render_dashboard_as_str added) ✓
- `tests/test_web_app_factory.py` — modified (7 xfail decorators removed) ✓
- `tests/test_web_dashboard.py` — modified (2 xfail decorators removed) ✓

Commits exist:
- `961f9f4` ✓

Test gate:
- `TestPhase25MarketRoutes`: 5/5 PASS ✓
- `TestPhase25SelectedMarketCookie`: 2/2 PASS ✓
- `TestMarketRoutesRegistered`: 6/6 PASS ✓

## Self-Check: PASSED
