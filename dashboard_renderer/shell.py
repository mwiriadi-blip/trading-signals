'''dashboard_renderer/shell.py — Phase 25 D-02: single source of truth for HTML shell.

Emits the full <!DOCTYPE html> shell with inline <style>, <script>, and the
Phase 25 D-08 AWST countdown helper. All constants imported from assets.py.

Per D-02: no external /static/dashboard.css or /static/dashboard.js.
Everything is inlined in the per-page HTML response (DASH-01 pattern).
'''

import html as _html

from dashboard_renderer.assets import (
  _CHARTJS_URL,
  _CHARTJS_SRI,
  _HANDLE_TRADES_ERROR_JS,
  _HTMX_JSON_ENC_SRI,
  _HTMX_JSON_ENC_URL,
  _HTMX_SRI,
  _HTMX_URL,
  _INLINE_CSS,
  _TRACE_TOGGLE_JS,
)
from dashboard_renderer.context import RenderContext

# Phase 25 D-08: AWST countdown helper. Inlined per D-02 — no external JS.
# Uses Date.UTC arithmetic — never browser local TZ (operator may travel;
# daemon always runs AWST = UTC+8, no DST).
# 08:00 AWST == 00:00 UTC. Target is 08:01 AWST == 00:01 UTC (60s buffer so
# state.json has time to write before the strip auto-refreshes).
_AWST_COUNTDOWN_JS = '''<script>
// Phase 25 D-08: AWST countdown. Fixed UTC+8 offset; ignores browser local TZ.
function _awstNext0800Utc() {
  var now = Date.now();
  var d = new Date(now);
  var target = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 0, 0, 0, 0);
  if (target <= now) target += 86400000;
  // Skip weekends — daemon does not run Sat/Sun (UTC day 0=Sun, 6=Sat).
  var dt = new Date(target);
  while (dt.getUTCDay() === 0 || dt.getUTCDay() === 6) {
    target += 86400000;
    dt = new Date(target);
  }
  return target;
}
function _formatAwstCountdown(targetUtcMs) {
  var now = Date.now();
  var dt = new Date(targetUtcMs);
  var days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var dayName = days[dt.getUTCDay()];
  var deltaMs = targetUtcMs - now;
  var deltaH = Math.floor(deltaMs / 3600000);
  var deltaM = Math.floor((deltaMs % 3600000) / 60000);
  if (deltaH >= 24) {
    var ddays = Math.floor(deltaH / 24);
    var hours = deltaH % 24;
    return dayName + ' 08:00 AWST · in ' + ddays + 'd ' + hours + 'h';
  }
  return '08:00 AWST · in ' + deltaH + 'h ' + deltaM + 'm';
}
function _refreshAwstCountdowns() {
  var target = _awstNext0800Utc();
  document.querySelectorAll('[data-countdown]').forEach(function(el) {
    el.textContent = _formatAwstCountdown(target);
  });
}
document.addEventListener('DOMContentLoaded', function() {
  _refreshAwstCountdowns();
  setInterval(_refreshAwstCountdowns, 60000);
});
</script>
'''


def render_html_shell(ctx: RenderContext, body: str) -> str:
  '''Phase 25 D-02: emit shared <head> + style + scripts inline.

  Single source of truth for all 5 dashboard*.html pages.
  Replaces the old 8-line wrapper that delegated to dashboard._render_html_shell.
  '''
  title = 'Trading Signals'  # Plan 25-03 overlays function+market per D-03
  return (
    '<!DOCTYPE html>\n'
    '<html lang="en">\n'
    '<head>\n'
    '  <meta charset="utf-8">\n'
    '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
    f'  <title>{_html.escape(title, quote=True)}</title>\n'
    f'  <script src="{_CHARTJS_URL}" '
    f'integrity="{_CHARTJS_SRI}" crossorigin="anonymous"></script>\n'
    f'  <script src="{_HTMX_URL}" '
    f'integrity="{_HTMX_SRI}" crossorigin="anonymous"></script>\n'
    f'  <script src="{_HTMX_JSON_ENC_URL}" '
    f'integrity="{_HTMX_JSON_ENC_SRI}" crossorigin="anonymous"></script>\n'
    '  <script>\n'
    + _HANDLE_TRADES_ERROR_JS
    + _TRACE_TOGGLE_JS
    + '  </script>\n'
    f'  <style>{_INLINE_CSS}</style>\n'
    '</head>\n'
    '<body>\n'
    '  <div class="container">\n'
    '    <div id="confirmation-banner"></div>\n'
    f'{body}'
    '  </div>\n'
    f'{_AWST_COUNTDOWN_JS}'
    '</body>\n'
    '</html>\n'
  )
