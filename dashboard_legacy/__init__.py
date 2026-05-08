"""dashboard_legacy — page-body orchestration + operator-form renderers.

Extracted from dashboard.py (Plan 27-14, Strategy B). The dashboard_renderer/
package owns component-level rendering; this package owns the legacy
page-body orchestration + operator forms + paper-trade subsections + account
region + Phase 17 trace panels + Phase 15 calc rows.

Hex-boundary preserved: stdlib + pytz + dashboard_renderer + system_params.
No imports from signal_engine / data_fetcher / notifier / main / numpy /
pandas / yfinance / requests at module top. Local sizing_engine + pnl_engine
imports inside function bodies preserved (C-2).
"""
from dashboard_legacy.render_helpers import (
    _CONTRACT_SPECS,
    _DEFAULT_STRATEGY_VERSION,
    _EXIT_REASON_DISPLAY,
    _INSTRUMENT_DISPLAY_NAMES,
    _SEED_LENGTHS,
    _SIGNAL_COLOUR,
    _SIGNAL_LABEL,
    _TRACE_FORMULAS,
    _TRACE_OPEN_PLACEHOLDER,
    _TRACE_TOGGLE_JS,
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
    TRAIL_MULT_LONG,
    TRAIL_MULT_SHORT,
)
from dashboard_legacy.trace_panels import (
    _INDICATOR_DISPLAY_NAMES,
    _INDICATOR_DISPLAY_ORDER,
    _render_trace_indicators,
    _render_trace_inputs,
    _render_trace_panels,
    _render_trace_vote,
)
from dashboard_legacy.section_renderers import (
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
from dashboard_legacy.positions_section import (
    _render_drift_banner,
    _render_open_form,
    _render_positions_table,
    _render_single_position_row,
    _render_trades_table,
    _render_trailing_stop_guidance,
)
from dashboard_legacy.calc_rows import (
    _render_calc_row,
    _render_entry_target_row,
)
from dashboard_legacy.paper_trades_section import (
    _render_alert_badge,
    _render_close_form_section,
    _render_paper_trades_closed,
    _render_paper_trades_open,
    _render_paper_trades_open_form,
    _render_paper_trades_region,
    _render_paper_trades_stats,
)
from dashboard_legacy.account_section import (
    _compute_account_stat_values,
    _render_account_balance_form,
    _render_account_management_region,
    _render_account_stats,
    _render_key_stats,
)
from dashboard_legacy.page_body import (
    _atomic_write_html,
    _render_html_shell,
    _render_page_body,
    _render_single_page_dashboard,
    _render_tabbed_dashboard,
)


# Plan 27-14: __all__ silences ruff F401 on every intentional re-export below.
# Same pattern Plan 27-12 used for notifier/__init__.py — explicit list of
# public surface beats per-line `# noqa: F401` clutter.
__all__ = [
    # render_helpers
    '_CONTRACT_SPECS', '_DEFAULT_STRATEGY_VERSION', '_EXIT_REASON_DISPLAY',
    '_INSTRUMENT_DISPLAY_NAMES', '_SEED_LENGTHS', '_SIGNAL_COLOUR',
    '_SIGNAL_LABEL', '_TRACE_FORMULAS', '_TRACE_OPEN_PLACEHOLDER',
    '_TRACE_TOGGLE_JS', '_VALID_TRACE_INSTRUMENT_KEYS',
    '_compute_aggregate_stats', '_compute_max_drawdown', '_compute_sharpe',
    '_compute_total_return', '_compute_trail_stop_display',
    '_compute_unrealised_pnl_display', '_compute_win_rate', '_display_names',
    '_enabled_market_registry', '_fmt_currency', '_fmt_em_dash',
    '_fmt_last_updated', '_fmt_percent_signed', '_fmt_percent_unsigned',
    '_fmt_pnl_with_colour', '_format_indicator_value', '_market_registry',
    '_resolve_strategy_version', '_resolve_trace_open_keys',
    '_strategy_settings_for', 'TRAIL_MULT_LONG', 'TRAIL_MULT_SHORT',
    # trace_panels
    '_INDICATOR_DISPLAY_NAMES', '_INDICATOR_DISPLAY_ORDER',
    '_render_trace_indicators', '_render_trace_inputs',
    '_render_trace_panels', '_render_trace_vote',
    # section_renderers
    '_distinct_equity_tuples', '_render_add_market_form',
    '_render_equity_chart_container', '_render_footer', '_render_header',
    '_render_header_ctx', '_render_market_test_tab', '_render_session_note',
    '_render_settings_tab', '_render_signal_cards', '_render_signout_button',
    # positions_section
    '_render_drift_banner', '_render_open_form', '_render_positions_table',
    '_render_single_position_row', '_render_trades_table',
    '_render_trailing_stop_guidance',
    # calc_rows
    '_render_calc_row', '_render_entry_target_row',
    # paper_trades_section
    '_render_alert_badge', '_render_close_form_section',
    '_render_paper_trades_closed', '_render_paper_trades_open',
    '_render_paper_trades_open_form', '_render_paper_trades_region',
    '_render_paper_trades_stats',
    # account_section
    '_compute_account_stat_values', '_render_account_balance_form',
    '_render_account_management_region', '_render_account_stats',
    '_render_key_stats',
    # page_body
    '_atomic_write_html', '_render_html_shell', '_render_page_body',
    '_render_single_page_dashboard', '_render_tabbed_dashboard',
]
