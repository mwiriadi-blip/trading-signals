'''Pydantic request models + helpers for web/routes/trades package.

Extracted from web/routes/trades.py (Phase 30 D-04 boundary split).
ZERO behaviour changes — all logic verbatim from the original single file.

Contains:
  _AWST, _OPERATOR_CLOSE, _now_awst
  _OpenConflict
  OpenTradeRequest, CloseTradeRequest, ModifyTradeRequest
  _format_pydantic_errors
  _build_position_dict
'''
import math
import zoneinfo
from datetime import date as _date
from datetime import datetime
from typing import Literal

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

_OPTIONAL_OPEN = frozenset({'executed_at', 'peak_price', 'trough_price', 'pyramid_level'})

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

  instrument: str = Field(pattern=r'^[A-Z0-9_]{2,20}$')
  direction: Literal['LONG', 'SHORT']
  entry_price: float = Field(gt=0)
  contracts: int = Field(ge=1)
  executed_at: _date | None = None
  peak_price: float | None = None
  trough_price: float | None = None
  pyramid_level: int | None = None

  @model_validator(mode='before')
  @classmethod
  def _coerce_empty_str(cls, data):
    # json-enc submits unfilled optional inputs as "" — coerce to None so
    # Pydantic's _date / float / int parsers don't reject them.
    if isinstance(data, dict):
      for key in _OPTIONAL_OPEN:
        if data.get(key) == '':
          data[key] = None
    return data

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

  instrument: str = Field(pattern=r'^[A-Z0-9_]{2,20}$')
  exit_price: float = Field(gt=0)
  executed_at: _date | None = None

  @model_validator(mode='before')
  @classmethod
  def _coerce_empty_str(cls, data):
    if isinstance(data, dict) and data.get('executed_at') == '':
      data['executed_at'] = None
    return data

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

  instrument: str = Field(pattern=r'^[A-Z0-9_]{2,20}$')
  new_stop: float | None = None
  new_contracts: int | None = None

  @model_validator(mode='before')
  @classmethod
  def _strip_empty_str(cls, data):
    # json-enc submits unfilled optional inputs as "". For modify, empty means
    # "not sent" — strip so they're absent from model_fields_set (absent-vs-null
    # semantics: absent=no-op, None=clear, value=set).
    if isinstance(data, dict):
      for key in ('new_stop', 'new_contracts'):
        if data.get(key) == '':
          del data[key]
    return data

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
      (str(p) for p in reversed(loc) if isinstance(p, str | int) and p != 'body'),
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
  import logging
  logger = logging.getLogger(__name__)
  logger.info(
    '[Web] validation failure on %s: %s',
    request.url.path, _format_pydantic_errors(exc),
  )
  return JSONResponse(
    status_code=400,
    content={'errors': _format_pydantic_errors(exc)},
  )


# =========================================================================
# Position dict builder
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
    'entry_date': (
      executed_at.isoformat() if hasattr(executed_at, 'isoformat') else str(executed_at)
    ),
    'n_contracts': req.contracts,
    'pyramid_level': pyramid_level,
    'peak_price': peak,
    'trough_price': trough,
    'atr_entry': atr_entry,
    'manual_stop': None,  # D-09 + Pitfall 5
  }
