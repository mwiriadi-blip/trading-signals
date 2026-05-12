# Phase 34: User Registry + Invite-Token Storage - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Pure storage layer — no routes. Convert `auth_store.py` to an `auth_store/` package and add two new arrays to `auth.json`: `users[]` (the user registry) and `pending_invites[]` (invite token records). Implement invite token mint (`mint_invite_token`), verify, and consume helpers with flock-backed single-use guarantee on the consume path. Bump auth schema to v2 with an auto-migration. Admin user is NOT auto-bootstrapped by the storage layer. Observable behaviour is unchanged.

</domain>

<decisions>
## Implementation Decisions

### Flock scope

- **D-01:** `fcntl.LOCK_EX` is isolated to the consume path only — `consume_and_create_user()`. All other auth helpers (devices, magic links, TOTP, new `create_user()`) keep the existing load→save pattern. No `mutate_auth()` wrapper at this phase.

- **D-02:** `consume_and_create_user(unhashed_token, new_user_fields)` holds a single `fcntl.LOCK_EX` window: validate + mark invite consumed AND append the user row, then one atomic write. Satisfies SC-1 (no race window where invite is consumed but user not yet created).

- **D-03:** Standalone `create_user(fields)` helper exists for test setup and admin bootstrap (no flock, operator-driven single-process). `consume_and_create_user()` is the only flock-guarded path.

- **D-04:** Lock fd is opened on `auth.json` itself (not a sidecar `.lock` file). Matches `state_manager/io.py` pattern. Lock is released before `os.replace` swaps in the tempfile (same ordering as state_manager).

### User record fields

- **D-05:** `User` TypedDict fields at Phase 34: `uid` (str), `email` (str), `role` (`"admin" | "ff"`), `created_at` (ISO 8601 UTC str), `disabled` (bool, default `False`). No `password_hash` or `last_login` — those land in Phase 35/37.

- **D-06:** `uid` format: `uuid4().hex` — matches the existing `trusted_devices.uuid` pattern.

- **D-07:** Admin user is bootstrapped explicitly via `create_user()` (e.g., in a one-time migration script or Phase 34 test fixture). `load_auth()` stays side-effect-free — no auto-insert on empty `users[]`.

- **D-08:** `PendingInvite` TypedDict fields: `token_hash` (str, `"sha256:<hex>"`), `email` (str), `invited_by` (uid str), `created_at` (ISO 8601 UTC str), `expires_at` (ISO 8601 UTC str), `consumed` (bool, default `False`), `consumed_at` (str | None).

### Schema version bump

- **D-09:** `SCHEMA_VERSION` bumps to `2`. `load_auth()` detects `schema_version == 1`, back-fills `users=[]` and `pending_invites=[]`, sets `schema_version=2`, and calls `save_auth()` immediately (upgrade + save on first read). Disk reflects v2 after first process startup. Admin user is NOT auto-inserted by migration — stays explicit per D-07.

### File size / package split

- **D-10:** `auth_store.py` → `auth_store/` package. Module layout:
  - `auth_store/__init__.py` — public API re-exports only (zero logic)
  - `auth_store/_io.py` — `_atomic_write`, `_atomic_write_unlocked`, `load_auth`, `save_auth`, `_default_auth_data`, `_resolve_path`, `_quarantine_corrupt_auth_file`, schema migration
  - `auth_store/_devices.py` — trusted-device helpers
  - `auth_store/_magic_links.py` — magic-link helpers
  - `auth_store/_users.py` — `User` + `PendingInvite` TypedDicts, `create_user`, `mint_invite_token`, `consume_and_create_user`, `get_user`, `list_users`, `set_user_disabled`
  - `auth_store/_schema.py` — `AuthData` TypedDict, `TrustedDevice`, `PendingMagicLink`, `SCHEMA_VERSION`, `_ensure_aware`

- **D-11:** `auth_store/__init__.py` re-exports all currently-public symbols. All callers (`web/routes/`, tests) keep `from auth_store import load_auth` etc. unchanged — zero import churn.

- **D-12:** `tests/test_auth_store.py` stays as one file. Only split if it grows past 500 LOC after Phase 34 tests are added.

### Claude's Discretion

- Exact internal module split if `_schema.py` feels like over-engineering — merging TypedDicts into `_io.py` is acceptable if it keeps each file under 500 LOC.
- Whether `mint_invite_token()` returns `(raw_token, expires_at_iso)` tuple or just the raw token (caller computes expiry).
- Log prefix for user/invite operations (`[Auth]` consistent with existing pattern is fine).
- Whether `consume_and_create_user()` returns the newly-created `User` dict or just `(True, uid)` on success.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase goal + requirements
- `.planning/ROADMAP.md` — Phase 34 goal, success criteria, and phase details (§Phase 34: User Registry + Invite-Token Storage)
- `.planning/REQUIREMENTS.md` — RBAC-03 (storage half); RBAC-04 (admin view needs `disabled` field)

### Architecture constraints
- `CLAUDE.md` — hexagonal-lite rules; `auth_store` is a stdlib-only I/O adapter; forbidden imports: `web/`, `signal_engine`, `sizing_engine`, `notifier`, `dashboard`, `main`
- `tests/test_auth_store.py` — `TestForbiddenImports` AST guard; must stay green after package split

### Existing auth_store implementation to split
- `auth_store.py` — 520 LOC monolith to be converted to `auth_store/` package; read fully before splitting
- `auth.json` — current schema v1 on disk; `load_auth()` migration will upgrade to v2 on first read

### Flock pattern to mirror
- `state_manager/io.py` — `_atomic_write` (flock pattern), `_atomic_write_unlocked`, lock-fd ordering (lock destination file, release before os.replace); `consume_and_create_user()` must follow the same sequence

### Prior package split precedent
- `.planning/phases/30-file-size-pre-split/30-CONTEXT.md` — D-01..D-09: package-per-file pattern, 500 LOC cap, audit-first approach
- `.planning/phases/31-core-module-split/31-CONTEXT.md` — `__init__.py` re-export conventions, `_models.py` placement

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `auth_store.py::_atomic_write` — copy verbatim into `auth_store/_io.py`; the flock variant for `consume_and_create_user()` mirrors `state_manager/io.py::_atomic_write`
- `auth_store.py::_atomic_write_unlocked` — same; needed by the flock-guarded path for the inner write
- `uuid.uuid4().hex` — existing uid generation pattern from `add_trusted_device()`; reuse for User uid
- `hashlib.sha256(...).hexdigest()` — already imported and used in `consume_magic_link()`; reuse for invite token hashing
- `hmac.compare_digest` — NOT yet imported in auth_store; needs to be added to `_users.py` (stdlib `hmac` module)
- `secrets.token_urlsafe` — NOT yet imported in auth_store; needs to be added to `_users.py`

### Established Patterns
- Load→mutate→save with `_resolve_path()` monkeypatching hook: all auth helpers follow this pattern; new helpers in `_users.py` must too
- ISO 8601 UTC timestamps via `datetime.now(timezone.utc).isoformat()` — used throughout; new helpers must match
- `path: Path | None = None` kwarg pattern — all public helpers accept this for test redirection
- No flock on low-mutation operator-driven paths — D-01 confirmed; only `consume_and_create_user()` gets the lock

### Integration Points
- `tests/test_auth_store.py::TestForbiddenImports` — AST guard walks `auth_store.py`; after split, must walk the package instead (update import path in test)
- `web/routes/login/`, `web/routes/totp/` — current callers of `load_auth`, `get_totp_secret`, `add_trusted_device`, etc.; must keep working after package split via `__init__.py` re-exports
- `auth.json` on disk — schema v1 today; `load_auth()` v1→v2 migration runs automatically on first process start after deploy

</code_context>

<specifics>
## Specific Ideas

- `token_hash` stored as `"sha256:<hex>"` prefix-tagged string (not bare hex) so the hash algorithm is explicit in the stored value. Consistent with the pattern of tagging stored secrets.
- `consume_and_create_user()` is the canonical name (not `accept_invite()` or `redeem_invite()`) — makes the dual-action semantics clear.
- No auto-bootstrap of admin user in `load_auth()` — load stays a pure read. Admin created explicitly once (migration script or test fixture).

</specifics>

<deferred>
## Deferred Ideas

- Full `mutate_auth()` wrapper for all auth writes — deferred to Phase 36+ when multi-process writes become a real concern.
- `last_login` field on User row — added in Phase 35 when cookie session wires it.
- `password_hash` field on User row — added in Phase 37 when invite acceptance flow lands.
- Terminal user delete — explicitly out of scope per RBAC-04; deferred to v1.3.x.

</deferred>

---

*Phase: 34-user-registry-invite-token-storage*
*Context gathered: 2026-05-13*
