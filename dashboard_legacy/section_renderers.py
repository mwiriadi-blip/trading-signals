"""dashboard_legacy.section_renderers — small thin-wrap section renderers + equity chart.

Extracted from dashboard.py (Plan 27-14). Most of these forward to dashboard_renderer
components; equity chart contains the inline Chart.js JSON-payload assembly.
"""
import html
import json
from datetime import datetime

from dashboard_renderer.context import RenderContext
from dashboard_renderer.components.footer import render_footer as dr_render_footer
from dashboard_renderer.components.header import render_header as dr_render_header
from dashboard_renderer.components.header import (
    render_header_from_context as dr_render_header_from_context,
)
from dashboard_renderer.components.settings import (
    render_add_market_form as dr_render_add_market_form,
    render_market_test_tab as dr_render_market_test_tab,
    render_settings_tab as dr_render_settings_tab,
)
from dashboard_renderer.components.signals import (
    render_signal_cards as dr_render_signal_cards,
)
from system_params import (
    _COLOR_BORDER,
    _COLOR_LONG,
    _COLOR_TEXT_MUTED,
)


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

def _render_header(
  state: dict, now: datetime, is_cookie_session: bool | None = None,
) -> str:  # noqa: ARG001 — state reserved for future
  '''UI-SPEC §Header — H1 "Trading Signals" + subtitle + Last-updated AWST.

  state is reserved for future use (e.g. surfacing schema_version); the live
  clock render uses the injected `now`. _fmt_last_updated raises ValueError on
  naive datetimes (Pitfall 9 golden-snapshot drift guard).

  Phase 16.1 — `is_cookie_session` 3-way semantics (LEARNING 2026-04-27 hex
  boundary: dashboard.py must NOT decode cookies; the auth signal arrives as
  a primitive bool computed by the caller):
    None  — emit the literal {{SIGNOUT_BUTTON}}{{SESSION_NOTE}} placeholders
            so web/routes/dashboard.py can substitute per request (matches
            the Phase 14 {{WEB_AUTH_SECRET}} pattern). This is what
            main.run_daily_check writes to disk.
    True  — render the Sign Out button inline (test path: direct
            render_dashboard_files(..., is_cookie_session=True)).
    False — render the session note inline (test path: header-auth flow).
  '''
  return dr_render_header(state, now, is_cookie_session=is_cookie_session)

def _render_header_ctx(
  ctx: RenderContext,
  is_cookie_session: bool | None = None,
) -> str:
  return dr_render_header_from_context(ctx, is_cookie_session=is_cookie_session)

def _render_signal_cards(state: dict, *, active_market: str | None = None) -> str:
  '''UI-SPEC §Signal cards — 2 cards SPI200 + AUDUSD (D-02, DASH-03).

  Per-instrument state['signals'][key] has {signal, signal_as_of, as_of_run,
  last_scalars, last_close}. Empty state (missing key): big "—" chip in
  _COLOR_FLAT + "Signal as of never" + single em-dash scalars line.
  Phase 26 B1: when active_market is set, only that market's card is rendered.
  '''
  return dr_render_signal_cards(state, active_market=active_market)

def _render_settings_tab(state: dict, *, active_market: str | None = None) -> str:
  return dr_render_settings_tab(state, active_market=active_market)


def _render_add_market_form(state: dict) -> str:
  return dr_render_add_market_form(state)


def _render_market_test_tab(state: dict, *, active_market: str | None = None) -> str:
  return dr_render_market_test_tab(state, active_market=active_market)

def _render_footer(strategy_version: str) -> str:
  '''UI-SPEC §Footer disclaimer — "Signal-only system. Not financial advice."

  Phase 22 D-06: appends a small <div class="strategy-version"> line
  showing the active strategy version. The version arrives as a
  primitive str argument from render_dashboard (which calls
  _resolve_strategy_version on the state dict) — preserves the
  hex-boundary rule that dashboard.py never imports
  system_params.STRATEGY_VERSION (LEARNINGS 2026-04-27).
  '''
  return dr_render_footer(strategy_version)

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
  from system_params import _decimal_default
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
    '                         callback: (v) => "$" + v.toLocaleString() }},\n'
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
