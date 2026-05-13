# Phase 35: Cookie + Depends(current_user) + Sub-Router Admin Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 35-cookie-depends-current-user-sub-router-admin-gate
**Areas discussed:** uid lookup at login, Session payload shape, Header auth uid, Admin sub-router scope

---

## uid lookup at login

| Option | Description | Selected |
|--------|-------------|----------|
| `get_user_by_email` | Add `get_user_by_email(email)` to auth_store._users. Login flow passes username (admin email) — clean, general, works for F&F users too. | ✓ |
| `get_user_by_role('admin')` | Scan users[] for first row where role=='admin'. Works now but fragile if ever more than one admin. | |
| Env-var ADMIN_UID | Store admin's uid in .env as ADMIN_UID. No auth.json read at login. Operationally awkward. | |

**User's choice:** `get_user_by_email` (Recommended)
**Notes:** None

---

## uid lookup fallback (login fails)

| Option | Description | Selected |
|--------|-------------|----------|
| Issue cookie with uid=None, shim treats as admin | Session still issued. Middleware sees uid=None, applies shim: treat as admin. Admin can log in during bootstrap gap. | ✓ |
| Block login — admin MUST be in users[] first | If get_user_by_email returns None, refuse session. Admin cannot log in until bootstrapped. Strict but operationally risky on first deploy. | |

**User's choice:** Issue cookie with uid=None, shim treats as admin (Recommended)
**Notes:** Grace period for first deploy before admin bootstrap.

---

## Session payload shape

| Option | Description | Selected |
|--------|-------------|----------|
| `{'u': uname, 'uid': uid, 'iat': int}` | Keep 'u' alongside new 'uid'. Old cookies still decode. Shim checks 'uid' presence only. | ✓ |
| `{'uid': uid, 'iat': int}` — drop 'u' | Cleaner payload. Shim must handle both old (has 'u', no 'uid') and new (has 'uid', no 'u'). Old sessions invalid until re-login. | |

**User's choice:** `{'u': uname, 'uid': uid, 'iat': int}` (Recommended)
**Notes:** Backward compatibility — no forced re-login on deploy.

---

## Backward-compat shim location

| Option | Description | Selected |
|--------|-------------|----------|
| In `_try_cookie` | AuthMiddleware._try_cookie reads payload; uid absent/None → shim resolves admin uid. One place, clear intent. | ✓ |
| In `current_user_id` Depends | Middleware sets user_id = payload.get('uid') (may be None). Dependency handles None by looking up admin. Pushes logic to dependency layer. | |

**User's choice:** In `_try_cookie` (Recommended)
**Notes:** Keeps shim logic at the auth boundary, not leaking into the dependency layer.

---

## Header auth uid

| Option | Description | Selected |
|--------|-------------|----------|
| Look up admin uid from users[] | Call get_user_by_email(admin_email) in _try_header. One extra auth.json read per header-auth request. Always accurate. | |
| Same shim as cookie: None → admin lookup in _try_cookie shim | Header auth sets user_id = None. Downstream handles None by looking up admin. | |
| Keep header auth uid-free (constant) | Header auth is legacy operator-only path. Set user_id to constant sentinel or None. No auth.json read. Scripts don't need per-user scoping. | ✓ |

**User's choice:** Keep header auth uid-free (Recommended)
**Notes:** Header auth is legacy/script-only. Scripts never hit admin-gated or per-user routes.

---

## Header auth sentinel value

| Option | Description | Selected |
|--------|-------------|----------|
| None | request.state.user_id = None. Depends(current_user_id) raises 403 for header-only callers trying to use per-user routes. Scripts never need current_user_id. | ✓ |
| admin email string | request.state.user_id = 'mwiriadi@gmail.com'. Not a uid format — could cause confusion. | |
| `"__admin__"` constant | Sentinel string that require_admin checks for explicitly. Adds a special case. | |

**User's choice:** None (Recommended)
**Notes:** Clean — header-auth callers on `/admin/*` get 403 intentionally.

---

## Admin sub-router scope

| Option | Description | Selected |
|--------|-------------|----------|
| Shell only — Phase 36 adds routes | No /admin/* routes in Phase 35. Startup invariant passes vacuously (0 paths). 403-sweep runs on empty set. | |
| Add /admin/ping health route | Adds minimal GET /admin/ping → 200 {"ok": true}. Startup invariant and 403-sweep have a real path. Tests are concrete, not vacuous. | ✓ |

**User's choice:** Add /admin/ping health route (Recommended)
**Notes:** Makes the RBAC-02 startup invariant meaningful from day 1.

---

## require_admin check mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Re-read role from auth.json via `get_user(uid)` | require_admin calls get_user(request.state.user_id), checks role=='admin'. One auth.json read per admin-gated request. Authoritative — role changes immediate. | ✓ |
| Cache role in session cookie payload | Add 'role' to session payload. No auth.json read at all. But role changes don't take effect until re-login. | |

**User's choice:** Re-read role from auth.json via `get_user(uid)` (Recommended)
**Notes:** Authoritative. Single admin, few gated requests — extra read is negligible.

---

## Claude's Discretion

- Whether `require_admin` returns `str` (uid) or `dict` (full User row)
- Exact module name for startup invariant test (new file vs appended to `test_web_app.py`)
- Whether `get_user_by_email` uses linear scan or adds an index
- Whether `request.state.user_id` is typed as `str | None` or left untyped
- Whether `update_last_login(uid)` is added in this phase (deferred from Phase 34)

## Deferred Ideas

- `update_last_login(uid)` call after session issuance — deferred from Phase 34, can land in Phase 35 at Claude's discretion
- `mutate_auth()` wrapper — deferred to Phase 36+ per Phase 34 D-01
- Caching `require_admin` results per-request — premature at this scale
