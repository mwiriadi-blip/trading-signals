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
import html  # noqa: F401 — Wave 1 per-surface escape at leaf render sites
import json  # noqa: F401 — Wave 2 last_email.html fallback
import logging
import os  # noqa: F401 — Wave 2 RESEND_API_KEY read + atomic write
import tempfile  # noqa: F401 — Wave 2 _atomic_write_html
import time  # noqa: F401 — Wave 2 _post_to_resend retry backoff
from datetime import datetime  # noqa: F401 — Wave 1 compose_email_body clock arg
from pathlib import Path  # noqa: F401 — Wave 2 last_email.html path

import pytz  # noqa: F401 — Wave 1 AWST localisation parity with dashboard
import requests  # noqa: F401 — Wave 2 Resend HTTPS POST

from state_manager import (
  load_state,  # noqa: F401 — CLI convenience path only (python -m notifier)
)
from system_params import (  # noqa: F401 — Wave 1 contract specs + palette
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
) -> str:
  '''D-04 subject template:

    {emoji} {YYYY-MM-DD} — SPI200 {SIG}, AUDUSD {SIG} — Equity ${X,XXX}

  Emoji per D-04:
    🔴 (U+1F534) when _detect_signal_changes is True.
    📊 (U+1F4CA) when unchanged OR first-run (D-06).
  [TEST] prefix (with trailing space) BEFORE emoji when is_test=True.

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

  # Assembly: [TEST] prefix BEFORE emoji per D-04 line 92.
  core = (
    f'{emoji} {date_iso} — SPI200 {spi_label}, '
    f'AUDUSD {audusd_label} — Equity {equity_str}'
  )
  if is_test:
    return f'[TEST] {core}'
  return core


def compose_email_body(
  state: dict,
  old_signals: dict,
  now: datetime,
) -> str:
  '''Wave 1 (06-02) fills per D-07/D-08/D-10/D-11. See UI-SPEC + CONTEXT.'''
  raise NotImplementedError('Wave 1 (06-02): compose_email_body per D-07/D-10')


def send_daily_email(
  state: dict,
  old_signals: dict,
  now: datetime,
  is_test: bool = False,
) -> int:
  '''Wave 2 (06-03) fills per D-13 + D-14. NEVER raises (NOTF-07/NOTF-08).'''
  raise NotImplementedError('Wave 2 (06-03): send_daily_email per D-13')


# =========================================================================
# Private helpers — Wave 2 fills
# =========================================================================

def _post_to_resend(
  api_key: str,
  from_addr: str,
  to_addr: str,
  subject: str,
  html_body: str,
  timeout_s: int = _RESEND_TIMEOUT_S,
  retries: int = _RESEND_RETRIES,
  backoff_s: int = _RESEND_BACKOFF_S,
) -> None:
  '''Wave 2 (06-03) fills per D-12 + RESEARCH §1 (429 special-case).'''
  raise NotImplementedError('Wave 2 (06-03): _post_to_resend retry loop')


def _atomic_write_html(data: str, path: Path) -> None:
  '''Wave 2 (06-03) fills — duplicate of dashboard._atomic_write_html per D-13.'''
  raise NotImplementedError('Wave 2 (06-03): _atomic_write_html (dashboard mirror)')


# =========================================================================
# CLI entrypoint stub — Wave 2 wires
# =========================================================================

if __name__ == '__main__':
  # Operator-only preview: python -m notifier. Wave 2 wires to load_state
  # + send_daily_email with is_test=True. Wave 0 just exits cleanly.
  raise NotImplementedError('Wave 2 (06-03): CLI entrypoint wiring')
