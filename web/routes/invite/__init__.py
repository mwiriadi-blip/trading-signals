'''Phase 37 D-04/D-05 — public unauthenticated invite acceptance wizard.

3-step flow:
  GET  /accept-invite?token=<raw>     → step-1 password page (validate without consuming)
  POST /accept-invite                 → validate password → bcrypt hash → consume + create user → /enroll-totp
  GET  /accept-invite/device          → transition step=totp → step=device, render step-3 page
  POST /accept-invite/device          → optional tsi_trusted cookie → clear wizard → /

ZERO COUPLING to web/routes/totp/__init__.py per review consensus #6 — the wizard
sets `next='/accept-invite/device'` in the tsi_enroll cookie payload and the
existing post-enroll handler at web/routes/totp/__init__.py line 203 reads
`payload.get('next', '/')` which handles the redirect. NO changes to totp module needed.

Review #1 (deployment blocker): this module's register() must be called in
web/app.py::create_app() BEFORE add_middleware(AuthMiddleware, ...).
'''
import hashlib
import logging
import os
import time

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer

from system_params import INVITE_WIZARD_TTL_SECONDS
from web.routes.invite._renderers import (
  _render_invite_error_page,
  _render_step1_password_page,
  _render_step3_device_page,
)

logger = logging.getLogger(__name__)

# Cookie name + serializer salt for the multi-step wizard cookie.
INVITE_WIZARD_SALT = 'tsi-invite-wizard'
# IN-03: sourced from system_params (single source of truth for all cookie TTLs).
_WIZARD_COOKIE_MAX_AGE = INVITE_WIZARD_TTL_SECONDS

# tsi_enroll salt mirrors web/routes/totp/__init__.py constant exactly (review #6 zero-coupling).
# The existing TOTP enroll handler reads tsi_enroll with this salt — we issue the cookie here
# so the invitee is accepted by /enroll-totp without any changes to the TOTP module.
_ENROLL_SALT = 'tsi-enroll-cookie'
_ENROLL_COOKIE_MAX_AGE = 600  # 10 min — mirrors existing totp constant

# tsi_trusted salt mirrors web/routes/totp/__init__.py constant + web/middleware/auth.py.
_TRUSTED_SALT = 'tsi-trusted-cookie'
_TRUSTED_COOKIE_MAX_AGE = 2592000  # 30 days — mirrors existing trusted-device TTL

# Cookie attribute strings — HttpOnly + Secure + SameSite=Strict (T-37-04-01 / T-37-04-03).
_COOKIE_ATTRS_WIZARD = '; Path=/; Secure; HttpOnly; SameSite=Strict'
_COOKIE_ATTRS_TRUSTED = '; Max-Age=2592000; Path=/; Secure; HttpOnly; SameSite=Strict'
_COOKIE_ATTRS_DELETE = '; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict'


def register(app: FastAPI) -> None:
  '''Register /accept-invite + /accept-invite/device on the FastAPI app.

  Called from web/app.py::create_app() BEFORE add_middleware(AuthMiddleware, ...)
  per Phase 13 D-06 invariant (review #1 deployment-blocker fix).

  Reads WEB_AUTH_SECRET at register-time per Phase 13 D-18 testability convention.
  '''
  secret = os.environ.get('WEB_AUTH_SECRET', '').strip()

  wizard_serializer = URLSafeTimedSerializer(secret, salt=INVITE_WIZARD_SALT)
  enroll_serializer = URLSafeTimedSerializer(secret, salt=_ENROLL_SALT)
  trusted_serializer = URLSafeTimedSerializer(secret, salt=_TRUSTED_SALT)

  def _validate_wizard_cookie(request: Request) -> dict | None:
    '''Mirror of _validate_enroll_cookie in web/routes/totp/__init__.py lines 55-66.

    Returns the decoded payload dict or None (expired or invalid or missing).
    '''
    token = request.cookies.get('tsi_invite_wizard')
    if not token:
      return None
    try:
      return wizard_serializer.loads(token, max_age=_WIZARD_COOKIE_MAX_AGE)
    except SignatureExpired:
      return None
    except BadSignature:
      return None

  def _set_wizard_cookie(payload: dict) -> str:
    '''Build a tsi_invite_wizard=<value>; Max-Age=...; ... cookie string.'''
    val = wizard_serializer.dumps(payload)
    return f'tsi_invite_wizard={val}; Max-Age={_WIZARD_COOKIE_MAX_AGE}{_COOKIE_ATTRS_WIZARD}'

  @app.get('/accept-invite')
  def get_accept_invite(request: Request, token: str = '') -> Response:
    '''D-04/D-05: validate raw token (peek without consuming) → render step-1 password page.

    D-07: expired/consumed/missing token → 200 HTML error page (NOT a redirect).
    No raw token in log (T-37-04-05 acceptance criterion).
    '''
    if not token:
      return HTMLResponse(
        content=_render_invite_error_page(),
        status_code=200,
      )

    import auth_store
    try:
      # _peek_invite_token validates without consuming — raises if expired/consumed.
      email = auth_store._peek_invite_token(token)
    except (auth_store.InviteAlreadyConsumed, auth_store.InviteExpired):
      # D-07: 200 HTML error page, NOT a redirect — same page for both error types
      # (timing oracle T-37-04-07 accepted — identical response).
      return HTMLResponse(
        content=_render_invite_error_page(),
        status_code=200,
      )

    # Token valid: set wizard cookie at step=password and render the form.
    # CR-02: store token_hash (not raw_token) in the signed cookie so
    # cookie exfiltration cannot replay the raw token. The raw token is
    # embedded as a hidden form field in the page (transient, not persisted).
    token_hash = 'sha256:' + hashlib.sha256(token.encode('utf-8')).hexdigest()
    payload = {'step': 'password', 'token_hash': token_hash, 'email': email}
    logger.info('[Invite] accept-invite peek ok email=%s', email)
    # NOTE: raw token NOT logged above — only email (T-37-04-05).

    resp = HTMLResponse(
      content=_render_step1_password_page(email, raw_token=token),
      status_code=200,
    )
    resp.raw_headers.append((
      b'set-cookie',
      _set_wizard_cookie(payload).encode('latin-1'),
    ))
    return resp

  @app.post('/accept-invite')
  def post_accept_invite(
    request: Request,
    password: str = Form(...),
    password2: str = Form(...),
    raw_token: str = Form(default=''),
  ) -> Response:
    '''Step 1 POST: validate password → bcrypt hash → consume token → create user → step 2.

    On success: wizard cookie updated to step=totp (raw_token dropped, uid added);
    tsi_enroll cookie issued with next='/accept-invite/device' (review #6 zero-coupling);
    302 to /enroll-totp.

    Password validation order (plan spec):
      1. Wizard cookie presence + step == 'password'
      2. Length >= 12 + match
      3. hash_password (catches ValueError for >72 bytes — review #9)
      4. consume_and_create_user (catches InviteAlreadyConsumed/InviteExpired — concurrent race)
    '''
    wizard_payload = _validate_wizard_cookie(request)
    if wizard_payload is None or wizard_payload.get('step') != 'password':
      # Step-skipping defense (T-37-04-02) or missing cookie.
      return Response(status_code=302, headers={'Location': '/login'})

    email = wizard_payload.get('email', '')

    # CR-02: validate raw_token from form matches token_hash in cookie.
    # Prevents cookie-replay attacks where a revoked invite's cookie is reused.
    expected_hash = 'sha256:' + hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
    if wizard_payload.get('token_hash') != expected_hash:
      return HTMLResponse(
        content=_render_invite_error_page(),
        status_code=400,
      )

    # Client-side length + match check — returns 400 with re-rendered form.
    if len(password) < 12:
      return HTMLResponse(
        content=_render_step1_password_page(
          email,
          raw_token=raw_token,
          error='Password must be at least 12 characters. Try again.',
        ),
        status_code=400,
      )
    if password != password2:
      return HTMLResponse(
        content=_render_step1_password_page(
          email,
          raw_token=raw_token,
          error='Passwords do not match. Try again.',
        ),
        status_code=400,
      )

    import auth_store

    # bcrypt hash — catches ValueError for >72 UTF-8 bytes (review #9).
    # Must NOT propagate as 500 (test_password_over_72_bytes_returns_400 pins this).
    try:
      pw_hash = auth_store.hash_password(password)
    except ValueError as ve:
      return HTMLResponse(
        content=_render_step1_password_page(
          email,
          raw_token=raw_token,
          error=f'Password is too long (must be ≤72 bytes). {ve}',
        ),
        status_code=400,
      )

    # Consume invite + create user (flock-guarded in auth_store).
    # Catch concurrent race: another request may have consumed the token.
    try:
      new_user = auth_store.consume_and_create_user(
        raw_token,
        {'email': email, 'role': 'ff'},
        password_hash=pw_hash,
      )
    except (auth_store.InviteAlreadyConsumed, auth_store.InviteExpired):
      # Review #2 degraded path: token was consumed by a concurrent request.
      return HTMLResponse(
        content=_render_invite_error_page(),
        status_code=200,
      )

    uid = new_user['uid']
    logger.info('[Invite] user created email=%s uid=%s', email, uid)

    # Issue TWO set-cookie headers (review #6 + step transition):
    #   (a) wizard cookie: step=totp (raw_token dropped — it has been consumed)
    #   (b) tsi_enroll cookie: payload includes next='/accept-invite/device'
    #       The existing TOTP enroll handler at web/routes/totp/__init__.py line 203
    #       reads payload.get('next', '/') and redirects there after enrollment.
    #       ZERO changes to the TOTP module needed (review consensus #6).

    wizard_step2_payload = {'step': 'totp', 'uid': uid, 'email': email}
    wizard_cookie_str = _set_wizard_cookie(wizard_step2_payload)

    # tsi_enroll payload: mirrors existing schema (uid, email) + adds next field (review #6).
    enroll_payload = {
      'uid': uid,
      'email': email,
      'next': '/accept-invite/device',  # review #6: existing line-203 reader consumes this
    }
    enroll_val = enroll_serializer.dumps(enroll_payload)
    enroll_cookie_str = (
      f'tsi_enroll={enroll_val}; Max-Age={_ENROLL_COOKIE_MAX_AGE}{_COOKIE_ATTRS_WIZARD}'
    )

    resp = Response(status_code=302, headers={'Location': '/enroll-totp'})
    for sc in [wizard_cookie_str, enroll_cookie_str]:
      resp.raw_headers.append((b'set-cookie', sc.encode('latin-1')))
    return resp

  @app.get('/accept-invite/device')
  def get_invite_device(request: Request) -> Response:
    '''Wizard step transition: step=totp → step=device.

    After TOTP enrollment, the existing totp post-enroll handler redirects to
    /accept-invite/device (via the next field in tsi_enroll cookie — review #6).
    The wizard cookie is still at step=totp at this point (TOTP module does not
    touch the wizard cookie — zero coupling per review #6).

    This GET handler: if wizard cookie step=totp, re-issue at step=device and
    render the step-3 trust-device page. If step=device already (browser refresh),
    re-render step-3. Any other state → 302 /login.
    '''
    wizard_payload = _validate_wizard_cookie(request)
    if wizard_payload is None:
      return Response(status_code=302, headers={'Location': '/login'})

    step = wizard_payload.get('step')
    if step not in ('totp', 'device'):
      return Response(status_code=302, headers={'Location': '/login'})

    uid = wizard_payload.get('uid', '')
    email = wizard_payload.get('email', '')

    # Transition to step=device (idempotent if already device).
    device_payload = {'step': 'device', 'uid': uid, 'email': email}
    resp = HTMLResponse(
      content=_render_step3_device_page(),
      status_code=200,
    )
    resp.raw_headers.append((
      b'set-cookie',
      _set_wizard_cookie(device_payload).encode('latin-1'),
    ))
    return resp

  @app.post('/accept-invite/device')
  def post_invite_device(
    request: Request,
    trust_device: str = Form(default=''),
  ) -> Response:
    '''Step 3 POST: optional tsi_trusted cookie → clear wizard cookie → 302 /.

    Validates wizard cookie at step=device (step-skipping defense T-37-04-02).
    If trust_device is truthy ('1', 'on', 'true'): issue tsi_trusted cookie
    mirroring the existing TOTP trusted-device pattern (same payload shape).
    Always: delete tsi_invite_wizard cookie (Max-Age=0). Return 302 /.
    '''
    wizard_payload = _validate_wizard_cookie(request)
    if wizard_payload is None or wizard_payload.get('step') != 'device':
      return Response(status_code=302, headers={'Location': '/login'})

    uid = wizard_payload.get('uid', '')
    cookies_to_set = [
      f'tsi_invite_wizard={_COOKIE_ATTRS_DELETE}',
    ]

    # Issue tsi_trusted if trust_device is truthy — mirror totp post_verify lines 261-281.
    # Payload shape: {'uuid': new_uuid, 'iat': timestamp} — same as the existing trusted-device
    # path so the auth middleware's _refuse_revoked_uuid check works without changes.
    if trust_device in ('1', 'on', 'true', 'yes'):
      import auth_store
      from datetime import UTC, datetime
      xff = request.headers.get('x-forwarded-for', '')
      client_ip = (
        xff.split(',')[0].strip()
        if xff
        else (request.client.host if request.client else '-')
      )
      ua = request.headers.get('user-agent', '')
      granted_at_iso = datetime.now(UTC).isoformat()
      # Build a human-readable device label (reuse totp pattern).
      label = f'Invite · {client_ip} · {granted_at_iso.split("T")[0]}'
      new_uuid = auth_store.add_trusted_device(label=label)
      trusted_token = trusted_serializer.dumps({
        'uuid': new_uuid, 'iat': int(time.time()),
      })
      cookies_to_set.append(f'tsi_trusted={trusted_token}{_COOKIE_ATTRS_TRUSTED}')
      logger.info('[Invite] trusted_device issued uid=%s uuid=%s', uid, new_uuid)

    logger.info('[Invite] wizard complete uid=%s', uid)
    resp = Response(status_code=302, headers={'Location': '/'})
    for sc in cookies_to_set:
      resp.raw_headers.append((b'set-cookie', sc.encode('latin-1')))
    return resp


__all__ = ['register']
