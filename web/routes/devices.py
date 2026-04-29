'''Phase 16.1 Plan 02 Task 4 — /devices route (E-06 + E-08).

Implements the operator-facing trusted-device management page:

  GET  /devices               Renders the trusted_devices table — Label,
                              Granted, Last seen, Revoke button (active rows
                              only). Marks the current device when tsi_trusted
                              is present. Cookie-session-only — header-only
                              auth returns 403 (E-06).
  POST /devices/revoke        Form field `uuid` → flips revoked=True on that
                              row in auth.json. 302 → /devices.
  POST /devices/revoke-all    Flips all-except-current. 302 → /devices.

Architecture (CLAUDE.md hex-lite):
  Local imports of auth_store inside handlers per Phase 11/13 D-15 hex
  convention. Module-top imports limited to: stdlib, fastapi, starlette,
  itsdangerous.

E-06: header-only auth path explicitly rejected with 403. /devices is NOT
in PUBLIC_PATHS — middleware denies unauthenticated access first; THEN
this route's _require_cookie_session_or_403 helper denies header-path
clients (curl/scripts) that did get past middleware via the auth header.

E-08 (full-trust active session): no TOTP re-prompt for revoke. Operator
authenticated via cookie session has full revoke authority.

T-16.1-XSS-defensive: every dynamic value (device label, granted_at,
last_seen) runs through html.escape before f-string substitution.

Log prefix: [Web] — Phase 11 convention.
'''
import logging
import os
from html import escape as html_escape

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer

logger = logging.getLogger(__name__)

DEVICES_PATH = '/devices'

# Cookie names — literal duplicates of middleware constants to keep hex
# boundary (no cross-module import for a 12-byte string).
_SESSION_COOKIE_NAME = 'tsi_session'
_TRUSTED_COOKIE_NAME = 'tsi_trusted'

_SESSION_MAX_AGE = 43200    # 12h (Plan 01 D-11)
_TRUSTED_MAX_AGE = 2592000  # 30d (Plan 02 E-05)


# =========================================================================
# Inline CSS — copy of dashboard._INLINE_CSS :root token block + table rules.
# Hex boundary: NOT importing dashboard here (dashboard is a sibling adapter,
# not in web/). The :root block is a duplicated palette literal — the source
# of truth lives in system_params._COLOR_* and dashboard._INLINE_CSS reads
# those. Plan 02 keeps the same hex-literal pattern login.py + totp.py used.
# =========================================================================

_DEVICES_INLINE_CSS = '''
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
  padding: var(--space-6);
}
.devices-shell {
  max-width: 880px;
  margin: 0 auto;
}
.devices-shell h1 {
  font-size: var(--fs-display);
  font-weight: 600;
  margin: 0 0 var(--space-2);
}
.devices-shell .eyebrow {
  font-size: var(--fs-label);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-dim);
  margin: 0 0 var(--space-1);
}
.devices-shell p.subtitle {
  color: var(--color-text-muted);
  margin: 0 0 var(--space-6);
}
.devices-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}
.devices-table th {
  font-size: var(--fs-label);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-3);
  text-align: left;
}
.devices-table td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text);
  font-size: var(--fs-body);
}
.devices-table tr:last-child td { border-bottom: none; }
.devices-table tr.revoked td {
  color: var(--color-text-dim);
  font-style: italic;
}
.devices-table tr.current .current-marker {
  color: var(--color-long);
  font-size: var(--fs-label);
  margin-left: var(--space-2);
}
.btn-revoke {
  background: transparent;
  color: var(--color-short);
  border: 1px solid var(--color-short);
  border-radius: 4px;
  padding: var(--space-1) var(--space-3);
  font-size: var(--fs-label);
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.btn-revoke:hover { background: rgba(239, 68, 68, 0.10); }
.revoke-all-row {
  margin-top: var(--space-6);
  display: flex;
  justify-content: flex-end;
}
.btn-revoke-all {
  background: transparent;
  color: var(--color-short);
  border: 1px solid var(--color-short);
  border-radius: 4px;
  padding: var(--space-2) var(--space-4);
  font-size: var(--fs-body);
  font-weight: 600;
  cursor: pointer;
}
.btn-revoke-all:hover { background: rgba(239, 68, 68, 0.10); }
.back-link {
  display: inline-block;
  margin-top: var(--space-6);
  color: var(--color-text-dim);
  text-decoration: none;
  font-size: var(--fs-label);
}
.back-link:hover { text-decoration: underline; }
.empty-state {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: var(--space-6);
  color: var(--color-text-muted);
  text-align: center;
}
'''


def _render_devices_page(devices, current_uuid):
  '''Render the trusted_devices list as HTML. Every dynamic value is escaped.

  devices: list[TrustedDevice]
  current_uuid: str | None — the uuid resolved from tsi_trusted (or None)
  '''
  active_count = sum(1 for d in devices if not d['revoked'])

  if not devices:
    body_html = (
      '<div class="empty-state">'
      'No trusted devices on file. Trust a device by checking '
      '"Trust this device for 30 days" on your next 2FA verification.'
      '</div>'
    )
  else:
    rows = []
    for dev in devices:
      label = html_escape(dev['label'])
      granted = html_escape(dev['granted_at'])
      last_seen = html_escape(dev['last_seen'])
      uid = html_escape(dev['uuid'])
      revoked = dev['revoked']
      classes = []
      if revoked:
        classes.append('revoked')
      if current_uuid and dev['uuid'] == current_uuid:
        classes.append('current')
      cls_attr = f' class="{" ".join(classes)}"' if classes else ''
      if revoked:
        revoke_cell = '<td>revoked</td>'
      else:
        revoke_cell = (
          f'<td>'
          f'<form method="POST" action="/devices/revoke" '
          f'style="display:inline">'
          f'<button type="submit" class="btn-revoke" '
          f'name="uuid" value="{uid}">Revoke</button>'
          f'</form>'
          f'</td>'
        )
      is_current = bool(current_uuid and dev['uuid'] == current_uuid)
      label_cell = (
        f'<td>{label}'
        f'<span class="current-marker">(this device)</span>'
        f'</td>'
        if is_current
        else f'<td>{label}</td>'
      )
      rows.append(
        f'<tr{cls_attr}>'
        f'{label_cell}'
        f'<td>{granted}</td>'
        f'<td>{last_seen}</td>'
        f'{revoke_cell}'
        f'</tr>'
      )
    rows_html = '\n'.join(rows)
    revoke_all_html = ''
    if active_count >= 2:
      revoke_all_html = (
        '<div class="revoke-all-row">'
        '<form method="POST" action="/devices/revoke-all">'
        '<button type="submit" class="btn-revoke-all" name="revoke-all" '
        'value="1">Revoke all other devices</button>'
        '</form>'
        '</div>'
      )
    body_html = (
      '<table class="devices-table">'
      '<thead><tr>'
      '<th>Label</th><th>Granted</th><th>Last seen</th><th></th>'
      '</tr></thead>'
      f'<tbody>{rows_html}</tbody>'
      '</table>'
      f'{revoke_all_html}'
    )

  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Devices</title>
<style>{_DEVICES_INLINE_CSS}</style>
</head>
<body>
<main class="devices-shell">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Trusted devices</h1>
<p class="subtitle">Manage trusted devices that skip TOTP verification.</p>
{body_html}
<a href="/" class="back-link">← Back to dashboard</a>
</main>
</body>
</html>
'''


def register(app: FastAPI) -> None:
  '''Register GET /devices, POST /devices/revoke, POST /devices/revoke-all.

  Reads WEB_AUTH_SECRET at register-time (Phase 13 D-18 testability convention)
  to build the session/trusted serializers. tsi_session signature alone is the
  authority — header-path requests (X-Trading-Signals-Auth) are explicitly
  rejected with 403 per E-06.
  '''
  secret = os.environ.get('WEB_AUTH_SECRET', '').strip()
  session_serializer = URLSafeTimedSerializer(secret, salt='tsi-session-cookie')
  trusted_serializer = URLSafeTimedSerializer(secret, salt='tsi-trusted-cookie')

  def _require_cookie_session_or_403(request: Request) -> Response | None:
    '''Return None if a valid tsi_session cookie is present; else a 403
    Response. Header-only auth (E-06) and unauth requests both → 403.

    Note: middleware has ALREADY validated that the request is authenticated
    SOMEHOW (header or cookie). This helper additionally requires that auth
    came via tsi_session cookie — header-path callers got past middleware
    but are denied here. Trusted-device-only callers (no tsi_session, only
    tsi_trusted) are also denied — they need to log in via the form to
    manage other devices (E-06 / E-08 spirit: revocation is a
    "full-trust active session" action).
    '''
    token = request.cookies.get(_SESSION_COOKIE_NAME, '')
    if not token:
      return Response(
        content='forbidden',
        status_code=403,
        media_type='text/plain; charset=utf-8',
      )
    try:
      session_serializer.loads(token, max_age=_SESSION_MAX_AGE)
      return None
    except SignatureExpired:
      pass
    except BadSignature:
      pass
    return Response(
      content='forbidden',
      status_code=403,
      media_type='text/plain; charset=utf-8',
    )

  def _get_current_uuid(request: Request) -> str | None:
    '''Extract uuid from the tsi_trusted cookie if present and valid.

    Returns None when:
      - cookie absent
      - signature invalid / expired
      - payload missing 'uuid'
    The /devices route doesn't fail on a stale tsi_trusted cookie — it just
    doesn't mark any row as "(this device)".
    '''
    token = request.cookies.get(_TRUSTED_COOKIE_NAME, '')
    if not token:
      return None
    try:
      payload = trusted_serializer.loads(token, max_age=_TRUSTED_MAX_AGE)
    except SignatureExpired:
      return None
    except BadSignature:
      return None
    if not isinstance(payload, dict):
      return None
    uuid_value = payload.get('uuid', '')
    return str(uuid_value) if uuid_value else None

  @app.get('/devices')
  def get_devices(request: Request) -> Response:
    forbidden = _require_cookie_session_or_403(request)
    if forbidden is not None:
      return forbidden
    import auth_store
    data = auth_store.load_auth()
    current_uuid = _get_current_uuid(request)
    return HTMLResponse(
      content=_render_devices_page(data['trusted_devices'], current_uuid),
    )

  @app.post('/devices/revoke')
  def post_revoke(
    request: Request, uuid: str = Form(...),
  ) -> Response:
    forbidden = _require_cookie_session_or_403(request)
    if forbidden is not None:
      return forbidden
    import auth_store
    auth_store.revoke_device(uuid)
    logger.info('[Web] device revoked: uuid=%s', uuid)
    return Response(status_code=302, headers={'Location': '/devices'})

  @app.post('/devices/revoke-all')
  def post_revoke_all(request: Request) -> Response:
    forbidden = _require_cookie_session_or_403(request)
    if forbidden is not None:
      return forbidden
    import auth_store
    current = _get_current_uuid(request) or ''
    n = auth_store.revoke_all_other_devices(except_uuid=current)
    logger.info('[Web] revoke_all: count=%d except=%s', n, current)
    return Response(status_code=302, headers={'Location': '/devices'})
