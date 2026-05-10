'''Module-level renderer helpers for the dashboard route package.

These are pure, closure-free helpers extracted from the monolithic
web/routes/dashboard.py during Phase 30 Plan 30-03 (D-07 boundary).

Only helpers that do NOT capture names defined inside register() live here.
Everything that references _session_secret, _session_serializer, or
_MARKET_COOKIE_ATTRS stays inside register() in __init__.py.
'''
import os
import re
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response

from system_params import INSTRUMENT_ID_RE as _MARKET_ID_RE  # r'^[A-Z0-9_]{2,20}$'

# Phase 25 D-01: Required dashboard marker (forces regen of all 5 sibling
# HTMLs post-deploy). Shared constant — __init__.py imports this to avoid
# duplication.
_REQUIRED_DASHBOARD_MARKER = b'class="tabs tabs-function"'  # Phase 25 D-01

# D-09: repo root, matches dashboard.py default
_STATE_PATH = 'state.json'


def _is_stale_for(page_output: Path) -> bool:
  '''Phase 26 Plan 26-07 (R1): per-file staleness check.

  D-08 generalised: state.json mtime > page_output mtime means regen needed.
  Each sibling HTML (dashboard.html, dashboard-signals.html, ...) is now
  gated by its own marker presence + own mtime — previously only
  dashboard.html was checked, leaving siblings stale on disk after deploys
  that bumped the marker but already had a fresh dashboard.html.

  Returns True if page_output is missing (caller handles via .exists()).
  Returns True if state.json is newer than page_output (regen path).
  Returns True if cached page_output predates the tabbed dashboard marker.
  Returns False if page_output is fresh relative to state.json.
  Returns False if state.json itself is missing (no state to render from).
  '''
  try:
    html_mtime = os.stat(page_output).st_mtime_ns
  except FileNotFoundError:
    return True  # missing page output — caller handles 503
  try:
    state_mtime = os.stat(_STATE_PATH).st_mtime_ns
  except FileNotFoundError:
    return False  # no state.json — serve whatever page_output is
  try:
    if _REQUIRED_DASHBOARD_MARKER not in page_output.read_bytes():
      return True
  except OSError:
    return True
  return state_mtime > html_mtime


def _is_htmx_request(request: Request) -> bool:
  '''Phase 25 Pitfall 6: HTMX swap requests carry HX-Request: true header.'''
  return request.headers.get('HX-Request', '').lower() == 'true'


def _resolve_trace_open(request: Request) -> frozenset:
  '''Read tsi_trace_open cookie and return allowlisted instrument keys.

  The cookie value is a comma-separated list of instrument keys
  (e.g. "SPI200,AUDUSD"). Only keys matching the canonical market-ID regex
  ^[A-Z0-9_]{2,20}$ (sourced from _MARKET_ID_RE) are accepted — all other
  values are discarded silently. Returns empty frozenset when cookie absent
  or contains no valid keys.

  Phase 29 Plan 12: widened from a static frozenset{'SPI200','AUDUSD'} to
  a regex-validated format allowlist so dynamically-added markets (Phase 25+
  multi-market API) are also covered. Security is preserved: _trace_open_repl
  can only emit b' open' or b'' — no injection surface regardless of market ID.
  '''
  raw = request.cookies.get('tsi_trace_open', '')
  if not raw:
    return frozenset()
  parts = {p.strip() for p in raw.split(',') if p.strip()}
  return frozenset(p for p in parts if _MARKET_ID_RE.fullmatch(p))


def _forward_stop_fragment_response(request: Request, fragment: str | None):
  # Phase 15 CALC-03 + REVIEWS L-1: forward-stop fragment — EXACT match.
  # Handled BEFORE the dashboard.html file-read path because this fragment
  # does not need the on-disk dashboard.html to exist (it reads state.json
  # directly via load_state). Degenerate Z returns em-dash, never 4xx.
  if fragment != 'forward-stop':
    return None
  import html as _html
  import math as _math

  from dashboard import _fmt_currency, _fmt_em_dash  # LOCAL — C-2
  from sizing_engine import get_trailing_stop  # LOCAL — C-2
  from state_manager import load_state as _ls  # LOCAL — C-2

  instrument = request.query_params.get('instrument', '')
  z_raw = request.query_params.get('z', '')
  span_id_suffix = _html.escape(instrument, quote=True) if instrument else 'unknown'

  def _em_dash_response():
    body = f'<span id="forward-stop-{span_id_suffix}-w">{_fmt_em_dash()}</span>'
    return Response(content=body.encode('utf-8'), media_type='text/html; charset=utf-8')

  try:
    z = float(z_raw)
  except (ValueError, TypeError):
    return _em_dash_response()
  if not _math.isfinite(z) or z <= 0:
    return _em_dash_response()

  try:
    state = _ls()
  except (OSError, ValueError, TypeError):
    return _em_dash_response()

  pos = state.get('positions', {}).get(instrument)
  if pos is None:
    return _em_dash_response()

  synth = dict(pos)
  direction = synth.get('direction', 'LONG')
  if direction == 'LONG':
    peak = synth.get('peak_price') or synth.get('entry_price', 0.0)
    synth['peak_price'] = max(peak, z)
  else:
    trough = synth.get('trough_price') or synth.get('entry_price', 0.0)
    synth['trough_price'] = min(trough, z)

  try:
    w = get_trailing_stop(synth, 0.0, 0.0)
  except (ValueError, TypeError, KeyError):
    return _em_dash_response()

  if not _math.isfinite(w):
    w_html = _fmt_em_dash()
  else:
    w_html = _html.escape(_fmt_currency(w), quote=True)

  body = f'<span id="forward-stop-{span_id_suffix}-w">{w_html}</span>'
  return Response(content=body.encode('utf-8'), media_type='text/html; charset=utf-8')
