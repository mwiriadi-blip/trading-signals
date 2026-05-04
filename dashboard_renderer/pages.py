'''Page composition wrappers for phased migration.'''

from dashboard_renderer.context import RenderContext

def render_dashboard_page_body(
  ctx: RenderContext,
  page: str,
  nav_mode: str = 'web',
) -> str:
  import dashboard

  return dashboard._render_single_page_dashboard(ctx, page, nav_mode=nav_mode)
