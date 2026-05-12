'''Dashboard formatting helpers extracted from dashboard.py.

Phase 32 Plan 01: absorbs unique non-delegating symbols from
dashboard_legacy/render_helpers.py — market registry, resolve helpers,
constants, and _TraceOpenPlaceholderMap. Underscore-prefixed names are
CANONICAL per 32-01-PLAN.md §CANONICAL NAMING LOCK.
'''

import html
import logging
import math
import re as _re
from datetime import date, datetime, timedelta

import pytz

from system_params import (
  _COLOR_FLAT,
  _COLOR_LONG,
  _COLOR_SHORT,
  DEFAULT_MARKETS,
  DEFAULT_STRATEGY_SETTINGS,
  FALLBACK_CONTRACT_SPECS,
)

logger = logging.getLogger(__name__)


# =========================================================================
# Display-name + contract-spec dicts (ported from render_helpers.py)
# =========================================================================

_INSTRUMENT_DISPLAY_NAMES = {
  'SPI200': 'SPI 200',
  'AUDUSD': 'AUD / USD',
}

# Phase 8 IN-05: _CONTRACT_SPECS is a re-export of system_params.FALLBACK_CONTRACT_SPECS.
_CONTRACT_SPECS = FALLBACK_CONTRACT_SPECS


def _market_registry(state: dict | None = None) -> dict:
  markets = (state or {}).get('markets')
  if not isinstance(markets, dict):
    return {key: dict(value) for key, value in DEFAULT_MARKETS.items()}
  merged = {key: dict(value) for key, value in DEFAULT_MARKETS.items()}
  for key, value in markets.items():
    if isinstance(value, dict):
      merged[key] = {**merged.get(key, {}), **value}
  return dict(sorted(
    merged.items(),
    key=lambda item: (item[1].get('sort_order', 999), item[0]),
  ))


def _enabled_market_registry(state: dict | None = None) -> dict:
  return {
    key: market for key, market in _market_registry(state).items()
    if market.get('enabled', True)
  }


def _display_names(state: dict | None = None) -> dict[str, str]:
  return {
    key: str(market.get('display_name') or key)
    for key, market in _enabled_market_registry(state).items()
  }


def _strategy_settings_for(state: dict, market_id: str) -> dict:
  settings = state.get('strategy_settings', {}).get(market_id, {})
  if not isinstance(settings, dict):
    settings = {}
  return {**DEFAULT_STRATEGY_SETTINGS, **settings}


# Phase 22 D-06: dashboard fallback when no signal row carries strategy_version.
_DEFAULT_STRATEGY_VERSION = 'v1.0.0'


def _resolve_strategy_version(state: dict) -> str:
  '''Phase 22: extract the active strategy version from state.signals.

  Reads strategy_version off each dict-shaped signal row, picks the
  lexicographic max (str) when instruments disagree (transient migration
  window), defaults to 'v1.0.0' if no row carries the field. Emits a
  [State] WARN log for each dict-shaped row that lacks the field.
  '''
  signals = state.get('signals', {})
  found: list[str] = []
  for sig in signals.values():
    if isinstance(sig, dict):
      if 'strategy_version' in sig:
        found.append(sig['strategy_version'])
      else:
        logger.warning(
          '[State] WARN signal row missing strategy_version field — '
          'defaulting to v1.0.0',
        )
  if not found:
    return _DEFAULT_STRATEGY_VERSION
  return max(found, key=str)


# D-04: instrument keys whose <details open> we honour at the route-layer
# cookie read. Mirrors state.signals keys (SPI200, AUDUSD).
_VALID_TRACE_INSTRUMENT_KEYS: frozenset = frozenset({'SPI200', 'AUDUSD'})


def _resolve_trace_open_keys(
  state: dict,
  trace_open_keys: list,
) -> set:
  '''Phase 17 D-04: which per-instrument <details> render with the `open`
  attribute. Applies a defensive allowlist intersection against
  _VALID_TRACE_INSTRUMENT_KEYS AND against the keys actually present in
  state.signals.
  '''
  present_keys = set(state.get('signals', {}).keys())
  return {
    k for k in trace_open_keys
    if k in _VALID_TRACE_INSTRUMENT_KEYS and k in present_keys
  }


# Phase 29 Plan 12: defaultdict-style callable so ALL market IDs emit
# the correct {{TRACE_OPEN_<KEY>}} placeholder.
class _TraceOpenPlaceholderMap:
  '''Returns {{TRACE_OPEN_<KEY>}} for any valid instrument key; '' for invalid.

  Mimics dict .get(key, default) so existing call sites are unchanged.
  Invalid key = does not satisfy ^[A-Z0-9_]{2,20}$ (matches _MARKET_ID_RE).
  '''
  _RE = _re.compile(r'^[A-Z0-9_]{2,20}$')

  def get(self, key: str, default: str = '') -> str:  # noqa: ANN001
    if not self._RE.fullmatch(key or ''):
      return default
    return f'{{{{TRACE_OPEN_{key}}}}}'


_TRACE_OPEN_PLACEHOLDER = _TraceOpenPlaceholderMap()

# Signal display dicts
_SIGNAL_LABEL = {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}
_SIGNAL_COLOUR = {1: _COLOR_LONG, -1: _COLOR_SHORT, 0: _COLOR_FLAT}

# Exit-reason display mapping (UI-SPEC §Closed trades table §Reason column).
_EXIT_REASON_DISPLAY = {
  'flat_signal': 'Signal flat',
  'signal_reversal': 'Reversal',
  'stop_hit': 'Stop hit',
  'adx_exit': 'ADX drop',
}

# Phase 17 D-13: trace panel constants
_TRACE_FORMULAS: dict[str, str] = {
  'tr': 'TR = max(High - Low, |High - prev Close|, |Low - prev Close|)',
  'atr': 'ATR(14) = Wilder-smooth(TR, 14) - initial seed = SMA(TR, 14)',
  'plus_di': '+DI(20) = 100 * Wilder-smooth(+DM, 20) / ATR(20)',
  'minus_di': '-DI(20) = 100 * Wilder-smooth(-DM, 20) / ATR(20)',
  'adx': 'ADX(20) = 100 * Wilder-smooth(|+DI - -DI| / (+DI + -DI), 20)',
  'mom1': 'Mom1 = (Close_t - Close_{t-1}) / Close_{t-1}',
  'mom3': 'Mom3 = (Close_t - Close_{t-3}) / Close_{t-3}',
  'mom12': 'Mom12 = (Close_t - Close_{t-12}) / Close_{t-12}',
  'rvol': 'RVol(20) = Volume_t / SMA(Volume, 20)',
}

# D-06: seed window length per indicator.
_SEED_LENGTHS: dict[str, int] = {
  'tr': 1, 'atr': 14, 'plus_di': 20, 'minus_di': 20,
  'adx': 20, 'mom1': 2, 'mom3': 4, 'mom12': 13, 'rvol': 20,
}


# =========================================================================
# Underscore-prefixed format helpers — CANONICAL NAMES per 32-01-PLAN.md
# These delegate to the public implementations below; downstream plans
# (32-02, 32-03, 32-04) bind against these underscore-prefixed names.
# =========================================================================

def _fmt_em_dash() -> str:
  '''UI-SPEC §Format Helper Contracts: single call site for the em-dash empty-value token.'''
  return fmt_em_dash()


def _fmt_currency(value: float) -> str:
  '''UI-SPEC §Format Helper Contracts: $1,234.56 / -$567.89 / $0.00.'''
  return fmt_currency(value)


def _fmt_percent_signed(fraction: float) -> str:
  '''UI-SPEC §Format Helper Contracts: +5.3% / -12.5% / +0.0%.'''
  return fmt_percent_signed(fraction)


def _fmt_percent_unsigned(fraction: float) -> str:
  '''UI-SPEC §Format Helper Contracts: 58.3% / 12.5%. Input is a fraction.'''
  return fmt_percent_unsigned(fraction)


def _fmt_pnl_with_colour(value: float) -> str:
  '''UI-SPEC §Format Helper Contracts + CONTEXT D-16: P&L span coloured by sign.'''
  return fmt_pnl_with_colour(value)


def _fmt_last_updated(now: datetime) -> str:
  '''UI-SPEC §Format Helper Contracts + DASH-08: YYYY-MM-DD HH:MM AEST.'''
  return fmt_last_updated(now)


def _format_indicator_value(
  value: float,
  seed_required: int,
  bars_available: int,
) -> str:
  '''Phase 17 D-05 + D-06: format a single indicator scalar for display.'''
  return format_indicator_value(value, seed_required, bars_available)


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
