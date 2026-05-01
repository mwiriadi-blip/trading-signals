"""Phase 23 — web routes for /backtest report + history + override form.

Routes (CONTEXT D-12):
  GET  /backtest              — latest report (sorted by mtime desc); empty-state if none
  GET  /backtest?history=true — D-06 table + 10-run overlay chart
  GET  /backtest?run=<file>   — specified report; path-traversal guarded (RESEARCH §Pattern 5)
  POST /backtest/run          — operator override form (D-14)

Auth: Phase 16.1 cookie-session middleware gates all paths uniformly. No per-route auth code.
Hex tier: adapter — imports backtest/*, FastAPI, web layer.
        Does NOT import signal_engine, sizing_engine directly (those go through backtest.simulator).

Performance budget (CONTEXT D-14 + D-18):
  POST /backtest/run is synchronous and must complete within uvicorn's 60s
  default worker timeout. Mitigations:
    1. Parquet cache (D-01) — first run after a fresh strategy is the only
       cache miss; subsequent overrides reuse the existing parquet file
       (sub-second fetch).
    2. Vectorized simulator (RESEARCH §Pattern 2) — 5y × 2 instruments
       benchmarks at ~120ms; 10x droplet penalty still <2s.
    3. If real-world runs exceed 30s on the droplet, defer the async-job
       pattern to v1.3+ per CONTEXT D-14.

  At fail-time: uvicorn returns 504; operator should re-run from CLI
  (no timeout) or split work via --refresh once. Manual droplet timing
  verification is the absolute bound (VALIDATION.md Manual-Only).
"""
from __future__ import annotations
import html
import json
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from backtest.cli import RunArgs, run_backtest
from backtest.data_fetcher import DataFetchError, ShortFrameError
from backtest.render import render_history, render_report

logger = logging.getLogger(__name__)

_LOG_PREFIX = '[Web]'  # web layer keeps [Web]; CLI uses [Backtest]
_BACKTEST_DIR = Path('.planning/backtests')
_SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9._-]+\.json$')


# ---------- Path-traversal defence (T-23-traversal) ----------

def _resolve_safe_backtest_path(filename: str, backtest_dir: Path | None = None) -> Path:
  """Two-layer defence (RESEARCH §Pattern 5):
    1. Regex `^[a-zA-Z0-9._-]+\\.json$` rejects `..`, `/`, absolute paths
    2. os.listdir() whitelist confirms file is in canonical directory

  Raises ValueError on any traversal attempt or unknown filename.
  """
  if backtest_dir is None:
    backtest_dir = _BACKTEST_DIR
  if not isinstance(filename, str) or not _SAFE_FILENAME_RE.match(filename):
    raise ValueError(f'invalid backtest filename: {filename!r}')
  try:
    available = set(os.listdir(backtest_dir))
  except FileNotFoundError:
    raise ValueError(f'backtest directory does not exist: {backtest_dir}')
  if filename not in available:
    raise ValueError(f'backtest file not found: {filename!r}')
  return backtest_dir / filename


# ---------- Helpers ----------

def _list_reports(backtest_dir: Path | None = None) -> list[Path]:
  """Return existing *.json files sorted by mtime descending. Empty list if none."""
  if backtest_dir is None:
    backtest_dir = _BACKTEST_DIR
  if not backtest_dir.exists():
    return []
  files = [p for p in backtest_dir.iterdir() if p.is_file() and p.suffix == '.json']
  files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
  return files


def _load_report(path: Path) -> dict | None:
  """Load and parse JSON. Returns None on corrupt/truncated files."""
  try:
    data = json.loads(path.read_text())
  except (json.JSONDecodeError, OSError) as exc:
    logger.warning('%s corrupt backtest file %s: %s', _LOG_PREFIX, path.name, exc)
    return None
  data.setdefault('metadata', {})
  data['metadata']['filename'] = path.name
  return data


def _wrap_html(body: str) -> str:
  """Minimal page shell. Production styles inherited from existing dashboard CSS at GET /."""
  return (
    '<!doctype html><html lang="en">'
    '<head><meta charset="utf-8"><title>Backtest Validation</title></head>'
    f'<body>{body}</body></html>'
  )


# ---------- GET /backtest (covers ?history=true and ?run=<file>) ----------

async def get_backtest(request: Request) -> HTMLResponse:
  """CONTEXT D-12 + D-15: cookie-auth-gated by Phase 16.1 middleware (no code here).

  Branches:
    ?run=<filename>     → render specified report (path-traversal guarded)
    ?history=true       → render history view (D-06)
    (no query)          → render latest by mtime; empty-state if none
  """
  params = request.query_params

  # ?run=<filename> branch — strictest first (path-traversal defence)
  run_filename = params.get('run')
  if run_filename:
    try:
      path = _resolve_safe_backtest_path(run_filename)
    except ValueError as exc:
      logger.warning('%s rejected ?run= traversal attempt: %s', _LOG_PREFIX, exc)
      return HTMLResponse(
        content=_wrap_html(
          '<section class="error"><h1>Invalid backtest filename.</h1>'
          '<p><a href="/backtest">← Back to latest run</a></p></section>'
        ),
        status_code=400,
      )
    report = _load_report(path)
    if report is None:
      return HTMLResponse(
        content=_wrap_html(
          '<section class="error"><h1>Backtest file is corrupt.</h1>'
          '<p><a href="/backtest">← Back to latest run</a></p></section>'
        ),
        status_code=400,
      )
    return HTMLResponse(content=_wrap_html(render_report(report)), status_code=200)

  # ?history=true branch
  if params.get('history') == 'true':
    files = _list_reports()
    reports = [r for r in (_load_report(p) for p in files) if r is not None]
    return HTMLResponse(content=_wrap_html(render_history(reports)), status_code=200)

  # Default branch — latest report or empty state
  files = _list_reports()
  if not files:
    return HTMLResponse(content=_wrap_html(render_report({})), status_code=200)
  latest = _load_report(files[0])
  return HTMLResponse(content=_wrap_html(render_report(latest or {})), status_code=200)


# ---------- POST /backtest/run (operator override form D-14) ----------

async def post_backtest_run(
  request: Request,
  initial_account_aud: float = Form(...),
  cost_spi_aud: float = Form(...),
  cost_audusd_aud: float = Form(...),
) -> Response:
  """CONTEXT D-14: operator override form submit.

  Validates inputs server-side (T-23-input), runs simulation synchronously
  via backtest.cli.run_backtest, redirects 303 to /backtest on success.

  400 on validation failure, ShortFrameError, or DataFetchError.
  303 (NOT 307) per RESEARCH §Pattern 8 + A2 (FastAPI default 307 re-POSTs).
  """
  # T-23-input validation
  if not (initial_account_aud > 0):
    return HTMLResponse(
      content=_wrap_html(
        '<section class="error"><h1>Initial account must be greater than zero.</h1>'
        '<p><a href="/backtest">← Back</a></p></section>'
      ),
      status_code=400,
    )
  if cost_spi_aud < 0:
    return HTMLResponse(
      content=_wrap_html(
        '<section class="error"><h1>SPI 200 cost must be greater than or equal to zero.</h1>'
        '<p><a href="/backtest">← Back</a></p></section>'
      ),
      status_code=400,
    )
  if cost_audusd_aud < 0:
    return HTMLResponse(
      content=_wrap_html(
        '<section class="error"><h1>AUD/USD cost must be greater than or equal to zero.</h1>'
        '<p><a href="/backtest">← Back</a></p></section>'
      ),
      status_code=400,
    )

  args = RunArgs(
    initial_account_aud=float(initial_account_aud),
    cost_spi_aud=float(cost_spi_aud),
    cost_audusd_aud=float(cost_audusd_aud),
  )
  try:
    report, written_path, exit_code = run_backtest(args)
  except ShortFrameError as exc:
    logger.warning('%s ShortFrameError: %s', _LOG_PREFIX, exc)
    return HTMLResponse(
      content=_wrap_html(
        f'<section class="error"><h1>Backtest cannot run.</h1><p>{html.escape(str(exc))}</p>'
        f'<p><a href="/backtest">← Back</a></p></section>'
      ),
      status_code=400,
    )
  except DataFetchError as exc:
    logger.warning('%s DataFetchError: %s', _LOG_PREFIX, exc)
    return HTMLResponse(
      content=_wrap_html(
        '<section class="error"><h1>Could not fetch market data right now.</h1>'
        '<p>Try again in a minute, or run from CLI to see the underlying error.</p>'
        '<p><a href="/backtest">← Back</a></p></section>'
      ),
      status_code=400,
    )

  logger.info('%s POST /backtest/run wrote %s (exit_code=%d)',
              _LOG_PREFIX, written_path, exit_code)
  return RedirectResponse(url='/backtest', status_code=303)


# ---------- Mount factory ----------

def register(app: FastAPI) -> None:
  """Mount Phase 23 routes; called from web/app.py:create_app()."""
  app.add_api_route('/backtest', get_backtest, methods=['GET'])
  app.add_api_route('/backtest/run', post_backtest_run, methods=['POST'])
