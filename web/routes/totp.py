'''Phase 16.1 Plan 01 Task 3b — /enroll-totp + /verify-totp routes.

Implements TOTP enrollment (E-03) + TOTP verification (E-04):

  GET  /enroll-totp     Gated by tsi_enroll cookie (issued post-login when
                        auth.json.totp_secret is None). Renders QR code +
                        manual-entry secret + 6-digit input.
  POST /enroll-totp     Validates 6-digit code via pyotp.TOTP(secret).verify
                        (valid_window=1 → ±30s clock drift). On success:
                        auth_store.mark_enrolled() + Set-Cookie tsi_session
                        (12h) + delete tsi_enroll (attrs match creation) +
                        302 to next (sanitised). On failure: re-render with
                        generic error.
  GET  /verify-totp     Gated by tsi_pending cookie (issued post-login when
                        auth.json.totp_enrolled is True). Renders 6-digit
                        input + "trust this device" checkbox (default
                        UNCHECKED — Plan 02 wires the checkbox value).
  POST /verify-totp     Validates 6-digit code; success → tsi_session +
                        delete tsi_pending + 302 to next.

Architecture (CLAUDE.md hex-lite):
  Local imports of auth_store, pyotp, qrcode inside handlers per Phase 11/13
  D-15 hex-boundary convention. No Jinja2.

T-16.1-08: server-side TOTP brute-force surface is 10⁶ codes per 90s window
(valid_window=1 = ±30s). Plan 03 adds rate limiting (5 attempts / 15 min on
verify POST). Plan 01 logs [Web] totp failure: ... reason=... so Plan 03 can
tune the threshold from real observation.

Log prefix: [Web] — Phase 11 convention.
'''
import base64
import io
import logging
import os
import time

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer

logger = logging.getLogger(__name__)

ENROLL_PATH = '/enroll-totp'
VERIFY_PATH = '/verify-totp'

_COOKIE_ATTRS_CREATE_SESSION = '; Max-Age=43200; Path=/; Secure; HttpOnly; SameSite=Strict'
_COOKIE_ATTRS_DELETE = '; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict'

# Reuse the open-redirect validator from web.routes.login (same shape, single
# source of truth — no separate copy here).


def _is_safe_next(next_value) -> bool:
  if not isinstance(next_value, str) or not next_value:
    return False
  if len(next_value) > 512:
    return False
  if not next_value.startswith('/'):
    return False
  if next_value.startswith('//') or next_value.startswith('/\\'):
    return False
  if '\\' in next_value or '://' in next_value:
    return False
  for ch in next_value:
    if ord(ch) < 0x20 or ch == '\x7f':
      return False
  return True


# Inline CSS — same token block as login.py. Locked subset of UI-SPEC §Surface
# (palette tokens + form rules + extra .qr-code rule for the enrollment image).
_TOTP_INLINE_CSS = '''
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
.totp-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 32px;
  width: 100%;
  max-width: 420px;
  margin: 16px;
}
.totp-card .eyebrow {
  font-size: var(--fs-label);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-dim);
  margin: 0 0 4px;
}
.totp-card h1 {
  font-size: var(--fs-display);
  font-weight: 600;
  margin: 0 0 16px;
}
.totp-card p { color: var(--color-text-muted); }
.qr-frame {
  background: #fff;
  padding: 12px;
  border-radius: 8px;
  display: flex;
  justify-content: center;
  margin: 16px 0;
}
.qr-frame img { display: block; max-width: 220px; }
.manual-secret {
  font-family: var(--font-mono);
  font-size: var(--fs-body);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 8px 12px;
  word-break: break-all;
  user-select: all;
  margin: 8px 0 16px;
}
.totp-form .field { margin-bottom: 16px; }
.totp-form label {
  display: block;
  font-size: var(--fs-label);
  color: var(--color-text-muted);
  margin-bottom: 4px;
}
.totp-form input[type="text"] {
  width: 100%;
  background: var(--color-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 10px 12px;
  font-size: var(--fs-heading);
  font-family: var(--font-mono);
  letter-spacing: 0.2em;
  text-align: center;
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
.checkbox-row { margin: 12px 0; display: flex; gap: 8px; align-items: center; }
'''


def _render_qr_data_uri(provisioning_uri: str) -> str:
  '''pyotp provisioning URI → PNG data URI for inline <img> tag.

  Uses qrcode.make() which returns a PIL Image (pillow required per
  BLOCKER-03 fix in requirements.txt).
  '''
  import qrcode
  img = qrcode.make(provisioning_uri)
  buf = io.BytesIO()
  img.save(buf, format='PNG')
  return f'data:image/png;base64,{base64.b64encode(buf.getvalue()).decode("ascii")}'


def _render_enroll_page(
  qr_data_uri: str, manual_secret: str, error: str | None = None,
) -> str:
  error_block = ''
  if error:
    error_block = (
      f'<div class="error" role="alert" aria-live="polite">'
      f'<p class="error-heading">{error}</p>'
      f'</div>'
    )
  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Set up 2FA</title>
<style>{_TOTP_INLINE_CSS}</style>
</head>
<body>
<main class="totp-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Set up 2FA</h1>
{error_block}
<p>Scan the QR code with your authenticator app (Google Authenticator,
1Password, Authy), then enter the 6-digit code below to finish.</p>
<div class="qr-frame">
<img src="{qr_data_uri}" alt="QR code for TOTP enrollment" width="220" height="220">
</div>
<p>Or enter this secret manually:</p>
<p class="manual-secret">{manual_secret}</p>
<form class="totp-form" method="POST" action="/enroll-totp" autocomplete="off">
<div class="field">
<label for="totp-code">6-digit code</label>
<input id="totp-code" name="code" type="text" inputmode="numeric"
       autocomplete="one-time-code" pattern="[0-9]{{6}}" maxlength="6"
       required autofocus>
</div>
<button type="submit" class="btn-primary">Verify and finish</button>
</form>
</main>
</body>
</html>
'''


def _render_verify_page(error: str | None = None) -> str:
  error_block = ''
  if error:
    error_block = (
      f'<div class="error" role="alert" aria-live="polite">'
      f'<p class="error-heading">{error}</p>'
      f'</div>'
    )
  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Verify 2FA</title>
<style>{_TOTP_INLINE_CSS}</style>
</head>
<body>
<main class="totp-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Verify 2FA</h1>
{error_block}
<p>Enter the 6-digit code from your authenticator app.</p>
<form class="totp-form" method="POST" action="/verify-totp" autocomplete="off">
<div class="field">
<label for="totp-code">6-digit code</label>
<input id="totp-code" name="code" type="text" inputmode="numeric"
       autocomplete="one-time-code" pattern="[0-9]{{6}}" maxlength="6"
       required autofocus>
</div>
<div class="checkbox-row">
<input id="trust-device" name="trust_device" type="checkbox" value="1">
<label for="trust-device">Trust this device for 30 days</label>
</div>
<button type="submit" class="btn-primary">Verify</button>
</form>
</main>
</body>
</html>
'''


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

  def _make_session_cookie(uname: str) -> str:
    token = session_serializer.dumps({'u': uname, 'iat': int(time.time())})
    return f'tsi_session={token}{_COOKIE_ATTRS_CREATE_SESSION}'

  def _provisioning_uri(secret_b32: str, uname: str) -> str:
    import pyotp
    return pyotp.TOTP(secret_b32).provisioning_uri(
      name=f'{uname}@signals.mwiriadi.me',
      issuer_name='Trading Signals',
    )

  def _verify_code(secret_b32: str, code: str) -> bool:
    import pyotp
    if not code or len(code) != 6 or not code.isdigit():
      return False
    return pyotp.TOTP(secret_b32).verify(code, valid_window=1)

  @app.get('/enroll-totp')
  def get_enroll(request: Request) -> Response:
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
    request: Request, code: str = Form(...),
  ) -> Response:
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
    set_cookies = [
      _make_session_cookie(username),
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
    trust_device: str = Form(default=''),  # Plan 02 wires the value
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
    resp = Response(status_code=302, headers={'Location': next_value})
    for sc in (
      _make_session_cookie(username),
      f'tsi_pending={_COOKIE_ATTRS_DELETE}',
    ):
      resp.raw_headers.append((b'set-cookie', sc.encode('latin-1')))
    return resp


def _log_totp_failure(request: Request, reason: str, path: str) -> None:
  '''[Web] totp failure: ip=... ua=... path=... reason=...

  Plan 03 reads these to tune the rate-limit threshold (T-16.1-08).
  '''
  xff = request.headers.get('x-forwarded-for', '')
  client_ip = (
    xff.split(',')[0].strip()
    if xff
    else (request.client.host if request.client else '-')
  )
  ua = (request.headers.get('user-agent') or '')[:120]
  logger.warning(
    '[Web] totp failure: ip=%s ua=%r path=%s reason=%s',
    client_ip, ua, path, reason,
  )
