r'''Notifier — HTML email I/O hex (package).

Owns Resend HTTPS dispatch for the daily signal email. This package was
extracted from the single-file notifier.py in Plan 27-12 to enforce the
project's <500 LOC-per-file convention. Public API + monkeypatch-target
surface preserved by re-exports below.

Public API (D-01):
  compose_email_subject(state, old_signals, is_test=False) -> str
  compose_email_body(state, old_signals, now, *, from_addr) -> str
  send_daily_email(state, old_signals, now, is_test=False) -> SendStatus
  send_crash_email(exc, state_summary, now=None) -> SendStatus
  send_magic_link_email(to_email, link, action, expires_at) -> SendStatus
  send_stop_alert_email(transitions, dashboard_url) -> bool

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. Peer of state_manager,
data_fetcher, dashboard. Must NOT import signal_engine, sizing_engine,
data_fetcher, main, dashboard, numpy, pandas, yfinance. AST blocklist
in tests/test_signal_engine.py::TestDeterminism enforces this.

Allowed imports (D-01 allowlist): stdlib (html, json, logging, os, time,
tempfile, datetime, pathlib, re) + pytz + requests (Resend HTTPS) +
state_manager (load_state convenience CLI path) + system_params +
pnl_engine (Phase 27 #7 entry-side cost helper).

XSS posture: every dynamic value flows through html.escape(value,
quote=True) at leaf render site (Phase 5 D-15 precedent). Inline
style='...' on every coloured span — NO CSS classes, NO <style> block.

Never-crash posture (D-13, NOTF-07, NOTF-08): every send_*_email
catches every Exception, logs at WARNING with [Email] prefix, returns
SendStatus(ok=False) (or False for legacy stop-alert API).
'''
# Public API re-exports from dispatch (orchestrators)
# Same reasoning for `os` — some tests reference `notifier.os` (e.g.
# environment-variable monkeypatch contexts). Bind it explicitly.
import os  # noqa: F401,E402 — re-export for legacy test compat

# Phase 27 #5: HTTP_TIMEOUT_S re-exported via system_params indirection
# (some tests import it via `from notifier import HTTP_TIMEOUT_S` historically).
from system_params import HTTP_TIMEOUT_S  # noqa: F401 — re-export

# Crash-path re-exports (Plan 27-11)
from .crash_path import (
  _SECRET_PATTERNS_PHASE27_11,
  _build_last_crash_payload,
  _redact_secrets_in_text,
  _resolve_last_crash_path,
  _write_last_crash,
)
from .dispatch import (
  send_backup_stale_email,
  send_crash_email,
  send_daily_email,
  send_magic_link_email,
  send_stop_alert_email,
)

# Public API re-exports from formatters (compose_email_subject is here)
from .formatters import (
  _closed_position_for_instrument_on,
  _compute_trail_stop_email,
  _compute_unrealised_pnl_email,
  _detect_signal_changes,
  _extract_last_close,
  _extract_signal_as_of,
  _extract_signal_int,
  _fmt_currency_email,
  _fmt_em_dash_email,
  _fmt_instrument_display_email,
  _fmt_last_updated_email,
  _fmt_percent_signed_email,
  _fmt_percent_unsigned_email,
  _fmt_pnl_with_colour_email,
  compose_email_subject,
)

# Public API re-exports from templates (compose_email_body lives here)
from .templates import (
  _has_critical_banner,
  _render_footer_email,
  _render_header_email,
  _render_hero_card_email,
  compose_email_body,
)

# Alert + magic-link template re-exports
from .templates_alerts import (
  _build_alert_subject,
  _format_expires_awst,
  _render_alert_email_html,
  _render_alert_email_text,
  _render_magic_link_html,
  _render_magic_link_text,
)

# Per-section renderer re-exports (templates_sections)
from .templates_sections import (
  _render_action_required_email,
  _render_closed_trades_email,
  _render_positions_email,
  _render_signal_status_email,
  _render_todays_pnl_email,
)

# Transport re-exports — public + monkeypatch-target preservation
# Monkeypatch-target preservation: tests do
# `monkeypatch.setattr('notifier.requests.post', ...)` which requires
# `notifier.requests` to resolve to the requests module. transport.py
# `import requests` makes it a transport attribute; we re-bind here at the
# package root so the legacy `notifier.requests.post` path stays live.
from .transport import (
  _RESEND_BACKOFF_S,
  _RESEND_RETRIES,
  _RESEND_RETRY_EXCEPTIONS,
  ResendError,
  SendStatus,
  _atomic_write_html,
  _post_to_resend,
  _resolve_email_to_or_skip,
  requests,  # noqa: F401 — monkeypatch target
)

# FIFO bound helper (Plan 27-12)
from .warnings_fifo import enforce_fifo_bound

__all__ = [
  # =========================================================================
  # Public API — daily email + crash + magic-link + stop-alert
  # =========================================================================
  'compose_email_body',
  'compose_email_subject',
  'send_crash_email',
  'send_daily_email',
  'send_magic_link_email',
  'send_stop_alert_email',
  # =========================================================================
  # Public types
  # =========================================================================
  'ResendError',
  'SendStatus',
  # =========================================================================
  # Monkeypatch + helper surface used by tests/test_notifier.py and
  # tests/test_crash_email_fallback.py — every name in this block is a
  # documented re-export (intentional F401 suppression via __all__).
  # =========================================================================
  '_RESEND_BACKOFF_S',
  '_RESEND_RETRIES',
  '_RESEND_RETRY_EXCEPTIONS',
  '_SECRET_PATTERNS_PHASE27_11',
  '_atomic_write_html',
  '_build_last_crash_payload',
  '_closed_position_for_instrument_on',
  '_compute_trail_stop_email',
  '_compute_unrealised_pnl_email',
  '_detect_signal_changes',
  '_extract_last_close',
  '_extract_signal_as_of',
  '_extract_signal_int',
  '_fmt_currency_email',
  '_fmt_em_dash_email',
  '_fmt_instrument_display_email',
  '_fmt_last_updated_email',
  '_fmt_percent_signed_email',
  '_fmt_percent_unsigned_email',
  '_fmt_pnl_with_colour_email',
  '_format_expires_awst',
  '_has_critical_banner',
  '_post_to_resend',
  '_redact_secrets_in_text',
  '_render_action_required_email',
  '_render_alert_email_html',
  '_render_alert_email_text',
  '_render_closed_trades_email',
  '_render_footer_email',
  '_render_header_email',
  '_render_hero_card_email',
  '_render_magic_link_html',
  '_render_magic_link_text',
  '_render_positions_email',
  '_render_signal_status_email',
  '_render_todays_pnl_email',
  '_resolve_email_to_or_skip',
  '_resolve_last_crash_path',
  '_write_last_crash',
  '_build_alert_subject',
  # =========================================================================
  # FIFO helper (Plan 27-12)
  # =========================================================================
  'enforce_fifo_bound',
  # =========================================================================
  # Monkeypatch target — `notifier.requests.post`
  # =========================================================================
  'requests',
  # =========================================================================
  # Re-exported for compat — `notifier.HTTP_TIMEOUT_S` legacy access
  # =========================================================================
  'HTTP_TIMEOUT_S',
  # =========================================================================
  # Module re-export — some tests reference `notifier.os` for env-var
  # monkeypatching context.
  # =========================================================================
  'os',
]


# =========================================================================
# CLI entrypoint — `python -m notifier`
# =========================================================================
# Operator-only preview: loads current state.json, sends [TEST]-prefixed
# email with no baseline. If RESEND_API_KEY unset, writes last_email.html
# (NOTF-08) and exits 0.

def _cli_main() -> int:
  import logging
  from datetime import datetime as _dt

  import pytz as _pytz

  from state_manager import load_state

  # IN-03: force=True overrides any prior basicConfig (e.g. from a host
  # process that imported the package). Without force=True the call is a
  # silent no-op when logging was already configured, so the CLI's INFO
  # emits never appear.
  logging.basicConfig(level=logging.INFO, format='%(message)s', force=True)
  state = load_state()
  old_signals: dict = {'^AXJO': None, 'AUDUSD=X': None}
  now = _dt.now(_pytz.timezone('Australia/Perth'))
  status = send_daily_email(state, old_signals, now, is_test=True)
  return 0 if status.ok else 1


if __name__ == '__main__':
  import sys
  sys.exit(_cli_main())
