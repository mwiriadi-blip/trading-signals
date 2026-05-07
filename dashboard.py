r'''Dashboard renderer — self-contained single-file HTML I/O hex.

Owns dashboard.html at the repo root and exposes a single public function:
  render_dashboard.

DASH-01..09 (REQUIREMENTS.md §Dashboard). Reads state.json (caller-supplied
state dict) and writes a single-file, self-contained HTML report to disk via
atomic tempfile + fsync + os.replace. Chart.js 4.4.6 UMD loads client-side
from jsDelivr with SRI integrity check (D-12). All other assets (CSS, fonts,
scripts) are inline — no external network requests except Chart.js.

Public surface (D-01):
  render_dashboard(state: dict, out_path: Path = Path('dashboard.html'),
                   now: datetime | None = None) -> None

Private helpers (Waves 1/2 fill bodies — Wave 0 is scaffold):
  _render_header           UI-SPEC §Header
  _render_signal_cards     UI-SPEC §Signal cards (D-02, DASH-03)
  _render_positions_table  UI-SPEC §Open positions table (DASH-05, B-1)
  _render_trades_table     UI-SPEC §Closed trades table (DASH-06)
  _render_key_stats        UI-SPEC §Key stats block (DASH-07)
  _render_footer           UI-SPEC §Footer disclaimer
  _render_equity_chart_container  UI-SPEC §Chart Component (DASH-04)
  _render_html_shell       <!DOCTYPE> + <head> + Chart.js script + CSS + <body>

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. Peer of state_manager,
data_fetcher, and (future) notifier. Must NOT import signal_engine,
sizing_engine, data_fetcher, notifier, main, numpy, pandas, yfinance, or
requests. AST blocklist in tests/test_signal_engine.py::TestDeterminism
enforces this structurally via FORBIDDEN_MODULES_DASHBOARD.

Allowed imports (D-01 allowlist): stdlib (html, json, logging, math, os,
statistics, tempfile, datetime, pathlib) + pytz + state_manager (for
load_state CLI convenience path only — production render is invoked by
main.py with a pre-loaded state dict) + system_params (palette-adjacent
contract constants + INITIAL_ACCOUNT + TRAIL_MULT_*).

XSS posture: every dynamic value flows through html.escape() at the leaf
render site (per-surface per C-5 revision). Chart.js script-context JSON
uses json.dumps + `.replace('</', r'<\/')` to defuse embedded `</script>`
sequences (RESEARCH Pitfall 1). Only palette + numeric series are
script-embedded — no user-controlled strings land in JS context.

Never-crash posture (D-06): render_dashboard failures are Wave 2's
responsibility. When wired from main.py in Phase 6, a raised
exception is caught at the orchestrator boundary and logged as [Dashboard]
— the email/ schedule path MUST NOT be blocked by a render failure.

Clock injection (D-01): render_dashboard accepts now=None. When None,
dashboard.py's internal normalisation uses
`pytz.timezone('Australia/Perth').localize(datetime.now())` to produce the
"Last updated" header stamp. Tests pass an aware FROZEN_NOW constant for
byte-identical golden snapshots. C-1 reviews: never construct via
`datetime(..., tzinfo=pytz.timezone(...))` — that silently adopts a
historical LMT offset (+07:43:24 for Perth pre-1895). Always use
`.localize()`.

Wave 0 (landed 2026-04-22, commit 038af29): all 9 helpers are stubs; palette +
Chart.js SRI + _INLINE_CSS :root vars are locked in place so Wave 1 can
append per-block render output against a fixed contract.

Wave 1 (landed 2026-04-22): filled 6 per-block renderers (header, signal_cards,
positions_table, trades_table, key_stats, footer) + 4 stats helpers + 2 inline
display-math helpers + 6 formatters. Three stubs remain for Wave 2:
_render_equity_chart_container, _render_html_shell, and render_dashboard.
'''
import html  # noqa: F401 — Wave 1 per-surface escape at leaf render sites
import json  # noqa: F401 — Wave 2 script-context data serialisation
import logging
import math  # noqa: F401 — Wave 1 stats (isfinite guards) and format helpers
import os  # noqa: F401 — Wave 2 _atomic_write_html (tempfile + fsync + os.replace)
import statistics  # noqa: F401 — Wave 1 Sharpe / drawdown via stdlib only
import tempfile  # noqa: F401 — Wave 2 _atomic_write_html
from datetime import datetime  # noqa: F401 — Wave 1 header timestamp, Wave 2 render_dashboard
from pathlib import Path

import pytz  # noqa: F401 — Wave 1 Australia/Perth localisation

from dashboard_renderer import formatters as dr_formatters
from dashboard_renderer import stats as dr_stats
from dashboard_renderer.context import RenderContext
from dashboard_renderer.components.footer import render_footer as dr_render_footer
from dashboard_renderer.components.header import render_header as dr_render_header
from dashboard_renderer.components.header import (
  render_header_from_context as dr_render_header_from_context,
)
from dashboard_renderer.components.paper_trades import (
  render_paper_trades_region as dr_render_paper_trades_region,
)
from dashboard_renderer.components.positions import (
  render_positions_table as dr_render_positions_table,
)
from dashboard_renderer.components.settings import (
  render_add_market_form as dr_render_add_market_form,
  render_market_test_tab as dr_render_market_test_tab,
  render_settings_tab as dr_render_settings_tab,
)
from dashboard_renderer.components.signals import (
  render_signal_cards as dr_render_signal_cards,
)
from dashboard_renderer.components.trades import render_trades_table as dr_render_trades_table
from dashboard_renderer.io import atomic_write_html as dr_atomic_write_html
from state_manager import (
  load_state,  # noqa: F401 — CLI convenience path; prod uses caller-supplied state
)
from system_params import (  # noqa: F401 — Wave 1 contract specs + trail multipliers; Phase 6 Wave 0 palette retrofit
  _COLOR_BG,
  _COLOR_BORDER,
  _COLOR_FLAT,
  _COLOR_LONG,
  _COLOR_SHORT,
  _COLOR_SURFACE,
  _COLOR_TEXT,
  _COLOR_TEXT_DIM,
  _COLOR_TEXT_MUTED,
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  DEFAULT_MARKETS,
  DEFAULT_STRATEGY_SETTINGS,
  FALLBACK_CONTRACT_SPECS,
  INITIAL_ACCOUNT,
  SPI_COST_AUD,
  SPI_MULT,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
)

# =========================================================================
# Module logger
# =========================================================================

logger = logging.getLogger(__name__)


# =========================================================================
# Shell constants — Phase 25: re-exported from dashboard_renderer/assets.py (D-02).
# assets.py is now the single source of truth for CDN pins, JS helpers, and CSS.
# =========================================================================
from dashboard_renderer.assets import (
  _CHARTJS_URL,
  _CHARTJS_SRI,
  _HTMX_URL,
  _HTMX_SRI,
  _HTMX_JSON_ENC_URL,
  _HTMX_JSON_ENC_SRI,
)

# Phase 14 UI-SPEC §Decision 4: _HANDLE_TRADES_ERROR_JS re-exported from assets.py (Phase 25).
from dashboard_renderer.assets import _HANDLE_TRADES_ERROR_JS  # noqa: F811

# Phase 25 D-19 #1: aria-expanded sync JS (imported from shell.py constant).
from dashboard_renderer.shell import _DETAILS_ARIA_SYNC_JS as _DETAILS_ARIA_SYNC_INLINE_JS  # noqa: E501



# =========================================================================
# Display-name + contract-spec dicts — Wave 1 lookup sources
# =========================================================================

_INSTRUMENT_DISPLAY_NAMES = {
  'SPI200': 'SPI 200',
  'AUDUSD': 'AUD / USD',
}

# Phase 8 IN-05: _CONTRACT_SPECS is now a re-export of
# system_params.FALLBACK_CONTRACT_SPECS — single source of truth shared with
# notifier.py. Local binding retained so existing call sites inside this
# module (and any out-of-tree consumers that imported the name) continue to
# work without churn.
_CONTRACT_SPECS = FALLBACK_CONTRACT_SPECS


def _market_registry(state: dict | None = None) -> dict:
  markets = (state or {}).get('markets')
  if not isinstance(markets, dict):
    return {key: dict(value) for key, value in DEFAULT_MARKETS.items()}
  merged = {key: dict(value) for key, value in DEFAULT_MARKETS.items()}
  for key, value in markets.items():
    if isinstance(value, dict):
      merged[key] = {**merged.get(key, {}), **value}
  return dict(sorted(
    merged.items(),
    key=lambda item: (item[1].get('sort_order', 999), item[0]),
  ))


def _enabled_market_registry(state: dict | None = None) -> dict:
  return {
    key: market for key, market in _market_registry(state).items()
    if market.get('enabled', True)
  }


def _display_names(state: dict | None = None) -> dict[str, str]:
  return {
    key: str(market.get('display_name') or key)
    for key, market in _enabled_market_registry(state).items()
  }


def _strategy_settings_for(state: dict, market_id: str) -> dict:
  settings = state.get('strategy_settings', {}).get(market_id, {})
  if not isinstance(settings, dict):
    settings = {}
  return {**DEFAULT_STRATEGY_SETTINGS, **settings}


# =========================================================================
# Inline CSS — Phase 25: re-exported from dashboard_renderer/assets.py (D-02).
# =========================================================================
from dashboard_renderer.assets import _INLINE_CSS  # noqa: F811

# =========================================================================
# Formatters — UI-SPEC §Format Helper Contracts + CONTEXT D-16
# _fmt_em_dash is placed first so _compute_* helpers can reference it for
# empty-state fallbacks. All formatters are pure (no state arg, no clock
# read, no side effects). _fmt_last_updated rejects naive datetimes per
# RESEARCH Pitfall 9 (naive now silently produces different bytes per CI
# runner timezone, breaking golden-snapshot determinism).
# =========================================================================

def _fmt_em_dash() -> str:
  '''UI-SPEC §Format Helper Contracts: single call site for the em-dash empty-value token.'''
  return dr_formatters.fmt_em_dash()


def _fmt_currency(value: float) -> str:
  '''UI-SPEC §Format Helper Contracts: $1,234.56 / -$567.89 / $0.00.'''
  return dr_formatters.fmt_currency(value)


def _fmt_percent_signed(fraction: float) -> str:
  '''UI-SPEC §Format Helper Contracts: +5.3% / -12.5% / +0.0%.'''
  return dr_formatters.fmt_percent_signed(fraction)


def _fmt_percent_unsigned(fraction: float) -> str:
  '''UI-SPEC §Format Helper Contracts: 58.3% / 12.5%. Input is a fraction.'''
  return dr_formatters.fmt_percent_unsigned(fraction)


def _fmt_pnl_with_colour(value: float) -> str:
  '''UI-SPEC §Format Helper Contracts + CONTEXT D-16: P&L span coloured by sign.'''
  return dr_formatters.fmt_pnl_with_colour(value)


def _fmt_last_updated(now: datetime) -> str:
  '''UI-SPEC §Format Helper Contracts + DASH-08: YYYY-MM-DD HH:MM AWST.'''
  return dr_formatters.fmt_last_updated(now)


# =========================================================================
# Phase 17 D-05 + D-06: indicator format helper (pure; math only)
# =========================================================================

def _format_indicator_value(
  value: float,
  seed_required: int,
  bars_available: int,
) -> str:
  '''Phase 17 D-05 + D-06: format a single indicator scalar for display.'''
  return dr_formatters.format_indicator_value(value, seed_required, bars_available)


# =========================================================================
# Stats math helpers — CONTEXT D-07 / D-08 / D-09 / D-10
# =========================================================================

def _compute_sharpe(state: dict) -> str:
  '''CONTEXT D-07: daily log-returns, rf=0, annualised × √252.'''
  return dr_stats.compute_sharpe(state, em_dash=_fmt_em_dash())


def _compute_max_drawdown(state: dict) -> str:
  '''CONTEXT D-08: rolling peak-to-trough %. Always <= 0.'''
  return dr_stats.compute_max_drawdown(state, em_dash=_fmt_em_dash())


def _compute_win_rate(state: dict) -> str:
  '''CONTEXT D-09: closed trades with gross_pnl > 0.'''
  return dr_stats.compute_win_rate(state, em_dash=_fmt_em_dash())


def _compute_total_return(state: dict) -> str:
  '''D-16 (Phase 8): use state["initial_account"] as the baseline.'''
  return dr_stats.compute_total_return(state)


def _compute_aggregate_stats(paper_trades=None, signals=None) -> dict:
  '''Phase 19 D-06 — compute 5-key aggregate stats for the sticky stats bar.

  Returns dict with keys: realised, unrealised, wins, losses, win_rate.
  Mutable-default avoided (planner trap): use None sentinels.

  pnl_engine is LOCAL-imported (mirrors sizing_engine convention — Phase 11 C-2
  + dashboard hex symmetry). dashboard.py does NOT import pnl_engine at module
  top per hex-boundary preservation.

  win_rate: wins / (wins + losses) * 100; '—' when denominator is 0.
  Zero realised_pnl rows are excluded from wins AND losses (CONTEXT D-06).
  Open rows with last_close=None or NaN skip unrealised contribution.
  '''
  return dr_stats.compute_aggregate_stats(paper_trades=paper_trades, signals=signals)


# =========================================================================
# Inline display-math helpers — UI-SPEC §Derived render-time calculations
# Re-implementation of sizing_engine formulas inline per CONTEXT D-01 hex
# fence. TestStatsMath::test_unrealised_pnl_matches_sizing_engine locks
# bit-identical output against sizing_engine.compute_unrealised_pnl on a
# shared fixture — drift surfaces as a red test.
# =========================================================================

def _compute_trail_stop_display(position: dict, settings: dict | None = None) -> float:
  '''UI-SPEC §Positions table Trail Stop formula. Anchors on position['atr_entry']
  (NOT today's ATR — matches sizing_engine D-15 semantics).

  LONG: peak_price - TRAIL_MULT_LONG * atr_entry (fallback: entry_price if peak_price None)
  SHORT: trough_price + TRAIL_MULT_SHORT * atr_entry (fallback: entry_price if trough_price None)

  Phase 14 D-09 + UI-SPEC §Decision 6: manual_stop precedence — when operator
  has set a stop via /trades/modify (position['manual_stop'] is not None),
  return that value directly. Mirrors sizing_engine.get_trailing_stop precedence
  (CLAUDE.md hex-lite lockstep). NaN guard on atr_entry runs FIRST so the
  parity test against sizing_engine.get_trailing_stop holds bit-identically
  for the NaN-pass-through case (B-1).

  Pitfall 5: position.get('manual_stop') so pre-migration position dicts
  (no key) silently fall through to computed.
  '''
  return dr_stats.compute_trail_stop_display(position, settings=settings)


def _compute_unrealised_pnl_display(
  position: dict, state_key: str, current_close: float | None,
  state: dict | None = None,
) -> float | None:
  '''UI-SPEC §Positions table Unrealised P&L formula. Inline re-implementation
  of sizing_engine.compute_unrealised_pnl per CONTEXT D-01 hex fence. Returns
  None when current_close is None (caller renders em-dash).

  Per CLAUDE.md §Operator Decisions / CONTEXT D-13: opening-half cost is
  deducted here (matches sizing_engine.compute_unrealised_pnl exactly —
  TestStatsMath::test_unrealised_pnl_matches_sizing_engine locks parity).

  Phase 8 WR-01 fix: prefer the operator-selected tier values from
  state['_resolved_contracts'][state_key]; fall back to the module-level
  _CONTRACT_SPECS defaults when state is None or lacks _resolved_contracts
  (pre-Phase-8 state shape or non-load_state callers like unit tests that
  build state dicts directly). Mirrors D-17 resolved-tier flow.
  '''
  if current_close is not None:
    has_resolved = state is not None and state.get('_resolved_contracts', {}).get(state_key) is not None
    if not has_resolved:
      logger.debug(
        '[Dashboard] _resolved_contracts missing for %s; falling back to '
        'module-level _CONTRACT_SPECS default tier', state_key,
      )
  return dr_stats.compute_unrealised_pnl_display(
    position=position,
    state_key=state_key,
    current_close=current_close,
    contract_specs=_CONTRACT_SPECS,
    state=state,
  )


# =========================================================================
# Render-helper lookups — signal label/colour maps + exit-reason display map
# =========================================================================

# Phase 22 D-06: dashboard fallback when no signal row carries strategy_version.
_DEFAULT_STRATEGY_VERSION = 'v1.0.0'

# =========================================================================
# Phase 17 D-13: trace panel constants (hex-boundary preserved — no imports
# from signal_engine, system_params, state_manager, etc.)
# =========================================================================

# D-13: indicator formula text catalogue (presentation-only, plain text).
# Lookup keys match state.signals[<inst>].indicator_scalars keys exactly.
# Inlined here per D-10: formula text is presentation, not logic; the
# engine's behaviour is pinned by tests/test_signal_engine.py independently.
_TRACE_FORMULAS: dict[str, str] = {
  'tr': 'TR = max(High - Low, |High - prev Close|, |Low - prev Close|)',
  'atr': 'ATR(14) = Wilder-smooth(TR, 14) - initial seed = SMA(TR, 14)',
  'plus_di': '+DI(20) = 100 * Wilder-smooth(+DM, 20) / ATR(20)',
  'minus_di': '-DI(20) = 100 * Wilder-smooth(-DM, 20) / ATR(20)',
  'adx': 'ADX(20) = 100 * Wilder-smooth(|+DI - -DI| / (+DI + -DI), 20)',
  'mom1': 'Mom1 = (Close_t - Close_{t-1}) / Close_{t-1}',
  'mom3': 'Mom3 = (Close_t - Close_{t-3}) / Close_{t-3}',
  'mom12': 'Mom12 = (Close_t - Close_{t-12}) / Close_{t-12}',
  'rvol': 'RVol(20) = Volume_t / SMA(Volume, 20)',
}

# D-06: seed window length per indicator. Hardcoded per D-10 (NOT imported
# from signal_engine — if the engine constants drift, the dashboard golden
# test surfaces the mismatch rather than silently rendering stale text).
_SEED_LENGTHS: dict[str, int] = {
  'tr': 1, 'atr': 14, 'plus_di': 20, 'minus_di': 20,
  'adx': 20, 'mom1': 2, 'mom3': 4, 'mom12': 13, 'rvol': 20,
}

# D-04: instrument keys whose <details open> we honour at the route-layer
# cookie read. Mirrors state.signals keys (SPI200, AUDUSD).
_VALID_TRACE_INSTRUMENT_KEYS: frozenset = frozenset({'SPI200', 'AUDUSD'})

# D-17 (PATTERNS.md §Pattern To Design From Scratch): attribute-level
# placeholder substitution. dashboard.py emits these literal strings inside
# each <details data-instrument="..."> opening tag at write time.
# web/routes/dashboard.py substitutes them per-request with ' open' or ''
# based on the tsi_trace_open cookie (allowlist-filtered).
# Note: attribute-level vs Phase 16.1's block-level placeholders — new design.
_TRACE_OPEN_PLACEHOLDER: dict[str, str] = {
  'SPI200': '{{TRACE_OPEN_SPI200}}',
  'AUDUSD': '{{TRACE_OPEN_AUDUSD}}',
}

# D-03 + D-12: _TRACE_TOGGLE_JS re-exported from assets.py (Phase 25).
from dashboard_renderer.assets import _TRACE_TOGGLE_JS  # noqa: F811

def _resolve_strategy_version(state: dict) -> str:
  '''Phase 22: extract the active strategy version from state.signals.

  Reads strategy_version off each dict-shaped signal row, picks the
  lexicographic max (str) when instruments disagree (transient migration
  window), defaults to 'v1.0.0' if no row carries the field. Emits a
  [State] WARN log for each dict-shaped row that lacks the field —
  surfaces silent migration drift in journalctl rather than rendering a
  spurious default.

  Hex-boundary (LEARNINGS 2026-04-27): dashboard.py does NOT import
  system_params.STRATEGY_VERSION. The version arrives via the state dict
  (which the orchestrator at main.py:1280 has already tagged on the most
  recent run). This preserves the rule "pass primitives, not module
  references, into render layer".

  Tie-break for cross-version states (e.g. SPI200=v1.1.0, AUDUSD=v1.2.0):
  lexicographic max of the strings starting with 'v'. For semver-formatted
  strings of the same MAJOR.MINOR.PATCH digit-width this matches numerical
  max. Cross-MAJOR comparisons are approximate; in practice instruments
  converge within one daily run after a bump.
  '''
  signals = state.get('signals', {})
  found: list[str] = []
  for sig in signals.values():
    if isinstance(sig, dict):
      if 'strategy_version' in sig:
        found.append(sig['strategy_version'])
      else:
        logger.warning(
          '[State] WARN signal row missing strategy_version field — '
          'defaulting to v1.0.0',
        )
  if not found:
    return _DEFAULT_STRATEGY_VERSION
  return max(found, key=str)


_SIGNAL_LABEL = {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}
_SIGNAL_COLOUR = {1: _COLOR_LONG, -1: _COLOR_SHORT, 0: _COLOR_FLAT}


def _resolve_trace_open_keys(
  state: dict,
  trace_open_keys: list,
) -> set:
  '''Phase 17 D-04: which per-instrument <details> render with the `open`
  attribute. Caller (web/routes/dashboard.py) computes the list from the
  tsi_trace_open cookie; this helper applies a defensive allowlist
  intersection against _VALID_TRACE_INSTRUMENT_KEYS AND against the keys
  actually present in state.signals.

  Hex-boundary preserved: reads only state-dict primitives + a list of
  strings; no module-attribute reads, no I/O, no auth.
  '''
  present_keys = set(state.get('signals', {}).keys())
  return {
    k for k in trace_open_keys
    if k in _VALID_TRACE_INSTRUMENT_KEYS and k in present_keys
  }

# Exit-reason display mapping (UI-SPEC §Closed trades table §Reason column).
# Unknown / unmapped values fall through raw (html.escape applied at render leaf).
_EXIT_REASON_DISPLAY = {
  'flat_signal': 'Signal flat',
  'signal_reversal': 'Reversal',
  'stop_hit': 'Stop hit',
  'adx_exit': 'ADX drop',
}


# =========================================================================
# Private render helpers — Wave 1 (header/signal_cards/positions/trades/
# key_stats/footer) + Wave 2 stubs (equity_chart_container/html_shell).
#
# D-15 XSS posture: every state-derived string (exit_reason, signal_as_of,
# dates, instrument display names) passes through html.escape(value,
# quote=True) at the LEAF interpolation site — never at intermediate concat
# (PATTERNS.md §XSS escape pattern, RESEARCH §Pattern 4).
# =========================================================================

def _render_signout_button() -> str:
  '''Phase 16.1 UI-SPEC §Surface 3: Sign Out button for cookie-session users.

  Form POSTs to /logout (the auth.py middleware lets /logout through via
  PUBLIC_PATHS, then web/routes/login.py::post_logout clears the cookie
  with attrs matching creation per global LEARNING).
  '''
  return (
    '<form method="POST" action="/logout" class="signout-form">'
    '<button type="submit" class="btn-signout" '
    'aria-label="Sign out of Trading Signals">Sign out</button>'
    '</form>'
  )


def _render_session_note() -> str:
  '''Phase 16.1 UI-SPEC §Surface 4 (E-01 generalised — Basic Auth removed).

  Shown in the header when the request did NOT carry a valid tsi_session
  cookie (i.e. the operator is authenticated via X-Trading-Signals-Auth
  header — usually a curl/script). Renders the no-op "close tabs" hint
  since there's no cookie to clear server-side.
  '''
  return (
    '<p class="session-note">'
    'Signed in via header — close browser tabs to sign out.'
    '</p>'
  )


def _render_header(
  state: dict, now: datetime, is_cookie_session: bool | None = None,
) -> str:  # noqa: ARG001 — state reserved for future
  '''UI-SPEC §Header — H1 "Trading Signals" + subtitle + Last-updated AWST.

  state is reserved for future use (e.g. surfacing schema_version); the live
  clock render uses the injected `now`. _fmt_last_updated raises ValueError on
  naive datetimes (Pitfall 9 golden-snapshot drift guard).

  Phase 16.1 — `is_cookie_session` 3-way semantics (LEARNING 2026-04-27 hex
  boundary: dashboard.py must NOT decode cookies; the auth signal arrives as
  a primitive bool computed by the caller):
    None  — emit the literal {{SIGNOUT_BUTTON}}{{SESSION_NOTE}} placeholders
            so web/routes/dashboard.py can substitute per request (matches
            the Phase 14 {{WEB_AUTH_SECRET}} pattern). This is what
            main.run_daily_check writes to disk.
    True  — render the Sign Out button inline (test path: direct
            render_dashboard(..., is_cookie_session=True)).
    False — render the session note inline (test path: header-auth flow).
  '''
  return dr_render_header(state, now, is_cookie_session=is_cookie_session)


def _render_header_ctx(
  ctx: RenderContext,
  is_cookie_session: bool | None = None,
) -> str:
  return dr_render_header_from_context(ctx, is_cookie_session=is_cookie_session)


def _render_trace_inputs(ohlc_window: list) -> str:
  '''Phase 17 D-02 + D-11: Inputs panel — rolling 40-bar OHLC table.

  Empty ohlc_window -> "Awaiting first daily run" placeholder per D-11.
  Non-empty -> one <tr data-row-index="N"> per bar, columns Date/Open/High/Low/Close.
  All leaf values pass through html.escape per T-17-03 (XSS defence-in-depth).
  '''
  if not ohlc_window:
    return (
      '<section class="trace-panel">\n'
      '  <p><em>Awaiting first daily run — calculations will appear after '
      'the next 08:00 AWST cycle.</em></p>\n'
      '</section>\n'
    )
  rows = []
  for i, entry in enumerate(ohlc_window):
    date_esc = html.escape(str(entry.get('date', '')), quote=True)
    open_esc = html.escape(f'{entry.get("open", 0.0):.2f}', quote=True)
    high_esc = html.escape(f'{entry.get("high", 0.0):.2f}', quote=True)
    low_esc = html.escape(f'{entry.get("low", 0.0):.2f}', quote=True)
    close_esc = html.escape(f'{entry.get("close", 0.0):.2f}', quote=True)
    rows.append(
      f'<tr data-row-index="{i}">'
      f'<td class="date">{date_esc}</td>'
      f'<td class="num">{open_esc}</td>'
      f'<td class="num">{high_esc}</td>'
      f'<td class="num">{low_esc}</td>'
      f'<td class="num">{close_esc}</td>'
      '</tr>\n'
    )
  return (
    '<section class="trace-panel">\n'
    '  <p class="eyebrow">INPUTS — OHLC WINDOW (40 bars)</p>\n'
    '  <table class="trace-ohlc-table">\n'
    '    <thead><tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th></tr></thead>\n'
    '    <tbody>\n'
    + ''.join(rows)
    + '  </tbody></table>\n'
    '</section>\n'
  )


# Fixed display order for indicator rows — matches _TRACE_FORMULAS key order.
_INDICATOR_DISPLAY_ORDER = ['tr', 'atr', 'plus_di', 'minus_di', 'adx', 'mom1', 'mom3', 'mom12', 'rvol']
_INDICATOR_DISPLAY_NAMES = {
  'tr': 'TR', 'atr': 'ATR(14)', 'plus_di': '+DI(20)', 'minus_di': '-DI(20)',
  'adx': 'ADX(20)', 'mom1': 'Mom1', 'mom3': 'Mom3', 'mom12': 'Mom12', 'rvol': 'RVol(20)',
}


def _render_trace_indicators(indicator_scalars: dict, bars_available: int) -> str:
  '''Phase 17 D-03 + D-05 + D-06: Indicators panel — one row per indicator
  with tap-to-toggle formula reveal.

  Each indicator row: name cell (cursor:pointer, data-formula-open="false",
  title=formula tooltip) + value cell (6-decimal or reason text).
  Followed immediately by a hidden formula-row for D-03 tap-to-toggle.

  Empty indicator_scalars: all 9 rows render with "n/a (need N bars, have 0)".
  '''
  rows = []
  for key in _INDICATOR_DISPLAY_ORDER:
    formula = _TRACE_FORMULAS.get(key, '')
    formula_esc = html.escape(formula, quote=True)
    display_name = _INDICATOR_DISPLAY_NAMES.get(key, key)
    name_esc = html.escape(display_name, quote=True)
    seed = _SEED_LENGTHS.get(key, 1)
    raw = indicator_scalars.get(key, float('nan'))
    value_str = _format_indicator_value(float(raw), seed, bars_available)
    value_esc = html.escape(value_str, quote=True)
    rows.append(
      f'<tr>'
      f'<td class="trace-indicator-name" data-formula-open="false" title="{formula_esc}">'
      f'{name_esc}</td>'
      f'<td class="num">{value_esc}</td>'
      f'</tr>\n'
      f'<tr class="formula-row" hidden>'
      f'<td colspan="2">{formula_esc}</td>'
      f'</tr>\n'
    )
  return (
    '<section class="trace-panel">\n'
    '  <p class="eyebrow">INDICATORS</p>\n'
    '  <table class="trace-indicators-table">\n'
    '    <tbody>\n'
    + ''.join(rows)
    + '  </tbody></table>\n'
    '</section>\n'
  )


def _render_trace_vote(indicator_scalars: dict, signal: int) -> str:
  '''Phase 17 D-07: Vote panel — 3 Mom badges + ADX gate badge + outcome.

  Badge classes: plus/minus/zero for Mom sign; pass/fail for ADX gate.
  ADX gate threshold: 25.0 (literal per D-10 — NOT imported from system_params).
  Empty indicator_scalars: "Awaiting first daily run." per D-11.
  '''
  if not indicator_scalars:
    return (
      '<section class="trace-panel trace-vote">\n'
      '  <p><em>Awaiting first daily run.</em></p>\n'
      '</section>\n'
    )
  _OUTCOME_LABEL = {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}
  ADX_GATE_THRESHOLD = 25.0  # D-10: literal — no import from system_params

  def _mom_badge(val: float) -> str:
    if math.isnan(val) or val == 0.0:
      return '<span class="trace-badge zero">0</span>'
    if val > 0:
      return '<span class="trace-badge plus">+</span>'
    return '<span class="trace-badge minus">-</span>'

  mom1 = float(indicator_scalars.get('mom1', float('nan')))
  mom3 = float(indicator_scalars.get('mom3', float('nan')))
  mom12 = float(indicator_scalars.get('mom12', float('nan')))
  adx = float(indicator_scalars.get('adx', float('nan')))

  seed_mom = _SEED_LENGTHS.get('mom1', 2)
  bars_avail = 40  # display context: we always show 40 bars when populated

  mom1_val = html.escape(_format_indicator_value(mom1, seed_mom, bars_avail), quote=True)
  mom3_val = html.escape(_format_indicator_value(mom3, _SEED_LENGTHS.get('mom3', 4), bars_avail), quote=True)
  mom12_val = html.escape(_format_indicator_value(mom12, _SEED_LENGTHS.get('mom12', 13), bars_avail), quote=True)

  adx_finite = not math.isnan(adx)
  adx_pass = adx_finite and adx >= ADX_GATE_THRESHOLD
  adx_badge_cls = 'pass' if adx_pass else 'fail'
  adx_val_str = html.escape(_format_indicator_value(adx, _SEED_LENGTHS.get('adx', 20), bars_avail), quote=True)
  gate_text = html.escape(f'>= {ADX_GATE_THRESHOLD:.0f}', quote=True)
  gate_result = 'PASS' if adx_pass else 'FAIL'

  outcome_label = html.escape(_OUTCOME_LABEL.get(signal, 'FLAT'), quote=True)

  # Count positive mom votes (D-07: 2 of 3 majority).
  votes = sum(1 for v in (mom1, mom3, mom12) if not math.isnan(v) and v > 0)
  anti_votes = sum(1 for v in (mom1, mom3, mom12) if not math.isnan(v) and v < 0)
  if votes > anti_votes:
    prelim = 'LONG'
  elif anti_votes > votes:
    prelim = 'SHORT'
  else:
    prelim = 'FLAT'
  prelim_esc = html.escape(prelim, quote=True)

  return (
    '<section class="trace-panel trace-vote">\n'
    '  <p class="eyebrow">VOTE</p>\n'
    '  <table class="trace-vote-table"><tbody>\n'
    f'  <tr><td>Mom1</td><td>{_mom_badge(mom1)}</td><td class="num">{mom1_val}</td></tr>\n'
    f'  <tr><td>Mom3</td><td>{_mom_badge(mom3)}</td><td class="num">{mom3_val}</td></tr>\n'
    f'  <tr><td>Mom12</td><td>{_mom_badge(mom12)}</td><td class="num">{mom12_val}</td></tr>\n'
    f'  <tr><td>ADX gate</td><td><span class="trace-badge {adx_badge_cls}">{gate_result}</span></td>'
    f'<td class="num">ADX {adx_val_str} {gate_text}</td></tr>\n'
    '  </tbody></table>\n'
    f'  <p>Vote: {prelim_esc}</p>\n'
    f'  <p class="trace-outcome">FINAL: {outcome_label}</p>\n'
    '</section>\n'
  )


def _render_trace_panels(
  sig_dict: dict,
  instrument_key: str,
  placeholder: str,
) -> str:
  '''Phase 17 D-04: per-instrument <details> wrapper around the three trace
  panels (Inputs / Indicators / Vote).

  `placeholder` is the literal string "{{TRACE_OPEN_<KEY>}}" (from
  _TRACE_OPEN_PLACEHOLDER[instrument_key]) — emitted verbatim AFTER the
  data-instrument attribute. web/routes/dashboard.py substitutes it
  per-request with " open" or "" based on the tsi_trace_open cookie.

  Design note (PATTERNS.md §Pattern To Design From Scratch): attribute-level
  substitution vs Phase 16.1's block-level. The placeholder is inside the
  opening tag, not surrounding a content block.
  '''
  inst_esc = html.escape(instrument_key, quote=True)
  ohlc_window = sig_dict.get('ohlc_window', [])
  indicator_scalars = sig_dict.get('indicator_scalars', {})
  signal = sig_dict.get('signal', 0)
  bars_available = len(ohlc_window)
  inner = (
    _render_trace_inputs(ohlc_window)
    + _render_trace_indicators(indicator_scalars, bars_available)
    + _render_trace_vote(indicator_scalars, signal)
  )
  return (
    f'<details class="trace-disclosure" data-instrument="{inst_esc}"{placeholder}>\n'
    '  <summary class="trace-summary">Show calculations</summary>\n'
    + inner
    + '</details>\n'
  )


def _render_signal_cards(state: dict, *, active_market: str | None = None) -> str:
  '''UI-SPEC §Signal cards — 2 cards SPI200 + AUDUSD (D-02, DASH-03).

  Per-instrument state['signals'][key] has {signal, signal_as_of, as_of_run,
  last_scalars, last_close}. Empty state (missing key): big "—" chip in
  _COLOR_FLAT + "Signal as of never" + single em-dash scalars line.
  Phase 26 B1: when active_market is set, only that market's card is rendered.
  '''
  return dr_render_signal_cards(state, active_market=active_market)


def _render_market_selector(state: dict) -> str:
  options = ''.join(
    f'        <option value="{html.escape(key, quote=True)}">{html.escape(display, quote=True)}</option>\n'
    for key, display in _display_names(state).items()
  )
  return (
    '<section class="market-selector" aria-labelledby="heading-market-selector">\n'
    '  <h2 id="heading-market-selector">Market</h2>\n'
    '  <select aria-label="Market selection">\n'
    f'{options}'
    '  </select>\n'
    '</section>\n'
  )


def _render_open_form(state: dict | None = None) -> str:
  '''UI-SPEC §Decision 1 + §Decision 7: Open New Position form, ABOVE the
  Open Positions table. 4 required fields inline; 4 optional in collapsed
  <details>. POST /trades/open via HTMX; 4xx errors surface in inline
  .error region via hx-on::after-request handler (UI-SPEC §Decision 4).

  Phase 14 REVIEWS HIGH #4 — Auth header discipline:
    The `hx-headers` attribute on the <section> emits the literal placeholder
    string `{{WEB_AUTH_SECRET}}`. The on-disk dashboard.html cache file therefore
    NEVER contains the real WEB_AUTH_SECRET value. The web/routes/dashboard.py
    GET / handler (Plan 14-04 Task 5) substitutes the real secret at request
    time. Tests assert the placeholder is on disk + the real secret is absent.

  Phase 14 REVIEWS HIGH #3 — per-tbody grouping topology:
    The form's hx-swap is "none"; the response is empty + carries an HX-Trigger
    "positions-changed" event header. Each per-instrument
    <tbody id="position-group-{instrument}"> listens for the event via
    hx-trigger="positions-changed from:body" and refreshes via a
    GET /?fragment=position-group-{instrument} fetch. This keeps swaps at
    single-tbody granularity (no orphan rows, valid HTML5 since multiple
    <tbody> elements in one <table> is well-formed).

  hx-headers on the <section> propagates to all HTMX requests inside it.
  '''
  options = ''.join(
    f'        <option value="{html.escape(key, quote=True)}">'
    f'{html.escape(display, quote=True)}</option>\n'
    for key, display in _display_names(state).items()
  )
  return (
    '<section class="open-form" '
    '''hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'>\n'''
    '  <p class="eyebrow">OPEN NEW POSITION</p>\n'
    '  <form\n'
    '    hx-post="/trades/open"\n'
    '    hx-ext="json-enc"\n'
    '    hx-swap="none"\n'
    '    hx-on::after-request="handleTradesError(event)"\n'
    '  >\n'
    '    <div class="field">\n'
    '      <label for="open-form-instrument">Instrument</label>\n'
    '      <select id="open-form-instrument" name="instrument" required>\n'
    f'{options}'
    '      </select>\n'
    '    </div>\n'
    '    <div class="field">\n'
    '      <label for="open-form-direction">Direction</label>\n'
    '      <select id="open-form-direction" name="direction" required>\n'
    '        <option value="LONG">LONG</option>\n'
    '        <option value="SHORT">SHORT</option>\n'
    '      </select>\n'
    '    </div>\n'
    '    <div class="field">\n'
    '      <label for="open-form-entry-price">Entry price</label>\n'
    '      <input id="open-form-entry-price" name="entry_price" type="number" step="0.01" min="0.01" required>\n'
    '    </div>\n'
    '    <div class="field">\n'
    '      <label for="open-form-contracts">Contracts</label>\n'
    '      <input id="open-form-contracts" name="contracts" type="number" step="1" min="1" required>\n'
    '    </div>\n'
    '    <details class="form-advanced">\n'
    '      <summary>Advanced</summary>\n'
    '      <p class="advanced-helper">Leave blank unless back-dating a pyramided position.</p>\n'
    '      <div class="field">\n'
    '        <label for="open-form-executed-at">Executed at</label>\n'
    '        <input id="open-form-executed-at" name="executed_at" type="date">\n'
    '        <small>Optional. Defaults to today (AWST).</small>\n'
    '      </div>\n'
    '      <div class="field">\n'
    '        <label for="open-form-peak-price">Peak price</label>\n'
    '        <input id="open-form-peak-price" name="peak_price" type="number" step="0.01" min="0">\n'
    '        <small>LONG only. Leave blank to default to entry price.</small>\n'
    '      </div>\n'
    '      <div class="field">\n'
    '        <label for="open-form-trough-price">Trough price</label>\n'
    '        <input id="open-form-trough-price" name="trough_price" type="number" step="0.01" min="0">\n'
    '        <small>SHORT only. Leave blank to default to entry price.</small>\n'
    '      </div>\n'
    '      <div class="field">\n'
    '        <label for="open-form-pyramid-level">Pyramid level</label>\n'
    '        <input id="open-form-pyramid-level" name="pyramid_level" type="number" step="1" min="0" max="2">\n'
    '        <small>Defaults to 0. Use only when back-dating a pyramided position.</small>\n'
    '      </div>\n'
    '    </details>\n'
    '    <button type="submit" class="btn-primary">Open live position</button>\n'
  '  </form>\n'
    '  <div class="error" role="alert" aria-live="polite" hidden></div>\n'
    '</section>\n'
  )


def _render_single_position_row(state: dict, state_key: str, pos: dict) -> str:
  '''Phase 14 REVIEWS HIGH #3: render one <tr id="position-row-{state_key}">
  with 9 <td> cells (8 data + 1 Actions). Extracted from the body of
  _render_positions_table so each row can be wrapped in its own
  <tbody id="position-group-{state_key}"> for single-tbody-level HTMX swaps.

  Action buttons target the parent <tbody id="position-group-{state_key}">
  via hx-target="#position-group-{state_key}" with hx-swap="innerHTML" so
  close/modify confirmation panels swap cleanly without orphan rows.
  '''
  display = _display_names(state).get(state_key, state_key)
  signals = state.get('signals', {})
  instrument_cell = html.escape(display, quote=True)
  direction_int = 1 if pos['direction'] == 'LONG' else -1
  dir_label = html.escape(pos['direction'], quote=True)
  # D-19 #5: use semantic class instead of inline style="color:..."
  _DIR_CLASS = {1: 'signal-long', -1: 'signal-short'}
  dir_class = _DIR_CLASS.get(direction_int, 'signal-flat')
  entry_cell = html.escape(_fmt_currency(pos['entry_price']), quote=True)
  sig_entry = signals.get(state_key) or {}
  last_close = sig_entry.get('last_close')
  if last_close is None:
    current_cell = html.escape(_fmt_em_dash(), quote=True)
  else:
    current_cell = html.escape(_fmt_currency(last_close), quote=True)
  contracts_cell = html.escape(str(pos['n_contracts']), quote=True)
  pyramid_cell = html.escape(f'Lvl {pos["pyramid_level"]}', quote=True)
  settings = _strategy_settings_for(state, state_key)
  trail_stop = _compute_trail_stop_display(pos, settings)
  trail_currency = html.escape(_fmt_currency(trail_stop), quote=True)
  # Phase 14 D-09 + UI-SPEC §Decision 6 + CONTEXT D-15: manual_stop badge.
  # Tooltip explicitly says "(manual; dashboard only)" per CONTEXT D-15 promise:
  # manual_stop is DISPLAY-ONLY in Phase 14 — sizing_engine.check_stop_hit
  # (daily exit-detection loop) does NOT honor manual_stop. The badge surfaces
  # the override so the operator audits at-a-glance; the daily loop continues
  # to use the v1.0 computed trailing stop until a future phase aligns them.
  if pos.get('manual_stop') is not None:
    # Phase 15 D-10 + UI-SPEC §Decision 6: side-by-side stop cell.
    # Shows both manual override value AND computed trailing stop.
    # (will close) annotation clarifies which value the daily loop respects.
    manual_val = html.escape(_fmt_currency(float(pos['manual_stop'])), quote=True)
    from sizing_engine import get_trailing_stop  # LOCAL — C-2
    synth = dict(pos)
    synth['manual_stop'] = None
    computed_val_raw = get_trailing_stop(synth, 0.0, 0.0)
    computed_val = (
      html.escape(_fmt_currency(computed_val_raw), quote=True)
      if math.isfinite(computed_val_raw) else _fmt_em_dash()
    )
    trail_cell = (
      f'<span class="trail-stop-split">'
      f'<span class="manual-stop-val">manual: {manual_val}</span>'
      f'<span class="stop-sep"> | </span>'
      f'<span class="computed-stop-val">computed: {computed_val} <em>(will close)</em></span>'
      f'</span>'
    )
  else:
    # Phase 14 baseline — unchanged
    trail_cell = trail_currency
  unrealised = _compute_unrealised_pnl_display(pos, state_key, last_close, state)
  if unrealised is None:
    pnl_cell = html.escape(_fmt_em_dash(), quote=True)
  else:
    pnl_cell = _fmt_pnl_with_colour(unrealised)  # already html.escape'd internally
  state_key_esc = html.escape(state_key, quote=True)
  return (
    f'      <tr id="position-row-{state_key_esc}">\n'
    f'        <td>{instrument_cell}</td>\n'
    f'        <td data-label="Direction"><span class="{dir_class}">{dir_label}</span></td>\n'
    f'        <td class="num">{entry_cell}</td>\n'
    f'        <td class="num">{current_cell}</td>\n'
    f'        <td class="num">{contracts_cell}</td>\n'
    f'        <td class="num">{pyramid_cell}</td>\n'
    f'        <td class="num">{trail_cell}</td>\n'
    f'        <td class="num">{pnl_cell}</td>\n'
    f'        <td>'
    f'<button type="button" class="btn-row btn-close" '
    f'hx-get="/trades/close-form?instrument={state_key_esc}" '
    f'hx-target="#position-group-{state_key_esc}" '
    f'hx-swap="innerHTML">Close</button>'
    f'<button type="button" class="btn-row btn-modify" '
    f'hx-get="/trades/modify-form?instrument={state_key_esc}" '
    f'hx-target="#position-group-{state_key_esc}" '
    f'hx-swap="innerHTML">Modify</button>'
    f'</td>\n'
    '      </tr>\n'
  )


def _render_calc_row(state: dict, state_key: str, pos: dict) -> str:
  '''Phase 15 CALC-01/04: calculator sub-row rendered after a position row.

  Cells (REVIEWS H-1 + M-3 + L-3):
    - STOP        : current trailing stop (manual_stop precedence honored)
    - DIST        : |current_close - trail_stop| in $ and %  (M-3: current-price baseline)
    - NEXT ADD    : entry +/- (level+1)*atr_entry           (Pitfall 6)
    - LEVEL       : level N/MAX_PYRAMID_LEVEL or "fully pyramided"
    - NEW STOP    : projected stop AFTER the next pyramid add (H-1: synthesize peak=NEXT_ADD)
    - IF HIGH     : forward-look HTMX input + W placeholder (em-dash on first render)
                    + conditional "(enter high to project)" hint (L-3)

  sizing_engine import is LOCAL (C-2; permitted by Plan 01
  FORBIDDEN_MODULES_DASHBOARD update + Plan 01 Task 2 AST guard for
  module-top imports). check_pyramid is intentionally NOT imported —
  its return type does not contain the next-add price (Pitfall 6 +
  REVIEWS H-1: compute the price + projected stop directly).
  '''
  from sizing_engine import get_trailing_stop  # LOCAL — C-2 + REVIEWS M-2
  from system_params import MAX_PYRAMID_LEVEL

  state_key_esc = html.escape(state_key, quote=True)
  direction = pos.get('direction', 'LONG')
  entry_price = float(pos.get('entry_price', 0.0))
  atr_entry = float(pos.get('atr_entry', 0.0))
  # Position TypedDict (system_params.py) names the field `pyramid_level`.
  # Phase 15 plan/tests called it `current_level`. Accept both — production
  # uses pyramid_level; some test fixtures use current_level.
  # Tolerate non-int values (defensive — e.g. XSS-escape regression fixtures).
  try:
    current_level = int(pos.get('pyramid_level', pos.get('current_level', 0)))
  except (ValueError, TypeError):
    current_level = 0

  # STOP cell — reuse Phase 14 _compute_trail_stop_display for the value
  # (handles manual_stop precedence + NaN guards).
  settings = _strategy_settings_for(state, state_key)
  trail_stop = _compute_trail_stop_display(pos, settings)
  stop_html = (
    html.escape(_fmt_currency(trail_stop), quote=True)
    if trail_stop is not None and math.isfinite(trail_stop)
    else _fmt_em_dash()
  )

  # REVIEWS M-3: DIST baseline = current_close, NOT entry_price.
  # Source: state['signals'][state_key]['last_close']. When signal is int
  # shape (Phase 3 reset) or missing, current_close is None -> em-dash.
  sig_entry = state.get('signals', {}).get(state_key)
  if isinstance(sig_entry, dict):
    current_close_raw = sig_entry.get('last_close')
    try:
      current_close = float(current_close_raw) if current_close_raw is not None else None
    except (TypeError, ValueError):
      current_close = None
  else:
    current_close = None

  if (
    current_close is not None and math.isfinite(current_close) and current_close > 0
    and trail_stop is not None and math.isfinite(trail_stop)
  ):
    dist_abs = abs(current_close - trail_stop)
    dist_pct = dist_abs / current_close
    dist_dollar = html.escape(_fmt_currency(dist_abs), quote=True)
    dist_pct_html = html.escape(_fmt_percent_unsigned(dist_pct), quote=True)
  else:
    dist_dollar = _fmt_em_dash()
    dist_pct_html = _fmt_em_dash()

  # NEXT ADD price (Pitfall 6 formula — direction-aware)
  can_pyramid = (
    current_level < MAX_PYRAMID_LEVEL
    and math.isfinite(atr_entry) and atr_entry > 0
    and entry_price > 0
  )
  if can_pyramid:
    if direction == 'LONG':
      next_add_price = entry_price + (current_level + 1) * atr_entry
    else:  # SHORT
      next_add_price = entry_price - (current_level + 1) * atr_entry
    next_add_html = html.escape(_fmt_currency(next_add_price), quote=True)
  else:
    next_add_price = None
    next_add_html = _fmt_em_dash()

  # LEVEL cell
  if current_level >= MAX_PYRAMID_LEVEL:
    level_html = (
      f'<span class="calc-dim">level {current_level}/{MAX_PYRAMID_LEVEL} — '
      f'fully pyramided</span>'
    )
  else:
    level_html = f'level {current_level}/{MAX_PYRAMID_LEVEL}'

  # REVIEWS H-1 + ATR annotation: NEW STOP cell.
  # Synthesize a position whose peak (LONG) / trough (SHORT) is at
  # next_add_price; drop manual_stop so we get the COMPUTED projected stop.
  # Same pattern as the forward-look fragment handler in Plan 06.
  if can_pyramid and next_add_price is not None:
    synth_for_add = dict(pos)
    if direction == 'LONG':
      synth_for_add['peak_price'] = max(
        pos.get('peak_price') or entry_price, next_add_price,
      )
    else:
      synth_for_add['trough_price'] = min(
        pos.get('trough_price') or entry_price, next_add_price,
      )
    synth_for_add['manual_stop'] = None
    try:
      new_stop_value = get_trailing_stop(synth_for_add, 0.0, 0.0)
    except Exception:
      new_stop_value = float('nan')
    if math.isfinite(new_stop_value):
      new_stop_html = html.escape(_fmt_currency(new_stop_value), quote=True)
    else:
      new_stop_html = _fmt_em_dash()
    # Step annotation matches "+1×ATR" for level-0->1, "+2×ATR" for level-1->2
    atr_step_label = f'(+{current_level + 1}×ATR)'
  else:
    new_stop_html = _fmt_em_dash()
    atr_step_label = ''

  # IF HIGH — forward-look input + W placeholder + conditional hint (REVIEWS L-3)
  forward_input = (
    f'<input id="forward-stop-{state_key_esc}-z" name="z" type="number" step="0.01" min="0" '
    f'hx-get="/?fragment=forward-stop&amp;instrument={state_key_esc}" '
    f'hx-trigger="input changed delay:300ms" '
    f'hx-target="#forward-stop-{state_key_esc}-w" '
    f'hx-include="this" '
    f'class="calc-input" '
    f'aria-label="Enter today&apos;s high to project trailing stop for {state_key_esc}">'
  )
  # REVIEWS L-3: hint shown only on initial render (W is em-dash).
  # When Plan 06's fragment response replaces the W span with a real value,
  # the response also overrides the hint span (Plan 06 returns the W span
  # alone; the hint span outside the swap target stays put — but is still
  # only meaningful when W is em-dash). Rendering the hint here is safe
  # because the swap target only replaces #forward-stop-{X}-w. To make the
  # hint disappear after typing, Plan 06 returns a wrapper that includes
  # both the W span AND a (no-op or empty) hint span via an oob swap on
  # a sibling id. For Wave 2 we render the hint as a separate span with
  # id="forward-stop-{X}-hint"; Plan 06 will optionally hx-swap-oob it
  # out. (Documented constraint: this plan ships only the initial-render
  # hint; the conditional disappearance is Plan 06 scope.)
  hint_html = (
    f'<span id="forward-stop-{state_key_esc}-hint" class="calc-dim">'
    f'(enter high to project)</span>'
  )

  # Pyramid label sub-formatting: when can_pyramid we want
  # "next add at $X (+1×ATR)" + "new stop $S" — adjacent labels per UI-SPEC.
  next_add_with_step = (
    f'{next_add_html} <span class="calc-dim">{atr_step_label}</span>'
    if atr_step_label
    else next_add_html
  )

  return (
    f'    <tr class="calc-row" aria-label="Calculator data for {state_key_esc}">\n'
    f'      <td colspan="9" class="calc-cell">\n'
    f'        <span class="calc-label">STOP</span>\n'
    f'        <span class="calc-value num">{stop_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-label">DIST</span>\n'
    f'        <span class="calc-value num">{dist_dollar}</span>\n'
    f'        <span class="calc-dim"> / </span>\n'
    f'        <span class="calc-value num">{dist_pct_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-label">NEXT ADD</span>\n'
    f'        <span class="calc-value num">{next_add_with_step}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-label">LEVEL</span>\n'
    f'        <span class="calc-value">{level_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-label">NEW STOP</span>\n'
    f'        <span class="calc-value num">{new_stop_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-label">IF HIGH</span>\n'
    f'        {forward_input}\n'
    f'        <span class="calc-dim">stop rises to</span>\n'
    f'        <span id="forward-stop-{state_key_esc}-w" class="calc-value num">{_fmt_em_dash()}</span>\n'
    f'        {hint_html}\n'
    f'      </td>\n'
    f'    </tr>\n'
  )


def _render_entry_target_row(state: dict, state_key: str) -> str:
  '''Phase 15 CALC-02: entry-target row when position is None and signal
  is LONG or SHORT. Returns empty string when signal is FLAT.

  sizing_engine.calc_position_size import is LOCAL (C-2).
  '''
  sig_entry = state.get('signals', {}).get(state_key)
  if sig_entry is None:
    return ''
  if isinstance(sig_entry, int):
    sig_val = sig_entry
    last_close = None
    atr = None
    rvol = None
  elif isinstance(sig_entry, dict):
    sig_val = sig_entry.get('signal')
    last_close = sig_entry.get('last_close')
    last_scalars = sig_entry.get('last_scalars') or {}
    atr = last_scalars.get('atr')
    rvol = last_scalars.get('rvol')
  else:
    return ''
  if sig_val not in (1, -1):
    return ''
  direction_label = 'LONG' if sig_val == 1 else 'SHORT'
  # D-19 #5: use semantic class instead of inline style="color:..."
  direction_class = 'signal-long' if sig_val == 1 else 'signal-short'
  state_key_esc = html.escape(state_key, quote=True)

  # Threshold = today's last_close (RESEARCH §Open Question 2)
  if last_close is not None and math.isfinite(last_close):
    threshold_html = html.escape(_fmt_currency(last_close), quote=True)
  else:
    threshold_html = _fmt_em_dash()

  # Suggested contracts via calc_position_size (LOCAL import)
  contracts_html = _fmt_em_dash()
  initial_stop_html = _fmt_em_dash()
  try:
    if all(v is not None and math.isfinite(v)
           for v in (last_close, atr, rvol)):
      from sizing_engine import calc_position_size  # LOCAL — C-2
      account = float(state.get('account', 0.0))
      contracts_per_inst = state.get('_resolved_contracts', {}).get(state_key) or {}
      multiplier = float(contracts_per_inst.get('multiplier', 1.0))
      decision = calc_position_size(
        account, sig_val, atr, rvol, multiplier,
        settings=_strategy_settings_for(state, state_key),
      )
      if decision.contracts > 0:
        contracts_html = html.escape(
          f'{decision.contracts} contracts', quote=True,
        )
        settings = _strategy_settings_for(state, state_key)
        if sig_val == 1:
          initial_stop = last_close - float(settings.get('trail_mult_long', TRAIL_MULT_LONG)) * atr
        else:
          initial_stop = last_close + float(settings.get('trail_mult_short', TRAIL_MULT_SHORT)) * atr
        if math.isfinite(initial_stop):
          initial_stop_html = html.escape(_fmt_currency(initial_stop), quote=True)
  except Exception:
    # Fallback to em-dashes; never crash the dashboard render
    pass

  return (
    f'    <tr class="calc-row" aria-label="Entry target for {state_key_esc}">\n'
    f'      <td colspan="9" class="calc-cell entry-target">\n'
    f'        <span class="calc-label">Entry target</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-dim">Signal:</span>\n'
    f'        <span class="{direction_class}">{direction_label}</span>\n'
    f'        <span class="calc-dim"> — enter on next close ≥ </span>\n'
    f'        <span class="calc-value num">{threshold_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-dim">Size:</span>\n'
    f'        <span class="calc-value">{contracts_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-dim">Initial stop:</span>\n'
    f'        <span class="calc-value num">{initial_stop_html}</span>\n'
    f'      </td>\n'
    f'    </tr>\n'
  )


def _render_drift_banner(state: dict) -> str:
  '''Phase 15 SENTINEL-01/02 + D-11/D-13 + REVIEWS H-2: drift sentinel banner.

  Returns:
    - empty string when no warnings have source='drift'
    - <div class="sentinel-banner sentinel-reversal"> when any drift
      warning message contains 'reversal recommended' (D-13: red border)
    - <div class="sentinel-banner sentinel-drift"> otherwise (amber)

  Body lists each drift warning as a <li> in a <ul class="sentinel-body">.

  Called from render_dashboard() body composition (REVIEWS H-2 — top-level
  slot before _render_positions_table). NOT called from inside
  _render_positions_table — the banner sits at the same DOM level as
  future corruption + stale dashboard banners will eventually live.
  '''
  drift_warnings = [
    w for w in state.get('warnings', [])
    if w.get('source') == 'drift'
  ]
  if not drift_warnings:
    return ''
  has_reversal = any(
    'reversal recommended' in w.get('message', '')
    for w in drift_warnings
  )
  css_class = (
    'sentinel-banner sentinel-reversal' if has_reversal
    else 'sentinel-banner sentinel-drift'
  )
  lines_html = '\n'.join(
    f'        <li>{html.escape(w.get("message", ""), quote=True)}</li>'
    for w in drift_warnings
  )
  return (
    f'  <div class="{css_class}" role="alert" aria-live="polite">\n'
    f'    <p class="sentinel-heading">Drift detected</p>\n'
    f'    <ul class="sentinel-body">\n'
    f'{lines_html}\n'
    f'    </ul>\n'
    f'  </div>\n'
  )


def _render_trailing_stop_guidance(state: dict) -> str:
  rows = []
  for market_id, display in _display_names(state).items():
    pos = state.get('positions', {}).get(market_id)
    if pos is None:
      continue
    sig = state.get('signals', {}).get(market_id, {})
    last_close = sig.get('last_close') if isinstance(sig, dict) else None
    settings = _strategy_settings_for(state, market_id)
    stop = _compute_trail_stop_display(pos, settings)
    current_html = _fmt_em_dash()
    distance_html = _fmt_em_dash()
    if last_close is not None and math.isfinite(float(last_close)) and math.isfinite(stop):
      current = float(last_close)
      current_html = html.escape(_fmt_currency(current), quote=True)
      distance_html = html.escape(
        f'{_fmt_currency(abs(current - stop))} / {_fmt_percent_unsigned(abs(current - stop) / current)}',
        quote=True,
      )
    stop_html = html.escape(_fmt_currency(stop), quote=True) if math.isfinite(stop) else _fmt_em_dash()
    atr = float(pos.get('atr_entry', float('nan')))
    next_add = _fmt_em_dash()
    if math.isfinite(atr) and atr > 0:
      level = int(pos.get('pyramid_level', 0))
      if pos.get('direction') == 'LONG':
        next_add_val = float(pos.get('entry_price', 0.0)) + (level + 1) * atr
      else:
        next_add_val = float(pos.get('entry_price', 0.0)) - (level + 1) * atr
      next_add = html.escape(_fmt_currency(next_add_val), quote=True)
    signal_as_of = sig.get('signal_as_of', 'never') if isinstance(sig, dict) else 'never'
    rows.append(
      '      <tr>\n'
      f'        <td>{html.escape(display, quote=True)}</td>\n'
      f'        <td>{html.escape(pos.get("direction", ""), quote=True)}</td>\n'
      f'        <td class="num">{current_html}</td>\n'
      f'        <td class="num">{stop_html}</td>\n'
      f'        <td class="num">{distance_html}</td>\n'
      f'        <td class="num">{next_add}</td>\n'
      f'        <td>{html.escape(str(signal_as_of), quote=True)}</td>\n'
      '      </tr>\n'
    )
  if not rows:
    rows.append(
      '      <tr><td colspan="7" class="empty-state">'
      'No open positions need trailing-stop updates.'
      '</td></tr>\n'
    )
  return (
    '<section aria-labelledby="heading-trailing-stops">\n'
    '  <h2 id="heading-trailing-stops">Trailing Stops</h2>\n'
    '  <table class="data-table">\n'
    '    <thead><tr><th>Market</th><th>Direction</th><th>Current</th>'
    '<th>Trailing Stop</th><th>Distance</th><th>Next Add</th><th>Updated</th></tr></thead>\n'
    '    <tbody>\n'
    f'{"".join(rows)}'
    '    </tbody>\n'
    '  </table>\n'
    '</section>\n'
  )


def _render_positions_table(state: dict, include_open_form: bool = True) -> str:
  '''UI-SPEC §Open positions table — 9 cols incl. Actions (DASH-05, B-1, Phase 14).

  Phase 14 changes (TRADE-05):
    - <section class="open-form"> emitted ABOVE the table (UI-SPEC §Decision 1)
    - 9th <th>Actions</th> column with Close + Modify per-row buttons (UI-SPEC §Decision 2)
    - When position['manual_stop'] is not None, the Trail Stop cell carries a
      <span class="badge badge-manual">manual</span> pill AND the displayed
      value equals manual_stop verbatim (NOT the computed peak-trail) per
      UI-SPEC §Decision 6 + Phase 14 D-09

  Phase 14 REVIEWS HIGH #3 — per-instrument tbody grouping topology:
    Each instrument's row is wrapped in its OWN
    <tbody id="position-group-{instrument}"> (multiple <tbody> elements in
    one <table> is valid HTML5). All HTMX close/modify swaps target this
    <tbody> with hx-swap="innerHTML" so confirmation rows + cancel rows +
    final result rows are SINGLE-tbody-level swaps — no orphan panels, no
    invalid <div>-as-child-of-<tbody> shapes. Each <tbody> also carries
    hx-trigger="positions-changed from:body" + hx-get="/?fragment=position-
    group-{X}" so it self-refreshes when an HX-Trigger event fires from
    /trades/* responses.

  Phase 14 REVIEWS HIGH #4 — Auth header placeholder discipline:
    Every per-instrument tbody emits the literal placeholder string
    `{{WEB_AUTH_SECRET}}` in its hx-headers attribute. The on-disk
    dashboard.html cache file therefore NEVER contains the real
    WEB_AUTH_SECRET value. web/routes/dashboard.py GET / substitutes the
    real secret at request time.

  Iterates _INSTRUMENT_DISPLAY_NAMES in declaration order. Rows where
  state['positions'][key] is None are omitted (partial-state rule). Empty
  state (all None) renders one <td colspan="9"> placeholder row inside a
  <tbody id="positions-empty"> per F-4 + REVIEWS HIGH #3.
  Current column sources state['signals'][key]['last_close'] (B-1 retrofit).
  '''
  return dr_render_positions_table(state, include_open_form=include_open_form)


def _render_trades_table(state: dict) -> str:
  '''UI-SPEC §Closed trades table — 7 cols, last 20 newest-first (DASH-06).

  Slice [-20:][::-1] → last 20 reversed so most-recent is the first row.
  Empty trade_log renders single <td colspan="7"> placeholder.
  '''
  return dr_render_trades_table(state)


def _render_paper_trades_stats(stats: dict | None = None) -> str:
  '''Phase 19 D-06 — renders the sticky aggregate stats <aside>.

  Formats 5 badges from the _compute_aggregate_stats output dict:
  realised, unrealised, wins, losses, win_rate.
  win_rate is pre-computed (string) by _compute_aggregate_stats; escape it.
  '''
  if stats is None:
    stats = {
      'realised': 0.0, 'unrealised': 0.0,
      'wins': 0, 'losses': 0, 'win_rate': '—',
    }
  return (
    '<aside class="stats-bar" aria-labelledby="stats-bar-heading">\n'
    '  <h2 id="stats-bar-heading" class="visually-hidden">Aggregate paper-trade stats</h2>\n'
    f'  <div class="stats-bar-item"><span class="label">Realised</span><span>{stats["realised"]:+.2f}</span></div>\n'
    f'  <div class="stats-bar-item"><span class="label">Unrealised</span><span>{stats["unrealised"]:+.2f}</span></div>\n'
    f'  <div class="stats-bar-item"><span class="label">Wins</span><span>{stats["wins"]}</span></div>\n'
    f'  <div class="stats-bar-item"><span class="label">Losses</span><span>{stats["losses"]}</span></div>\n'
    f'  <div class="stats-bar-item"><span class="label">Win rate</span><span>{html.escape(str(stats["win_rate"]))}</span></div>\n'
    '</aside>\n'
  )


def _render_paper_trades_open_form() -> str:
  '''Phase 19 D-13 — render the open-paper-trade form.

  hx-post="/paper-trade/open" + hx-target="#trades-region" + hx-swap="outerHTML".
  Content-type: application/x-www-form-urlencoded (browser/HTMX default, no
  hx-ext="json-enc" per planner D-17). The FastAPI route reads request.form()
  and validates via Pydantic model_validate() — see web/routes/paper_trades.py
  _parse_form helper (gap-closure 2026-04-30).

  Gap-closure 2026-04-30: original implementation used a non-standard enctype value
  (browsers silently fall back to form-encoded, causing route mismatch).
  Corrected to use application/x-www-form-urlencoded (the HTML default, explicit here
  for clarity) so browser + HTMX submissions match what the route handler expects.
  '''
  # D-19 #6: use explicit for/id pairing (not implicit wrap) for SR discoverability
  return (
    '<section id="open-trade-form-section">\n'
    '  <h2>Record New Paper Trade</h2>\n'
    '  <form hx-post="/paper-trade/open"\n'
    '        hx-target="#trades-region"\n'
    '        hx-swap="outerHTML"\n'
    '        enctype="application/x-www-form-urlencoded">\n'
    '    <label for="paper-trade-instrument">Instrument</label>\n'
    '    <select id="paper-trade-instrument" name="instrument" required>\n'
    '      <option value="SPI200">SPI200</option>\n'
    '      <option value="AUDUSD">AUDUSD</option>\n'
    '    </select>\n'
    '    <label for="paper-trade-side">Side</label>\n'
    '    <select id="paper-trade-side" name="side" required>\n'
    '      <option value="LONG">LONG</option>\n'
    '      <option value="SHORT">SHORT</option>\n'
    '    </select>\n'
    '    <label for="paper-trade-entry-dt">Entry date/time (AWST)</label>\n'
    '    <input id="paper-trade-entry-dt" type="datetime-local" name="entry_dt" required>\n'
    '    <label for="paper-trade-entry-price">Entry price</label>\n'
    '    <input id="paper-trade-entry-price" type="number" name="entry_price" step="0.0001" min="0.0001" required>\n'
    '    <label for="paper-trade-contracts">Contracts</label>\n'
    '    <input id="paper-trade-contracts" type="number" name="contracts" step="0.01" min="0.01" required>\n'
    '    <label for="paper-trade-stop-price">Stop price (optional)</label>\n'
    '    <input id="paper-trade-stop-price" type="number" name="stop_price" step="0.0001" min="0">\n'
    '    <button type="submit" class="btn-primary">Record paper trade</button>\n'
  '  </form>\n'
    '</section>\n'
  )


def _render_alert_badge(state: str | None, has_stop: bool) -> str:
  '''Phase 20 D-19: render an alert state badge <span>.

  Returns a <span class="alert-badge alert-{lower}">...</span>.
  Dashboard uses CSS classes (never inline styles — per RESEARCH §Pitfall 3).
  All state text passed through html.escape before render.

  state=None or unrecognised state -> alert-none with "--" placeholder.
  has_stop=False -> alert-none (no stop to monitor, title="no stop set").
  '''
  _KNOWN = {'CLEAR', 'APPROACHING', 'HIT'}
  if not has_stop or state is None:
    title = 'no stop set' if not has_stop else 'awaiting next daily run'
    return (
      f'<span class="alert-badge alert-none" title="{title}">--</span>'
    )
  esc_state = html.escape(str(state), quote=True)
  if state in _KNOWN:
    css_class = f'alert-{state.lower()}'
  else:
    css_class = 'alert-none'
  return f'<span class="alert-badge {css_class}">{esc_state}</span>'


def _render_paper_trades_open(paper_trades=None, signals=None) -> str:
  '''Phase 19 D-11/D-13 — renders open paper-trades table with MTM unrealised P&L.

  Mirrors _render_positions_table shape (Phase 5 analog).
  LOCAL imports for pnl_engine (hex symmetry with sizing_engine convention).
  Mutable-default avoided (planner trap): use None sentinels.
  NaN guard before compute per RESEARCH §Pitfall 5.
  Trade IDs flowed through html.escape(..., quote=True) per PATTERNS.
  '''
  if paper_trades is None:
    paper_trades = []
  if signals is None:
    signals = {}

  from pnl_engine import compute_unrealised_pnl  # LOCAL — Phase 11 C-2

  _MULT = {'SPI200': 5.0, 'AUDUSD': 10000.0}

  open_rows = [r for r in paper_trades if r.get('status') == 'open']

  if not open_rows:
    return (
      '<section id="open-trades-section">\n'
      '  <h2>Open Paper Trades</h2>\n'
      '  <div class="table-scroll" tabindex="0" role="region" aria-label="Open paper trades (scrollable)">\n'
      '  <table class="paper-trades-table">\n'
      '    <tbody>\n'
      '      <tr><td colspan="10" class="empty-state">'
      'No open paper trades. Use the form above to record a new entry.'
      '</td></tr>\n'
      '    </tbody>\n'
      '  </table>\n'
      '  </div>\n'
      '</section>\n'
    )

  rows_html = ''
  for row in open_rows:
    trade_id = row.get('id', '')
    esc_id = html.escape(trade_id, quote=True)
    instrument = row.get('instrument', '')
    sig = signals.get(instrument, {})
    lc = sig.get('last_close')

    if lc is None:
      pnl_str = 'n/a (no close price yet)'
      pnl_class = 'pnl-zero'
    else:
      try:
        lc_float = float(lc)
      except (TypeError, ValueError):
        lc_float = float('nan')
      if math.isnan(lc_float):
        pnl_str = 'n/a (no close price yet)'
        pnl_class = 'pnl-zero'
      else:
        upnl = compute_unrealised_pnl(
          row['side'], row['entry_price'], lc_float,
          row['contracts'], _MULT.get(instrument, 1.0),
          row['entry_cost_aud'],
        )
        pnl_str = f'{upnl:+.2f}'
        pnl_class = (
          'pnl-positive' if upnl > 0 else ('pnl-negative' if upnl < 0 else 'pnl-zero')
        )

    alert_badge_html = _render_alert_badge(
      row.get('last_alert_state'),
      has_stop=row.get('stop_price') is not None,
    )
    rows_html += (
      f'  <tr class="row-clickable" data-trade-id="{esc_id}">\n'
      f'    <td>{esc_id}</td>\n'
      f'    <td>{html.escape(instrument)}</td>\n'
      f'    <td>{html.escape(row.get("side", ""))}</td>\n'
      f'    <td>{html.escape(str(row.get("entry_price", "")))}</td>\n'
      f'    <td>{html.escape(str(row.get("contracts", "")))}</td>\n'
      f'    <td>{html.escape(str(row.get("stop_price") or "—"))}</td>\n'
      f'    <td class="{pnl_class}">{html.escape(pnl_str)}</td>\n'
      f'    <td>{alert_badge_html}</td>\n'
      f'    <td>\n'
      f'      <button hx-get="/paper-trade/{esc_id}/close-form"\n'
      f'              hx-target="#close-form-section"\n'
      f'              hx-swap="outerHTML">Close</button>\n'
      f'    </td>\n'
      f'    <td>\n'
      f'      <button hx-delete="/paper-trade/{esc_id}"\n'
      f'              hx-target="#trades-region"\n'
      f'              hx-swap="outerHTML"\n'
      f'              hx-confirm="Delete this open paper trade?">Delete</button>\n'
      f'    </td>\n'
      f'  </tr>\n'
    )

  return (
    '<section id="open-trades-section">\n'
    '  <h2>Open Paper Trades</h2>\n'
    '  <div class="table-scroll" tabindex="0" role="region" aria-label="Open paper trades (scrollable)">\n'
    '  <table class="paper-trades-table">\n'
    '    <thead>\n'
    '      <tr><th>ID</th><th>Instrument</th><th>Side</th><th>Entry</th>'
    '<th>Contracts</th><th>Stop</th><th>Unrealised P&amp;L</th>'
    '<th>Alert</th><th>Close</th><th>Delete</th></tr>\n'
    '    </thead>\n'
    '    <tbody>\n'
    f'{rows_html}'
    '    </tbody>\n'
    '  </table>\n'
    '  </div>\n'
    '</section>\n'
  )


def _render_paper_trades_closed(paper_trades=None) -> str:
  '''Phase 19 D-11/D-13 — renders closed paper-trades table sorted by exit_dt desc.

  Mirrors _render_trades_table shape.
  Mutable-default avoided: use None sentinel.
  '''
  if paper_trades is None:
    paper_trades = []

  closed_rows = sorted(
    [r for r in paper_trades if r.get('status') == 'closed'],
    key=lambda r: r.get('exit_dt') or '',
    reverse=True,
  )

  if not closed_rows:
    return (
      '<section id="closed-trades-section">\n'
      '  <h2>Closed Paper Trades</h2>\n'
      '  <div class="table-scroll" tabindex="0" role="region" aria-label="Closed paper trades (scrollable)">\n'
      '  <table class="paper-trades-table">\n'
      '    <tbody>\n'
      '      <tr><td colspan="7" class="empty-state">'
      'No closed trades yet. Trades will appear here after you close an open position.'
      '</td></tr>\n'
      '    </tbody>\n'
      '  </table>\n'
      '  </div>\n'
      '</section>\n'
    )

  rows_html = ''
  for row in closed_rows:
    trade_id = row.get('id', '')
    esc_id = html.escape(trade_id, quote=True)
    realised = row.get('realised_pnl') or 0.0
    pnl_str = f'{realised:+.2f}'
    pnl_class = (
      'pnl-positive' if realised > 0 else ('pnl-negative' if realised < 0 else 'pnl-zero')
    )
    rows_html += (
      f'  <tr>\n'
      f'    <td data-label="ID">{esc_id}</td>\n'
      f'    <td data-label="Instrument">{html.escape(row.get("instrument", ""))}</td>\n'
      f'    <td data-label="Side">{html.escape(row.get("side", ""))}</td>\n'
      f'    <td data-label="Entry">{html.escape(str(row.get("entry_price", "")))}</td>\n'
      f'    <td data-label="Exit">{html.escape(str(row.get("exit_price", "")))}</td>\n'
      f'    <td data-label="Exit Date">{html.escape(str(row.get("exit_dt", "—")))}</td>\n'
      f'    <td data-label="Realised P&L" class="{pnl_class}">{html.escape(pnl_str)}</td>\n'
      f'  </tr>\n'
    )

  return (
    '<section id="closed-trades-section">\n'
    '  <h2>Closed Paper Trades</h2>\n'
    '  <div class="table-scroll" tabindex="0" role="region" aria-label="Closed paper trades (scrollable)">\n'
    '  <table class="paper-trades-table">\n'
    '    <thead>\n'
    '      <tr><th>ID</th><th>Instrument</th><th>Side</th><th>Entry</th>'
    '<th>Exit</th><th>Exit Date</th><th>Realised P&amp;L</th></tr>\n'
    '    </thead>\n'
    '    <tbody>\n'
    f'{rows_html}'
    '    </tbody>\n'
    '  </table>\n'
    '  </div>\n'
    '</section>\n'
  )


def _render_close_form_section() -> str:
  '''Phase 19 D-03 — placeholder section for the close-form fragment.

  Default: empty section shell. The GET /paper-trade/<id>/close-form route
  returns a populated <section id="close-form-section"> that replaces this
  placeholder via HTMX hx-swap="outerHTML".
  '''
  return '<section id="close-form-section"></section>\n'


def _render_paper_trades_region(state: dict) -> str:
  '''Phase 19 D-13 — wraps all paper-trade subsections in #trades-region.

  Order: stats bar → open-trade form → open table → close-form section → closed table.
  This entire <div> is the HTMX hx-target="#trades-region" swap target for every
  paper-trade mutation (POST /paper-trade/open, PATCH, DELETE, POST close).
  '''
  return dr_render_paper_trades_region(state)


def _render_key_stats(state: dict) -> str:
  '''UI-SPEC §Key stats block — 4 tiles Total Return/Sharpe/MaxDD/WinRate (DASH-07).

  Tile 1 Total Return is coloured (positive → long, negative → short, zero →
  muted). Tiles 2-4 are not coloured (magnitude reads as negative by sign;
  double-encoding would be noisy per UI-SPEC).
  '''
  total_return = _compute_total_return(state)
  sharpe = _compute_sharpe(state)
  max_dd = _compute_max_drawdown(state)
  win_rate = _compute_win_rate(state)

  # D-19 #5: Total Return CSS class — no inline style="color:..."
  # .pnl-positive/.pnl-negative/.pnl-zero defined in _INLINE_CSS (Plan 25-09)
  if total_return == _fmt_em_dash():
    tr_class = 'pnl-zero'
  elif total_return.startswith('-'):
    tr_class = 'pnl-negative'
  elif total_return in ('+0.0%', '-0.0%'):
    tr_class = 'pnl-zero'
  else:
    tr_class = 'pnl-positive'
  tr_value_esc = html.escape(total_return, quote=True)
  sharpe_esc = html.escape(sharpe, quote=True)
  max_dd_esc = html.escape(max_dd, quote=True)
  win_rate_esc = html.escape(win_rate, quote=True)

  return (
    '<section aria-labelledby="heading-stats">\n'
    '  <h2 id="heading-stats">Key Stats</h2>\n'
    '  <div class="stats-grid">\n'
    '    <div class="stat-tile">\n'
    '      <p class="label">Total Return</p>\n'
    f'      <p class="value {tr_class}">{tr_value_esc}</p>\n'
    '    </div>\n'
    '    <div class="stat-tile">\n'
    '      <p class="label">Sharpe</p>\n'
    f'      <p class="value">{sharpe_esc}</p>\n'
    '    </div>\n'
    '    <div class="stat-tile">\n'
    '      <p class="label">Max Drawdown</p>\n'
    f'      <p class="value">{max_dd_esc}</p>\n'
    '    </div>\n'
    '    <div class="stat-tile">\n'
    '      <p class="label">Win Rate</p>\n'
    f'      <p class="value">{win_rate_esc}</p>\n'
    '    </div>\n'
    '  </div>\n'
    '</section>\n'
  )


def _compute_account_stat_values(state: dict) -> dict:
  initial = float(state.get('initial_account', INITIAL_ACCOUNT))
  account = float(state.get('account', initial))
  realised = sum(float(t.get('net_pnl', 0.0)) for t in state.get('trade_log', []))
  unrealised = 0.0
  open_trades = 0
  exposure = 0.0
  for market_id, pos in state.get('positions', {}).items():
    if pos is None:
      continue
    open_trades += 1
    sig = state.get('signals', {}).get(market_id, {})
    last_close = sig.get('last_close') if isinstance(sig, dict) else None
    if last_close is None:
      continue
    resolved = state.get('_resolved_contracts', {}).get(market_id, {})
    multiplier = float(resolved.get('multiplier', 1.0))
    exposure += abs(float(last_close) * float(pos.get('n_contracts', 0)) * multiplier)
    upnl = _compute_unrealised_pnl_display(pos, market_id, float(last_close), state)
    if upnl is not None:
      unrealised += upnl
  equity = account + unrealised
  return {
    'initial': initial,
    'account': account,
    'realised': realised,
    'unrealised': unrealised,
    'equity': equity,
    'total_return': ((equity / initial) - 1.0) if initial > 0 else 0.0,
    'max_drawdown': _compute_max_drawdown(state),
    'win_rate': _compute_win_rate(state),
    'open_exposure': exposure,
    'open_trades': open_trades,
    'closed_trades': len(state.get('trade_log', [])),
  }


def _render_account_stats(state: dict) -> str:
  stats = _compute_account_stat_values(state)
  tiles = [
    ('Starting Balance', _fmt_currency(stats['initial'])),
    ('Account Balance', _fmt_currency(stats['account'])),
    ('Realised P&L', f'{stats["realised"]:+,.2f}'),
    ('Unrealised P&L', f'{stats["unrealised"]:+,.2f}'),
    ('Total Return', _fmt_percent_signed(stats['total_return'])),
    ('Max Drawdown', stats['max_drawdown']),
    ('Win Rate', stats['win_rate']),
    ('Open Exposure', _fmt_currency(stats['open_exposure'])),
    ('Open Trades', str(stats['open_trades'])),
    ('Closed Trades', str(stats['closed_trades'])),
  ]
  body = ''.join(
    '    <div class="stat-tile">\n'
    f'      <p class="label">{html.escape(label, quote=True)}</p>\n'
    f'      <p class="value">{html.escape(value, quote=True)}</p>\n'
    '    </div>\n'
    for label, value in tiles
  )
  return (
    '<section aria-labelledby="heading-account-stats">\n'
    '  <h2 id="heading-account-stats">Key Stats</h2>\n'
    '  <div class="stats-grid account-stats-grid">\n'
    f'{body}'
    '  </div>\n'
    '</section>\n'
  )


def _render_account_balance_form(state: dict) -> str:
  initial = float(state.get('initial_account', INITIAL_ACCOUNT))
  account = float(state.get('account', initial))
  return (
    '<section class="open-form account-balance-form">\n'
    '  <p class="eyebrow">ACCOUNT BASELINE</p>\n'
    '  <form hx-patch="/account/balance" hx-ext="json-enc" '
    'hx-target="#account-management-region" hx-swap="outerHTML" '
    'hx-on::after-request="handleTradesError(event)">\n'
    f'    <div class="field"><label for="account-balance-initial">Starting balance</label><input id="account-balance-initial" name="initial_account" type="number" step="0.01" min="0.01" value="{initial:.2f}" required></div>\n'
    f'    <div class="field"><label for="account-balance-current">Account balance</label><input id="account-balance-current" name="account" type="number" step="0.01" min="0" value="{account:.2f}" required></div>\n'
    '    <button type="submit" class="btn-primary">Update balances</button>\n'
    '  </form>\n'
    '  <div class="error" role="alert" aria-live="polite" hidden></div>\n'
    '</section>\n'
  )


def _render_account_management_region(state: dict) -> str:
  return (
    '<div id="account-management-region">\n'
    + _render_account_balance_form(state)
    + _render_account_stats(state)
    + _render_positions_table(state, include_open_form=True)
    + _render_trades_table(state)
    + '</div>\n'
  )


def _render_settings_tab(state: dict, *, active_market: str | None = None) -> str:
  return dr_render_settings_tab(state, active_market=active_market)


def _render_add_market_form(state: dict) -> str:
  return dr_render_add_market_form(state)


def _render_market_test_tab(state: dict, *, active_market: str | None = None) -> str:
  return dr_render_market_test_tab(state, active_market=active_market)


def _render_footer(strategy_version: str) -> str:
  '''UI-SPEC §Footer disclaimer — "Signal-only system. Not financial advice."

  Phase 22 D-06: appends a small <div class="strategy-version"> line
  showing the active strategy version. The version arrives as a
  primitive str argument from render_dashboard (which calls
  _resolve_strategy_version on the state dict) — preserves the
  hex-boundary rule that dashboard.py never imports
  system_params.STRATEGY_VERSION (LEARNINGS 2026-04-27).
  '''
  return dr_render_footer(strategy_version)


def _distinct_equity_tuples(equity_history: list) -> list:
  '''Phase 25 D-11: dedupe (date, equity) tuples; chart hides until >=5 distinct.

  Three identical {date: '2026-04-23', equity: 100000.0} entries produce ONE
  distinct entry, not three. Only dicts with parseable date+equity are kept.
  '''
  seen: set = set()
  distinct = []
  for row in equity_history:
    if not isinstance(row, dict):
      continue
    try:
      key = (row['date'], float(row['equity']))
    except (KeyError, TypeError, ValueError):
      continue
    if key not in seen:
      seen.add(key)
      distinct.append(row)
  return distinct


def _render_equity_chart_container(state: dict) -> str:
  '''DASH-04 / CONTEXT D-11 / UI-SPEC §Chart Component. Category x-axis.

  JSON payload injection defence (Pitfall 1): json.dumps + .replace('</', '<\\/').

  D-11 empty state: chart hidden until >=5 distinct (date, equity) tuples.
  Three identical points still count as one distinct point (D-11 spec).
  '''
  equity_history = state.get('equity_history', []) or []
  distinct = _distinct_equity_tuples(equity_history)
  if len(distinct) < 5:
    return (
      '<section aria-labelledby="heading-equity">\n'
      '  <h2 id="heading-equity">Equity curve</h2>\n'
      '  <div class="empty-state">'
      'Chart appears once 5 daily equity points have been recorded.'
      '</div>\n'
      '</section>\n'
    )
  # Build labels + data from the deduped distinct list (NOT raw equity_history).
  # JSON-serialise with <script>-close injection defence (Pitfall 1) and
  # byte-stable dict ordering (Pitfall 2).
  labels = [row['date'] for row in distinct]
  data = [float(row['equity']) for row in distinct]
  payload = json.dumps(
    {'labels': labels, 'data': data},
    ensure_ascii=False,
    sort_keys=True,    # Pitfall 2: byte-stable dict order
    allow_nan=False,   # G-1 reviews: stray NaN must fail loudly rather than
                       # emit invalid JSON that Chart.js renders as a blank line
  ).replace('</', '<\\/')
  return (
    '<section aria-labelledby="heading-equity">\n'
    '  <h2 id="heading-equity">Equity Curve</h2>\n'
    '  <div class="chart-container">\n'
    '    <canvas id="equityChart" '
    'aria-label="Account equity line chart over time" role="img"></canvas>\n'
    '  </div>\n'
    '  <script>\n'
    '    (function() {\n'
    f'      const payload = {payload};\n'
    '      new Chart(document.getElementById("equityChart"), {\n'
    '        type: "line",\n'
    '        data: {\n'
    '          labels: payload.labels,\n'
    '          datasets: [{\n'
    '            label: "Account equity",\n'
    '            data: payload.data,\n'
    f'            borderColor: "{_COLOR_LONG}",\n'
    f'            backgroundColor: "{_COLOR_LONG}",\n'
    '            fill: false,\n'
    '            tension: 0.1,\n'
    '            borderWidth: 2,\n'
    '            pointRadius: 0,\n'
    '            pointHoverRadius: 4\n'
    '          }]\n'
    '        },\n'
    '        options: {\n'
    '          scales: {\n'
    f'            x: {{ type: "category",\n'
    f'               ticks: {{ color: "{_COLOR_TEXT_MUTED}", maxTicksLimit: 10 }},\n'
    f'               grid: {{ color: "{_COLOR_BORDER}" }} }},\n'
    f'            y: {{ ticks: {{ color: "{_COLOR_TEXT_MUTED}",\n'
    '                         callback: (v) => "$" + v.toLocaleString() }},\n'
    f'               grid: {{ color: "{_COLOR_BORDER}" }} }}\n'
    '          },\n'
    '          plugins: {\n'
    '            legend: { display: false },\n'
    '            tooltip: { callbacks: { label: (ctx) => "$" + ctx.parsed.y.toLocaleString() } }\n'
    '          },\n'
    '          maintainAspectRatio: false,\n'
    '          responsive: true\n'
    '        }\n'
    '      });\n'
    '    })();\n'
    '  </script>\n'
    '</section>\n'
  )


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
        # D-19 #4: _render_market_selector removed — replaced by market tab strip
        # in render_two_axis_nav (Plan 25-03). The old <select aria-label="Market selection">
        # is N/A; market switching is done via the tab strip in the two-axis nav.
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
  nav_mode: str = 'web',
) -> str:
  from dashboard_renderer.components.nav import render_two_axis_nav, _first_market_id
  selected = _render_page_body(ctx, page)
  section_id, heading_id, heading_text, heading_cls, render_body = selected
  body = render_body()
  heading_class_attr = f' class="{heading_cls}"' if heading_cls else ''

  # Phase 25: derive active_function/active_market from ctx (with fallbacks for
  # callers that don't pass the new kwargs — nav_mode='file' sibling generation).
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


def _render_dashboard_page_nav(active_page: str, nav_mode: str = 'web') -> str:
  '''DEPRECATED — Phase 25 Plan 03. Use render_two_axis_nav from dashboard_renderer.components.nav.

  Retained to avoid breaking any direct test calls. Plan 25-09 (final cleanup) deletes this.
  '''
  if nav_mode == 'file':
    pages = (
      ('signals', 'dashboard-signals.html', 'Signals'),
      ('account', 'dashboard-account.html', 'Account'),
      ('settings', 'dashboard-settings.html', 'Settings'),
      ('market-test', 'dashboard-market-test.html', 'Market Test'),
    )
  else:
    pages = (
      ('signals', '/signals', 'Signals'),
      ('account', '/account', 'Account'),
      ('settings', '/settings', 'Settings'),
      ('market-test', '/market-test', 'Market Test'),
    )
  links = []
  for page_key, href, label in pages:
    cls = ' class="active"' if page_key == active_page else ''
    links.append(
      f'  <a href="{href}"{cls}>{label}</a>\n',
    )
  return '<nav class="tabs" aria-label="Dashboard tabs">\n' + ''.join(links) + '</nav>\n'


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


# =========================================================================
# Atomic write — Phase 3 D-17 mirror of state_manager._atomic_write
# =========================================================================

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


# =========================================================================
# Public API — D-01
# =========================================================================

def render_dashboard(
  state: dict,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
  is_cookie_session: bool | None = None,
  trace_open_keys: list | None = None,  # Phase 17 D-04 — None=all-collapsed default
) -> None:
  '''Compatibility wrapper; primary orchestration now lives in dashboard_renderer.api.'''
  from dashboard_renderer.api import render_dashboard as dr_render_dashboard

  dr_render_dashboard(
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
  '''Compatibility wrapper; primary orchestration now lives in dashboard_renderer.api.'''
  from dashboard_renderer.api import render_dashboard_page as dr_render_dashboard_page

  dr_render_dashboard_page(
    state,
    page=page,
    out_path=out_path,
    now=now,
    is_cookie_session=is_cookie_session,
    trace_open_keys=trace_open_keys,
  )


if __name__ == '__main__':
  # C-6 reviews: CONTEXT D-05 convenience CLI. `python -m dashboard` loads
  # the current state.json and renders dashboard.html using the current
  # AWST wall-clock. Never used by CI; operator-only preview path.
  # render_dashboard(now=None) defaults to PERTH.localize-equivalent
  # datetime.now(PERTH), so we just pass load_state() and a default path.
  render_dashboard(load_state(), Path('dashboard.html'))
