'''Phase 30 Plan 04 — TOTP render helpers extracted from web/routes/totp.py.

All render helpers + _derive_device_label + _log_totp_failure moved here per
D-06 boundary (file-size split, behaviour-preserving). Zero semantic changes.
'''
import base64
import io
import logging

from fastapi import Request

logger = logging.getLogger(__name__)

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


def _derive_device_label(
  user_agent: str, client_ip: str, granted_at_iso: str,
) -> str:
  '''Best-effort UA→browser-name + IP first-3-octets + ISO date label.

  Format: '<UA-derived-name> · <ip-first-3-octets>.x · <YYYY-MM-DD>'
  Examples:
    iPhone Safari · 203.0.113.x · 2026-04-29
    Unknown device · testclient · 2026-04-29

  NOT used for security decisions — operator-readable display only (E-05).
  '''
  ua = user_agent or ''
  if 'iPhone' in ua:
    if 'CriOS' in ua:
      name = 'iPhone Chrome'
    elif 'FxiOS' in ua:
      name = 'iPhone Firefox'
    else:
      name = 'iPhone Safari'
  elif 'iPad' in ua:
    name = 'iPad'
  elif 'Android' in ua:
    name = 'Android'
  elif 'Macintosh' in ua and 'Chrome' in ua:
    name = 'macOS Chrome'
  elif 'Macintosh' in ua and 'Firefox' in ua:
    name = 'macOS Firefox'
  elif 'Macintosh' in ua:
    name = 'macOS Safari'
  elif 'Windows' in ua and 'Chrome' in ua:
    name = 'Windows Chrome'
  elif 'Windows' in ua:
    name = 'Windows'
  elif 'Linux' in ua:
    name = 'Linux'
  else:
    name = 'Unknown device'

  parts = (client_ip or '').split('.')
  if len(parts) == 4 and all(p for p in parts):
    ip_label = '.'.join(parts[:3]) + '.x'
  else:
    ip_label = client_ip or '-'

  date_str = granted_at_iso.split('T')[0] if 'T' in granted_at_iso else granted_at_iso
  return f'{name} · {ip_label} · {date_str}'


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


def _render_enroll_reset_choice_page() -> str:
  '''Phase 16.1 Plan 03 E-07: ?reset=1 entry — operator picks Keep or New.

  Shown ONLY when GET /enroll-totp?reset=1 with a valid tsi_session
  cookie (just consumed magic-link). Two action buttons:
    - 'Keep current authenticator' (POST action='keep') → /
    - 'Set up new authenticator'    (POST action='new')  → fresh QR
  Per E-07 the operator may have only forgotten which device had the
  authenticator — keeping the current secret is a valid recovery path.
  '''
  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Reset 2FA</title>
<style>{_TOTP_INLINE_CSS}</style>
</head>
<body>
<main class="totp-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Reset 2FA</h1>
<p>Choose how you'd like to recover access:</p>
<form class="totp-form" method="POST" action="/enroll-totp?reset=1" autocomplete="off">
<button type="submit" name="action" value="keep" class="btn-primary"
        style="margin-bottom:12px;">Keep current authenticator</button>
<button type="submit" name="action" value="new" class="btn-primary">
Set up new authenticator</button>
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
