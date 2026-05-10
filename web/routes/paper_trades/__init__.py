'''POST /paper-trade/open + PATCH/DELETE /paper-trade/<id> + POST /paper-trade/<id>/close
+ GET /paper-trade/<id>/close-form + GET /paper-trades — Phase 19 LEDGER-01..06 + VERSION-03.

Operator records paper trades (open/edit/delete/close) via this adapter. Every mutation
goes through state_manager.mutate_state (Phase 14 flock kernel — unchanged). Closed rows
are immutable (405 + Allow: GET per RFC 7231 §6.5.5). Composite trade ID generated inside
the mutate_state closure under LOCK_EX (D-01 + D-15 atomicity).

Phase 30 D-08: converted from a single 493-LOC file into a package.
  _models.py   — Pydantic request models + sentinel exceptions
  _renderers.py — constants (_D09_KEYS, _MULTIPLIER, _COST_AUD) + _method_not_allowed_405
  __init__.py  — register(app) + D-03 re-export surface

Log prefix: [Web].
'''
import html
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from web.routes.paper_trades._models import (
  _now_awst,
  _parse_form,
  _PaperTradeNotFound,
  _PaperTradeImmutable,
  _PaperTradeIDOverflow,
  OpenPaperTradeRequest,
  EditPaperTradeRequest,
  ClosePaperTradeRequest,
)
from web.routes.paper_trades._renderers import (
  _COST_AUD,
  _MULTIPLIER,
  _D09_KEYS,
  _method_not_allowed_405,
)

logger = logging.getLogger(__name__)

_LOG_PREFIX = '[Web]'

# D-03 import-surface preservation — service layer + tests import these
# names directly from `web.routes.paper_trades`. Re-export from the package
# so the import path is unchanged.
__all__ = [
  'register',
  'OpenPaperTradeRequest', 'EditPaperTradeRequest', 'ClosePaperTradeRequest',
  '_PaperTradeNotFound', '_PaperTradeImmutable', '_PaperTradeIDOverflow',
  '_D09_KEYS', '_MULTIPLIER', '_COST_AUD',
]


def register(app: FastAPI) -> None:  # noqa: C901 — route surface, acceptable length
  '''Mount all six Phase 19 paper-trade routes on the FastAPI app.

  Mirrors web/routes/trades.py::register pattern (Phase 14 analog).
  AuthMiddleware gates all routes uniformly — no per-route auth code here.
  '''

  # -----------------------------------------------------------------------
  # GET /paper-trades — list fragment (HTMX swap target after every mutation)
  # -----------------------------------------------------------------------
  @app.get('/paper-trades', response_class=HTMLResponse)
  async def get_paper_trades_fragment(request: Request) -> HTMLResponse:
    '''Return rendered #trades-region HTML fragment. Used as HTMX hx-target
    for all mutations.
    '''
    from state_manager import load_state
    from dashboard import _render_paper_trades_region
    state = load_state()
    return HTMLResponse(content=_render_paper_trades_region(state))

  # -----------------------------------------------------------------------
  # POST /paper-trade/open
  # -----------------------------------------------------------------------
  @app.post('/paper-trade/open', response_class=HTMLResponse)
  async def open_paper_trade(request: Request) -> HTMLResponse:
    '''Validate D-04, generate composite ID inside flock, append row to
    state.paper_trades. Returns rendered #trades-region HTML fragment.

    D-17 gap-closure: accepts application/x-www-form-urlencoded (browser/HTMX default).
    '''
    req = await _parse_form(request, OpenPaperTradeRequest)
    def _apply(state: dict) -> None:
      # Fresh import inside closure — kwarg-default capture trap prevention
      # (LEARNINGS 2026-04-29 + planner D-19).
      from system_params import STRATEGY_VERSION  # noqa: PLC0415

      rows = state.setdefault('paper_trades', [])
      today_awst = _now_awst().strftime('%Y%m%d')
      prefix = f'{req.instrument}-{today_awst}-'
      same_day = [r for r in rows if r['id'].startswith(prefix)]
      if len(same_day) >= 999:
        raise _PaperTradeIDOverflow(req.instrument, today_awst)
      counter = len(same_day) + 1
      trade_id = f'{prefix}{counter:03d}'
      # Phase 27 WR-01: route raw cost split through pnl_engine.entry_side_cost
      # so the AUD-cent boundary uses the canonical HALF_UP-rounded helper.
      from pnl_engine import entry_side_cost  # noqa: PLC0415 — local import per planner D-19
      entry_cost_aud = float(entry_side_cost(_COST_AUD[req.instrument]))
      rows.append({
        'id': trade_id,
        'instrument': req.instrument,
        'side': req.side,
        'entry_dt': req.entry_dt.isoformat(),
        'entry_price': req.entry_price,
        'contracts': req.contracts,
        'stop_price': req.stop_price,
        'entry_cost_aud': entry_cost_aud,
        'status': 'open',
        'exit_dt': None,
        'exit_price': None,
        'realised_pnl': None,
        'strategy_version': STRATEGY_VERSION,
      })

    try:
      from state_manager import mutate_state
      state = mutate_state(_apply)
    except _PaperTradeIDOverflow as exc:
      logger.warning(
        '%s ID counter overflow %s %s', _LOG_PREFIX, exc.instrument, exc.day,
      )
      raise HTTPException(
        status_code=400,
        detail=f'counter overflow for {exc.instrument} on {exc.day} (999 limit)',
      )

    from dashboard import _render_paper_trades_region
    return HTMLResponse(content=_render_paper_trades_region(state))

  # -----------------------------------------------------------------------
  # PATCH /paper-trade/{trade_id}
  # -----------------------------------------------------------------------
  @app.patch('/paper-trade/{trade_id}', response_class=HTMLResponse)
  async def edit_paper_trade(trade_id: str, request: Request) -> HTMLResponse:
    '''Edit an open paper trade row in-place. Closed rows return 405.
    D-05: strategy_version is refreshed to current STRATEGY_VERSION on edit.

    D-17 gap-closure: accepts application/x-www-form-urlencoded (browser/HTMX default).
    '''
    req = await _parse_form(request, EditPaperTradeRequest)
    def _apply(state: dict) -> None:
      from system_params import STRATEGY_VERSION  # noqa: PLC0415 — fresh import (kwarg trap)

      rows = state.get('paper_trades', [])
      matches = [r for r in rows if r['id'] == trade_id]
      if not matches:
        raise _PaperTradeNotFound(trade_id)
      row = matches[0]
      if row['status'] == 'closed':
        raise _PaperTradeImmutable(trade_id)

      # Apply partial updates (only fields that were supplied)
      if req.instrument is not None:
        row['instrument'] = req.instrument
      if req.side is not None:
        row['side'] = req.side
      if req.entry_dt is not None:
        row['entry_dt'] = req.entry_dt.isoformat()
      if req.entry_price is not None:
        row['entry_price'] = req.entry_price
      if req.contracts is not None:
        row['contracts'] = req.contracts
      # stop_price: allow explicit set to None (clear stop) or new value
      if 'stop_price' in (req.model_fields_set or set()):
        row['stop_price'] = req.stop_price

      # D-05: refresh strategy_version on edit (operator hasn't resolved the trade yet)
      row['strategy_version'] = STRATEGY_VERSION
      # Phase 20 D-09: reset last_alert_state on edit so next daily run recomputes.
      # Operator has changed the stop; prior alert state is stale.
      row['last_alert_state'] = None

    try:
      from state_manager import mutate_state
      state = mutate_state(_apply)
    except _PaperTradeNotFound:
      raise HTTPException(status_code=404, detail=f'paper trade {trade_id!r} not found')
    except _PaperTradeImmutable:
      return _method_not_allowed_405('GET')

    from dashboard import _render_paper_trades_region
    return HTMLResponse(content=_render_paper_trades_region(state))

  # -----------------------------------------------------------------------
  # DELETE /paper-trade/{trade_id}
  # -----------------------------------------------------------------------
  @app.delete('/paper-trade/{trade_id}', response_class=HTMLResponse)
  async def delete_paper_trade(trade_id: str) -> HTMLResponse:
    '''Remove an open paper trade row entirely. Closed rows return 405.
    D-21: no body on DELETE.
    '''
    def _apply(state: dict) -> None:
      rows = state.get('paper_trades', [])
      matches = [r for r in rows if r['id'] == trade_id]
      if not matches:
        raise _PaperTradeNotFound(trade_id)
      row = matches[0]
      if row['status'] == 'closed':
        raise _PaperTradeImmutable(trade_id)
      state['paper_trades'] = [r for r in rows if r['id'] != trade_id]

    try:
      from state_manager import mutate_state
      state = mutate_state(_apply)
    except _PaperTradeNotFound:
      raise HTTPException(status_code=404, detail=f'paper trade {trade_id!r} not found')
    except _PaperTradeImmutable:
      return _method_not_allowed_405('GET')

    from dashboard import _render_paper_trades_region
    return HTMLResponse(content=_render_paper_trades_region(state))

  # -----------------------------------------------------------------------
  # POST /paper-trade/{trade_id}/close
  # -----------------------------------------------------------------------
  @app.post('/paper-trade/{trade_id}/close', response_class=HTMLResponse)
  async def close_paper_trade(trade_id: str, request: Request) -> HTMLResponse:
    '''Close an open paper trade: compute realised P&L via pnl_engine, flip
    status=closed. Closed rows return 405 (D-05 immutability).

    D-17 gap-closure: accepts application/x-www-form-urlencoded (browser/HTMX default).
    '''
    req = await _parse_form(request, ClosePaperTradeRequest)
    def _apply(state: dict) -> None:
      from pnl_engine import compute_realised_pnl  # LOCAL — Phase 11 C-2

      rows = state.get('paper_trades', [])
      matches = [r for r in rows if r['id'] == trade_id]
      if not matches:
        raise _PaperTradeNotFound(trade_id)
      row = matches[0]
      if row['status'] == 'closed':
        raise _PaperTradeImmutable(trade_id)

      # D-04 close validation: exit_dt must be >= entry_dt
      from datetime import datetime as _dt
      import zoneinfo as _zi
      entry_dt_raw = row['entry_dt']
      entry_dt = _dt.fromisoformat(entry_dt_raw)
      exit_dt_aware = req.exit_dt
      if exit_dt_aware.tzinfo is None:
        exit_dt_aware = req.exit_dt.replace(tzinfo=_zi.ZoneInfo('Australia/Perth'))
      if entry_dt.tzinfo is None:
        entry_dt = entry_dt.replace(tzinfo=_zi.ZoneInfo('Australia/Perth'))
      if exit_dt_aware < entry_dt:
        raise HTTPException(
          status_code=400,
          detail='exit_dt: must not be before entry_dt of the trade being closed',
        )

      mult = _MULTIPLIER[row['instrument']]
      rt_cost = _COST_AUD[row['instrument']]  # full round-trip per CONTEXT D-11
      realised = compute_realised_pnl(
        row['side'], row['entry_price'], req.exit_price,
        row['contracts'], mult, rt_cost,
      )
      # Phase 27 #1: pnl_engine returns Decimal AUD-quantized; coerce to float
      # at the persistence boundary so state['paper_trades'] rows stay
      # float-typed (downstream readers — dashboard rendering, accumulators,
      # state_manager v8→v9 quantize-on-save — all consume float). The
      # AUD-cent precision is preserved by the v9 quantize-on-save migrator.
      row['realised_pnl'] = float(realised)
      row['exit_price'] = req.exit_price
      row['exit_dt'] = req.exit_dt.isoformat()
      row['status'] = 'closed'

    try:
      from state_manager import mutate_state
      state = mutate_state(_apply)
    except _PaperTradeNotFound:
      raise HTTPException(status_code=404, detail=f'paper trade {trade_id!r} not found')
    except _PaperTradeImmutable:
      return _method_not_allowed_405('GET')
    except HTTPException:
      raise  # re-raise HTTPException from within _apply (exit_dt validation)

    from dashboard import _render_paper_trades_region
    return HTMLResponse(content=_render_paper_trades_region(state))

  # -----------------------------------------------------------------------
  # GET /paper-trade/{trade_id}/close-form
  # -----------------------------------------------------------------------
  @app.get('/paper-trade/{trade_id}/close-form', response_class=HTMLResponse)
  async def get_close_form(trade_id: str) -> HTMLResponse:
    '''Return a close-form HTML fragment with hx-post baked into the action.
    Trade ID travels in URL per RESEARCH §Pattern 1 (Phase 14 close-form precedent).
    '''
    from state_manager import load_state
    state = load_state()
    rows = state.get('paper_trades', [])
    matches = [r for r in rows if r['id'] == trade_id]
    if not matches:
      raise HTTPException(status_code=404, detail=f'paper trade {trade_id!r} not found')
    row = matches[0]
    esc_id = html.escape(trade_id, quote=True)
    now_awst = _now_awst().strftime('%Y-%m-%dT%H:%M')
    frag = (
      f'<section id="close-form-section">\n'
      f'  <h3>Close Trade: {esc_id}</h3>\n'
      f'  <form hx-post="/paper-trade/{esc_id}/close"\n'
      f'        hx-target="#trades-region"\n'
      f'        hx-swap="outerHTML"\n'
      f'        enctype="application/x-www-form-urlencoded">\n'
      f'    <label>Exit date/time (AEST)\n'
      f'      <input type="datetime-local" name="exit_dt" value="{now_awst}" required>\n'
      f'    </label>\n'
      f'    <label>Exit price\n'
      f'      <input type="number" name="exit_price" step="0.0001" min="0.0001" required>\n'
      f'    </label>\n'
      f'    <button type="submit">Close position</button>\n'
      f'    <button type="button" hx-get="/paper-trades"\n'
      f'            hx-target="#trades-region" hx-swap="outerHTML">Cancel</button>\n'
      f'  </form>\n'
      f'</section>\n'
    )
    return HTMLResponse(content=frag)
