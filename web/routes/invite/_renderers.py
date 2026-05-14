'''Phase 37 Plan 04 — Invite acceptance wizard render helpers.

Three private render functions for the multi-step invite acceptance wizard.
Mirror the inline-CSS token block from web/routes/totp/_renderers.py verbatim.
All dynamic values escaped via html.escape(quote=True).
'''
import html

# Inline CSS token block — copy verbatim from _TOTP_INLINE_CSS in
# web/routes/totp/_renderers.py. No new tokens introduced (UI-SPEC §Design System).
_INVITE_INLINE_CSS = '''
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
.invite-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 32px;
  width: 100%;
  max-width: 360px;
  margin: 16px;
}
.invite-card .eyebrow {
  font-size: var(--fs-label);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-dim);
  margin: 0 0 4px;
}
.invite-card h1 {
  font-size: var(--fs-display);
  font-weight: 600;
  margin: 0 0 8px;
}
.step-indicator {
  font-size: var(--fs-label);
  color: var(--color-text-dim);
  margin: 0 0 var(--space-4);
}
.invite-card p { color: var(--color-text-muted); }
.field { margin-bottom: 16px; }
.field label {
  display: block;
  font-size: var(--fs-label);
  color: var(--color-text-muted);
  margin-bottom: 4px;
}
.field input[type="password"] {
  width: 100%;
  background: var(--color-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 10px 12px;
  font-size: var(--fs-body);
}
.footnote {
  font-size: var(--fs-label);
  color: var(--color-text-dim);
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
.link-secondary {
  color: var(--color-text-muted);
  text-decoration: underline;
  font-size: var(--fs-body);
  display: inline-block;
  margin-top: 16px;
}
.checkbox-row {
  margin: 12px 0;
  display: flex;
  gap: 8px;
  align-items: center;
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
  margin: 0 0 8px;
}
'''


def _render_step1_password_page(email: str, error: str | None = None) -> str:
  '''Surface 2 (UI-SPEC): centered card, max-width 360px, step 1 of 3.

  minlength=12 AND maxlength=72 on password inputs (review #9 client hint).
  All dynamic values escaped with html.escape(quote=True).
  '''
  safe_email = html.escape(email, quote=True)
  error_block = ''
  if error:
    safe_error = html.escape(error, quote=True)
    error_block = (
      f'<div class="error" role="alert" aria-live="polite">'
      f'<p class="error-heading">{safe_error}</p>'
      f'</div>'
    )
  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Set your password</title>
<style>{_INVITE_INLINE_CSS}</style>
</head>
<body>
<main class="invite-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Set your password</h1>
<p class="step-indicator">Step 1 of 3</p>
{error_block}
<form method="POST" action="/accept-invite" autocomplete="off">
<div class="field">
<label for="inv-password">Password</label>
<input id="inv-password" name="password" type="password"
       autocomplete="new-password" required autofocus
       minlength="12" maxlength="72">
</div>
<div class="field">
<label for="inv-password2">Confirm password</label>
<input id="inv-password2" name="password2" type="password"
       autocomplete="new-password" required
       minlength="12" maxlength="72">
<small class="footnote">Minimum 12 characters.</small>
</div>
<button type="submit" class="btn-primary">Set password</button>
</form>
</main>
</body>
</html>
'''


def _render_step3_device_page() -> str:
  '''Surface 4 (UI-SPEC): centered card, max-width 420px, step 3 of 3.

  No dynamic values — static page. Uses .totp-card class (420px wide per UI-SPEC).
  '''
  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Trust this device?</title>
<style>{_INVITE_INLINE_CSS}</style>
</head>
<body>
<main class="totp-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Trust this device?</h1>
<p class="step-indicator">Step 3 of 3</p>
<p>Check the box to skip 2FA for 30 days on this browser.</p>
<form method="POST" action="/accept-invite/device" autocomplete="off">
<div class="checkbox-row">
<input id="trust-device" name="trust_device" type="checkbox" value="1">
<label for="trust-device">Trust this device for 30 days</label>
</div>
<button type="submit" class="btn-primary">Continue to dashboard</button>
</form>
</main>
</body>
</html>
'''


def _render_invite_error_page() -> str:
  '''Surface 5 (UI-SPEC): centered card, max-width 360px. HTTP 200 (D-07).

  No dynamic values — all copy is static per UI-SPEC §Copywriting Contract.
  '''
  return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — Link expired</title>
<style>{_INVITE_INLINE_CSS}</style>
</head>
<body>
<main class="invite-card">
<p class="eyebrow">TRADING SIGNALS</p>
<h1>Link expired</h1>
<div class="error" role="alert">
<p class="error-heading">This invite link has expired or has already been used.</p>
</div>
<p>Contact the administrator for a new invite.</p>
<a href="/login" class="link-secondary">Back to sign in</a>
</main>
</body>
</html>
'''
