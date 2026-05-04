'''Header component implementation.'''

import html
from datetime import datetime

from dashboard_renderer.context import RenderContext

def render_header(state: dict, now: datetime, is_cookie_session: bool | None = None) -> str:
  import dashboard as d

  del state
  subtitle = html.escape('SPI 200 & AUD/USD mechanical system', quote=True)
  last_updated = html.escape(d._fmt_last_updated(now), quote=True)
  if is_cookie_session is None:
    auth_widget = '{{SIGNOUT_BUTTON}}{{SESSION_NOTE}}'
  elif is_cookie_session:
    auth_widget = d._render_signout_button()
  else:
    auth_widget = d._render_session_note()
  return (
    '<header>\n'
    '  <h1>Trading Signals</h1>\n'
    f'  <p class="subtitle">{subtitle}</p>\n'
    '  <p class="meta">\n'
    '    <span class="label">Last updated</span>\n'
    f'    <span class="value">{last_updated}</span>\n'
    f'    {auth_widget}\n'
    '  </p>\n'
    '</header>\n'
  )


def render_header_from_context(ctx: RenderContext, is_cookie_session: bool | None = None) -> str:
  return render_header(ctx.state, ctx.now, is_cookie_session=is_cookie_session)
