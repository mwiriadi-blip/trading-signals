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
  _fmt_last_updated,
  _format_countdown_text,
)
from system_params import (
  LAST_CRASH_FILE,
  STATE_FILE,
  _COLOR_BORDER,
  _COLOR_LONG,
  _COLOR_TEXT_MUTED,
  _decimal_default,
)


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

  # OR-02: static "08:00 AEST" label is always visible; JS countdown updates
  # only the inner span (ticker portion). This keeps "AEST" in the rendered HTML
  # regardless of countdown magnitude so the AEST-gate grep always passes.
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
    f'  <span class="next-run">08:00 AEST · '
    f'<span data-countdown="{html.escape(next_run_iso, quote=True)}">'
    f'{html.escape(countdown_initial, quote=True)}</span></span>\n'
    '</div>\n'
  )


def render_header(state: dict, now: datetime, is_cookie_session: bool | None = None) -> str:
  # Phase 26 B1: market-agnostic subtitle. Hardcoded market names ('SPI 200',
  # 'AUD/USD') leaked into market-scoped pages and violated the per-market
  # scoping contract enforced by TestPhase26MarketScoping.
  subtitle = html.escape('Mechanical multi-market trading system', quote=True)
  last_updated = html.escape(_fmt_last_updated(now), quote=True)
  if is_cookie_session is None:
    auth_widget = '{{SIGNOUT_BUTTON}}{{SESSION_NOTE}}'
  elif is_cookie_session:
    auth_widget = _render_signout_button()
  else:
    auth_widget = _render_session_note()

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


# =========================================================================
# Phase 32 Plan 01: unique functions ported from dashboard_legacy/section_renderers.py
# Byte-identical bodies; imports adjusted to canonical dashboard_renderer homes.
# =========================================================================

def _render_signout_button() -> str:
  '''Phase 16.1 UI-SPEC §Surface 3: Sign Out button for cookie-session users.

  Form POSTs to /logout (the auth.py middleware lets /logout through via
  PUBLIC_PATHS, then web/routes/login.py::post_logout clears the cookie
  with attrs matching creation per global LEARNING).
  '''
  return (
    '<form method="POST" action="/logout" class="signout-form">'
    '<button type="submit" class="btn-signout" '
    'aria-label="Sign out of Trading Signals">Sign out</button>'
    '</form>'
  )


def _render_session_note() -> str:
  '''Phase 16.1 UI-SPEC §Surface 4 (E-01 generalised — Basic Auth removed).

  Shown in the header when the request did NOT carry a valid tsi_session
  cookie (i.e. the operator is authenticated via X-Trading-Signals-Auth
  header — usually a curl/script). Renders the no-op "close tabs" hint
  since there's no cookie to clear server-side.
  '''
  return (
    '<p class="session-note">'
    'Signed in via header — close browser tabs to sign out.'
    '</p>'
  )


def _distinct_equity_tuples(equity_history: list) -> list:
  '''Phase 25 D-11: dedupe (date, equity) tuples; chart hides until >=5 distinct.

  Three identical {date: '2026-04-23', equity: 100000.0} entries produce ONE
  distinct entry, not three. Only dicts with parseable date+equity are kept.
  '''
  seen: set = set()
  distinct = []
  for row in equity_history:
    if not isinstance(row, dict):
      continue
    try:
      key = (row['date'], float(row['equity']))
    except (KeyError, TypeError, ValueError):
      continue
    if key not in seen:
      seen.add(key)
      distinct.append(row)
  return distinct


def _render_equity_chart_container(state: dict) -> str:
  '''DASH-04 / CONTEXT D-11 / UI-SPEC §Chart Component. Category x-axis.

  JSON payload injection defence (Pitfall 1): json.dumps with
  ensure_ascii=True (forces \\uXXXX for U+2028/U+2029 line separators —
  some JS parsers treat those as line terminators inside string
  literals, breaking the embedded payload) plus a `</` -> `<\\/` scrub
  for the <script>-close vector. Phase 27 WR-07 hardening.

  D-11 empty state: chart hidden until >=5 distinct (date, equity) tuples.
  Three identical points still count as one distinct point (D-11 spec).
  '''
  equity_history = state.get('equity_history', []) or []
  distinct = _distinct_equity_tuples(equity_history)
  if len(distinct) < 5:
    return (
      '<section aria-labelledby="heading-equity">\n'
      '  <h2 id="heading-equity">Equity curve</h2>\n'
      '  <div class="empty-state">'
      'Chart appears once 5 daily equity points have been recorded.'
      '</div>\n'
      '</section>\n'
    )
  # Build labels + data from the deduped distinct list (NOT raw equity_history).
  # JSON-serialise with <script>-close injection defence (Pitfall 1) and
  # byte-stable dict ordering (Pitfall 2).
  labels = [row['date'] for row in distinct]
  # Phase 27 #1: equity values may be Decimal post-Plan-27-01 (state_manager
  # round-trip path). float(...) at the boundary is the canonical coercion
  # before json.dumps; the default=_decimal_default kwarg below is a
  # belt-and-suspenders fallback for any nested Decimal that survived
  # this point (e.g., a future row shape with Decimal sub-fields).
  data = [float(row['equity']) for row in distinct]
  payload = json.dumps(
    {'labels': labels, 'data': data},
    # Phase 27 WR-07: ensure_ascii=True forces \uXXXX escaping for
    # U+2028 / U+2029 (JS line-terminator characters that some parsers
    # treat as ending a string literal). The <script>-close defence
    # below catches the </ vector; ensure_ascii catches the line-sep
    # vector. Both are required for embedded-script JSON safety.
    ensure_ascii=True,
    sort_keys=True,    # Pitfall 2: byte-stable dict order
    allow_nan=False,   # G-1 reviews: stray NaN must fail loudly rather than
                       # emit invalid JSON that Chart.js renders as a blank line
    default=_decimal_default,  # Phase 27 #1 (truth #7): Decimal-safe encoder
  ).replace('</', '<\\/')
  return (
    '<section aria-labelledby="heading-equity">\n'
    '  <h2 id="heading-equity">Equity Curve</h2>\n'
    '  <div class="chart-container">\n'
    '    <canvas id="equityChart" '
    'aria-label="Account equity line chart over time" role="img"></canvas>\n'
    '  </div>\n'
    '  <script>\n'
    '    (function() {\n'
    f'      const payload = {payload};\n'
    '      new Chart(document.getElementById("equityChart"), {\n'
    '        type: "line",\n'
    '        data: {\n'
    '          labels: payload.labels,\n'
    '          datasets: [{\n'
    '            label: "Account equity",\n'
    '            data: payload.data,\n'
    f'            borderColor: "{_COLOR_LONG}",\n'
    f'            backgroundColor: "{_COLOR_LONG}",\n'
    '            fill: false,\n'
    '            tension: 0.1,\n'
    '            borderWidth: 2,\n'
    '            pointRadius: 0,\n'
    '            pointHoverRadius: 4\n'
    '          }]\n'
    '        },\n'
    '        options: {\n'
    '          scales: {\n'
    f'            x: {{ type: "category",\n'
    f'               ticks: {{ color: "{_COLOR_TEXT_MUTED}", maxTicksLimit: 10 }},\n'
    f'               grid: {{ color: "{_COLOR_BORDER}" }} }},\n'
    f'            y: {{ ticks: {{ color: "{_COLOR_TEXT_MUTED}",\n'
    '                         callback: (v) => "$" + v.toLocaleString() },\n'
    f'               grid: {{ color: "{_COLOR_BORDER}" }} }}\n'
    '          },\n'
    '          plugins: {\n'
    '            legend: { display: false },\n'
    '            tooltip: { callbacks: { label: (ctx) => "$" + ctx.parsed.y.toLocaleString() } }\n'
    '          },\n'
    '          maintainAspectRatio: false,\n'
    '          responsive: true\n'
    '        }\n'
    '      });\n'
    '    })();\n'
    '  </script>\n'
    '</section>\n'
  )
