"""Phase 23 — pure HTML render for /backtest report + history + override form.

Architecture (hexagonal-lite, CLAUDE.md): pure render. NO I/O, NO env vars,
NO clock injection.
DOES NOT IMPORT dashboard.py per CONTEXT D-07 — Chart.js URL+SRI duplicated below.

Forbidden imports (BACKTEST_PATHS_PURE AST guard): same as simulator.py.
Allowed: html (escape), json, typing.
"""
from __future__ import annotations
import html
import json

# Chart.js 4.4.6 UMD CDN constants — DUPLICATED from dashboard.py:113-116 per D-07.
_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'


def render_report(report: dict) -> str:
  raise NotImplementedError('Phase 23 Wave 2 Plan 05 — to be implemented')


def render_history(reports: list[dict]) -> str:
  raise NotImplementedError('Phase 23 Wave 2 Plan 05 — to be implemented')


def render_run_form(defaults: dict) -> str:
  raise NotImplementedError('Phase 23 Wave 2 Plan 05 — to be implemented')
