"""dashboard_legacy.paper_trades_section — paper-trade subsections.

Extracted from dashboard.py (Plan 27-14).
"""
import html
import math

from dashboard_renderer.components.paper_trades import (
    render_paper_trades_region as dr_render_paper_trades_region,
)


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
    f'  <div class="stats-bar-item"><span class="label">Win rate</span><span>{html.escape(str(stats["win_rate"]), quote=True)}</span></div>\n'
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
    '  <div class="error" hidden></div>\n'
    '  <form hx-post="/paper-trade/open"\n'
    '        hx-target="#trades-region"\n'
    '        hx-swap="outerHTML"\n'
    '        hx-on::after-request="handleTradesError(event)"\n'
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
    '    <label for="paper-trade-entry-dt">Entry date/time (AEST)</label>\n'
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
    # WR-05: html.escape requires str — None/int row['id'] would crash the
    # render. Force str coercion at the boundary so a malformed paper trade
    # row never reaches html.escape with a non-str argument.
    trade_id = str(row.get('id', '') or '')
    esc_id = html.escape(trade_id, quote=True)
    instrument = str(row.get('instrument', '') or '')
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
        # Phase 27 #1: pnl_engine returns Decimal; coerce to float at the
        # display boundary so f-string formatting + comparisons work uniformly.
        upnl = float(compute_unrealised_pnl(
          row['side'], row['entry_price'], lc_float,
          row['contracts'], _MULT.get(instrument, 1.0),
          row['entry_cost_aud'],
        ))
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
      f'    <td>{html.escape(instrument, quote=True)}</td>\n'
      f'    <td>{html.escape(row.get("side", ""), quote=True)}</td>\n'
      f'    <td>{html.escape(str(row.get("entry_price", "")), quote=True)}</td>\n'
      f'    <td>{html.escape(str(row.get("contracts", "")), quote=True)}</td>\n'
      f'    <td>{html.escape(str(row.get("stop_price") or "—"), quote=True)}</td>\n'
      f'    <td class="{pnl_class}">{html.escape(pnl_str, quote=True)}</td>\n'
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
    # WR-05: same str-coercion guard as the open-trades loop above —
    # html.escape can't take None / int.
    trade_id = str(row.get('id', '') or '')
    esc_id = html.escape(trade_id, quote=True)
    realised = row.get('realised_pnl') or 0.0
    pnl_str = f'{realised:+.2f}'
    pnl_class = (
      'pnl-positive' if realised > 0 else ('pnl-negative' if realised < 0 else 'pnl-zero')
    )
    rows_html += (
      f'  <tr>\n'
      f'    <td data-label="ID">{esc_id}</td>\n'
      f'    <td data-label="Instrument">{html.escape(row.get("instrument", ""), quote=True)}</td>\n'
      f'    <td data-label="Side">{html.escape(row.get("side", ""), quote=True)}</td>\n'
      f'    <td data-label="Entry">{html.escape(str(row.get("entry_price", "")), quote=True)}</td>\n'
      f'    <td data-label="Exit">{html.escape(str(row.get("exit_price", "")), quote=True)}</td>\n'
      f'    <td data-label="Exit Date">{html.escape(str(row.get("exit_dt", "—")), quote=True)}</td>\n'
      f'    <td data-label="Realised P&L" class="{pnl_class}">{html.escape(pnl_str, quote=True)}</td>\n'
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
