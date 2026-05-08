'''Email formatters + signal extractors + subject composition.

Extracted from notifier.py in Plan 27-12 (notifier package split).

D-02 mirror of dashboard semantics with inline style. Email clients strip
CSS classes → _fmt_pnl_with_colour_email emits inline style="color:#..."
NOT class="...".

D-04 / D-06 / D-10 — signal-change detection + subject template.
'''
import html
import logging
from datetime import datetime

import pytz

from pnl_engine import entry_side_cost  # Phase 27 #7: half-cost helper
from system_params import (
  _COLOR_FLAT,
  _COLOR_LONG,
  _COLOR_SHORT,
  _COLOR_TEXT_MUTED,
  FALLBACK_CONTRACT_SPECS,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
)

logger = logging.getLogger(__name__)


# =========================================================================
# Display-name + contract-spec dicts (D-02 hex-rule duplicate; parity with dashboard)
# =========================================================================

_INSTRUMENT_DISPLAY_NAMES_EMAIL = {
  'SPI200': 'SPI 200',
  'AUDUSD': 'AUD / USD',
}

# Phase 8 IN-05: _CONTRACT_SPECS_EMAIL is now a re-export of
# system_params.FALLBACK_CONTRACT_SPECS — single source of truth shared with
# dashboard.py. Local binding retained so existing call sites inside this
# module continue to work without churn.
_CONTRACT_SPECS_EMAIL = FALLBACK_CONTRACT_SPECS

# D-05: state_key → yfinance symbol for old_signals dict lookup (old_signals
# is keyed by yfinance symbol per main.py pre-run capture).
_STATE_KEY_TO_YF_SYMBOL = {
  'SPI200': '^AXJO',
  'AUDUSD': 'AUDUSD=X',
}

# D-04: signal int → display label (bare words, no emoji).
_SIGNAL_LABELS_EMAIL = {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}

# D-04 / UI-SPEC §Color: signal int → inline hex colour for coloured spans.
_SIGNAL_COLOUR_EMAIL = {1: _COLOR_LONG, -1: _COLOR_SHORT, 0: _COLOR_FLAT}

# UI-SPEC §6 closed-trades: exit_reason raw → display copy. Unknown values
# pass through verbatim (html.escape at leaf render site).
_EXIT_REASON_DISPLAY_EMAIL = {
  'flat_signal': 'Signal flat',
  'signal_reversal': 'Reversal',
  'stop_hit': 'Stop hit',
  'adx_exit': 'ADX drop',
}


# =========================================================================
# Email formatters (D-02) — mirror dashboard semantics with inline style.
# =========================================================================

def _fmt_em_dash_email() -> str:
  '''D-02: em-dash glyph for missing/empty cells (U+2014, single char).'''
  return '—'


def _fmt_currency_email(value: float) -> str:
  '''D-02: $X,XXX.XX with thousands separator; negative prefixed with `-$`.

  Always 2 dp. Locale-independent (PEP 3101 , and . format spec).
  Matches dashboard._fmt_currency output byte-for-byte.
  '''
  if value < 0:
    return f'-${-value:,.2f}'
  return f'${value:,.2f}'


def _fmt_percent_signed_email(fraction: float) -> str:
  '''D-02: X.X% with leading sign; for since-inception / today's-change rollups.

  Input is a fraction (0.0123 → +1.2%). Leading + preserved for positive
  AND zero values — matches dashboard _fmt_percent_signed.
  '''
  return f'{fraction * 100:+.1f}%'


def _fmt_percent_unsigned_email(fraction: float) -> str:
  '''D-02: X.X% without leading +; for ADX / RVol display.

  Input is a fraction (0.0123 → 1.2%). Negative values still show the
  minus sign (f-string :.1f preserves it).
  '''
  return f'{fraction * 100:.1f}%'


def _fmt_pnl_with_colour_email(value: float) -> str:
  '''D-02: P&L with inline colour span — LONG green / SHORT red / zero muted.

  Email clients strip CSS classes — this MUST use inline style='...'
  (NOT class='...'). html.escape applied to BOTH the colour hex
  (defense-in-depth; hex values are ASCII so no-op but belt-and-braces)
  AND the body text (numeric output is safe but escape anyway per
  Phase 5 D-15 leaf discipline).

  Positive: <span style="color:#22c55e">+$1,234.56</span>
  Negative: <span style="color:#ef4444">-$567.89</span>
  Zero:     <span style="color:#cbd5e1">$0.00</span>
  '''
  if value > 0:
    colour = _COLOR_LONG
    body = f'+{_fmt_currency_email(value)}'
  elif value < 0:
    colour = _COLOR_SHORT
    body = _fmt_currency_email(value)
  else:
    colour = _COLOR_TEXT_MUTED
    body = '$0.00'
  return (
    f'<span style="color:{html.escape(colour, quote=True)}">'
    f'{html.escape(body, quote=True)}</span>'
  )


def _fmt_last_updated_email(now: datetime) -> str:
  '''D-02: AWST wall-clock timestamp for email header.

  C-1 reviews (Phase 5): REJECT naive datetime loudly. Callers MUST
  pass timezone-aware via PERTH.localize(...) — never datetime(...,
  tzinfo=PERTH). Mirror of dashboard._fmt_last_updated semantic.
  '''
  if now.tzinfo is None:
    raise ValueError(
      '_fmt_last_updated_email requires a timezone-aware datetime; '
      f'got naive datetime={now!r}'
    )
  awst = now.astimezone(pytz.timezone('Australia/Perth'))
  return awst.strftime('%Y-%m-%d %H:%M AWST')


def _fmt_instrument_display_email(state_key: str) -> str:
  '''D-02: state-key → display name lookup (SPI200 → SPI 200).

  Unknown keys pass through unchanged; leaf html.escape in the caller.
  '''
  return _INSTRUMENT_DISPLAY_NAMES_EMAIL.get(state_key, state_key)


# =========================================================================
# Signal-change detection + subject composition (D-04 / D-06 / D-10)
# =========================================================================

def _detect_signal_changes(state: dict, old_signals: dict) -> bool:
  '''D-06: True iff any instrument's signal changed from old_signals.

  First-run case (old_signals[yf_sym] is None) is treated as NO CHANGE
  per D-06 — there is no baseline to compare against; emitting 🔴 on
  first run would be noise.

  Handles BOTH Phase 3 reset_state int shape AND Phase 4 D-08 dict
  shape for state['signals'][state_key] per Phase 4 Pitfall 7.
  '''
  signals = state.get('signals', {})
  for state_key, yf_sym in _STATE_KEY_TO_YF_SYMBOL.items():
    old = old_signals.get(yf_sym)
    raw = signals.get(state_key)
    if raw is None:
      new = 0
    elif isinstance(raw, int):
      new = raw
    else:
      new = raw.get('signal', 0)
    if old is not None and old != new:
      return True
  return False


def compose_email_subject(
  state: dict,
  old_signals: dict,
  is_test: bool = False,
  has_critical_banner: bool = False,   # D-04 (Phase 8)
) -> str:
  '''D-04 subject template:

    {emoji} {YYYY-MM-DD} — SPI200 {SIG}, AUDUSD {SIG} — Equity ${X,XXX}

  Emoji per D-04:
    🔴 (U+1F534) when _detect_signal_changes is True.
    📊 (U+1F4CA) when unchanged OR first-run (D-06).
  Phase 8 D-04: `[!]` prefix (with trailing space) AFTER `[TEST]` BEFORE the
  core when `has_critical_banner=True` (stale state or corrupt-reset).
  `[TEST]` prefix (with trailing space) BEFORE `[!]` when `is_test=True`.

  Date from state['signals'][<any_key>]['as_of_run'] (ISO YYYY-MM-DD);
  falls back to state['last_run'] if signals are legacy int shape OR
  missing as_of_run.

  Equity = int(round(state['account'])) formatted with thousands
  separator and no cents.

  Signal labels: bare LONG / SHORT / FLAT (D-04 — no emoji in signal slot).
  '''
  any_changed = _detect_signal_changes(state, old_signals)
  emoji = '🔴' if any_changed else '📊'

  # Date: prefer dict-shape as_of_run; fall back to state['last_run'].
  signals = state.get('signals', {})
  date_iso: str | None = None
  for state_key in ('SPI200', 'AUDUSD'):
    raw = signals.get(state_key)
    if isinstance(raw, dict) and raw.get('as_of_run'):
      date_iso = raw['as_of_run']
      break
  if date_iso is None:
    date_iso = state.get('last_run') or ''

  # Signal labels: both instruments. Handles int + dict shapes.
  def _extract_signal(state_key: str) -> int:
    raw = signals.get(state_key)
    if raw is None:
      return 0
    if isinstance(raw, int):
      return raw
    return raw.get('signal', 0)

  spi_label = _SIGNAL_LABELS_EMAIL.get(_extract_signal('SPI200'), 'FLAT')
  audusd_label = _SIGNAL_LABELS_EMAIL.get(_extract_signal('AUDUSD'), 'FLAT')

  # Equity: int(round(account)) → $X,XXX (no cents, thousands separator).
  account = float(state.get('account', 0.0))
  equity_dollars = int(round(account))
  equity_str = f'${equity_dollars:,}'

  # WR-02 close (2026-04-22): when date_iso resolves empty (first run —
  # last_run=null AND no dict-shape as_of_run on any instrument), use
  # 'first run' as a self-documenting label so the subject never has
  # a double-space between emoji and em-dash. D-04 template shape
  # (position of date field in the subject) is preserved.
  date_label = date_iso if date_iso else 'first run'

  # Assembly: [TEST] prefix BEFORE emoji per D-04 line 92.
  # Phase 8 D-04: `[!]` prefix injected BETWEEN [TEST] and emoji when
  # has_critical_banner=True (stale state or corrupt-reset). Order:
  # [TEST] [!] <emoji> ...
  core = (
    f'{emoji} {date_label} — SPI200 {spi_label}, '
    f'AUDUSD {audusd_label} — Equity {equity_str}'
  )
  prefix_parts: list[str] = []
  if is_test:
    prefix_parts.append('[TEST]')
  if has_critical_banner:
    prefix_parts.append('[!]')
  if prefix_parts:
    return f"{' '.join(prefix_parts)} {core}"
  return core


def _closed_position_for_instrument_on(
  state: dict, state_key: str, run_date_iso: str,
) -> dict | None:
  '''UI-SPEC §2 Option A: return the most recent trade_log entry for
  `state_key` closed on `run_date_iso`, scanning up to the last 3 records.

  Fix 4 (REVIEWS.md): widen scan to last 3 records — if BOTH instruments
  close on the same run (SPI200 AND AUDUSD reversal on same day),
  trade_log[-1] only covers one instrument. Scanning the last 3 records
  (tail + 2 preceding) covers same-run double-close without risk of
  picking up stale matches from earlier days.

  D-11: dominant case is signal reversal → record_trade just appended to
  trade_log during run_daily_check. trade_log tail is deterministic
  post-run.

  Returns the 12-field trade dict if matched, else None.
  '''
  trade_log = state.get('trade_log') or []
  if not trade_log:
    return None
  # Scan last 3 records (tail-first so most-recent match wins).
  for entry in reversed(trade_log[-3:]):
    if (
      entry.get('exit_date') == run_date_iso
      and entry.get('instrument') == state_key
    ):
      return entry
  return None


# =========================================================================
# Per-section signal extractors (state['signals'] shape compat)
# =========================================================================

def _extract_signal_int(state: dict, state_key: str) -> int | None:
  '''Read state['signals'][state_key] handling both int (legacy) + dict shapes.

  Returns None when the entry is absent (pre-first-run signal shape).
  '''
  raw = state.get('signals', {}).get(state_key)
  if raw is None:
    return None
  if isinstance(raw, int):
    return raw
  return raw.get('signal', 0)


def _extract_signal_as_of(state: dict, state_key: str) -> str | None:
  '''Read state['signals'][state_key]['signal_as_of']; None when legacy int or absent.'''
  raw = state.get('signals', {}).get(state_key)
  if isinstance(raw, dict):
    return raw.get('signal_as_of')
  return None


def _extract_last_close(state: dict, state_key: str) -> float | None:
  '''Read state['signals'][state_key]['last_close']; None when legacy int or absent.'''
  raw = state.get('signals', {}).get(state_key)
  if isinstance(raw, dict):
    return raw.get('last_close')
  return None


def _compute_trail_stop_email(position: dict) -> float:
  '''Inline re-impl of sizing_engine trail-stop — hex-fence per D-01.

  LONG: peak_price - TRAIL_MULT_LONG * atr_entry (fallback: entry_price)
  SHORT: trough_price + TRAIL_MULT_SHORT * atr_entry (fallback: entry_price)
  '''
  atr_entry = position['atr_entry']
  if position['direction'] == 'LONG':
    peak = position.get('peak_price') or position['entry_price']
    return peak - TRAIL_MULT_LONG * atr_entry
  trough = position.get('trough_price') or position['entry_price']
  return trough + TRAIL_MULT_SHORT * atr_entry


def _compute_unrealised_pnl_email(
  position: dict, state_key: str, current_close: float | None,
  state: dict | None = None,
) -> float | None:
  '''Inline re-impl of sizing_engine.compute_unrealised_pnl — hex-fence per D-01.

  Per D-13: opening half-cost deducted here (matches sizing_engine and
  Phase 5 dashboard). cost_open = cost_aud_round_trip / 2 per contract.

  LONG:  gross = (current - entry) * n * multiplier; pnl = gross - cost_open*n
  SHORT: gross = (entry - current) * n * multiplier; pnl = gross - cost_open*n

  Phase 8 WR-01 fix: prefer the operator-selected tier values from
  state['_resolved_contracts'][state_key]; fall back to the module-level
  _CONTRACT_SPECS_EMAIL defaults when state is None or lacks
  _resolved_contracts (pre-Phase-8 state shape or non-load_state callers
  like unit tests that build state dicts directly). Mirrors D-17
  resolved-tier flow.
  '''
  if current_close is None:
    return None
  resolved = None
  if state is not None:
    resolved = state.get('_resolved_contracts', {}).get(state_key)
  if resolved is not None:
    multiplier = resolved['multiplier']
    cost_aud_round_trip = resolved['cost_aud']
  else:
    logger.debug(
      '[Email] _resolved_contracts missing for %s; falling back to '
      'module-level _CONTRACT_SPECS_EMAIL default tier', state_key,
    )
    multiplier, cost_aud_round_trip = _CONTRACT_SPECS_EMAIL[state_key]
  # Phase 27 #7: entry-side cost via canonical helper (half of round-trip,
  # AUD-cent quantized HALF_UP). Float() at the consumption boundary so the
  # downstream gross/open_cost arithmetic stays in float (this is a display
  # path; pnl_engine is the Decimal authority).
  cost_open = float(entry_side_cost(cost_aud_round_trip))
  direction_mult = 1.0 if position['direction'] == 'LONG' else -1.0
  price_diff = current_close - position['entry_price']
  gross = direction_mult * price_diff * position['n_contracts'] * multiplier
  open_cost = cost_open * position['n_contracts']
  return gross - open_cost
