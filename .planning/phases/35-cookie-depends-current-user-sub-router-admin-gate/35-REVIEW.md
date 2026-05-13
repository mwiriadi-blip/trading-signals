---
phase: 35
status: has_issues
reviewed_at: 2026-05-13T05:14:49Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - auth_store/_users.py
  - auth_store/__init__.py
  - web/routes/totp/__init__.py
  - web/middleware/auth.py
  - web/dependencies.py
  - web/routes/admin/__init__.py
  - web/app.py
---

## Summary

Phase 35 adds RBAC foundations: `get_user_by_email`, `uid` in session cookies, middleware `user_id` population, `current_user_id`/`require_admin` Depends factories, and the `/admin` sub-router. The core wiring is sound. Two security gaps stand out: `require_admin` does not enforce the `disabled` flag on user rows, and `consume_and_create_user` does not validate that the registrant email matches the invite's intended email.

## Findings

### Critical

**[CR-01] [web/dependencies.py:34-44] — `require_admin` ignores `disabled` flag; a disabled admin retains full admin access.**

`require_admin` checks `row.get('role') != 'admin'` but never checks `row.get('disabled')`. A user disabled via `set_user_disabled(uid, True)` with an existing valid session cookie can still reach every `/admin/*` route. The `disabled` field exists precisely to revoke access, but the gate never reads it.

Severity: **Critical**

Fix:
```python
def require_admin(request: Request) -> str:
  uid = getattr(request.state, 'user_id', None)
  if uid is None:
    raise HTTPException(status_code=403, detail=_DETAIL_ADMIN_REQUIRED)
  row = get_user(uid)
  if row is None or row.get('role') != 'admin' or row.get('disabled'):
    raise HTTPException(status_code=403, detail=_DETAIL_ADMIN_REQUIRED)
  return uid
```

The same gap applies to `current_user_id` — it never checks `disabled` either. Fix both together in Phase 36 or as a separate Phase 35 fix phase.

---

**[CR-02] [auth_store/_users.py:201-270] — `consume_and_create_user` does not enforce that `new_user_fields['email']` matches the invite's `email` field.**

The invite row stores the intended invitee email (`matched_row['email']`). After validating the token, the function creates a user with `email` taken from `new_user_fields` — which the caller supplies independently. Anyone holding a valid token can register with any email address, not just the one the invite was issued for. This breaks invite-scoping and allows email squatting.

Severity: **Critical**

Fix: After the expiry check, assert the emails match (case-insensitive, consistent with `get_user_by_email`):
```python
invite_email = matched_row.get('email', '')
if invite_email.lower() != email.lower():
  raise ValueError(
    f'email mismatch: invite issued for {invite_email!r}, '
    f'got {email!r}'
  )
```

---

### Warning

**[WR-01] [web/middleware/auth.py:253-269] — D-04 shim calls `get_user_by_email(uname)` where `uname` is the `u` field from the cookie, treating it as an email. This implicit contract (WEB_AUTH_USERNAME == user email in auth.json) is not validated at startup.**

If the operator creates their user row with an email that differs from `WEB_AUTH_USERNAME`, the D-04 shim silently returns `uid=None` on every legacy cookie request, causing the admin gate to return 403 unexpectedly after a deploy. There is no boot-time check linking `WEB_AUTH_USERNAME` to the `users` table.

Severity: **Warning**

Fix: Either document the requirement explicitly in `_read_auth_credentials` as a validated invariant (fail closed on mismatch if a user row exists), or emit a startup WARNING log if `get_user_by_email(username)` returns `None` at app construction time.

---

**[WR-02] [web/routes/totp/__init__.py:107] — TOTP provisioning URI hardcodes the operator domain `signals.mwiriadi.me`.**

```python
name=f'{uname}@signals.mwiriadi.me',
```

This is a personal domain baked into source code. If the service is redeployed under any other domain, every TOTP authenticator app shows `marc@signals.mwiriadi.me` as the account label. Should be driven from an env var or `system_params`.

Severity: **Warning**

Fix:
```python
issuer = os.environ.get('TOTP_ISSUER', 'Trading Signals')
domain = os.environ.get('TOTP_DOMAIN', 'signals.mwiriadi.me')
name = f'{uname}@{domain}'
```

---

### Info

**[IN-01] [tests/test_web_auth_middleware.py:977-998] — `test_default_user_id_is_none_on_public_path` contains no meaningful assertion; ends with `assert True`.**

The test body explicitly abandons its stated behavioral goal and defers to "AST check above + header_auth test". The test name implies a behavioral regression check but makes no runtime assertion. This gives false confidence in the test suite's coverage.

Severity: **Info**

Fix: Either delete the test (the coverage it claims is covered elsewhere) or replace it with a real assertion using a `/healthz`-path request with the capture fixture to confirm `user_id` is not leaked via `request.state` across requests.

---

**[IN-02] [tests/test_auth_store.py:870-879] — `test_get_user_by_email_returns_none_for_empty_string_arg` docstring claims "even if a row has email=''" but the test only seeds a row with a real email.**

The function would in fact match a row with `email=''` when called with `''` (since `''.lower() == ''`). The test does not cover that edge case; it only incidentally passes because `'real@example.com'.lower() != ''`. The docstring is misleading.

Severity: **Info**

Fix: Rename the test to `test_get_user_by_email_returns_none_for_empty_string_when_no_empty_row_exists` and add a companion test that seeds a row with `email=''` directly and verifies it IS found (or add an explicit guard in `get_user_by_email` to return `None` when `not needle`).

---

**[IN-03] [web/dependencies.py:22] — `current_user_id` return type annotation is `-> str` but the function can only return after confirming `uid is not None`, so the annotation is technically correct. However it does not check `disabled`, making the annotation misleading once disabled-user enforcement is added (see CR-01).**

Severity: **Info**

Noted as a follow-up for Phase 36 when `current_user_id` is adopted by non-admin routes.
