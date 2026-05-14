'''Phase 37 — HTML render helpers for web/routes/admin package.

Phase 37 D-09/D-10 + UI-SPEC Surface 1:
  _render_admin_users_page        — full HTML page for /admin/users
  _render_admin_users_html_fragment — HTMX partial (review #8: HX-Request path)
  _render_invite_url_fragment     — HTMX swap fragment after POST /admin/invites

All dynamic values use html.escape(value, quote=True) per Phase 27 audit.
2-space indent throughout (CLAUDE.md — do NOT run ruff format).
'''
import html
from urllib.parse import quote as _url_quote

_CSS = '''
  <style>
    :root {
      --color-bg: #0f1117; --color-surface: #161a24; --color-border: #252a36;
      --color-text: #e5e7eb; --color-text-muted: #cbd5e1; --color-text-dim: #64748b;
      --color-long: #22c55e; --color-short: #ef4444; --color-flat: #eab308;
      --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
      --space-6: 24px; --space-8: 32px; --space-12: 48px;
      --fs-label: 14px; --fs-body: 16px; --fs-heading: 23px; --fs-display: 32px;
      --font-mono: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
      --touch-target-min: 44px;
    }
    body {
      background: var(--color-bg); color: var(--color-text);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: var(--fs-body); margin: 0; padding: 0;
    }
    .container { max-width: 1100px; padding: 32px 24px 48px; margin: 0 auto; }
    h1 { font-size: var(--fs-display); font-weight: 600; margin: 0 0 var(--space-6); }
    h2 { font-size: var(--fs-heading); font-weight: 600; margin: var(--space-8) 0 var(--space-4); }
    nav a { color: var(--color-long); text-decoration: none; margin-right: var(--space-4); }
    .open-form {
      background: var(--color-surface); border: 1px solid var(--color-border);
      border-radius: 8px; padding: var(--space-6); margin-bottom: var(--space-8);
    }
    .field { margin-bottom: var(--space-4); }
    label { display: block; font-size: var(--fs-label); color: var(--color-text-muted);
            margin-bottom: var(--space-2); }
    input[type="email"] {
      background: var(--color-bg); border: 1px solid var(--color-border);
      color: var(--color-text); padding: var(--space-2) var(--space-3);
      border-radius: 4px; width: 100%; box-sizing: border-box;
      font-size: var(--fs-body);
    }
    .btn-primary {
      background: var(--color-long); color: #000; border: none;
      padding: var(--space-2) var(--space-4); border-radius: 4px;
      font-size: var(--fs-body); cursor: pointer; font-weight: 600;
    }
    .btn-row.btn-close {
      background: transparent; color: var(--color-short);
      border: 1px solid var(--color-short); padding: var(--space-1) var(--space-2);
      border-radius: 4px; cursor: pointer; font-size: var(--fs-label);
      min-height: var(--touch-target-min);
    }
    table { width: 100%; border-collapse: collapse; }
    th { text-align: left; font-size: var(--fs-label); color: var(--color-text-muted);
         padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--color-border); }
    th[scope="col"] { font-weight: 600; }
    td { padding: var(--space-3); border-bottom: 1px solid var(--color-border);
         font-size: var(--fs-body); vertical-align: middle; }
    .empty-state { text-align: center; color: var(--color-text-dim);
                   padding: var(--space-6); }
    .banner-success {
      background: var(--color-surface); border: 1px solid var(--color-long);
      border-radius: 4px; padding: var(--space-3) var(--space-4);
      margin-top: var(--space-4);
    }
    code.invite-url {
      font-family: var(--font-mono); font-size: var(--fs-label);
      word-break: break-all; user-select: all;
      background: var(--color-bg); border: 1px solid var(--color-border);
      border-radius: 4px; padding: var(--space-2) var(--space-3);
      display: block; margin-top: var(--space-2);
    }
  </style>
'''


def _render_invite_url_fragment(
  email: str,
  expires_at: str,
) -> str:
  '''HTMX swap fragment shown inline after POST /admin/invites succeeds.

  CR-01: raw token MUST NOT be embedded in HTML response. Confirmation only.
  The invite link was sent to the invitee via email. Admin is shown a
  confirmation message with email + expiry only.
  All dynamic values are html.escape(quote=True).
  '''
  safe_email = html.escape(email, quote=True)
  safe_expires = html.escape(expires_at, quote=True)
  return (
    f'<div class="banner-success" role="status" aria-live="polite">'
    f'<p>Invite sent to {safe_email}. The link expires: {safe_expires}.</p>'
    f'<p>The invitation email has been delivered. '
    f'Ask the invitee to check their inbox.</p>'
    f'</div>'
  )


def _render_admin_users_html_fragment(
  summaries: list,
  pending: list,
) -> str:
  '''HTML fragment for HTMX HX-Request swaps (review #8: no outer chrome).

  Contains the pending invites + active users tables only — no <html>/<head>.
  Used when GET /admin/users has HX-Request: true header.
  '''
  return (
    _render_pending_table(pending)
    + _render_users_table(summaries)
  )


def _render_admin_users_page(
  summaries: list,
  pending: list,
) -> str:
  '''Full HTML page for /admin/users (Accept: text/html or unspecified).

  Visual hierarchy per UI-SPEC Surface 1:
    1. Page heading "Users"
    2. Issue invite form (primary anchor)
    3. Pending invites table
    4. Active users table
  '''
  invite_form = (
    '<section class="open-form" id="invite-form-wrapper">'
    '<h2 style="margin-top:0">Issue Invite</h2>'
    '<form hx-post="/admin/invites" '
    'hx-target="#invite-form-wrapper" hx-swap="innerHTML">'
    '<div class="field">'
    '<label for="inv-email">Email address</label>'
    '<input id="inv-email" type="email" name="email" required autofocus '
    'placeholder="invitee@example.com">'
    '</div>'
    '<button type="submit" class="btn-primary">Issue invite</button>'
    '</form>'
    '</section>'
  )
  body = (
    f'<div class="container">'
    f'<h1>Users</h1>'
    f'<nav><a href="/admin/users">Users</a></nav>'
    f'{invite_form}'
    + _render_pending_table(pending)
    + _render_users_table(summaries)
    + '</div>'
  )
  return (
    '<!DOCTYPE html><html><head>'
    '<meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<title>Admin — Users</title>'
    + _CSS
    + '</head><body>'
    + body
    + '</body></html>'
  )


def _render_pending_table(pending: list) -> str:
  '''Pending invites table section (consumed=False rows only).'''
  active_pending = [p for p in pending if not p.get('consumed')]
  if not active_pending:
    rows = (
      '<tr><td colspan="4" class="data-table empty-state">'
      'No pending invites.</td></tr>'
    )
  else:
    rows = ''
    for inv in active_pending:
      safe_email = html.escape(inv.get('email', ''), quote=True)
      safe_created = html.escape(inv.get('created_at', '')[:10], quote=True)
      safe_expires = html.escape(inv.get('expires_at', '')[:10], quote=True)
      safe_hash = html.escape(inv.get('token_hash', ''), quote=True)
      # WR-03: URL-encode token_hash for the hx-delete path segment.
      url_hash = _url_quote(inv.get('token_hash', ''), safe='')
      rows += (
        f'<tr>'
        f'<td>{safe_email}</td>'
        f'<td>{safe_created}</td>'
        f'<td>{safe_expires}</td>'
        f'<td>'
        f'<button class="btn-row btn-close" '
        f'hx-delete="/admin/invites/{url_hash}" '
        f'hx-target="closest tr" hx-swap="outerHTML" '
        f'hx-confirm="Revoke this invite? The link will stop working immediately." '
        f'aria-label="Revoke invite for {safe_email}">'
        f'Revoke invite</button>'
        f'</td>'
        f'</tr>'
      )
  return (
    '<section>'
    '<h2>Pending Invites</h2>'
    '<table>'
    '<thead><tr>'
    '<th scope="col">Email</th>'
    '<th scope="col">Issued</th>'
    '<th scope="col">Expires</th>'
    '<th scope="col">Actions</th>'
    '</tr></thead>'
    f'<tbody>{rows}</tbody>'
    '</table>'
    '</section>'
  )


def _render_users_table(summaries: list) -> str:
  '''Active/disabled users table section.'''
  if not summaries:
    rows = (
      '<tr><td colspan="5" class="data-table empty-state">'
      'No users yet.</td></tr>'
    )
  else:
    rows = ''
    for s in summaries:
      # summaries is list of PublicUserSummary or dict
      if hasattr(s, 'user_id'):
        uid = s.user_id
        email = s.display_name
        status = s.status
        last_seen = s.last_seen_date or ''
      else:
        uid = s.get('user_id', '')
        email = s.get('display_name', '')
        status = s.get('status', '')
        last_seen = s.get('last_seen_date') or ''
      safe_uid = html.escape(uid, quote=True)
      safe_email = html.escape(email, quote=True)
      safe_status = html.escape(status, quote=True)
      safe_seen = html.escape(last_seen, quote=True)
      rows += (
        f'<tr>'
        f'<td>{safe_uid}</td>'
        f'<td>{safe_email}</td>'
        f'<td>{safe_status}</td>'
        f'<td>{safe_seen}</td>'
        f'<td>'
        f'<button class="btn-row btn-close" '
        f'hx-patch="/admin/users/{safe_uid}/disable" '
        f'hx-target="closest tr" hx-swap="outerHTML" '
        f'hx-confirm="Disable {safe_email}? They will not be able to log in. Their data is preserved." '
        f'aria-label="Disable {safe_email}">'
        f'Disable user</button>'
        f'</td>'
        f'</tr>'
      )
  return (
    '<section>'
    '<h2>Users</h2>'
    '<table>'
    '<thead><tr>'
    '<th scope="col">UID</th>'
    '<th scope="col">Email</th>'
    '<th scope="col">Status</th>'
    '<th scope="col">Last seen</th>'
    '<th scope="col">Actions</th>'
    '</tr></thead>'
    f'<tbody>{rows}</tbody>'
    '</table>'
    '</section>'
  )


__all__ = [
  '_render_admin_users_page',
  '_render_admin_users_html_fragment',
  '_render_invite_url_fragment',
]
