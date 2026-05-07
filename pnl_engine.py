'''Pnl Engine — pure-math paper-trade P&L (Phase 19 D-11).

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY. Imports math + decimal
+ typing only. Multiplier and round-trip cost are explicit float args (per Phase 2
D-17 anti-coupling rule; Phase 19 planner D-19). No system_params imports — caller-
side adapters supply the constants.

Phase 27 #1 (review-fix agreed-7): money math returns `Decimal` quantized to AUD
cents using `ROUND_HALF_UP`. Inputs may be int/float/str — they are coerced via
`Decimal(str(x))` at the boundary to avoid float-binary precision noise. Indicator
math elsewhere (signal_engine / sizing_engine indicator paths) stays float64; the
Decimal slice is ONLY at the money-math boundary.

NaN propagation: a NaN float input flows through `Decimal(str(nan))` to
`Decimal('NaN')`, which propagates through arithmetic the same way float NaN
does. Callers can detect via `decimal_value.is_nan()` or by attempting
`float(decimal_value)` and checking `math.isnan(...)`.

Forbidden imports (enforced by tests/test_signal_engine.py::TestDeterminism):
  state_manager, notifier, dashboard, main, requests, datetime, os, numpy, pandas,
  yfinance, schedule, dotenv.

Functions:
  compute_unrealised_pnl(side, entry_price, last_close, contracts, multiplier,
                         entry_cost_aud) -> Decimal (AUD-quantized HALF_UP)
  compute_realised_pnl(side, entry_price, exit_price, contracts, multiplier,
                       round_trip_cost_aud) -> Decimal (AUD-quantized HALF_UP)
'''
import math  # noqa: F401 — used for NaN propagation detection by callers
from decimal import ROUND_HALF_UP, Decimal


# Local mirror of system_params.AUD_QUANTIZE / AUD_ROUND. We deliberately
# avoid `from system_params import …` here because pnl_engine is on the
# stdlib-only hex-boundary tier (test_pnl_engine_module_imports_only_math_
# and_typing). The values must stay in lockstep with system_params; the
# project-wide regression `test_aud_quantize_constant_is_two_dp` pins them.
_AUD_QUANTIZE: Decimal = Decimal('0.01')
_AUD_ROUND = ROUND_HALF_UP


def _to_dec(x) -> Decimal:
  '''Coerce any numeric-shaped input to Decimal via str() to avoid
  float-binary precision noise leaking into money math.
  '''
  if isinstance(x, Decimal):
    return x
  return Decimal(str(x))


def compute_unrealised_pnl(
  side: str,
  entry_price,
  last_close,
  contracts,
  multiplier,
  entry_cost_aud,
) -> Decimal:
  '''D-11 unrealised. Returns Decimal AUD-quantized (HALF_UP).

  LONG:  (last_close - entry_price) * contracts * multiplier - entry_cost_aud
  SHORT: (entry_price - last_close) * contracts * multiplier - entry_cost_aud

  All numeric inputs are coerced via Decimal(str(x)) at the boundary;
  arithmetic stays in Decimal; result is quantized to AUD cents.

  NaN last_close propagates: Decimal('NaN') flows through arithmetic the
  same way float NaN does. Callers detect via `result.is_nan()`.
  '''
  ep = _to_dec(entry_price)
  lc = _to_dec(last_close)
  c  = _to_dec(contracts)
  m  = _to_dec(multiplier)
  ec = _to_dec(entry_cost_aud)
  if side == 'LONG':
    gross = (lc - ep) * c * m
  else:  # SHORT
    gross = (ep - lc) * c * m
  result = gross - ec
  # NaN cannot be quantized — propagate as-is so callers can detect.
  if result.is_nan():
    return result
  return result.quantize(_AUD_QUANTIZE, rounding=_AUD_ROUND)


def compute_realised_pnl(
  side: str,
  entry_price,
  exit_price,
  contracts,
  multiplier,
  round_trip_cost_aud,
) -> Decimal:
  '''D-11 realised. Returns Decimal AUD-quantized (HALF_UP).

  Full round-trip cost deducted at close (both halves applied here, per
  Phase 19 D-11 — diverges from sizing_engine which splits across
  record_trade D-14).
  '''
  ep = _to_dec(entry_price)
  xp = _to_dec(exit_price)
  c  = _to_dec(contracts)
  m  = _to_dec(multiplier)
  rt = _to_dec(round_trip_cost_aud)
  if side == 'LONG':
    gross = (xp - ep) * c * m
  else:  # SHORT
    gross = (ep - xp) * c * m
  result = gross - rt
  if result.is_nan():
    return result
  return result.quantize(_AUD_QUANTIZE, rounding=_AUD_ROUND)
