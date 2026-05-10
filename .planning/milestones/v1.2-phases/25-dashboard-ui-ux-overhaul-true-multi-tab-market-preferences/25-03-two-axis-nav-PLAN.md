---
phase: 25
plan: 03
type: execute
wave: 2
depends_on: [25-01, 25-02]
files_modified:
  - dashboard_renderer/components/nav.py
  - dashboard_renderer/shell.py
  - dashboard_renderer/api.py
  - dashboard_renderer/context.py
  - dashboard_renderer/pages.py
  - dashboard.py
autonomous: true
requirements: [P25-10]
must_haves:
  truths:
    - "Function tab strip renders 4 tabs (Signals, Account, Settings, Market Test); active tab has aria-current=page"
    - "Market tab strip renders one anchor per market_id in state['markets'] (insertion order per OR-03) with hx-get/hx-target/hx-swap/hx-push-url"
    - "When active_function='account', render_market_strip returns '' (zero DOM) per D-04"
    - "When active_market is None and we're on /account, function-tab links for market-scoped functions use first market in insertion order (OR-03)"
    - "All emitted market_id values are html.escape'd to defend against XSS"
    - "render_dashboard accepts htmx_panel_only=True returning ONLY the inner panel HTML for HTMX swaps; consumed by Plan 25-04 in lieu of fragile regex extraction"
    - "Roving tabindex JS helper handles arrow keys within each tablist"
  artifacts:
    - path: dashboard_renderer/components/nav.py
      provides: "Full implementation of render_function_strip / render_market_strip / render_two_axis_nav with WAI-ARIA tabs pattern"
      min_lines: 80
    - path: dashboard_renderer/api.py
      provides: "render_dashboard signature accepts active_function and active_market params"
      contains: "active_market"
    - path: dashboard_renderer/context.py
      provides: "RenderContext with active_function and active_market fields"
      contains: "active_market"
  key_links:
    - from: "dashboard_renderer/components/nav.py"
      to: "state['markets']"
      via: "state.get('markets', {}).keys() insertion order"
      pattern: "state\\['markets'\\]|state.get\\('markets'"
    - from: "dashboard.py _render_dashboard_page_nav"
      to: "dashboard_renderer.components.nav.render_two_axis_nav"
      via: "function call replacement"
      pattern: "render_two_axis_nav"
---

<objective>
Wave 2 implementation. Replace flat 4-tab nav (`dashboard.py:_render_dashboard_page_nav`) with two-axis nav: function strip × market strip. Includes WAI-ARIA roving tabindex (arrow-key + Home/End), aria-current="page" on active, HTMX swap attributes on market strip per D-01/D-03/D-18. Zero-DOM market strip on /account per D-04. First-market fallback per OR-03 (insertion order).

Output: nav.py implementation; render_dashboard wired to accept and pass active_function/active_market; dashboard.py call site replaced.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-02-SUMMARY.md
@dashboard_renderer/components/nav.py
@dashboard_renderer/api.py
@dashboard_renderer/context.py
@dashboard_renderer/pages.py
@dashboard_renderer/shell.py
@dashboard.py

<interfaces>
# dashboard_renderer/context.py existing dataclass:
#   @dataclass(slots=True)
#   class RenderContext:
#       state: dict
#       now: datetime
#       strategy_version: str
#       trace_open_keys: tuple[str, ...] = ()
# Phase 25 adds: active_function: str = 'signals', active_market: str | None = None

# dashboard.py:_render_dashboard_page_nav (locate via grep) — flat 4-tab nav. Replace call site to use render_two_axis_nav.

# state['markets'] shape: {'SPI200': {'sort_order': 10, ...}, 'AUDUSD': {'sort_order': 20, ...}}
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement nav.py bodies (function strip + market strip + roving-tabindex JS)</name>
  <read_first>
    - dashboard_renderer/components/nav.py (the stubs from Plan 02)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md (§Architecture Patterns Pattern 1, §Pitfall 6)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md (§Tab strips, §Active-tab affordance, §Two-axis nav)
    - dashboard_renderer/shell.py (place to add tabs-keyboard JS)
  </read_first>
  <files>dashboard_renderer/components/nav.py, dashboard_renderer/shell.py</files>
  <action>
Replace the stub bodies in `dashboard_renderer/components/nav.py` with real implementations:

```python
"""dashboard_renderer/components/nav.py — Phase 25 D-01/D-03/D-04/D-05/D-18 two-axis nav."""

import html


# Function tab definition: (key, label, is_market_scoped). Order is the visible left-to-right order.
_FUNCTION_TABS = (
    ('signals', 'Signals', True),
    ('account', 'Account', False),
    ('settings', 'Settings', True),
    ('market-test', 'Market Test', True),
)


def _first_market_id(state: dict) -> str:
    """Per OR-03: first-market fallback uses dict insertion order (Python 3.7+ guarantees).
    No special-case for SPI200; pure insertion order.
    """
    markets = state.get('markets', {}) or {}
    if not markets:
        return ''
    return next(iter(markets))


def render_function_strip(active_function: str, active_market: str | None, state: dict | None = None) -> str:
    """Function tab strip — full-page nav (no HTMX swap). Per D-01/D-18.

    aria-current='page' on the active anchor (D-18). Roving tabindex (active=0, inactive=-1).
    Market-scoped functions link to /markets/{fallback}/<function> when active_market is set or
    when state has markets (use first market in insertion order per OR-03).
    """
    fallback_market = active_market or (_first_market_id(state) if state else '')
    out = ['<nav role="tablist" aria-label="Function" class="tabs tabs-function">\n']
    for key, label, is_market_scoped in _FUNCTION_TABS:
        if is_market_scoped and fallback_market:
            href = f'/markets/{html.escape(fallback_market, quote=True)}/{key}'
        elif key == 'account':
            href = '/account'
        else:
            href = f'/{key}'
        is_active = (key == active_function)
        tabindex = '0' if is_active else '-1'
        aria_current = 'page' if is_active else 'false'
        cls = 'tab-active' if is_active else 'tab-inactive'
        out.append(
            f'  <a role="tab" tabindex="{tabindex}" aria-current="{aria_current}" '
            f'class="{cls}" href="{href}" data-tab-key="{key}">'
            f'{html.escape(label, quote=True)}</a>\n'
        )
    out.append('</nav>\n')
    return ''.join(out)


def render_market_strip(state: dict, active_market: str, active_function: str) -> str:
    """Market tab strip — HTMX swap (D-01/D-03).

    Hidden entirely (zero DOM) when active_function == 'account' (D-04).
    Tabs in insertion order in state['markets'] (per OR-03).
    The + Add market chip is appended in Plan 25-05; here we leave a placeholder comment.
    """
    if active_function == 'account':
        return ''  # D-04
    markets = state.get('markets', {}) or {}
    out = ['<nav role="tablist" aria-label="Market" class="tabs tabs-market" id="market-tab-strip">\n']
    for market_id in markets.keys():
        market_esc = html.escape(market_id, quote=True)
        is_active = (market_id == active_market)
        tabindex = '0' if is_active else '-1'
        aria_current = 'page' if is_active else 'false'
        cls = 'tab-active' if is_active else 'tab-inactive'
        out.append(
            f'  <a role="tab" tabindex="{tabindex}" aria-current="{aria_current}" '
            f'class="{cls}" '
            f'href="/markets/{market_esc}/{active_function}" '
            f'hx-get="/markets/{market_esc}/{active_function}" '
            f'hx-target="#market-panel" hx-swap="innerHTML" hx-push-url="true" '
            f'hx-headers=\'{{"X-Trading-Signals-Auth": "{{{{WEB_AUTH_SECRET}}}}"}}\' '
            f'data-market-id="{market_esc}">'
            f'{market_esc}</a>\n'
        )
    out.append('  <!-- Phase 25 Plan 05: + Add market chip injected here (D-16) -->\n')
    out.append('</nav>\n')
    return ''.join(out)


def render_two_axis_nav(state: dict, active_function: str, active_market: str | None) -> str:
    """Compose function strip + market strip. Replaces dashboard._render_dashboard_page_nav."""
    return render_function_strip(active_function, active_market, state) + render_market_strip(
        state, active_market or '', active_function
    )
```

Add tabs-keyboard JS helper to `dashboard_renderer/shell.py`:

```python
_TABS_KEYBOARD_JS = """
<script>
// Phase 25 D-18: WAI-ARIA tabs roving tabindex + arrow-key navigation.
(function () {
  function bindTablist(navEl) {
    const tabs = Array.from(navEl.querySelectorAll('[role=\"tab\"]'));
    if (tabs.length === 0) return;
    navEl.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' && e.key !== 'Home' && e.key !== 'End') return;
      const current = tabs.indexOf(document.activeElement);
      if (current < 0) return;
      let next = current;
      if (e.key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
      else if (e.key === 'ArrowRight') next = (current + 1) % tabs.length;
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = tabs.length - 1;
      e.preventDefault();
      tabs.forEach(function (t, i) { t.setAttribute('tabindex', i === next ? '0' : '-1'); });
      tabs[next].focus();
    });
  }
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('nav[role=\"tablist\"]').forEach(bindTablist);
  });
  document.body.addEventListener('htmx:afterSwap', function () {
    document.querySelectorAll('nav[role=\"tablist\"]').forEach(bindTablist);
  });
})();
</script>
"""
```

Wire `_TABS_KEYBOARD_JS` into `render_html_shell` body block (append after the existing `_AWST_COUNTDOWN_JS` script).
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -c "
from dashboard_renderer.components.nav import render_function_strip, render_market_strip, render_two_axis_nav
state = {'markets': {'SPI200': {}, 'AUDUSD': {}}}
fs = render_function_strip('signals', 'SPI200', state)
assert 'aria-current=\"page\"' in fs and 'href=\"/markets/SPI200/signals\"' in fs and 'tabindex=\"0\"' in fs and 'tabindex=\"-1\"' in fs
assert render_market_strip(state, '', 'account') == ''
ms = render_market_strip(state, 'SPI200', 'signals')
assert 'hx-get=\"/markets/SPI200/signals\"' in ms and 'hx-push-url=\"true\"' in ms and 'aria-label=\"Market\"' in ms
fs_account = render_function_strip('account', None, state)
assert '/markets/SPI200/signals' in fs_account, 'OR-03 fallback failed'
print('OK')
" && grep -q "_TABS_KEYBOARD_JS" dashboard_renderer/shell.py && echo "JS helper present"</automated>
  </verify>
  <done>
    - render_function_strip emits 4 anchors with correct aria-current/tabindex/href values
    - render_market_strip emits zero DOM on /account and proper HTMX-attributed anchors elsewhere
    - render_two_axis_nav composes both strips
    - _TABS_KEYBOARD_JS present in shell.py and emitted by render_html_shell
    - All emitted market_id values are html-escaped
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire active_function and active_market through RenderContext, api.render_dashboard, pages.render_dashboard_page_body, and dashboard.py call site</name>
  <read_first>
    - dashboard_renderer/context.py (existing RenderContext dataclass)
    - dashboard_renderer/api.py (render_dashboard signature + _build_render_context)
    - dashboard_renderer/pages.py (render_dashboard_page_body signature)
    - dashboard.py — locate `_render_dashboard_page_nav` call site (and its callers in `_render_single_page_dashboard`, `_render_tabbed_dashboard`)
  </read_first>
  <files>dashboard_renderer/context.py, dashboard_renderer/api.py, dashboard_renderer/pages.py, dashboard.py</files>
  <action>
**Step 1 — extend RenderContext** (`dashboard_renderer/context.py`):

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(slots=True)
class RenderContext:
    state: dict
    now: datetime
    strategy_version: str
    trace_open_keys: tuple[str, ...] = ()
    active_function: str = 'signals'  # Phase 25 D-01: one of 'signals'|'account'|'settings'|'market-test'
    active_market: str | None = None   # Phase 25 D-03/D-04: None on /account; market_id otherwise
```

**Step 2 — extend `dashboard_renderer/api.render_dashboard` signature:**

Add keyword-only params `active_function: str = 'signals'` and `active_market: str | None = None`. Pass them into the constructed RenderContext. Existing callers continue to work via defaults.

```python
def render_dashboard(
    state: dict,
    now: datetime | None = None,
    *,
    strategy_version: str | None = None,
    trace_open_keys: tuple[str, ...] = (),
    active_function: str = 'signals',
    active_market: str | None = None,
    htmx_panel_only: bool = False,
) -> str:
    ctx = _build_render_context(
        state, now, strategy_version, trace_open_keys,
        active_function=active_function, active_market=active_market,
    )
    if htmx_panel_only:
        # Phase 25 Plan 04: HTMX swap path — return ONLY the inner HTML of <section id="market-panel">
        # (no shell, no nav strips). This replaces fragile regex extraction in web/routes/dashboard.py
        # (resolves Plan 25-04 WARNING 4).
        from dashboard_renderer.pages import render_panel_only
        return render_panel_only(ctx)
    ...
```

Update `_build_render_context` to plumb the new fields.

Add `render_panel_only(ctx)` to `dashboard_renderer/pages.py` — it composes ONLY the per-market panel inner HTML (Signals trace cards / Settings fieldsets / Market Test form), without the surrounding `<section id="market-panel">…</section>` wrapper, without the function strip, without the market strip, without `<head>`/`<body>`. Plan 04 calls `render_dashboard(state, ..., htmx_panel_only=True)` for HTMX-Request responses.

**Step 3 — extend `dashboard_renderer/pages.render_dashboard_page_body`:**

Existing signature: `render_dashboard_page_body(ctx, page, nav_mode)`. Phase 25: derive `active_function` and `active_market` from `ctx`, pass to nav rendering.

```python
def render_dashboard_page_body(ctx, page: str, nav_mode: str) -> str:
    # Replace inline nav rendering with nav.render_two_axis_nav.
    from dashboard_renderer.components.nav import render_two_axis_nav
    nav_html = render_two_axis_nav(ctx.state, ctx.active_function, ctx.active_market)
    # ... existing body rendering ... (still delegates to dashboard._render_single_page_dashboard for now;
    # Plan 03 only swaps the nav call site)
```

**Step 4 — replace `dashboard.py:_render_dashboard_page_nav` call sites:**

Locate every callsite of `_render_dashboard_page_nav` (use grep). Replace each call with:
```python
from dashboard_renderer.components.nav import render_two_axis_nav
nav_html = render_two_axis_nav(state, active_function, active_market)
```

Where `active_function` and `active_market` are derived from the page being rendered. For the legacy `/signals`, `/settings`, `/market-test` paths (without `/markets/{m}/` prefix), `active_market` defaults to `_first_market_id(state)` from nav.py (re-export the helper if needed).

KEEP the old `_render_dashboard_page_nav` function definition for now (mark with a deprecation comment) to avoid breaking any tests that might reach it directly. Plan 25-09 (final cleanup) deletes it.

**Step 5 — wrap the panel content in `<section id="market-panel">`:**

The HTMX swap target is `#market-panel`. The page body must contain a single element with `id="market-panel"` wrapping the per-market content (Signals/Settings/Market Test). For /account, the wrapper is omitted (no market panel — Account is market-agnostic).

In `_render_single_page_dashboard` (or wherever the per-page body is composed), wrap the per-market content:

```python
if active_function != 'account':
    body = f'<section id="market-panel" aria-live="polite">\n{panel_content}\n</section>\n'
else:
    body = panel_content
```

**Step 6 — run the full test suite + Phase-25 xfail tests for nav:**

After this task, the Phase-25 tests for active-tab/aria-current/aria-label-Market/aria-label-Function should flip from XFAIL to PASS (xfail-strict will then fail → executor flips them to non-xfail by removing the decorator). 

Update `tests/test_dashboard.py::TestPhase25ActiveTab` (added in Plan 01) by removing the `@pytest.mark.xfail` decorators on those three tests so they assert real green.

Also: existing `tests/test_dashboard.py:3108-3112` may assert the old "Account Management" tab label. If it does, update the assertion to `Account` per UI-SPEC §Tab strips.
  </action>
  <verify>
    <automated>python -c "
from dashboard_renderer.api import render_dashboard
state = {'markets': {'SPI200': {}, 'AUDUSD': {}}, 'last_run': '2026-04-23', 'warnings': [], 'equity_history': [], 'signals': {'SPI200': {'strategy_version': 'v1.2.0', 'signal': 0}}, 'paper_trades': [], 'positions': [], 'closed_trades': [], 'strategy_settings': {'SPI200': {}, 'AUDUSD': {}}, 'account_balance_paper': 100000.0, 'account_balance_live': 100000.0}
html_out = render_dashboard(state, active_function='signals', active_market='SPI200')
assert 'aria-label=\"Function\"' in html_out
assert 'aria-label=\"Market\"' in html_out
assert 'id=\"market-panel\"' in html_out
print('OK')
" && python -m pytest tests/test_dashboard.py::TestPhase25ActiveTab -q --no-header 2>&1 | tail -5</automated>
  </verify>
  <done>
    - RenderContext has active_function and active_market fields
    - render_dashboard accepts the new kwargs and threads them to ctx
    - render_dashboard_page_body uses render_two_axis_nav (not the old _render_dashboard_page_nav)
    - Body output contains `<section id="market-panel">` for market-scoped pages, omitted for /account
    - Phase-25 ActiveTab tests are now PASS (xfail decorator removed)
    - Pre-existing test_dashboard.py assertions updated for "Account Management" → "Account" rename
    - Full test suite green
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Renderer → HTML output | market_id values come from state.json (server-controlled) but flow through HTML attributes; must escape. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-03-01 | Tampering (XSS) | render_market_strip | mitigate | All market_id values pass through `html.escape(value, quote=True)` before HTML emission, including href, hx-get, hx-target, data-market-id. Verified by grep gate `grep -E 'f"<a[^"]*\\{market_id\\b' dashboard_renderer/components/nav.py | grep -v escape` returns zero matches. |
| T-25-03-02 | Information Disclosure | hx-headers in nav anchors | accept | hx-headers includes `{{WEB_AUTH_SECRET}}` placeholder substituted server-side at render — same pattern as existing forms (verified RESEARCH §6). No new disclosure surface. |
</threat_model>

<verification>
- `python -c "from dashboard_renderer.components.nav import render_two_axis_nav; print(render_two_axis_nav({'markets': {'X': {}}}, 'signals', 'X'))"` prints valid HTML.
- TestPhase25ActiveTab tests pass (xfail decorators removed).
- Full test suite green: `pytest -q` exits 0.
- No `_render_dashboard_page_nav` direct invocations remain in render path (confirmed via grep): `grep -rn "_render_dashboard_page_nav(" --include="*.py"` returns no matches outside the deprecated definition itself.
</verification>

<success_criteria>
- nav.py implements the WAI-ARIA tabs pattern verbatim.
- Function strip and market strip composed via render_two_axis_nav.
- /account branch returns zero DOM for market strip (D-04).
- OR-03 first-market fallback uses insertion order.
- Roving-tabindex JS helper handles arrows/Home/End and re-binds after HTMX swaps.
- RenderContext + render_dashboard + pages.render_dashboard_page_body wired through.
- Phase-25 active-tab and aria-label tests PASS.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-03-SUMMARY.md` summarising nav implementation, the test xfail flips, and any drift from the legacy nav rendering that needed test updates.
</output>
