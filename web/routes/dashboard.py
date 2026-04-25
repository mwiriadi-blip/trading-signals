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

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response
from pathlib import Path

logger = logging.getLogger(__name__)

_DASHBOARD_PATH = 'dashboard.html'  # D-09: repo root, matches dashboard.py default
_STATE_PATH = 'state.json'

# Phase 14 Plan 14-04 Task 5 (REVIEWS HIGH #4): substitute placeholder with
# env secret at request time so on-disk dashboard.html never carries the
# real value. Plan 14-05 emits the literal placeholder in hx-headers.
_PLACEHOLDER = b'{{WEB_AUTH_SECRET}}'


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

  @app.get('/')
  def get_dashboard(fragment: str | None = None):
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
