'''Phase 16.1 Plan 01 Task 3a — /login + /logout routes.

Implements E-03 (first-login enrollment branch) + E-04 (subsequent-login
verify branch) of the cookie+TOTP login flow:

  GET /login        Renders the sign-in form (UI-SPEC §Surface 1).
  POST /login       Validates username + password via hmac.compare_digest;
                    on success, branches based on auth.json state:
                      totp_secret is None  → 302 /enroll-totp + tsi_enroll
                      totp_enrolled  True  → 302 /verify-totp + tsi_pending
                      otherwise (partial) → 302 /enroll-totp + tsi_enroll
                    On failure, re-renders with generic "Sign in failed"
                    error (D-14 + AUTH-02 spirit — no leaked info, no hints).
  POST /logout      Clears tsi_session with deletion attrs matching creation
                    (global LEARNING — cookie-deletion-must-match-creation).
                    Renders confirmation HTML.

Architecture (CLAUDE.md hex-lite):
  web/routes/login.py is an adapter hex (peer of web/routes/healthz.py).
  Local imports (auth_store, pyotp) inside handlers per Phase 11/13 D-15
  hex-boundary convention. Module-top imports limited to: stdlib, fastapi,
  starlette, itsdangerous.

T-16.1-11: every dynamic value rendered via inline f-string runs through
html.escape FIRST. Negative test in tests/test_web_routes_login.py asserts
&lt;script&gt; output never contains raw <script>.

Open-redirect prevention (T-16.1-07): _is_safe_next applies 8 guards before
allowing a `?next=` value. RESEARCH §Open-redirect 14-payload parametrize
test in tests/test_web_routes_login.py::TestLoginNextOpenRedirect.

Log prefix: [Web] — Phase 11 convention.
'''
import hmac
import logging
import os
import time
from html import escape as html_escape
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer

logger = logging.getLogger(__name__)

LOGIN_PATH = '/login'
LOGOUT_PATH = '/logout'

_COOKIE_ATTRS_CREATE = '; Path=/; Secure; HttpOnly; SameSite=Strict'
_DELETION_ATTRS = '; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict'

# Open-redirect prevention thresholds.
_MAX_NEXT_LEN = 512


def _is_safe_next(next_value) -> bool:
  '''Return True iff next_value is a safe relative path for 302-redirect.

  Guards (RESEARCH §Open-redirect prevention lines 426..458):
    1. Must be a string.
    2. Length cap (≤ _MAX_NEXT_LEN) to prevent DoS via giant cookie payloads.
    3. Must start with '/'.
    4. Must NOT start with '//' or '/\\' (protocol-relative bypass).
    5. Must NOT contain '\\' anywhere (Windows path separator + URL trick).
    6. Must NOT contain '://' (absolute-URL injection).
    7. Must NOT contain control characters (CRLF injection into Set-Cookie /
       Location headers).
    8. Empty string fails — fallback to '/'.
  '''
  if not isinstance(next_value, str):
    return False
  if not next_value:
    return False
  if len(next_value) > _MAX_NEXT_LEN:
    return False
  if not next_value.startswith('/'):
    return False
  if next_value.startswith('//') or next_value.startswith('/\\'):
    return False
  if '\\' in next_value:
    return False
  if '://' in next_value:
    return False
  for ch in next_value:
    if ord(ch) < 0x20 or ch == '\x7f':
      return False
  return True


# -----------------------------------------------------------------------------
# Inline CSS — copy of dashboard.py :root token block + login-specific rules.
# -----------------------------------------------------------------------------
# Note: f-string style with literal { } braces escaped as {{ }} where needed
# (this constant is itself a plain string, no f-string substitutions).

_LOGIN_INLINE_CSS = '''
:root {
  --color-bg: #0f1117;
  --color-surface: #161a24;
  --color-border: #252a36;
  --color-text: #e5e7eb;
  --color-text-muted: #cbd5e1;
  --color-text-dim: #64748b;
  --color-long: #22c55e;
  --color-short: #ef4444;
  --color-flat: #eab308;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-6: 24px; --space-8: 32px; --space-12: 48px;
  --fs-body: 14px; --fs-label: 12px; --fs-heading: 20px; --fs-display: 28px;
  --font-mono: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
}
* { box-sizing: border-box; }
body {
  background: var(--color-bg);
  color: var(--color-text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
               'Helvetica Neue', Arial, sans-serif;
  font-size: var(--fs-body);
  line-height: 1.5;
  margin: 0;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 32px;
  width: 100%;
  max-width: 360px;
  margin: 16px;
}
.login-card .eyebrow {
  font-size: var(--fs-label);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-dim);
  margin: 0 0 4px;
}
.login-card h1 {
  font-size: var(--fs-display);
  font-weight: 600;
  margin: 0 0 24px;
}
.login-form .field { margin-bottom: 16px; }
.login-form label {
  display: block;
  font-size: var(--fs-label);
  color: var(--color-text-muted);
  margin-bottom: 4px;
}
.login-form input {
  width: 100%;
  background: var(--color-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 10px 12px;
  font-size: var(--fs-body);
  font-family: inherit;
}
.login-form input:focus {
  outline: none;
  border-color: var(--color-text-muted);
}
.btn-primary {
  width: 100%;
  background: var(--color-long);
  color: var(--color-bg);
  border: none;
  border-radius: 4px;
  padding: 12px;
  font-size: var(--fs-body);
  font-weight: 600;
  cursor: pointer;
  margin-top: 8px;
}
.btn-primary:hover { filter: brightness(1.1); }
.error {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid var(--color-short);
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 16px;
}
.error-heading {
  margin: 0;
  color: var(--color-short);
  font-weight: 600;
}
.footnote {
  font-size: var(--fs-label);
  color: var(--color-text-dim);
  margin-top: 16px;
}
.link-secondary {
  font-size: var(--fs-label);
  color: var(--color-text-dim);
  text-decoration: none;
  display: block;
  margin-top: 12px;
  text-align: center;
}
.link-secondary:hover { text-decoration: underline; }
'''


def _render_login_form(
  next_value: str = '/', error: str | None = None, username_value: str = '',
) -> str:
  '''Inline HTML for GET /login + POST /login error re-render.

  Every dynamic value is HTML-escaped via html.escape before f-string
  substitution (T-16.1-11 mitigation).
  '''
  next_escaped = html_escape(next_value, quote=True)
  username_escaped = html_escape(username_value, quote=True)
  error_block = ''
  if error:
    error_block = (
      f'<div class="error" role="alert" aria-live="polite">'
      f'<p class="error-heading">{html_escape(error)}</p>'
      f'</div>'
    )
  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Sign in</title>
<style>{_LOGIN_INLINE_CSS}</style>
</head>
<body>
<main class="login-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Sign in</h1>
{error_block}
<form class="login-form" method="POST" action="/login?next={next_escaped}" autocomplete="on">
<div class="field">
<label for="login-username">Username</label>
<input id="login-username" name="username" type="text"
       autocomplete="username" required autofocus
       value="{username_escaped}">
</div>
<div class="field">
<label for="login-password">Password</label>
<input id="login-password" name="password" type="password"
       autocomplete="current-password" required>
</div>
<button type="submit" class="btn-primary">Sign in</button>
</form>
<a href="/forgot-2fa" class="link-secondary">Lost 2FA? Reset via email</a>
</main>
</body>
</html>
'''


def _render_logout_confirmation() -> str:
  '''Inline HTML for POST /logout confirmation page (UI-SPEC §Surface 2).'''
  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Signed out</title>
<style>{_LOGIN_INLINE_CSS}</style>
</head>
<body>
<main class="login-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Signed out</h1>
<p>You're signed out. <a href="/login">Sign in again</a>.</p>
<p class="footnote">Close all browser tabs to fully clear cached credentials.</p>
</main>
</body>
</html>
'''


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

  @app.post('/logout')
  def post_logout() -> Response:
    return Response(
      content=_render_logout_confirmation(),
      media_type='text/html; charset=utf-8',
      headers={
        'Set-Cookie': f'tsi_session={_DELETION_ATTRS}',
      },
    )


def _log_login_failure(request: Request, reason: str) -> None:
  '''[Web] login failure: ip=... ua=... reason=...

  Mirrors web.middleware.auth._log_failure shape. UA truncated to 120 chars,
  IP from XFF first entry with fallback to request.client.host.
  '''
  xff = request.headers.get('x-forwarded-for', '')
  client_ip = (
    xff.split(',')[0].strip()
    if xff
    else (request.client.host if request.client else '-')
  )
  ua = (request.headers.get('user-agent') or '')[:120]
  logger.warning(
    '[Web] login failure: ip=%s ua=%r reason=%s',
    client_ip,
    ua,
    reason,
  )


# Reference quote() so static-analysis tools see the import is intentional
# (the import is here for parity with middleware/auth.py's quoting in case
# this module needs URL-quoting in the future; keeping the symbol live).
_ = quote
