'''Public dashboard rendering API.

Primary render-orchestration entrypoint. Keeps the public `dashboard.py`
surface stable while moving top-level composition into `dashboard_renderer`.
'''

from datetime import datetime
from pathlib import Path

import pytz

from dashboard_renderer.context import RenderContext


def _resolve_now(now: datetime | None) -> datetime:
  if now is not None:
    return now
  perth = pytz.timezone('Australia/Perth')
  return datetime.now(perth)


def _build_render_context(
  *,
  state: dict,
  now: datetime | None,
  trace_open_keys: list | None,
  active_function: str = 'signals',
  active_market: str | None = None,
) -> RenderContext:
  import dashboard as d

  resolved_now = _resolve_now(now)
  strategy_version = d._resolve_strategy_version(state)
  ctx = RenderContext.build(
    state=state,
    now=resolved_now,
    strategy_version=strategy_version,
    trace_open_keys=trace_open_keys,
    active_function=active_function,
    active_market=active_market,
  )
  d._resolve_trace_open_keys(ctx.state, list(ctx.trace_open_keys))
  return ctx


def _render_header_and_body(
  *,
  ctx: RenderContext,
  is_cookie_session: bool | None,
  body_html: str,
) -> str:
  import dashboard as d

  body = d._render_header_ctx(ctx, is_cookie_session=is_cookie_session) + body_html
  return d._render_html_shell(ctx, body)


def render_dashboard(
  state: dict,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
  is_cookie_session: bool | None = None,
  trace_open_keys: list | None = None,
  *,
  active_function: str = 'signals',
  active_market: str | None = None,
  htmx_panel_only: bool = False,
) -> None:
  '''Render the full dashboard (or HTMX panel-only fragment).

  Phase 25: accepts active_function and active_market kwargs. Existing callers
  continue to work via defaults. htmx_panel_only=True returns the inner panel
  HTML for HTMX swaps (Plan 25-04), without shell/nav.
  '''
  import dashboard as d

  ctx = _build_render_context(
    state=state,
    now=now,
    trace_open_keys=trace_open_keys,
    active_function=active_function,
    active_market=active_market,
  )

  if htmx_panel_only:
    # Phase 25 Plan 04: HTMX swap path — return ONLY the inner panel HTML
    # (no shell, no nav strips). Resolves Plan 25-04 WARNING 4.
    from dashboard_renderer.pages import render_panel_only
    return render_panel_only(ctx)

  d.logger.info('[Dashboard] rendering to %s', out_path)
  html_str = _render_header_and_body(
    ctx=ctx,
    is_cookie_session=is_cookie_session,
    # Keep dashboard.html as the full composition entrypoint.
    body_html=d._render_tabbed_dashboard(ctx),
  )
  d._atomic_write_html(html_str, out_path)

  sibling_targets = (
    ('signals', Path('dashboard-signals.html')),
    ('account', Path('dashboard-account.html')),
    ('settings', Path('dashboard-settings.html')),
    ('market-test', Path('dashboard-market-test.html')),
  )
  for sibling_page, sibling_out in sibling_targets:
    sibling_html_str = _render_header_and_body(
      ctx=ctx,
      is_cookie_session=is_cookie_session,
      body_html=d._render_single_page_dashboard(ctx, sibling_page, nav_mode='file'),
    )
    d._atomic_write_html(sibling_html_str, sibling_out)
  d.logger.info('[Dashboard] wrote %d bytes to %s', len(html_str), out_path)


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
  import dashboard as d
  return _render_header_and_body(
    ctx=ctx,
    is_cookie_session=None,
    body_html=d._render_single_page_dashboard(ctx, active_function, nav_mode='web'),
  )


def render_dashboard_page(
  state: dict,
  page: str,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
  is_cookie_session: bool | None = None,
  trace_open_keys: list | None = None,
) -> None:
  import dashboard as d

  ctx = _build_render_context(
    state=state,
    now=now,
    trace_open_keys=trace_open_keys,
  )
  d.logger.info('[Dashboard] rendering page=%s to %s', page, out_path)
  html_str = _render_header_and_body(
    ctx=ctx,
    is_cookie_session=is_cookie_session,
    body_html=d._render_single_page_dashboard(ctx, page, nav_mode='web'),
  )
  d._atomic_write_html(html_str, out_path)
  d.logger.info('[Dashboard] wrote page=%s (%d bytes) to %s', page, len(html_str), out_path)
