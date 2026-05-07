'''Header component implementation.'''

import html
import json
import os
from datetime import datetime
from pathlib import Path

from dashboard_renderer.context import RenderContext
from dashboard_renderer.formatters import (
  _compute_next_awst_0800,
  _derive_status_dot_class,
  _format_countdown_text,
)
from system_params import LAST_CRASH_FILE, STATE_FILE


def _resolve_last_crash_path() -> Path:
  '''Phase 27 #15 (Plan 27-11): mirror notifier._resolve_last_crash_path.

  Honors the LAST_CRASH_PATH env-var override so an operator-configured
  location is consistent across the writer (notifier) and the reader
  (dashboard banner). Defined locally rather than imported to keep
  dashboard_renderer free of a notifier import (hex boundary D-01:
  renderer never imports notifier).
  '''
  override = os.environ.get('LAST_CRASH_PATH', '').strip()
  if override:
    return Path(override)
  return Path(STATE_FILE).parent / LAST_CRASH_FILE


def render_last_crash_banner() -> str:
  '''Phase 27 #15 (Plan 27-11): surface last_crash.json on the dashboard.

  Returns the empty string when no last_crash.json file exists at the
  configured path. Otherwise renders a single ``<div class="last-crash-banner">``
  block with timestamp + exception type + exception message — every
  interpolation flows through ``html.escape(value, quote=True)`` per the
  Plan 27-08 XSS contract.

  Read failure (FileNotFoundError, JSONDecodeError, OSError) is silent —
  defensive at the trust boundary (a malformed file MUST NOT crash the
  dashboard render).
  '''
  path = _resolve_last_crash_path()
  try:
    data = json.loads(path.read_text())
  except (FileNotFoundError, json.JSONDecodeError, OSError):
    return ''
  if not isinstance(data, dict):
    return ''
  timestamp = html.escape(str(data.get('timestamp_utc', '')), quote=True)
  exc_type = html.escape(str(data.get('exception_type', '')), quote=True)
  exc_msg = html.escape(str(data.get('exception_message', '')), quote=True)
  return (
    '<div class="last-crash-banner" role="alert" aria-live="polite">'
    f'<strong>Last crash:</strong> {timestamp} — '
    f'{exc_type}: {exc_msg}'
    '</div>\n'
  )


def render_status_strip(state: dict, now_awst: datetime) -> str:
  '''Phase 25 D-06/D-07/D-08 + OR-01/OR-02: System Status strip.

  Server-renders last-run timestamp + status dot + next-run countdown placeholder.
  Client-side JS (Plan 02 _AWST_COUNTDOWN_JS) ticks the countdown using
  [data-countdown] attribute. Strip is an HTMX target for auto-refresh at
  08:01 AWST and on visibilitychange.

  Warning text is NOT rendered (T-25-06-01: only count/state, not message).
  '''
  last_run = state.get('last_run')
  dot_class, status_text = _derive_status_dot_class(state, now_awst)
  next_run = _compute_next_awst_0800(now_awst)
  next_run_iso = next_run.isoformat()
  countdown_initial = _format_countdown_text(now_awst, next_run)

  if last_run is None:
    last_run_html = '<span>Awaiting first run</span>'
  else:
    last_run_esc = html.escape(last_run, quote=True)
    last_run_html = (
      f'<time datetime="{last_run_esc}" class="mono">{last_run_esc}</time>'
      f' · {html.escape(status_text, quote=True)}'
    )

  # OR-02: static "08:00 AWST" label is always visible; JS countdown updates
  # only the inner span (ticker portion). This keeps "AWST" in the rendered HTML
  # regardless of countdown magnitude so the AWST-gate grep always passes.
  return (
    '<div id="status-strip" class="status-strip" '
    'hx-get="/status-strip" '
    'hx-trigger="refresh, visibilitychange[document.visibilityState==\'visible\'] from:document" '
    'hx-swap="outerHTML" aria-live="polite">\n'
    f'  <span class="status-dot {dot_class}" aria-hidden="true"></span>\n'
    '  <span class="status-label">Last run</span>\n'
    f'  {last_run_html}\n'
    '  <span class="status-sep"> · </span>\n'
    '  <span class="status-label">Next run</span>\n'
    f'  <span class="next-run">08:00 AWST · '
    f'<span data-countdown="{html.escape(next_run_iso, quote=True)}">'
    f'{html.escape(countdown_initial, quote=True)}</span></span>\n'
    '</div>\n'
  )


def render_header(state: dict, now: datetime, is_cookie_session: bool | None = None) -> str:
  import dashboard as d

  # Phase 26 B1: market-agnostic subtitle. Hardcoded market names ('SPI 200',
  # 'AUD/USD') leaked into market-scoped pages and violated the per-market
  # scoping contract enforced by TestPhase26MarketScoping.
  subtitle = html.escape('Mechanical multi-market trading system', quote=True)
  last_updated = html.escape(d._fmt_last_updated(now), quote=True)
  if is_cookie_session is None:
    auth_widget = '{{SIGNOUT_BUTTON}}{{SESSION_NOTE}}'
  elif is_cookie_session:
    auth_widget = d._render_signout_button()
  else:
    auth_widget = d._render_session_note()

  status_strip = render_status_strip(state, now)
  # Phase 27 #15 (Plan 27-11): silent-crash-dropout fallback. When
  # notifier.send_crash_email's outbound dispatch failed on the prior
  # daily run, last_crash.json carries the redacted crash payload and
  # this banner surfaces it next to the status strip. Empty string when
  # no file exists — banner is opt-in, never empty-shell HTML.
  last_crash_banner = render_last_crash_banner()

  return (
    '<header>\n'
    '  <h1>Trading Signals</h1>\n'
    f'  <p class="subtitle">{subtitle}</p>\n'
    '  <p class="meta">\n'
    '    <span class="label">Last updated</span>\n'
    f'    <span class="value">{last_updated}</span>\n'
    f'    {auth_widget}\n'
    '  </p>\n'
    f'{status_strip}'
    f'{last_crash_banner}'
    '</header>\n'
  )


def render_header_from_context(ctx: RenderContext, is_cookie_session: bool | None = None) -> str:
  return render_header(ctx.state, ctx.now, is_cookie_session=is_cookie_session)
