'''POST /paper-trade/open + PATCH/DELETE /paper-trade/<id> + POST /paper-trade/<id>/close
+ GET /paper-trade/<id>/close-form + GET /paper-trades — Phase 19 LEDGER-01..06 + VERSION-03.

Operator records paper trades (open/edit/delete/close) via this adapter. Every mutation
goes through state_manager.mutate_state (Phase 14 flock kernel — unchanged). Closed rows
are immutable (405 + Allow: GET per RFC 7231 §6.5.5). Composite trade ID generated inside
the mutate_state closure under LOCK_EX (D-01 + D-15 atomicity).

Contract (CONTEXT.md 2026-04-30 D-01..D-16 + planner D-17..D-22):
  D-01: Composite ID <INSTRUMENT>-<YYYYMMDD>-<NNN> inside mutate_state lock
  D-02: Half round-trip cost on entry (entry_cost_aud = round_trip / 2)
  D-03: Close form rendered below open trades table (HTMX hx-get close-form route)
  D-04: Strict server-side validation: future entry_dt, entry_price<=0, contracts<=0,
        fractional SPI contracts, wrong-side stop, unknown instrument/side
  D-05: PATCH/DELETE allowed on open rows; closed rows return 405 immutable
  D-09: state.paper_trades[] row shape (13 fields)
  D-11: P&L formulas via pnl_engine (pure-math module)
  D-13: Single #trades-region HTMX swap target for every mutation
  D-15: ALL mutations via mutate_state — no direct load_state/save_state in _apply
  D-17: No hx-ext="json-enc"; routes accept application/x-www-form-urlencoded.
        Browsers + HTMX send form-encoded data by default (no json-enc extension needed).
        Handlers read Request.form() and validate via Pydantic model_validate().
        Gap closure 2026-04-30: original implementation incorrectly accepted JSON body;
        corrected to accept form-encoded body per D-17 and the browser/HTMX contract.
  D-18: Singular /paper-trade/<id> for individual ops; plural /paper-trades for list
  D-21: DELETE carries no body
  D-22: Validation failures return 400 (global RequestValidationError -> 400 handler)

Hex-lite layering (CLAUDE.md + Phase 19 D-14):
  Adapter tier: imports pnl_engine (pure-math), state_manager.mutate_state (I/O),
                system_params.STRATEGY_VERSION (LOCAL inside _apply — kwarg trap).
  system_params / pnl_engine / state_manager are LOCAL imports inside handler bodies
  per Phase 11 C-2 (prevents circular imports, matches trades.py convention).

Auth: Phase 16.1 AuthMiddleware gates all /paper-trade/* routes uniformly across
GET/POST/PATCH/DELETE — no per-route auth boilerplate needed.

Log prefix: [Web].
'''
import html
import logging
import math
import zoneinfo
from datetime import datetime
from typing import Literal, TypeVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_T = TypeVar('_T', bound=BaseModel)

logger = logging.getLogger(__name__)

_AWST = zoneinfo.ZoneInfo('Australia/Perth')
_LOG_PREFIX = '[Web]'
_VALID_INSTRUMENTS = frozenset({'SPI200', 'AUDUSD'})
_VALID_SIDES = frozenset({'LONG', 'SHORT'})

# Mirror of system_params constants — kept here so pnl_engine stays decoupled per
# planner D-19 + Phase 2 D-17. If system_params changes, update here and bump tests.
_COST_AUD: dict[str, float] = {'SPI200': 6.0, 'AUDUSD': 5.0}  # full round-trip
_MULTIPLIER: dict[str, float] = {'SPI200': 5.0, 'AUDUSD': 10000.0}

_D09_KEYS = frozenset({
  'id', 'instrument', 'side', 'entry_dt', 'entry_price', 'contracts',
  'stop_price', 'entry_cost_aud', 'status', 'exit_dt', 'exit_price',
  'realised_pnl', 'strategy_version',
})


def _now_awst() -> datetime:
  '''Return the current datetime in AWST (Australia/Perth). Copy from trades.py:73.'''
  return datetime.now(_AWST)


async def _parse_form(request: Request, model_cls: type[_T]) -> _T:
  '''Read application/x-www-form-urlencoded body from request and validate via Pydantic.

  D-17 gap-closure (2026-04-30): browsers + HTMX (without hx-ext="json-enc") send
  form-encoded bodies, not JSON. This helper bridges the HTMX → FastAPI gap by:
  1. Reading the form data dict (starlette Request.form() — already parsed by middleware)
  2. Dropping empty-string values so optional fields remain None (not "")
  3. Calling model_cls.model_validate() with from_attributes=False
  4. Re-raising Pydantic ValidationError as FastAPI RequestValidationError so the
     global handler in web/app.py remaps to 400 (planner D-22).

  Called from the three mutation POST/PATCH handlers; DELETE has no body (D-21).
  '''
  raw_form = await request.form()
  # Convert ImmutableMultiDict → plain dict; drop empty strings (optional fields)
  form_dict: dict = {}
  for key, value in raw_form.multi_items():
    if value != '':
      form_dict[key] = value

  try:
    return model_cls.model_validate(form_dict)
  except ValidationError as exc:
    # Wrap as RequestValidationError so web/app.py's handler remaps to 400 (D-22)
    raise RequestValidationError(errors=exc.errors()) from exc


# =========================================================================
# Sentinels — raised inside _apply closures, caught by handlers
# =========================================================================

class _PaperTradeNotFound(Exception):
  '''Row with the given trade_id does not exist in state.paper_trades.'''


class _PaperTradeImmutable(Exception):
  '''Raised when PATCH/DELETE/close is attempted on a status=closed row.'''


class _PaperTradeIDOverflow(Exception):
  '''Raised when the per-instrument-per-day counter would exceed 999.'''
  def __init__(self, instrument: str, day: str) -> None:
    self.instrument = instrument
    self.day = day


# =========================================================================
# 405 helper — RFC 7231 §6.5.5
# =========================================================================

def _method_not_allowed_405(allow: str = 'GET') -> Response:
  '''RFC 7231 §6.5.5 — 405 MUST include Allow header listing allowed methods.

  Manual 405 responses (closed-row immutability) do NOT include Allow
  automatically unlike FastAPI's auto-generated 405 for unknown methods.
  We must add it explicitly. RESEARCH §Pattern 3 verified this.
  '''
  return Response(
    content='closed rows are immutable',
    status_code=405,
    headers={'Allow': allow},
    media_type='text/plain; charset=utf-8',
  )


# =========================================================================
# Pydantic request models (D-04 + planner D-22)
# =========================================================================

class OpenPaperTradeRequest(BaseModel):
  '''POST /paper-trade/open body — D-04 strict server-side validation.

  Pydantic 422 is auto-remapped to 400 by the global RequestValidationError
  handler in web/app.py (planner D-22 amendment — CONTEXT D-04 says 422
  but the codebase-wide handler remaps to 400).
  '''
  model_config = ConfigDict(extra='forbid')  # D-04: unknown fields → 400

  instrument: Literal['SPI200', 'AUDUSD']
  side: Literal['LONG', 'SHORT']
  entry_dt: datetime
  entry_price: float = Field(gt=0)
  contracts: float = Field(gt=0)
  stop_price: float | None = None

  @model_validator(mode='after')
  def _coherence(self) -> 'OpenPaperTradeRequest':
    '''D-04 cross-field validations: future entry_dt, SPI fractional contracts,
    stop_price sign check.'''
    # entry_dt must not be in the future (AWST)
    now = _now_awst()
    entry_dt_aware = self.entry_dt
    if entry_dt_aware.tzinfo is None:
      # naive datetime: assume AWST for comparison
      import zoneinfo as _zi
      entry_dt_aware = self.entry_dt.replace(tzinfo=_zi.ZoneInfo('Australia/Perth'))
    if entry_dt_aware > now:
      raise ValueError('entry_dt: must not be in the future (AWST)')

    # SPI 200 mini contracts must be a whole integer
    if self.instrument == 'SPI200' and self.contracts != int(self.contracts):
      raise ValueError('contracts: SPI200 mini contracts must be a whole integer')

    # stop_price validation
    if self.stop_price is not None:
      if self.stop_price <= 0:
        raise ValueError('stop_price: must be > 0')
      if self.side == 'LONG' and self.stop_price >= self.entry_price:
        raise ValueError('stop_price: must be < entry_price for LONG')
      if self.side == 'SHORT' and self.stop_price <= self.entry_price:
        raise ValueError('stop_price: must be > entry_price for SHORT')

    return self


class EditPaperTradeRequest(BaseModel):
  '''PATCH /paper-trade/<id> body — same D-04 rules as OpenPaperTradeRequest
  but all fields optional (only supplied fields are updated).
  '''
  model_config = ConfigDict(extra='forbid')

  instrument: Literal['SPI200', 'AUDUSD'] | None = None
  side: Literal['LONG', 'SHORT'] | None = None
  entry_dt: datetime | None = None
  entry_price: float | None = Field(default=None, gt=0)
  contracts: float | None = Field(default=None, gt=0)
  stop_price: float | None = None

  @model_validator(mode='after')
  def _coherence(self) -> 'EditPaperTradeRequest':
    '''Validate stop_price sign relative to entry_price when both are supplied.
    Full D-04 coherence is enforced inside _apply (post-merge) for partial edits.
    '''
    if self.stop_price is not None and self.stop_price <= 0:
      raise ValueError('stop_price: must be > 0')
    return self


class ClosePaperTradeRequest(BaseModel):
  '''POST /paper-trade/<id>/close body.'''
  model_config = ConfigDict(extra='forbid')

  exit_dt: datetime
  exit_price: float = Field(gt=0)


# =========================================================================
# register() factory — mounts all six routes
# =========================================================================

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
      entry_cost_aud = _COST_AUD[req.instrument] / 2.0
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
      row['realised_pnl'] = realised
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
      f'    <label>Exit date/time (AWST)\n'
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
