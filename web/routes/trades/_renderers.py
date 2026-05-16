'''HTML partial renderer helpers for web/routes/trades package.

Extracted from web/routes/trades.py (Phase 30 D-04 boundary split).
ZERO behaviour changes — all logic verbatim from the original single file.

Contains:
  _render_position_row_partial
  _render_positions_tbody_partial
  _render_close_form_partial
  _render_modify_form_partial
  _render_open_success_partial
  _render_close_success_partial
  _render_modify_success_partial
'''
import html

from fastapi.responses import HTMLResponse, Response


def _esc(s: object) -> str:
  return html.escape(str(s), quote=True)


def _render_position_row_partial(state, instrument, pos) -> str:
  '''Single <tr id="position-row-{instrument}"> stub.

  Plan 14-05 wires up to dashboard._render_positions_table for full
  parity (Actions column, manual badge, etc.). Plan 14-04 ships a
  minimal-but-valid <tr>. Buttons target #position-group-{instrument}
  with hx-swap="innerHTML" per REVIEWS HIGH #3 (per-instrument tbody
  grouping; entire tbody contents replaced on close/modify form open).
  '''
  esc = _esc
  manual_badge = ''
  if pos.get('manual_stop') is not None:
    manual_badge = '<span class="badge badge-manual" title="Operator override">manual</span>'
  return (
    f'<tr id="position-row-{esc(instrument)}">'
    f'<td>{esc(instrument)}</td>'
    f'<td>{esc(pos["direction"])}</td>'
    f'<td>{esc(pos["entry_price"])}</td>'
    f'<td>{esc(pos["n_contracts"])}</td>'
    f'<td>{manual_badge}</td>'
    f'<td>'
    f'<button class="btn-row btn-close" '
    f'hx-get="/trades/close-form?instrument={esc(instrument)}" '
    f'hx-target="#position-group-{esc(instrument)}" hx-swap="innerHTML">Close</button>'
    f'<button class="btn-row btn-modify" '
    f'hx-get="/trades/modify-form?instrument={esc(instrument)}" '
    f'hx-target="#position-group-{esc(instrument)}" hx-swap="innerHTML">Modify</button>'
    f'</td>'
    f'</tr>'
  )


def _render_positions_tbody_partial(state) -> str:
  '''Re-render the full positions <tbody> contents (UI-SPEC §Decision 3).'''
  rows = []
  for inst in (state.get('markets') or state.get('positions', {})):
    pos = state.get('positions', {}).get(inst)
    if pos is not None:
      rows.append(_render_position_row_partial(state, inst, pos))
  return ''.join(rows)


def _render_close_form_partial(state, instrument, pos) -> str:
  '''REVIEWS HIGH #3: SINGLE confirmation <tr> only.

  The caller (close-form GET handler) returns this string with hx-target
  pointing at #position-group-{instrument} and hx-swap="innerHTML" so
  the entire tbody contents is replaced by this row. Cancel restores
  the original <tr> by GET /trades/cancel-row?instrument={X} which
  returns _render_position_row_partial(state, X, pos).

  Single-tbody-level swap means no orphans: open form / confirmation /
  success state are mutually exclusive contents of the SAME tbody.
  '''
  esc = _esc
  return (
    f'<tr><td colspan="9">'
    f'Close {esc(pos["direction"])} {esc(instrument)} '
    f'({esc(pos["n_contracts"])} contracts) at exit price '
    f'<input type="number" step="0.01" min="0.01" name="exit_price" required autofocus />'
    f'<button type="button" class="btn-row" '
    f'hx-get="/trades/cancel-row?instrument={esc(instrument)}" '
    f'hx-target="#position-group-{esc(instrument)}" hx-swap="innerHTML">Cancel</button>'
    # REVIEW CR-01: hx-ext="json-enc" converts the form-encoded body produced
    # by hx-include="closest tr" + hx-vals into JSON before POST. Without it
    # the FastAPI handler (Pydantic body parameter, no Form(...)) returns 400.
    f'<button type="button" class="btn-row btn-close" '
    f'hx-post="/trades/close" hx-ext="json-enc" hx-include="closest tr" '
    f'hx-vals=\'{{"instrument": "{esc(instrument)}"}}\' '
    f'hx-target="#position-group-{esc(instrument)}" hx-swap="innerHTML" '
    f'hx-on::after-request="handleTradesError(event)">Confirm close</button>'
    f'</td></tr>'
  )


def _render_modify_form_partial(state, instrument, pos) -> str:
  '''REVIEWS HIGH #3: SINGLE confirmation <tr> only — same topology as close-form.'''
  esc = _esc
  return (
    f'<tr><td colspan="9">'
    f'Modify {esc(instrument)}: '
    f'<label>new stop <input type="number" step="0.01" name="new_stop"></label> '
    f'<label>new contracts <input type="number" step="1" min="1" name="new_contracts"></label> '
    f'<button type="button" class="btn-row" '
    f'hx-get="/trades/cancel-row?instrument={esc(instrument)}" '
    f'hx-target="#position-group-{esc(instrument)}" hx-swap="innerHTML">Cancel</button>'
    # REVIEW CR-01: hx-ext="json-enc" — see _render_close_form_partial above.
    f'<button type="button" class="btn-row btn-modify" '
    f'hx-post="/trades/modify" hx-ext="json-enc" hx-include="closest tr" '
    f'hx-vals=\'{{"instrument": "{esc(instrument)}"}}\' '
    f'hx-target="#position-group-{esc(instrument)}" hx-swap="innerHTML">Save</button>'
    f'</td></tr>'
  )


def _render_open_success_partial(state, instrument, direction, entry_price, contracts) -> Response:
  '''Open success -> re-rendered tbody partial + OOB confirmation banner.'''
  escaped_inst = html.escape(instrument, quote=True)
  escaped_dir = html.escape(direction, quote=True)
  banner_html = (
    f'<div hx-swap-oob="innerHTML:#confirmation-banner">'
    f'<p class="banner-success">Opened {escaped_dir} {escaped_inst} '
    f'at {entry_price}, {contracts} contracts.</p>'
    f'</div>'
  )
  tbody_partial = _render_positions_tbody_partial(state)
  return HTMLResponse(
    content=tbody_partial + banner_html,
    status_code=200,
    headers={'HX-Refresh': 'true'},
  )


def _render_close_success_partial(instrument, gross_pnl, cost_aud, n_contracts) -> Response:
  '''Close success — full page refresh so stats/positions update immediately.'''
  return HTMLResponse(
    content='',
    status_code=200,
    headers={'HX-Refresh': 'true'},
  )


def _render_modify_success_partial(state, instrument) -> Response:
  '''Re-render the single position row + OOB confirmation banner.'''
  pos = state['positions'].get(instrument)
  banner_html = (
    f'<div hx-swap-oob="innerHTML:#confirmation-banner">'
    f'<p class="banner-success">Modified {html.escape(instrument)}.</p>'
    f'</div>'
  )
  row_html = _render_position_row_partial(state, instrument, pos) if pos else ''
  return HTMLResponse(
    content=row_html + banner_html, status_code=200,
    headers={'HX-Refresh': 'true'},
  )
