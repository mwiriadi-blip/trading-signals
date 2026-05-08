"""dashboard_legacy.positions_section — open form, position rows, drift banner, trailing stops, positions/trades tables.

Extracted from dashboard.py (Plan 27-14).
"""
import html
import math

from dashboard_renderer.components.positions import render_positions_table as dr_render_positions_table
from dashboard_renderer.components.trades import render_trades_table as dr_render_trades_table

from dashboard_legacy.render_helpers import (
    _compute_trail_stop_display,
    _compute_unrealised_pnl_display,
    _display_names,
    _fmt_currency,
    _fmt_em_dash,
    _fmt_percent_unsigned,
    _fmt_pnl_with_colour,
    _strategy_settings_for,
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

def _render_drift_banner(state: dict) -> str:
  '''Phase 15 SENTINEL-01/02 + D-11/D-13 + REVIEWS H-2: drift sentinel banner.

  Returns:
    - empty string when no warnings have source='drift'
    - <div class="sentinel-banner sentinel-reversal"> when any drift
      warning message contains 'reversal recommended' (D-13: red border)
    - <div class="sentinel-banner sentinel-drift"> otherwise (amber)

  Body lists each drift warning as a <li> in a <ul class="sentinel-body">.

  Called from render_dashboard_files() body composition (REVIEWS H-2 — top-level
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
