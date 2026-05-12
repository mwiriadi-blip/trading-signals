'''Public dashboard rendering API.

Primary render-orchestration entrypoint. Keeps the public `dashboard.py`
surface stable while moving top-level composition into `dashboard_renderer`.
'''

import logging
from datetime import datetime
from pathlib import Path

import pytz

from dashboard_renderer.components.header import render_header_from_context
from dashboard_renderer.context import RenderContext
from dashboard_renderer.formatters import _resolve_strategy_version, _resolve_trace_open_keys
from dashboard_renderer.io import atomic_write_html
from dashboard_renderer.shell import (
  _render_single_page_dashboard,
  _render_tabbed_dashboard,
  render_html_shell,
)

logger = logging.getLogger(__name__)


def _resolve_now(now: datetime | None) -> datetime:
  if now is not None:
    return now
  sydney = pytz.timezone('Australia/Sydney')
  return datetime.now(sydney)


def _build_render_context(
  *,
  state: dict,
  now: datetime | None,
  trace_open_keys: list | None,
  active_function: str = 'signals',
  active_market: str | None = None,
) -> RenderContext:
  resolved_now = _resolve_now(now)
  strategy_version = _resolve_strategy_version(state)
  ctx = RenderContext.build(
    state=state,
    now=resolved_now,
    strategy_version=strategy_version,
    trace_open_keys=trace_open_keys,
    active_function=active_function,
    active_market=active_market,
  )
  _resolve_trace_open_keys(ctx.state, list(ctx.trace_open_keys))
  return ctx


def _render_header_and_body(
  *,
  ctx: RenderContext,
  is_cookie_session: bool | None,
  body_html: str,
) -> str:
  body = render_header_from_context(ctx, is_cookie_session=is_cookie_session) + body_html
  return render_html_shell(ctx, body)


def render_dashboard_files(
  state: dict,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
  is_cookie_session: bool | None = None,
  trace_open_keys: list | None = None,
  *,
  active_function: str = 'signals',
  active_market: str | None = None,
) -> None:
  '''Render the full dashboard plus on-disk per-page siblings.

  Phase 26 Plan 06 (R2): pure file-write entrypoint. Returns None per
  annotation. The HTMX panel-only path moved to render_panel_html; the
  mixed-return-type predecessor that returned str on htmx_panel_only=True
  is gone (eliminated annotation lie).
  '''
  ctx = _build_render_context(
    state=state,
    now=now,
    trace_open_keys=trace_open_keys,
    active_function=active_function,
    active_market=active_market,
  )

  logger.info('[Dashboard] rendering to %s', out_path)
  html_str = _render_header_and_body(
    ctx=ctx,
    is_cookie_session=is_cookie_session,
    # Keep dashboard.html as the full composition entrypoint.
    body_html=_render_tabbed_dashboard(ctx),
  )
  atomic_write_html(html_str, out_path)

  sibling_targets = (
    ('signals', Path('dashboard-signals.html')),
    ('account', Path('dashboard-account.html')),
    ('settings', Path('dashboard-settings.html')),
    ('market-test', Path('dashboard-market-test.html')),
  )
  # Phase 26 R3: on-disk siblings serve unscoped /signals, /settings, /market-test
  # routes — the cache is single-key per page, so document the first-market
  # fallback explicitly. Per-market scoping uses the in-memory render path
  # (_serve_market_scoped_page → render_dashboard_as_str) with Cache-Control: no-store.
  from dashboard_renderer.components.nav import _first_market_id
  sibling_market = _first_market_id(state)
  for sibling_page, sibling_out in sibling_targets:
    sibling_ctx = _build_render_context(
      state=state,
      now=now,
      trace_open_keys=trace_open_keys,
      active_function=sibling_page,
      active_market=sibling_market or None,
    )
    sibling_html_str = _render_header_and_body(
      ctx=sibling_ctx,
      is_cookie_session=is_cookie_session,
      body_html=_render_single_page_dashboard(sibling_ctx, sibling_page),
    )
    atomic_write_html(sibling_html_str, sibling_out)
  logger.info('[Dashboard] wrote %d bytes to %s', len(html_str), out_path)


def render_panel_html(
  state: dict,
  *,
  active_function: str = 'signals',
  active_market: str | None = None,
  now: datetime | None = None,
  trace_open_keys: list | None = None,
) -> str:
  '''Return ONLY the inner panel HTML for HTMX swaps (Plan 25-04).

  Phase 26 Plan 06 (R2): public wrapper around dashboard_renderer.pages.render_panel_only.
  No shell, no nav strips, no <head>/<body> — the raw content that would
  appear inside <section id="market-panel">. Used by _serve_market_scoped_page
  on HX-Request branches.
  '''
  ctx = _build_render_context(
    state=state,
    now=now,
    trace_open_keys=trace_open_keys,
    active_function=active_function,
    active_market=active_market,
  )
  from dashboard_renderer.pages import render_panel_only
  return render_panel_only(ctx)


def render_dashboard_as_str(
  state: dict,
  now=None,
  active_function: str = 'signals',
  active_market: str | None = None,
) -> str:
  '''Render full dashboard to a string without writing to disk.

  Phase 25 Plan 04: used by _serve_market_scoped_page to serve full-page
  HTML directly in the HTTP response (no intermediate file). Returns the
  complete <!DOCTYPE html>…</html> string for the given market/function.
  '''
  ctx = _build_render_context(
    state=state,
    now=now,
    trace_open_keys=None,
    active_function=active_function,
    active_market=active_market,
  )
  return _render_header_and_body(
    ctx=ctx,
    is_cookie_session=None,
    body_html=_render_single_page_dashboard(ctx, active_function),
  )


def render_dashboard_page(
  state: dict,
  page: str,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
  is_cookie_session: bool | None = None,
  trace_open_keys: list | None = None,
  *,
  active_market: str | None = None,
) -> None:
  ctx = _build_render_context(
    state=state,
    now=now,
    trace_open_keys=trace_open_keys,
    active_function=page,
    active_market=active_market,
  )
  logger.info('[Dashboard] rendering page=%s to %s', page, out_path)
  html_str = _render_header_and_body(
    ctx=ctx,
    is_cookie_session=is_cookie_session,
    body_html=_render_single_page_dashboard(ctx, page),
  )
  atomic_write_html(html_str, out_path)
  logger.info('[Dashboard] wrote page=%s (%d bytes) to %s', page, len(html_str), out_path)
