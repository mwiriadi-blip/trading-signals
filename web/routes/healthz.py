'''GET /healthz — Phase 11 WEB-07 + D-13..D-19.

Response schema: {'status':'ok', 'last_run':<YYYY-MM-DD str|null>, 'stale':<bool>}

Contract (CONTEXT.md 2026-04-24 reconciled post-REVIEWS HIGH #1):
  D-13: last_run is a DATE-ONLY ISO string ('YYYY-MM-DD'), matching
        what main.py:1042 writes via state['last_run'] = run_date_iso.
  D-14: always HTTP 200 if process is alive.
  D-15: last_run from state_manager.load_state() — local import (C-2).
  D-16: stale=True iff (now.date() - last_run_date).days > 2. Handler
        uses date.fromisoformat (date-only, REVIEWS HIGH #1).
  D-19: NEVER non-200; on exception, return degraded body + WARN [Web].
'''
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def register(app: FastAPI) -> None:
  '''Register GET /healthz on the given FastAPI instance.'''

  @app.get('/healthz')
  def healthz() -> dict:
    import zoneinfo
    from datetime import date as _date
    from datetime import datetime

    try:
      from state_manager import load_state  # local import — C-2

      state = load_state()
      last_run = state.get('last_run')  # YYYY-MM-DD str or None

      stale = False
      if last_run is not None:
        # D-16: state stores date-only strings — use date.fromisoformat.
        awst = zoneinfo.ZoneInfo('Australia/Perth')
        now_awst = datetime.now(awst)
        try:
          last_dt = _date.fromisoformat(last_run)
          delta_days = (now_awst.date() - last_dt).days
          stale = delta_days > 2
        except (TypeError, ValueError):
          stale = False

      return {'status': 'ok', 'last_run': last_run, 'stale': stale}

    except Exception as exc:  # noqa: BLE001 — D-19 never-crash
      logger.warning(
        '[Web] /healthz load_state failed: %s: %s',
        type(exc).__name__,
        exc,
      )
      return {'status': 'ok', 'last_run': None, 'stale': False}
