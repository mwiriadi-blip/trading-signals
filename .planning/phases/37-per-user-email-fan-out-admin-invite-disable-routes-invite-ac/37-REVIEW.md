---
phase: 37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac
reviewed: 2026-05-14T12:00:00Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - auth_store/__init__.py
  - auth_store/_schema.py
  - auth_store/_users.py
  - main.py
  - notifier/transport.py
  - per_user_fanout.py
  - system_params.py
  - tests/conftest.py
  - tests/test_auth_store_users.py
  - tests/test_main.py
  - tests/test_per_user_fanout.py
  - tests/test_web_admin_invite.py
  - tests/test_web_dashboard_email_prefs.py
  - tests/test_web_invite.py
  - web/app.py
  - web/middleware/auth.py
  - web/routes/admin/__init__.py
  - web/routes/admin/_models.py
  - web/routes/admin/_renderers.py
  - web/routes/dashboard/__init__.py
  - web/routes/healthz.py
  - web/routes/invite/__init__.py
  - web/routes/invite/_renderers.py
findings:
  critical: 4
  warning: 5
  info: 3
  total: 12
status: issues_found
---

# Phase 37: Code Review Report

**Reviewed:** 2026-05-14T12:00:00Z
**Depth:** standard
**Files Reviewed:** 22
**Status:** issues_found

## Summary

Phase 37 adds per-user email fan-out, an admin invite flow, user disable/enable,
and a multi-step invite-acceptance wizard. Core crypto and locking patterns are
sound. Four BLOCKER-tier issues were found: the raw invite token is exposed in
the HTML response body sent to the admin browser (token-leak vector); the wizard
stores the raw token inside a signed cookie that can be replayed after the invite
is consumed; `create_user` silently drops the `password_hash` field on any
non-invite path; and the PATCH `/admin/users/{uid}/disable` endpoint takes
`disabled` as a query-string boolean, which FastAPI parses from the URL, meaning
`PATCH /admin/users/abc/disable?disabled=false` re-enables a user with no admin
confirmation—an RBAC boundary surprise. Five warnings cover missing email
validation at the invite boundary, silent no-op on empty admin_uid, an
unescaped token_hash in HTMX `hx-delete` attributes, a rate-limit duplicate-
constant drift risk, and a TOCTOU window in `_peek_invite_token`. Three info
items note dead code, a missing test isolation gap, and a magic-number TTL.

---

## Critical Issues

### CR-01: Raw invite token written into HTML response body returned to admin browser

**File:** `web/routes/admin/__init__.py:161-168` and `web/routes/admin/_renderers.py:93-102`

**Issue:** `admin_issue_invite` builds `invite_url = f'{base_url}/accept-invite?token={raw_token}'` and passes it directly to `_render_invite_url_fragment`, which embeds the full URL—including the secret raw token—inside a `<code>` block in the HTML response. The browser caches this response, it appears in browser history, is present in server access logs (if the full response body is logged), and leaks in any Content-Security-Policy or network-layer logging of response bodies.

The raw token is a 32-byte `secrets.token_urlsafe` value equivalent to a one-time password. Exposing it in HTML is consistent with the design intent (admin copy-pastes it) but it means the token travels in plaintext HTML, not just in the out-of-band invite email. Combined with a logging or proxy layer that captures response bodies, the token is fully exposed.

More critically: the fragment is returned as the inner HTML of `#invite-form-wrapper` via HTMX (`hx-target="#invite-form-wrapper" hx-swap="innerHTML"`). This HTML fragment—containing the raw token—will be captured in any HTMX response log, browser dev-tools network tab replay, or XSS exfiltration of the DOM.

**Fix:** Do not embed the raw token in any server-rendered HTML. Instead return only a confirmation message and the token hash (which the admin already sees in the pending-invites table for revocation). The raw token was already emailed to the invitee. If the admin needs a copy-able link, truncate/mask the token in the UI: e.g. show only the first 6 chars + `...` as a visual confirmation the link was issued, but never render the full token in HTML.

```python
# _renderers.py: replace invite_url embed with masked confirmation
def _render_invite_url_fragment(email: str, expires_at: str) -> str:
  safe_email = html.escape(email, quote=True)
  safe_expires = html.escape(expires_at, quote=True)
  return (
    f'<div class="banner-success" role="status" aria-live="polite">'
    f'<p>Invite sent to {safe_email}. The link expires: {safe_expires}.</p>'
    f'<p>The invitation email has been delivered. '
    f'Ask the invitee to check their inbox.</p>'
    f'</div>'
  )

# admin/__init__.py: drop invite_url from the renderer call
return HTMLResponse(_render_invite_url_fragment(email, expires_at))
```

---

### CR-02: Raw invite token stored in wizard cookie payload — survives server-side invite revocation

**File:** `web/routes/invite/__init__.py:115`

**Issue:** On GET `/accept-invite`, the handler stores the raw token in the signed `tsi_invite_wizard` cookie:

```python
payload = {'step': 'password', 'raw_token': token, 'email': email}
```

The signed cookie is issued to the invitee's browser. The browser can hold this cookie for up to 1 hour (`_WIZARD_COOKIE_MAX_AGE = 3600`). If an admin calls `DELETE /admin/invites/{token_hash}` to revoke the invite while the invitee's wizard cookie is active, the cookie still contains the raw token. When the invitee then submits POST `/accept-invite`, the handler reads `raw_token` from the cookie and calls `consume_and_create_user`. The consume path does re-check expiry and consumed status **inside a flock**, so revocation via `revoke_invite` (which sets `consumed=True`) will prevent the new user from being created.

However: the raw token is now persisted on the invitee's disk (in browser cookie storage) for up to 1 hour beyond any revocation. If the cookie is exfiltrated (XSS, local storage access, shared browser profile), the raw token is exposed. Per plan LEARNINGS G-72, token hashes must be enforced at all storage boundaries. The raw token must not be stored in a cookie.

**Fix:** Instead of storing `raw_token` in the cookie, store only the token hash. On POST `/accept-invite`, read the raw token from a hidden form field (passed from the GET response HTML) and re-derive the hash for the consume call. The raw token only lives in the URL query parameter and in the form submit body, never in persistent cookie storage.

```python
# GET handler: store hash, not raw token, in cookie
token_hash = 'sha256:' + hashlib.sha256(token.encode('utf-8')).hexdigest()
payload = {'step': 'password', 'token_hash': token_hash, 'email': email}

# Step-1 form: embed token in a hidden input (lives only in the transient page)
# _render_step1_password_page: add <input type="hidden" name="raw_token" value="{safe_token}">

# POST handler: get raw_token from Form(...), not from cookie
raw_token: str = Form(...)
# validate: cookie step == 'password' and hash matches
expected_hash = 'sha256:' + hashlib.sha256(raw_token.encode()).hexdigest()
if wizard_payload.get('token_hash') != expected_hash:
    return HTMLResponse(_render_invite_error_page(), status_code=400)
```

---

### CR-03: `create_user` silently drops `password_hash` — no-invite user creation path creates users without passwords

**File:** `auth_store/_users.py:150-165`

**Issue:** `create_user` builds the user dict without a `password_hash` field:

```python
user = {
    'uid': uuid.uuid4().hex,
    'email': email,
    'role': role,
    'created_at': datetime.now(timezone.utc).isoformat(),
    'disabled': False,
}
```

The `User` TypedDict declares `password_hash: str | None` (line 56 of `_schema.py`). Any caller that uses `create_user` to create an account (as opposed to `consume_and_create_user`) produces a row without the `password_hash` key. If `verify_password` is later called with `stored_hash=None` (from `.get('password_hash')`), it silently returns `False` rather than raising—which is correct—but a row with no `password_hash` key at all will return `None` from `.get('password_hash')`, which also maps to `False` from `verify_password`. The silent divergence between `None` (explicitly no password) and missing key (accidentally no password) is a data integrity risk: new code that checks `user.get('password_hash') is not None` as a "has a password" guard will treat both cases identically.

**Fix:** Add `password_hash` field explicitly to `create_user`:

```python
user = {
    'uid': uuid.uuid4().hex,
    'email': email,
    'role': role,
    'created_at': datetime.now(timezone.utc).isoformat(),
    'disabled': False,
    'password_hash': fields.get('password_hash'),  # None for admin-only rows
}
```

---

### CR-04: PATCH `/admin/users/{uid}/disable` accepts `disabled` as a query-string boolean — re-enable is a one-param URL with no confirmation gate

**File:** `web/routes/admin/__init__.py:124-135`

**Issue:**

```python
@router.patch('/users/{uid}/disable')
def admin_disable_user(uid: str, disabled: bool = True):
```

FastAPI resolves `disabled` from the **query string** (not from a form body or JSON body), because `bool` is a scalar type without a `Body(...)` or `Form(...)` annotation. The HTMX button in `_renderers.py` calls `hx-patch="/admin/users/{uid}/disable"` without any request body—so the default `disabled=True` fires, correctly disabling the user.

However, since `disabled` is a query param, **any** request to `PATCH /admin/users/{uid}/disable?disabled=false` will re-enable the user. This is exploitable by an authenticated admin who can craft a URL, or inadvertently by a future HTMX form that adds query params. More critically, the endpoint name is `/disable` (suggesting a one-way action) but it is actually a full toggle controlled by a query param—a contract mismatch that is not surfaced in the UI.

**Fix:** Require `disabled` from a form body and rename the endpoint to make toggle semantics explicit, or split into two endpoints `/disable` and `/enable`:

```python
from fastapi import Form

@router.patch('/users/{uid}/disable')
def admin_disable_user(uid: str, disabled: bool = Form(default=True)):
    ...
```

Or, remove the `disabled` parameter entirely and make `PATCH /admin/users/{uid}/disable` always set `disabled=True`, and add a separate `PATCH /admin/users/{uid}/enable` endpoint. This matches the endpoint name and removes the re-enable footgun.

---

## Warnings

### WR-01: No email format validation on `POST /admin/invites` — any string is accepted as email

**File:** `web/routes/admin/__init__.py:139-168`

**Issue:** The `email` parameter is `email: str = Form(...)`. FastAPI's `Form(...)` only enforces non-empty presence; it does not validate email format. An admin submitting `email=notanemail` or `email=<script>alert(1)</script>` will mint a valid invite token and attempt to send an email to that address. The invite row is stored with the malformed email, which then propagates to `mint_invite_token`, `send_invite_email`, and ultimately the Resend API (which will return a 4xx and log it as a ResendError, silently dropped).

The lack of validation means the admin UI can silently create invite rows for invalid addresses that can never be accepted by a real invitee.

**Fix:** Add a simple email-format validator at the route boundary, consistent with `_EMAIL_RE` already used in `web/app.py`:

```python
import re
_INVITE_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

if not _INVITE_EMAIL_RE.match(email):
    raise HTTPException(status_code=422, detail='Invalid email address')
```

---

### WR-02: `admin_uid` from `Depends(current_user_id)` can be `None` — silently stored as `invited_by: None`

**File:** `web/routes/admin/__init__.py:143-160`

**Issue:**

```python
admin_uid: str = Depends(current_user_id),
...
raw_token, expires_at = mint_invite_token(invited_by_uid=admin_uid, email=email)
```

`current_user_id` (from `web/dependencies.py`) returns `request.state.user_id`, which `AuthMiddleware` sets to `None` for trusted-device sessions (Phase 35 Option B: `request.state.user_id = None` is explicitly set on the tsi_trusted path—see `web/middleware/auth.py:295`). If a trusted-device session calls `POST /admin/invites`, `admin_uid` will be `None`, and the stored invite row will have `invited_by: None`. This is a data-integrity issue: the audit trail for who issued the invite is silently lost.

**Fix:** Add a None guard before minting the token:

```python
if not admin_uid:
    raise HTTPException(status_code=403, detail='Cannot determine admin identity; re-login with TOTP session')
```

---

### WR-03: Unescaped `token_hash` injected into HTMX `hx-delete` URL path attribute — partial XSS vector

**File:** `web/routes/admin/_renderers.py:190`

**Issue:**

```python
safe_hash = html.escape(inv.get('token_hash', ''), quote=True)
...
f'hx-delete="/admin/invites/{safe_hash}" '
```

`html.escape(quote=True)` encodes `&`, `<`, `>`, `"`, and `'`. It does NOT encode `/` or `:`. A token hash stored as `sha256:abcdef...` is valid. However, if an attacker-controlled value were stored in `token_hash` (e.g., via a crafted auth.json write), a value like `sha256:abc/../../other-path` would produce `hx-delete="/admin/invites/sha256:abc/../../other-path"` in the HTML. The HTMX client would send a `DELETE` request to the resolved path, potentially targeting a different route.

In practice the token_hash is always written by `mint_invite_token` using `hashlib.sha256` output (hex digits only after the `sha256:` prefix), so there is no realistic path injection under normal operation. But the rendered HTML attribute should enforce URL encoding for the path segment:

**Fix:** URL-encode the hash value when embedding in HTMX attributes:

```python
from urllib.parse import quote as _url_quote
safe_hash_url = _url_quote(inv.get('token_hash', ''), safe='')
...
f'hx-delete="/admin/invites/{safe_hash_url}" '
```

---

### WR-04: Rate-limit constants duplicated between `web/middleware/auth.py` and `system_params.py` — drift risk documented but not enforced

**File:** `web/middleware/auth.py:74-83`

**Issue:** The file comment explicitly acknowledges the duplication:

> "These literals SHADOW system_params.RATE_LIMIT_* — we keep a private copy here because the AST hex-boundary guard rejects ANY occurrence of 'system_params' in this file. Drift risk: low (single operator, infrequent config change). If you bump either copy, bump the other in the same PR."

The current values match `system_params.py` but there is no automated enforcement. A future commit that bumps `system_params.RATE_LIMIT_LOGIN_PER_15M` from 5 to 10 without updating `auth.py` will silently apply different limits to the login route. The LEARNINGS pattern (G-74) requires environment-driven configuration for values that vary per deployment; this case is slightly different (a policy constant) but the drift risk is real.

**Fix:** Add an AST or import-time test that asserts the two sets of literals are equal:

```python
# tests/test_rate_limit_constants.py
def test_rate_limit_constants_not_drifted():
    from system_params import (
        RATE_LIMIT_LOGIN_PER_15M, RATE_LIMIT_FORGOT_PER_HOUR, RATE_LIMIT_RESET_PER_HOUR,
    )
    from web.middleware.auth import (
        RATE_LIMIT_LOGIN_PER_15M as AUTH_LOGIN,
        RATE_LIMIT_FORGOT_PER_HOUR as AUTH_FORGOT,
        RATE_LIMIT_RESET_PER_HOUR as AUTH_RESET,
    )
    assert AUTH_LOGIN == RATE_LIMIT_LOGIN_PER_15M
    assert AUTH_FORGOT == RATE_LIMIT_FORGOT_PER_HOUR
    assert AUTH_RESET == RATE_LIMIT_RESET_PER_HOUR
```

---

### WR-05: `_peek_invite_token` has a TOCTOU window — token can be consumed between peek and consume

**File:** `auth_store/_users.py:333-352`

**Issue:** `_peek_invite_token` reads the auth store without a flock and returns the email if the token is valid and unexpired. The caller (`get_accept_invite` in `web/routes/invite/__init__.py:104`) uses this to validate the token before rendering the password form. Between the peek and the eventual `consume_and_create_user` call (which does hold a flock), a concurrent request could:

1. Concurrent GET `/accept-invite?token=X` → peek succeeds, wizard cookie issued.
2. Admin calls `DELETE /admin/invites/{hash}` → token marked consumed.
3. Invitee submits POST `/accept-invite` → consume fails with `InviteAlreadyConsumed`.

This is an accepted TOCTOU (the revocation wins per design), but the current error handling on step 3 in `post_accept_invite` returns `_render_invite_error_page()` with HTTP 200, which is correct. The issue is that the peek does not check consumed status atomically with the flock—it uses `load_auth` without a lock—meaning if two invitees simultaneously try to accept the same token, both will pass the peek, both will issue wizard cookies, and only the first to reach `consume_and_create_user` will succeed. The second sees an error page. This is the documented behavior, but:

The peek at line 342 iterates the FULL pending_invites list and raises `InviteAlreadyConsumed` on the first matching (but consumed) token. If the token matches NO row at all, it raises `InviteAlreadyConsumed` from line 352. The timing-safety comment at line 338 says it "walks the full pending_invites list before deciding"—but the loop `break`s immediately on first match (line 343), so it does NOT walk the full list before deciding for the happy path. It only walks fully when no match is found.

This means a partial match (e.g., token that matches the first of N invites) short-circuits immediately and skips timing noise for the remaining N-1 invites—a minor timing oracle for enumerating invite list length.

**Fix:** Accept the documented TOCTOU tradeoff but fix the timing claim: remove the comment "Timing-safe: walks the full pending_invites list before deciding" since it is only true for the not-found path. Update the docstring to accurately describe the actual behavior.

---

## Info

### IN-01: Dead code block in `admin_list_users` — user_devices dict built but never populated

**File:** `web/routes/admin/__init__.py:73-79`

**Issue:**

```python
user_devices: dict = {}
for dev in auth_data.get('trusted_devices', []):
    # trusted_devices are global per auth.json v2 schema (not per-user)
    # Phase 37: associate devices per user via device uuid → user lookup
    pass
```

The `for` loop body is `pass`—`user_devices` is never populated. The variable is then never read. This is dead code left over from an incomplete Phase 37 implementation stub. The `last_seen_date` computation at line 96 uses `auth_data.get('trusted_devices', [])` directly instead of the (empty) `user_devices` dict.

**Fix:** Remove lines 73-79 entirely, or implement the per-user device association if it is needed.

---

### IN-02: `test_invite_route_registered_before_auth_middleware` opens file with a relative path — test is environment-sensitive

**File:** `tests/test_web_invite.py:407`

**Issue:**

```python
src = open('web/app.py').read()
```

Uses a relative path. This test will fail if pytest is run from any directory other than the repo root. The project's CLAUDE.md convention requires tests to use absolute paths or `Path(__file__).parent` anchors.

**Fix:**

```python
from pathlib import Path
src = (Path(__file__).parent.parent / 'web' / 'app.py').read_text()
```

---

### IN-03: `_WIZARD_COOKIE_MAX_AGE = 3600` is a magic number not sourced from `system_params`

**File:** `web/routes/invite/__init__.py:36`

**Issue:** The wizard cookie TTL of 3600 seconds (1 hour) is a hardcoded magic number. All other cookie TTLs in the project are defined in `system_params.py` (e.g., `TSI_SESSION_TTL_SECONDS`, `TSI_ENROLL_TTL_SECONDS`, `MAGIC_LINK_TTL_SECONDS`). The `_ENROLL_COOKIE_MAX_AGE = 600` on line 42 mirrors `system_params.TSI_ENROLL_TTL_SECONDS` but is not imported—same pattern as the rate-limit duplication (WR-04). A future change to the enroll TTL in `system_params` won't automatically update this constant.

**Fix:** Add `INVITE_WIZARD_TTL_SECONDS: int = 3600` to `system_params.py` and import it in the invite module. For `_ENROLL_COOKIE_MAX_AGE`, import `TSI_ENROLL_TTL_SECONDS` from `system_params` (or document why the literal shadow is intentional, mirroring the auth.py pattern).

---

_Reviewed: 2026-05-14T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
