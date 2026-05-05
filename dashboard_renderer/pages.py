'''Page composition wrappers for phased migration.'''

from dashboard_renderer.context import RenderContext


def render_dashboard_page_body(
  ctx: RenderContext,
  page: str,
  nav_mode: str = 'web',
) -> str:
  '''Render full single-page dashboard body (nav + panel).

  Phase 25: derives active_function/active_market from ctx; uses render_two_axis_nav.
  '''
  import dashboard

  return dashboard._render_single_page_dashboard(ctx, page, nav_mode=nav_mode)


def render_panel_only(ctx: RenderContext) -> str:
  '''Return ONLY the inner panel HTML for HTMX swaps (Plan 25-04).

  No shell, no nav strips, no <head>/<body>. Used when htmx_panel_only=True
  is passed to render_dashboard(). Resolves Plan 25-04 WARNING 4 (fragile
  regex extraction).

  Returns the raw content that would appear inside <section id="market-panel">,
  without the wrapper itself.
  '''
  import dashboard as d

  page = ctx.active_function
  if page not in ('signals', 'account', 'settings', 'market-test'):
    page = 'signals'

  _, _, _, _, render_body = d._render_page_body(ctx, page)
  return render_body()
