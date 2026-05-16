'''Phase 35 D-08 / D-09 — admin sub-router.

All routes on this router require admin role via require_admin dependency
injected at mount time (D-08). New admin routes: register on `router`,
not on `application` directly. The gate is inherited automatically.

Anti-pattern note: if a future contributor adds a route to `application`
instead of `router`, the Plan 05 startup invariant test catches it (it walks
app.routes and checks require_admin in each /admin/* route's dependency list).

Phase 36: adds GET /admin/users (list[PublicUserSummary]) and
PATCH /admin/users/{uid}/disable (toggle disabled flag).

Phase 37 Plan 05:
  GET /admin/users — extended with Accept-header negotiation per review #8.
    Accept-header precedence per review consensus #8:
    HX-Request: true → HTML fragment; Accept: application/json → JSON list;
    else → full HTML page.
  POST /admin/invites — mints invite token + sends email (review #10 —
    send_invite_email imported from per_user_fanout, NOT notifier.dispatch).
  DELETE /admin/invites/{token_hash} — revokes a pending invite.
  Note: GET /healthz/last-cycle is NOT in admin router — it lives in
    web/routes/healthz.py per D-15 (plan spec: standalone route).
'''
import json
import logging
import os
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from web.dependencies import current_user_id, require_admin
from web.routes.admin._models import (
  PublicUserSummary,
  _compute_last_seen_date,
)
from web.routes.admin._renderers import (
  _render_admin_users_html_fragment,
  _render_admin_users_page,
  _render_invite_url_fragment,
)

logger = logging.getLogger(__name__)

# WR-01: basic email format guard at the invite route boundary.
_INVITE_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])


@router.get('/ping')
def ping():
  '''D-09: non-vacuous startup invariant target. Returns 200 {"ok": true}.'''
  return {'ok': True}


@router.get('/trades/full')
def admin_trades_full(user_id: str = Depends(current_user_id)):
  '''D-06: download full trade log for the authenticated user (tenant-scoped).

  Resolves user_id from session only — no query-param override, no cross-user
  iteration. require_admin on the router enforces auth before this handler runs.
  '''
  from state_manager import load_state
  state = load_state()
  trade_log = state.get('users', {}).get(user_id, {}).get('trade_log', [])
  date_str = datetime.now(UTC).strftime('%Y-%m-%d')
  body = json.dumps({'user_id': user_id, 'trade_log': trade_log})
  return Response(
    content=body,
    media_type='application/json',
    headers={
      'Content-Disposition': f'attachment; filename="trades-{user_id}-{date_str}.json"',
    },
  )


@router.get('/users')
def admin_list_users(request: Request):
  '''Phase 36 RBAC-04 / D-07..D-11 + Phase 37 review #8.

  Accept-header precedence per review consensus #8:
  HX-Request: true → HTML fragment (HTMX takes precedence over Accept);
  Accept: application/json → JSON list[PublicUserSummary] (Phase 36 JSON
  backward-compat); else → full HTML page (covers Accept: text/html and
  unspecified).

  FastAPI response_model is NOT set here because we branch on content-type.
  JSON path returns a list, both HTML paths return HTMLResponse.
  '''
  from auth_store import list_pending_invites, list_users
  from auth_store._io import load_auth
  from state_manager import load_state
  state = load_state()
  users_map = state.get('users', {})
  auth_data = load_auth()
  # Build per-user device list from users rows (v2 schema: auth_data.users[].uid)
  # IN-01: removed dead `user_devices` dict + empty for-loop (never populated or read).
  uid_to_user_row: dict = {u.get('uid', ''): u for u in auth_data.get('users', [])}

  summaries = []
  for user in list_users():
    uid = user.get('uid', '')
    user_bucket = users_map.get(uid, {})
    positions = user_bucket.get('positions', {})
    has_active = any(v is not None for v in positions.values())
    status = 'disabled' if user.get('disabled') else 'active'
    # Phase 37: last_seen_date from trusted devices (TrustedDevice.last_seen)
    # auth.json v2 stores trusted_devices at the top level (not per-user).
    # Filter by matching uid via a get_user lookup would need per-user device list.
    # In the current schema, trusted_devices are global; last_seen per device is
    # tracked but not per-uid. Use the full list per user row as best-effort.
    # Phase 37 workaround: scan all trusted devices (global list) — for single-admin
    # scale this is acceptable. Full per-user device tracking is future work.
    devices = auth_data.get('trusted_devices', [])
    last_seen = _compute_last_seen_date(devices)
    summaries.append(PublicUserSummary(
      user_id=uid,
      display_name=user.get('email', ''),
      status=status,
      last_seen_date=last_seen,
      has_active_position=has_active,
    ))

  # Accept-header precedence per review consensus #8:
  # HX-Request first (HTMX takes precedence over Accept), then JSON, then HTML fallback.
  if request.headers.get('HX-Request') == 'true':
    try:
      pending = list_pending_invites()
    except Exception:  # noqa: BLE001
      pending = []
    return HTMLResponse(_render_admin_users_html_fragment(summaries, pending))
  accept = request.headers.get('accept', '')
  if 'application/json' in accept:
    return summaries  # Phase 36 JSON response_model behaviour
  # default: full HTML page (covers Accept: text/html and unspecified)
  try:
    pending = list_pending_invites()
  except Exception:  # noqa: BLE001
    pending = []
  return HTMLResponse(_render_admin_users_page(summaries, pending))


@router.patch('/users/{uid}/disable')
def admin_disable_user(uid: str, disabled: bool = Form(default=True)):
  '''Phase 36 RBAC-04: toggle disabled flag on a user account.

  CR-04: disabled sourced from form body (not query string) so
  PATCH /admin/users/{uid}/disable?disabled=false cannot bypass the intent.
  Returns 404 if uid is not found. Returns {"ok": True, "uid": ..., "disabled": ...}.
  Behind require_admin Depends on admin sub-router — non-admin gets 403 (T-36-08).
  '''
  from auth_store import set_user_disabled
  found = set_user_disabled(uid, disabled)
  if not found:
    raise HTTPException(status_code=404, detail=f'user {uid!r} not found')
  return {'ok': True, 'uid': uid, 'disabled': disabled}


@router.post('/invites')
def admin_issue_invite(
  request: Request,
  email: str = Form(...),
  admin_uid: str = Depends(current_user_id),
):
  '''Phase 37: mint invite token + send invite email (review #10).

  REVIEW #10: send_invite_email is imported from per_user_fanout (NOT
  notifier.dispatch). This is the authoritative import path per plan spec.

  Logs [Invite] issued_by_admin=<uid> to_email=<email> at INFO.
  MUST NOT log the raw invite token.
  '''
  from auth_store import mint_invite_token
  # REVIEW #10: import send_invite_email from per_user_fanout (NOT notifier)
  from per_user_fanout import send_invite_email

  logger.info('[Invite] POST received admin_uid=%s email=%s', admin_uid or 'NONE', email)

  # WR-01: validate email format before minting token.
  if not _INVITE_EMAIL_RE.match(email):
    logger.warning('[Invite] rejected invalid email=%s', email)
    raise HTTPException(status_code=422, detail='Invalid email address')

  # WR-02: admin_uid must be set — trusted-device sessions return None from current_user_id.
  if not admin_uid:
    raise HTTPException(
      status_code=403,
      detail='Cannot determine admin identity; re-login with TOTP session',
    )

  base_url = os.environ.get('BASE_URL', '').strip()
  if not base_url:
    logger.error('[Invite] BASE_URL not configured — invite cannot be issued')
    raise HTTPException(status_code=500, detail='BASE_URL not configured')

  raw_token, expires_at = mint_invite_token(invited_by_uid=admin_uid, email=email)
  invite_url = f'{base_url}/accept-invite?token={raw_token}'

  logger.info('[Invite] issued by_admin=%s to_email=%s', admin_uid, email)

  # send_invite_email is never-raise — call unconditionally
  send_invite_email(to_email=email, invite_url=invite_url)

  # CR-01: raw token NOT embedded in HTML response — confirmation only.
  # HTMX: HX-Redirect causes the browser to navigate to /admin/users/ after the
  # request completes, refreshing the pending invites table.
  resp = HTMLResponse(_render_invite_url_fragment(email, expires_at))
  resp.headers['HX-Redirect'] = '/admin/users/'
  return resp


@router.delete('/invites/{token_hash}')
def admin_revoke_invite(token_hash: str):
  '''Phase 37: revoke a pending invite by token_hash.

  Returns 404 if no unconsumed row matches token_hash.
  Returns {"ok": True, "token_hash": ...} on success.
  Behind require_admin Depends on admin sub-router (T-37-05-01).
  '''
  from auth_store import revoke_invite
  found = revoke_invite(token_hash)
  if not found:
    raise HTTPException(status_code=404, detail='invite not found')
  # HTMX swaps this into the <tr> with outerHTML — empty string removes the row.
  return HTMLResponse('', status_code=200)


__all__ = ['router']
