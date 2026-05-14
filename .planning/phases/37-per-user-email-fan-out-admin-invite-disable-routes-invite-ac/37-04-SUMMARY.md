---
phase: 37
plan: "04"
subsystem: invite-acceptance-wizard
tags: [wave-2, rbac-03, invite-wizard, public-routes, bcrypt, totp-zero-coupling, auth-middleware]
dependency_graph:
  requires:
    - 37-01 (Wave 0 test scaffolding)
    - 37-03 (auth_store bcrypt primitives + _peek_invite_token)
  provides:
    - web/routes/invite/__init__.py (register(app), GET/POST /accept-invite, GET/POST /accept-invite/device)
    - web/routes/invite/_renderers.py (step-1 password page, step-3 device page, error page)
    - web/middleware/auth.py PUBLIC_PATHS (+2 entries)
    - web/app.py invite_route.register() BEFORE AuthMiddleware (review #1 fix)
  affects:
    - tests/test_web_invite.py (22 real tests replacing Wave 0 stubs)
tech_stack:
  added: []
  patterns:
    - itsdangerous URLSafeTimedSerializer wizard cookie (step state machine)
    - tsi_enroll.next field zero-coupling pattern (review #6)
    - raw_headers.append multi-cookie pattern (mirror totp/__init__.py)
    - Route registration before AuthMiddleware (Phase 13 D-06 invariant)
    - html.escape(quote=True) on all dynamic render values
key_files:
  created:
    - web/routes/invite/__init__.py (320 lines)
    - web/routes/invite/_renderers.py (257 lines)
  modified:
    - web/middleware/auth.py (PUBLIC_PATHS +2 entries)
    - web/app.py (invite_route import + register call before add_middleware)
    - tests/test_web_invite.py (478 lines — Wave 0 stubs replaced with 22 real tests)
decisions:
  - "Zero coupling to totp module via tsi_enroll.next field — existing line-203 reader handles redirect, NO changes to web/routes/totp/__init__.py (review #6)"
  - "GET /accept-invite/device transitions wizard cookie from step=totp to step=device server-side — self-contained in invite module, no TOTP hook needed"
  - "Partial enrollment (User row created, TOTP not completed) accepted as documented degraded path in v1.3 — admin must issue new invite for recovery (review #2)"
  - "invite_route.register() placed BEFORE add_middleware(AuthMiddleware) in create_app() — Phase 13 D-06 invariant, review #1 deployment-blocker fix"
  - "hash_password ValueError (>72 bytes) caught in POST /accept-invite → 400 re-render, NOT 500 (review #9)"
metrics:
  duration: "~16 minutes"
  completed: "2026-05-14T08:26:00Z"
  tasks: 1
  files_modified: 5
---

# Phase 37 Plan 04: Invite Acceptance Wizard Summary

**One-liner:** Public /accept-invite wizard wired end-to-end — password + TOTP + device steps, zero TOTP module coupling via tsi_enroll.next field, review #1 deployment-blocker fixed, partial-enrollment path documented.

---

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| RED | Failing tests for invite wizard (22 tests) | `1672109` | tests/test_web_invite.py |
| GREEN | web/routes/invite/ package + PUBLIC_PATHS + app.py registration | `e9b49b3` | web/routes/invite/__init__.py, web/routes/invite/_renderers.py, web/middleware/auth.py, web/app.py |

---

## New Package: web/routes/invite/

**Line counts:**
- `web/routes/invite/__init__.py`: 320 lines
- `web/routes/invite/_renderers.py`: 257 lines

**Public surface (register(app) closure):**

| Handler | Method | Path | Description |
|---------|--------|------|-------------|
| `get_accept_invite` | GET | `/accept-invite` | Peek token (no consume) → step-1 form or error page |
| `post_accept_invite` | POST | `/accept-invite` | Validate pw → bcrypt → consume+create user → /enroll-totp |
| `get_invite_device` | GET | `/accept-invite/device` | Transition step=totp → step=device, render step-3 |
| `post_invite_device` | POST | `/accept-invite/device` | Optional tsi_trusted → clear wizard → 302 / |

---

## PUBLIC_PATHS Diff

```python
# Before:
PUBLIC_PATHS = frozenset({
  '/login', '/logout', '/enroll-totp', '/verify-totp',
  '/forgot-2fa', '/reset-totp',
})

# After (Phase 37):
PUBLIC_PATHS = frozenset({
  '/login', '/logout', '/enroll-totp', '/verify-totp',
  '/forgot-2fa', '/reset-totp',
  '/accept-invite',         # Phase 37 D-04
  '/accept-invite/device',  # Phase 37 D-04
})
```

+2 entries. Both paths listed explicitly (middleware uses exact-match).

---

## Review #1: Route Registration Ordering (Deployment Blocker)

`web/app.py` changes:

1. Added import: `from web.routes import invite as invite_route`
2. Added call: `invite_route.register(application)` placed AFTER `reset_route.register(application)` and BEFORE `application.add_middleware(AuthMiddleware, ...)`.

Verification (acceptance criterion):

```python
# grep -n "invite_route.register|application.add_middleware(AuthMiddleware" web/app.py
# invite_route.register at pos N < add_middleware at pos M: CONFIRMED
```

`TestRouteRegistration.test_invite_route_registered_before_auth_middleware` pins this ordering at test time. Without this fix, all wizard routes return 404 on deploy (Phase 13 D-06 invariant).

---

## Review #6: Zero TOTP Module Coupling

**Key insight:** The existing TOTP post-enroll handler at `web/routes/totp/__init__.py` line 203 already reads `payload.get('next', '/')` from the `tsi_enroll` cookie and uses it as the post-enroll redirect target. This path existed before Phase 37 (used by the `?reset=1` flow which issues a fresh tsi_enroll with `next='/'`).

**Implementation:** `post_accept_invite` issues a `tsi_enroll` cookie with payload:
```python
{'uid': uid, 'email': email, 'next': '/accept-invite/device'}
```

The existing totp line-203 reader consumes this `next` field and redirects to `/accept-invite/device` after TOTP enrollment. **ZERO changes to `web/routes/totp/__init__.py`.**

**Acceptance criterion:**
- `git diff --name-only HEAD -- web/routes/totp/__init__.py | wc -l` → 0 (file not in diff)
- `grep -q "'next': '/accept-invite/device'" web/routes/invite/__init__.py` → OK
- `TestNextFieldForTOTPHandoff.test_tsi_enroll_carries_next_field_for_invite_wizard` → GREEN

---

## Review #2: Partial Enrollment Degraded Path

**Decision (consensus #2):** Partial enrollment (User row created, TOTP secret not yet enrolled) is an accepted degraded state in v1.3. The invite token is single-use; after `consume_and_create_user` completes, the token is marked consumed. If the invitee navigates back to the original invite URL, they see the standard "link expired or already used" error page (200, D-07). No automatic recovery.

**Recovery path (admin):** Admin must issue a new invite for the same email. However, `consume_and_create_user` enforces unique email — the second consume will fail because the email row already exists. Full recovery requires a "delete partial user" admin action, deferred to a follow-up phase.

**Test:** `TestPartialEnrollmentRecovery.test_reused_invite_token_after_user_created_renders_error_page` pins this behavior (GREEN).

---

## Review #9 Integration: Password >72 Bytes Returns 400

`post_accept_invite` catches `ValueError` from `auth_store.hash_password()`:

```python
try:
    pw_hash = auth_store.hash_password(password)
except ValueError as ve:
    return HTMLResponse(
        content=_render_step1_password_page(email, error=f'Password is too long...'),
        status_code=400,
    )
```

`TestStep1Password.test_password_over_72_bytes_returns_400` verifies this returns 400 (not 500). The route catches the ValueError at the HTTP boundary — never propagates to a 500 server error.

---

## Cookie Schema

| Cookie | Salt | Max-Age | Attributes | Payload Shape per Step |
|--------|------|---------|------------|------------------------|
| `tsi_invite_wizard` | `tsi-invite-wizard` | 3600s | Secure; HttpOnly; SameSite=Strict | `{step: 'password', raw_token, email}` → `{step: 'totp', uid, email}` → `{step: 'device', uid, email}` |
| `tsi_enroll` | `tsi-enroll-cookie` | 600s | Secure; HttpOnly; SameSite=Strict | `{uid, email, next: '/accept-invite/device'}` (review #6) |
| `tsi_trusted` | `tsi-trusted-cookie` | 2592000s | Secure; HttpOnly; SameSite=Strict | `{uuid, iat}` (issued only if trust_device truthy) |

**Step transitions enforced server-side:**
- `post_accept_invite` requires `step == 'password'` → redirects to `/login` otherwise
- `get_invite_device` accepts `step in ('totp', 'device')` → transitions to `step=device`
- `post_invite_device` requires `step == 'device'` → redirects to `/login` otherwise

---

## Test Class Inventory (tests/test_web_invite.py)

| Class | Methods | Covers |
|-------|---------|--------|
| `TestExpiredToken` | 5 | D-07: expired/consumed/missing/unknown tokens → 200 error page; public access (no 401) |
| `TestStep1Password` | 7 | GET form rendering; POST short/mismatch/72-byte/valid/no-cookie/wrong-step; review #6 next field |
| `TestStep3Device` | 4 | Trust device → tsi_trusted; no trust → redirect only; no cookie → /login; GET transition |
| `TestRouteRegistration` | 2 | Review #1: routes in app.routes; line ordering verified |
| `TestPartialEnrollmentRecovery` | 1 | Review #2: consumed token after user creation → 200 error page |
| `TestNextFieldForTOTPHandoff` | 2 | Review #6: tsi_enroll.next == '/accept-invite/device'; TOTP module not modified |
| **Total** | **22** | **All GREEN** |

---

## No Raw Token in Any Log Line

Acceptance criterion verified:

```bash
grep -nE "logger\.(info|warning|error|debug).*raw_token|logger\.(info|warning|error|debug).*token=" \
  web/routes/invite/__init__.py
# → empty (no output)
```

Only `email` and `uid` are logged. The `raw_token` field in the wizard cookie is never interpolated into any log line (T-37-04-05).

---

## Render Helpers: html.escape(quote=True)

All dynamic values in `web/routes/invite/_renderers.py` use `html.escape(value, quote=True)`. The static pages (`_render_step3_device_page`, `_render_invite_error_page`) have no dynamic values. Acceptance criterion:

```bash
grep -nE "html\.escape\([^)]*\)" web/routes/invite/_renderers.py | grep -v "quote=True"
# → empty (all uses include quote=True)
```

---

## Deviations from Plan

None. Plan executed exactly as written.

---

## Threat Surface Scan

Two new public HTTP endpoints introduced:

| Flag | File | Description |
|------|------|-------------|
| threat_flag: public-route | web/routes/invite/__init__.py | GET /accept-invite: unauthenticated; raw_token in query string is the auth mechanism. Added to PUBLIC_PATHS per plan (T-37-04-08). |
| threat_flag: public-route | web/routes/invite/__init__.py | POST /accept-invite: plaintext password crosses HTTPS boundary; bcrypt-hashed before storage. SameSite=Strict cookie is the CSRF protection (T-37-04-03). |
| threat_flag: public-route | web/routes/invite/__init__.py | GET/POST /accept-invite/device: wizard cookie is the auth mechanism. Added to PUBLIC_PATHS. |

All threats covered by plan's threat register (T-37-04-01 through T-37-04-13). No new surface beyond the planned scope.

---

## Known Stubs

None. All production code is fully implemented. All 22 tests are real assertions (no pytest.skip).

---

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| web/routes/invite/__init__.py exists | FOUND |
| web/routes/invite/_renderers.py exists | FOUND |
| PUBLIC_PATHS contains /accept-invite | FOUND |
| PUBLIC_PATHS contains /accept-invite/device | FOUND |
| invite_route.register in web/app.py | FOUND |
| invite_route.register BEFORE add_middleware | VERIFIED |
| tsi_enroll next='/accept-invite/device' in code | FOUND |
| web/routes/totp/__init__.py NOT in diff | VERIFIED (0 lines) |
| No raw token in log lines | VERIFIED (empty grep) |
| html.escape(quote=True) on all dynamic values | VERIFIED |
| Cookie attrs Secure + HttpOnly + SameSite=Strict | VERIFIED |
| All 22 test_web_invite.py tests GREEN | PASS |
| Existing TOTP tests GREEN (test_web_routes_totp.py) | PASS |
| Full suite 2295 passed, 0 failed | PASS |
| Commit 1672109 exists (RED) | FOUND |
| Commit e9b49b3 exists (GREEN) | FOUND |
