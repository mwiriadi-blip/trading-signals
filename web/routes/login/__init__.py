'''Phase 30 Plan 05 — web/routes/login package.

Behaviour-preserving split of the original 608-LOC web/routes/login.py.
Render helpers + _is_safe_next live in _renderers.py (D-05 boundary).
This __init__.py owns register(app) and re-exports the public import surface
(D-03: _is_safe_next importable from web.routes.login for sibling route totp).
'''
import hmac
import logging
import os
import time

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response
from itsdangerous.url_safe import URLSafeTimedSerializer

from web.routes.login._renderers import (
  _is_safe_next,
  _log_login_failure,
  _render_check_email_page,
  _render_forgot_2fa_form,
  _render_login_form,
  _render_logout_confirmation,
)

logger = logging.getLogger(__name__)

LOGIN_PATH = '/login'
LOGOUT_PATH = '/logout'

_COOKIE_ATTRS_CREATE = '; Path=/; Secure; HttpOnly; SameSite=Strict'
_DELETION_ATTRS = '; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict'


def register(app: FastAPI) -> None:
  '''Register /login (GET, POST) + /logout (POST) on the FastAPI app.

  Reads WEB_AUTH_USERNAME + WEB_AUTH_SECRET at register-time (NOT module-top)
  per Phase 13 D-18 testability convention. create_app() in tests pops
  web.app from sys.modules then re-imports, so each test gets a fresh
  serializer pair built off the current monkeypatched env vars.
  '''
  username = os.environ.get('WEB_AUTH_USERNAME', '').strip()
  secret = os.environ.get('WEB_AUTH_SECRET', '').strip()

  session_serializer = URLSafeTimedSerializer(secret, salt='tsi-session-cookie')
  pending_serializer = URLSafeTimedSerializer(secret, salt='tsi-pending-cookie')
  enroll_serializer = URLSafeTimedSerializer(secret, salt='tsi-enroll-cookie')
  # Phase 16.1 Plan 03 F-02: magic-link signing salt — separate from all
  # tsi-*-cookie salts so a tsi_session token cannot be replayed against
  # the magic-link verifier and vice versa (RESEARCH §itsdangerous
  # salt-non-optional + T-16.1-20 mitigation).
  magic_link_serializer = URLSafeTimedSerializer(secret, salt='magic-link')

  @app.get('/login')
  def get_login(request: Request) -> HTMLResponse:
    next_value = request.query_params.get('next', '/')
    if not _is_safe_next(next_value):
      next_value = '/'
    return HTMLResponse(content=_render_login_form(next_value=next_value))

  @app.post('/login')
  def post_login(
    request: Request,
    username_in: str = Form(..., alias='username'),
    password_in: str = Form(..., alias='password'),
  ) -> Response:
    next_value = request.query_params.get('next', '/')
    if not _is_safe_next(next_value):
      next_value = '/'

    # 1. Validate username (constant-time)
    username_match = hmac.compare_digest(
      username_in.encode('utf-8'),
      username.encode('utf-8'),
    )
    # 2. Validate password (constant-time) — always run both compares to
    #    keep timing identical regardless of which fails (D-14 spirit).
    password_match = hmac.compare_digest(
      password_in.encode('utf-8'),
      secret.encode('utf-8'),
    )
    if not username_match:
      _log_login_failure(request, reason='wrong_username')
      return HTMLResponse(content=_render_login_form(
        next_value=next_value,
        error='Sign in failed',
        username_value=username_in,
      ))
    if not password_match:
      _log_login_failure(request, reason='wrong_secret')
      return HTMLResponse(content=_render_login_form(
        next_value=next_value,
        error='Sign in failed',
        username_value=username_in,
      ))

    # Branch on auth.json state per E-03 / E-04 (local import — hex boundary)
    import auth_store
    secret_on_file = auth_store.get_totp_secret()
    auth_data = auth_store.load_auth()
    enrolled = auth_data['totp_enrolled']

    iat = int(time.time())

    if secret_on_file is None:
      # E-03 first-login: generate fresh TOTP secret + persist + tsi_enroll
      import pyotp
      new_secret = pyotp.random_base32()
      auth_store.set_totp_secret(new_secret)
      enroll_token = enroll_serializer.dumps({
        'u': username_in, 'iat': iat, 'next': next_value,
      })
      logger.info('[Web] login success: enroll user=%s', username_in)
      return Response(
        status_code=302,
        headers={
          'Location': '/enroll-totp',
          'Set-Cookie': f'tsi_enroll={enroll_token}; Max-Age=600{_COOKIE_ATTRS_CREATE}',
        },
      )

    if enrolled:
      # E-04 subsequent-login: tsi_pending cookie + 302 /verify-totp
      pending_token = pending_serializer.dumps({
        'u': username_in, 'iat': iat, 'next': next_value, 'pwd_ok': True,
      })
      logger.info('[Web] login success: verify user=%s', username_in)
      return Response(
        status_code=302,
        headers={
          'Location': '/verify-totp',
          'Set-Cookie': f'tsi_pending={pending_token}; Max-Age=600{_COOKIE_ATTRS_CREATE}',
        },
      )

    # Partial enrollment (secret stored, not yet verified) — re-issue tsi_enroll
    enroll_token = enroll_serializer.dumps({
      'u': username_in, 'iat': iat, 'next': next_value,
    })
    logger.info('[Web] login success: enroll-resume user=%s', username_in)
    return Response(
      status_code=302,
      headers={
        'Location': '/enroll-totp',
        'Set-Cookie': f'tsi_enroll={enroll_token}; Max-Age=600{_COOKIE_ATTRS_CREATE}',
      },
    )

  @app.get('/forgot-2fa')
  def get_forgot_2fa() -> HTMLResponse:
    '''Phase 16.1 Plan 03 F-07: form mirror of /login for the recovery flow.

    Public route (in PUBLIC_PATHS — operator has no session at recovery
    time). No CSRF token: this endpoint always returns the same generic
    page regardless of cred validity (E-07), so a forged POST achieves
    nothing more than the legitimate flow already permits.
    '''
    return HTMLResponse(content=_render_forgot_2fa_form())

  @app.post('/forgot-2fa')
  def post_forgot_2fa(
    request: Request,
    username_in: str = Form(..., alias='username'),
    password_in: str = Form(..., alias='password'),
  ) -> HTMLResponse:
    '''Phase 16.1 Plan 03 F-02 + F-03 + F-08:
      1. Validate creds with hmac.compare_digest (BOTH compares always
         run — constant-time response shape per T-16.1-21).
      2. Per-account rate check via auth_store.count_recent_magic_links.
      3. If valid + under per-account limit + BASE_URL set: generate
         signed token, persist sha256(token), send email via Resend.
      4. ALWAYS render generic 'Check your email' page (no leak per E-07).
    '''
    # 1. Constant-time cred validation (BOTH compares always evaluated).
    username_match = hmac.compare_digest(
      username_in.encode('utf-8'), username.encode('utf-8'),
    )
    password_match = hmac.compare_digest(
      password_in.encode('utf-8'), secret.encode('utf-8'),
    )
    creds_ok = username_match and password_match

    # 2. Local imports preserve hex boundary (Plan 01 pattern).
    import hashlib
    from datetime import datetime, timedelta, timezone
    import auth_store
    import notifier as notifier_mod

    if not creds_ok:
      _log_login_failure(request, reason='forgot_2fa_wrong_creds')
      # Generic page (no leak per E-07 + T-16.1-21).
      return HTMLResponse(content=_render_check_email_page())

    # 3. Per-account rate check (F-08: max 3 magic links / 24h / account).
    recent_count = auth_store.count_recent_magic_links(within_seconds=86400)
    if recent_count >= 3:
      logger.warning(
        '[Web] forgot-2fa rate limited (per-account): count=%d',
        recent_count,
      )
      return HTMLResponse(content=_render_check_email_page())

    # 4. Opportunistic purge to keep auth.json bounded (housekeeping).
    auth_store.purge_expired_magic_links()

    # 5. BASE_URL guard — no localhost fallback per global LEARNING
    # 'Localhost fallbacks in URL construction break silently in production'.
    base_url = os.environ.get('BASE_URL', '').strip()
    if not base_url:
      logger.error(
        '[Web] BASE_URL env var not set — magic-link email skipped',
      )
      # Generic page anyway (no leak about misconfigured server).
      return HTMLResponse(content=_render_check_email_page())

    # 6. Generate token, persist sha256(token), email link.
    iat = int(time.time())
    token = magic_link_serializer.dumps({
      'purpose': 'totp-reset', 'iat': iat,
    })
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    expires_at = (
      datetime.now(timezone.utc) + timedelta(seconds=3600)
    ).isoformat()
    recovery_email = request.app.state.operator_recovery_email
    auth_store.add_magic_link(
      token_hash=token_hash,
      action='totp-reset',
      expires_at=expires_at,
      email=recovery_email,
    )
    link = f'{base_url}/reset-totp?token={token}'
    # Email failure NEVER crashes (CLAUDE.md "Email sends NEVER crash the
    # workflow"); send_magic_link_email returns SendStatus, we discard.
    notifier_mod.send_magic_link_email(
      to_email=recovery_email,
      link=link,
      action='totp-reset',
      expires_at=expires_at,
    )
    logger.info('[Web] forgot-2fa: magic-link generated for action=totp-reset')
    return HTMLResponse(content=_render_check_email_page())

  @app.post('/logout')
  def post_logout() -> Response:
    return Response(
      content=_render_logout_confirmation(),
      media_type='text/html; charset=utf-8',
      headers={
        'Set-Cookie': f'tsi_session={_DELETION_ATTRS}',
      },
    )


# D-03 import-surface preservation — sibling route module totp imports
# `_is_safe_next` directly from `web.routes.login` (was line 43 of
# web/routes/totp.py, now web/routes/totp/__init__.py). Re-export from the
# package so the import path is unchanged.
__all__ = ['register', '_is_safe_next']
