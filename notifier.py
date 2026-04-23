r'''Notifier — self-contained single-file HTML email I/O hex.

Owns Resend HTTPS dispatch for the daily signal email. Exposes three
public functions:
  compose_email_subject, compose_email_body, send_daily_email.

NOTF-01..09 (REQUIREMENTS.md §Notifier). Reads a caller-supplied state
dict and posts an inline-CSS HTML body to Resend via the requests
library. Missing RESEND_API_KEY degrades to writing last_email.html
(NOTF-08, D-13).

Public surface (D-01):
  compose_email_subject(state, old_signals, is_test=False) -> str
  compose_email_body(state, old_signals, now) -> str
  send_daily_email(state, old_signals, now, is_test=False) -> int

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. Peer of state_manager,
data_fetcher, dashboard. Must NOT import signal_engine, sizing_engine,
data_fetcher, main, dashboard, numpy, pandas, yfinance. AST blocklist
in tests/test_signal_engine.py::TestDeterminism enforces this via
FORBIDDEN_MODULES_NOTIFIER.

Allowed imports (D-01 allowlist): stdlib (html, json, logging, os, time,
tempfile, datetime, pathlib) + pytz + requests (Resend HTTPS) +
state_manager (load_state convenience CLI path) + system_params
(palette + contract specs + INITIAL_ACCOUNT).

XSS posture: every dynamic value flows through html.escape(value,
quote=True) at leaf render site (Phase 5 D-15 precedent). Inline
style='...' on every coloured span — NO CSS classes, NO <style> block.

Never-crash posture (D-13, NOTF-07, NOTF-08): send_daily_email catches
every Exception from _post_to_resend, logs at WARNING with [Email]
prefix, returns 0. Missing RESEND_API_KEY writes last_email.html.

Clock injection (D-01): compose_email_body(state, old_signals, now)
requires a timezone-aware datetime. Tests pass
PERTH.localize(datetime(2026, 4, 22, 9, 0)) for byte-identical golden
snapshots. C-1 reviews (Phase 5): NEVER construct via
datetime(..., tzinfo=PERTH) — pytz carries LMT offset pre-1895; use
PERTH.localize(...) — always.

Wave 0 (this commit): module stub with all public/private helpers
raising NotImplementedError. Wave 1 fills compose_email_subject +
compose_email_body + formatters. Wave 2 fills _post_to_resend +
send_daily_email + _atomic_write_html + dispatch wiring.
'''
import html
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import pytz
import requests

from state_manager import load_state
from system_params import (
  _COLOR_BG,
  _COLOR_BORDER,
  _COLOR_FLAT,
  _COLOR_LONG,
  _COLOR_SHORT,
  _COLOR_SURFACE,
  _COLOR_TEXT,
  _COLOR_TEXT_DIM,
  _COLOR_TEXT_MUTED,
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  INITIAL_ACCOUNT,
  SPI_COST_AUD,
  SPI_MULT,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
)

logger = logging.getLogger(__name__)


# =========================================================================
# SendStatus — Phase 8 D-08 dispatch-result discriminator
# =========================================================================

class SendStatus(NamedTuple):
  '''Phase 8 D-08: dispatch-result discriminator returned by send_daily_email
  and send_crash_email. Orchestrator (main.run_daily_check) translates
  `ok=False` into state_manager.append_warning for surfacing on the next
  run. NamedTuple chosen over dataclass for immutability + positional
  unpacking: `ok, reason = send_daily_email(...)`.
  '''
  ok: bool
  reason: str | None   # None on success; <=200-char human-readable on failure


# =========================================================================
# Email sender / recipient config (D-14)
# =========================================================================

_EMAIL_FROM = 'signals@carbonbookkeeping.com.au'  # verified Resend sender per PROJECT.md
_EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com'  # operator-confirmed fallback (Option C per REVIEWS.md)


# =========================================================================
# Retry policy (D-12 — mirror data_fetcher.fetch_ohlcv)
# =========================================================================

_RESEND_TIMEOUT_S = 30
_RESEND_RETRIES = 3
_RESEND_BACKOFF_S = 10

# D-12 retry-eligible transient exceptions (mirror data_fetcher:40-44).
# 429 + 5xx raise HTTPError via resp.raise_for_status() and flow through
# this tuple into the retry branch. 4xx (other than 429) fails fast with
# ResendError directly (no HTTPError raise, no retry).
_RESEND_RETRY_EXCEPTIONS = (
  requests.exceptions.Timeout,
  requests.exceptions.ConnectionError,
  requests.exceptions.HTTPError,
)


# =========================================================================
# Display-name + contract-spec dicts (D-02 hex-rule duplicate; parity with dashboard)
# =========================================================================

_INSTRUMENT_DISPLAY_NAMES_EMAIL = {
  'SPI200': 'SPI 200',
  'AUDUSD': 'AUD / USD',
}

_CONTRACT_SPECS_EMAIL = {
  'SPI200': (SPI_MULT, SPI_COST_AUD),
  'AUDUSD': (AUDUSD_NOTIONAL, AUDUSD_COST_AUD),
}

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
# Exception class (Wave 2 raises; Wave 0 just defines)
# =========================================================================

class ResendError(Exception):
  '''Raised when Resend POST fails after retries exhaust or returns non-retryable 4xx.

  NOT propagated past send_daily_email — caught by the outer try/except
  and logged at WARNING. Phase 8 may revisit if crash-email path needs
  discrimination.
  '''


# =========================================================================
# Public API stubs — Waves 1 + 2 fill
# =========================================================================

# =========================================================================
# Email formatters (D-02) — mirror dashboard semantics with inline style.
# Email clients strip CSS classes → _fmt_pnl_with_colour_email emits
# inline style="color:#..." NOT class="...".
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
# Signal-change detection + subject/body composition (D-04 / D-06 / D-10)
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
# Per-section renderers (D-10 7-section body)
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
  cost_open = cost_aud_round_trip / 2
  direction_mult = 1.0 if position['direction'] == 'LONG' else -1.0
  price_diff = current_close - position['entry_price']
  gross = direction_mult * price_diff * position['n_contracts'] * multiplier
  open_cost = cost_open * position['n_contracts']
  return gross - open_cost


def _render_hero_card_email(state: dict, now: datetime) -> str:
  '''B4 revision (Phase 8): the existing hero card (Trading Signals h1 +
  subtitle + Last updated + Signal as of) — extracted verbatim from
  pre-edit _render_header_email so the new composing _render_header_email
  can assemble parts=[banner?, hero, routine?].

  Section 1: site title + subtitle + last-updated + signal-as-of (D-10, Fix 6).
  '''
  last_updated = _fmt_last_updated_email(now)
  # Signal-as-of: prefer a single shared value if both instruments match.
  spi_as_of = _extract_signal_as_of(state, 'SPI200')
  audusd_as_of = _extract_signal_as_of(state, 'AUDUSD')
  if spi_as_of is not None and audusd_as_of is not None:
    if spi_as_of == audusd_as_of:
      signal_as_of_line = f'Signal as of {html.escape(spi_as_of, quote=True)}'
    else:
      signal_as_of_line = (
        f'Signal as of {html.escape(spi_as_of, quote=True)} (SPI 200) '
        f'&middot; {html.escape(audusd_as_of, quote=True)} (AUD / USD)'
      )
  elif spi_as_of is not None:
    signal_as_of_line = f'Signal as of {html.escape(spi_as_of, quote=True)} (SPI 200)'
  elif audusd_as_of is not None:
    signal_as_of_line = (
      f'Signal as of {html.escape(audusd_as_of, quote=True)} (AUD / USD)'
    )
  else:
    signal_as_of_line = (
      f'Signal as of <span style="color:{_COLOR_TEXT_DIM}">never</span>'
    )
  return (
    f'<tr><td style="padding:20px 24px;">'
    f'<h1 style="margin:0;font-size:22px;font-weight:600;'
    f'color:{_COLOR_TEXT};line-height:1.2;">Trading Signals</h1>'
    f'<p style="margin:4px 0 8px 0;font-size:14px;color:{_COLOR_TEXT_MUTED};'
    f'line-height:1.5;">'
    f'{html.escape("SPI 200 & AUD/USD mechanical system", quote=True)}</p>'
    f'<p style="margin:0;font-size:12px;color:{_COLOR_TEXT_MUTED};line-height:1.4;">'
    f'<span style="font-weight:600;letter-spacing:0.04em;'
    f'text-transform:uppercase;">Last updated</span>'
    f'&nbsp;&middot;&nbsp;<span>{html.escape(last_updated, quote=True)}</span>'
    f'</p>'
    f'<p style="margin:4px 0 0 0;font-size:14px;'
    f'color:{_COLOR_TEXT_MUTED};line-height:1.5;">{signal_as_of_line}</p>'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _has_critical_banner(state: dict) -> bool:
  '''D-04 + B2/B3 revisions (Phase 8): True iff state has a critical
  surface — transient `_stale_info` (ERR-05) OR a `state['warnings']`
  entry whose message starts with `'recovered from corruption'` (ERR-03).
  Age filter BYPASSED: corrupt warnings may be tagged with a date other
  than `prior_run_date`; staleness is not even stored in warnings (it is
  a transient runtime key set by orchestrator pre-render).
  '''
  if state.get('_stale_info'):
    return True
  for w in state.get('warnings', []):
    if (
      w.get('source') == 'state_manager'
      and w.get('message', '').startswith('recovered from corruption')
    ):
      return True
  return False


def _render_header_email(state: dict, now: datetime) -> str:
  '''D-01 / D-03 / B2 + B3 revisions (Phase 8):

  Composes: [critical banner?] + hero card + [routine row?].

  Critical banner sources (age-filter BYPASSED — always render when present):
    - `state['_stale_info']` (transient dict from orchestrator) — red border
      `_COLOR_SHORT`, label "Stale state", message includes days_stale.
    - `state['warnings']` entry where `source='state_manager'` AND
      `message.startswith('recovered from corruption')` — gold border
      `_COLOR_FLAT`, label "State was reset".

  Routine row source (subject to D-03 age filter):
    `state['warnings']` entries where `w['date'] == prior_run_date` AND not
    matched by the critical classifier above. Compact metadata line +
    stacked list of messages.

  Hero card: delegated to `_render_hero_card_email` (B4 — verbatim extract).

  XSS posture (preserved): every dynamic value flows through
  `html.escape(value, quote=True)` at leaf render site.
  '''
  parts: list[str] = []

  # --- CRITICAL BANNER 1: stale state via transient _stale_info (B3) ---
  stale_info = state.get('_stale_info')
  if stale_info:
    days = stale_info.get('days_stale', 0)
    last_run_date = stale_info.get('last_run_date', 'unknown')
    safe_msg = html.escape(
      f'Last run was {days} days ago ({last_run_date}) — data + signals may be stale',
      quote=True,
    )
    parts.append(
      f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
      f'border-left:4px solid {_COLOR_SHORT};'
      f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
      f'Roboto,sans-serif;font-size:14px;color:{_COLOR_TEXT};'
      f'line-height:1.5;">'
      f'<p style="margin:0 0 4px 0;font-size:16px;font-weight:700;'
      f'color:{_COLOR_TEXT};letter-spacing:0.02em;">'
      f'━━━ Stale state ━━━</p>'
      f'<p style="margin:0;color:{_COLOR_TEXT_MUTED};font-size:13px;">'
      f'{safe_msg}</p>'
      f'</td></tr>\n'
      f'<tr><td height="16" style="height:16px;font-size:0;line-height:0;">'
      f'&nbsp;</td></tr>\n'
    )

  # --- CRITICAL BANNER 2: corrupt-reset via warnings prefix (B2 / B3) ---
  # Age-filter BYPASSED: state_manager.load_state appends this warning with
  # TODAY's date at corrupt-recovery time, which is likely NOT equal to
  # prior_run_date (state.json was missing/corrupt and thus has no prior_run).
  corrupt_warnings = [
    w for w in state.get('warnings', [])
    if w.get('source') == 'state_manager'
    and w.get('message', '').startswith('recovered from corruption')
  ]
  for w in corrupt_warnings:
    safe_msg = html.escape(w.get('message', ''), quote=True)
    parts.append(
      f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
      f'border-left:4px solid {_COLOR_FLAT};'
      f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
      f'Roboto,sans-serif;font-size:14px;color:{_COLOR_TEXT};'
      f'line-height:1.5;">'
      f'<p style="margin:0 0 4px 0;font-size:16px;font-weight:700;'
      f'color:{_COLOR_TEXT};letter-spacing:0.02em;">'
      f'━━━ State was reset ━━━</p>'
      f'<p style="margin:0;color:{_COLOR_TEXT_MUTED};font-size:13px;">'
      f'{safe_msg}</p>'
      f'</td></tr>\n'
      f'<tr><td height="16" style="height:16px;font-size:0;line-height:0;">'
      f'&nbsp;</td></tr>\n'
    )

  # --- HERO CARD (verbatim from pre-edit function, B4) ---
  parts.append(_render_hero_card_email(state, now))

  # --- ROUTINE ROW: age-filtered non-critical warnings (D-03) ---
  prior_run_date = state.get('last_run')
  if prior_run_date:
    routine = [
      w for w in state.get('warnings', [])
      if w.get('date') == prior_run_date
      and not (
        w.get('source') == 'state_manager'
        and w.get('message', '').startswith('recovered from corruption')
      )
    ]
  else:
    routine = []

  if routine:
    n = len(routine)
    # Plural/singular labels kept as literal substrings so grep audits can
    # locate the routine-row metadata copy in source (D-01 / Phase 8 AC).
    if n == 1:
      label = f'{n} warning from prior run'
    else:
      label = f'{n} warnings from prior run'
    items_html = ''.join(
      f'<div style="margin:4px 0;color:{_COLOR_TEXT_DIM};font-size:12px;">'
      f'&bull; {html.escape(w.get("message", ""), quote=True)}'
      f'</div>'
      for w in routine
    )
    parts.append(
      f'<tr><td style="padding:8px 16px;background:{_COLOR_BG};'
      f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
      f'Roboto,sans-serif;font-size:12px;color:{_COLOR_TEXT_MUTED};">'
      f'<div>{label}</div>'
      f'{items_html}'
      f'</td></tr>\n'
      f'<tr><td height="16" style="height:16px;font-size:0;line-height:0;">'
      f'&nbsp;</td></tr>\n'
    )

  return ''.join(parts)


def _render_action_required_email(
  state: dict, old_signals: dict, run_date_iso: str,
) -> str:
  '''Section 2 (conditional): ACTION REQUIRED red-border block (D-11).

  Emitted ONLY when _detect_signal_changes is True. First-run is a no-op
  per D-06. Close-position copy sourced from
  _closed_position_for_instrument_on (last-3 scan per Fix 4). Uses raw
  Unicode → (U+2192) per Fix 5 — NEVER &rarr;.
  '''
  if not _detect_signal_changes(state, old_signals):
    return ''

  pieces: list[str] = []
  for state_key, yf_sym in _STATE_KEY_TO_YF_SYMBOL.items():
    old = old_signals.get(yf_sym)
    new = _extract_signal_int(state, state_key) or 0
    if old is None or old == new:
      continue
    inst = _fmt_instrument_display_email(state_key)
    old_label = _SIGNAL_LABELS_EMAIL.get(old, 'FLAT')
    new_label = _SIGNAL_LABELS_EMAIL.get(new, 'FLAT')
    # Close-position copy from trade_log (last-3 scan per Fix 4).
    closed = _closed_position_for_instrument_on(state, state_key, run_date_iso)
    close_copy = ''
    if closed is not None:
      direction_raw = str(closed.get('direction', ''))
      n_contracts = int(closed.get('n_contracts', 0))
      entry_price = float(closed.get('entry_price', 0.0))
      contract_word = 'contract' if n_contracts == 1 else 'contracts'
      close_copy = (
        f'<p style="margin:4px 0 0 0;color:{_COLOR_TEXT_MUTED};">'
        f'Close existing {html.escape(direction_raw, quote=True)} position '
        f'({html.escape(str(n_contracts), quote=True)} '
        f'{html.escape(contract_word, quote=True)} @ entry '
        f'{html.escape(_fmt_currency_email(entry_price), quote=True)}).'
        f'</p>'
      )
    # Open-new copy (skip on LONG/SHORT → FLAT since there's nothing to open).
    open_copy = ''
    if new != 0:
      open_copy = (
        f'<p style="margin:4px 0 0 0;color:{_COLOR_TEXT_MUTED};">'
        f'Open new {html.escape(new_label, quote=True)} position.'
        f'</p>'
      )
    # Raw Unicode → per Fix 5 (never &rarr;). Also escape labels/inst.
    pieces.append(
      f'<div style="margin-top:12px;">'
      f'<p style="margin:0;font-weight:600;color:{_COLOR_TEXT};">'
      f'{html.escape(inst, quote=True)}: '
      f'{html.escape(old_label, quote=True)} → '
      f'{html.escape(new_label, quote=True)}'
      f'</p>'
      f'{close_copy}{open_copy}'
      f'</div>'
    )

  if not pieces:
    return ''

  body_items = ''.join(pieces)
  return (
    f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
    f'border-left:4px solid {_COLOR_SHORT};'
    f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
    f'Roboto,sans-serif;font-size:14px;color:{_COLOR_TEXT};'
    f'line-height:1.5;">'
    f'<p style="margin:0 0 8px 0;font-size:20px;font-weight:700;'
    f'color:{_COLOR_TEXT};letter-spacing:0.02em;">'
    f'━━━ ACTION REQUIRED ━━━</p>'
    f'{body_items}'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _render_signal_status_email(state: dict) -> str:
  '''Section 3: signal-status table — 2 rows × 5 cols (D-10).

  Instrument / Signal (coloured) / As of / ADX / Mom snapshot.
  '''
  rows: list[str] = []
  for state_key in ('SPI200', 'AUDUSD'):
    display = _fmt_instrument_display_email(state_key)
    sig_int = _extract_signal_int(state, state_key)
    as_of = _extract_signal_as_of(state, state_key)
    raw = state.get('signals', {}).get(state_key)
    scalars = raw.get('last_scalars') if isinstance(raw, dict) else None

    if sig_int is None or raw is None:
      sig_html = f'<span style="color:{_COLOR_FLAT};font-weight:600">—</span>'
    else:
      label = _SIGNAL_LABELS_EMAIL.get(sig_int, 'FLAT')
      colour = _SIGNAL_COLOUR_EMAIL.get(sig_int, _COLOR_FLAT)
      sig_html = (
        f'<span style="color:{colour};font-weight:600">'
        f'{html.escape(label, quote=True)}</span>'
      )

    if as_of:
      as_of_html = html.escape(as_of, quote=True)
    else:
      as_of_html = (
        f'<span style="color:{_COLOR_TEXT_DIM}">never</span>'
      )

    if scalars:
      adx_cell = html.escape(f'{scalars.get("adx", 0.0):.1f}', quote=True)
      mom1 = _fmt_percent_signed_email(scalars.get('mom1', 0.0))
      mom3 = _fmt_percent_signed_email(scalars.get('mom3', 0.0))
      mom12 = _fmt_percent_signed_email(scalars.get('mom12', 0.0))
      mom_cell = (
        f'{html.escape(mom1, quote=True)} &middot; '
        f'{html.escape(mom3, quote=True)} &middot; '
        f'{html.escape(mom12, quote=True)}'
      )
    else:
      adx_cell = html.escape(_fmt_em_dash_email(), quote=True)
      mom_cell = html.escape(_fmt_em_dash_email(), quote=True)

    rows.append(
      f'<tr style="border-bottom:1px solid {_COLOR_BORDER};">'
      f'<td style="padding:8px 12px;font-size:14px;color:{_COLOR_TEXT};">'
      f'{html.escape(display, quote=True)}</td>'
      f'<td style="padding:8px 12px;font-size:14px;">{sig_html}</td>'
      f'<td style="padding:8px 12px;font-size:14px;color:{_COLOR_TEXT_MUTED};">'
      f'{as_of_html}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{adx_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{mom_cell}</td>'
      f'</tr>'
    )

  header_row = (
    f'<tr style="background:{_COLOR_SURFACE};'
    f'border-bottom:1px solid {_COLOR_BORDER};">'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Instrument</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Signal</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">As of</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">ADX</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Mom</th>'
    f'</tr>'
  )
  body = ''.join(rows)
  return (
    f'<tr><td style="padding:0 12px;">'
    f'<h2 style="margin:0 12px 8px;font-size:20px;font-weight:600;'
    f'color:{_COLOR_TEXT};line-height:1.3;">Signal Status</h2>'
    f'<table role="presentation" cellpadding="0" cellspacing="0" '
    f'border="0" width="100%">'
    f'<thead>{header_row}</thead><tbody>{body}</tbody></table>'
    f'<p style="margin:4px 12px 0;font-size:11px;color:{_COLOR_TEXT_MUTED};">'
    f'Mom reads as 21d &middot; 63d &middot; 252d</p>'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _render_positions_email(state: dict) -> str:
  '''Section 4: open positions table — 7 cols (D-10).

  Instrument / Direction / Entry / Current / Contracts / Trail Stop /
  Unrealised P&L. Empty-state: single row "No open positions" colspan=7.
  '''
  positions = state.get('positions', {})
  rendered_rows: list[str] = []
  for state_key in ('SPI200', 'AUDUSD'):
    pos = positions.get(state_key)
    if pos is None:
      continue
    display = _fmt_instrument_display_email(state_key)
    direction_raw = str(pos.get('direction', ''))
    direction_int = (
      1 if direction_raw == 'LONG' else -1 if direction_raw == 'SHORT' else 0
    )
    dir_colour = _SIGNAL_COLOUR_EMAIL.get(direction_int, _COLOR_FLAT)
    entry_cell = html.escape(_fmt_currency_email(pos['entry_price']), quote=True)
    last_close = _extract_last_close(state, state_key)
    if last_close is None:
      current_cell = html.escape(_fmt_em_dash_email(), quote=True)
    else:
      current_cell = html.escape(_fmt_currency_email(last_close), quote=True)
    contracts_cell = html.escape(str(pos['n_contracts']), quote=True)
    trail = _compute_trail_stop_email(pos)
    trail_cell = html.escape(_fmt_currency_email(trail), quote=True)
    unrealised = _compute_unrealised_pnl_email(pos, state_key, last_close, state)
    if unrealised is None:
      pnl_cell = html.escape(_fmt_em_dash_email(), quote=True)
    else:
      pnl_cell = _fmt_pnl_with_colour_email(unrealised)
    rendered_rows.append(
      f'<tr style="border-bottom:1px solid {_COLOR_BORDER};">'
      f'<td style="padding:8px 12px;font-size:14px;color:{_COLOR_TEXT};">'
      f'{html.escape(display, quote=True)}</td>'
      f'<td style="padding:8px 12px;font-size:14px;">'
      f'<span style="color:{dir_colour};font-weight:600">'
      f'{html.escape(direction_raw, quote=True)}</span></td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{entry_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{current_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{contracts_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{trail_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;">{pnl_cell}</td>'
      f'</tr>'
    )

  if not rendered_rows:
    body = (
      f'<tr><td colspan="7" style="padding:16px;text-align:center;'
      f'font-size:14px;color:{_COLOR_TEXT_DIM};">'
      f'— No open positions —</td></tr>'
    )
  else:
    body = ''.join(rendered_rows)

  header_row = (
    f'<tr style="background:{_COLOR_SURFACE};'
    f'border-bottom:1px solid {_COLOR_BORDER};">'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Instrument</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Direction</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Entry</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Current</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Contracts</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Trail Stop</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Unrealised P&amp;L</th>'
    f'</tr>'
  )
  return (
    f'<tr><td style="padding:0 12px;">'
    f'<h2 style="margin:0 12px 8px;font-size:20px;font-weight:600;'
    f'color:{_COLOR_TEXT};line-height:1.3;">Open Positions</h2>'
    f'<table role="presentation" cellpadding="0" cellspacing="0" '
    f'border="0" width="100%">'
    f'<thead>{header_row}</thead><tbody>{body}</tbody></table>'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _render_todays_pnl_email(state: dict) -> str:
  '''Section 5: Today's P&L + Running equity rollup (D-10).

  today_change = equity_history[-1].equity - equity_history[-2].equity
                 when len ≥ 2 else em-dash.
  running_equity = equity_history[-1].equity (or state['account'] when empty).
  since_inception = (running_equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT.
  '''
  equity_history = state.get('equity_history') or []
  if len(equity_history) >= 2:
    change = equity_history[-1]['equity'] - equity_history[-2]['equity']
    change_html = _fmt_pnl_with_colour_email(change)
  else:
    change_html = (
      f'<span style="color:{_COLOR_TEXT_DIM}">'
      f'{html.escape(_fmt_em_dash_email(), quote=True)}</span>'
    )

  if equity_history:
    equity = equity_history[-1]['equity']
  else:
    equity = float(state.get('account', INITIAL_ACCOUNT))
  equity_cell = html.escape(_fmt_currency_email(equity), quote=True)

  since_inception_frac = (equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT
  since_inception_str = _fmt_percent_signed_email(since_inception_frac)
  if since_inception_frac > 0:
    si_colour = _COLOR_LONG
  elif since_inception_frac < 0:
    si_colour = _COLOR_SHORT
  else:
    si_colour = _COLOR_TEXT_MUTED
  si_html = (
    f'<span style="color:{si_colour}">'
    f'{html.escape(since_inception_str, quote=True)}</span>'
  )

  # Pre-escape apostrophe-bearing literals (Python 3.11 f-string expressions
  # cannot contain backslashes). html.escape with quote=True renders ' as &#x27;.
  today_pnl_heading = html.escape("Today's P&L", quote=True)
  todays_change_label = html.escape("Today's change", quote=True)

  return (
    f'<tr><td style="padding:20px 24px;">'
    f'<h2 style="margin:0 0 16px;font-size:20px;font-weight:600;'
    f'color:{_COLOR_TEXT};line-height:1.3;">{today_pnl_heading}</h2>'
    f'<p style="margin:0;font-size:12px;font-weight:600;'
    f'color:{_COLOR_TEXT_MUTED};text-transform:uppercase;letter-spacing:0.04em;">'
    f'{todays_change_label}</p>'
    f'<p style="margin:8px 0 4px;font-size:22px;font-weight:600;'
    f'font-family:\'SF Mono\',Menlo,Consolas,monospace;">{change_html}</p>'
    f'<p style="margin:0 0 24px;font-size:12px;color:{_COLOR_TEXT_MUTED};">'
    f'from yesterday&#39;s close</p>'
    f'<p style="margin:0;font-size:12px;font-weight:600;'
    f'color:{_COLOR_TEXT_MUTED};text-transform:uppercase;letter-spacing:0.04em;">'
    f'Running equity</p>'
    f'<p style="margin:8px 0 4px;font-size:22px;font-weight:600;'
    f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
    f'{equity_cell}</p>'
    f'<p style="margin:0;font-size:12px;color:{_COLOR_TEXT_MUTED};">'
    f'{si_html} since inception</p>'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _render_closed_trades_email(state: dict) -> str:
  '''Section 6: last 5 closed trades — 5 cols, newest first (D-10).

  Closed / Instrument / Direction / Entry → Exit / P&L.
  Uses net_pnl (NOT gross_pnl) per Phase 5 dashboard precedent.
  Empty-state: single row "No closed trades yet" colspan=5.
  '''
  trade_log = state.get('trade_log') or []
  slice_newest_first = list(reversed(trade_log[-5:]))
  rendered_rows: list[str] = []
  for trade in slice_newest_first:
    exit_date = html.escape(str(trade.get('exit_date', '')), quote=True)
    instrument_raw = str(trade.get('instrument', ''))
    instrument_display = _fmt_instrument_display_email(instrument_raw)
    instrument_cell = html.escape(instrument_display, quote=True)
    direction_raw = str(trade.get('direction', ''))
    direction_int = (
      1 if direction_raw == 'LONG' else -1 if direction_raw == 'SHORT' else 0
    )
    dir_colour = _SIGNAL_COLOUR_EMAIL.get(direction_int, _COLOR_FLAT)
    entry_price = html.escape(
      _fmt_currency_email(float(trade.get('entry_price', 0.0))), quote=True,
    )
    exit_price = html.escape(
      _fmt_currency_email(float(trade.get('exit_price', 0.0))), quote=True,
    )
    pnl_cell = _fmt_pnl_with_colour_email(float(trade.get('net_pnl', 0.0)))
    # Exit-reason rendered as dim small-print subtitle below P&L (retains
    # UI-SPEC §6 5-col layout while exercising T-06-03 leaf escape on
    # the highest-risk state-derived string). Display map converts known
    # raw values; unknown values pass through verbatim (html.escape at leaf).
    exit_reason_raw = str(trade.get('exit_reason', ''))
    reason_display = _EXIT_REASON_DISPLAY_EMAIL.get(
      exit_reason_raw, exit_reason_raw,
    )
    reason_html = html.escape(reason_display, quote=True)
    rendered_rows.append(
      f'<tr style="border-bottom:1px solid {_COLOR_BORDER};">'
      f'<td style="padding:8px 12px;font-size:14px;color:{_COLOR_TEXT};">'
      f'{exit_date}</td>'
      f'<td style="padding:8px 12px;font-size:14px;color:{_COLOR_TEXT};">'
      f'{instrument_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;">'
      f'<span style="color:{dir_colour};font-weight:600">'
      f'{html.escape(direction_raw, quote=True)}</span></td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};'
      f'white-space:normal;">'
      f'{entry_price} → {exit_price}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;">'
      f'{pnl_cell}'
      f'<div style="margin-top:2px;font-size:11px;font-weight:400;'
      f'font-family:-apple-system,BlinkMacSystemFont,sans-serif;'
      f'color:{_COLOR_TEXT_DIM};">{reason_html}</div>'
      f'</td>'
      f'</tr>'
    )

  if not rendered_rows:
    body = (
      f'<tr><td colspan="5" style="padding:16px;text-align:center;'
      f'font-size:14px;color:{_COLOR_TEXT_DIM};">'
      f'— No closed trades yet —</td></tr>'
    )
  else:
    body = ''.join(rendered_rows)

  header_row = (
    f'<tr style="background:{_COLOR_SURFACE};'
    f'border-bottom:1px solid {_COLOR_BORDER};">'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Closed</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Instrument</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Direction</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Entry → Exit</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">P&amp;L</th>'
    f'</tr>'
  )
  return (
    f'<tr><td style="padding:0 12px;">'
    f'<h2 style="margin:0 12px 8px;font-size:20px;font-weight:600;'
    f'color:{_COLOR_TEXT};line-height:1.3;">Last 5 Closed Trades</h2>'
    f'<table role="presentation" cellpadding="0" cellspacing="0" '
    f'border="0" width="100%">'
    f'<thead>{header_row}</thead><tbody>{body}</tbody></table>'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _render_footer_email(state: dict, now: datetime) -> str:  # noqa: ARG001
  '''Section 7: footer disclaimer + sender + run-date (D-10).

  state arg reserved for future use (e.g. schema_version surfacing).
  '''
  run_date_iso = now.strftime('%Y-%m-%d')
  return (
    f'<tr><td style="padding:20px 24px;text-align:center;">'
    f'<p style="margin:0 0 4px;font-size:12px;color:{_COLOR_TEXT_DIM};'
    f'line-height:1.4;">Signal-only system. Not financial advice.</p>'
    f'<p style="margin:0 0 4px;font-size:12px;color:{_COLOR_TEXT_DIM};'
    f'line-height:1.4;">Trading Signals — sent by '
    f'{html.escape(_EMAIL_FROM, quote=True)}</p>'
    f'<p style="margin:0;font-size:12px;color:{_COLOR_TEXT_DIM};'
    f'line-height:1.4;">Run date: {html.escape(run_date_iso, quote=True)}</p>'
    f'</td></tr>\n'
  )


def compose_email_body(
  state: dict,
  old_signals: dict,
  now: datetime,
) -> str:
  '''D-07 HTML shell + D-10 7-section body (NOTF-03/04/06/09).

  - Inline CSS only; NO <style>; NO CSS classes; NO @media query.
  - role="presentation" on layout tables (D-07 accessibility).
  - bgcolor attributes alongside inline style (D-07 Outlook redundancy).
  - max-width:600px;width:100% fluid-hybrid (D-08).
  - Full <meta> tag suite for Gmail + iOS Mail (RESEARCH §2).
  - Every state-derived string escaped via html.escape(value, quote=True)
    at leaf interpolation (NOTF-09; Phase 5 D-15 leaf discipline).
  - Raw Unicode → (U+2192) in ACTION REQUIRED per Fix 5 — never &rarr;.
  - Clock injection: uses now= parameter; must be tz-aware (T-06-04).
  '''
  # Belt-and-braces naive-datetime rejection (T-06-04) — also enforced
  # inside _fmt_last_updated_email but surface the error at the top
  # call site for clearer traces.
  if now.tzinfo is None:
    raise ValueError(
      f'compose_email_body requires a timezone-aware datetime; '
      f'got naive datetime={now!r}'
    )
  run_date_iso = now.strftime('%Y-%m-%d')

  sections = (
    _render_header_email(state, now)
    + _render_action_required_email(state, old_signals, run_date_iso)
    + _render_signal_status_email(state)
    + _render_positions_email(state)
    + _render_todays_pnl_email(state)
    + _render_closed_trades_email(state)
    + _render_footer_email(state, now)
  )

  return (
    f'<!DOCTYPE html>\n'
    f'<html lang="en">\n'
    f'<head>\n'
    f'<meta charset="utf-8">\n'
    f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    f'<meta name="color-scheme" content="dark only">\n'
    f'<meta name="supported-color-schemes" content="dark">\n'
    f'<meta name="x-apple-disable-message-reformatting">\n'
    f'<meta name="format-detection" content="telephone=no,date=no,'
    f'address=no,email=no">\n'
    f'<title>Trading Signals &mdash; {html.escape(run_date_iso, quote=True)}'
    f'</title>\n'
    f'</head>\n'
    f'<body style="margin:0;padding:0;background:{_COLOR_BG};'
    f'color:{_COLOR_TEXT};font-family:-apple-system,BlinkMacSystemFont,'
    f'\'Segoe UI\',Roboto,sans-serif;">\n'
    f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
    f'width="100%" bgcolor="{_COLOR_BG}" style="background:{_COLOR_BG};">\n'
    f'<tr><td align="center" style="padding:16px 8px;">\n'
    f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
    f'width="100%" bgcolor="{_COLOR_SURFACE}" '
    f'style="max-width:600px;width:100%;background:{_COLOR_SURFACE};'
    f'border:1px solid {_COLOR_BORDER};">\n'
    f'{sections}'
    f'</table>\n'
    f'</td></tr>\n'
    f'</table>\n'
    f'</body>\n'
    f'</html>\n'
  )


def _atomic_write_html(data: str, path: Path) -> None:
  '''Mirror of state_manager._atomic_write + dashboard._atomic_write_html.

  D-13 durability sequence:
    1. write data to tempfile in same directory as target
    2. flush + fsync(tempfile.fileno()) — data durable on disk
    3. close tempfile (NamedTemporaryFile context exit)
    4. os.replace(tempfile, target) — atomic rename
    5. fsync(parent dir fd) on POSIX — rename itself durable on disk

  C-7 reviews (Phase 5): `newline='\\n'` on tempfile forces LF regardless
  of platform — text-mode default on Windows translates \\n → \\r\\n
  which would drift committed goldens (byte-stability gate).
  '''
  parent = path.parent
  tmp_path_str: str | None = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
      newline='\n',  # C-7: force LF regardless of platform
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    # D-17: os.replace BEFORE parent-dir fsync (rename durability).
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None  # success: do not delete in finally
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass


def _post_to_resend(
  api_key: str,
  from_addr: str,
  to_addr: str,
  subject: str,
  html_body: str | None = None,
  timeout_s: int = _RESEND_TIMEOUT_S,
  retries: int = _RESEND_RETRIES,
  backoff_s: int = _RESEND_BACKOFF_S,
  text_body: str | None = None,
) -> None:
  '''POST to Resend with retry-on-transient (D-12 + RESEARCH §1).

  Mirrors data_fetcher.fetch_ohlcv retry policy. 4xx except 429 fails fast;
  429 + 5xx + network errors retry up to `retries` times with flat
  `backoff_s` sleep (RESEARCH §1 — 429 IS retryable per Resend guidance).

  Raises ResendError after retries exhaust OR on non-retryable 4xx
  (400/401/403/422/etc., but NOT 429).

  Phase 8: accepts either `html_body` (existing callers) or `text_body`
  (Phase 8 `send_crash_email`) or both. Raises `ValueError` if both are
  None. Resend API accepts both keys simultaneously; the server picks
  the correct MIME part per recipient client.

  REVIEWS.md Fix 1 (HIGH): api_key MUST be actively redacted from any
  error message built from resp.text OR an exception repr. We replace the
  literal api_key with '[REDACTED]' before raising — defense-in-depth
  against Resend echoing the Authorization header back in its error body.

  REVIEWS.md Fix 2 (MEDIUM): timeout uses tuple (5, timeout_s) — 5s
  connect-phase + `timeout_s` read-phase. Prevents hung DNS/TCP handshake
  from consuming the full read budget.
  '''
  if html_body is None and text_body is None:
    raise ValueError('_post_to_resend requires html_body OR text_body')
  payload: dict = {
    'from': from_addr,
    'to': [to_addr],
    'subject': subject,
  }
  if html_body is not None:
    payload['html'] = html_body
  if text_body is not None:
    payload['text'] = text_body
  headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
  }
  last_err: Exception | None = None
  for attempt in range(1, retries + 1):
    try:
      resp = requests.post(
        'https://api.resend.com/emails',
        headers=headers,
        json=payload,
        timeout=(5, timeout_s),  # Fix 2: (connect, read) tuple
      )
      # RESEARCH §1: 429 IS retryable per Resend — special-case BEFORE
      # the 4xx fail-fast band. Raise HTTPError → caught by the retry
      # branch below.
      if resp.status_code == 429:
        raise requests.exceptions.HTTPError('429 rate-limit', response=resp)
      if 400 <= resp.status_code < 500:
        # Fix 1 (T-06-02): truncate AND redact api_key from any echo.
        safe_body = resp.text[:200]
        if api_key:
          safe_body = safe_body.replace(api_key, '[REDACTED]')
        raise ResendError(
          f'4xx from Resend: {resp.status_code} {safe_body}',
        )
      resp.raise_for_status()  # 5xx → HTTPError → retry branch
      return
    except _RESEND_RETRY_EXCEPTIONS as e:
      last_err = e
      logger.warning(
        '[Email] Resend attempt %d/%d failed: %s: %s',
        attempt, retries, type(e).__name__, e,
      )
      if attempt < retries:
        time.sleep(backoff_s)
  # Fix 1 (T-06-02): redact api_key from exhausted-retries message too —
  # last_err.__str__ may include response bodies or header echoes.
  err_repr = f'{type(last_err).__name__}: {last_err}'
  if api_key:
    err_repr = err_repr.replace(api_key, '[REDACTED]')
  raise ResendError(
    f'retries exhausted after {retries} attempts; last error: {err_repr[:200]}',
  ) from last_err


def send_daily_email(
  state: dict,
  old_signals: dict,
  now: datetime,
  is_test: bool = False,
) -> SendStatus:
  '''Public dispatch. NEVER raises. Returns SendStatus on every path.

  NOTF-01: POSTs to Resend via _post_to_resend when RESEND_API_KEY present.
  NOTF-07: Resend API failure logs warning, returns SendStatus(ok=False,
    reason=...). Orchestrator (main.run_daily_check) translates into
    state_manager.append_warning so the failure surfaces on the next run
    (D-08 / Phase 8).
  NOTF-08: Missing RESEND_API_KEY → log WARN + return
    SendStatus(ok=True, reason='no_api_key'). Graceful degradation is NOT
    a failure — operator chose to run without a dispatch path.
  D-02 (Phase 8): `last_email.html` written on EVERY dispatch path,
    regardless of RESEND_API_KEY presence or Resend success — operator
    grep-recovery source of truth. Disk-write failure is logged but does
    NOT abort Resend dispatch.
  D-04 (Phase 8): subject gets `[!]` prefix when `_has_critical_banner`
    returns True (stale state or corrupt-reset).

  Recipient: os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK).
  '''
  has_critical = _has_critical_banner(state)
  subject = compose_email_subject(
    state, old_signals,
    is_test=is_test, has_critical_banner=has_critical,
  )
  try:
    html_body = compose_email_body(state, old_signals, now)
  except Exception as e:
    logger.warning(
      '[Email] WARN compose_email_body failed: %s: %s',
      type(e).__name__, e,
    )
    return SendStatus(
      ok=False,
      reason=f'compose_body_failed: {type(e).__name__}: {e}'[:200],
    )

  # D-02 (Phase 8): write last_email.html EVERY run, BEFORE any api_key
  # or dispatch branch. Operator grep-recovery source of truth.
  last_email_path = Path('last_email.html')
  try:
    _atomic_write_html(html_body, last_email_path)
  except Exception as e:
    logger.warning(
      '[Email] WARN last_email.html write failed: %s: %s',
      type(e).__name__, e,
    )
    # Continue — disk-write failure must not block Resend dispatch.

  api_key = os.environ.get('RESEND_API_KEY')
  if not api_key:
    logger.warning(
      '[Email] WARN RESEND_API_KEY missing — wrote %s (fallback)',
      last_email_path,
    )
    return SendStatus(ok=True, reason='no_api_key')

  to_addr = os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)
  try:
    _post_to_resend(api_key, _EMAIL_FROM, to_addr, subject, html_body)
    logger.info('[Email] sent to %s subject=%r', to_addr, subject)
    return SendStatus(ok=True, reason=None)
  except ResendError as e:
    # NOTF-07: log + return failure status; orchestrator translates to warning.
    logger.warning('[Email] WARN send failed: %s', e)
    return SendStatus(ok=False, reason=str(e)[:200])
  except Exception as e:
    # Belt-and-braces: ANY unexpected exception logged not propagated.
    # The ONLY place this codebase allows a bare Exception catch — email
    # delivery is not worth crashing the daily run (state already saved).
    logger.warning(
      '[Email] WARN unexpected failure: %s: %s', type(e).__name__, e,
    )
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])


def send_crash_email(
  exc: BaseException,
  state_summary: str,
  now: datetime | None = None,
) -> SendStatus:
  '''D-05/D-06/D-07 (Phase 8): text/plain [CRASH] dispatch.

  Reuses `_post_to_resend` retry loop (3 retries, flat backoff) — accepts
  the 30s max hang on exit for parity with regular sends. NEVER raises.
  No last_crash.html disk fallback: crash emails are transient; operator
  has `journalctl` / GHA logs for traceback recovery.

  Body format (text/plain, D-06):
    Timestamp: <ISO AWST>
    Exception: <class>: <message>

    Traceback:
      <traceback.format_exception() output>

    State summary:
      <state_summary argument, verbatim>

  `state_summary` is built by the caller (main._build_crash_state_summary
  in Plan 03) so notifier never touches state.json. Keeps hex-boundary
  clean. Text/plain body means NO html escape on `state_summary`; it is
  rendered verbatim.
  '''
  import traceback as _tb  # local import: no hex-boundary change needed
  if now is None:
    now = datetime.now(pytz.UTC)
  awst = pytz.timezone('Australia/Perth')
  iso_awst = now.astimezone(awst).strftime('%Y-%m-%d %H:%M:%S %Z')
  date_only = now.astimezone(awst).strftime('%Y-%m-%d')
  subject = f'[CRASH] Trading Signals — {date_only}'
  tb_text = _tb.format_exception(type(exc), exc, exc.__traceback__)
  body = (
    f'Timestamp: {iso_awst}\n'
    f'Exception: {type(exc).__name__}: {exc}\n'
    f'\n'
    f'Traceback:\n'
    f'{"".join(tb_text)}\n'
    f'State summary:\n'
    f'{state_summary}\n'
  )

  api_key = os.environ.get('RESEND_API_KEY')
  if not api_key:
    logger.warning(
      '[Email] WARN crash-email: RESEND_API_KEY missing — skipping dispatch',
    )
    return SendStatus(ok=False, reason='no_api_key')

  to_addr = os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)
  if not to_addr:
    logger.warning(
      '[Email] WARN crash-email: SIGNALS_EMAIL_TO missing — skipping dispatch',
    )
    return SendStatus(ok=False, reason='no_recipient')

  try:
    _post_to_resend(
      api_key=api_key,
      from_addr=_EMAIL_FROM,
      to_addr=to_addr,
      subject=subject,
      html_body=None,
      text_body=body,
    )
    logger.info('[Email] CRASH email sent to %s', to_addr)
    return SendStatus(ok=True, reason=None)
  except ResendError as e:
    logger.warning('[Email] WARN crash-email send failed: %s', e)
    return SendStatus(ok=False, reason=str(e)[:200])
  except Exception as e:
    logger.warning(
      '[Email] WARN crash-email unexpected failure: %s: %s',
      type(e).__name__, e,
    )
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])


# =========================================================================
# CLI entrypoint — operator preview (python -m notifier)
# =========================================================================

if __name__ == '__main__':
  # Operator-only preview: python -m notifier.
  # Loads current state.json, sends [TEST]-prefixed email with no baseline.
  # If RESEND_API_KEY unset, writes last_email.html (NOTF-08) and exits 0.
  import sys

  logging.basicConfig(level=logging.INFO, format='%(message)s')
  _state = load_state()
  _old_signals: dict = {'^AXJO': None, 'AUDUSD=X': None}
  _now = datetime.now(pytz.timezone('Australia/Perth'))
  _status = send_daily_email(_state, _old_signals, _now, is_test=True)
  # Back-to-back Plan 03 adopts the SendStatus contract in main.py.
  # CLI preview: ok=True → exit 0; ok=False → exit 1 for operator feedback.
  sys.exit(0 if _status.ok else 1)
