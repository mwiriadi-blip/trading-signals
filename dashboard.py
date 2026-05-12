'''dashboard — public API shim delegating to dashboard_renderer.

Phase 32 Plan 04: thinned to ≤100 LOC pass-through shim. All rendering
lives in dashboard_renderer/. This module exposes only the public API
(render_dashboard_files, render_dashboard_page, render_dashboard alias)
and the module logger.

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. Must NOT import
signal_engine, sizing_engine, data_fetcher, notifier, main, numpy,
pandas, yfinance, or requests at module top.
'''
import logging
from datetime import datetime  # noqa: F401 — type-hint surface for callers
from pathlib import Path

from state_manager import (
  load_state,  # noqa: F401 — CLI convenience path
)

# Module logger — name preserved as 'dashboard' for journalctl + test capture
logger = logging.getLogger('dashboard')


def render_dashboard_files(
  state: dict,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
  is_cookie_session: bool | None = None,
  trace_open_keys: list | None = None,
) -> None:
  '''Compatibility wrapper; primary orchestration lives in dashboard_renderer.api.

  Phase 26 Plan 06 (R2): renamed from render_dashboard → render_dashboard_files.
  Pure file-write, returns None. The render_dashboard alias below preserves
  back-compat callers.
  '''
  from dashboard_renderer.api import render_dashboard_files as _impl
  _impl(
    state,
    out_path=out_path,
    now=now,
    is_cookie_session=is_cookie_session,
    trace_open_keys=trace_open_keys,
  )


def render_dashboard_page(
  state: dict,
  page: str,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
  is_cookie_session: bool | None = None,
  trace_open_keys: list | None = None,
) -> None:
  '''Compatibility wrapper; primary orchestration lives in dashboard_renderer.api.'''
  from dashboard_renderer.api import render_dashboard_page as _impl
  _impl(
    state,
    page=page,
    out_path=out_path,
    now=now,
    is_cookie_session=is_cookie_session,
    trace_open_keys=trace_open_keys,
  )


# Phase 26 Plan 06 back-compat: alias for legacy callers using render_dashboard.
render_dashboard = render_dashboard_files  # noqa: F811 — back-compat alias


if __name__ == '__main__':
  # CONTEXT D-05 convenience CLI. `python -m dashboard` loads the current
  # state.json and renders dashboard.html using the current AWST wall-clock.
  render_dashboard_files(load_state(), Path('dashboard.html'))
