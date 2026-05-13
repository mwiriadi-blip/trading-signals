'''Phase 30 Plan 04 — web/routes/totp package __init__.py.

Holds register(app) exactly as before. Render helpers + _log_totp_failure +
_derive_device_label moved to _renderers.py (D-06 boundary, <=500 LOC each).

Cross-route dependency: _is_safe_next imported from web.routes.login per D-03
(Plan 30-05 re-exports _is_safe_next from web/routes/login/__init__.py).
'''
import logging
import os
import time

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer

from web.routes.login import _is_safe_next  # cross-route helper (D-03 dependency on Plan 30-05)
from web.routes.totp._renderers import (
  _derive_device_label,
  _log_totp_failure,
  _render_enroll_page,
  _render_enroll_reset_choice_page,
  _render_qr_data_uri,
  _render_verify_page,
)

logger = logging.getLogger(__name__)

ENROLL_PATH = '/enroll-totp'
VERIFY_PATH = '/verify-totp'

_COOKIE_ATTRS_CREATE_SESSION = '; Max-Age=43200; Path=/; Secure; HttpOnly; SameSite=Strict'
_COOKIE_ATTRS_DELETE = '; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict'
# Phase 16.1 Plan 02 — tsi_trusted attrs (E-05). 30-day TTL; same Path/Secure/
# HttpOnly/SameSite=Strict shape as tsi_session for deletion-attrs-match.
_COOKIE_ATTRS_CREATE_TRUSTED = '; Max-Age=2592000; Path=/; Secure; HttpOnly; SameSite=Strict'


def register(app: FastAPI) -> None:
  '''Register /enroll-totp + /verify-totp on the FastAPI app.

  Reads WEB_AUTH_USERNAME + WEB_AUTH_SECRET at register-time per Phase 13
  D-18 testability convention.
  '''
  username = os.environ.get('WEB_AUTH_USERNAME', '').strip()
  secret = os.environ.get('WEB_AUTH_SECRET', '').strip()

  session_serializer = URLSafeTimedSerializer(secret, salt='tsi-session-cookie')
  pending_serializer = URLSafeTimedSerializer(secret, salt='tsi-pending-cookie')
  enroll_serializer = URLSafeTimedSerializer(secret, salt='tsi-enroll-cookie')
  # Phase 16.1 Plan 02 — tsi_trusted (30d) issued when trust_device=on.
  trusted_serializer = URLSafeTimedSerializer(secret, salt='tsi-trusted-cookie')

  def _validate_enroll_cookie(request: Request) -> dict | None:
    token = request.cookies.get('tsi_enroll')
    if not token:
      return None
    try:
      payload = enroll_serializer.loads(token, max_age=600)
      return payload
    except SignatureExpired:
      return None
    except BadSignature:
      return None

  def _validate_session_cookie(request: Request) -> dict | None:
    '''Phase 16.1 Plan 03: ?reset=1 entry uses tsi_session (issued by
    /reset-totp) instead of tsi_enroll (post-/login). Same session_serializer +
    max_age=43200s as the rest of the auth path.
    '''
    token = request.cookies.get('tsi_session')
    if not token:
      return None
    try:
      payload = session_serializer.loads(token, max_age=43200)
      return payload if isinstance(payload, dict) else {'_': payload}
    except SignatureExpired:
      return None
    except BadSignature:
      return None

  def _validate_pending_cookie(request: Request) -> dict | None:
    token = request.cookies.get('tsi_pending')
    if not token:
      return None
    try:
      payload = pending_serializer.loads(token, max_age=600)
      return payload
    except SignatureExpired:
      return None
    except BadSignature:
      return None

  def _redirect_to_login() -> Response:
    return Response(status_code=302, headers={'Location': '/login'})

  def _make_session_cookie(uname: str, uid: str | None = None) -> str:
    # Phase 35 D-03: payload extended with uid. Old cookies (no uid) still
    # decode via _validate_session_cookie's isinstance guard (unchanged).
    token = session_serializer.dumps({'u': uname, 'uid': uid, 'iat': int(time.time())})
    return f'tsi_session={token}{_COOKIE_ATTRS_CREATE_SESSION}'

  def _provisioning_uri(secret_b32: str, uname: str) -> str:
    import pyotp
    _issuer = os.environ.get('TOTP_ISSUER', 'Trading Signals')
    _domain = os.environ.get('TOTP_DOMAIN', 'signals.mwiriadi.me')
    return pyotp.TOTP(secret_b32).provisioning_uri(
      name=f'{uname}@{_domain}',
      issuer_name=_issuer,
    )

  def _verify_code(secret_b32: str, code: str) -> bool:
    import pyotp
    if not code or len(code) != 6 or not code.isdigit():
      return False
    return pyotp.TOTP(secret_b32).verify(code, valid_window=1)

  @app.get('/enroll-totp')
  def get_enroll(request: Request) -> Response:
    # Phase 16.1 Plan 03: ?reset=1 mode — gated by tsi_session (just
    # consumed magic-link) instead of tsi_enroll (post-/login).
    if request.query_params.get('reset') == '1':
      if _validate_session_cookie(request) is None:
        return _redirect_to_login()
      return HTMLResponse(content=_render_enroll_reset_choice_page())

    # Plan 01 baseline: tsi_enroll-gated first-time enrollment.
    payload = _validate_enroll_cookie(request)
    if payload is None:
      return _redirect_to_login()
    import auth_store
    secret_b32 = auth_store.get_totp_secret()
    if secret_b32 is None:
      # No secret on file — operator stale-cookied; bounce to /login
      return _redirect_to_login()
    uri = _provisioning_uri(secret_b32, username)
    qr = _render_qr_data_uri(uri)
    return HTMLResponse(content=_render_enroll_page(qr, secret_b32))

  @app.post('/enroll-totp')
  def post_enroll(
    request: Request,
    code: str = Form(default=''),
    action: str = Form(default='verify'),
  ) -> Response:
    # Phase 16.1 Plan 03 E-07: ?reset=1 mode branches.
    if request.query_params.get('reset') == '1':
      session_payload = _validate_session_cookie(request)
      if session_payload is None:
        return _redirect_to_login()
      import auth_store
      if action == 'keep':
        # Operator keeps current authenticator — no auth.json change.
        # tsi_session already set by /reset-totp; just send them home.
        logger.info('[Web] totp reset: operator chose KEEP')
        return Response(status_code=302, headers={'Location': '/'})
      if action == 'new':
        # Regenerate secret + render fresh QR; operator must re-verify.
        import pyotp
        new_secret = pyotp.random_base32()
        auth_store.set_totp_secret(new_secret)  # also flips totp_enrolled=False
        logger.info('[Web] totp reset: operator chose NEW (secret regenerated)')
        uri = _provisioning_uri(new_secret, username)
        qr = _render_qr_data_uri(uri)
        # Re-render the standard enroll page (Plan 01 form posts to
        # /enroll-totp WITHOUT ?reset=1 — but this caller has tsi_session
        # already, not tsi_enroll. Issue a fresh tsi_enroll cookie here so
        # the subsequent verify-code POST hits the standard path.
        iat = int(time.time())
        enroll_token = enroll_serializer.dumps({
          'u': username, 'iat': iat, 'next': '/',
        })
        resp = HTMLResponse(content=_render_enroll_page(qr, new_secret))
        resp.raw_headers.append((
          b'set-cookie',
          f'tsi_enroll={enroll_token}; Max-Age=600; Path=/; Secure; '
          f'HttpOnly; SameSite=Strict'.encode('latin-1'),
        ))
        return resp
      # Unknown action in reset mode — bounce back to choice page.
      return HTMLResponse(content=_render_enroll_reset_choice_page())

    # Plan 01 baseline: code-verify path.
    payload = _validate_enroll_cookie(request)
    if payload is None:
      return _redirect_to_login()
    import auth_store
    secret_b32 = auth_store.get_totp_secret()
    if secret_b32 is None:
      return _redirect_to_login()
    if not _verify_code(secret_b32, code):
      _log_totp_failure(request, reason='wrong_code', path='/enroll-totp')
      uri = _provisioning_uri(secret_b32, username)
      qr = _render_qr_data_uri(uri)
      return HTMLResponse(
        content=_render_enroll_page(
          qr, secret_b32, error="Code didn't match — try again",
        ),
      )

    auth_store.mark_enrolled()
    next_value = payload.get('next', '/') if isinstance(payload, dict) else '/'
    if not _is_safe_next(next_value):
      next_value = '/'
    logger.info('[Web] totp enrollment success user=%s', username)
    # Phase 35 D-03: resolve uid so the cookie carries user_id for middleware.
    row = auth_store.get_user_by_email(username)
    uid = row['uid'] if row else None
    set_cookies = [
      _make_session_cookie(username, uid=uid),
      f'tsi_enroll={_COOKIE_ATTRS_DELETE}',
    ]
    # FastAPI Response only carries one Set-Cookie via headers dict — emit
    # multiple by joining with newline-delimited header pairs is non-standard;
    # use Response.raw_headers instead.
    resp = Response(status_code=302, headers={'Location': next_value})
    for sc in set_cookies:
      resp.raw_headers.append((b'set-cookie', sc.encode('latin-1')))
    return resp

  @app.get('/verify-totp')
  def get_verify(request: Request) -> Response:
    if _validate_pending_cookie(request) is None:
      return _redirect_to_login()
    return HTMLResponse(content=_render_verify_page())

  @app.post('/verify-totp')
  def post_verify(
    request: Request,
    code: str = Form(...),
    trust_device: str = Form(default=''),  # Plan 02: 'on' iff checkbox checked
  ) -> Response:
    payload = _validate_pending_cookie(request)
    if payload is None:
      return _redirect_to_login()
    import auth_store
    secret_b32 = auth_store.get_totp_secret()
    if secret_b32 is None:
      return _redirect_to_login()
    if not _verify_code(secret_b32, code):
      _log_totp_failure(request, reason='wrong_code', path='/verify-totp')
      return HTMLResponse(
        content=_render_verify_page(error="Code didn't match — try again"),
      )

    next_value = payload.get('next', '/') if isinstance(payload, dict) else '/'
    if not _is_safe_next(next_value):
      next_value = '/'
    logger.info('[Web] totp verify success user=%s', username)

    # Phase 35 D-03: resolve uid so the cookie carries user_id for middleware.
    row = auth_store.get_user_by_email(username)
    uid = row['uid'] if row else None
    # Build the cookie set: always tsi_session + delete tsi_pending; optionally
    # tsi_trusted when trust_device=on (Plan 02 E-04).
    cookies_to_set = [
      _make_session_cookie(username, uid=uid),
      f'tsi_pending={_COOKIE_ATTRS_DELETE}',
    ]
    if trust_device == 'on':
      from datetime import UTC, datetime
      xff = request.headers.get('x-forwarded-for', '')
      client_ip = (
        xff.split(',')[0].strip()
        if xff
        else (request.client.host if request.client else '-')
      )
      ua = request.headers.get('user-agent', '')
      granted_at_iso = datetime.now(UTC).isoformat()
      label = _derive_device_label(ua, client_ip, granted_at_iso)
      new_uuid = auth_store.add_trusted_device(label=label)
      trusted_token = trusted_serializer.dumps({
        'uuid': new_uuid, 'iat': int(time.time()),
      })
      cookies_to_set.append(
        f'tsi_trusted={trusted_token}{_COOKIE_ATTRS_CREATE_TRUSTED}'
      )
      logger.info(
        '[Web] trusted_device issued: uuid=%s label=%s', new_uuid, label,
      )

    resp = Response(status_code=302, headers={'Location': next_value})
    for sc in cookies_to_set:
      resp.raw_headers.append((b'set-cookie', sc.encode('latin-1')))
    return resp


# D-03 import-surface preservation — service layer + tests import `register`
# (and possibly other names) directly from `web.routes.totp`. Re-export
# from the package so the import path is unchanged.
__all__ = ['register']
