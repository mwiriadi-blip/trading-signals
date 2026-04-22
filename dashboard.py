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

from state_manager import (
  load_state,  # noqa: F401 — CLI convenience path; prod uses caller-supplied state
)
from system_params import (  # noqa: F401 — Wave 1 contract specs + trail multipliers
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
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
# Palette constants — UI-SPEC §Color (locked, do NOT retune)
# =========================================================================

_COLOR_BG = '#0f1117'
_COLOR_SURFACE = '#161a24'
_COLOR_BORDER = '#252a36'
_COLOR_TEXT = '#e5e7eb'
_COLOR_TEXT_MUTED = '#cbd5e1'
_COLOR_TEXT_DIM = '#64748b'
_COLOR_LONG = '#22c55e'
_COLOR_SHORT = '#ef4444'
_COLOR_FLAT = '#eab308'


# =========================================================================
# Chart.js constants — RESEARCH §Version verification (verified 2026-04-21)
# =========================================================================

# Chart.js 4.4.6 UMD — SRI verified 2026-04-21 via curl + openssl dgst.
# Both jsdelivr + unpkg return byte-identical 205,615-byte file.
_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'


# =========================================================================
# Display-name + contract-spec dicts — Wave 1 lookup sources
# =========================================================================

_INSTRUMENT_DISPLAY_NAMES = {
  'SPI200': 'SPI 200',
  'AUDUSD': 'AUD / USD',
}

_CONTRACT_SPECS = {
  'SPI200': (SPI_MULT, SPI_COST_AUD),
  'AUDUSD': (AUDUSD_NOTIONAL, AUDUSD_COST_AUD),
}


# =========================================================================
# Inline CSS — UI-SPEC §Design System (Wave 2 fills full stylesheet)
# =========================================================================

_INLINE_CSS = f'''
:root {{
  --color-bg: {_COLOR_BG};
  --color-surface: {_COLOR_SURFACE};
  --color-border: {_COLOR_BORDER};
  --color-text: {_COLOR_TEXT};
  --color-text-muted: {_COLOR_TEXT_MUTED};
  --color-text-dim: {_COLOR_TEXT_DIM};
  --color-long: {_COLOR_LONG};
  --color-short: {_COLOR_SHORT};
  --color-flat: {_COLOR_FLAT};
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-6: 24px; --space-8: 32px; --space-12: 48px;
  --fs-body: 14px; --fs-label: 12px; --fs-heading: 20px; --fs-display: 28px;
  --font-mono: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
}}
/* Wave 2 fills layout, typography, tables, cards, chart, stats, footer, visually-hidden. */
'''


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
  return '—'


def _fmt_currency(value: float) -> str:
  '''UI-SPEC §Format Helper Contracts: $1,234.56 / -$567.89 / $0.00.

  Always 2 dp. Negative uses leading -$, NEVER parentheses. No K/M/B suffix.
  '''
  if value < 0:
    return f'-${-value:,.2f}'
  return f'${value:,.2f}'


def _fmt_percent_signed(fraction: float) -> str:
  '''UI-SPEC §Format Helper Contracts: +5.3% / -12.5% / +0.0%.

  Input is a fraction (0.053 → +5.3%). Signed zero renders as '+0.0%'.
  '''
  return f'{fraction * 100:+.1f}%'


def _fmt_percent_unsigned(fraction: float) -> str:
  '''UI-SPEC §Format Helper Contracts: 58.3% / 12.5%. Input is a fraction.'''
  return f'{fraction * 100:.1f}%'


def _fmt_pnl_with_colour(value: float) -> str:
  '''UI-SPEC §Format Helper Contracts + CONTEXT D-16: P&L span coloured by sign.

  Positive: <span style="color: #22c55e">+$1,234.56</span>
  Negative: <span style="color: #ef4444">-$567.89</span>
  Zero:     <span style="color: #cbd5e1">$0.00</span>

  Belt-and-braces html.escape on both colour + body (numeric formats already safe;
  the escape keeps reviewer scan trivial per D-15).
  '''
  if value > 0:
    colour = _COLOR_LONG
    body = f'+{_fmt_currency(value)}'
  elif value < 0:
    colour = _COLOR_SHORT
    body = _fmt_currency(value)
  else:
    colour = _COLOR_TEXT_MUTED
    body = '$0.00'
  return (
    f'<span style="color: {html.escape(colour, quote=True)}">'
    f'{html.escape(body, quote=True)}</span>'
  )


def _fmt_last_updated(now: datetime) -> str:
  '''UI-SPEC §Format Helper Contracts + DASH-08: YYYY-MM-DD HH:MM AWST.

  Raises ValueError on naive datetime (RESEARCH Pitfall 9: a naive now silently
  produces different bytes per CI runner timezone, breaking golden-snapshot
  determinism). Always applies Australia/Perth via astimezone → strftime.
  '''
  if now.tzinfo is None:
    raise ValueError(
      '_fmt_last_updated requires a timezone-aware datetime; '
      f'got naive datetime={now!r}'
    )
  awst = now.astimezone(pytz.timezone('Australia/Perth'))
  return awst.strftime('%Y-%m-%d %H:%M AWST')


# =========================================================================
# Stats math helpers — CONTEXT D-07 / D-08 / D-09 / D-10
# =========================================================================

def _compute_sharpe(state: dict) -> str:
  '''CONTEXT D-07: daily log-returns, rf=0, annualised × √252. Returns em-dash
  if <30 samples, any non-positive equity (Pitfall 4: math.log domain error),
  or flat equity / <2 log-returns (Pitfall 3: statistics.stdev needs >= 2 samples).
  '''
  equities = [row['equity'] for row in state.get('equity_history', [])]
  if len(equities) < 30:
    return _fmt_em_dash()
  if any(e <= 0 for e in equities):  # Pitfall 4: math.log domain error guard
    return _fmt_em_dash()
  log_returns = [math.log(equities[i] / equities[i - 1]) for i in range(1, len(equities))]
  if len(log_returns) < 2:  # Pitfall 3: statistics.stdev requires >= 2 samples
    return _fmt_em_dash()
  mean_r = statistics.mean(log_returns)
  std_r = statistics.stdev(log_returns)
  if std_r == 0:  # Pitfall 3 belt-and-braces: degenerate flat streak
    return _fmt_em_dash()
  sharpe = (mean_r / std_r) * math.sqrt(252)
  return f'{sharpe:.2f}'


def _compute_max_drawdown(state: dict) -> str:
  '''CONTEXT D-08: rolling peak-to-trough %. Always <= 0. Empty history → em-dash.'''
  equities = [row['equity'] for row in state.get('equity_history', [])]
  if not equities:
    return _fmt_em_dash()
  running_max = equities[0]
  max_dd = 0.0
  for eq in equities:
    running_max = max(running_max, eq)
    if running_max == 0:  # Pitfall 5: guard divide-by-zero on pathological fixture
      continue
    dd = (eq - running_max) / running_max  # always <= 0
    max_dd = min(max_dd, dd)
  return f'{max_dd * 100:.1f}%'


def _compute_win_rate(state: dict) -> str:
  '''CONTEXT D-09: closed trades with gross_pnl > 0.

  Uses gross_pnl (NOT realised/net_pnl) — industry "win before costs" convention.
  '''
  closed = state.get('trade_log', [])
  if not closed:
    return _fmt_em_dash()
  wins = sum(1 for t in closed if t.get('gross_pnl', 0) > 0)
  return f'{wins / len(closed) * 100:.1f}%'


def _compute_total_return(state: dict) -> str:
  '''CONTEXT D-10: (current_equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT * 100. Always defined.'''
  eq_hist = state.get('equity_history', [])
  if eq_hist:
    current = eq_hist[-1].get('equity', state.get('account', INITIAL_ACCOUNT))
  else:
    current = state.get('account', INITIAL_ACCOUNT)
  total_return = (current - INITIAL_ACCOUNT) / INITIAL_ACCOUNT
  return f'{total_return * 100:+.1f}%'  # signed format: '+5.3%', '-2.1%', '+0.0%'


# =========================================================================
# Inline display-math helpers — UI-SPEC §Derived render-time calculations
# Re-implementation of sizing_engine formulas inline per CONTEXT D-01 hex
# fence. TestStatsMath::test_unrealised_pnl_matches_sizing_engine locks
# bit-identical output against sizing_engine.compute_unrealised_pnl on a
# shared fixture — drift surfaces as a red test.
# =========================================================================

def _compute_trail_stop_display(position: dict) -> float:
  '''UI-SPEC §Positions table Trail Stop formula. Anchors on position['atr_entry']
  (NOT today's ATR — matches sizing_engine D-15 semantics).

  LONG: peak_price - TRAIL_MULT_LONG * atr_entry (fallback: entry_price if peak_price None)
  SHORT: trough_price + TRAIL_MULT_SHORT * atr_entry (fallback: entry_price if trough_price None)
  '''
  atr_entry = position['atr_entry']
  if position['direction'] == 'LONG':
    peak = position.get('peak_price') or position['entry_price']
    return peak - TRAIL_MULT_LONG * atr_entry
  trough = position.get('trough_price') or position['entry_price']
  return trough + TRAIL_MULT_SHORT * atr_entry


def _compute_unrealised_pnl_display(
  position: dict, state_key: str, current_close: float | None,
) -> float | None:
  '''UI-SPEC §Positions table Unrealised P&L formula. Inline re-implementation
  of sizing_engine.compute_unrealised_pnl per CONTEXT D-01 hex fence. Returns
  None when current_close is None (caller renders em-dash).

  Per CLAUDE.md §Operator Decisions / CONTEXT D-13: opening-half cost is
  deducted here (matches sizing_engine.compute_unrealised_pnl exactly —
  TestStatsMath::test_unrealised_pnl_matches_sizing_engine locks parity).
  '''
  if current_close is None:
    return None
  multiplier, cost_aud_round_trip = _CONTRACT_SPECS[state_key]
  cost_aud_open = cost_aud_round_trip / 2
  direction_mult = 1.0 if position['direction'] == 'LONG' else -1.0
  price_diff = current_close - position['entry_price']
  gross = direction_mult * price_diff * position['n_contracts'] * multiplier
  open_cost = cost_aud_open * position['n_contracts']
  return gross - open_cost


# =========================================================================
# Render-helper lookups — signal label/colour maps + exit-reason display map
# =========================================================================

_SIGNAL_LABEL = {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}
_SIGNAL_COLOUR = {1: _COLOR_LONG, -1: _COLOR_SHORT, 0: _COLOR_FLAT}

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

def _render_header(state: dict, now: datetime) -> str:  # noqa: ARG001 — state reserved for future
  '''UI-SPEC §Header — H1 "Trading Signals" + subtitle + Last-updated AWST.

  state is reserved for future use (e.g. surfacing schema_version); the live
  clock render uses the injected `now`. _fmt_last_updated raises ValueError on
  naive datetimes (Pitfall 9 golden-snapshot drift guard).
  '''
  subtitle = html.escape('SPI 200 & AUD/USD mechanical system', quote=True)
  last_updated = html.escape(_fmt_last_updated(now), quote=True)
  return (
    '<header>\n'
    '  <h1>Trading Signals</h1>\n'
    f'  <p class="subtitle">{subtitle}</p>\n'
    '  <p class="meta">\n'
    '    <span class="label">Last updated</span>\n'
    f'    <span class="value">{last_updated}</span>\n'
    '  </p>\n'
    '</header>\n'
  )


def _render_signal_cards(state: dict) -> str:
  '''UI-SPEC §Signal cards — 2 cards SPI200 + AUDUSD (D-02, DASH-03).

  Per-instrument state['signals'][key] has {signal, signal_as_of, as_of_run,
  last_scalars, last_close}. Empty state (missing key): big "—" chip in
  _COLOR_FLAT + "Signal as of never" + single em-dash scalars line.
  '''
  signals = state.get('signals', {})
  parts = [
    '<section aria-labelledby="heading-signals">\n',
    '  <h2 id="heading-signals">Signal Status</h2>\n',
    '  <div class="cards-row">\n',
  ]
  for state_key, display in _INSTRUMENT_DISPLAY_NAMES.items():
    eyebrow = html.escape(display, quote=True)
    sig_entry = signals.get(state_key)
    if sig_entry is None:
      label = html.escape(_fmt_em_dash(), quote=True)
      colour = html.escape(_COLOR_FLAT, quote=True)
      signal_as_of_line = 'Signal as of never'
      scalars_line = html.escape(_fmt_em_dash(), quote=True)
    else:
      signal_int = sig_entry.get('signal', 0)
      label = html.escape(_SIGNAL_LABEL.get(signal_int, _fmt_em_dash()), quote=True)
      colour = html.escape(_SIGNAL_COLOUR.get(signal_int, _COLOR_FLAT), quote=True)
      signal_as_of = html.escape(sig_entry.get('signal_as_of', 'never'), quote=True)
      signal_as_of_line = f'Signal as of {signal_as_of}'
      scalars = sig_entry.get('last_scalars') or {}
      if scalars:
        adx = f'{scalars.get("adx", 0.0):.1f}'
        mom1 = _fmt_percent_signed(scalars.get('mom1', 0.0))
        mom3 = _fmt_percent_signed(scalars.get('mom3', 0.0))
        mom12 = _fmt_percent_signed(scalars.get('mom12', 0.0))
        rvol = f'{scalars.get("rvol", 0.0):.2f}'
        scalars_line = (
          f'ADX {html.escape(adx, quote=True)}  ·  '
          f'Mom<sub>1</sub> {html.escape(mom1, quote=True)}  ·  '
          f'Mom<sub>3</sub> {html.escape(mom3, quote=True)}  ·  '
          f'Mom<sub>12</sub> {html.escape(mom12, quote=True)}  ·  '
          f'RVol {html.escape(rvol, quote=True)}'
        )
      else:
        scalars_line = html.escape(_fmt_em_dash(), quote=True)
    parts.append(
      '    <article class="card">\n'
      f'      <p class="eyebrow">{eyebrow}</p>\n'
      f'      <p class="big-label" style="color: {colour}">{label}</p>\n'
      f'      <p class="sub">{signal_as_of_line}</p>\n'
      f'      <p class="scalars">{scalars_line}</p>\n'
      '    </article>\n'
    )
  parts.append('  </div>\n')
  parts.append('</section>\n')
  return ''.join(parts)


def _render_positions_table(state: dict) -> str:
  '''UI-SPEC §Open positions table — 8 cols incl. Current from last_close (DASH-05, B-1).

  Iterates _INSTRUMENT_DISPLAY_NAMES in declaration order. Rows where
  state['positions'][key] is None are omitted (partial-state rule). Empty
  state (all None) renders one <td colspan="8"> placeholder row per F-4.
  Current column sources state['signals'][key]['last_close'] (B-1 retrofit).
  '''
  positions = state.get('positions', {})
  signals = state.get('signals', {})
  rendered_rows = []
  for state_key, display in _INSTRUMENT_DISPLAY_NAMES.items():
    pos = positions.get(state_key)
    if pos is None:
      continue
    instrument_cell = html.escape(display, quote=True)
    direction_int = 1 if pos['direction'] == 'LONG' else -1
    dir_label = html.escape(pos['direction'], quote=True)
    dir_colour = html.escape(_SIGNAL_COLOUR[direction_int], quote=True)
    entry_cell = html.escape(_fmt_currency(pos['entry_price']), quote=True)
    sig_entry = signals.get(state_key) or {}
    last_close = sig_entry.get('last_close')
    if last_close is None:
      current_cell = html.escape(_fmt_em_dash(), quote=True)
    else:
      current_cell = html.escape(_fmt_currency(last_close), quote=True)
    contracts_cell = html.escape(str(pos['n_contracts']), quote=True)
    pyramid_cell = html.escape(f'Lvl {pos["pyramid_level"]}', quote=True)
    trail_stop = _compute_trail_stop_display(pos)
    trail_cell = html.escape(_fmt_currency(trail_stop), quote=True)
    unrealised = _compute_unrealised_pnl_display(pos, state_key, last_close)
    if unrealised is None:
      pnl_cell = html.escape(_fmt_em_dash(), quote=True)
    else:
      pnl_cell = _fmt_pnl_with_colour(unrealised)  # already html.escape'd internally
    rendered_rows.append(
      '      <tr>\n'
      f'        <td>{instrument_cell}</td>\n'
      f'        <td><span style="color: {dir_colour}">{dir_label}</span></td>\n'
      f'        <td class="num">{entry_cell}</td>\n'
      f'        <td class="num">{current_cell}</td>\n'
      f'        <td class="num">{contracts_cell}</td>\n'
      f'        <td class="num">{pyramid_cell}</td>\n'
      f'        <td class="num">{trail_cell}</td>\n'
      f'        <td class="num">{pnl_cell}</td>\n'
      '      </tr>\n'
    )
  if not rendered_rows:
    rendered_rows = [
      '      <tr>\n'
      '        <td colspan="8" class="empty-state">— No open positions —</td>\n'
      '      </tr>\n'
    ]
  body = ''.join(rendered_rows)
  return (
    '<section aria-labelledby="heading-positions">\n'
    '  <h2 id="heading-positions">Open Positions</h2>\n'
    '  <table class="data-table">\n'
    '    <caption class="visually-hidden">Open positions with current price, '
    'contracts, trail stop, and unrealised P&amp;L</caption>\n'
    '    <thead>\n'
    '      <tr>\n'
    '        <th scope="col">Instrument</th>\n'
    '        <th scope="col">Direction</th>\n'
    '        <th scope="col">Entry</th>\n'
    '        <th scope="col">Current</th>\n'
    '        <th scope="col">Contracts</th>\n'
    '        <th scope="col">Pyramid</th>\n'
    '        <th scope="col">Trail Stop</th>\n'
    '        <th scope="col">Unrealised P&amp;L</th>\n'
    '      </tr>\n'
    '    </thead>\n'
    '    <tbody>\n'
    f'{body}'
    '    </tbody>\n'
    '  </table>\n'
    '</section>\n'
  )


def _render_trades_table(state: dict) -> str:
  '''UI-SPEC §Closed trades table — 7 cols, last 20 newest-first (DASH-06).

  Slice [-20:][::-1] → last 20 reversed so most-recent is the first row.
  Empty trade_log renders single <td colspan="7"> placeholder.
  '''
  trade_log = state.get('trade_log', [])
  slice_newest_first = list(reversed(trade_log[-20:]))
  rendered_rows = []
  for trade in slice_newest_first:
    closed = html.escape(trade.get('exit_date', ''), quote=True)
    instrument_key = trade.get('instrument', '')
    instrument_display = _INSTRUMENT_DISPLAY_NAMES.get(instrument_key, instrument_key)
    instrument = html.escape(instrument_display, quote=True)
    direction_raw = trade.get('direction', '')
    direction_int = 1 if direction_raw == 'LONG' else -1 if direction_raw == 'SHORT' else 0
    dir_label = html.escape(direction_raw, quote=True)
    dir_colour = html.escape(_SIGNAL_COLOUR.get(direction_int, _COLOR_FLAT), quote=True)
    entry_price = html.escape(_fmt_currency(trade.get('entry_price', 0.0)), quote=True)
    exit_price = html.escape(_fmt_currency(trade.get('exit_price', 0.0)), quote=True)
    contracts = html.escape(str(trade.get('n_contracts', 0)), quote=True)
    exit_reason_raw = trade.get('exit_reason', '')
    reason_display = _EXIT_REASON_DISPLAY.get(exit_reason_raw, exit_reason_raw)
    reason = html.escape(reason_display, quote=True)
    pnl_cell = _fmt_pnl_with_colour(trade.get('net_pnl', 0.0))
    rendered_rows.append(
      '      <tr>\n'
      f'        <td>{closed}</td>\n'
      f'        <td>{instrument}</td>\n'
      f'        <td><span style="color: {dir_colour}">{dir_label}</span></td>\n'
      f'        <td class="num">{entry_price} → {exit_price}</td>\n'
      f'        <td class="num">{contracts}</td>\n'
      f'        <td>{reason}</td>\n'
      f'        <td class="num">{pnl_cell}</td>\n'
      '      </tr>\n'
    )
  if not rendered_rows:
    rendered_rows = [
      '      <tr>\n'
      '        <td colspan="7" class="empty-state">— No closed trades yet —</td>\n'
      '      </tr>\n'
    ]
  body = ''.join(rendered_rows)
  return (
    '<section aria-labelledby="heading-trades">\n'
    '  <h2 id="heading-trades">Closed Trades</h2>\n'
    '  <p class="subtle">last 20</p>\n'
    '  <table class="data-table">\n'
    '    <caption class="visually-hidden">Most recent 20 closed trades, '
    'newest first</caption>\n'
    '    <thead>\n'
    '      <tr>\n'
    '        <th scope="col">Closed</th>\n'
    '        <th scope="col">Instrument</th>\n'
    '        <th scope="col">Direction</th>\n'
    '        <th scope="col">Entry → Exit</th>\n'
    '        <th scope="col">Contracts</th>\n'
    '        <th scope="col">Reason</th>\n'
    '        <th scope="col">P&amp;L</th>\n'
    '      </tr>\n'
    '    </thead>\n'
    '    <tbody>\n'
    f'{body}'
    '    </tbody>\n'
    '  </table>\n'
    '</section>\n'
  )


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

  # Total Return colour — parse the signed percent to pick the accent.
  # '+0.0%' is zero → muted. Negative starts with '-'. Positive starts with '+'
  # but may be exactly zero (+0.0%).
  if total_return == _fmt_em_dash():
    tr_colour = _COLOR_TEXT_MUTED
  elif total_return.startswith('-'):
    tr_colour = _COLOR_SHORT
  elif total_return in ('+0.0%', '-0.0%'):
    tr_colour = _COLOR_TEXT_MUTED
  else:
    tr_colour = _COLOR_LONG
  tr_colour_esc = html.escape(tr_colour, quote=True)
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
    f'      <p class="value" style="color: {tr_colour_esc}">{tr_value_esc}</p>\n'
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


def _render_footer() -> str:
  '''UI-SPEC §Footer disclaimer — "Signal-only system. Not financial advice."'''
  return (
    '<footer>\n'
    '  Signal-only system. Not financial advice.\n'
    '</footer>\n'
  )


def _render_equity_chart_container(state: dict) -> str:
  '''UI-SPEC §Chart Component — Chart.js canvas + inline script (DASH-04).'''
  raise NotImplementedError('Wave 2: fills per UI-SPEC §Chart Component + RESEARCH §Pattern 2')


def _render_html_shell(body: str) -> str:
  '''UI-SPEC §Component Hierarchy — <!DOCTYPE> + <head> + Chart.js script + inline CSS + <body>.'''
  raise NotImplementedError('Wave 2: fills per RESEARCH §Pattern 2')


# =========================================================================
# Public API — D-01
# =========================================================================

def render_dashboard(
  state: dict,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
) -> None:
  '''Public API (CONTEXT D-01). Writes dashboard.html atomically.'''
  raise NotImplementedError(
    'Wave 2: concatenates body blocks + _render_html_shell + _atomic_write_html',
  )
