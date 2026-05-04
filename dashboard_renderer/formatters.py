'''Dashboard formatting helpers extracted from dashboard.py.'''

import html
import math
from datetime import datetime

import pytz

from system_params import _COLOR_LONG, _COLOR_SHORT, _COLOR_TEXT_MUTED


def fmt_em_dash() -> str:
  return '—'


def fmt_currency(value: float) -> str:
  if value < 0:
    return f'-${-value:,.2f}'
  return f'${value:,.2f}'


def fmt_percent_signed(fraction: float) -> str:
  return f'{fraction * 100:+.1f}%'


def fmt_percent_unsigned(fraction: float) -> str:
  return f'{fraction * 100:.1f}%'


def fmt_pnl_with_colour(value: float) -> str:
  if value > 0:
    colour = _COLOR_LONG
    body = f'+{fmt_currency(value)}'
  elif value < 0:
    colour = _COLOR_SHORT
    body = fmt_currency(value)
  else:
    colour = _COLOR_TEXT_MUTED
    body = '$0.00'
  return (
    f'<span style="color: {html.escape(colour, quote=True)}">'
    f'{html.escape(body, quote=True)}</span>'
  )


def fmt_last_updated(now: datetime) -> str:
  if now.tzinfo is None:
    raise ValueError(
      'fmt_last_updated requires a timezone-aware datetime; '
      f'got naive datetime={now!r}'
    )
  awst = now.astimezone(pytz.timezone('Australia/Perth'))
  return awst.strftime('%Y-%m-%d %H:%M AWST')


def format_indicator_value(
  value: float,
  seed_required: int,
  bars_available: int,
) -> str:
  if math.isnan(value):
    if bars_available < seed_required:
      return f'n/a (need {seed_required} bars, have {bars_available})'
    return 'n/a (flat price)'
  return f'{value:.6f}'
