"""dashboard_legacy.page_body — page-level orchestration + HTML shell + atomic write.

Extracted from dashboard.py (Plan 27-14). Owns the <!DOCTYPE>...<body> shell,
tabbed/single-page composition, and the atomic write primitive.
"""
import logging
import os  # noqa: F401 — re-exported via dashboard.py shim for monkeypatch test surface
from pathlib import Path

from dashboard_renderer.assets import (
    _CHARTJS_SRI,
    _CHARTJS_URL,
    _HANDLE_TRADES_ERROR_JS,
    _HTMX_JSON_ENC_SRI,
    _HTMX_JSON_ENC_URL,
    _HTMX_SRI,
    _HTMX_URL,
)
from dashboard_renderer.assets import _INLINE_CSS
from dashboard_renderer.assets import _TRACE_TOGGLE_JS
from dashboard_renderer.context import RenderContext
from dashboard_renderer.io import atomic_write_html as dr_atomic_write_html
from dashboard_renderer.shell import _DETAILS_ARIA_SYNC_JS as _DETAILS_ARIA_SYNC_INLINE_JS

# Imports from sibling daughter modules used by _render_page_body composition.
from dashboard_legacy.account_section import _render_account_management_region
from dashboard_legacy.paper_trades_section import _render_paper_trades_region
from dashboard_legacy.positions_section import _render_drift_banner, _render_trailing_stop_guidance
from dashboard_legacy.render_helpers import _resolve_strategy_version  # noqa: F401
from dashboard_legacy.section_renderers import (
    _render_add_market_form,
    _render_equity_chart_container,
    _render_footer,
    _render_market_test_tab,
    _render_settings_tab,
    _render_signal_cards,
)

logger = logging.getLogger(__name__)


def _render_page_body(ctx: RenderContext, page: str) -> str:
  '''Render one dashboard tab body from RenderContext.

  Phase 3: page composition consumes RenderContext across boundaries so callers
  no longer thread state/strategy_version primitives independently.
  Phase 26 B1: forwards ctx.active_market to per-market renderers so each
  /markets/{M}/{fn} GET only renders M's panels.
  '''
  state = ctx.state
  active_market = getattr(ctx, 'active_market', None)
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
        _render_signal_cards(state, active_market=active_market)
        + _render_paper_trades_region(state)
        + _render_trailing_stop_guidance(state)
        + _render_equity_chart_container(state)
        + _render_drift_banner(state)
      ),
    ),
    'account': (
      'account-tab',
      'account-tab-heading',
      'Account',
      '',
      lambda: _render_account_management_region(state),
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

def _render_html_shell(ctx: RenderContext, body: str) -> str:  # noqa: ARG001
  '''UI-SPEC §Component Hierarchy — <!DOCTYPE> + <head> + Chart.js + HTMX + inline CSS + <body>.

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
    + _DETAILS_ARIA_SYNC_INLINE_JS +
    '</body>\n'
    '</html>\n'
  )

def _atomic_write_html(data: str, path: Path) -> None:
  '''Mirror of state_manager._atomic_write (Phase 3 D-17 post-replace parent-dir fsync).

  Durability sequence:
    1. write data to tempfile in same directory as target
    2. flush + fsync(tempfile.fileno())  — data durable on disk
    3. close tempfile (NamedTemporaryFile context exit)
    4. os.replace(tempfile, target)      — atomic rename
    5. fsync(parent dir fd) on POSIX     — rename itself durable on disk

  Tempfile cleanup: try/finally unlinks the tempfile if any step before
  os.replace raises. On success, tmp_path_str is set to None so the finally
  clause is a no-op.

  C-7 reviews: `newline='\\n'` on the tempfile forces LF regardless of
  platform — text-mode default on Windows translates `\\n` -> `\\r\\n`
  which would drift the committed goldens (byte-stability gate).
  '''
  dr_atomic_write_html(data, path)
