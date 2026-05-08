r'''Dashboard renderer — re-export shim around dashboard_legacy + dashboard_renderer.

Plan 27-14 (file-size hygiene): the prior 2221 LOC monolith was split into the
`dashboard_legacy/` package along clean seams (page_body, render_helpers,
section_renderers, trace_panels, positions_section, calc_rows,
paper_trades_section, account_section). This module is the public surface +
re-export shim every legacy caller (web/routes, main.py, tests) imports.

Public API (D-01; Phase 26 Plan 06 R2 rename — preserved):
  render_dashboard_files(state, out_path=Path('dashboard.html'), now=None,
                         is_cookie_session=None, trace_open_keys=None) -> None
  render_dashboard_page(state, page, out_path=Path('dashboard.html'), now=None,
                        is_cookie_session=None, trace_open_keys=None) -> None
  render_dashboard       — back-compat alias for render_dashboard_files

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. Peer of state_manager,
data_fetcher, and notifier. Must NOT import signal_engine, sizing_engine,
data_fetcher, notifier, main, numpy, pandas, yfinance, or requests at module
top. AST blocklist in tests/test_signal_engine.py::TestDeterminism enforces
this structurally via FORBIDDEN_MODULES_DASHBOARD.

XSS posture (Plan 27-08 preserved post-split): every dynamic value flows
through html.escape(value, quote=True) at the leaf render site. Quote=True is
the codebase contract — see tests/test_html_xss_audit.py for the AST gate.

Last-crash banner (Plan 27-11 preserved post-split): rendered by
dashboard_renderer/components/header.render_last_crash_banner inside
render_header — wired transitively when dashboard_legacy.section_renderers
forwards to dashboard_renderer.

Signal-shape invariant (Plan 27-09 preserved post-split): state['signals'][...]
is dict-only post v9->v10 migration; no bare-int defensives in renderer.

Clock injection (D-01): render_dashboard_files accepts now=None. When None,
pytz.timezone('Australia/Perth').localize(datetime.now())  is used. Tests
pass an aware FROZEN_NOW for byte-identical golden snapshots.
'''
import logging
import os  # noqa: F401 — load-bearing module attribute (tests do `patch('dashboard.os.replace', ...)`)
from datetime import datetime  # noqa: F401 — type-hint surface for callers
from pathlib import Path

from state_manager import (
    load_state,  # noqa: F401 — CLI convenience path; prod uses caller-supplied state
)

# =========================================================================
# Module logger — name preserved as 'dashboard' for journalctl + test capture
# =========================================================================
logger = logging.getLogger(__name__)


# =========================================================================
# Shell constants — re-exported from dashboard_renderer/assets.py (D-02)
# =========================================================================
from dashboard_renderer.assets import (  # noqa: E402, F401 — public re-exports
    _CHARTJS_SRI,
    _CHARTJS_URL,
    _HANDLE_TRADES_ERROR_JS,
    _HTMX_JSON_ENC_SRI,
    _HTMX_JSON_ENC_URL,
    _HTMX_SRI,
    _HTMX_URL,
    _INLINE_CSS,
    _TRACE_TOGGLE_JS,
)
from dashboard_renderer.shell import (  # noqa: E402, F401 — public re-exports
    _DETAILS_ARIA_SYNC_JS as _DETAILS_ARIA_SYNC_INLINE_JS,
)


# =========================================================================
# Public API — D-01
# =========================================================================

def render_dashboard_files(
  state: dict,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
  is_cookie_session: bool | None = None,
  trace_open_keys: list | None = None,  # Phase 17 D-04 — None=all-collapsed default
) -> None:
  '''Compatibility wrapper; primary orchestration lives in dashboard_renderer.api.

  Phase 26 Plan 06 (R2): renamed from render_dashboard → render_dashboard_files
  to match the split entrypoint in dashboard_renderer.api. Pure file-write,
  returns None per annotation. The deprecated `render_dashboard` alias below
  preserves test/legacy callers.
  '''
  from dashboard_renderer.api import render_dashboard_files as dr_render_dashboard_files

  dr_render_dashboard_files(
    state,
    out_path=out_path,
    now=now,
    is_cookie_session=is_cookie_session,
    trace_open_keys=trace_open_keys,
  )


def render_dashboard_page(
  state: dict,
  page: str,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
  is_cookie_session: bool | None = None,
  trace_open_keys: list | None = None,
) -> None:
  '''Compatibility wrapper; primary orchestration lives in dashboard_renderer.api.'''
  from dashboard_renderer.api import render_dashboard_page as dr_render_dashboard_page

  dr_render_dashboard_page(
    state,
    page=page,
    out_path=out_path,
    now=now,
    is_cookie_session=is_cookie_session,
    trace_open_keys=trace_open_keys,
  )


# =========================================================================
# dashboard_legacy re-exports — every name historically reachable via
# `dashboard.X` or `from dashboard import X` continues to work post-split.
# =========================================================================
from dashboard_legacy.render_helpers import (  # noqa: E402, F401
    _CONTRACT_SPECS,
    _DEFAULT_STRATEGY_VERSION,
    _EXIT_REASON_DISPLAY,
    _INSTRUMENT_DISPLAY_NAMES,
    _SEED_LENGTHS,
    _SIGNAL_COLOUR,
    _SIGNAL_LABEL,
    _TRACE_FORMULAS,
    _TRACE_OPEN_PLACEHOLDER,
    _VALID_TRACE_INSTRUMENT_KEYS,
    _compute_aggregate_stats,
    _compute_max_drawdown,
    _compute_sharpe,
    _compute_total_return,
    _compute_trail_stop_display,
    _compute_unrealised_pnl_display,
    _compute_win_rate,
    _display_names,
    _enabled_market_registry,
    _fmt_currency,
    _fmt_em_dash,
    _fmt_last_updated,
    _fmt_percent_signed,
    _fmt_percent_unsigned,
    _fmt_pnl_with_colour,
    _format_indicator_value,
    _market_registry,
    _resolve_strategy_version,
    _resolve_trace_open_keys,
    _strategy_settings_for,
)
from dashboard_legacy.trace_panels import (  # noqa: E402, F401
    _INDICATOR_DISPLAY_NAMES,
    _INDICATOR_DISPLAY_ORDER,
    _render_trace_indicators,
    _render_trace_inputs,
    _render_trace_panels,
    _render_trace_vote,
)
from dashboard_legacy.section_renderers import (  # noqa: E402, F401
    _distinct_equity_tuples,
    _render_add_market_form,
    _render_equity_chart_container,
    _render_footer,
    _render_header,
    _render_header_ctx,
    _render_market_test_tab,
    _render_session_note,
    _render_settings_tab,
    _render_signal_cards,
    _render_signout_button,
)
from dashboard_legacy.positions_section import (  # noqa: E402, F401
    _render_drift_banner,
    _render_open_form,
    _render_positions_table,
    _render_single_position_row,
    _render_trades_table,
    _render_trailing_stop_guidance,
)
from dashboard_legacy.calc_rows import (  # noqa: E402, F401
    _render_calc_row,
    _render_entry_target_row,
)
from dashboard_legacy.paper_trades_section import (  # noqa: E402, F401
    _render_alert_badge,
    _render_close_form_section,
    _render_paper_trades_closed,
    _render_paper_trades_open,
    _render_paper_trades_open_form,
    _render_paper_trades_region,
    _render_paper_trades_stats,
)
from dashboard_legacy.account_section import (  # noqa: E402, F401
    _compute_account_stat_values,
    _render_account_balance_form,
    _render_account_management_region,
    _render_account_stats,
    _render_key_stats,
)
from dashboard_legacy.page_body import (  # noqa: E402, F401
    _atomic_write_html,
    _render_html_shell,
    _render_page_body,
    _render_single_page_dashboard,
    _render_tabbed_dashboard,
)


# Phase 26 Plan 06 back-compat: legacy test callers still reference
# dashboard.render_dashboard. Alias is an assignment (not a `def`).
render_dashboard = render_dashboard_files  # noqa: F811 — back-compat alias


if __name__ == '__main__':
  # CONTEXT D-05 convenience CLI. `python -m dashboard` loads the current
  # state.json and renders dashboard.html using the current AWST wall-clock.
  render_dashboard_files(load_state(), Path('dashboard.html'))
