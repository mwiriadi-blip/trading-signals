'''Dashboard renderer package exports.'''

from dashboard_renderer.api import (
  render_dashboard_files,
  render_dashboard_page,
  render_panel_html,
)

__all__ = ['render_dashboard_files', 'render_dashboard_page', 'render_panel_html']
