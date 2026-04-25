'''GET /api/state — Phase 13 WEB-06 + D-12..D-15.

Returns the current state.json as JSON, with top-level underscore-prefixed
keys stripped. Used by mobile / CLI / external scripts that need the
source-of-truth state without HTML rendering.

Contract (CONTEXT.md 2026-04-25):
  D-12: top-level keys starting with '_' are stripped (runtime-only convention
        from Phase 8 D-14). Nested dicts keep their keys intact — filter is
        TOP LEVEL ONLY.
  D-13: Content-Type application/json (FastAPI JSONResponse default) +
        explicit Cache-Control: no-store. Required because state becomes
        mutation-capable in Phase 14; stale cached snapshots would mislead.
  D-14: Trust state_manager.load_state recovery (Phase 3 + Phase 8). load_state
        recovers from corrupt state, handles missing file (returns reset_state()),
        and never raises in normal operation. NO try/except wrapper here — if it
        does raise, the middleware returns 500 and that's a real bug to surface.
  D-15: Compact JSON (FastAPI default; no indent=2). Humans use `curl | jq`
        for pretty-printing. Keeps response bytes minimal — state.json grows
        to ~50KB over months of trade history.

SC-3 lock (REVIEWS MEDIUM #2):
  Every non-underscore top-level key from state.json appears in the response.
  The full key set {schema_version, account, last_run, positions, signals,
  trade_log, equity_history, warnings, contracts} is proven verbatim by
  tests/test_web_state.py::TestStateResponse::test_full_top_level_key_set_preserved_except_runtime_keys.

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  web/routes/ is an adapter hex.
  Allowed: fastapi, starlette, stdlib, state_manager (read-only per Phase 10 D-15).
  Forbidden: signal_engine, sizing_engine, system_params, notifier, main, dashboard.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

  state_manager import is LOCAL (inside the handler) per Phase 11 C-2.

Log prefix: [Web].
'''
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register(app: FastAPI) -> None:
  '''Register GET /api/state on the given FastAPI instance.'''

  @app.get('/api/state')
  def get_state():
    from state_manager import load_state  # local import — C-2 hex boundary

    state = load_state()  # D-14: trust Phase 3 recovery; no try/except here

    # D-12: strip TOP-LEVEL underscore-prefixed keys only. Nested dicts
    # (e.g., positions[instrument] dicts) keep their keys intact in case
    # v1.2 adds a legitimate `_comment` or similar inside a position.
    clean = {k: v for k, v in state.items() if not k.startswith('_')}

    return JSONResponse(
      content=clean,
      headers={'Cache-Control': 'no-store'},  # D-13
    )
    # D-15: FastAPI JSONResponse default is compact (no indent) — no
    # additional kwarg needed. Verified by RESEARCH.md §JSONResponse defaults.
