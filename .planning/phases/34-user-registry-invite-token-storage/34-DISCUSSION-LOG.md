# Phase 34: User Registry + Invite-Token Storage - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 34-user-registry-invite-token-storage
**Areas discussed:** Flock scope, User record fields, Schema version bump, File size / split

---

## Flock scope

**Q1 — Flock isolation**

| Option | Description | Selected |
|--------|-------------|----------|
| Consume only | fcntl.LOCK_EX only inside consume_and_create_user(); all other helpers keep load→save | ✓ |
| Full mutate_auth() wrapper | Mirror mutate_state(); all auth writes go through flock-backed wrapper | |

**User's choice:** Consume only
**Notes:** Other auth ops remain operator-driven, single-process. No need for full wrapper at this phase.

---

**Q2 — Transactional consume + create**

| Option | Description | Selected |
|--------|-------------|----------|
| Single flock window — consume + create | One LOCK_EX acquire: mark invite consumed AND append user row, then atomic write. Satisfies SC-1. | ✓ |
| Two separate calls | consume_invite_token() + create_user() separately; creates TOCTOU window | |

**User's choice:** Single flock window
**Notes:** SC-1 requirement from ROADMAP.md — no race window where invite consumed but user not created.

---

**Q3 — Standalone create_user()**

| Option | Description | Selected |
|--------|-------------|----------|
| Both helpers | create_user() for test setup/admin bootstrap (no flock) + consume_and_create_user() for invite accept (flock-guarded) | ✓ |
| Only consume_and_create_user() | Only the flock-guarded path; admin bootstrap uses it too | |

**User's choice:** Both helpers

---

**Q4 — Lock fd target**

| Option | Description | Selected |
|--------|-------------|----------|
| Lock auth.json itself | Matches state_manager pattern; one fewer file to manage | ✓ |
| auth.lock sidecar | Separate lock file; fd stays stable across atomic replaces | |

**User's choice:** Lock auth.json itself

---

## User record fields

**Q1 — Fields at Phase 34**

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal + status | uid, email, role, created_at, disabled=False | ✓ |
| Minimal only | uid, email, role, created_at (no disabled) | |
| Full placeholder | + password_hash=None, last_login=None | |

**User's choice:** Minimal + status
**Notes:** disabled needed by RBAC-04 admin view landing in Phase 35.

---

**Q2 — uid format**

| Option | Description | Selected |
|--------|-------------|----------|
| uuid4().hex | Matches existing trusted_devices uuid pattern | ✓ |
| secrets.token_urlsafe(16) | URL-safe base64 string — a second id-generation pattern | |
| You decide | Claude picks | |

**User's choice:** uuid4().hex

---

**Q3 — Admin bootstrap**

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit create only | No auto-bootstrap; create_user() called once from migration/script | ✓ |
| Auto-bootstrap in load_auth() | Insert admin row if users[] empty; breaks pure-read contract | |

**User's choice:** Explicit create only

---

**Q4 — invited_by field**

| Option | Description | Selected |
|--------|-------------|----------|
| Include invited_by | Admin uid on invite row; useful for /admin/users view | ✓ |
| No invited_by | Simpler; can add later if needed | |

**User's choice:** Include invited_by

---

## Schema version bump

**Q1 — Version bump decision**

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — bump to v2 + migration | SCHEMA_VERSION=2; load_auth() detects v1, back-fills arrays, saves immediately | ✓ |
| Yes — bump but no migration logic | Bump version but add arrays as defaults only; no version check | |
| No bump — just add arrays | Keep SCHEMA_VERSION=1; cheapest now | |

**User's choice:** Yes — bump to v2 + migration

---

**Q2 — Migration save behaviour**

| Option | Description | Selected |
|--------|-------------|----------|
| Upgrade + save immediately | load_auth() writes v2 to disk on first read; disk upgraded at startup | ✓ |
| In-memory only, save deferred | Return upgraded dict; next explicit save persists v2; risk: pre-save restart leaves v1 on disk | |

**User's choice:** Upgrade + save immediately

---

## File size / split

**Q1 — Split approach**

| Option | Description | Selected |
|--------|-------------|----------|
| Split into package now | auth_store/ package: __init__.py, _io.py, _devices.py, _magic_links.py, _users.py, _schema.py | ✓ |
| Split invites only | auth_store_invites.py; keep auth_store.py monolithic | |
| Defer split | Accept ~640 LOC; tech-debt note | |

**User's choice:** Split into package now

---

**Q2 — Public API surface**

| Option | Description | Selected |
|--------|-------------|----------|
| __init__.py re-exports all public symbols | Callers keep `from auth_store import X` unchanged; zero import churn | ✓ |
| Callers update imports to submodule | Explicit but requires updating all callers | |

**User's choice:** __init__.py re-exports

---

**Q3 — Test file split**

| Option | Description | Selected |
|--------|-------------|----------|
| Keep one test file | tests/test_auth_store.py stays monolithic; split only if >500 LOC | ✓ |
| Split to match package | tests/test_auth_store_users.py etc. | |

**User's choice:** Keep one test file

---

## Claude's Discretion

- Whether `_schema.py` is a standalone module or TypedDicts are merged into `_io.py`
- `mint_invite_token()` return type: `(raw_token, expires_at_iso)` tuple vs raw token only
- `consume_and_create_user()` return type: `User` dict vs `(True, uid)` tuple
- Log prefix for user/invite ops (consistent `[Auth]` prefix)

## Deferred Ideas

- Full `mutate_auth()` wrapper for all auth writes — deferred to Phase 36+
- `last_login` field on User — Phase 35
- `password_hash` field on User — Phase 37
- Terminal user delete — out of scope per RBAC-04; deferred to v1.3.x
