'''dashboard_renderer/shell.py — Phase 25 D-02: single source of truth for HTML shell.

Emits the full <!DOCTYPE html> shell with inline <style>, <script>, and the
Phase 25 D-08 AWST countdown helper. All constants imported from assets.py.

Per D-02: no external /static/dashboard.css or /static/dashboard.js.
Everything is inlined in the per-page HTML response (DASH-01 pattern).

Phase 32 Plan 01: _render_page_body, _render_tabbed_dashboard, and
_render_single_page_dashboard ported from dashboard_legacy/page_body.py with
byte-identical bodies. render_html_shell body replaced with the active content
from dashboard_legacy/page_body._render_html_shell.

H-02 WAVE-2 IMPORT RULE: dashboard_renderer/components/account (and any other
Wave-2 component that does not exist until plan 32-02+) must be imported as
LOCAL imports inside the callable body, NOT at module top. This ensures
`import dashboard_renderer.shell` succeeds before Wave 2 runs.
'''

import html as _html
from typing import Callable

from dashboard_renderer.assets import (
  _CHARTJS_URL,
  _CHARTJS_SRI,
  _HANDLE_TRADES_ERROR_JS,
  _HTMX_JSON_ENC_SRI,
  _HTMX_JSON_ENC_URL,
  _HTMX_SRI,
  _HTMX_URL,
  _INLINE_CSS,
  _TRACE_TOGGLE_JS,
)
from dashboard_renderer.context import RenderContext

# Phase 25 D-08: AEST countdown helper. Inlined per D-02 — no external JS.
# Uses Date.UTC arithmetic — never browser local TZ (operator may travel;
# daemon runs at 08:00 AEST = UTC+10).
# 08:00 AEST == 22:00 UTC (previous UTC calendar day). Target is 22:01 UTC
# (60s buffer so state.json has time to write before the strip auto-refreshes).
_AWST_COUNTDOWN_JS = '''<script>
// Phase 25 D-08: AEST countdown. Fixed UTC+10 offset; ignores browser local TZ.
// 08:00 AEST = 22:00 UTC of the previous UTC calendar day.
function _awstNext0800Utc() {
  var now = Date.now();
  var d = new Date(now);
  var target = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 22, 0, 0, 0);
  if (target <= now) target += 86400000;
  // Skip weekends: 22:00 UTC Fri = 08:00 AEST Sat; 22:00 UTC Sat = 08:00 AEST Sun.
  var dt = new Date(target);
  while (dt.getUTCDay() === 5 || dt.getUTCDay() === 6) {
    target += 86400000;
    dt = new Date(target);
  }
  return target;
}
function _formatAwstCountdown(targetUtcMs) {
  var now = Date.now();
  // Day name reflects AEST date (UTC+10 = targetUtcMs + 10h), not UTC date.
  var aestMs = targetUtcMs + 10 * 3600000;
  var dt = new Date(aestMs);
  var days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var dayName = days[dt.getUTCDay()];
  var deltaMs = targetUtcMs - now;
  var deltaH = Math.floor(deltaMs / 3600000);
  var deltaM = Math.floor((deltaMs % 3600000) / 60000);
  if (deltaH >= 24) {
    var ddays = Math.floor(deltaH / 24);
    var hours = deltaH % 24;
    return dayName + ' 08:00 AEST · in ' + ddays + 'd ' + hours + 'h';
  }
  return '08:00 AEST · in ' + deltaH + 'h ' + deltaM + 'm';
}
function _refreshAwstCountdowns() {
  var target = _awstNext0800Utc();
  document.querySelectorAll('[data-countdown]').forEach(function(el) {
    el.textContent = _formatAwstCountdown(target);
  });
}
document.addEventListener('DOMContentLoaded', function() {
  _refreshAwstCountdowns();
  setInterval(_refreshAwstCountdowns, 60000);
});
</script>
'''


# Phase 25 D-18: WAI-ARIA tabs roving tabindex + arrow-key navigation.
# Binds on DOMContentLoaded and re-binds after HTMX swaps.
_TABS_KEYBOARD_JS = '''<script>
// Phase 25 D-18: WAI-ARIA tabs roving tabindex + arrow-key navigation.
(function () {
  function bindTablist(navEl) {
    var tabs = Array.from(navEl.querySelectorAll('[role="tab"]'));
    if (tabs.length === 0) return;
    navEl.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' && e.key !== 'Home' && e.key !== 'End') return;
      var current = tabs.indexOf(document.activeElement);
      if (current < 0) return;
      var next = current;
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
    document.querySelectorAll('nav[role="tablist"]').forEach(bindTablist);
  });
  document.body.addEventListener('htmx:afterSwap', function () {
    document.querySelectorAll('nav[role="tablist"]').forEach(bindTablist);
  });
})();
</script>
'''


# Phase 25 D-07 Plan 06: one-shot 08:01 AEST status-strip refresh.
# 08:01 AEST = 22:01 UTC (previous UTC day; AEST is UTC+10). Fixed offset — no browser TZ.
# Fires htmx 'refresh' event on #status-strip, which hx-trigger="refresh" catches.
# Re-arms for the next day after firing so the tab stays live indefinitely.
_STATUS_STRIP_REFRESH_JS = '''<script>
// Phase 25 D-07: schedule one-shot status-strip refresh at 08:01 AEST.
// 08:01 AEST = 22:01 UTC. Fixed offset; ignores browser local TZ.
(function () {
  function msToNext0801Utc() {
    var now = Date.now();
    var d = new Date(now);
    var target = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 22, 1, 0, 0);
    if (target <= now) target += 86400000;
    return target - now;
  }
  function fireStatusStripRefresh() {
    var el = document.getElementById('status-strip');
    if (el && window.htmx) {
      window.htmx.trigger(el, 'refresh');
    }
    // Re-arm for next day.
    setTimeout(fireStatusStripRefresh, msToNext0801Utc());
  }
  document.addEventListener('DOMContentLoaded', function () {
    setTimeout(fireStatusStripRefresh, msToNext0801Utc());
  });
})();
</script>
'''


# Phase 25 D-19 #1: sync aria-expanded with <details> open state for SR users.
# Binds on DOMContentLoaded (initial load) and after every htmx:afterSwap (fragments).
# Uses a data-ariaSyncBound marker to avoid duplicate toggle listeners after re-bind.
_DETAILS_ARIA_SYNC_JS = """<script>
// Phase 25 D-19 #1: sync aria-expanded with <details> open state for SR users.
(function () {
  function syncAriaExpanded(el) {
    el.setAttribute('aria-expanded', el.open ? 'true' : 'false');
  }
  function bindAll() {
    document.querySelectorAll('details').forEach(function (d) {
      syncAriaExpanded(d);
      // Avoid duplicate toggle listeners after re-bind: store a marker.
      if (!d.dataset.ariaSyncBound) {
        d.addEventListener('toggle', function () { syncAriaExpanded(d); });
        d.dataset.ariaSyncBound = '1';
      }
    });
  }
  document.addEventListener('DOMContentLoaded', bindAll);
  document.body.addEventListener('htmx:afterSwap', bindAll);
})();
</script>
"""


def render_html_shell(ctx: RenderContext, body: str) -> str:  # noqa: ARG001
  '''UI-SPEC §Component Hierarchy — <!DOCTYPE> + <head> + Chart.js + HTMX + inline CSS + <body>.

  Phase 32 Plan 01: body replaced with the ACTIVE content from
  dashboard_legacy/page_body._render_html_shell (verbatim). The previous dead
  implementation emitted 4 JS blocks; the active implementation emits ONLY
  _DETAILS_ARIA_SYNC_JS to preserve byte-identity with golden.html.
  The constants _AWST_COUNTDOWN_JS, _STATUS_STRIP_REFRESH_JS, _TABS_KEYBOARD_JS
  remain defined in this module for nav/status-strip consumers but are NOT
  emitted by this function.

  Chart.js 4.4.6 loads in <head> with SRI. Phase 14 adds HTMX 1.9.12 SRI-pinned
  AFTER Chart.js (UI-SPEC §HTMX vendor pin / load location: "<head> after Chart.js,
  before inline <style>"), plus the inline handleTradesError JS handler for
  hx-on::after-request 4xx surfacing (UI-SPEC §Decision 4 — only client-side
  script Phase 14 ships beyond HTMX itself).

  The inline chart-instantiation <script> is IN the body (emitted by
  _render_equity_chart_container). Single-file, inline CSS, no external
  stylesheet (DASH-01).

  Phase 14 UI-SPEC §Decision 3: emits <div id="confirmation-banner"> at the
  top of the body wrapper as the OOB swap target for success messages from
  /trades/* responses.
  '''
  return (
    '<!DOCTYPE html>\n'
    '<html lang="en">\n'
    '<head>\n'
    '  <meta charset="utf-8">\n'
    '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
    '  <title>Trading Signals — Dashboard</title>\n'
    f'  <script src="{_CHARTJS_URL}" '
    f'integrity="{_CHARTJS_SRI}" crossorigin="anonymous"></script>\n'
    f'  <script src="{_HTMX_URL}" '
    f'integrity="{_HTMX_SRI}" crossorigin="anonymous"></script>\n'
    # REVIEW CR-01: json-enc converts form-encoded body to JSON for FastAPI
    # Pydantic body parsing. Loads AFTER core HTMX so the extension can
    # register itself; activated per-form via hx-ext="json-enc".
    f'  <script src="{_HTMX_JSON_ENC_URL}" '
    f'integrity="{_HTMX_JSON_ENC_SRI}" crossorigin="anonymous"></script>\n'
    '  <script>\n'
    + _HANDLE_TRADES_ERROR_JS +
    _TRACE_TOGGLE_JS +
    '  </script>\n'
    f'  <style>{_INLINE_CSS}</style>\n'
    '</head>\n'
    '<body>\n'
    '  <div class="container">\n'
    '    <div id="confirmation-banner"></div>\n'
    f'{body}'
    '  </div>\n'
    # Phase 25 D-19 #1: sync aria-expanded with <details> open state for SR users.
    # Appended at end of body per D-02 inline-script pattern.
    + _DETAILS_ARIA_SYNC_JS +
    '</body>\n'
    '</html>\n'
  )


def _render_page_body(ctx: RenderContext, page: str) -> tuple[str, str, str, str, Callable[[], str]]:
  '''Render one dashboard tab body from RenderContext.

  Phase 3: page composition consumes RenderContext across boundaries so callers
  no longer thread state/strategy_version primitives independently.
  Phase 26 B1: forwards ctx.active_market to per-market renderers so each
  /markets/{M}/{fn} GET only renders M's panels.

  Returns a 5-tuple: (section_id, heading_id, heading_text, heading_cls, render_fn).
  Note: annotation was `-> str` in the legacy source (a documentation bug);
  fixed here per 32-01 PLAN §Pitfall 2.

  H-02: Wave-2 components (account) are imported LOCAL inside the callable
  body so `import dashboard_renderer.shell` succeeds before Wave 2 runs.
  '''
  from dashboard_renderer.components.footer import render_footer as _render_footer
  from dashboard_renderer.components.header import _render_equity_chart_container
  from dashboard_renderer.components.positions import (
    _render_drift_banner,
    _render_trailing_stop_guidance,
  )
  from dashboard_renderer.components.settings import (
    render_add_market_form as _render_add_market_form,
    render_market_test_tab as _render_market_test_tab,
    render_settings_tab as _render_settings_tab,
  )
  from dashboard_renderer.components.signals import render_signal_cards as _render_signal_cards

  state = ctx.state
  active_market = getattr(ctx, 'active_market', None)

  def _account_body() -> str:
    # LOCAL — Wave-2 dep: dashboard_renderer/components/account.py created in plan 32-02+
    from dashboard_renderer.components.account import _render_account_management_region
    return _render_account_management_region(state)

  def _paper_trades_body() -> str:
    # LOCAL — Wave-2 dep: full paper_trades absorption in plan 32-02+
    from dashboard_renderer.components.paper_trades import render_paper_trades_region as _rptr
    return _rptr(state)

  page_map = {
    'signals': (
      'signals-tab',
      'signals-tab-heading',
      'Signals',
      'visually-hidden',
      lambda: (
        # Market switching is done via the tab strip in render_two_axis_nav
        # (Plan 25-03); the old <select> picker was removed in Phase 25 D-19 #4
        # and the helper deleted in Phase 26 Plan 26-08.
        # Phase 38: pass per-user news state for news panel injection.
        _render_signal_cards(
          state,
          active_market=active_market,
          uid=getattr(ctx, 'uid', None),
          news_dismissed=getattr(ctx, 'news_dismissed', {}),
          news_panel_collapsed=getattr(ctx, 'news_panel_collapsed', {}),
        )
        + _paper_trades_body()
        + _render_trailing_stop_guidance(state, uid=getattr(ctx, 'uid', None))
        + _render_equity_chart_container(state)
        + _render_drift_banner(state)
      ),
    ),
    'account': (
      'account-tab',
      'account-tab-heading',
      'Account',
      '',
      _account_body,
    ),
    'settings': (
      'settings-tab',
      'settings-tab-heading',
      'Settings',
      '',
      lambda: _render_settings_tab(state, active_market=active_market) + _render_add_market_form(state),
    ),
    'market-test': (
      'market-test-tab',
      'market-test-tab-heading',
      'Market Test',
      '',
      lambda: _render_market_test_tab(state, active_market=active_market),
    ),
  }
  return page_map.get(page, page_map['signals'])


def _render_tabbed_dashboard(ctx: RenderContext) -> str:
  from dashboard_renderer.components.footer import render_footer as _render_footer
  from dashboard_renderer.components.nav import render_two_axis_nav
  _, _, _, _, render_signals = _render_page_body(ctx, 'signals')
  _, _, _, _, render_account = _render_page_body(ctx, 'account')
  _, _, _, _, render_settings = _render_page_body(ctx, 'settings')
  _, _, _, _, render_market_test = _render_page_body(ctx, 'market-test')
  # Phase 25: two-axis nav replaces the flat single-nav. active_function defaults
  # to 'signals' for the multi-tab dashboard.html composite; active_market from ctx.
  active_function = getattr(ctx, 'active_function', 'signals')
  active_market = getattr(ctx, 'active_market', None)
  return (
    render_two_axis_nav(ctx.state, active_function, active_market)
    # Phase 25: market-panel wrapper for HTMX swap target. Encloses all
    # market-scoped tabs (signals, settings, market-test). Account is
    # market-agnostic and lives outside market-panel (D-04).
    + '<section id="market-panel" aria-live="polite">\n'
    '<section id="signals-tab" class="tab-panel" aria-labelledby="signals-tab-heading">\n'
    '  <h2 id="signals-tab-heading" class="visually-hidden">Signals</h2>\n'
    f'{render_signals()}'
    '</section>\n'
    '<section id="settings-tab" class="tab-panel" aria-labelledby="settings-tab-heading">\n'
    '  <h2 id="settings-tab-heading">Settings</h2>\n'
    f'{render_settings()}'
    '</section>\n'
    '<section id="market-test-tab" class="tab-panel" aria-labelledby="market-test-tab-heading">\n'
    '  <h2 id="market-test-tab-heading">Market Test</h2>\n'
    f'{render_market_test()}'
    '</section>\n'
    '</section>\n'
    '<section id="account-tab" class="tab-panel" aria-labelledby="account-tab-heading">\n'
    '  <h2 id="account-tab-heading">Account</h2>\n'
    f'{render_account()}'
    '</section>\n'
    + _render_footer(ctx.strategy_version)
  )


def _render_single_page_dashboard(
  ctx: RenderContext,
  page: str,
) -> str:
  from dashboard_renderer.components.footer import render_footer as _render_footer
  from dashboard_renderer.components.nav import render_two_axis_nav, _first_market_id
  selected = _render_page_body(ctx, page)
  section_id, heading_id, heading_text, heading_cls, render_body = selected
  body = render_body()
  heading_class_attr = f' class="{heading_cls}"' if heading_cls else ''

  # Phase 25: derive active_function/active_market from ctx (with fallbacks for
  # callers that don't pass the new kwargs — sibling regen path uses page-derived
  # active_function and first-market default).
  active_function = getattr(ctx, 'active_function', None) or page
  if active_function not in ('signals', 'account', 'settings', 'market-test'):
    active_function = 'signals'
  active_market = getattr(ctx, 'active_market', None)
  if active_market is None and active_function != 'account':
    active_market = _first_market_id(ctx.state)

  nav_html = render_two_axis_nav(ctx.state, active_function, active_market)

  # Wrap per-market content in <section id="market-panel"> for HTMX swap target.
  # Account is market-agnostic — no market-panel wrapper (D-04).
  inner = (
    f'<section id="{section_id}" class="tab-panel" aria-labelledby="{heading_id}">\n'
    + f'  <h2 id="{heading_id}"{heading_class_attr}>{heading_text}</h2>\n'
    + body
    + '</section>\n'
  )
  if active_function != 'account':
    inner = f'<section id="market-panel" aria-live="polite">\n{inner}</section>\n'

  return nav_html + inner + _render_footer(ctx.strategy_version)
