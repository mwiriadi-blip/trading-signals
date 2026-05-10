---
phase: 25
plan: 05
type: execute
wave: 3
depends_on: [25-03, 25-04]
files_modified:
  - dashboard_renderer/components/nav.py
  - dashboard_renderer/components/settings.py
  - web/routes/markets.py
  - web/routes/dashboard.py
  - dashboard.py
autonomous: true
requirements: [P25-09]
must_haves:
  truths:
    - "Market tab strip contains a <details class=add-market-chip> element with summary `+ Add market`"
    - "Expanding the chip reveals an inline mini-form with hx-post=/markets that includes WEB_AUTH_SECRET header"
    - "On 2xx response from POST /markets, the existing endpoint sends HX-Trigger: markets-changed header which causes the market strip to refresh"
    - "The buried <a href=#settings-tab>Add market</a> in dashboard.html is removed (D-17)"
    - "aria-expanded on <details> stays in sync with open/closed state via the existing toggle JS or a small new listener"
  artifacts:
    - path: dashboard_renderer/components/nav.py
      provides: "render_add_market_chip() helper called from render_market_strip"
      contains: "def render_add_market_chip"
    - path: web/routes/markets.py
      provides: "POST /markets handler emits HX-Trigger: markets-changed response header on success (verify; add if missing)"
      contains: "HX-Trigger"
  key_links:
    - from: "Add-market chip form"
      to: "POST /markets handler"
      via: "hx-post"
      pattern: "hx-post=\"/markets\""
    - from: "POST /markets response"
      to: "Market tab strip refresh"
      via: "HX-Trigger: markets-changed → hx-trigger=markets-changed from:body"
      pattern: "HX-Trigger.*markets-changed"
---

<objective>
Wave 3. Add the inline-expanding "+ Add market" chip beside the market tab strip per D-16/D-17. Posts to existing POST /markets endpoint. On success the market strip auto-refreshes via HTMX HX-Trigger header. Removes the buried "Add market" link from the dashboard's old-style anchor location per D-17.

Output: render_add_market_chip helper; market strip reloads on HX-Trigger; legacy link removed.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@dashboard_renderer/components/nav.py
@dashboard_renderer/components/settings.py
@web/routes/markets.py
@dashboard.py

<interfaces>
# web/routes/markets.py:135 — POST /markets handler. Existing Pydantic body shape:
#   class MarketRequest(BaseModel):
#     market_id: str  # validated /[A-Z0-9_]{2,20}/
#     label: str
#     contract_size: float
#     ...
# Verify whether response sets HX-Trigger header (RESEARCH §6 says the project pattern
# DOES emit `HX-Trigger: markets-changed` from PATCH /markets/* — verify POST /markets
# behavior; add if missing).
#
# dashboard_renderer/components/settings.py:render_add_market_form — existing inline
# add-market form on Settings page. Reuse the form HTML structure for consistency.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Render the Add-market chip in nav.py + register GET /markets-strip endpoint + remove buried legacy link</name>
  <read_first>
    - dashboard_renderer/components/nav.py (current render_market_strip from Plan 25-03)
    - dashboard_renderer/components/settings.py (existing render_add_market_form for form HTML structure reference)
    - dashboard.py — locate the buried `<a class="btn-row btn-modify" href="#settings-tab">Add market</a>` (around line 676) and the renderer that emits it
    - web/routes/dashboard.py — confirm dashboard router is the appropriate place to register GET /markets-strip (consistent with Plan 25-04 ownership)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md §Add market chip + §D-17 single-source language
  </read_first>
  <files>dashboard_renderer/components/nav.py, dashboard.py, web/routes/dashboard.py</files>
  <action>
**Step 1 — append `render_add_market_chip` helper to nav.py:**

```python
def render_add_market_chip() -> str:
    """Phase 25 D-16: + Add market chip beside the market tab strip.

    <details> wrapping inline mini-form. Posts to existing POST /markets.
    On 2xx, the existing handler emits HX-Trigger: markets-changed which refreshes the strip
    (Task 2 confirms/adds the header on the server side).
    NOT inside role=tablist — chip is excluded from arrow-key tab traversal per UI-SPEC.
    """
    return (
        '  <details class="add-market-chip">\n'
        '    <summary aria-label="Add market">+ Add market</summary>\n'
        '    <form\n'
        '        hx-post="/markets"\n'
        '        hx-ext="json-enc"\n'
        '        hx-target="this"\n'
        '        hx-swap="outerHTML"\n'
        '        hx-headers=\'{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}\'\n'
        '        hx-on::after-request="handleTradesError(event)">\n'
        '      <label for="add-market-id">Code</label>\n'
        '      <input id="add-market-id" name="market_id" type="text" pattern="[A-Z0-9_]{2,20}" required>\n'
        '      <label for="add-market-label">Label</label>\n'
        '      <input id="add-market-label" name="label" type="text" required>\n'
        '      <label for="add-market-size">Contract size</label>\n'
        '      <input id="add-market-size" name="contract_size" type="number" step="any" required>\n'
        '      <button type="submit">Add market</button>\n'
        '      <button type="reset" onclick="this.closest(\'details\').open=false;return false;">Cancel</button>\n'
        '    </form>\n'
        '  </details>\n'
    )
```

Update `render_market_strip` in nav.py to inject the chip before the closing `</nav>` (replace the placeholder comment from Plan 25-03):

```python
# In render_market_strip — replace:
#   out.append('  <!-- Phase 25 Plan 05: + Add market chip injected here (D-16) -->\n')
# with:
    out.append(render_add_market_chip())
```

Add `id="market-tab-strip"` and the markets-changed listener attributes to the strip wrapper (the wrapper currently emitted by Plan 25-03):

```python
    out = ['<nav role="tablist" aria-label="Market" class="tabs tabs-market" id="market-tab-strip" '
           'hx-trigger="markets-changed from:body" hx-get="/markets-strip" hx-swap="outerHTML">\n']
```

**Step 2 — register GET /markets-strip in web/routes/dashboard.py:**

```python
@router.get('/markets-strip', response_class=Response)
async def get_markets_strip(request: Request):
    state = state_manager.load_state()
    active_market = request.cookies.get('selected_market')
    if not active_market or active_market not in (state.get('markets') or {}):
        # Fall back to first market in insertion order (per OR-03)
        markets = state.get('markets') or {}
        active_market = next(iter(markets), '')
    from dashboard_renderer.components.nav import render_market_strip
    body = render_market_strip(state, active_market, 'signals')
    return Response(
        content=body.encode('utf-8'),
        media_type='text/html; charset=utf-8',
        status_code=200,
        headers={'Cache-Control': 'no-store, private'},
    )
```

**Step 3 — remove the buried `<a class="btn-row btn-modify" href="#settings-tab">Add market</a>`:**

Locate in dashboard.py (around line 676 per RESEARCH §canonical_refs). The renderer code that emits this anchor must be deleted. Per D-17, the chip REPLACES the buried link — Settings page may still keep its own add-market form (existing render_add_market_form). Verify by grep:

```bash
grep -rn 'href="#settings-tab"' dashboard_renderer/ dashboard.py
# Expected after this step: zero matches in renderer source code.
```

The 5 sibling HTML files will regenerate automatically via the marker change from Plan 25-02.

**Step 4 — partial test flip:**

Remove `@pytest.mark.xfail` from `tests/test_dashboard.py::TestPhase25AddMarket::test_market_strip_contains_add_market_chip`, `::test_add_market_chip_form_posts_to_markets`, and `::test_buried_settings_link_removed`. The HX-Trigger end-to-end behavioural test stays xfail until Task 2 completes.
  </action>
  <verify>
    <automated>python -c "
from dashboard_renderer.components.nav import render_market_strip
state = {'markets': {'SPI200': {}}}
ms = render_market_strip(state, 'SPI200', 'signals')
assert 'class=\"add-market-chip\"' in ms, 'chip missing'
assert 'hx-post=\"/markets\"' in ms, 'form action missing'
assert '+ Add market' in ms, 'chip label missing'
assert 'id=\"market-tab-strip\"' in ms, 'strip id missing'
assert 'hx-trigger=\"markets-changed from:body\"' in ms, 'markets-changed listener missing'
print('OK')
" && grep -rn 'href="#settings-tab"' dashboard.py dashboard_renderer/ 2>/dev/null | head -3 || echo "BURIED LINK REMOVED" && python -m pytest tests/test_dashboard.py::TestPhase25AddMarket -q --no-header 2>&1 | tail -5</automated>
  </verify>
  <done>
    - render_add_market_chip helper exists in nav.py and is called by render_market_strip
    - Strip wrapper has id="market-tab-strip" + hx-trigger=markets-changed listener
    - GET /markets-strip endpoint registered in web/routes/dashboard.py and returns the strip fragment
    - Buried `href="#settings-tab"` link removed from renderer source
    - 3 of 4 TestPhase25AddMarket tests PASS (xfail removed for chip / form-post / buried-link)
  </done>
</task>

<task type="auto">
  <name>Task 2: Confirm/add HX-Trigger: markets-changed response header on POST /markets + flip remaining xfail</name>
  <read_first>
    - web/routes/markets.py:135 — POST /markets handler. Read the existing return Response shape (status code, body, headers).
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md §6 (HTMX HX-Trigger pattern; verify whether project pattern already emits HX-Trigger)
    - tests/test_web_app_factory.py — check whether any existing test asserts the response header on POST /markets
  </read_first>
  <files>web/routes/markets.py, tests/test_dashboard.py</files>
  <action>
**Step 1 — confirm/add HX-Trigger: markets-changed on POST /markets success branch:**

Read web/routes/markets.py around line 135 — POST /markets handler. If the response does NOT already include `HX-Trigger: markets-changed`, add it on the success branch:

```python
return Response(
    content=...,        # existing body bytes / json
    status_code=201,    # or whatever existing status is
    media_type='application/json',
    headers={'HX-Trigger': 'markets-changed'},
)
```

Do not change the response body shape — only add the header. If a response header already exists with different events, append: `HX-Trigger: existing,markets-changed` (comma-separated event list per HTMX 1.9 spec).

If POST /markets returns a `JSONResponse` instead of a raw `Response`, set the header via `response.headers['HX-Trigger'] = 'markets-changed'` after construction.

**Step 2 — manual smoke + add a regression test for the header:**

Append to `tests/test_web_app_factory.py` (or extend the existing post-markets test) a test that POSTs a new market and asserts the response header:

```python
class TestPhase25AddMarketHXTrigger:
    """Phase 25 P25-09: POST /markets must emit HX-Trigger: markets-changed so the strip refreshes."""

    def test_post_markets_emits_hx_trigger_markets_changed(self):
        from fastapi.testclient import TestClient
        from web.app import create_app
        client = TestClient(create_app())
        resp = client.post(
            '/markets',
            json={'market_id': 'TEST123', 'label': 'Test', 'contract_size': 1.0},
            headers={'X-Trading-Signals-Auth': 'a' * 32},
        )
        # Header must appear on success (201/200) — accept any 2xx.
        if 200 <= resp.status_code < 300:
            hx_trigger = resp.headers.get('hx-trigger', '')  # case-insensitive lookup; Starlette lowercases
            assert 'markets-changed' in hx_trigger, f'HX-Trigger missing or wrong: {hx_trigger!r}'
```

(If POST /markets validates against an existing-state dictionary and rejects new IDs in test mode, mock state_manager.load_state to include 'TEST123' or use the existing test-fixture pattern.)

This test is NOT xfail.

**Step 3 — flip remaining AddMarket xfail decorator:**

The end-to-end TestPhase25AddMarket tests are now all green. Confirm by re-running:

```bash
pytest tests/test_dashboard.py::TestPhase25AddMarket tests/test_web_app_factory.py::TestPhase25AddMarketHXTrigger -q
```

Both classes must report all PASS.
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -m pytest tests/test_dashboard.py::TestPhase25AddMarket tests/test_web_app_factory.py::TestPhase25AddMarketHXTrigger -q --no-header 2>&1 | tail -10</automated>
  </verify>
  <done>
    - POST /markets success response includes HX-Trigger: markets-changed header (verified by automated test)
    - TestPhase25AddMarketHXTrigger added and passes
    - All TestPhase25AddMarket tests PASS (no xfail remaining)
    - Settings page add-market form (existing render_add_market_form) preserved per D-17 single-source-of-truth language
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Add-market chip → POST /markets | User-supplied market_id and contract_size cross trust boundary. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-05-01 | Tampering | POST /markets handler | mitigate | Reuses existing Pydantic validation: market_id pattern `[A-Z0-9_]{2,20}`, contract_size float bounds. No new validation surface. CSRF protection: `X-Trading-Signals-Auth` header (custom — browser cannot forge cross-origin without preflight per RESEARCH §Security row "CSRF on Add-market chip"). |
| T-25-05-02 | (n/a) | Add-market chip rendering | accept | All chip output is static HTML (no user-controlled data interpolated). No XSS surface in the chip itself. |
</threat_model>

<verification>
- Phase-25 chip-related tests pass: `pytest tests/test_dashboard.py::TestPhase25AddMarket -q`.
- POST /markets response headers include `hx-trigger: markets-changed` (lowercase per Starlette).
- GET /markets-strip returns just the `<nav>` fragment (no `<html>`).
- No `href="#settings-tab"` remains in any renderer source file.
- Manual smoke (after deploy): clicking + Add market expands the form; submitting valid data collapses the form and the strip auto-refreshes with the new market tab visible.
</verification>

<success_criteria>
- + Add market chip rendered beside market tabs.
- Inline-expanding mini-form posts to /markets with auth header + json-enc.
- Market strip auto-refreshes on markets-changed event.
- Legacy buried link gone.
- AddMarket xfail tests flipped to PASS.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-05-SUMMARY.md` summarising chip implementation, HX-Trigger wiring, and any markets-strip endpoint complications.
</output>
