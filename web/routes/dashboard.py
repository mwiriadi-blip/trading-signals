'''GET / — Phase 13 WEB-05 + D-07..D-11.

Serves the v1.0 dashboard.html behind shared-secret auth. Regenerates the
file lazily when state.json has been written more recently than the cached
dashboard.html. Never crashes — render failure logs WARN and serves the
stale on-disk copy. First-run before any signal run has rendered → 503
plain-text "dashboard not ready".

Contract (CONTEXT.md 2026-04-25):
  D-07: GET / serves dashboard.html via FileResponse; regenerates only when
        state.json mtime > dashboard.html mtime. FileResponse adds
        Content-Length, Last-Modified, ETag, conditional GET (304) automatically.
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
  The handler regenerates BEFORE serving so the FileResponse streams the
  newly-written bytes — not a pre-regen snapshot. Locked by
  tests/test_web_dashboard.py::TestStaleness::test_stale_state_triggers_regen_and_serves_regenerated_bytes
  which asserts the response body byte-equals the regenerated file content.

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

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse

logger = logging.getLogger(__name__)

_DASHBOARD_PATH = 'dashboard.html'  # D-09: repo root, matches dashboard.py default
_STATE_PATH = 'state.json'


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
  def get_dashboard():
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

    # D-07: FileResponse handles ETag/Last-Modified/Content-Length/conditional-GET.
    # SC-2: regen (above) completes BEFORE this FileResponse is constructed,
    # so the served bytes reflect the freshly-regenerated file content.
    return FileResponse(
      _DASHBOARD_PATH,
      media_type='text/html; charset=utf-8',
    )
