'''POST /trades/{open,close,modify} — Phase 14 TRADE-01..06 + D-01..D-13.

Three mutation endpoints + three HTMX support GETs (close-form, modify-form,
cancel-row) that record operator-executed trades in state.json. Every success
flows through state_manager.mutate_state exactly once (TRADE-06; D-11 atomic).

Contract (CONTEXT.md 2026-04-25, REVIEWS HIGH #1/2/3/4 + LOW #8/9/10):
  D-01: opposite-direction position -> 409 with locked message
  D-02: same-direction -> sizing_engine.check_pyramid; should_add=False -> 409
  D-03: peak/trough/pyramid_level coherence checks; reject mismatched direction
  D-04: Pydantic v2; 422 remapped to 400 by app-level handler
  D-05: gross_pnl is INLINE raw price-delta — anti-pitfall against
        sizing_engine's unrealised-pnl helper which would double-deduct
        closing-half cost (record_trade D-14 already deducts it)
  D-06: exit_reason = 'operator_close' literal
  D-07: multiplier + cost_aud from state['_resolved_contracts'][instrument]
  D-08: executed_at? optional -> default today AWST
  D-09: manual_stop on Position; sizing_engine.get_trailing_stop precedence
  D-10: new_contracts mutates n_contracts AND resets pyramid_level=0
  D-11: atomic single mutate_state per modify
  D-12: model_fields_set distinguishes absent (no change) vs null (clear override)
  D-13: state_manager.mutate_state holds fcntl.LOCK_EX across the FULL
        load -> mutate -> save critical section (REVIEWS HIGH #1 fix)

REVIEWS revisions baked in (2026-04-25):
  HIGH #1: handlers use mutate_state, not load_state + save_state
  HIGH #2: close-success returns empty body + HX-Trigger event header
           (NOT a <div> banner — invalid HTML5 inside <tbody>)
  HIGH #3: per-instrument tbody grouping; close/modify forms target
           #position-group-{instrument} with hx-swap="innerHTML"
  MEDIUM #7: ATR lookup uses signals[instrument].last_scalars.atr
             (verified shape via main.py:1225)
  LOW #9:  modify_trade resets pyramid_level on ANY successful modify
           (outside the new_contracts conditional)

Architecture (CLAUDE.md hex-lite + Phase 14 D-14 amends Phase 10 D-15):
  web/routes/ is an adapter hex.
  Allowed: fastapi, starlette, stdlib, state_manager (read+WRITE per D-14),
           sizing_engine (D-02 check_pyramid), system_params (D-12 MAX_PYRAMID_LEVEL).
  Forbidden: signal_engine, data_fetcher, notifier, main.
  Phase 13 D-07: dashboard is allowed but Phase 14 doesn't need it.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary (Plan 14-01 promoted
  sizing_engine + system_params out of FORBIDDEN_FOR_WEB).

  state_manager + sizing_engine + system_params imports are LOCAL inside
  handler bodies / Pydantic validator bodies per Phase 11 C-2.

Auth: Phase 13 AuthMiddleware gates /trades/* automatically (D-01 sole
chokepoint; no per-route boilerplate). Operator's WEB_AUTH_SECRET sent
via X-Trading-Signals-Auth header (HTMX hx-headers attribute).

TRADE-06 sole-writer invariant: NO endpoint here writes to the warnings key.
AST-walk regression test in tests/test_web_trades.py::TestSoleWriterInvariant.

Log prefix: [Web].
'''
import html
import json as _json
import logging
import math
import zoneinfo
from datetime import datetime, date as _date
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

_AWST = zoneinfo.ZoneInfo('Australia/Perth')
_OPERATOR_CLOSE = 'operator_close'  # D-06 literal


def _now_awst() -> datetime:
  return datetime.now(_AWST)


class _OpenConflict(Exception):
  '''Internal sentinel: a conflict detected inside the mutate_state mutator.

  Caught by the handler to return a 409. Body is the conflict message.
  Raised inside `_apply` mutators so the mutate_state finally-blocks
  release the fcntl lock before the handler converts to an HTTP response.
  '''


# =========================================================================
# Pydantic v2 request models (D-04, D-08, D-12)
# =========================================================================


class OpenTradeRequest(BaseModel):
  '''POST /trades/open body — D-04 + D-03 coherence checks.

  Literal enums + Field(gt=0) constraints catch malformed types/values
  BEFORE the handler runs. The 422 response is auto-remapped to 400 by
  the app-level RequestValidationError handler (Pattern 6).

  REVIEW HR-01: extra='forbid' rejects unknown fields with a 400 — without
  this, Pydantic's default 'ignore' would silently drop typos like
  `entry_priec` and apply the (defaulted) wrong value, masking operator errors.
  '''

  model_config = ConfigDict(extra='forbid')

  instrument: Literal['SPI200', 'AUDUSD']
  direction: Literal['LONG', 'SHORT']
  entry_price: float = Field(gt=0)
  contracts: int = Field(ge=1)
  executed_at: _date | None = None
  peak_price: float | None = None
  trough_price: float | None = None
  pyramid_level: int | None = None

  @model_validator(mode='after')
  def _coherence(self):
    # math.isfinite check rejects NaN, +/-inf (D-04 explicit validator)
    for name, val in (
      ('entry_price', self.entry_price),
      ('peak_price', self.peak_price),
      ('trough_price', self.trough_price),
    ):
      if val is not None and not math.isfinite(val):
        raise ValueError(f'{name}: must be finite (not NaN/+/-inf)')
    # D-03 direction-coherence checks
    if self.direction == 'LONG':
      if self.peak_price is not None and self.peak_price < self.entry_price:
        raise ValueError('peak_price: must be >= entry_price for LONG')
      if self.trough_price is not None:
        raise ValueError('trough_price: must be absent or null for LONG')
    else:  # SHORT
      if self.trough_price is not None and self.trough_price > self.entry_price:
        raise ValueError('trough_price: must be <= entry_price for SHORT')
      if self.peak_price is not None:
        raise ValueError('peak_price: must be absent or null for SHORT')
    if self.pyramid_level is not None:
      from system_params import MAX_PYRAMID_LEVEL  # local import (hex)
      if self.pyramid_level < 0 or self.pyramid_level > MAX_PYRAMID_LEVEL:
        raise ValueError(
          f'pyramid_level: must be in [0, {MAX_PYRAMID_LEVEL}]'
        )
    return self


class CloseTradeRequest(BaseModel):
  '''POST /trades/close body — D-08 (executed_at default to today AWST).

  REVIEW HR-01: extra='forbid' rejects unknown fields (typos surface as 400).
  '''

  model_config = ConfigDict(extra='forbid')

  instrument: Literal['SPI200', 'AUDUSD']
  exit_price: float = Field(gt=0)
  executed_at: _date | None = None

  @model_validator(mode='after')
  def _exit_finite(self):
    if not math.isfinite(self.exit_price):
      raise ValueError('exit_price: must be finite (not NaN/+/-inf)')
    return self


class ModifyTradeRequest(BaseModel):
  '''POST /trades/modify body — D-12 absent-vs-null PATCH semantics.

  field absent  -> NOT in model_fields_set -> handler leaves position attr unchanged
  field == None -> IN  model_fields_set    -> handler clears the position attr
  field == val  -> IN  model_fields_set    -> handler sets position attr to val

  Per RESEARCH §Pattern 5; the absent-vs-null distinction lives in
  `model_fields_set`, NOT in the type annotation. Both `field: float | None = None`
  forms produce identical JSON schemas — only `model_fields_set` reveals
  whether the operator sent the key or omitted it.

  REVIEW HR-01: extra='forbid' rejects unknown fields. Critical here:
  a typo like `new_top` (instead of `new_stop`) would otherwise be silently
  dropped, producing a no-op modify that returns 200 — masking the operator
  error and leaving the position with stale stop/contracts.
  '''

  model_config = ConfigDict(extra='forbid')

  instrument: Literal['SPI200', 'AUDUSD']
  new_stop: float | None = None
  new_contracts: int | None = None

  @model_validator(mode='after')
  def _at_least_one(self):
    # D-12: at least one field must be PRESENT (not just non-null).
    # model_fields_set covers BOTH "explicit value" AND "explicit null".
    if not (self.model_fields_set & {'new_stop', 'new_contracts'}):
      raise ValueError(
        'at least one of new_stop, new_contracts must be present'
      )
    return self

  @model_validator(mode='after')
  def _new_contracts_floor(self):
    if 'new_contracts' in self.model_fields_set and self.new_contracts is not None:
      if self.new_contracts < 1:
        raise ValueError('new_contracts: must be >= 1')
    return self

  @model_validator(mode='after')
  def _new_stop_finite(self):
    # ASVS V5 input validation — reject NaN/+/-inf on numeric overrides.
    if 'new_stop' in self.model_fields_set and self.new_stop is not None:
      if not math.isfinite(self.new_stop):
        raise ValueError('new_stop: must be finite (not NaN/+/-inf)')
    return self


# =========================================================================
# 422 -> 400 remap exception handler (D-04; registered by web/app.py)
# =========================================================================


def _format_pydantic_errors(exc: RequestValidationError) -> list[dict]:
  '''Convert Pydantic v2 errors to {field, reason} shape per D-04.

  exc.errors() returns dicts like:
    {'type': 'greater_than', 'loc': ('body', 'entry_price'),
     'msg': 'Input should be greater than 0', 'input': -1, 'ctx': {'gt': 0}}
  We extract the LAST element of 'loc' as the field name (skipping 'body').
  '''
  out = []
  for err in exc.errors():
    loc = err.get('loc', ())
    leaf = next(
      (str(p) for p in reversed(loc) if isinstance(p, (str, int)) and p != 'body'),
      '<root>',
    )
    out.append({'field': leaf, 'reason': err.get('msg', 'invalid')})
  return out


async def _validation_exception_handler(request: Request, exc: RequestValidationError):
  '''Phase 14 D-04: 422 -> 400 remap with field-level error JSON.

  Single global handler (registered in web/app.py::create_app via
  add_exception_handler) covers all routes. REVIEWS LOW #10 regression
  test confirms non-Pydantic-validation errors (e.g., 405 Method Not
  Allowed) are NOT remapped.
  '''
  logger.info(
    '[Web] validation failure on %s: %s',
    request.url.path, _format_pydantic_errors(exc),
  )
  return JSONResponse(
    status_code=400,
    content={'errors': _format_pydantic_errors(exc)},
  )


# =========================================================================
# HTML partial helpers (server-side escape via stdlib html.escape)
# =========================================================================


def _build_position_dict(req, executed_at, atr_entry):
  '''Phase 14 D-03 + D-09: assemble Position dict from request + ATR.

  Pitfall 5: manual_stop=None is set explicitly so sizing_engine.get_trailing_stop
  doesn't KeyError if called transiently before _migrate_v2_to_v3 runs.

  D-03 default-path values (when req.peak_price/trough_price/pyramid_level are None):
    LONG  peak=entry_price,  trough=None
    SHORT peak=None,         trough=entry_price
    pyramid_level=0
  '''
  if req.direction == 'LONG':
    peak = req.peak_price if req.peak_price is not None else req.entry_price
    trough = None
  else:  # SHORT
    peak = None
    trough = req.trough_price if req.trough_price is not None else req.entry_price

  pyramid_level = req.pyramid_level if req.pyramid_level is not None else 0

  return {
    'direction': req.direction,
    'entry_price': req.entry_price,
    'entry_date': executed_at.isoformat() if hasattr(executed_at, 'isoformat') else str(executed_at),
    'n_contracts': req.contracts,
    'pyramid_level': pyramid_level,
    'peak_price': peak,
    'trough_price': trough,
    'atr_entry': atr_entry,
    'manual_stop': None,  # D-09 + Pitfall 5
  }


def _render_position_row_partial(state, instrument, pos) -> str:
  '''Single <tr id="position-row-{instrument}"> stub.

  Plan 14-05 wires up to dashboard._render_positions_table for full
  parity (Actions column, manual badge, etc.). Plan 14-04 ships a
  minimal-but-valid <tr>. Buttons target #position-group-{instrument}
  with hx-swap="innerHTML" per REVIEWS HIGH #3 (per-instrument tbody
  grouping; entire tbody contents replaced on close/modify form open).
  '''
  esc = lambda s: html.escape(str(s), quote=True)
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
  for inst in ('SPI200', 'AUDUSD'):
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
  esc = lambda s: html.escape(str(s), quote=True)
  return (
    f'<tr><td colspan="9">'
    f'Close {esc(pos["direction"])} {esc(instrument)} '
    f'({esc(pos["n_contracts"])} contracts) at exit price '
    f'<input type="number" step="0.01" min="0" name="exit_price" required autofocus />'
    f'<button type="button" class="btn-row" '
    f'hx-get="/trades/cancel-row?instrument={esc(instrument)}" '
    f'hx-target="#position-group-{esc(instrument)}" hx-swap="innerHTML">Cancel</button>'
    f'<button type="button" class="btn-row btn-close" '
    f'hx-post="/trades/close" hx-include="closest tr" '
    f'hx-vals=\'{{"instrument": "{esc(instrument)}"}}\' '
    f'hx-target="#position-group-{esc(instrument)}" hx-swap="innerHTML">Confirm close</button>'
    f'</td></tr>'
  )


def _render_modify_form_partial(state, instrument, pos) -> str:
  '''REVIEWS HIGH #3: SINGLE confirmation <tr> only — same topology as close-form.'''
  esc = lambda s: html.escape(str(s), quote=True)
  return (
    f'<tr><td colspan="9">'
    f'Modify {esc(instrument)}: '
    f'<label>new stop <input type="number" step="0.01" name="new_stop"></label> '
    f'<label>new contracts <input type="number" step="1" min="1" name="new_contracts"></label> '
    f'<button type="button" class="btn-row" '
    f'hx-get="/trades/cancel-row?instrument={esc(instrument)}" '
    f'hx-target="#position-group-{esc(instrument)}" hx-swap="innerHTML">Cancel</button>'
    f'<button type="button" class="btn-row btn-modify" '
    f'hx-post="/trades/modify" hx-include="closest tr" '
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
    headers={'HX-Trigger': 'positions-changed'},
  )


def _render_close_success_partial(instrument, gross_pnl, cost_aud, n_contracts) -> Response:
  '''REVIEWS HIGH #2: close-success returns EMPTY body + HX-Trigger event.

  Why empty body: the response targets a per-instrument <tbody> via
  hx-swap="innerHTML". Returning a <div> banner would land as a direct
  child of <tbody> — invalid HTML5 table structure. Instead: empty body
  + HX-Trigger header tells the dashboard's tbody listener (Plan 14-05)
  to refresh the group via fragment GET. Banner display is handled by
  the listener (it can render the OOB confirmation banner client-side
  from the event detail).
  '''
  net_pnl = gross_pnl - (cost_aud * n_contracts / 2)
  payload = {
    'positions-changed': {
      'instrument': instrument,
      'kind': 'close',
      'net_pnl': net_pnl,
    },
  }
  return HTMLResponse(
    content='',  # empty: tbody listener refreshes via fragment GET
    status_code=200,
    headers={'HX-Trigger': _json.dumps(payload)},
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
    headers={'HX-Trigger': 'positions-changed'},
  )


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
  def open_trade(req: OpenTradeRequest):
    '''Phase 14 TRADE-01 + D-01..D-04 + D-13 (REVIEWS HIGH #1: mutate_state).'''
    # Phase 11 C-2 + Phase 14 D-13: local imports preserve hex boundary
    from state_manager import mutate_state
    from sizing_engine import check_pyramid

    # Captured in closure for response rendering after mutate returns.
    result_holder: dict = {'kind': None, 'extra': None}

    def _apply(state):
      existing = state['positions'].get(req.instrument)
      if existing is not None and existing['direction'] != req.direction:
        # D-01: opposite direction is a hard conflict
        msg = (
          f'instrument {req.instrument} already has an open '
          f'{existing["direction"]} position; close it first via '
          f'POST /trades/close before opening a {req.direction}'
        )
        result_holder['kind'] = 'conflict_opposite'
        result_holder['extra'] = msg
        # Raise to short-circuit out of mutate_state; lock released by
        # mutate_state's finally.
        raise _OpenConflict(msg)

      if existing is not None and existing['direction'] == req.direction:
        # D-02 + REVIEWS MEDIUM #7: ATR lookup is nested under last_scalars
        # (verified shape via main.py:1225 — daily loop writes
        # signals[state_key] = {signal: ..., last_scalars: scalars,
        # last_close: ..., ...}; scalars.atr lives inside last_scalars).
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
      state['positions'][req.instrument] = _build_position_dict(req, executed_at, atr_entry)
      result_holder['kind'] = 'fresh_open'

    try:
      state = mutate_state(_apply)
    except _OpenConflict as exc:
      logger.warning('[Web] /trades/open conflict: %s', exc)
      return Response(
        content=str(exc), status_code=409,
        media_type='text/plain; charset=utf-8',
      )

    logger.info(
      '[Web] /trades/open %s: instrument=%s direction=%s entry=%s contracts=%d',
      result_holder['kind'], req.instrument, req.direction,
      req.entry_price, req.contracts,
    )
    return _render_open_success_partial(
      state, req.instrument, req.direction, req.entry_price, req.contracts,
    )

  @app.post('/trades/close')
  def close_trade(req: CloseTradeRequest):
    '''Phase 14 TRADE-03 + D-05..D-08 + D-13 (REVIEWS HIGH #1: mutate_state).'''
    from state_manager import mutate_state, record_trade

    capture: dict = {'gross_pnl': None, 'cost_aud': None, 'n_contracts': None}

    def _apply(state):
      pos = state['positions'].get(req.instrument)
      if pos is None:
        msg = f'no open position for instrument {req.instrument}'
        raise _OpenConflict(msg)
      # D-07: read multiplier and cost_aud from _resolved_contracts
      # (load_state rematerializes per Phase 8 D-14)
      resolved = state['_resolved_contracts'][req.instrument]
      multiplier = resolved['multiplier']
      cost_aud = resolved['cost_aud']

      # D-05 ANTI-PITFALL — DO NOT call sizing_engine's unrealised-pnl helper HERE.
      # record_trade D-14 deducts the closing-half cost. The unrealised-pnl helper
      # already deducts the opening-half cost. Passing realised_pnl as gross_pnl
      # would double-count the closing cost. See state_manager.py:499-506,
      # Phase 4 D-15/D-19 anti-pitfall.
      if pos['direction'] == 'LONG':
        gross_pnl = (req.exit_price - pos['entry_price']) * pos['n_contracts'] * multiplier
      else:  # SHORT
        gross_pnl = (pos['entry_price'] - req.exit_price) * pos['n_contracts'] * multiplier
      capture['gross_pnl'] = gross_pnl
      capture['cost_aud'] = cost_aud
      capture['n_contracts'] = pos['n_contracts']

      exit_date = (req.executed_at or _now_awst().date()).isoformat()
      trade = {
        'instrument': req.instrument,                  # locked-key shape per Phase 3 D-15
        'direction': pos['direction'],
        'n_contracts': pos['n_contracts'],
        'entry_date': pos['entry_date'],
        'exit_date': exit_date,
        'exit_reason': _OPERATOR_CLOSE,                # D-06 literal
        'entry_price': pos['entry_price'],
        'exit_price': req.exit_price,
        'gross_pnl': gross_pnl,                        # D-05 inline raw price-delta
        'multiplier': multiplier,                      # D-07
        'cost_aud': cost_aud,                          # D-07
      }
      # record_trade mutates state in place (Phase 3 D-13/D-20)
      record_trade(state, trade)

    try:
      mutate_state(_apply)
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
  def modify_trade(req: ModifyTradeRequest):
    '''Phase 14 TRADE-04 + D-09..D-13 + REVIEWS LOW #9 (pyramid resets on ANY modify).'''
    from state_manager import mutate_state

    def _apply(state):
      pos = state['positions'].get(req.instrument)
      if pos is None:
        msg = f'no open position for instrument {req.instrument}'
        raise _OpenConflict(msg)
      if 'new_stop' in req.model_fields_set:
        # PRESENT: explicit set or null (D-12)
        pos['manual_stop'] = req.new_stop  # may be None (clear-override)
      if 'new_contracts' in req.model_fields_set and req.new_contracts is not None:
        pos['n_contracts'] = req.new_contracts
      # REVIEWS LOW #9 / D-10: pyramid_level resets on ANY successful modify
      # (OUTSIDE the new_contracts conditional — fires on new_stop-only modifies too).
      pos['pyramid_level'] = 0

    try:
      state = mutate_state(_apply)
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
    return _render_modify_success_partial(state, req.instrument)

  @app.get('/trades/close-form')
  def close_form(instrument: str):
    '''UI-SPEC §Decision 5: 2-stage destructive close confirmation panel.

    Returns a SINGLE <tr> (the confirmation panel) per REVIEWS HIGH #3.
    The caller's hx-target=#position-group-{instrument} + hx-swap=innerHTML
    means the entire tbody is replaced by this confirmation row while the
    operator decides. Cancel restores the canonical position row.
    '''
    from state_manager import load_state
    state = load_state()
    pos = state['positions'].get(instrument)
    if pos is None:
      return Response(
        content=f'no open position for {instrument}', status_code=404,
        media_type='text/plain; charset=utf-8',
      )
    return HTMLResponse(content=_render_close_form_partial(state, instrument, pos))

  @app.get('/trades/modify-form')
  def modify_form(instrument: str):
    '''UI-SPEC §Decision 2: inline modify form panel (single <tr>).'''
    from state_manager import load_state
    state = load_state()
    pos = state['positions'].get(instrument)
    if pos is None:
      return Response(
        content=f'no open position for {instrument}', status_code=404,
        media_type='text/plain; charset=utf-8',
      )
    return HTMLResponse(content=_render_modify_form_partial(state, instrument, pos))

  @app.get('/trades/cancel-row')
  def cancel_row(instrument: str):
    '''Restore a position's original row inside #position-group-{instrument}.

    Returns ONE <tr> (the canonical position row). HX swap is innerHTML on
    the parent tbody so the tbody contains exactly this one row after cancel.
    '''
    from state_manager import load_state
    state = load_state()
    pos = state['positions'].get(instrument)
    if pos is None:
      return Response(
        content=f'no open position for {instrument}', status_code=404,
        media_type='text/plain; charset=utf-8',
      )
    return HTMLResponse(content=_render_position_row_partial(state, instrument, pos))
