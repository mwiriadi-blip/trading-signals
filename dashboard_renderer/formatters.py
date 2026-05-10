'''Dashboard formatting helpers extracted from dashboard.py.'''

import html
import math
from datetime import date, datetime, timedelta

import pytz



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
  # D-19 #5: use CSS classes instead of inline style="color:..."
  # .pnl-positive / .pnl-negative / .pnl-zero defined in _INLINE_CSS (Plan 25-09)
  if value > 0:
    css_class = 'pnl-positive'
    body = f'+{fmt_currency(value)}'
  elif value < 0:
    css_class = 'pnl-negative'
    body = fmt_currency(value)
  else:
    css_class = 'pnl-zero'
    body = '$0.00'
  return f'<span class="{css_class}">{html.escape(body, quote=True)}</span>'


def fmt_last_updated(now: datetime) -> str:
  if now.tzinfo is None:
    raise ValueError(
      'fmt_last_updated requires a timezone-aware datetime; '
      f'got naive datetime={now!r}'
    )
  aest = now.astimezone(pytz.timezone('Australia/Sydney'))
  return aest.strftime('%Y-%m-%d %H:%M AEST')


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


# ---------------------------------------------------------------------------
# Phase 25 D-06/D-07/D-08 + OR-01/OR-02: System Status strip helpers
# ---------------------------------------------------------------------------

def _compute_next_awst_0800(now_awst: datetime) -> datetime:
  '''Return the next 08:00 AEST datetime on a Mon-Fri weekday.

  OR-02 display rule: if >24h away, format as `Mon 08:00 AEST · in 2d 16h`;
  if <24h, format as `in Nh Mm`; if <1h, format as `in NNm`.
  '''
  # Strip to 08:00 AEST on the same calendar day as now_awst.
  today_0800 = now_awst.replace(hour=8, minute=0, second=0, microsecond=0)
  # If we are before 08:00 today AND today is a weekday, the target is today.
  if now_awst < today_0800 and now_awst.weekday() < 5:
    target = today_0800
  else:
    # Move to next calendar day and keep advancing until we land on a weekday.
    target = today_0800 + timedelta(days=1)
  while target.weekday() >= 5:  # Sat=5, Sun=6
    target += timedelta(days=1)
  return target


def _format_countdown_text(now_awst: datetime, target_awst: datetime) -> str:
  '''OR-02 countdown format.

  >24h : `Mon 08:00 AWST · in 2d 16h`
  <24h  : `in Nh Mm`
  <1h   : `in NNm`
  '''
  delta = target_awst - now_awst
  total_sec = max(0.0, delta.total_seconds())
  total_min = int(total_sec // 60)
  days = total_min // (24 * 60)
  hours = (total_min % (24 * 60)) // 60
  mins = total_min % 60
  day_name = target_awst.strftime('%a')  # Mon, Tue, ...
  if total_sec >= 24 * 3600:
    return f'{day_name} 08:00 AEST · in {days}d {hours}h'
  if total_sec >= 3600:
    return f'in {hours}h {mins}m'
  return f'in {mins}m'


def _derive_status_dot_class(state: dict, now_awst: datetime) -> tuple:
  '''OR-01 status derivation. Returns (css_class, status_text).

  css_class is one of:
    status-dot--success   (green — today's run, no recent warnings)
    status-dot--stale     (amber — one missed cycle or today+warnings)
    status-dot--failure   (red  — multiple missed cycles)
    status-dot--never     (grey — never run)
  status_text is one of: 'OK', 'Stale', 'Failed', 'Never run'.
  '''
  last_run = state.get('last_run')
  warnings = state.get('warnings', []) or []
  today = now_awst.date()
  weekday = now_awst.weekday()  # 0=Mon .. 6=Sun

  if last_run is None:
    return ('status-dot--never', 'Never run')

  try:
    last_run_date = date.fromisoformat(last_run)
  except (TypeError, ValueError):
    return ('status-dot--never', 'Never run')

  days_diff = (today - last_run_date).days

  # Recent warnings: entries whose 'date' key is >= last_run date string
  recent_warnings = [
    w for w in warnings
    if isinstance(w, dict) and w.get('date', '') >= last_run
  ]

  # Weekend handling: Sat/Sun inherit Friday's status (no run expected Sat/Sun).
  if weekday >= 5:  # Sat=5, Sun=6
    # Saturday: Friday was 1 day ago; Sunday: Friday was 2 days ago.
    expected_days = weekday - 4  # Sat → 1, Sun → 2
    if days_diff <= expected_days:
      if recent_warnings:
        return ('status-dot--stale', 'Stale')
      return ('status-dot--success', 'OK')
    return ('status-dot--failure', 'Failed')

  # Weekday cases
  today_iso = today.isoformat()
  if last_run == today_iso:
    if recent_warnings:
      return ('status-dot--stale', 'Stale')
    return ('status-dot--success', 'OK')

  # Yesterday's run + today is a weekday → one missed cycle, amber
  if days_diff == 1:
    return ('status-dot--stale', 'Stale')

  # Multiple missed weekday cycles → red
  return ('status-dot--failure', 'Failed')
