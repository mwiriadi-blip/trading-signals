---
phase: 34-user-registry-invite-token-storage
reviewed: 2026-05-13T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - auth_store/__init__.py
  - auth_store/_devices.py
  - auth_store/_io.py
  - auth_store/_magic_links.py
  - auth_store/_schema.py
  - auth_store/_users.py
  - tests/test_auth_store.py
  - tests/test_auth_store_users.py
  - tests/test_secret_redaction.py
findings:
  critical: 2
  warning: 4
  info: 3
  total: 9
status: issues_found
---

# Phase 34: Code Review Report

**Reviewed:** 2026-05-13T00:00:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the auth_store package split (Phase 34 Plan 01) and user registry + invite token storage (Plan 02). The flock-on-inode design for `consume_and_create_user` is sound, `_verify_token` correctly uses `hmac.compare_digest`, and the `sha256:` prefix validation fails-closed. The main correctness gap is unguarded timezone-naive datetime comparison inside the flock window. A secondary security issue is that `consume_magic_link` uses `!=` (timing-sensitive) for token hash comparison instead of `hmac.compare_digest`. Four warnings cover a misleading docstring, a bare `json.loads` that raises an unexpected exception type inside the lock, an `assert` in production code that is stripped by `-O`, and duplicate `import logging` inside function bodies.

---

## Critical Issues

### CR-01: Naive datetime comparison crashes inside flock window in `consume_and_create_user`

**File:** `auth_store/_users.py:224`
**Issue:** `datetime.fromisoformat(matched_row['expires_at'])` does not call `_ensure_aware`. If `expires_at` is a naive ISO string (e.g. hand-edited auth.json, or a future code path that writes without UTC), line 225 raises `TypeError: can't compare offset-naive and offset-aware datetimes`. The exception propagates through the flock `finally` (lock is released correctly), but the caller receives `TypeError` instead of `InviteExpired`. The `_magic_links.consume_magic_link` already uses `_ensure_aware` for this same pattern; `_users` does not.

**Fix:**
```python
from auth_store._schema import _ensure_aware

# line 224-226 in consume_and_create_user:
try:
  expires_dt = _ensure_aware(datetime.fromisoformat(matched_row['expires_at']))
except (TypeError, ValueError):
  raise InviteExpired('invite token has unparseable expiry')
if datetime.now(timezone.utc) > expires_dt:
  raise InviteExpired('invite token expired')
```

---

### CR-02: `consume_magic_link` uses `!=` (non-constant-time) for token hash comparison

**File:** `auth_store/_magic_links.py:81`
**Issue:** `if row['token_hash'] != token_hash:` compares two SHA-256 hex strings with Python's built-in `!=`. For stored hashes of unexpired unconsumed tokens this is a timing side-channel: an attacker who can measure response latency across many requests can distinguish "first byte mismatch" from "all bytes match". The invite path uses `hmac.compare_digest` via `_verify_token`; the magic-link path does not. The risk is low in practice (auth.json is file-backed, one user, not an HMAC oracle), but the inconsistency is a security regression relative to the invite path in the same package.

**Fix:**
```python
import hmac

# replace line 81:
if not hmac.compare_digest(row['token_hash'], token_hash):
  continue
# then remove the `if row['token_hash'] != token_hash: continue` pattern
# (invert: only proceed when digests match)
```

Restructured loop body:
```python
for row in data['pending_magic_links']:
  if not hmac.compare_digest(row['token_hash'], token_hash):
    continue
  if row['consumed']:
    return (False, None)
  ...
```

---

## Warnings

### WR-01: `_read_auth_unlocked` raises `json.JSONDecodeError` (not a clean auth error) inside flock window

**File:** `auth_store/_users.py:62`
**Issue:** `return json.loads(text)` at line 62 has no exception handler for `json.JSONDecodeError` or `UnicodeDecodeError`. If auth.json is corrupt at the moment `consume_and_create_user` holds LOCK_EX, the raw JSON exception propagates to the caller unhandled — it is not wrapped in `InviteAlreadyConsumed` or any auth-specific type. This makes the caller's exception handling more complex and exposes internal implementation details. The `load_auth` path in `_io.py` already handles this correctly (lines 157-161).

**Fix:**
```python
def _read_auth_unlocked(resolved: Path) -> dict:
  try:
    text = resolved.read_text(encoding='utf-8')
  except FileNotFoundError:
    return _default_auth_data()
  if not text.strip():
    return _default_auth_data()
  try:
    return json.loads(text)
  except (json.JSONDecodeError, UnicodeDecodeError):
    logger.warning('[Auth] corrupt auth.json at %s; using defaults inside lock', resolved)
    return _default_auth_data()
```

---

### WR-02: `load_auth` docstring says `save_auth() acquires LOCK_EX` — factually incorrect

**File:** `auth_store/_io.py:149`
**Issue:** The docstring warns: *"cannot safely be called inside a LOCK_EX window — save_auth() acquires LOCK_EX, which will deadlock against an already-held lock."* `save_auth` does NOT acquire any flock — it calls `_atomic_write` → `_atomic_write_unlocked`, neither of which uses `fcntl.flock`. The actual concern is a race condition: `load_auth` might call `save_auth` (v1 migration) while a separate flock holder in `consume_and_create_user` is mid-write, producing a lost-update window. The misleading deadlock claim will cause future maintainers to reason incorrectly about the locking model.

**Fix:**
```python
  '''Load auth.json from disk and return AuthData. Migrates v1 -> v2 on first read.

  WARNING: This function performs disk I/O via save_auth() during v1->v2 migration
  and must NOT be called inside a LOCK_EX window. save_auth() issues an atomic
  os.replace WITHOUT acquiring a lock; calling it while a flock holder holds LOCK_EX
  creates a lost-update race (the unlocked write will overwrite the locked write's
  inode). Callers inside a flock window must use _read_auth_unlocked + _normalize_v2
  directly (see auth_store._users.consume_and_create_user).
  '''
```

---

### WR-03: `assert` in production code inside flock window stripped by `-O`

**File:** `auth_store/_users.py:212`
**Issue:** `assert data.get('schema_version', 0) >= 2, 'migration must precede invite flow'` is inside the LOCK_EX window. Python's `-O` (optimize) flag strips all `assert` statements, so this guard is silently absent in optimized builds. If the migration somehow fails and `schema_version < 2`, `data['pending_invites']` would be absent (KeyError) or silently empty, causing `InviteAlreadyConsumed` on a valid token. Use an explicit `if` guard instead.

**Fix:**
```python
# replace line 212:
if data.get('schema_version', 0) < 2:
  raise RuntimeError(
    f'[Auth] expected schema_version>=2 before invite flow; got {data.get("schema_version")!r}'
  )
```

---

### WR-04: Magic number `days=7` for invite expiry violates single-source-of-truth convention

**File:** `auth_store/_users.py:163`
**Issue:** `expires = now + timedelta(days=7)` hard-codes the invite TTL as a magic number inside the function body. Per CLAUDE.md: `system_params.py` is the single source of truth for all constants. If the invite TTL needs to change (e.g. enterprise requires 30 days), the constant must be hunted down inside `_users.py`. The purge retention in `_magic_links.purge_expired_magic_links` (`retention_seconds=604800`) also uses a magic number but has a default parameter, so it is less exposed.

**Fix:** Define the constant in `system_params.py`:
```python
# system_params.py
INVITE_TOKEN_TTL_DAYS: int = 7
```
Then in `_users.py`:
```python
from system_params import INVITE_TOKEN_TTL_DAYS
expires = now + timedelta(days=INVITE_TOKEN_TTL_DAYS)
```

---

## Info

### IN-01: `import logging` inside function bodies in `__init__.py`

**File:** `auth_store/__init__.py:83,94`
**Issue:** `set_totp_secret` and `mark_enrolled` each contain `import logging` inside the function body. `logging` is a stdlib module — there is no circular-import risk. All other modules in the package import `logging` at module level. This inconsistency adds per-call overhead (import cache lookup on every call) and breaks the established pattern.

**Fix:** Move `import logging` and `logger = logging.getLogger(__name__)` to module top level in `__init__.py`, mirroring `_io.py`, `_devices.py`, etc.

---

### IN-02: Inconsistent token hash storage format between magic-links and invites

**File:** `auth_store/_magic_links.py` vs `auth_store/_users.py`
**Issue:** Invite tokens store hashes as `sha256:<hex>` (prefixed). Magic link hashes are stored as bare hex (caller-supplied, no prefix enforced). The `_verify_token` helper in `_users.py` explicitly validates the `sha256:` prefix and fails-closed if absent. `consume_magic_link` has no such validation — it accepts any string as a stored hash. The inconsistency will confuse future maintainers and could admit a hash-algorithm confusion attack if the magic-link storage format is ever extended.

**Fix:** Align `add_magic_link` to enforce `sha256:` prefix and update `consume_magic_link` to validate the prefix, mirroring the invite token pattern. Or document explicitly why magic links intentionally differ.

---

### IN-03: `test_auth_store_users.py` imports `auth_store._io.save_auth` directly to set up expired invite test

**File:** `tests/test_auth_store_users.py:169`
**Issue:** `import auth_store._io as _io; _io.save_auth(data)` bypasses the public `auth_store.save_auth` surface. If `_io` is renamed or refactored, this test breaks with an `ImportError` rather than a useful assertion failure. The test uses the monkeypatched `DEFAULT_AUTH_PATH` via `isolated_auth_json`, but `_io.save_auth` re-resolves via `_resolve_path` which reads from `auth_store.DEFAULT_AUTH_PATH` — so it happens to work. The direct sub-module import is fragile.

**Fix:** Replace `import auth_store._io as _io; _io.save_auth(data)` with `auth_store.save_auth(data)` (already in scope via top-level import).

---

_Reviewed: 2026-05-13T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
