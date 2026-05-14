# Phase 37: Per-User Email Fan-Out + Admin Invite/Disable Routes + Invite-Acceptance Flow - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-14
**Phase:** 37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac
**Areas discussed:** F&F email content, Invite acceptance flow, Admin invite UI, Email prefs on dashboard

---

## F&F email content

| Option | Description | Selected |
|--------|-------------|----------|
| User section + shared signals | Top section: stop-loss alerts + paper P&L. Bottom section: shared signal block (same as admin). | ✓ |
| Personal only | Only stop-loss alerts + paper P&L. No shared signal block. | |
| Full admin clone | Exact same email as admin, plus personal P&L section inserted. | |

**User's choice:** User section + shared signals
**Notes:** Clean separation between per-user and market data. Admin email unchanged.

---

| Option | Description | Selected |
|--------|-------------|----------|
| No — admin email unchanged | Admin keeps existing daily email. Gets additional end-of-cycle summary. | ✓ |
| Admin gets cycle summary only | Admin's regular email replaced by summary. | |
| Admin gets both | Admin keeps existing email + separate summary. | |

**User's choice:** Admin email unchanged
**Notes:** Admin gets their existing daily email plus a new end-of-cycle summary email.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Always — every cycle | Short summary every weekday whether or not failures occurred. | ✓ |
| Only on failure | Summary sent only when at least one user failed. | |
| You decide | Claude picks based on notifier pattern. | |

**User's choice:** Always — every cycle
**Notes:** Makes anomalies visible passively.

---

## Invite acceptance flow

| Option | Description | Selected |
|--------|-------------|----------|
| Multi-step: password → TOTP → trusted device | Three separate steps. Mirrors existing TOTP enrollment UX. No step skippable. | ✓ |
| Single page with all fields | One form: password, QR code, confirm device. | |
| Password only, TOTP on next login | TOTP deferred to first login. | |

**User's choice:** Multi-step wizard
**Notes:** Step 1: set password. Step 2: TOTP enrollment. Step 3: trusted device. Step 4: redirect to dashboard.

---

| Option | Description | Selected |
|--------|-------------|----------|
| /accept-invite?token=<raw> | Token in query string. Route validates + consumes + starts multi-step flow. | ✓ |
| /register/<raw_token> | Token in path segment. | |
| You decide | Claude picks based on existing route patterns. | |

**User's choice:** /accept-invite?token=<raw>
**Notes:** Simple, readable. Consistent with query-string pattern used elsewhere.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Error page with contact message | Dedicated error page: "Link expired / already used. Contact admin." | ✓ |
| Redirect to login with flash message | Redirect to /login with query-param error. | |
| You decide | Claude handles error UX based on existing patterns. | |

**User's choice:** Error page with contact message
**Notes:** Not a redirect to login — dedicated page so invitee knows what to do.

---

## Admin invite UI

| Option | Description | Selected |
|--------|-------------|----------|
| HTMX panel on /admin/users HTML page | HTML page listing users + pending invites + issue-invite form. HTMX mutations. | ✓ |
| API-only (no UI for now) | Admin uses curl/script. No HTML page in Phase 37. | |
| Separate /admin/invites page | Separate HTML page for invite management. | |

**User's choice:** HTMX panel on /admin/users HTML page
**Notes:** Consistent with HTMX-only app pattern.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Displayed on page + emailed to invitee | Raw URL shown inline for copy-paste AND system sends invite email. | ✓ |
| Emailed to invitee only | System sends invite email; admin doesn't see raw URL. | |
| Displayed on page only | Admin copies URL manually; no invite email. | |

**User's choice:** Displayed on page + emailed to invitee
**Notes:** Both paths: inline copy-paste URL + automatic invite email via `send_invite_email`.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — add admin link to dashboard nav | Admin sees nav link in dashboard header to /admin/users. | ✓ |
| No — admin navigates by URL | No nav change. | |
| You decide | Claude decides based on existing nav patterns. | |

**User's choice:** Yes — add admin link to dashboard nav
**Notes:** Visible only to admin role.

---

## Email prefs on dashboard

| Option | Description | Selected |
|--------|-------------|----------|
| Settings tab / section on dashboard | Email prefs in existing/new Settings section. dashboard-settings.html anchor. | ✓ |
| Separate /settings page | Standalone /settings route. | |
| Inline in dashboard header | Small toggle visible in main dashboard. | |

**User's choice:** Settings tab / section on dashboard
**Notes:** dashboard-settings.html is already in repo. Email prefs section added there.

---

| Option | Description | Selected |
|--------|-------------|----------|
| HTML <input type="date"> field | Native browser date picker. No JS library. HTMX form submit. | ✓ |
| Text input YYYY-MM-DD | Plain text with format hint. Server-side validation. | |
| Quick-select buttons | Preset: "Pause 1 week", "Pause 1 month", etc. | |

**User's choice:** HTML `<input type="date">`
**Notes:** Native picker, no library dependency. Consistent with date inputs elsewhere in dashboard.

---

## Claude's Discretion

- `send_invite_email` template content and subject line
- Whether `/admin/users` HTML and JSON endpoint coexist at same path (content-type negotiation) or JSON renamed to `/admin/users/json`
- Where `/healthz/last-cycle` data is persisted (state.json key vs sidecar)
- Password hashing algorithm (bcrypt vs argon2 — researcher to verify for Python 3.13)
- Per-user error boundary retry logic in `per_user_fanout.py`
- How `send_invite_email` gets BASE_URL for invite link (env var)

## Deferred Ideas

- Public signup — explicitly out of scope (admin-only invite system)
- Bulk invite via CSV — out of scope for ≤dozens of users
- Terminal user delete — deferred to v1.3.x
- Per-domain email loaders — `load_user_state(uid)` is sufficient
- Retry logic per user in fan-out — fail-fast acceptable for now

---

## SC-5 Gap Closure Discussion (2026-05-14)

**Context:** Phase 37 verification found SC-5 failed — dashboard not scoped to per-user state.

### Area selection

| Area | Selected |
|------|----------|
| Account page isolation (core SC-5 fix) | ✓ |
| Settings page scoping | |
| Crash-email test (line 156) | |
| Isolation test URL (line 178) | |

### Render strategy for /account

| Option | Description | Selected |
|--------|-------------|----------|
| Dynamic render, no disk | render_dashboard_as_str(); same path as market pages; no file written | ✓ |
| Per-uid disk files | dashboard-account-{uid}.html per user | |
| Shared disk + placeholder swap | Keep shared file; substitute uid data at serve time | |

**User's choice:** Dynamic render, no disk

### State scoping location

| Option | Description | Selected |
|--------|-------------|----------|
| Route layer | Pre-filter state in handler before renderer; renderer unchanged | ✓ |
| Renderer layer | Add uid param to render_dashboard_as_str() + RenderContext | |

**User's choice:** Route layer

### Fields to scope

| Option | Description | Selected |
|--------|-------------|----------|
| paper_trades + equity_history only | TRADE_CONTENT_RE targets: entry_price, n_contracts, direction | ✓ |
| All per-user fields | Promote paper_trades, equity_history, account, positions, etc. | |

**User's choice:** paper_trades + equity_history only

### Isolation test URL

| Option | Description | Selected |
|--------|-------------|----------|
| /account | Actual paper_trades render page; real assertions | ✓ |
| /dashboard | Would 404 (route retired in Phase 32); trivially passes | |

**User's choice:** /account

### SC-5 Claude's Discretion

- Crash-email test (line 156): update skip reason to `'SC-5 deferred: crash-email body assertions not yet written'`; keep skipped.
- Settings page scoping: out of scope for this fix.
- `Cache-Control: no-store, private` on account page response.

### SC-5 Deferred

- Settings page per-user scoping (email prefs values on page load)
- `test_crash_email_body_has_no_trade_content` body + assertions
