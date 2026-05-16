'''web/routes/dashboard/_cache.py — module-level constants for the dashboard route.

Cache paths, placeholder bytes, regex patterns, and page-output mappings.
All values are import-time constants — no I/O at module load.

No imports from _routes, _helpers, or _renderers to avoid circular imports.
'''
import re

_DASHBOARD_PATH = 'dashboard.html'  # D-09: repo root, matches dashboard.py default
_STATE_PATH = 'state.json'

# Phase 26 Plan 26-07 (R6): allowlist for active_function query param.
_ALLOWED_FUNCTIONS = {'signals', 'account', 'settings', 'market-test'}

# Phase 14 Plan 14-04 Task 5 (REVIEWS HIGH #4): substitute placeholder with
# env secret at request time so on-disk dashboard.html never carries the
# real value. Plan 14-05 emits the literal placeholder in hx-headers.
_PLACEHOLDER = b'{{WEB_AUTH_SECRET}}'

# Phase 16.1 — placeholders for the per-request auth-widget swap (Sign Out
# button vs session note). Mirrors the Phase 14 {{WEB_AUTH_SECRET}} pattern.
_SIGNOUT_PLACEHOLDER = b'{{SIGNOUT_BUTTON}}'
_SESSION_NOTE_PLACEHOLDER = b'{{SESSION_NOTE}}'

# Phase 17 Plan 17-01 — trace-panel open-state cookie.
# The unsigned UI-preference cookie `tsi_trace_open` carries a comma-separated
# list of instrument keys whose <details> should be pre-expanded. The allowlist
# prevents arbitrary attribute injection into the substituted HTML.
_VALID_TRACE_INSTRUMENT_KEYS: frozenset = frozenset({'SPI200', 'AUDUSD'})
_TRACE_OPEN_PLACEHOLDER_SPI200 = b'{{TRACE_OPEN_SPI200}}'
_TRACE_OPEN_PLACEHOLDER_AUDUSD = b'{{TRACE_OPEN_AUDUSD}}'

# Phase 26 Plan 26-04 (B2/B3): generalised TRACE_OPEN placeholder regex matches
# `{{TRACE_OPEN_<MARKET>}}` for any market id satisfying ^[A-Z0-9_]{2,20}$.
# Bytes regex is used because _substitute operates on bytes.
_TRACE_OPEN_RE = re.compile(rb'\{\{TRACE_OPEN_([A-Z0-9_]{2,20})\}\}')

_PAGE_OUTPUTS = {
  'signals': 'dashboard-signals.html',
  'account': 'dashboard-account.html',
  'settings': 'dashboard-settings.html',
  'market-test': 'dashboard-market-test.html',
}
