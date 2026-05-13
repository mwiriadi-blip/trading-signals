'''POST /trades/{open,close,modify} — Phase 14 TRADE-01..06 + D-01..D-13.

Package init: exports register(app) and the public import surface
(OpenTradeRequest, CloseTradeRequest, ModifyTradeRequest).

Phase 30 D-04 boundary split: single-file 746-LOC trades.py converted
to a 3-file package. ZERO behaviour changes.

Phase 36: migrated all mutate_state → mutate_user_state; all _apply bodies
navigate state['users'][user_id]; read-path GET handlers use load_user_state
and return 404 when position is None.
'''
import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

from web.dependencies import current_user_id
from web.routes.trades._models import (
  _OPERATOR_CLOSE,
  CloseTradeRequest,
  ModifyTradeRequest,
  OpenTradeRequest,
  _build_position_dict,
  _now_awst,
  _OpenConflict,
  _validation_exception_handler,
)
from web.routes.trades._renderers import (
  _render_close_form_partial,
  _render_close_success_partial,
  _render_modify_form_partial,
  _render_modify_success_partial,
  _render_open_success_partial,
  _render_position_row_partial,
)

logger = logging.getLogger(__name__)


# =========================================================================
# register() — six endpoint handlers as nested functions
# =========================================================================


def register(app: FastAPI) -> None:
  '''Register six Phase 14 endpoints on the given FastAPI instance.

  Three POST mutations + three GET HTMX support endpoints. The
  RequestValidationError handler is registered separately by web/app.py
  (so the handler covers all routes, not just /trades/*).
  '''

  @app.post('/trades/open')
  def open_trade(req: OpenTradeRequest, user_id: str = Depends(current_user_id)):
    '''Phase 14 TRADE-01 + D-01..D-04 + D-13 (REVIEWS HIGH #1: mutate_user_state).'''
    # Phase 11 C-2 + Phase 14 D-13: local imports preserve hex boundary
    from sizing_engine import check_pyramid
    from state_manager import mutate_user_state

    # Captured in closure for response rendering after mutate returns.
    result_holder: dict = {'kind': None, 'extra': None}

    def _apply(state):
      user = state['users'][user_id]
      known_markets = state.get('markets') or state.get('positions', {})
      if req.instrument not in known_markets:
        raise _OpenConflict(f'unknown market {req.instrument}')
      existing = user['positions'].get(req.instrument)
      if existing is not None and existing['direction'] != req.direction:
        # D-01: opposite direction is a hard conflict
        msg = (
          f'instrument {req.instrument} already has an open '
          f'{existing["direction"]} position; close it first via '
          f'POST /trades/close before opening a {req.direction}'
        )
        result_holder['kind'] = 'conflict_opposite'
        result_holder['extra'] = msg
        # Raise to short-circuit out of mutate_user_state; lock released by
        # mutate_user_state's finally.
        raise _OpenConflict(msg)

      if existing is not None and existing['direction'] == req.direction:
        # D-02 + REVIEWS MEDIUM #7: ATR lookup is nested under last_scalars
        sig_entry = state.get('signals', {}).get(req.instrument, {})
        if not isinstance(sig_entry, dict):
          result_holder['kind'] = 'conflict_no_atr'
          result_holder['extra'] = 'pyramid blocked: no ATR available in state.signals'
          raise _OpenConflict(result_holder['extra'])
        atr_entry = sig_entry.get('last_scalars', {}).get('atr')
        if atr_entry is None:
          result_holder['kind'] = 'conflict_no_atr'
          result_holder['extra'] = 'pyramid blocked: no ATR available in state.signals'
          raise _OpenConflict(result_holder['extra'])

        decision = check_pyramid(existing, current_price=req.entry_price, atr_entry=atr_entry)
        if decision.add_contracts == 0:
          result_holder['kind'] = 'conflict_pyramid_blocked'
          result_holder['extra'] = 'Pyramid blocked: gate not met or already at MAX_PYRAMID_LEVEL'
          raise _OpenConflict(result_holder['extra'])
        # Apply pyramid-up
        existing['n_contracts'] += decision.add_contracts
        existing['pyramid_level'] = decision.new_level
        result_holder['kind'] = 'pyramid_up'
        return

      # Fresh-open path
      sig_entry = state.get('signals', {}).get(req.instrument, {})
      atr_entry = (
        sig_entry.get('last_scalars', {}).get('atr')
        if isinstance(sig_entry, dict) else None
      )
      if atr_entry is None:
        result_holder['kind'] = 'conflict_no_atr'
        result_holder['extra'] = (
          'open blocked: no ATR available in state.signals; '
          'daily run must complete first'
        )
        raise _OpenConflict(result_holder['extra'])

      executed_at = req.executed_at or _now_awst().date()
      user['positions'][req.instrument] = _build_position_dict(req, executed_at, atr_entry)
      result_holder['kind'] = 'fresh_open'
      # Phase 15 D-02: drift recompute after position mutation.
      from sizing_engine import detect_drift  # LOCAL — C-2
      from state_manager import append_warning, clear_warnings_by_source  # LOCAL — C-2
      clear_warnings_by_source(state, 'drift')
      for ev in detect_drift(user.get('positions', {}), state.get('signals', {})):
        append_warning(state, source='drift', message=ev.message)

    try:
      state = mutate_user_state(user_id, _apply)
    except _OpenConflict as exc:
      logger.warning('[Web] /trades/open conflict: %s', exc)
      if str(exc).startswith('unknown market '):
        return JSONResponse(
          status_code=400,
          content={'errors': [{'field': 'instrument', 'reason': str(exc)}]},
        )
      return Response(
        content=str(exc), status_code=409,
        media_type='text/plain; charset=utf-8',
      )

    logger.info(
      '[Web] /trades/open %s: instrument=%s direction=%s entry=%s contracts=%d',
      result_holder['kind'], req.instrument, req.direction,
      req.entry_price, req.contracts,
    )
    # Renderers need positions at top-level; inject from user bucket.
    user_state = state['users'][user_id]
    display_state = {**state, 'positions': user_state['positions']}
    return _render_open_success_partial(
      display_state, req.instrument, req.direction, req.entry_price, req.contracts,
    )

  @app.post('/trades/close')
  def close_trade(req: CloseTradeRequest, user_id: str = Depends(current_user_id)):
    '''Phase 14 TRADE-03 + D-05..D-08 + D-13 (REVIEWS HIGH #1: mutate_user_state).'''
    from state_manager import mutate_user_state, record_trade

    capture: dict = {'gross_pnl': None, 'cost_aud': None, 'n_contracts': None}

    def _apply(state):
      user = state['users'][user_id]
      known_markets = state.get('markets') or state.get('positions', {})
      if req.instrument not in known_markets:
        raise _OpenConflict(f'unknown market {req.instrument}')
      pos = user['positions'].get(req.instrument)
      if pos is None:
        msg = f'no open position for instrument {req.instrument}'
        raise _OpenConflict(msg)
      # D-07: read multiplier and cost_aud from _resolved_contracts
      resolved = state['_resolved_contracts'][req.instrument]
      multiplier = resolved['multiplier']
      cost_aud = resolved['cost_aud']

      if pos['direction'] == 'LONG':
        gross_pnl = (req.exit_price - pos['entry_price']) * pos['n_contracts'] * multiplier
      else:  # SHORT
        gross_pnl = (pos['entry_price'] - req.exit_price) * pos['n_contracts'] * multiplier
      capture['gross_pnl'] = gross_pnl
      capture['cost_aud'] = cost_aud
      capture['n_contracts'] = pos['n_contracts']

      exit_date = (req.executed_at or _now_awst().date()).isoformat()
      trade = {
        'instrument': req.instrument,
        'direction': pos['direction'],
        'n_contracts': pos['n_contracts'],
        'entry_date': pos['entry_date'],
        'exit_date': exit_date,
        'exit_reason': _OPERATOR_CLOSE,
        'entry_price': pos['entry_price'],
        'exit_price': req.exit_price,
        'gross_pnl': gross_pnl,
        'multiplier': multiplier,
        'cost_aud': cost_aud,
      }
      # Phase 36: pass uid=user_id so record_trade writes to the correct bucket.
      record_trade(state, trade, uid=user_id)
      # Phase 15 D-02: drift recompute after position mutation.
      from sizing_engine import detect_drift  # LOCAL — C-2
      from state_manager import append_warning, clear_warnings_by_source  # LOCAL — C-2
      clear_warnings_by_source(state, 'drift')
      for ev in detect_drift(user.get('positions', {}), state.get('signals', {})):
        append_warning(state, source='drift', message=ev.message)

    try:
      mutate_user_state(user_id, _apply)
    except _OpenConflict as exc:
      logger.warning('[Web] /trades/close conflict: %s', exc)
      return Response(
        content=str(exc), status_code=409,
        media_type='text/plain; charset=utf-8',
      )

    logger.info(
      '[Web] /trades/close completed: instrument=%s gross_pnl=%.2f',
      req.instrument, capture['gross_pnl'],
    )
    return _render_close_success_partial(
      req.instrument, capture['gross_pnl'],
      capture['cost_aud'], capture['n_contracts'],
    )

  @app.post('/trades/modify')
  def modify_trade(req: ModifyTradeRequest, user_id: str = Depends(current_user_id)):
    '''Phase 14 TRADE-04 + D-09..D-13 + REVIEWS LOW #9 (pyramid resets on ANY modify).'''
    from state_manager import mutate_user_state

    def _apply(state):
      user = state['users'][user_id]
      known_markets = state.get('markets') or state.get('positions', {})
      if req.instrument not in known_markets:
        raise _OpenConflict(f'unknown market {req.instrument}')
      pos = user['positions'].get(req.instrument)
      if pos is None:
        msg = f'no open position for instrument {req.instrument}'
        raise _OpenConflict(msg)
      if 'new_stop' in req.model_fields_set:
        pos['manual_stop'] = req.new_stop
      if 'new_contracts' in req.model_fields_set and req.new_contracts is not None:
        pos['n_contracts'] = req.new_contracts
      # REVIEWS LOW #9 / D-10: pyramid_level resets on ANY successful modify
      pos['pyramid_level'] = 0
      # Phase 15 D-02: drift recompute after position mutation.
      from sizing_engine import detect_drift  # LOCAL — C-2
      from state_manager import append_warning, clear_warnings_by_source  # LOCAL — C-2
      clear_warnings_by_source(state, 'drift')
      for ev in detect_drift(user.get('positions', {}), state.get('signals', {})):
        append_warning(state, source='drift', message=ev.message)

    try:
      state = mutate_user_state(user_id, _apply)
    except _OpenConflict as exc:
      logger.warning('[Web] /trades/modify conflict: %s', exc)
      return Response(
        content=str(exc), status_code=409,
        media_type='text/plain; charset=utf-8',
      )

    logger.info(
      '[Web] /trades/modify completed: instrument=%s fields=%s',
      req.instrument,
      sorted(req.model_fields_set & {'new_stop', 'new_contracts'}),
    )
    user_state = state['users'][user_id]
    display_state = {**state, 'positions': user_state['positions']}
    return _render_modify_success_partial(display_state, req.instrument)

  @app.get('/trades/close-form')
  def close_form(instrument: str, user_id: str = Depends(current_user_id)):
    '''UI-SPEC §Decision 5: 2-stage destructive close confirmation panel.

    Phase 36: reads from user bucket via load_user_state. Returns 404 if
    the user has no position for this instrument (not their position or
    position is None) — prevents IDOR and gives correct 404 semantics.
    '''
    from state_manager import load_state, load_user_state
    state = load_state()
    positions = load_user_state(user_id)['positions']
    pos = positions.get(instrument)
    if pos is None:
      raise HTTPException(
        status_code=404,
        detail=f'No open position for {instrument}',
      )
    display_state = {**state, 'positions': positions}
    return HTMLResponse(content=_render_close_form_partial(display_state, instrument, pos))

  @app.get('/trades/modify-form')
  def modify_form(instrument: str, user_id: str = Depends(current_user_id)):
    '''UI-SPEC §Decision 2: inline modify form panel (single <tr>).

    Phase 36: reads from user bucket; 404 if no position for instrument.
    '''
    from state_manager import load_state, load_user_state
    state = load_state()
    positions = load_user_state(user_id)['positions']
    pos = positions.get(instrument)
    if pos is None:
      raise HTTPException(
        status_code=404,
        detail=f'No open position for {instrument}',
      )
    display_state = {**state, 'positions': positions}
    return HTMLResponse(content=_render_modify_form_partial(display_state, instrument, pos))

  @app.get('/trades/cancel-row')
  def cancel_row(instrument: str, user_id: str = Depends(current_user_id)):
    '''Restore a position row. Phase 36: reads from user bucket; 404 if None.'''
    from state_manager import load_state, load_user_state
    state = load_state()
    positions = load_user_state(user_id)['positions']
    pos = positions.get(instrument)
    if pos is None:
      raise HTTPException(
        status_code=404,
        detail=f'No open position for {instrument}',
      )
    display_state = {**state, 'positions': positions}
    return HTMLResponse(content=_render_position_row_partial(display_state, instrument, pos))


# D-03 import-surface preservation — tests and service layer import these names
# directly from `web.routes.trades`. Re-export from the package so the import
# path is unchanged.
__all__ = [
  'register',
  'OpenTradeRequest', 'CloseTradeRequest', 'ModifyTradeRequest',
  '_OpenConflict', '_OPERATOR_CLOSE',
  '_validation_exception_handler',
]
