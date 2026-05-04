'''Shell rendering wrappers for phased migration.'''

from dashboard_renderer.context import RenderContext

def render_html_shell(ctx: RenderContext, body: str) -> str:
  import dashboard

  return dashboard._render_html_shell(ctx, body)
