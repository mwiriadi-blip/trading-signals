'''Phase 35 D-08 / D-09 — admin sub-router.

All routes on this router require admin role via require_admin dependency
injected at mount time (D-08). New admin routes: register on `router`,
not on `application` directly. The gate is inherited automatically.

Anti-pattern note: if a future contributor adds a route to `application`
instead of `router`, the Plan 05 startup invariant test catches it (it walks
app.routes and checks require_admin in each /admin/* route's dependency list).

Phase 36: adds GET /admin/users (list[PublicUserSummary]) and
PATCH /admin/users/{uid}/disable (toggle disabled flag).
'''
from fastapi import APIRouter, Depends, HTTPException

from web.dependencies import require_admin
from web.routes.admin._models import PublicUserSummary

router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])


@router.get('/ping')
def ping():
  '''D-09: non-vacuous startup invariant target. Returns 200 {"ok": true}.'''
  return {'ok': True}


@router.get('/users', response_model=list[PublicUserSummary])
def admin_list_users():
  '''Phase 36 RBAC-04 / D-07..D-11: return all users as PublicUserSummary.

  FastAPI response_model=list[PublicUserSummary] enforces field redaction
  automatically — paper_trades, equity_history, trade_log and all other
  per-user trade content are stripped before the response leaves the server
  (T-36-06: Information Disclosure mitigated).
  '''
  from auth_store import list_users
  from state_manager import load_state
  state = load_state()
  users_map = state.get('users', {})
  summaries = []
  for user in list_users():
    uid = user.get('uid', '')
    user_bucket = users_map.get(uid, {})
    positions = user_bucket.get('positions', {})
    has_active = any(v is not None for v in positions.values())
    status = 'disabled' if user.get('disabled') else 'active'
    summaries.append(PublicUserSummary(
      user_id=uid,
      display_name=user.get('email', ''),
      status=status,
      last_seen_date=None,  # deferred to Phase 37
      has_active_position=has_active,
    ))
  return summaries


@router.patch('/users/{uid}/disable')
def admin_disable_user(uid: str, disabled: bool = True):
  '''Phase 36 RBAC-04: toggle disabled flag on a user account.

  Returns 404 if uid is not found. Returns {"ok": True, "uid": ..., "disabled": ...}.
  Behind require_admin Depends on admin sub-router — non-admin gets 403 (T-36-08).
  '''
  from auth_store import set_user_disabled
  found = set_user_disabled(uid, disabled)
  if not found:
    raise HTTPException(status_code=404, detail=f'user {uid!r} not found')
  return {'ok': True, 'uid': uid, 'disabled': disabled}


__all__ = ['router']
