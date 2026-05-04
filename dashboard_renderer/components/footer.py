'''Footer component implementation.'''

import html


def render_footer(strategy_version: str) -> str:
  version_esc = html.escape(strategy_version, quote=True)
  return (
    '<footer>\n'
    '  Signal-only system. Not financial advice.\n'
    f'  <div class="strategy-version">Strategy version: <code>{version_esc}</code></div>\n'
    '</footer>\n'
  )
