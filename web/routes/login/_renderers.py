'''Render helpers for the login package (D-05 boundary split).

Contains: _is_safe_next, _LOGIN_INLINE_CSS, _render_login_form,
_render_forgot_2fa_form, _render_check_email_page,
_render_logout_confirmation, _log_login_failure.

These are pure helpers moved verbatim from web/routes/login.py (Phase 30
file-size pre-split).  No behaviour change.

Open-redirect prevention (T-16.1-07): _is_safe_next applies 8 guards before
allowing a `?next=` value.

T-16.1-11: every dynamic value rendered via inline f-string runs through
html.escape FIRST.

Log prefix: [Web] — Phase 11 convention.
'''
import logging
from html import escape as html_escape
from urllib.parse import quote

from fastapi import Request

logger = logging.getLogger(__name__)

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


def _render_forgot_2fa_form(error: str | None = None) -> str:
  '''Inline HTML for GET /forgot-2fa (UI-SPEC §F-07: mirrors login form).

  Same _LOGIN_INLINE_CSS palette. Form posts to /forgot-2fa. Both username
  and password fields required (constant-time validation; identical
  response shape regardless of cred validity per E-07 + T-16.1-21).
  '''
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
<title>Trading Signals — Reset 2FA</title>
<style>{_LOGIN_INLINE_CSS}</style>
</head>
<body>
<main class="login-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Reset 2FA</h1>
{error_block}
<p>Enter your username and password. If they match, we'll email a one-time
reset link to your recovery address.</p>
<form class="login-form" method="POST" action="/forgot-2fa" autocomplete="on">
<div class="field">
<label for="forgot-username">Username</label>
<input id="forgot-username" name="username" type="text"
       autocomplete="username" required autofocus>
</div>
<div class="field">
<label for="forgot-password">Password</label>
<input id="forgot-password" name="password" type="password"
       autocomplete="current-password" required>
</div>
<button type="submit" class="btn-primary">Send reset link</button>
</form>
<a href="/login" class="link-secondary">Back to sign in</a>
</main>
</body>
</html>
'''


def _render_check_email_page() -> str:
  '''Inline HTML for POST /forgot-2fa response (UI-SPEC §Surface — generic
  no-leak page).

  Identical render regardless of credential validity, rate-limit hit, or
  email-send outcome — per E-07 + T-16.1-21 (no leak of credential
  validity via response body, status, or timing).
  '''
  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Check your email</title>
<style>{_LOGIN_INLINE_CSS}</style>
</head>
<body>
<main class="login-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Check your email</h1>
<p>If your username and password match an account, a reset link has been
sent. The link is valid for one hour and can be used once.</p>
<a href="/login" class="link-secondary">Back to sign in</a>
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
# (kept here for parity with the original module; URL-quoting may be needed
# in the future).
_ = quote
