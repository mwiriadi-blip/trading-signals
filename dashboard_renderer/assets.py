'''dashboard_renderer/assets.py — Phase 25 source of truth for shell constants.

All inline CSS, CDN URLs, SRI hashes, and JS helpers live here.
dashboard.py re-exports these via `from dashboard_renderer.assets import ...`.
Per D-02: no external static files — everything is inlined at serve time.

CSS and JS content lives in dashboard_renderer/static/ and is loaded at
module-import time. The CSS template uses str.format() with color constants
from system_params so the :root block carries real hex values.

innerHTML usage in _HANDLE_TRADES_ERROR_JS: content is server-controlled
Pydantic validation errors and hardcoded literals only — NOT user-controllable.
Per CLAUDE.md: acceptable when content is server-controlled prose. See
dashboard.py Phase 14 UI-SPEC §Decision 4 comment for full audit trail.
'''

from pathlib import Path

from system_params import (
  _COLOR_BG,
  _COLOR_BORDER,
  _COLOR_FLAT,
  _COLOR_LONG,
  _COLOR_SHORT,
  _COLOR_SURFACE,
  _COLOR_TEXT,
  _COLOR_TEXT_DIM,
  _COLOR_TEXT_MUTED,
)

_STATIC_DIR = Path(__file__).resolve().parent / 'static'

# =========================================================================
# CDN vendor pins — SRI verified 2026-04-21
# =========================================================================

_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'

_HTMX_URL = 'https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js'
_HTMX_SRI = 'sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2'

_HTMX_JSON_ENC_URL = 'https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/ext/json-enc.js'
_HTMX_JSON_ENC_SRI = 'sha384-nRnAvEUI7N/XvvowiMiq7oEI04gOXMCqD3Bidvedw+YNbj7zTQACPlRI3Jt3vYM4'

# Legacy alias names from the old assets.py shim — kept for any out-of-tree consumers.
CHARTJS_URL = _CHARTJS_URL
CHARTJS_SRI = _CHARTJS_SRI
HTMX_URL = _HTMX_URL
HTMX_SRI = _HTMX_SRI
HTMX_JSON_ENC_URL = _HTMX_JSON_ENC_URL
HTMX_JSON_ENC_SRI = _HTMX_JSON_ENC_SRI

# =========================================================================
# Inline JS helpers — loaded from static/ at import time
# =========================================================================

_HANDLE_TRADES_ERROR_JS = (_STATIC_DIR / 'handle_trades_error.js').read_text(encoding='utf-8')
_TRACE_TOGGLE_JS = (_STATIC_DIR / 'trace_toggle.js').read_text(encoding='utf-8')

# =========================================================================
# Inline CSS — loaded from static/dashboard.css template and formatted with
# color constants from system_params (single source of truth per D-02).
# =========================================================================

_INLINE_CSS = (_STATIC_DIR / 'dashboard.css').read_text(encoding='utf-8').format(
  COLOR_BG=_COLOR_BG,
  COLOR_SURFACE=_COLOR_SURFACE,
  COLOR_BORDER=_COLOR_BORDER,
  COLOR_TEXT=_COLOR_TEXT,
  COLOR_TEXT_MUTED=_COLOR_TEXT_MUTED,
  COLOR_TEXT_DIM=_COLOR_TEXT_DIM,
  COLOR_LONG=_COLOR_LONG,
  COLOR_SHORT=_COLOR_SHORT,
  COLOR_FLAT=_COLOR_FLAT,
)

# Legacy names from old shim for any out-of-tree consumers.
INLINE_CSS = _INLINE_CSS
HANDLE_TRADES_ERROR_JS = _HANDLE_TRADES_ERROR_JS
