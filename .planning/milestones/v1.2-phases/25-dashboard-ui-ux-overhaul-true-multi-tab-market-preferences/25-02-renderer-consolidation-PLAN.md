---
phase: 25
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - dashboard_renderer/shell.py
  - dashboard_renderer/assets.py
  - dashboard_renderer/components/__init__.py
  - dashboard_renderer/components/nav.py
  - web/routes/dashboard.py
autonomous: true
requirements: [P25-10]
must_haves:
  truths:
    - "Common <style> + JS helpers (handleTradesError, trace-toggle, AWST countdown) live in dashboard_renderer/shell.py as the single source of truth"
    - "A new dashboard_renderer/components/nav.py module exists with render_function_strip and render_market_strip stubs (interface contracts only)"
    - "_REQUIRED_DASHBOARD_MARKER in web/routes/dashboard.py is updated to a Phase-25 marker that forces regen of all 5 sibling HTML files on next request post-deploy"
  artifacts:
    - path: dashboard_renderer/shell.py
      provides: "Single source for inline <style>, <script>, and JS helpers (DASH-01 inline pattern preserved per D-02)"
      min_lines: 60
    - path: dashboard_renderer/components/nav.py
      provides: "render_function_strip(active_function, active_market), render_market_strip(state, active_market, active_function), render_two_axis_nav(state, active_function, active_market) — INTERFACE STUBS for Wave 2"
      contains: "def render_function_strip"
    - path: web/routes/dashboard.py
      provides: "_REQUIRED_DASHBOARD_MARKER updated to Phase-25 token"
      contains: "_REQUIRED_DASHBOARD_MARKER"
  key_links:
    - from: "dashboard_renderer/shell.py"
      to: "dashboard.py shell constants (_INLINE_CSS, _HANDLE_TRADES_ERROR_JS, _TRACE_TOGGLE_JS)"
      via: "import or constant migration"
      pattern: "_INLINE_CSS|_HANDLE_TRADES_ERROR_JS|_TRACE_TOGGLE_JS"
    - from: "web/routes/dashboard.py:_is_stale"
      to: "dashboard*.html files on disk"
      via: "marker substring check"
      pattern: "_REQUIRED_DASHBOARD_MARKER"
---

<objective>
Wave 1 foundation. Migrate the inline shell (<style>, <script>, JS helpers) into dashboard_renderer/shell.py so all 5 generated dashboard*.html files share one source. Create the nav.py module with interface stubs that downstream Wave 2 (Plan 03) will implement. Update the regen marker so the deploy automatically refreshes all 5 stale sibling files.

Purpose: Prevents the 4-file × ~1000-LOC duplication from continuing to drift. Sets up the surface that all downstream plans modify (per D-01/D-02). Wave 2 plans depend on this foundation.

Output: shell.py becomes the load-bearing module for chrome; nav.py exists as stub for downstream impl; marker change forces regen of all 5 sibling HTMLs on next request.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-CONTEXT.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@dashboard_renderer/shell.py
@dashboard_renderer/assets.py
@dashboard_renderer/api.py
@dashboard.py
@web/routes/dashboard.py

<interfaces>
# From dashboard.py (current locations of constants to migrate):
# - _INLINE_CSS: large inline <style> block (~3000 chars) — search dashboard.py for "_INLINE_CSS ="
# - _HANDLE_TRADES_ERROR_JS: JS function definition for error handling
# - _TRACE_TOGGLE_JS: JS for cookie-driven <details> toggle
# - _CHARTJS_*: Chart.js CDN URL + integrity hash constants
# - _HTMX_*: HTMX CDN URL + integrity constants

# From dashboard_renderer/assets.py — currently re-exports from dashboard.py (bridge module).
# Phase 25 promotes assets.py and shell.py as source of truth.

# From web/routes/dashboard.py:
# - _REQUIRED_DASHBOARD_MARKER = b'<nav class="tabs"' — current marker (line ~74)
# - _is_stale(html_path, state_path) reads marker substring; marker absent → regenerate
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Migrate inline shell constants (_INLINE_CSS, _HANDLE_TRADES_ERROR_JS, _TRACE_TOGGLE_JS) into dashboard_renderer/shell.py + assets.py</name>
  <read_first>
    - dashboard.py — locate the constants:
      `grep -n "^_INLINE_CSS\|^_HANDLE_TRADES_ERROR_JS\|^_TRACE_TOGGLE_JS\|^_CHARTJS_\|^_HTMX_" dashboard.py`
    - dashboard_renderer/shell.py (current 8-line wrapper)
    - dashboard_renderer/assets.py (current 12-line re-export bridge)
    - dashboard_renderer/api.py (where shell + assets are consumed)
  </read_first>
  <files>dashboard_renderer/shell.py, dashboard_renderer/assets.py, dashboard.py</files>
  <action>
Move the load-bearing shell constants from dashboard.py into dashboard_renderer/assets.py + dashboard_renderer/shell.py without changing their content yet (D-15 token rebalance happens in Plan 09; D-01 nav rendering happens in Plan 03; this plan is pure relocation).

**Step 1 — read constant definitions from dashboard.py:**
Use grep to find the exact line ranges for `_INLINE_CSS`, `_HANDLE_TRADES_ERROR_JS`, `_TRACE_TOGGLE_JS`, `_CHARTJS_URL`, `_CHARTJS_INTEGRITY`, `_HTMX_URL`, `_HTMX_INTEGRITY`, `_HTMX_JSON_ENC_URL`, `_HTMX_JSON_ENC_INTEGRITY`. Record exact byte content (including triple-quoted strings).

**Step 2 — relocate to dashboard_renderer/assets.py:**
Replace the current re-export shim in `dashboard_renderer/assets.py` with the actual constant definitions copied verbatim from dashboard.py. The new assets.py becomes the source of truth.

**Step 3 — update dashboard.py to re-export from assets.py:**
Replace the constant definitions in dashboard.py with:
```python
from dashboard_renderer.assets import (
    _INLINE_CSS,
    _HANDLE_TRADES_ERROR_JS,
    _TRACE_TOGGLE_JS,
    _CHARTJS_URL,
    _CHARTJS_INTEGRITY,
    _HTMX_URL,
    _HTMX_INTEGRITY,
    _HTMX_JSON_ENC_URL,
    _HTMX_JSON_ENC_INTEGRITY,
)
```
This preserves all existing dashboard.py imports/uses while making assets.py the canonical home.

**Step 4 — flesh out dashboard_renderer/shell.py:**
Currently shell.py is an 8-line wrapper that delegates to `dashboard._render_html_shell`. Replace with a proper renderer that consumes the constants from assets.py:

```python
"""dashboard_renderer/shell.py — single source of truth for HTML shell (<head>, <style>, <script>) per D-02."""

import html
from datetime import datetime

from dashboard_renderer.assets import (
    _INLINE_CSS,
    _HANDLE_TRADES_ERROR_JS,
    _TRACE_TOGGLE_JS,
    _CHARTJS_URL,
    _CHARTJS_INTEGRITY,
    _HTMX_URL,
    _HTMX_INTEGRITY,
    _HTMX_JSON_ENC_URL,
    _HTMX_JSON_ENC_INTEGRITY,
)


# Phase 25 D-08: AWST countdown helper. Inlined per D-02 — no external /static/dashboard.js.
# Uses Date.UTC arithmetic — never browser local TZ.
_AWST_COUNTDOWN_JS = """
<script>
// Phase 25 D-08: AWST countdown. Fixed UTC+8 offset; ignores browser local TZ.
// 08:00 AWST == 00:00 UTC. We target 08:01 AWST == 00:01 UTC for the strip auto-refresh
// (60s buffer past daemon trigger so state.json has time to write).
function _awstNext0800Utc() {
  const now = Date.now();
  const d = new Date(now);
  // 00:00 UTC today
  let target = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 0, 0, 0, 0);
  if (target <= now) target += 86400000;
  // Skip weekends — daemon does not run Sat (UTC Fri 16:00+) / Sun (UTC Sat 16:00+).
  // Reference day: target's UTC day-of-week (0=Sun..6=Sat).
  let dt = new Date(target);
  while (dt.getUTCDay() === 0 || dt.getUTCDay() === 6) {
    target += 86400000;
    dt = new Date(target);
  }
  return target;
}
function _formatAwstCountdown(targetUtcMs) {
  const now = Date.now();
  const dt = new Date(targetUtcMs);
  // Day name from UTC (since AWST has no DST, UTC day-of-week == AWST day-of-week for 00:00 UTC)
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const dayName = days[dt.getUTCDay()];
  const hh = String(dt.getUTCHours() + 8).padStart(2, '0').slice(-2);  // 00 UTC = 08 AWST
  const mm = String(dt.getUTCMinutes()).padStart(2, '0');
  const deltaMs = targetUtcMs - now;
  const deltaH = Math.floor(deltaMs / 3600000);
  const deltaM = Math.floor((deltaMs % 3600000) / 60000);
  if (deltaH >= 24) {
    const days = Math.floor(deltaH / 24);
    const hours = deltaH % 24;
    return `${dayName} 08:00 AWST · in ${days}d ${hours}h`;
  }
  return `in ${deltaH}h ${deltaM}m`;
}
function _refreshAwstCountdowns() {
  const target = _awstNext0800Utc();
  document.querySelectorAll('[data-countdown]').forEach(function (el) {
    el.textContent = _formatAwstCountdown(target);
  });
}
document.addEventListener('DOMContentLoaded', function () {
  _refreshAwstCountdowns();
  setInterval(_refreshAwstCountdowns, 60000);
});
</script>
"""


def render_html_shell(ctx, body: str) -> str:
    """Phase 25 D-02: emit shared <head> + style + scripts inline. Single source of truth."""
    title = 'Trading Signals'  # function-tab + market segments overlay this in later plans
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{html.escape(title, quote=True)}</title>\n'
        f'<script src="{_HTMX_URL}" integrity="{_HTMX_INTEGRITY}" crossorigin="anonymous"></script>\n'
        f'<script src="{_HTMX_JSON_ENC_URL}" integrity="{_HTMX_JSON_ENC_INTEGRITY}" crossorigin="anonymous"></script>\n'
        f'<script src="{_CHARTJS_URL}" integrity="{_CHARTJS_INTEGRITY}" crossorigin="anonymous"></script>\n'
        f'<style>\n{_INLINE_CSS}\n</style>\n'
        '</head>\n'
        f'<body>\n{body}\n'
        f'<script>\n{_HANDLE_TRADES_ERROR_JS}\n</script>\n'
        f'<script>\n{_TRACE_TOGGLE_JS}\n</script>\n'
        f'{_AWST_COUNTDOWN_JS}\n'
        '</body>\n'
        '</html>\n'
    )
```

**CRITICAL:** Verify that `dashboard._render_html_shell` (existing function) and the new `dashboard_renderer.shell.render_html_shell` produce byte-identical output for the same input today. The migration must be transparent — Wave 2 plans assume the shell is centralised.

If `dashboard.py` previously delegated to `dashboard_renderer.shell.render_html_shell` (per existing 8-line wrapper) — verify that wrapper now ACTUALLY emits content (not delegate-back-to-dashboard cycle). Break the cycle: dashboard.py imports from dashboard_renderer.shell, NOT the other way.

Run full test suite after migration. Any test that asserted byte-exact HTML output may need a one-time golden refresh — but the actual rendered HTML should remain byte-equivalent for unchanged input.
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -c "from dashboard_renderer.shell import render_html_shell; from dashboard_renderer.assets import _INLINE_CSS, _HANDLE_TRADES_ERROR_JS, _TRACE_TOGGLE_JS; assert len(_INLINE_CSS) > 1000, 'CSS too small — migration incomplete'; print('OK')" && python -m pytest tests/test_dashboard.py tests/test_web_dashboard.py -q --no-header 2>&1 | tail -10</automated>
  </verify>
  <done>
    - dashboard_renderer/assets.py contains the actual constant definitions (not just re-exports)
    - dashboard_renderer/shell.py emits a complete HTML shell using assets.py imports + the new _AWST_COUNTDOWN_JS helper
    - dashboard.py either re-exports the constants from assets.py OR imports them transitively — but does NOT define them at module level any more
    - Full test suite (`pytest -q`) still passes — no byte-level shell drift
  </done>
</task>

<task type="auto">
  <name>Task 2: Create dashboard_renderer/components/nav.py interface stubs + update _REQUIRED_DASHBOARD_MARKER</name>
  <read_first>
    - dashboard_renderer/components/__init__.py (currently empty)
    - dashboard_renderer/components/header.py (existing component pattern)
    - dashboard.py — locate `_render_dashboard_page_nav` (around line 2673 per RESEARCH §2)
    - web/routes/dashboard.py — locate `_REQUIRED_DASHBOARD_MARKER` (around line 74) and `_is_stale` function
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md §Architecture Patterns Pattern 1 (full nav.py example)
  </read_first>
  <files>dashboard_renderer/components/nav.py, dashboard_renderer/components/__init__.py, web/routes/dashboard.py</files>
  <action>
**Step 1 — Create dashboard_renderer/components/nav.py with INTERFACE STUBS:**

This task only creates the module + signatures. Plan 03 (Wave 2) implements the full body. The stubs return placeholder strings so the module imports cleanly.

```python
"""dashboard_renderer/components/nav.py — Phase 25 D-01/D-03/D-04/D-05/D-18 two-axis nav.

Interface stubs only — full implementation lands in Plan 25-03 (Wave 2).
"""

import html


def render_function_strip(active_function: str, active_market: str | None) -> str:
    """Function tab strip — full-page nav (no HTMX swap). Per D-01/D-18.

    Args:
        active_function: one of 'signals' | 'account' | 'settings' | 'market-test'.
        active_market: market_id when on a market-scoped function; None on /account.

    Returns:
        HTML string: <nav role="tablist" aria-label="Function">...</nav>.

    NOTE: Plan 25-02 ships interface stub. Plan 25-03 fills in body per RESEARCH §Pattern 1.
    """
    return (
        '<nav role="tablist" aria-label="Function" class="tabs tabs-function">\n'
        '  <!-- TODO Plan 25-03: real anchors with aria-current + roving tabindex -->\n'
        '</nav>\n'
    )


def render_market_strip(state: dict, active_market: str, active_function: str) -> str:
    """Market tab strip — HTMX swap (D-01/D-03).

    Hidden entirely (zero DOM, not display:none) when active_function == 'account' (D-04).

    Args:
        state: full state dict (reads state['markets']).
        active_market: market_id of the highlighted tab.
        active_function: function being viewed; if 'account', return ''.

    Returns:
        HTML string: <nav role="tablist" aria-label="Market">...</nav> OR '' on /account.

    NOTE: Plan 25-02 ships interface stub. Plan 25-03 fills in body per RESEARCH §Pattern 1.
    Plan 25-05 adds the + Add market chip (D-16).
    """
    if active_function == 'account':
        return ''  # D-04: zero DOM
    return (
        '<nav role="tablist" aria-label="Market" class="tabs tabs-market" id="market-tab-strip">\n'
        '  <!-- TODO Plan 25-03: real market anchors with hx-get + hx-push-url -->\n'
        '</nav>\n'
    )


def render_two_axis_nav(state: dict, active_function: str, active_market: str | None) -> str:
    """Compose function strip + market strip. Top-level entry point for Plan 25-03.

    Returns:
        Concatenated HTML for both strips. Replaces dashboard._render_dashboard_page_nav.
    """
    return render_function_strip(active_function, active_market) + render_market_strip(
        state, active_market or '', active_function
    )
```

**Step 2 — Update _REQUIRED_DASHBOARD_MARKER in web/routes/dashboard.py:**

Read the current marker line (around line 74). It is `_REQUIRED_DASHBOARD_MARKER = b'<nav class="tabs"'` (or similar).

Change to:
```python
_REQUIRED_DASHBOARD_MARKER = b'class="tabs tabs-function"'  # Phase 25 D-01: forces regen of all 5 sibling HTMLs post-deploy
```

This new marker:
- Will NOT be present in the current 5 dashboard*.html files (they have the old `class="tabs"` only) → `_is_stale` returns True on first request after deploy → regeneration happens automatically (per RESEARCH §Pitfall 4).
- Will be present in newly-rendered HTML once Plan 25-03 lands (the new nav emits `class="tabs tabs-function"`).
- During the gap between Plan 02 ship and Plan 03 ship, `_is_stale` returns True every request — performance hit but correctness preserved (no stale literals served). Plan 03 lands within the same wave-merge so the gap is tight.

**Step 3 — Update dashboard_renderer/components/__init__.py:**
```python
"""Phase 25: explicit component imports."""
from dashboard_renderer.components.nav import render_two_axis_nav, render_function_strip, render_market_strip  # noqa: F401
```

**Verification:**
- `python -c "from dashboard_renderer.components.nav import render_two_axis_nav; print(render_two_axis_nav({'markets': {}}, 'signals', 'SPI200'))"` prints stub HTML.
- Full test suite still passes (the stubs don't break anything because no production code calls them yet — Plan 03 wires them in).
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -c "from dashboard_renderer.components.nav import render_function_strip, render_market_strip, render_two_axis_nav; out = render_two_axis_nav({'markets': {}}, 'signals', 'SPI200'); assert 'aria-label=\"Function\"' in out; assert 'aria-label=\"Market\"' in out; assert render_market_strip({}, '', 'account') == ''; print('OK')" && grep -n "_REQUIRED_DASHBOARD_MARKER" web/routes/dashboard.py | head -3 && python -m pytest tests/test_web_app_factory.py tests/test_web_dashboard.py -q --no-header 2>&1 | tail -5</automated>
  </verify>
  <done>
    - dashboard_renderer/components/nav.py exists with three exported functions
    - The `account` branch of render_market_strip returns '' (zero DOM per D-04)
    - dashboard_renderer/components/__init__.py re-exports the three nav functions
    - web/routes/dashboard.py _REQUIRED_DASHBOARD_MARKER updated to a token absent from current dashboard*.html files
    - `pytest -q` exits 0 — no regressions
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Renderer module → HTML output | Any user-controllable data (market_id, signal labels) must be html-escaped before emission. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-02-01 | Tampering (XSS) | nav.py stubs | mitigate | Stubs contain no user-controlled output. Plan 25-03 (Wave 2) implementation must apply `html.escape(market_id, quote=True)` per RESEARCH §Pattern 1 and §Security Domain row "XSS via market_id". |
| T-25-02-02 | (n/a) | shell.py constants | accept | Pure relocation — no new attack surface. |
</threat_model>

<verification>
- `python -c "from dashboard_renderer.shell import render_html_shell"` succeeds.
- `python -c "from dashboard_renderer.assets import _INLINE_CSS; assert len(_INLINE_CSS) > 1000"` succeeds (CSS migrated, not just shimmed).
- `python -c "from dashboard_renderer.components.nav import render_two_axis_nav"` succeeds.
- Full test suite green: `pytest -q` exits 0.
- The `_REQUIRED_DASHBOARD_MARKER` byte-string is absent from at least one of `dashboard.html`, `dashboard-signals.html`, `dashboard-account.html`, `dashboard-settings.html`, `dashboard-market-test.html` so `_is_stale` returns True post-deploy.
</verification>

<success_criteria>
- Inline shell constants live in dashboard_renderer/assets.py (source of truth) — dashboard.py re-exports.
- dashboard_renderer/shell.py emits the full shell using imported constants + new _AWST_COUNTDOWN_JS helper.
- dashboard_renderer/components/nav.py exists with stub interfaces; downstream Plan 25-03 implements bodies.
- Marker change forces regen of all 5 sibling HTMLs on next request after deploy.
- Zero test regressions.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-02-SUMMARY.md` capturing constant migration, marker change, and any byte-level shell drift detected/fixed.
</output>
