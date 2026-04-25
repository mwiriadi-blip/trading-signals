'''GET / — Phase 13 WEB-05 + D-07..D-11 — STUB.

Wave 1 stub. Plan 13-05 fills the body (D-07: dashboard.html + mtime-staleness
regen; D-10: 503 first-run; D-11: workers=1 concurrency posture).

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  web/routes/ is an adapter hex.
  Allowed: fastapi, starlette, stdlib, dashboard (Phase 13 D-07 promotion),
           state_manager (Phase 11 D-15 read-only).
  Forbidden: signal_engine, sizing_engine, system_params, notifier, main.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

Log prefix: [Web].
'''
import logging

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)


def register(app: FastAPI) -> None:
  '''Register GET / on the given FastAPI instance — STUB until Plan 13-05.'''

  @app.get('/')
  def get_dashboard():
    # Plan 02 stub: 503 until Plan 13-05 fills the body.
    return PlainTextResponse(
      content='dashboard not ready',
      status_code=503,
      media_type='text/plain; charset=utf-8',
    )
