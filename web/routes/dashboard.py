'''GET / — Phase 13 WEB-05 + D-07..D-11 + Phase 14 REVIEWS HIGH #4.

Serves the v1.0 dashboard.html behind shared-secret auth. Regenerates the
file lazily when state.json has been written more recently than the cached
dashboard.html. Never crashes — render failure logs WARN and serves the
stale on-disk copy. First-run before any signal run has rendered → 503
plain-text "dashboard not ready".

Phase 14 Plan 14-04 Task 5 (REVIEWS HIGH #4):
  The on-disk dashboard.html (rendered by main.run_daily_check via Plan 14-05)
  emits hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}' with a
  literal placeholder. This handler reads the bytes, substitutes the
  placeholder with the actual env-var value at request time, and returns
  the patched bytes. The disk file never carries the real secret.

  Threat T-14-15 (auth-secret leak via on-disk dashboard.html cache) is
  MITIGATED by this placeholder-substitution discipline. Tests in
  tests/test_web_dashboard.py::TestAuthSecretPlaceholderSubstitution lock
  the discipline via three assertions.

  ?fragment=position-group-{instrument} query param returns ONLY that
  tbody's inner HTML (used by the per-tbody listener wired in Plan 14-05
  for HX-Trigger refresh on positions-changed events).

Contract (CONTEXT.md 2026-04-25):
  D-07: GET / serves dashboard.html via Response (NOT FileResponse — we now
        modify content per request to substitute the auth-secret placeholder;
        FileResponse streams unmodified bytes). Conditional-GET semantics
        are sacrificed for auth-secret hygiene.
  D-08: Staleness = os.stat(state.json).st_mtime_ns > os.stat(dashboard.html).st_mtime_ns
        — strict greater-than. Both files use atomic tempfile+replace
        (Phase 3 + Phase 5), so mtime semantics are reliable.
  D-09: Cached dashboard.html lives at repo root (matches existing
        dashboard.render_dashboard default out_path).
  D-10: Never-crash. render_dashboard exception → log WARN + serve stale
        on-disk copy (200). Missing dashboard.html (first-run) → 503
        plain-text "dashboard not ready".
  D-11: Concurrency posture. workers=1 (Phase 11) means two concurrent
        GET /'s both noticing staleness double-render harmlessly. State
        read is stable within the window. No file locking needed.

SC-2 lock (REVIEWS MEDIUM #3):
  The handler regenerates BEFORE serving so the response streams the
  newly-written + secret-substituted bytes — not a pre-regen snapshot.

Architecture (CLAUDE.md hex-lite + Phase 10 D-15 + Phase 13 D-07 extension):
  web/routes/ is an adapter hex.
  Allowed: fastapi, starlette, stdlib, dashboard (Phase 13 D-07 promotion —
           render_dashboard is now an allowed adapter-to-adapter import),
           state_manager (Phase 11 D-15 read-only).
  Forbidden: signal_engine, sizing_engine, system_params, notifier, main.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

  Both state_manager AND dashboard imports are LOCAL (inside the handler)
  per Phase 11 C-2 / Phase 13 D-07. Module-top imports of either would
  fail tests/test_web_healthz.py::TestWebHexBoundary::test_web_adapter_imports_are_local_not_module_top.

Log prefix: [Web].
'''
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer

logger = logging.getLogger(__name__)

_DASHBOARD_PATH = 'dashboard.html'  # D-09: repo root, matches dashboard.py default
_STATE_PATH = 'state.json'

# Phase 14 Plan 14-04 Task 5 (REVIEWS HIGH #4): substitute placeholder with
# env secret at request time so on-disk dashboard.html never carries the
# real value. Plan 14-05 emits the literal placeholder in hx-headers.
_PLACEHOLDER = b'{{WEB_AUTH_SECRET}}'

# Phase 16.1 — placeholders for the per-request auth-widget swap (Sign Out
# button vs session note). Mirrors the Phase 14 {{WEB_AUTH_SECRET}} pattern.
_SIGNOUT_PLACEHOLDER = b'{{SIGNOUT_BUTTON}}'
_SESSION_NOTE_PLACEHOLDER = b'{{SESSION_NOTE}}'

# Phase 17 Plan 17-01 — trace-panel open-state cookie.
# The unsigned UI-preference cookie `tsi_trace_open` carries a comma-separated
# list of instrument keys whose <details> should be pre-expanded. The allowlist
# prevents arbitrary attribute injection into the substituted HTML.
_VALID_TRACE_INSTRUMENT_KEYS: frozenset = frozenset({'SPI200', 'AUDUSD'})
_TRACE_OPEN_PLACEHOLDER_SPI200 = b'{{TRACE_OPEN_SPI200}}'
_TRACE_OPEN_PLACEHOLDER_AUDUSD = b'{{TRACE_OPEN_AUDUSD}}'


def _is_stale() -> bool:
  '''D-08: state.json mtime > dashboard.html mtime means regen needed.

  Returns True if dashboard.html is missing (caller handles via os.path.exists).
  Returns True if state.json is newer than dashboard.html (regen path).
  Returns False if dashboard.html is fresh relative to state.json.
  Returns False if state.json itself is missing (no state to render from).
  '''
  try:
    html_mtime = os.stat(_DASHBOARD_PATH).st_mtime_ns
  except FileNotFoundError:
    return True  # missing dashboard.html — caller handles 503
  try:
    state_mtime = os.stat(_STATE_PATH).st_mtime_ns
  except FileNotFoundError:
    return False  # no state.json — serve whatever dashboard.html is
  return state_mtime > html_mtime


def register(app: FastAPI) -> None:
  '''Register GET / on the given FastAPI instance.'''

  # Phase 16.1: build a session serializer at register-time so the per-request
  # cookie validator is just a signature check (the constructor is non-trivial).
  _session_secret = os.environ.get('WEB_AUTH_SECRET', '')
  _session_serializer = URLSafeTimedSerializer(
    _session_secret, salt='tsi-session-cookie',
  )

  def _is_cookie_session(request: Request) -> bool:
    '''Validate tsi_session cookie via itsdangerous. Returns True iff the
    cookie is present and valid (not expired, signed correctly).
    '''
    token = request.cookies.get('tsi_session')
    if not token:
      return False
    try:
      _session_serializer.loads(token, max_age=43200)
      return True
    except SignatureExpired:
      return False
    except BadSignature:
      return False

  def _resolve_trace_open(request: Request) -> frozenset:
    '''Read tsi_trace_open cookie and return allowlisted instrument keys.

    The cookie value is a comma-separated list of instrument keys
    (e.g. "SPI200,AUDUSD"). Only keys in _VALID_TRACE_INSTRUMENT_KEYS are
    returned — all other values are discarded. Returns empty frozenset when
    cookie absent or contains no valid keys.
    '''
    raw = request.cookies.get('tsi_trace_open', '')
    if not raw:
      return frozenset()
    parts = {p.strip() for p in raw.split(',') if p.strip()}
    return frozenset(parts & _VALID_TRACE_INSTRUMENT_KEYS)

  @app.get('/')
  def get_dashboard(request: Request, fragment: str | None = None):
    '''Phase 13 GET / + Phase 14 REVIEWS HIGH #4 (placeholder substitution).

    The on-disk dashboard.html (rendered by main.run_daily_check via
    Plan 14-05) emits the literal placeholder {{WEB_AUTH_SECRET}} inside
    the form's hx-headers attribute. This handler reads the bytes,
    substitutes the placeholder with the actual env-var value at request
    time, and returns the patched bytes. The disk file never contains
    the real secret.

    ?fragment=position-group-{instrument}: returns ONLY that tbody's
    inner HTML (used by Plan 14-05's per-tbody listener for partial
    refresh on positions-changed events).
    '''
    # Phase 15 CALC-03 + REVIEWS L-1: forward-stop fragment — EXACT match.
    # Handled BEFORE the dashboard.html file-read path because this fragment
    # does not need the on-disk dashboard.html to exist (it reads state.json
    # directly via load_state). Degenerate Z returns em-dash, never 4xx.
    if fragment == 'forward-stop':
      import html as _html
      import math as _math

      from dashboard import _fmt_currency, _fmt_em_dash  # LOCAL — C-2
      from sizing_engine import get_trailing_stop  # LOCAL — C-2
      from state_manager import load_state as _ls  # LOCAL — C-2

      instrument = request.query_params.get('instrument', '')
      z_raw = request.query_params.get('z', '')
      span_id_suffix = _html.escape(instrument, quote=True) if instrument else 'unknown'

      def _em_dash_response():
        body = f'<span id="forward-stop-{span_id_suffix}-w">{_fmt_em_dash()}</span>'
        return Response(content=body.encode('utf-8'), media_type='text/html; charset=utf-8')

      try:
        z = float(z_raw)
      except (ValueError, TypeError):
        return _em_dash_response()
      if not _math.isfinite(z) or z <= 0:
        return _em_dash_response()

      try:
        state = _ls()
      except Exception:
        return _em_dash_response()

      pos = state.get('positions', {}).get(instrument)
      if pos is None:
        return _em_dash_response()

      synth = dict(pos)
      direction = synth.get('direction', 'LONG')
      if direction == 'LONG':
        peak = synth.get('peak_price') or synth.get('entry_price', 0.0)
        synth['peak_price'] = max(peak, z)
      else:
        trough = synth.get('trough_price') or synth.get('entry_price', 0.0)
        synth['trough_price'] = min(trough, z)

      try:
        w = get_trailing_stop(synth, 0.0, 0.0)
      except Exception:
        return _em_dash_response()

      if not _math.isfinite(w):
        w_html = _fmt_em_dash()
      else:
        w_html = _html.escape(_fmt_currency(w), quote=True)

      body = f'<span id="forward-stop-{span_id_suffix}-w">{w_html}</span>'
      return Response(content=body.encode('utf-8'), media_type='text/html; charset=utf-8')

    # D-07 / Phase 11 C-2: local imports preserve hex boundary.
    from dashboard import render_dashboard
    from state_manager import load_state

    try:
      if _is_stale():
        render_dashboard(load_state())
    except Exception as exc:  # noqa: BLE001 — D-10 never-crash
      logger.warning(
        '[Web] dashboard regen failed, serving stale: %s: %s',
        type(exc).__name__,
        exc,
      )

    if not os.path.exists(_DASHBOARD_PATH):  # D-10: first-run case
      return PlainTextResponse(
        content='dashboard not ready',
        status_code=503,
        media_type='text/plain; charset=utf-8',
      )

    # Phase 14 Plan 14-04 Task 5 (REVIEWS HIGH #4): substitute placeholder
    # with env secret at request time so on-disk dashboard.html never
    # carries the real value.
    content = Path(_DASHBOARD_PATH).read_bytes()
    secret = os.environ.get('WEB_AUTH_SECRET', '').encode('utf-8')
    content = content.replace(_PLACEHOLDER, secret)

    # Phase 16.1: per-request auth widget — Sign Out button (cookie session)
    # vs session note (header auth). LOCAL import preserves hex boundary
    # (Phase 11 C-2; web/routes/dashboard.py is allowed to import dashboard
    # per Phase 13 D-07).
    from dashboard import _render_session_note, _render_signout_button

    if _is_cookie_session(request):
      content = content.replace(
        _SIGNOUT_PLACEHOLDER,
        _render_signout_button().encode('utf-8'),
      )
      content = content.replace(_SESSION_NOTE_PLACEHOLDER, b'')
    else:
      content = content.replace(_SIGNOUT_PLACEHOLDER, b'')
      content = content.replace(
        _SESSION_NOTE_PLACEHOLDER,
        _render_session_note().encode('utf-8'),
      )

    # Phase 17 Plan 17-01: substitute tsi_trace_open cookie into
    # <details data-instrument="X"{{TRACE_OPEN_X}}> placeholders.
    # ' open' pre-expands the <details> element; empty string leaves it closed.
    trace_open = _resolve_trace_open(request)
    content = content.replace(
      _TRACE_OPEN_PLACEHOLDER_SPI200,
      b' open' if 'SPI200' in trace_open else b'',
    )
    content = content.replace(
      _TRACE_OPEN_PLACEHOLDER_AUDUSD,
      b' open' if 'AUDUSD' in trace_open else b'',
    )

    if fragment is not None:
      # Extract the tbody whose id matches `fragment`. Returns inner HTML only.
      # Quick-and-dirty regex (string-search) — dashboard markup is
      # server-controlled, not user input, so regex against rendered HTML
      # is safe (re.escape on the user-supplied fragment value blocks any
      # regex-injection attempt).
      m = re.search(
        rb'<tbody id="' + re.escape(fragment.encode('utf-8')) + rb'">(.*?)</tbody>',
        content, re.DOTALL,
      )
      if not m:
        return Response(
          content=b'', status_code=404,
          media_type='text/html; charset=utf-8',
        )
      return Response(
        content=m.group(1),
        media_type='text/html; charset=utf-8',
      )

    return Response(
      content=content,
      media_type='text/html; charset=utf-8',
    )
