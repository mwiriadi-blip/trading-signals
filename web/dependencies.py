'''Phase 35 D-07 — FastAPI Depends() factories for authenticated routes.

This file is an adapter hex:
  Allowed imports: fastapi, starlette, stdlib, auth_store.
  Forbidden imports: signal_engine, data_fetcher, main.

403 detail strings locked per --reviews consensus #5:
  _DETAIL_NOT_AUTHENTICATED = 'Not authenticated'
  _DETAIL_ADMIN_REQUIRED    = 'Admin access required'
FastAPI's default exception handler for HTTPException returns
Content-Type: application/json with body {"detail": "<string>"}.
No custom handler is required. Plan 05 asserts the JSON schema end-to-end.
'''
from fastapi import HTTPException, Request
from auth_store import get_user

# --reviews #5: locked 403 detail strings; FastAPI renders body as {"detail": "<string>"}; Plan 05 asserts the JSON schema end-to-end.
_DETAIL_NOT_AUTHENTICATED = 'Not authenticated'
_DETAIL_ADMIN_REQUIRED = 'Admin access required'


def current_user_id(request: Request) -> str:
  '''Return the authenticated user id from request.state, or raise 403.

  Reads getattr(request.state, 'user_id', None) to handle PUBLIC_PATHS where
  middleware never set the attribute (avoids AttributeError on missing state).
  '''
  uid = getattr(request.state, 'user_id', None)
  if uid is None:
    raise HTTPException(status_code=403, detail=_DETAIL_NOT_AUTHENTICATED)
  return uid


def require_admin(request: Request) -> str:
  '''Return the authenticated admin user id, or raise 403.'''
  # Live read from auth.json — admin role revocation takes effect on next request.
  # Single auth.json read per gated request; acceptable at single-admin scale.
  uid = getattr(request.state, 'user_id', None)
  if uid is None:
    raise HTTPException(status_code=403, detail=_DETAIL_ADMIN_REQUIRED)
  row = get_user(uid)
  if row is None or row.get('role') != 'admin' or row.get('disabled'):
    raise HTTPException(status_code=403, detail=_DETAIL_ADMIN_REQUIRED)
  return uid
