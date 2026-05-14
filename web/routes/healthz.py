'''GET /healthz — Phase 11 WEB-07 + D-13..D-19.
GET /healthz/last-cycle — Phase 37 D-15 (admin-gated via require_admin Depends).

/healthz response schema:
  {'status':'ok', 'last_run':<YYYY-MM-DD str|null>, 'stale':<bool>}

/healthz/last-cycle response schema (review consensus #5 — 7-key last_cycle schema):
  {'status':'ok', 'date':<str|null>, 'total':<int>, 'ok':<int>,
   'failed':<int>, 'users':<list>, 'errors':<list>, 'crash':<str|null>}

Contract (CONTEXT.md 2026-04-24 reconciled post-REVIEWS HIGH #1):
  D-13: last_run is a DATE-ONLY ISO string ('YYYY-MM-DD'), matching
        what main.py:1042 writes via state['last_run'] = run_date_iso.
  D-14: always HTTP 200 if process is alive.
  D-15: last_run from state_manager.load_state() — local import (C-2).
        Phase 37 D-15: /healthz/last-cycle also uses load_state, admin-gated.
  D-16: stale=True iff (now.date() - last_run_date).days > 2. Handler
        uses date.fromisoformat (date-only, REVIEWS HIGH #1).
  D-19: NEVER non-200; on exception, return degraded body + WARN [Web].
'''
import logging

from fastapi import Depends, FastAPI, Request

logger = logging.getLogger(__name__)


def _require_admin_local(request: Request) -> str:
  '''Local admin gate for /healthz/last-cycle (T-37-05-06).

  Declared as a FastAPI dependency (receives Request via injection).
  Uses function-local import of require_admin (C-2 local-import discipline).
  Admin-gated: non-admin gets 403 (T-37-05-06 mitigated).
  '''
  from web.dependencies import require_admin
  return require_admin(request)


def register(app: FastAPI) -> None:
  '''Register GET /healthz + GET /healthz/last-cycle on the given FastAPI instance.'''

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

  @app.get('/healthz/last-cycle')
  def healthz_last_cycle(
    _: str = Depends(_require_admin_local),
  ) -> dict:
    '''Phase 37 D-15: return last fan-out cycle data (admin-gated).

    Returns 7-key last_cycle schema per review consensus #5:
      {'status':'ok', 'date':<str|null>, 'total':<int>, 'ok':<int>,
       'failed':<int>, 'users':<list>, 'errors':<list>, 'crash':<str|null>}

    Admin-gated via explicit Depends(require_admin) (T-37-05-06).
    Never crashes (D-19): on exception, returns empty 7-key schema.
    '''
    try:
      from state_manager import load_state
      state = load_state()
      lc = state.get('last_cycle')
      if lc is None:
        return {
          'status': 'ok',
          'date': None,
          'total': 0,
          'ok': 0,
          'failed': 0,
          'users': [],
          'errors': [],
          'crash': None,
        }
      # REVIEW #5: return the 7-key schema directly; defensive .get() for legacy data
      return {
        'status': 'ok',
        'date': lc.get('date'),
        'total': lc.get('total', 0),
        'ok': lc.get('ok', 0),
        'failed': lc.get('failed', 0),
        'users': lc.get('users', []),
        'errors': lc.get('errors', []),
        'crash': lc.get('crash'),
      }
    except Exception:  # noqa: BLE001 — never crash healthz (D-19)
      return {
        'status': 'ok',
        'date': None,
        'total': 0,
        'ok': 0,
        'failed': 0,
        'users': [],
        'errors': [],
        'crash': None,
      }
