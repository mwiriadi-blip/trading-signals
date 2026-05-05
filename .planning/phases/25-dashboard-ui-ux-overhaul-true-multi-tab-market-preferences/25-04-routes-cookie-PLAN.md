---
phase: 25
plan: 04
type: execute
wave: 2
depends_on: [25-01, 25-02, 25-03]
files_modified:
  - web/routes/dashboard.py
  - web/routes/markets.py
autonomous: true
requirements: [P25-01, P25-02, P25-15]
must_haves:
  truths:
    - "GET /markets/{market_id}/{function} routes registered for function in {signals, settings, market-test}"
    - "Route registration order preserves the 18ea2c5 fix: literal /markets/settings before /markets/{market_id}"
    - "Unknown market_id returns 404 (not a fallback render of first market)"
    - "Set-Cookie: selected_market=<market_id> emitted on every market-scoped page render with HttpOnly NOT set, SameSite=Lax, Secure, Path=/, Max-Age=2592000"
    - "When request has HX-Request: true, response is panel-only HTML; without it, response is full document (per RESEARCH Pitfall 6)"
  artifacts:
    - path: web/routes/dashboard.py
      provides: "GET /markets/{market_id}/{function} handlers, /status-strip placeholder route (Plan 06 implements body), cookie set helper"
      contains: "_MARKET_COOKIE_ATTRS"
    - path: web/routes/markets.py
      provides: "Existing route ordering preserved; new GET routes from dashboard.py do not shadow"
      contains: "/markets/settings"
  key_links:
    - from: "web/routes/dashboard.py:_serve_dashboard_page"
      to: "Set-Cookie: selected_market response header"
      via: "Response(..., headers={'Set-Cookie': ...})"
      pattern: "selected_market="
    - from: "GET /markets/{market_id}/{function}"
      to: "render_dashboard(active_function=..., active_market=market_id)"
      via: "shared handler"
      pattern: "active_market="
---

<objective>
Wave 2. Register GET /markets/{market_id}/{function} routes for the three market-scoped functions (signals, settings, market-test). Add the selected_market cookie write on every market-scoped page render. Implement HX-Request header sniff so HTMX swaps return panel-only HTML and browser navigations return full document. Validate market_id against state['markets'] and return 404 on miss.

Does NOT implement /status-strip body — that's Plan 25-06. This plan registers the route as a 503 stub so the router has the surface; Plan 06 fills the body.

Output: 3 new GET routes + cookie write + HX-Request branching, all guarded by AuthMiddleware (no PUBLIC_PATHS additions).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@web/routes/dashboard.py
@web/routes/markets.py
@web/routes/login.py
@web/app.py

<interfaces>
# web/routes/login.py:51-52 — cookie attr literal pattern (project canonical):
#   _COOKIE_ATTRS_CREATE = '; Path=/; Secure; HttpOnly; SameSite=Strict'
# Phase 25 introduces _MARKET_COOKIE_ATTRS = '; Max-Age=2592000; Path=/; Secure; SameSite=Lax'
# (NO HttpOnly per D-05 — JS reads cookie from /account)
#
# web/routes/markets.py route ordering (lines 134-176, REQUIRED ORDER):
#   POST /markets                              (literal)
#   PATCH /markets/settings                    (literal — 18ea2c5 fix)
#   PATCH /markets/{market_id}/settings        (dynamic 2-segment)
#   PATCH /markets/{market_id}                 (dynamic 1-segment, MUST be last)
# 
# Phase 25 inserts new GET routes in web/routes/dashboard.py (separate router/registration);
# FastAPI matches across routers in registration order (web/app.py order). Verify the dashboard
# router is registered AFTER markets router (so dashboard's /markets/{m}/{fn} GET does not collide
# with markets' PATCH /markets/{m}). Method differs (GET vs PATCH) so no collision in practice,
# but order discipline still required.
#
# web/routes/dashboard.py existing _serve_dashboard_page (around line 208) — single handler
# that serves any of the 4 page routes. Phase 25 adds _serve_market_scoped_page that wraps it.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Register GET /markets/{market_id}/{function} routes (signals, settings, market-test) + /status-strip stub + market_id validation 404</name>
  <read_first>
    - web/routes/dashboard.py — full file; locate _serve_dashboard_page, _serve_dashboard_content, _serve_dashboard_root, _is_stale (around lines 119-415)
    - web/routes/markets.py — route ordering (134-176); confirm PATCH literal-before-dynamic discipline preserved
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md §4 (route ordering) + §Pattern 2 (handler skeleton)
    - tests/test_web_app_factory.py:344 (route-shadowing regression test — must remain green)
  </read_first>
  <files>web/routes/dashboard.py</files>
  <action>
**Step 1 — register the four new routes in web/routes/dashboard.py:**

Locate the existing `/signals`, `/account`, `/settings`, `/market-test` route handlers (around line 165-204). Add new market-scoped variants. Place the registrations BEFORE any catch-all like `/{path}`. Verify there is no `/markets/{market_id}` GET in dashboard.py that could shadow.

```python
@router.get('/markets/{market_id}/signals', response_class=Response)
async def get_market_signals(request: Request, market_id: str):
    return await _serve_market_scoped_page(request, market_id, 'signals')


@router.get('/markets/{market_id}/settings', response_class=Response)
async def get_market_settings(request: Request, market_id: str):
    return await _serve_market_scoped_page(request, market_id, 'settings')


@router.get('/markets/{market_id}/market-test', response_class=Response)
async def get_market_market_test(request: Request, market_id: str):
    return await _serve_market_scoped_page(request, market_id, 'market-test')


@router.get('/status-strip', response_class=Response)
async def get_status_strip_stub(request: Request):
    """Phase 25 Plan 04 stub. Plan 25-06 fills body."""
    return Response(
        content=b'<div id="status-strip"><!-- Phase 25 Plan 06 implements --></div>',
        media_type='text/html; charset=utf-8',
        status_code=200,
    )
```

Per D-01..D-04 (route registration): the four routes serve the three market-scoped functions plus the status-strip endpoint. The `_serve_market_scoped_page` shared handler is implemented in Task 2.

**Step 2 — add a stub `_serve_market_scoped_page` returning 404 for unknown market_id and 200 for known market_id (no cookie / no HX branching yet — Task 2 wires those):**

```python
async def _serve_market_scoped_page(request, market_id: str, function: str):
    """Phase 25 D-01..D-04: serve a market-scoped page (signals/settings/market-test).
    Validates market_id against state['markets']; 404 on miss.
    Task 2 adds cookie set + HX-Request panel branching.
    """
    state = state_manager.load_state()
    markets = state.get('markets', {}) or {}
    if market_id not in markets:
        return Response(
            content=f'Market not found: {market_id}'.encode('utf-8'),
            status_code=404,
            media_type='text/plain; charset=utf-8',
        )
    from dashboard_renderer.api import render_dashboard
    full_html = render_dashboard(state, now=None, active_function=function, active_market=market_id)
    return Response(
        content=full_html.encode('utf-8'),
        media_type='text/html; charset=utf-8',
        status_code=200,
        headers={'Cache-Control': 'no-store, private'},
    )
```

This calls `render_dashboard(active_function=…, active_market=…)` — the signature added by Plan 25-03 Task 2. Confirms the depends_on: [25-03] ordering.

**Step 3 — verify route ordering against the regression test:**

Run `pytest tests/test_web_app_factory.py::TestMarketRoutesRegistered -q`. The route-shadowing regression test must remain green. If it fails, check that:
1. `/markets/settings` literal PATCH in markets.py is still registered before `/markets/{market_id}` PATCH.
2. The new GET routes in dashboard.py don't introduce a `/markets/{market_id}` GET (only `/markets/{market_id}/{function}` 2-segment paths).
3. FastAPI's path matcher prioritises 2-segment paths over 1-segment for the same prefix.

**Step 4 — flip xfail decorators on the route-existence + 404 + 200-with-auth tests:**

Remove `@pytest.mark.xfail` from `tests/test_web_app_factory.py::TestPhase25MarketRoutes` test methods (`test_market_signals_route_registered`, `test_market_settings_route_registered`, `test_market_market_test_route_registered`, `test_get_market_signals_returns_200_with_auth`, `test_unknown_market_returns_404`). They should now pass.

Do NOT yet flip TestPhase25SelectedMarketCookie (Task 2 ships the cookie write).
  </action>
  <verify>
    <automated>python -m pytest tests/test_web_app_factory.py::TestPhase25MarketRoutes tests/test_web_app_factory.py::TestMarketRoutesRegistered -q --no-header 2>&1 | tail -10</automated>
  </verify>
  <done>
    - 3 new GET routes registered with correct path patterns; /status-strip stub returns 200
    - _serve_market_scoped_page validates market_id (404 on miss); 200 on known market with full HTML
    - TestPhase25MarketRoutes (5 tests) PASS (xfail removed)
    - test_existing_route_shadowing_regression_still_passes remains green
  </done>
</task>

<task type="auto">
  <name>Task 2: Add selected_market cookie write + HX-Request panel-fragment branching using render_dashboard(htmx_panel_only=True)</name>
  <read_first>
    - web/routes/dashboard.py — _serve_market_scoped_page from Task 1
    - web/routes/login.py:51-447 (cookie attr literal pattern)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-03-SUMMARY.md (confirm htmx_panel_only=True flag added to render_dashboard per Plan 25-03 — resolves WARNING 4 by replacing the brittle `re.search(rb'<section id="market-panel"…</section>', …)` regex)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md §5 (cookies) + §Pitfall 6 (HX-Request)
  </read_first>
  <files>web/routes/dashboard.py</files>
  <action>
**Step 1 — add cookie attrs constant near top of web/routes/dashboard.py:**

```python
# Phase 25 D-05: selected_market cookie attrs. NO HttpOnly (JS-readable per D-05).
# SameSite=Lax (UI-state cookie; not session). Secure required by production HTTPS-only deploy.
_MARKET_COOKIE_ATTRS = '; Max-Age=2592000; Path=/; Secure; SameSite=Lax'
```

**Step 2 — add HX-Request sniff and cookie set helpers:**

```python
def _is_htmx_request(request) -> bool:
    """Phase 25 Pitfall 6: HTMX swap requests carry HX-Request: true header."""
    return request.headers.get('HX-Request', '').lower() == 'true'


def _set_market_cookie(response, market_id: str) -> None:
    """Phase 25 D-05: set selected_market cookie on every market-scoped page render.
    Cookie is JS-readable (no HttpOnly) so /account can route to last-selected market.
    """
    if not market_id or len(market_id) > 32:
        return
    safe = market_id.replace('"', '').replace(';', '')  # belt-and-braces; market_id should already be /[A-Z0-9_]+/
    response.headers['Set-Cookie'] = f'selected_market={safe}{_MARKET_COOKIE_ATTRS}'
```

**Step 3 — replace _serve_market_scoped_page body to wire cookie + HX branching via the renderer flag:**

```python
async def _serve_market_scoped_page(request, market_id: str, function: str):
    """Phase 25 D-01..D-05: serve a market-scoped page (signals/settings/market-test).

    Validates market_id against state['markets']; 404 on miss.
    Sets selected_market cookie.
    HX-Request → render_dashboard(htmx_panel_only=True) returns panel-only HTML; otherwise full document.
    """
    state = state_manager.load_state()
    markets = state.get('markets', {}) or {}
    if market_id not in markets:
        return Response(
            content=f'Market not found: {market_id}'.encode('utf-8'),
            status_code=404,
            media_type='text/plain; charset=utf-8',
        )

    htmx = _is_htmx_request(request)

    from dashboard_renderer.api import render_dashboard
    body = render_dashboard(
        state,
        now=None,
        active_function=function,
        active_market=market_id,
        htmx_panel_only=htmx,  # Plan 25-03 added this kwarg; True returns inner panel HTML, False returns full document
    )

    response = Response(
        content=body.encode('utf-8'),
        media_type='text/html; charset=utf-8',
        status_code=200,
    )
    _set_market_cookie(response, market_id)
    response.headers['Cache-Control'] = 'no-store, private'
    return response
```

NOTE: This resolves WARNING 4. The `htmx_panel_only=True` flag is the single, authoritative way to get panel-only HTML; no regex extraction in the route handler. If the flag is missing from `render_dashboard` (Plan 25-03 ship gap), this task fails verification — escalate back to 25-03.

**Step 4 — flip xfail decorators on cookie tests:**

Remove `@pytest.mark.xfail` from `tests/test_web_app_factory.py::TestPhase25SelectedMarketCookie::test_market_route_sets_selected_market_cookie` and `::test_selected_market_cookie_has_lax_samesite_no_httponly`. Run, confirm green.

In `tests/test_web_dashboard.py`, leave xfail on the `TestPhase25StatusStripEndpoint::test_status_strip_endpoint_returns_html_fragment` test — Plan 06 ships the body. Mark `test_status_strip_endpoint_returns_200` as non-xfail (the stub already returns 200).

**Step 5 — manual smoke verification (post-deploy):**

```bash
# Full document
curl -i -H "X-Trading-Signals-Auth: $WEB_AUTH_SECRET" http://localhost:PORT/markets/SPI200/signals | head -20
# Expected: 200, Set-Cookie: selected_market=SPI200; ...; SameSite=Lax; Path=/; Secure (no HttpOnly)
# Body starts with <!DOCTYPE html>

# HTMX panel
curl -i -H "X-Trading-Signals-Auth: $WEB_AUTH_SECRET" -H "HX-Request: true" http://localhost:PORT/markets/SPI200/signals | head -20
# Expected: 200, body has NO <html> tag — panel-only fragment
```
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -m pytest tests/test_web_app_factory.py::TestPhase25SelectedMarketCookie tests/test_web_app_factory.py::TestPhase25MarketRoutes tests/test_web_app_factory.py::TestMarketRoutesRegistered -q --no-header 2>&1 | tail -10 && python -c "
from fastapi.testclient import TestClient
from web.app import create_app
client = TestClient(create_app())
# Full doc
r = client.get('/markets/SPI200/signals', headers={'X-Trading-Signals-Auth': 'a'*32})
assert r.status_code == 200
assert '<!DOCTYPE html>' in r.text or '<html' in r.text.lower(), 'full doc expected'
# HTMX panel-only
r2 = client.get('/markets/SPI200/signals', headers={'X-Trading-Signals-Auth': 'a'*32, 'HX-Request': 'true'})
assert r2.status_code == 200
assert '<html' not in r2.text.lower(), 'panel-only expected — render_dashboard(htmx_panel_only=True) failed'
print('OK')
"</automated>
  </verify>
  <done>
    - _MARKET_COOKIE_ATTRS, _is_htmx_request, _set_market_cookie helpers added
    - _serve_market_scoped_page now sets the selected_market cookie on every market-scoped response
    - HX-Request branching delegates entirely to render_dashboard(htmx_panel_only=True/False) — NO regex extraction (resolves WARNING 4)
    - Cache-Control: no-store, private set on market-scoped responses
    - TestPhase25SelectedMarketCookie tests PASS (xfail removed)
    - HTMX panel response contains no <html> tag; full-document response contains <!DOCTYPE html>
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HTTP request → FastAPI handler | market_id from URL path; user-controllable. |
| State.json read → cookie value emission | server-controlled; market_id has already passed validation. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-04-01 | Tampering (path injection) | _serve_market_scoped_page | mitigate | market_id validated against state['markets'] dict keys; mismatched → 404. FastAPI path matching already rejects URL-encoded `..` and `/`. |
| T-25-04-02 | Tampering (XSS in cookie value) | _set_market_cookie | mitigate | market_id origin is state.json (server-controlled); defensive sanitiser in `_set_market_cookie` strips `"` and `;`. Same approach as login.py existing pattern. |
| T-25-04-03 | Information Disclosure (cache poisoning) | market-scoped responses | mitigate | `Cache-Control: no-store, private` header set on every market-scoped response per RESEARCH §Security row "HTMX swap content cache poisoning". |
| T-25-04-04 | Spoofing (auth bypass) | new GET routes | mitigate | All new routes added under the existing dashboard router which is gated by AuthMiddleware. No PUBLIC_PATHS additions. Verified by `TestPhase25StatusStripEndpoint::test_status_strip_unauthed_returns_401_or_403` (Plan 06 will flip this from xfail). |
| T-25-04-05 | Route shadowing regression | route registration order | mitigate | `tests/test_web_app_factory.py:344` regression guard remains green — Plan 04 only adds GET routes; existing PATCH literal-before-dynamic discipline untouched. |
</threat_model>

<verification>
- TestPhase25MarketRoutes (5 tests) all PASS.
- TestPhase25SelectedMarketCookie (2 tests) all PASS.
- test_existing_route_shadowing_regression_still_passes still PASS.
- The pre-existing PATCH /markets/settings shadowing test (test_web_app_factory.py:344) remains green.
- Curl smoke (manual): `curl -i -H "X-Trading-Signals-Auth: $WEB_AUTH_SECRET" http://localhost:PORT/markets/SPI200/signals` returns 200 + Set-Cookie header.
- Curl with HX-Request: `curl -i -H "X-Trading-Signals-Auth: $WEB_AUTH_SECRET" -H "HX-Request: true" http://localhost:PORT/markets/SPI200/signals` returns panel-only HTML (no <html> tag).
</verification>

<success_criteria>
- GET /markets/{market_id}/signals|settings|market-test routes return 200 with auth.
- Unknown market_id → 404.
- selected_market cookie set with correct attrs (no HttpOnly, SameSite=Lax, Secure, Path=/, Max-Age=2592000).
- HX-Request branching delivers panel-only HTML for swaps, full doc for browser nav.
- /status-strip stub registered (Plan 06 implements body).
- Route-shadowing regression remains green.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-04-SUMMARY.md` documenting route registrations, cookie attrs, and any deviations from the regex-based panel extractor (e.g., if a more robust HTML parser was needed).
</output>
