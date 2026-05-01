"""Phase 23 — web routes for /backtest report + history + override form.

Routes (CONTEXT D-12):
  GET  /backtest              — latest report from .planning/backtests/*.json (sorted by mtime desc)
  GET  /backtest?history=true — D-06 table + 10-run overlay chart
  GET  /backtest?run=<file>   — specified report (path-traversal guarded per RESEARCH §Pattern 5)
  POST /backtest/run          — operator override form (D-14)

Auth: Phase 16.1 cookie-session middleware gates all paths uniformly. No per-route auth code.
Hex tier: adapter — imports backtest/*, FastAPI, system_params, web.middleware (transitively).
        Does NOT import signal_engine, sizing_engine directly (those go through backtest.simulator).
"""
from __future__ import annotations
import os
import re
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

_LOG_PREFIX = '[Web]'  # web layer keeps [Web]; CLI uses [Backtest]
_BACKTEST_DIR = Path('.planning/backtests')
_SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9._-]+\.json$')


def _resolve_safe_backtest_path(filename: str) -> Path:
  """Two-layer defence: regex gate + os.listdir whitelist (RESEARCH §Pattern 5).

  Raises ValueError on any path-traversal attempt or unknown filename.
  """
  raise NotImplementedError('Phase 23 Wave 2 Plan 06 — to be implemented')


async def get_backtest(request: Request) -> HTMLResponse:
  raise NotImplementedError('Phase 23 Wave 2 Plan 06 — to be implemented')


async def post_backtest_run(
  request: Request,
  initial_account_aud: float = Form(...),
  cost_spi_aud: float = Form(...),
  cost_audusd_aud: float = Form(...),
) -> RedirectResponse:
  raise NotImplementedError('Phase 23 Wave 2 Plan 06 — to be implemented')


def register(app: FastAPI) -> None:
  """Mount Phase 23 routes; called from web/app.py:create_app()."""
  app.add_api_route('/backtest', get_backtest, methods=['GET'])
  app.add_api_route('/backtest/run', post_backtest_run, methods=['POST'])
