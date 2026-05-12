# Phase 34: User Registry + Invite-Token Storage - Research

**Researched:** 2026-05-13
**Domain:** Python stdlib — fcntl, secrets, hmac, hashlib, uuid; auth.json schema migration; package split
**Confidence:** HIGH

## Summary

Phase 34 converts `auth_store.py` (a 520-LOC flat module) into an `auth_store/` package, adds a `users[]` and `pending_invites[]` array to `auth.json`, bumps the schema to v2 with an auto-migration, and implements invite-token mint/verify/consume with a flock-guarded single-use consume path. All decisions are locked in CONTEXT.md (D-01..D-12). Research confirms the stdlib primitives are available, the flock pattern is directly cloneable from `state_manager/io.py`, and the package-split precedent from Phases 30–31 fully applies.

Key risks: `tests/test_auth_store.py` is already 620 LOC — after Phase 34 tests land it will reach ~740 LOC. D-12 says "only split if it grows past 500 LOC after Phase 34 tests are added" but the file already exceeds 500. The planner must decide whether to declare D-12 satisfied (stay one file, tolerate > 500) or split as part of this phase. The `TestForbiddenImports` class hardcodes `AUTH_STORE_PATH = Path('auth_store.py')` — this must be updated to walk the `auth_store/` package directory after the split.

**Primary recommendation:** Two-plan structure — Plan A: package split + schema migration + new TypedDicts; Plan B: `_users.py` implementation (create_user, mint_invite_token, consume_and_create_user, get_user, list_users, set_user_disabled) + tests. Keeps each plan independently verifiable.

## User Constraints (from CONTEXT.md)

<user_constraints>

### Locked Decisions

- D-01: fcntl.LOCK_EX only on `consume_and_create_user()`.
- D-02: `consume_and_create_user(unhashed_token, new_user_fields)` — single LOCK_EX window.
- D-03: `create_user(fields)` — no flock, for test setup and admin bootstrap.
- D-04: Lock fd on `auth.json` itself (not sidecar). Same ordering as state_manager/io.py.
- D-05: User TypedDict: uid, email, role ("admin"|"ff"), created_at (ISO 8601 UTC), disabled (bool, default False).
- D-06: uid = uuid4().hex.
- D-07: load_auth() stays side-effect-free — NO auto-bootstrap.
- D-08: PendingInvite TypedDict: token_hash, email, invited_by, created_at, expires_at, consumed (bool), consumed_at (str|None).
- D-09: SCHEMA_VERSION 1→2 migration in load_auth(); backfill users=[], pending_invites=[]; call save_auth() immediately.
- D-10: Package layout: auth_store/__init__.py, _io.py, _devices.py, _magic_links.py, _users.py, _schema.py.
- D-11: __init__.py re-exports all currently-public symbols; zero import churn.
- D-12: tests/test_auth_store.py stays one file (unless already > 500 LOC after additions).

### Claude's Discretion

- Whether `_schema.py` is needed or TypedDicts can merge into `_io.py`.
- Whether `mint_invite_token()` returns `(raw_token, expires_at_iso)` or just raw token.
- Log prefix for user/invite ops.
- Whether `consume_and_create_user()` returns new `User` dict or `(True, uid)`.

### Deferred Ideas (OUT OF SCOPE)

- Full `mutate_auth()` wrapper — deferred to Phase 36+.
- `last_login` field — Phase 35.
- `password_hash` field — Phase 37.
- Terminal user delete — v1.3.x.

</user_constraints>

## Phase Requirements

<phase_requirements>

| ID | Description | Research Support |
|----|-------------|------------------|
| RBAC-03 (storage half) | Admin issues invite token (secrets.token_urlsafe(32) raw, sha256 hash stored, hmac.compare_digest verify, 7-day expiry, single-use via flock on consume) | All stdlib primitives confirmed available. flock pattern cloned from state_manager/io.py._atomic_write. |
| RBAC-04 | `disabled` field on User row; admin can reversibly disable non-admin user; data preserved | User TypedDict (D-05) includes disabled bool. set_user_disabled() in _users.py covers this. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| User registry (users[]) | auth_store/_users.py | auth_store/_io.py | Storage-only layer; no web routes this phase |
| Invite token mint | auth_store/_users.py | — | Pure stdlib operation; no web exposure |
| Invite consume (flock) | auth_store/_users.py | auth_store/_io.py | Flock pattern mirrors state_manager/io.py exactly |
| Schema migration v1→v2 | auth_store/_io.py (load_auth) | — | D-09: load_auth runs migration; _io.py owns load/save |
| TypedDicts (User, PendingInvite, AuthData) | auth_store/_schema.py | (or merged into _io.py) | Shared shape definitions used by _users.py and _io.py |
| Public re-export surface | auth_store/__init__.py | — | D-11: zero import churn for callers |

## Standard Stack

### Core (all stdlib — no new deps)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| secrets | stdlib (3.6+) | token_urlsafe(32) mint | [VERIFIED: stdlib] Cryptographically secure random URL-safe token |
| hmac | stdlib | compare_digest for timing-safe compare | [VERIFIED: stdlib] Prevents timing oracle on token comparison |
| hashlib | stdlib | sha256 hash of raw token before storage | [VERIFIED: stdlib] Already used in auth_store.py::consume_magic_link |
| fcntl | stdlib (POSIX) | LOCK_EX on consume path | [VERIFIED: stdlib] Already used in state_manager/io.py |
| uuid | stdlib | uuid4().hex for uid | [VERIFIED: stdlib] Already used in auth_store.py::add_trusted_device |
| datetime/timedelta/timezone | stdlib | ISO 8601 UTC stamps, expiry calculation | [VERIFIED: stdlib] Already used throughout auth_store.py |

**No new dependencies.** All primitives present and already imported across auth_store.py and state_manager/io.py.

**Installation:** none required.

## Architecture Patterns

### System Architecture Diagram

```
Test / Admin caller
        |
        v
auth_store/__init__.py     <-- public API, re-exports only
    |         |         |
    v         v         v
 _io.py   _users.py  _devices.py / _magic_links.py
 (load_    (create_   (existing helpers, moved verbatim)
  save_    user,
  atomic   mint_
  write,   invite_
  migrate) consume_    <-- fcntl.LOCK_EX on consume only
           get_user
           list_users
           set_user
           _disabled)
    |
    v
auth.json (schema v2)
  schema_version: 2
  users: [...]
  pending_invites: [...]
  trusted_devices: [...]
  pending_magic_links: [...]
  totp_secret / totp_enrolled / totp_enrolled_at
```

### Recommended Project Structure

```
auth_store/
├── __init__.py       # re-exports only; zero logic
├── _schema.py        # AuthData, User, PendingInvite, TrustedDevice, PendingMagicLink TypedDicts; SCHEMA_VERSION; _ensure_aware
├── _io.py            # _atomic_write, _atomic_write_unlocked, load_auth (with v1→v2 migration), save_auth, _default_auth_data, _resolve_path, _quarantine_corrupt_auth_file
├── _devices.py       # add_trusted_device, revoke_device, revoke_all_other_devices, get_trusted_device, update_last_seen, is_uuid_active
├── _magic_links.py   # add_magic_link, consume_magic_link, count_recent_magic_links, purge_expired_magic_links
└── _users.py         # User, PendingInvite (or import from _schema), create_user, mint_invite_token, consume_and_create_user, get_user, list_users, set_user_disabled
```

### Pattern 1: Package Split with Re-Export __init__.py

**What:** `auth_store.py` → `auth_store/` package. All currently-public symbols re-exported from `__init__.py`. Callers unchanged.
**When to use:** When a flat module exceeds 500 LOC or needs logical subdivision. Precedent: Phase 30 (web/routes splits), Phase 31 (state_manager/, sizing_engine/).

```python
# Source: auth_store/__init__.py — pattern from Phase 30/31 __init__.py precedent [VERIFIED: codebase]
from auth_store._io import load_auth, save_auth
from auth_store._devices import (
  add_trusted_device, revoke_device, revoke_all_other_devices,
  get_trusted_device, update_last_seen, is_uuid_active,
)
from auth_store._magic_links import (
  add_magic_link, consume_magic_link, count_recent_magic_links,
  purge_expired_magic_links,
)
from auth_store._users import (
  create_user, mint_invite_token, consume_and_create_user,
  get_user, list_users, set_user_disabled,
)
from auth_store._schema import (
  AuthData, User, PendingInvite, TrustedDevice, PendingMagicLink,
  SCHEMA_VERSION,
)
```

### Pattern 2: flock on consume path (single LOCK_EX window)

**What:** Open lock fd on auth.json, acquire LOCK_EX, load → validate invite → mark consumed AND append user → write via `_atomic_write_unlocked`, release lock.
**When to use:** Any path where two state mutations (consume + create user) must be atomic across processes.

```python
# Source: state_manager/io.py::_atomic_write [VERIFIED: codebase]
# consume_and_create_user mirrors this pattern exactly
import fcntl, os

def consume_and_create_user(unhashed_token, new_user_fields, path=None):
  resolved = _resolve_path(path)
  lock_fd = os.open(str(resolved), os.O_RDWR | os.O_CREAT, 0o600)
  try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
      data = _load_auth_unlocked(resolved)   # raw load, no flock
      # validate invite (expiry, consumed flag, hmac.compare_digest)
      # mark invite consumed
      # append user row
      _atomic_write_unlocked(json.dumps(data, ...) + '\n', resolved)
    finally:
      fcntl.flock(lock_fd, fcntl.LOCK_UN)
  finally:
    os.close(lock_fd)
```

Note: `_load_auth_unlocked` is a raw file-read helper that does NOT call `fcntl.flock` — identical to how `state_manager/io.py::mutate_state` calls `_save_state_unlocked` to avoid intra-process flock-on-different-fd deadlock. [VERIFIED: codebase D-14/Phase 14 flock note]

### Pattern 3: Token mint + hash storage

**What:** Mint raw token with `secrets.token_urlsafe(32)`, store only `"sha256:<hex>"` prefix-tagged hash in `pending_invites[]`. Verify via `hmac.compare_digest(stored_hash, recomputed_hash)`.

```python
# Source: [VERIFIED: stdlib docs; pattern mirrors consume_magic_link in auth_store.py]
import secrets, hashlib, hmac

def mint_invite_token():
  raw = secrets.token_urlsafe(32)      # 43-char URL-safe base64 string
  digest = hashlib.sha256(raw.encode()).hexdigest()
  token_hash = f'sha256:{digest}'      # prefix-tagged per CONTEXT specifics
  return raw, token_hash

def _verify_token(unhashed_token, stored_hash):
  if not stored_hash.startswith('sha256:'):
    return False
  expected = 'sha256:' + hashlib.sha256(unhashed_token.encode()).hexdigest()
  return hmac.compare_digest(stored_hash, expected)
```

### Pattern 4: Schema v1→v2 migration in load_auth()

**What:** Detect `schema_version == 1`, backfill `users=[]` and `pending_invites=[]`, bump to 2, call `save_auth()` immediately. D-09.

```python
# Source: state_manager/migrations.py pattern [VERIFIED: codebase]
def load_auth(path=None):
  resolved = _resolve_path(path)
  # ... existing load/corrupt-quarantine logic ...
  if payload.get('schema_version') == 1:
    payload['users'] = payload.get('users', [])
    payload['pending_invites'] = payload.get('pending_invites', [])
    payload['schema_version'] = 2
    save_auth(payload, path=path)
  return payload
```

### Pattern 5: AuthData TypedDict extension (v2)

```python
# Source: auth_store/_schema.py [ASSUMED — new code for this phase]
class User(TypedDict):
  uid: str           # uuid4().hex
  email: str
  role: str          # "admin" | "ff"
  created_at: str    # ISO 8601 UTC
  disabled: bool     # default False

class PendingInvite(TypedDict):
  token_hash: str    # "sha256:<hex>"
  email: str
  invited_by: str    # uid of issuing admin
  created_at: str
  expires_at: str    # created_at + 7 days
  consumed: bool
  consumed_at: str | None

class AuthData(TypedDict):  # v2 extension
  schema_version: int
  totp_secret: str | None
  totp_enrolled: bool
  totp_enrolled_at: str | None
  trusted_devices: list[TrustedDevice]
  pending_magic_links: list[PendingMagicLink]
  users: list[User]           # NEW in v2
  pending_invites: list[PendingInvite]  # NEW in v2
```

### Anti-Patterns to Avoid

- **Calling save_auth() inside the flock window via the public save_auth():** save_auth() calls `_atomic_write()` which tries to acquire LOCK_EX — deadlock. Use `_atomic_write_unlocked()` directly inside the flock window (same fix as Phase 14 D-13 for state_manager).
- **Hashing with bare hexdigest (no prefix tag):** `token_hash` must be `"sha256:<hex>"` not bare hex, to make algorithm explicit (per CONTEXT specifics).
- **Logging the raw or hashed token:** consume_magic_link precedent shows neither raw nor hash is logged. Same policy for invite tokens.
- **Auto-bootstrapping admin in load_auth():** D-07 explicitly forbids side-effects in load. Admin is created via explicit `create_user()` call.
- **Adding flock to create_user():** D-01 explicitly restricts flock to consume path only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timing-safe token compare | `stored == computed` | `hmac.compare_digest` | String equality leaks timing; stdlib compare_digest is constant-time [VERIFIED: Python docs] |
| Cryptographic token generation | random.choices / os.urandom direct | `secrets.token_urlsafe(32)` | secrets module purpose-built for tokens; URL-safe base64 output [VERIFIED: stdlib] |
| Atomic file rename | open/write/close | tempfile + fsync + os.replace | Already pattern in auth_store._atomic_write; don't duplicate or vary [VERIFIED: codebase] |
| Expiry calculation | custom timedelta math | `datetime.now(timezone.utc) + timedelta(days=7)` | Already pattern in purge_expired_magic_links [VERIFIED: codebase] |

## Common Pitfalls

### Pitfall 1: Flock deadlock on same fd
**What goes wrong:** `consume_and_create_user` acquires LOCK_EX, then calls `save_auth()` which calls `_atomic_write()` which tries to acquire LOCK_EX again — blocks forever.
**Why it happens:** POSIX flock locks the open-file-description; a second acquire from the same process on a different fd to the same file blocks (documented in Phase 14 D-13 notes in STATE.md).
**How to avoid:** Inside the flock window, call `_atomic_write_unlocked()` directly — never `_atomic_write()` or `save_auth()`. This is exactly how `state_manager.mutate_state` calls `_save_state_unlocked`.
**Warning signs:** Test hangs indefinitely instead of failing.

### Pitfall 2: TestForbiddenImports path after split
**What goes wrong:** `AUTH_STORE_PATH = Path('auth_store.py')` at line 27 of `tests/test_auth_store.py` points to the old flat file. After the split the file no longer exists.
**Why it happens:** AST guard reads a single file path; packages need directory walking.
**How to avoid:** Update `TestForbiddenImports` to walk all `*.py` files in `auth_store/` package directory instead of reading a single file. Pattern: `for f in Path('auth_store').glob('*.py'): ast.parse(f.read_text())`.
**Warning signs:** `test_auth_store_does_not_import_web_or_signal_layers` raises FileNotFoundError or passes vacuously (walks zero files).

### Pitfall 3: _schema.py LOC vs merged approach
**What goes wrong:** `_schema.py` is created as a separate file but only has ~40 LOC of TypedDicts. Adds a module for marginal gain; planner spends time wiring cross-imports.
**Why it happens:** D-10 lists it but Claude's Discretion allows merging into `_io.py`.
**How to avoid:** If `_io.py` stays under 500 LOC with TypedDicts merged (likely — original auth_store.py had io + schema at ~160 LOC combined), merge them. Only create `_schema.py` if `_io.py` would exceed 450 LOC (buffer for migration code).
**Warning signs:** `_io.py` approaching 500 LOC after merge.

### Pitfall 4: load_auth migration calls save_auth which calls load_auth
**What goes wrong:** v1→v2 migration in `load_auth()` calls `save_auth()`, which does nothing problematic — but if any future code adds a `load_auth()` call inside `save_auth()`, it creates recursion.
**Why it happens:** Migration-on-first-read pattern is inherently coupled.
**How to avoid:** Keep `save_auth()` as a pure write (no reads). Migration runs once in `load_auth()` only. This is the existing pattern (no circular risk in the current design).

### Pitfall 5: tests/test_auth_store.py already exceeds 500 LOC
**What goes wrong:** D-12 says "only split if grows past 500 LOC after Phase 34 tests are added" — but the file is already at 620 LOC before Phase 34 tests.
**Why it happens:** D-12 was written assuming the file was under 500 LOC.
**How to avoid:** Planner should acknowledge D-12 is already triggered. Options: (a) declare the file acceptable at its current size and continue adding Phase 34 tests inline, or (b) split as part of this phase into `test_auth_store_io.py` + `test_auth_store_users.py`. Claude's Discretion applies — D-12 is already technically violated.
**Warning signs:** File grows to ~750+ LOC, making grep/review hard.

### Pitfall 6: isolated_auth_json fixture monkeypatches auth_store module attribute
**What goes wrong:** After split, `conftest.py` does `import auth_store; monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', tmp_auth)`. After the split, `DEFAULT_AUTH_PATH` lives in `auth_store._io`, not the package `__init__`. Tests that depend on the monkeypatch will silently use the wrong path.
**Why it happens:** `monkeypatch.setattr` on a name resolves to the object where the name lives at runtime. If `auth_store/__init__.py` does `from auth_store._io import DEFAULT_AUTH_PATH`, the package namespace gets a COPY, but `_io.DEFAULT_AUTH_PATH` is the one `_resolve_path()` reads.
**How to avoid:** Two safe approaches:
  - (A) Keep `DEFAULT_AUTH_PATH` in `__init__.py` (not `_io.py`) and import it into `_io.py` — monkeypatch of `auth_store.DEFAULT_AUTH_PATH` then works.
  - (B) Each daughter module imports via `import auth_store._io as _io_mod` and reads `_io_mod.DEFAULT_AUTH_PATH` — then monkeypatch `auth_store._io.DEFAULT_AUTH_PATH`.
  - **Recommended:** Option A — `DEFAULT_AUTH_PATH` stays in `auth_store/__init__.py` since it's the public-facing config point. `_resolve_path()` in `_io.py` does `from auth_store import DEFAULT_AUTH_PATH` (or receives it as arg). This preserves all existing `monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', ...)` calls unchanged.
**Warning signs:** Tests pass in isolation but write to real `auth.json`.

## Code Examples

### flock-guarded consume + create (complete skeleton)

```python
# Source: mirrors state_manager/io.py::_atomic_write + mutate_state pattern [VERIFIED: codebase]
import fcntl, json, os
import hashlib, hmac
from datetime import datetime, timezone

def consume_and_create_user(unhashed_token, new_user_fields, path=None):
  '''Single LOCK_EX window: validate invite + mark consumed + append user + atomic write.
  Returns User dict on success. Raises ValueError on bad/expired/consumed token.
  '''
  from auth_store._io import _resolve_path, _atomic_write_unlocked, _load_raw
  resolved = _resolve_path(path)
  lock_fd = os.open(str(resolved), os.O_RDWR | os.O_CREAT, 0o600)
  try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
      data = _load_raw(resolved)   # no flock inside
      # find matching invite
      computed = 'sha256:' + hashlib.sha256(unhashed_token.encode()).hexdigest()
      invite = None
      for row in data.get('pending_invites', []):
        if hmac.compare_digest(row['token_hash'], computed):
          invite = row
          break
      if invite is None or invite['consumed']:
        raise ValueError('invalid or already consumed invite token')
      now = datetime.now(timezone.utc)
      expires = datetime.fromisoformat(invite['expires_at'])
      if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
      if expires < now:
        raise ValueError('invite token expired')
      # atomically consume + create
      invite['consumed'] = True
      invite['consumed_at'] = now.isoformat()
      import uuid as _uuid
      uid = _uuid.uuid4().hex
      user = {
        'uid': uid,
        'email': new_user_fields['email'],
        'role': new_user_fields.get('role', 'ff'),
        'created_at': now.isoformat(),
        'disabled': False,
      }
      data.setdefault('users', []).append(user)
      payload = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
      _atomic_write_unlocked(payload, resolved)
      return user
    finally:
      fcntl.flock(lock_fd, fcntl.LOCK_UN)
  finally:
    os.close(lock_fd)
```

### mint_invite_token

```python
# Source: [VERIFIED: stdlib secrets, hashlib]
import secrets, hashlib
from datetime import datetime, timedelta, timezone

def mint_invite_token(invited_by_uid, email, path=None):
  raw = secrets.token_urlsafe(32)
  token_hash = 'sha256:' + hashlib.sha256(raw.encode()).hexdigest()
  now = datetime.now(timezone.utc)
  expires = now + timedelta(days=7)
  # ... load → append PendingInvite → save ...
  return raw, expires.isoformat()
```

### TestForbiddenImports update for package

```python
# Source: Phase 30/31 pattern — walk package directory [VERIFIED: codebase precedent]
AUTH_STORE_PACKAGE = Path('auth_store')

class TestForbiddenImports:
  def test_auth_store_does_not_import_web_or_signal_layers(self):
    violations = []
    for py_file in AUTH_STORE_PACKAGE.glob('*.py'):
      src = py_file.read_text()
      tree = ast.parse(src)
      for node in ast.walk(tree):
        # ... same violation check ...
        if root in self.FORBIDDEN_ROOTS:
          violations.append(f'{py_file}:{node.lineno}: ...')
    assert violations == []
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Bare hexdigest for token hash | Prefix-tagged `"sha256:<hex>"` | Phase 34 decision | Algorithm explicit in stored value |
| Single flat auth_store.py | auth_store/ package | Phase 34 | Files stay under 500 LOC cap; logical grouping |
| Schema v1 (no users/invites) | Schema v2 (users[], pending_invites[]) | Phase 34 | Auto-migrated on first load |

**Deprecated/outdated:**
- `auth_store.py` (flat file): replaced by `auth_store/` package — delete after split verified green.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `_schema.py` vs merged TypedDicts — merging into `_io.py` is safe if it stays under 500 LOC | Architecture Patterns | If _io.py exceeds 500, must create _schema.py anyway |
| A2 | `consume_and_create_user()` returns `User` dict (Claude's Discretion) | Code Examples | Callers in Phase 35 may expect `(True, uid)` tuple instead — no routes land this phase so no callers yet |
| A3 | `mint_invite_token()` returns `(raw_token, expires_at_iso)` tuple | Code Examples | Caller (Phase 37 route) computes expiry differently — deferred, safe |

## Open Questions

1. **test_auth_store.py already at 620 LOC — split or tolerate?**
   - What we know: D-12 says split only if > 500 after Phase 34 additions; file is already > 500.
   - What's unclear: Did the discuss session intend "only split if the delta pushes it over 500" or "the file is already over the cap"?
   - Recommendation: Planner should resolve as Claude's Discretion — splitting now into `test_auth_store_io.py` + `test_auth_store_users.py` is low-risk and cleaner.

2. **DEFAULT_AUTH_PATH monkeypatch ownership after split**
   - What we know: All existing tests do `monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', tmp)`. After split, the name lives in `auth_store/_io.py`.
   - What's unclear: Which module should own it to preserve test compatibility.
   - Recommendation: Keep `DEFAULT_AUTH_PATH` in `auth_store/__init__.py` and import it into `_io.py`. This is the lowest-risk path — zero test changes needed.

## Environment Availability

Step 2.6: SKIPPED — phase is purely stdlib code changes with no new external dependencies.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing, in .venv) |
| Config file | pyproject.toml [VERIFIED: codebase] |
| Quick run command | `.venv/bin/pytest tests/test_auth_store.py -x --tb=short -q` |
| Full suite command | `.venv/bin/pytest -x --tb=short -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RBAC-03 | mint_invite_token: raw token + sha256 hash stored | unit | `pytest tests/test_auth_store.py::TestUserRegistry -x` | ❌ Wave 0 |
| RBAC-03 | consume_and_create_user: single-use under flock | unit | `pytest tests/test_auth_store.py::TestInviteConsume -x` | ❌ Wave 0 |
| RBAC-03 | hmac.compare_digest timing-safe verify | unit | included in TestInviteConsume | ❌ Wave 0 |
| RBAC-03 | 7-day expiry enforced | unit | included in TestInviteConsume | ❌ Wave 0 |
| RBAC-04 | set_user_disabled flips disabled=True | unit | `pytest tests/test_auth_store.py::TestUserRegistry -x` | ❌ Wave 0 |
| RBAC-04 | disabled user record preserved (not deleted) | unit | included in TestUserRegistry | ❌ Wave 0 |
| D-09 | v1→v2 migration backfills users=[], pending_invites=[] | unit | `pytest tests/test_auth_store.py::TestSchemaV2Migration -x` | ❌ Wave 0 |
| D-07 | load_auth() on v2 file with users=[] does NOT auto-insert admin | unit | included in TestSchemaV2Migration | ❌ Wave 0 |
| D-11 | import surface unchanged after package split | unit | `pytest tests/test_auth_store.py::TestForbiddenImports -x` + existing caller imports | ✅ (update needed) |

### Sampling Rate

- **Per task commit:** `.venv/bin/pytest tests/test_auth_store.py -x --tb=short -q`
- **Per wave merge:** `.venv/bin/pytest -x --tb=short -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_auth_store.py::TestSchemaV2Migration` — covers D-09 migration, D-07 no-auto-bootstrap
- [ ] `tests/test_auth_store.py::TestUserRegistry` — covers create_user, get_user, list_users, set_user_disabled (RBAC-04)
- [ ] `tests/test_auth_store.py::TestInviteConsume` — covers mint_invite_token, consume_and_create_user, expiry, single-use, hmac compare (RBAC-03)
- [ ] `tests/test_auth_store.py::TestForbiddenImports` — update to walk `auth_store/` package instead of `auth_store.py` file

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Invite tokens gated by hmac.compare_digest + expiry check |
| V3 Session Management | no | No sessions in storage layer |
| V4 Access Control | yes | disabled flag on User row; consume_and_create_user enforces single-use |
| V5 Input Validation | yes | email field validated by callers (Phase 37 route); storage layer stores as-is |
| V6 Cryptography | yes | secrets.token_urlsafe + sha256 — never hand-rolled |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Token replay (invite used twice) | Elevation of Privilege | consumed=True flip under LOCK_EX; hmac.compare_digest |
| Timing oracle on token compare | Information Disclosure | hmac.compare_digest (constant-time) |
| Invite token in auth.json leak | Information Disclosure | Only sha256 hash stored; raw token never persisted |
| Expired invite used | Elevation of Privilege | expires_at check inside flock window |
| Disabled user logs in | Elevation of Privilege | disabled flag on User (Phase 35 enforces at login layer) |

## Project Constraints (from CLAUDE.md)

- 2-space indent throughout; `ruff format` FORBIDDEN.
- stdlib-only in auth_store/ — forbidden imports: web/, signal_engine, sizing_engine, notifier, dashboard, main.
- `mutate_state()` is NOT used — auth_store uses its own load/save pattern.
- Files ≤500 LOC cap.
- ALWAYS run tests after code changes.
- ALWAYS read a file before editing it.
- NEVER commit secrets, credentials, or .env files.

## Sources

### Primary (HIGH confidence)

- `auth_store.py` (codebase) — full 520-LOC monolith read; all existing patterns verified directly
- `state_manager/io.py` (codebase) — `_atomic_write`, `_atomic_write_unlocked`, LOCK_EX pattern
- `tests/test_auth_store.py` (codebase) — 620-LOC test file; `TestForbiddenImports` AST guard at line 587
- `tests/conftest.py` (codebase) — `isolated_auth_json` fixture; monkeypatch pattern
- Python stdlib docs — secrets, hmac, hashlib, fcntl, uuid (all verified available in Python 3.13 env)

### Secondary (MEDIUM confidence)

- Phase 30 CONTEXT.md (codebase) — package-split D-01..D-09 precedent
- Phase 31 CONTEXT.md (codebase) — `__init__.py` re-export conventions, `_models.py` placement

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all stdlib, all verified present
- Architecture: HIGH — directly cloned from state_manager/io.py and Phase 30/31 precedent
- Pitfalls: HIGH — flock deadlock and monkeypatch scope issues are documented failures from Phase 14 and are directly applicable

**Research date:** 2026-05-13
**Valid until:** 2026-06-13 (stable stdlib patterns; 30-day horizon)
