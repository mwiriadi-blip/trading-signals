'''Pydantic request models + sentinel exceptions for the paper-trades route.

Moved verbatim from web/routes/paper_trades.py (Phase 30 D-08 pre-emptive split).
Zero semantic changes — all validation rules, field constraints, error messages, and
exception classes are preserved exactly.

Classes exported:
  _now_awst, _PaperTradeNotFound, _PaperTradeImmutable, _PaperTradeIDOverflow,
  OpenPaperTradeRequest, EditPaperTradeRequest, ClosePaperTradeRequest
'''
import zoneinfo
from datetime import datetime
from typing import Literal, TypeVar

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_T = TypeVar('_T', bound=BaseModel)

_AEST = zoneinfo.ZoneInfo('Australia/Sydney')


def _now_awst() -> datetime:
  '''Return the current datetime in AEST (Australia/Sydney). Label migrated to AEST in tz fix.'''
  return datetime.now(_AEST)


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
    # entry_dt must not be in the future (AEST)
    now = _now_awst()
    entry_dt_aware = self.entry_dt
    if entry_dt_aware.tzinfo is None:
      # naive datetime: assume AEST for comparison (matches form label)
      import zoneinfo as _zi
      entry_dt_aware = self.entry_dt.replace(tzinfo=_zi.ZoneInfo('Australia/Sydney'))
    if entry_dt_aware > now:
      raise ValueError('entry_dt: must not be in the future (AEST)')

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
