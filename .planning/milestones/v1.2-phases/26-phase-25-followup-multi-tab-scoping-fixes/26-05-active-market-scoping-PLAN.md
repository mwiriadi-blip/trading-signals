---
phase: 26
plan: 05
type: execute
wave: 2
parallel: true
depends_on:
  - 26-03-failing-test-scaffolding-PLAN.md
files_modified:
  - dashboard.py
  - dashboard_renderer/components/signals.py
  - dashboard_renderer/components/settings.py
  - dashboard_renderer/api.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "/markets/{M}/signals renders only M's signal cards (no other market's eyebrow appears)"
    - "/markets/{M}/settings renders only M's settings fieldset"
    - "/markets/{M}/market-test renders only M's market-test form"
    - "render_dashboard_page threads active_market into _build_render_context"
    - "On-disk sibling caches (dashboard-signals.html etc) explicitly use first-market fallback"
  artifacts:
    - path: dashboard.py
      provides: "_render_page_body forwards ctx.active_market to per-market renderers"
      contains: "active_market"
    - path: dashboard_renderer/components/signals.py
      provides: "render_signal_cards filters per active_market"
      contains: "active_market"
    - path: dashboard_renderer/components/settings.py
      provides: "render_settings_tab + render_market_test_tab filter per active_market"
      contains: "active_market"
    - path: dashboard_renderer/api.py
      provides: "render_dashboard_page forwards active_market kwarg"
      contains: "active_market"
  key_links:
    - from: "_render_page_body (dashboard.py:1961)"
      to: "render_signal_cards / render_settings_tab / render_market_test_tab"
      via: "active_market kwarg"
      pattern: "active_market="
    - from: "render_dashboard_page (api.py:143)"
      to: "_build_render_context"
      via: "active_market kwarg forward"
      pattern: "active_market=active_market"
---

<objective>
B1 + R3 together. Thread `ctx.active_market` into the three per-market render functions (`_render_signal_cards`, `render_settings_tab`, `_render_market_test_tab`) and filter the per-market loops. Forward `active_market` through `render_dashboard_page` → `_build_render_context`. On-disk siblings explicitly use first-market fallback.

Purpose: Phase 25 headline value prop — multi-tab scoping — actually works.
Output: Three renderer leaves filter per active market; cached siblings explicit about fallback.
</objective>

<context>
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-PATTERNS.md
@dashboard.py
@dashboard_renderer/components/signals.py
@dashboard_renderer/components/settings.py
@dashboard_renderer/api.py
@dashboard_renderer/components/nav.py

<interfaces>
# Source-of-truth fallback (already in repo):
#   dashboard_renderer/components/nav.py:19-26  _first_market_id(state) -> str
# Template threading already done correctly:
#   dashboard.py:2047-2080  _render_single_page_dashboard reads ctx.active_market and falls back to _first_market_id
# RenderContext (dashboard_renderer/context.py) already has active_market field (Phase 25 D-03).
# _build_render_context (dashboard_renderer/api.py:22-43) already accepts active_market kwarg.
# What's missing: _render_page_body, render_dashboard_page, and the 3 leaves don't pass / consume it.
# Display-name lookup pattern: d._display_names(state) returns dict {market_id: display_name}.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add active_market kwarg to the 3 leaf renderers + filter loops</name>
  <files>dashboard_renderer/components/signals.py, dashboard_renderer/components/settings.py</files>
  <behavior>
    - render_signal_cards(state, *, active_market: str | None = None) — when active_market is set and present in state['markets'], only that market's cards render.
    - render_settings_tab(state, *, active_market: str | None = None) — only active market's fieldset renders.
    - render_market_test_tab(state, *, active_market: str | None = None) — already uses next(iter(display_names)) (settings.py:128); switch to active_market when set, else first-market fallback (preserve existing behaviour).
    - When active_market is None or not in state['markets']: existing behaviour preserved (render every market or first-market for market-test).
  </behavior>
  <action>
1. Read signals.py:6 and settings.py:6, settings.py:117 to capture current loop bodies.
2. Add `active_market: str | None = None` keyword-only parameter to each of the three functions.
3. Inside each, before the per-market loop:
```python
display_names = d._display_names(state)
if active_market and active_market in display_names:
    display_names = {active_market: display_names[active_market]}
```
4. The loop iterates `display_names.items()` as before — it now sees only the active market.
5. For render_market_test_tab (settings.py:117), replace `next(iter(display_names), None)` with: prefer active_market if present, else first-market fallback. Pattern:
```python
target_market = active_market if (active_market and active_market in display_names) else next(iter(display_names), None)
```
6. No other changes — keep all rendering logic, IDs, classes intact. Hex-boundary: pure renderer code; no web/auth imports introduced.
  </action>
  <verify>
    <automated>pytest tests/test_dashboard.py -x</automated>
  </verify>
  <done>Existing test_dashboard.py suite stays green. Renderers compile without breaking existing callers (default active_market=None preserves old behaviour).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Thread active_market through dashboard.py + api.py</name>
  <files>dashboard.py, dashboard_renderer/api.py</files>
  <behavior>
    - _render_page_body(ctx, page) reads ctx.active_market and passes as kwarg to the 3 leaf renderers.
    - render_dashboard_page(state, page, ..., *, active_market: str | None = None) accepts and forwards active_market into _build_render_context (also fixing the missing active_function=page kwarg per 26-PATTERNS.md §R3).
    - When called for on-disk sibling regen (dashboard.render_dashboard at api.py:106-112), active_market is explicitly _first_market_id(state) — documents the fallback rather than implicit-default.
  </behavior>
  <action>
1. dashboard.py — locate `_render_page_body` (~line 1961). Where it currently calls render_signal_cards(state) / render_settings_tab(state) / _render_market_test_tab(state), pass `active_market=getattr(ctx, 'active_market', None)` as kwarg. Mirror the shape from `_render_single_page_dashboard` at line 2047-2080.
2. dashboard_renderer/api.py — `render_dashboard_page` (lines 143-165): add `*, active_market: str | None = None` keyword-only parameter; in the call to `_build_render_context`, add `active_function=page` and `active_market=active_market`.
3. dashboard_renderer/api.py — sibling-regen loop in `render_dashboard` (~lines 106-112) where each page is rendered to disk: pass `active_market=_first_market_id(state)` (importing _first_market_id locally from dashboard_renderer.components.nav). This makes the cache-key fallback explicit per CONTEXT R3 ("drop on-disk cache for market-scoped pages OR include active_market in cache key" — most-eloquent: don't cache market-scoped, document first-market fallback for the on-disk siblings).
4. For market-scoped GET requests (route `/markets/{M}/{fn}`), `_serve_market_scoped_page` already calls `render_dashboard_as_str(state, ..., active_market=market_id, ...)` (verify) — if not, add the kwarg pass-through there too. NOTE: market-scoped path already uses Cache-Control: no-store in-memory render, so no on-disk cache key change needed.
  </action>
  <verify>
    <automated>pytest tests/test_web_app_factory.py::TestPhase26MarketScoping -v</automated>
  </verify>
  <done>All TestPhase26MarketScoping tests flip from XFAIL → PASS.</done>
</task>

<task type="auto">
  <name>Task 3: Remove xfail decorators from now-passing TestPhase26MarketScoping</name>
  <files>tests/test_web_app_factory.py</files>
  <action>
Remove `@pytest.mark.xfail(...)` decorators from every newly-passing test in TestPhase26MarketScoping. Strict xfail with passing test → XPASS failure; we want green going forward.
  </action>
  <verify>
    <automated>pytest tests/test_web_app_factory.py -k "Phase26MarketScoping" -v 2>&1 | grep -cE "PASSED"</automated>
  </verify>
  <done>All Phase26MarketScoping tests report PASSED.</done>
</task>

</tasks>

<verification>
```
pytest tests/test_dashboard.py tests/test_web_app_factory.py tests/test_web_dashboard.py -x
pytest -x  # full suite
grep -rn '{{[A-Z_]\+}}' web/routes/dashboard.py dashboard.py dashboard_renderer/ | grep -v '^[^:]*:[^:]*:#\|_substitute' || true
```

Manual smoke (operator after deploy):
- `/markets/SPI200/settings` → only SPI 200 fieldset.
- `/markets/AUDUSD/signals` → only AUDUSD signal card.
- `/markets/ESM/market-test` → only ES Mini override form.
</verification>

<success_criteria>
- 3 leaf renderers accept active_market kwarg.
- _render_page_body forwards ctx.active_market.
- render_dashboard_page forwards active_market into _build_render_context with active_function=page set.
- TestPhase26MarketScoping all green.
- No regression in test_dashboard.py suite.
</success_criteria>

## Threat Model

| Threat ID | Category | Component | Disposition | Mitigation |
|---|---|---|---|---|
| T-26-07 | Tampering | Attacker passes crafted active_market path param to access another tenant's data | accept | single-operator app; no multi-tenancy. Pydantic ^[A-Z0-9_]{2,20}$ already validates upstream (web/routes/markets.py:20). |
| T-26-08 | Information disclosure | active_market lookup in state['markets'] could reveal market existence via timing | accept | low-value side channel; market list is operator-controlled. |

## Rollback

`git revert <plan-05-commit>`. Default-None kwargs preserve old behaviour on revert; the only behavioural change is per-market filtering, which reverts cleanly.

## Notes

Pattern map: 26-PATTERNS.md §B1 + §R3. Copy fallback shape from dashboard.py:2063-2065. Reuse `_first_market_id` from nav.py:19-26.

Caveman: thread the bool, filter the dict, ship.

<output>
Create `26-05-SUMMARY.md` listing kwargs added per file + Phase26MarketScoping pass count + manual smoke verdict.
</output>
