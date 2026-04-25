'''GET /api/state — Phase 13 WEB-06 + D-12..D-15 — STUB.

Wave 1 stub. Plan 13-04 fills the body (D-12: top-level _* key strip;
D-13: Cache-Control: no-store; D-14: trust load_state recovery;
D-15: compact JSON).

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  web/routes/ is an adapter hex.
  Allowed: fastapi, starlette, stdlib, state_manager (read-only per Phase 10 D-15).
  Forbidden: signal_engine, sizing_engine, system_params, notifier, main, dashboard.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

Log prefix: [Web].
'''
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register(app: FastAPI) -> None:
  '''Register GET /api/state on the given FastAPI instance — STUB until Plan 13-04.'''

  @app.get('/api/state')
  def get_state():
    # Plan 02 stub: 503 until Plan 13-04 fills the body.
    return JSONResponse(
      content={'error': 'not ready'},
      status_code=503,
      headers={'Cache-Control': 'no-store'},
    )
