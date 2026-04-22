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

Wave 0 (this commit): all 9 helpers raise NotImplementedError; palette +
Chart.js SRI + _INLINE_CSS :root vars are locked in place so Wave 1 can
append per-block render output against a fixed contract.
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
# Em-dash constant helper — placed early so _compute_* helpers can reference
# it for empty-state fallbacks (CONTEXT D-16). Full formatter suite lands in
# Task 2 of Wave 1 just below this block.
# =========================================================================

def _fmt_em_dash() -> str:
  '''UI-SPEC §Format Helper Contracts: single call site for the em-dash empty-value token.'''
  return '—'


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
# Private render helpers — Wave 0 stubs; Waves 1/2 fill bodies
# =========================================================================

def _render_header(state: dict, now: datetime) -> str:
  '''UI-SPEC §Header — H1 "Trading Signals" + subtitle + Last-updated AWST.'''
  raise NotImplementedError('Wave 1: fills per UI-SPEC §Header')


def _render_signal_cards(state: dict) -> str:
  '''UI-SPEC §Signal cards — 2 cards SPI200 + AUDUSD (D-02, DASH-03).'''
  raise NotImplementedError('Wave 1: fills per UI-SPEC §Signal cards')


def _render_positions_table(state: dict) -> str:
  '''UI-SPEC §Open positions table — 8 cols incl. Current from last_close (DASH-05, B-1).'''
  raise NotImplementedError('Wave 1: fills per UI-SPEC §Open positions table')


def _render_trades_table(state: dict) -> str:
  '''UI-SPEC §Closed trades table — 7 cols, last 20 newest-first (DASH-06).'''
  raise NotImplementedError('Wave 1: fills per UI-SPEC §Closed trades table')


def _render_key_stats(state: dict) -> str:
  '''UI-SPEC §Key stats block — 4 tiles Total Return/Sharpe/MaxDD/WinRate (DASH-07).'''
  raise NotImplementedError('Wave 1: fills per UI-SPEC §Key stats block')


def _render_footer() -> str:
  '''UI-SPEC §Footer disclaimer — "Signal-only system. Not financial advice."'''
  raise NotImplementedError('Wave 1: fills per UI-SPEC §Footer disclaimer')


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
