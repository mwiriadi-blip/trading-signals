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
# Chart.js constants — RESEARCH §Version verification (verified 2026-04-21)
# =========================================================================

# Chart.js 4.4.6 UMD — SRI verified 2026-04-21 via curl + openssl dgst.
# Both jsdelivr + unpkg return byte-identical 205,615-byte file.
_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'

# Phase 14 TRADE-05 / UI-SPEC §HTMX vendor pin: HTMX 1.9.12 UMD bundle.
# SRI verified 2026-04-25 against unpkg + jsdelivr (byte-identical).
# Mirrors the Chart.js vendor-pin precedent above. Loads in <head> AFTER
# Chart.js, BEFORE inline <style> (UI-SPEC §HTMX vendor pin / load location).
_HTMX_URL = 'https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js'
_HTMX_SRI = 'sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2'

# Phase 14 UI-SPEC §Decision 4: inline JS for hx-on::after-request 4xx surfacing.
# The ONLY client-side script Phase 14 ships beyond HTMX itself.
# innerHTML is used for layout speed; e.reason and 409 body text are server-controlled
# prose (Pydantic validators + D-01 conflict messages — NOT user-controllable).
# If a future REQ allows operator-supplied free-text in error reasons, switch
# to textContent per CLAUDE.md "innerHTML with dynamic data requires escaping".
_HANDLE_TRADES_ERROR_JS = '''
function handleTradesError(evt) {
  if (evt.detail.successful) return;
  var section = evt.target.closest('section');
  if (!section) return;
  var errorBox = section.querySelector('.error');
  if (!errorBox) return;
  var status = evt.detail.xhr.status;
  if (status === 401) {
    errorBox.innerHTML = '<p class="error-heading">Auth header missing or wrong — refresh the page</p>';
  } else if (status === 400) {
    var body;
    try { body = JSON.parse(evt.detail.xhr.responseText); } catch (e) {
      errorBox.innerHTML = '<p class="error-heading">Server error — see journald</p>';
      errorBox.hidden = false;
      return;
    }
    var heading = '<p class="error-heading">Could not save trade:</p>';
    var rows = (body.errors || []).map(function (e) {
      return '<div class="error-row"><code>' + e.field + '</code>: ' + e.reason + '</div>';
    }).join('');
    errorBox.innerHTML = heading + '<div class="error-rows">' + rows + '</div>';
  } else if (status === 409) {
    errorBox.innerHTML = '<p class="error-heading">' + evt.detail.xhr.responseText + '</p>';
  } else {
    errorBox.innerHTML = '<p class="error-heading">Server error — see journald: journalctl -u trading-signals-web</p>';
  }
  errorBox.hidden = false;
}
'''


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
body {{
  background: var(--color-bg);
  color: var(--color-text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
               'Helvetica Neue', Arial, sans-serif;
  font-size: var(--fs-body);
  line-height: 1.5;
  margin: 0;
  cursor: default;
}}
.container {{
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 24px 48px;
}}
header h1 {{
  font-size: var(--fs-display);
  font-weight: 600;
  margin: 0 0 8px;
}}
header .subtitle {{
  font-size: var(--fs-body);
  font-weight: 400;
  color: var(--color-text-muted);
  margin: 0 0 16px;
}}
header .meta {{
  display: inline-flex;
  gap: 16px;
  align-items: baseline;
  color: var(--color-text-muted);
  margin: 0 0 var(--space-8);
}}
header .meta .label {{
  font-size: var(--fs-label);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}
header .meta .value {{
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}}
section {{
  margin-bottom: var(--space-8);
}}
section h2 {{
  font-size: var(--fs-heading);
  font-weight: 600;
  margin: 0 0 16px;
}}
.cards-row {{
  display: flex;
  gap: var(--space-6);
  flex-wrap: wrap;
}}
.card {{
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: var(--space-6);
  flex: 1;
  min-width: 300px;
}}
.card .eyebrow {{
  font-size: var(--fs-label);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 0 0 var(--space-2);
}}
.card .big-label {{
  font-size: var(--fs-display);
  font-weight: 600;
  margin: 0 0 var(--space-2);
}}
.card .sub {{
  font-size: var(--fs-label);
  color: var(--color-text-muted);
  margin: 0 0 var(--space-2);
}}
.card .scalars {{
  font-family: var(--font-mono);
  font-size: var(--fs-label);
  color: var(--color-text-muted);
  margin: 0;
}}
.chart-container {{
  position: relative;
  /* G-S2 reviews: Fixed height mandatory for Chart.js
     maintainAspectRatio: false — do NOT optimise away. */
  height: 320px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: var(--space-6);
}}
.chart-container.empty-state {{
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-dim);
}}
.data-table {{
  width: 100%;
  border-collapse: collapse;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}}
.data-table thead th {{
  text-align: left;
  font-size: var(--fs-label);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}}
.data-table tbody td {{
  font-size: var(--fs-body);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}}
.data-table tbody tr:last-child td {{
  border-bottom: none;
}}
.data-table tbody td.num {{
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  text-align: right;
}}
.data-table .empty-state {{
  text-align: center;
  color: var(--color-text-dim);
}}
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-6);
}}
.stat-tile {{
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: var(--space-6);
}}
.stat-tile .label {{
  font-size: var(--fs-label);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 0 0 12px;
}}
.stat-tile .value {{
  font-size: var(--fs-display);
  font-weight: 600;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  margin: 0;
}}
.subtle {{
  font-size: var(--fs-label);
  font-weight: 400;
  color: var(--color-text-muted);
  margin: 0 0 var(--space-4);
}}
footer {{
  text-align: center;
  color: var(--color-text-dim);
  font-size: 12px;
  margin: 48px 0 24px;
}}
.visually-hidden {{
  position: absolute !important;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}}
@media (max-width: 720px) {{
  .cards-row {{
    flex-direction: column;
  }}
  .stats-grid {{
    grid-template-columns: repeat(2, 1fr);
  }}
  .container {{
    padding-left: 16px;
    padding-right: 16px;
  }}
}}
/* =========================================================================
 * Phase 14 — Trade Journal HTMX components
 * UI-SPEC §Decision 1 (open form), §Decision 2 (action buttons),
 * §Decision 4 (error region), §Decision 6 (manual badge), §Decision 7 (form layout)
 * All tokens inherited from :root above; no new design tokens.
 * ========================================================================= */
.open-form {{ margin-bottom: var(--space-6); }}
.open-form form {{
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  align-items: flex-end;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: var(--space-6);
}}
.open-form .field {{
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 140px;
  flex: 1;
}}
.open-form label {{
  font-size: var(--fs-label);
  font-weight: 600;
  color: var(--color-text-muted);
}}
.open-form input,
.open-form select {{
  background: var(--color-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: var(--space-2) var(--space-3);
  font-size: var(--fs-body);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}}
.open-form select {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}}
.open-form input:focus,
.open-form select:focus {{
  outline: none;
  border-color: var(--color-text-muted);
  box-shadow: 0 0 0 1px var(--color-text-muted);
}}
.open-form details {{
  width: 100%;
  margin-top: var(--space-2);
}}
.open-form summary {{
  cursor: pointer;
  font-size: var(--fs-label);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: var(--space-2) 0;
}}
.open-form .advanced-helper {{
  font-size: var(--fs-label);
  color: var(--color-text-dim);
  margin: var(--space-2) 0;
}}
.open-form small {{
  font-size: var(--fs-label);
  color: var(--color-text-dim);
}}
.btn-primary {{
  background: transparent;
  color: var(--color-long);
  border: 1px solid var(--color-long);
  border-radius: 4px;
  padding: var(--space-2) var(--space-4);
  font-size: var(--fs-body);
  font-weight: 600;
  cursor: pointer;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}}
.btn-primary:hover {{ background: rgba(34, 197, 94, 0.10); }}
.btn-primary:disabled {{
  color: var(--color-text-dim);
  border-color: var(--color-text-dim);
  cursor: not-allowed;
  background: transparent;
}}
.btn-row {{
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 4px var(--space-3);
  font-size: var(--fs-label);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  cursor: pointer;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}}
.btn-row.btn-close {{ color: var(--color-short); border-color: var(--color-short); }}
.btn-row.btn-close:hover {{ background: rgba(239, 68, 68, 0.10); }}
.btn-row.btn-modify {{ color: var(--color-flat); border-color: var(--color-flat); }}
.btn-row.btn-modify:hover {{ background: rgba(234, 179, 8, 0.10); }}
.btn-row + .btn-row {{ margin-left: var(--space-2); }}
.badge {{
  display: inline-block;
  padding: 2px 6px;
  margin-left: var(--space-2);
  font-size: var(--fs-label);
  font-weight: 600;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  text-transform: lowercase;
  border-radius: 4px;
  letter-spacing: 0;
}}
.badge-manual {{
  background: rgba(234, 179, 8, 0.10);
  color: var(--color-flat);
}}
.error {{
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-short);
  background: var(--color-surface);
  padding: var(--space-3);
  margin-top: var(--space-4);
  border-radius: 4px;
}}
.error-heading {{
  font-size: var(--fs-body);
  font-weight: 400;
  color: var(--color-text);
  margin: 0 0 var(--space-2);
}}
.error-row {{
  font-size: var(--fs-label);
  color: var(--color-text-muted);
  margin: 0;
  padding: 2px 0;
}}
.error-row code {{
  font-family: var(--font-mono);
  color: var(--color-text);
}}
#confirmation-banner {{
  margin: var(--space-4) 0;
}}
.banner-success {{
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-long);
  border-radius: 4px;
  padding: var(--space-3);
  color: var(--color-text);
  margin: 0;
}}
@media (max-width: 720px) {{
  .open-form .field {{ min-width: 100%; }}
}}
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
  '''D-16 (Phase 8): use state['initial_account'] as the baseline;
  fall through to system_params.INITIAL_ACCOUNT for pre-Phase-8 state
  that missed _migrate v2 backfill (defense-in-depth).
  '''
  initial = state.get('initial_account', INITIAL_ACCOUNT)
  eq_hist = state.get('equity_history', [])
  if eq_hist:
    current = eq_hist[-1].get('equity', state.get('account', initial))
  else:
    current = state.get('account', initial)
  total_return = (current - initial) / initial
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

  Phase 14 D-09 + UI-SPEC §Decision 6: manual_stop precedence — when operator
  has set a stop via /trades/modify (position['manual_stop'] is not None),
  return that value directly. Mirrors sizing_engine.get_trailing_stop precedence
  (CLAUDE.md hex-lite lockstep). NaN guard on atr_entry runs FIRST so the
  parity test against sizing_engine.get_trailing_stop holds bit-identically
  for the NaN-pass-through case (B-1).

  Pitfall 5: position.get('manual_stop') so pre-migration position dicts
  (no key) silently fall through to computed.
  '''
  atr_entry = position['atr_entry']
  if not math.isfinite(atr_entry):
    return float('nan')  # B-1: NaN-pass-through (lockstep with sizing_engine)
  # Phase 14 D-09: manual_stop takes precedence over computed trailing stop.
  manual = position.get('manual_stop')
  if manual is not None:
    return manual
  if position['direction'] == 'LONG':
    peak = position.get('peak_price') or position['entry_price']
    return peak - TRAIL_MULT_LONG * atr_entry
  trough = position.get('trough_price') or position['entry_price']
  return trough + TRAIL_MULT_SHORT * atr_entry


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
  if current_close is None:
    return None
  resolved = None
  if state is not None:
    resolved = state.get('_resolved_contracts', {}).get(state_key)
  if resolved is not None:
    multiplier = resolved['multiplier']
    cost_aud_round_trip = resolved['cost_aud']
  else:
    logger.debug(
      '[Dashboard] _resolved_contracts missing for %s; falling back to '
      'module-level _CONTRACT_SPECS default tier', state_key,
    )
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
    # D-08 upgrade branch (Pitfall 7 from Phase 4): state['signals'][key] may be
    # either an int (Phase 3 reset_state shape) OR a dict (Phase 4 nested shape).
    # Rule 1 auto-fix during Wave 2: regenerator hit AttributeError on reset
    # state fixture which has int shape. Renderer must handle both.
    if sig_entry is None:
      label = html.escape(_fmt_em_dash(), quote=True)
      colour = html.escape(_COLOR_FLAT, quote=True)
      signal_as_of_line = 'Signal as of never'
      scalars_line = html.escape(_fmt_em_dash(), quote=True)
    elif isinstance(sig_entry, int):
      # Phase 3 int shape: no signal_as_of, no last_scalars — render as FLAT
      # (or the literal signal value if mapped) with "never" timestamp.
      label = html.escape(_SIGNAL_LABEL.get(sig_entry, _fmt_em_dash()), quote=True)
      colour = html.escape(_SIGNAL_COLOUR.get(sig_entry, _COLOR_FLAT), quote=True)
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


def _render_open_form() -> str:
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
  return (
    '<section class="open-form" '
    '''hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'>\n'''
    '  <p class="eyebrow">OPEN NEW POSITION</p>\n'
    '  <form\n'
    '    hx-post="/trades/open"\n'
    '    hx-swap="none"\n'
    '    hx-on::after-request="handleTradesError(event)"\n'
    '  >\n'
    '    <div class="field">\n'
    '      <label for="open-form-instrument">Instrument</label>\n'
    '      <select id="open-form-instrument" name="instrument" required>\n'
    '        <option value="SPI200">SPI200</option>\n'
    '        <option value="AUDUSD">AUDUSD</option>\n'
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
    '    <button type="submit" class="btn-primary">Open Position</button>\n'
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
  display = _INSTRUMENT_DISPLAY_NAMES.get(state_key, state_key)
  signals = state.get('signals', {})
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
  trail_currency = html.escape(_fmt_currency(trail_stop), quote=True)
  # Phase 14 D-09 + UI-SPEC §Decision 6: manual_stop badge.
  if pos.get('manual_stop') is not None:
    trail_cell = (
      f'{trail_currency} '
      f'<span class="badge badge-manual" '
      f'title="Operator override — set via /trades/modify. '
      f'Clear by submitting Modify with new_stop blank.">manual</span>'
    )
  else:
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
    f'        <td><span style="color: {dir_colour}">{dir_label}</span></td>\n'
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


def _render_positions_table(state: dict) -> str:
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
  positions = state.get('positions', {})
  tbody_blocks = []
  any_position = False
  for state_key in _INSTRUMENT_DISPLAY_NAMES:
    pos = positions.get(state_key)
    if pos is None:
      continue
    any_position = True
    state_key_esc = html.escape(state_key, quote=True)
    row_html = _render_single_position_row(state, state_key, pos)
    # Per-instrument tbody — REVIEWS HIGH #3 + HIGH #4.
    # f-string brace escaping: {{ → { and }} → } in the rendered output.
    # The hx-headers attribute literally contains "{{WEB_AUTH_SECRET}}"
    # (the on-disk placeholder) — substituted at GET / time by
    # web/routes/dashboard.py per Plan 14-04 Task 5.
    tbody_blocks.append(
      f'    <tbody id="position-group-{state_key_esc}" '
      f'''hx-headers='{{"X-Trading-Signals-Auth": "{{{{WEB_AUTH_SECRET}}}}"}}' '''
      f'hx-trigger="positions-changed from:body" '
      f'hx-get="/?fragment=position-group-{state_key_esc}" '
      f'hx-swap="innerHTML">\n'
      f'{row_html}'
      f'    </tbody>\n'
    )
  if not any_position:
    tbody_blocks.append(
      '    <tbody id="positions-empty">\n'
      '      <tr>\n'
      '        <td colspan="9" class="empty-state">— No open positions —</td>\n'
      '      </tr>\n'
      '    </tbody>\n'
    )
  return (
    _render_open_form()
    + '<section aria-labelledby="heading-positions">\n'
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
    '        <th scope="col">Actions</th>\n'
    '      </tr>\n'
    '    </thead>\n'
    f'{"".join(tbody_blocks)}'
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
  '''DASH-04 / CONTEXT D-11 / UI-SPEC §Chart Component. Category x-axis.

  JSON payload injection defence (Pitfall 1): json.dumps + .replace('</', '<\\/').

  D-13 empty state: if equity_history is empty, render a placeholder <div>
  rather than an instantiated Chart.js canvas (avoids a blank chart band
  with no indication of why).
  '''
  equity_history = state.get('equity_history', [])
  if not equity_history:
    return (
      '<section aria-labelledby="heading-equity">\n'
      '  <h2 id="heading-equity">Equity Curve</h2>\n'
      '  <div class="chart-container empty-state">'
      'No equity history yet — first full run needed'
      '</div>\n'
      '</section>\n'
    )
  # Build labels + data as plain lists, then JSON-serialise with
  # <script>-close injection defence (Pitfall 1) and byte-stable dict
  # ordering (Pitfall 2).
  labels = [row['date'] for row in equity_history]
  data = [float(row['equity']) for row in equity_history]
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


def _render_html_shell(body: str) -> str:
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
    '  <script>\n'
    + _HANDLE_TRADES_ERROR_JS +
    '  </script>\n'
    f'  <style>{_INLINE_CSS}</style>\n'
    '</head>\n'
    '<body>\n'
    '  <div class="container">\n'
    '    <div id="confirmation-banner"></div>\n'
    f'{body}'
    '  </div>\n'
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
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
      newline='\n',  # C-7 reviews: force LF regardless of platform
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    # tempfile is now closed (NamedTemporaryFile context exit)
    # D-17: os.replace BEFORE parent-dir fsync (rename durability)
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None  # success: do not delete in finally
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass


# =========================================================================
# Public API — D-01
# =========================================================================

def render_dashboard(
  state: dict,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
) -> None:
  '''Public API per CONTEXT D-01. Writes dashboard.html atomically; never mutates state.

  Block order MUST match UI-SPEC §Component Hierarchy Rendering-order rule:
  header → signal cards → equity chart → positions table → closed trades →
  key stats → footer.

  C-1 reviews: when `now` is None, construct AWST wall-clock via
  PERTH.localize(datetime.now()) — NEVER via `datetime(..., tzinfo=PERTH)`
  which silently adopts the historical LMT offset (+07:43:24 for Perth
  pre-1895).
  '''
  if now is None:
    perth = pytz.timezone('Australia/Perth')
    now = datetime.now(perth)
  logger.info('[Dashboard] rendering to %s', out_path)
  body = (
    _render_header(state, now)
    + _render_signal_cards(state)
    + _render_equity_chart_container(state)
    + _render_positions_table(state)
    + _render_trades_table(state)
    + _render_key_stats(state)
    + _render_footer()
  )
  html_str = _render_html_shell(body)
  _atomic_write_html(html_str, out_path)
  logger.info('[Dashboard] wrote %d bytes to %s', len(html_str), out_path)


if __name__ == '__main__':
  # C-6 reviews: CONTEXT D-05 convenience CLI. `python -m dashboard` loads
  # the current state.json and renders dashboard.html using the current
  # AWST wall-clock. Never used by CI; operator-only preview path.
  # render_dashboard(now=None) defaults to PERTH.localize-equivalent
  # datetime.now(PERTH), so we just pass load_state() and a default path.
  render_dashboard(load_state(), Path('dashboard.html'))
