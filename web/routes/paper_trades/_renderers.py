'''Render helpers + module-level constants for the paper-trades route.

Moved verbatim from web/routes/paper_trades.py (Phase 30 D-08 pre-emptive split).
Zero semantic changes — all constant values and helper behaviour preserved exactly.

Constants exported:
  _COST_AUD, _MULTIPLIER, _D09_KEYS

Helpers exported:
  _method_not_allowed_405
'''
from fastapi.responses import Response

# Mirror of system_params constants — kept here so pnl_engine stays decoupled per
# planner D-19 + Phase 2 D-17. If system_params changes, update here and bump tests.
_COST_AUD: dict[str, float] = {'SPI200': 6.0, 'AUDUSD': 5.0}  # full round-trip
_MULTIPLIER: dict[str, float] = {'SPI200': 5.0, 'AUDUSD': 10000.0}

_D09_KEYS = frozenset({
  'id', 'instrument', 'side', 'entry_dt', 'entry_price', 'contracts',
  'stop_price', 'entry_cost_aud', 'status', 'exit_dt', 'exit_price',
  'realised_pnl', 'strategy_version', 'last_alert_state',
})


# =========================================================================
# 405 helper — RFC 7231 §6.5.5
# =========================================================================

def _method_not_allowed_405(allow: str = 'GET') -> Response:
  '''RFC 7231 §6.5.5 — 405 MUST include Allow header listing allowed methods.

  Manual 405 responses (closed-row immutability) do NOT include Allow
  automatically unlike FastAPI's auto-generated 405 for unknown methods.
  We must add it explicitly. RESEARCH §Pattern 3 verified this.
  '''
  return Response(
    content='closed rows are immutable',
    status_code=405,
    headers={'Allow': allow},
    media_type='text/plain; charset=utf-8',
  )
