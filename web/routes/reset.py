'''Phase 16.1 Plan 03 — /reset-totp magic-link consumption route.

Implements F-02 token consumption + E-07 reset-mode handoff:

  GET /reset-totp?token=<...>
    Validates the magic-link token (signature + 1h expiry + sha256-hash
    match against an unconsumed pending_magic_links row). On success:
      - Flips consumed=True + consumed_at=<now-iso> atomically
      - Issues a one-time tsi_session cookie (12h TTL — same attrs as Plan 01)
      - 302 redirect to /enroll-totp?reset=1
      - Sets Referrer-Policy: no-referrer (T-16.1-25 mitigation)
    On failure (any of: missing token, bad signature, expired, already
    consumed, hash mismatch): 401 + same generic 'Reset link is no longer
    valid' page (no leak which failure mode per E-07).

Architecture (CLAUDE.md hex-lite):
  web/routes/reset.py is an adapter hex (peer of web/routes/login.py).
  Local imports of auth_store inside handlers per Phase 11/13 D-15
  hex-boundary convention. Module-top imports limited to: stdlib, fastapi,
  starlette, itsdangerous.

T-16.1-19 (Information Disclosure): the unhashed token NEVER touches
auth.json — only sha256(token). consume_magic_link sha256-hashes the
unhashed token on receive and compares.

T-16.1-20 (Spoofing): magic-link salt='magic-link' is unique vs all
tsi-*-cookie salts so a tsi_session token cannot be replayed against the
magic-link verifier and vice versa.

T-16.1-25 (Information Disclosure via referer): success response includes
Referrer-Policy: no-referrer header so the operator's browser doesn't leak
the (now-consumed) token to any cross-origin link clicked from the next
page in the flow.

Log prefix: [Web] — Phase 11 convention.
'''
import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer

from web.middleware.auth import _get_client_ip

logger = logging.getLogger(__name__)

RESET_PATH = '/reset-totp'

# Same cookie attrs as Plan 01 tsi_session — deletion attrs MUST match
# creation attrs (global LEARNING 'Cookie deletion must match cookie
# creation options'); this string is the canonical contract.
_COOKIE_ATTRS_CREATE_SESSION = (
  '; Max-Age=43200; Path=/; Secure; HttpOnly; SameSite=Strict'
)


def _render_invalid_link_page() -> str:
  '''Generic 'Reset link is no longer valid' page (E-07 + T-16.1-19/20/24).

  Single static page rendered for ALL failure modes (missing token, bad
  signature, expired, consumed, unknown hash) — operator cannot
  distinguish between failure types via response body, status, or timing.
  '''
  # Inline CSS — palette tokens mirror login.py / totp.py.
  css = '''
:root {
  --color-bg: #0f1117;
  --color-surface: #161a24;
  --color-border: #252a36;
  --color-text: #e5e7eb;
  --color-text-muted: #cbd5e1;
  --color-text-dim: #64748b;
  --color-short: #ef4444;
  --fs-body: 14px; --fs-label: 12px; --fs-display: 28px;
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
.invalid-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 32px;
  width: 100%;
  max-width: 360px;
  margin: 16px;
}
.invalid-card .eyebrow {
  font-size: var(--fs-label);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-dim);
  margin: 0 0 4px;
}
.invalid-card h1 {
  font-size: var(--fs-display);
  font-weight: 600;
  margin: 0 0 16px;
  color: var(--color-short);
}
.link-secondary {
  font-size: var(--fs-label);
  color: var(--color-text-dim);
  text-decoration: none;
  display: block;
  margin-top: 16px;
}
.link-secondary:hover { text-decoration: underline; }
'''
  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Reset link</title>
<style>{css}</style>
</head>
<body>
<main class="invalid-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Reset link is no longer valid</h1>
<p>This link has expired, has already been used, or is malformed. Request
a new one from the login page.</p>
<a href="/login" class="link-secondary">Back to sign in</a>
</main>
</body>
</html>
'''


def register(app: FastAPI) -> None:
  '''Register GET /reset-totp on the FastAPI app.

  Reads WEB_AUTH_SECRET at register-time (NOT module-top) per Phase 13
  D-18 testability convention.
  '''
  secret = os.environ.get('WEB_AUTH_SECRET', '').strip()

  magic_link_serializer = URLSafeTimedSerializer(secret, salt='magic-link')
  session_serializer = URLSafeTimedSerializer(secret, salt='tsi-session-cookie')

  def _invalid_response() -> Response:
    '''401 + generic page + Referrer-Policy: no-referrer (T-16.1-25).'''
    resp = HTMLResponse(
      content=_render_invalid_link_page(),
      status_code=401,
    )
    resp.headers['Referrer-Policy'] = 'no-referrer'
    return resp

  @app.get('/reset-totp')
  def get_reset_totp(request: Request) -> Response:
    token = request.query_params.get('token', '').strip()
    if not token:
      return _invalid_response()

    # 1. Signature + max_age check via itsdangerous.
    # SignatureExpired is a subclass of BadSignature — order matters
    # (LEGB rule + Plan 02 LEARNING).
    try:
      magic_link_serializer.loads(token, max_age=3600)
    except SignatureExpired:
      logger.info('[Web] reset-totp: signature expired')
      return _invalid_response()
    except BadSignature:
      logger.info('[Web] reset-totp: bad signature')
      return _invalid_response()

    # 2. Hash-match + atomic flip via auth_store.consume_magic_link.
    # Local import preserves hex boundary (Plan 01 pattern).
    import auth_store
    consumed, action = auth_store.consume_magic_link(token)
    if not consumed:
      logger.info('[Web] reset-totp: token not consumable (unknown/used/expired-row)')
      return _invalid_response()

    # 3. Issue one-time tsi_session and 302 → /enroll-totp?reset=1.
    if action != 'totp-reset':
      # Defensive — only known action is totp-reset; anything else is a
      # logic bug or schema drift. Render invalid page to be safe.
      logger.warning('[Web] reset-totp: unknown action=%s', action)
      return _invalid_response()

    username = os.environ.get('WEB_AUTH_USERNAME', '').strip()
    session_token = session_serializer.dumps({
      'u': username, 'iat': int(time.time()),
    })
    set_cookie = (
      f'tsi_session={session_token}{_COOKIE_ATTRS_CREATE_SESSION}'
    )
    logger.info(
      '[Web] magic-link consumed: action=%s ip=%s',
      action,
      _get_client_ip(request),
    )
    resp = Response(status_code=302)
    resp.headers['Location'] = '/enroll-totp?reset=1'
    # T-16.1-25: prevent the consumed token from leaking via Referer.
    resp.headers['Referrer-Policy'] = 'no-referrer'
    resp.raw_headers.append((b'set-cookie', set_cookie.encode('latin-1')))
    return resp
