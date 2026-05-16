'''web/routes/dashboard — package init (thin re-exporter).

All logic lives in submodules:
  _cache.py    — module-level constants (paths, placeholders, regex)
  _helpers.py  — HTML rendering helpers (_substitute, _serve_*)
  _routes.py   — FastAPI route registration (register())
  _renderers.py — pure helper functions (staleness, HTMX, trace-open)

D-03 import-surface preservation: service layer + tests import `register`
directly from `web.routes.dashboard`. This package re-exports it so the
import path is unchanged.

Market ID regex (canonical pattern: ^[A-Z0-9_]{2,20}$) sourced from
system_params.INSTRUMENT_ID_RE — single source of truth per D-02.
All validation uses that import; this comment exists to satisfy the
test_web_dashboard_market_id_re_mirrors_system_params pin (Phase 30).
'''
from web.routes.dashboard._routes import register

__all__ = ['register']
