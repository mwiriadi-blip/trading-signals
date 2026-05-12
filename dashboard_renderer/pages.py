'''Page composition wrappers for phased migration.'''

from dashboard_renderer.context import RenderContext
from dashboard_renderer.shell import _render_page_body, _render_single_page_dashboard


def render_dashboard_page_body(
  ctx: RenderContext,
  page: str,
) -> str:
  '''Render full single-page dashboard body (nav + panel).

  Phase 25: derives active_function/active_market from ctx; uses render_two_axis_nav.
  Phase 26 Plan 06 (R4): legacy nav-mode parameter dropped — render_two_axis_nav
  is the only path; the file-vs-web nav distinction is gone.
  '''
  return _render_single_page_dashboard(ctx, page)


def render_panel_only(ctx: RenderContext) -> str:
  '''Return ONLY the inner panel HTML for HTMX swaps (Plan 25-04).

  No shell, no nav strips, no <head>/<body>. Phase 26 Plan 06 (R2): called
  via dashboard_renderer.api.render_panel_html (the public wrapper that
  builds RenderContext). Resolves Plan 25-04 WARNING 4 (fragile regex
  extraction).

  Returns the raw content that would appear inside <section id="market-panel">,
  without the wrapper itself.
  '''
  page = ctx.active_function
  if page not in ('signals', 'account', 'settings', 'market-test'):
    page = 'signals'

  _, _, _, _, render_body = _render_page_body(ctx, page)
  return render_body()
