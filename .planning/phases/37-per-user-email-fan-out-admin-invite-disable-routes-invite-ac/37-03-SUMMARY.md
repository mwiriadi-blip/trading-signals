---
phase: 37
plan: "03"
subsystem: auth-store-primitives
tags: [wave-1, bcrypt, password-hashing, invite-management, rbac, auth-store]
dependency_graph:
  requires:
    - 37-01 (Wave 0 test scaffolding + pending_invite_auth_json fixture)
  provides:
    - auth_store.hash_password (bcrypt 5.0.0, 72-byte cap per review #9)
    - auth_store.verify_password (fail-closed, timing-safe)
    - auth_store.User.password_hash field (optional, None for legacy admin)
    - auth_store._peek_invite_token (validate without consuming)
    - auth_store.list_pending_invites
    - auth_store.revoke_invite (with flock-safety docstring per review #12)
    - auth_store.consume_and_create_user.password_hash kwarg (D-06)
  affects:
    - auth_store/_schema.py (User TypedDict extended)
    - auth_store/_users.py (5 new public functions)
    - auth_store/__init__.py (re-exports updated)
    - requirements.txt (bcrypt==5.0.0 pinned)
tech_stack:
  added:
    - bcrypt==5.0.0 (OWASP minimum rounds=12; 72-byte cap enforced at boundary)
  patterns:
    - hash_password raises ValueError on >72 UTF-8 bytes (review consensus #9)
    - verify_password fail-closed via bare except returning False (BLE001)
    - _peek_invite_token walks full list before deciding (timing-safe T-37-03-03)
    - revoke_invite no-flock + idempotent design documented inline (review #12)
    - consume_and_create_user password_hash kwarg (None = backward compat)
key_files:
  created: []
  modified:
    - requirements.txt (+1 line: bcrypt==5.0.0)
    - auth_store/_schema.py (User TypedDict +1 field: password_hash: str | None)
    - auth_store/_users.py (+5 public functions, +1 kwarg to consume_and_create_user)
    - auth_store/__init__.py (re-export list updated)
    - tests/test_auth_store_users.py (+4 test classes, +33 test methods)
decisions:
  - "72-byte cap enforced in hash_password by raising ValueError (not relying on bcrypt silent truncation) — review consensus #9"
  - "revoke_invite deliberately no-flock: idempotent + OS-atomic os.replace makes concurrent revoke safe per review #12 + Phase 34 D-01"
  - "_peek_invite_token is a private helper (underscore prefix) but re-exported for Plan 04 invite wizard use"
metrics:
  duration: "~12 minutes"
  completed: "2026-05-14T06:05:00Z"
  tasks: 2
  files_modified: 5
---

# Phase 37 Plan 03: auth_store Primitives — bcrypt + Invite Helpers Summary

**One-liner:** bcrypt 5.0.0 installed with 72-byte cap; User.password_hash field; hash_password + verify_password + _peek_invite_token + list_pending_invites + revoke_invite with full flock-safety rationale documented.

---

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 (RED) | Failing tests for password hashing + schema | `62904e3` | tests/test_auth_store_users.py |
| 1 (GREEN) | hash_password + verify_password + User.password_hash | `0836af9` | auth_store/_schema.py, auth_store/_users.py, auth_store/__init__.py |
| 2 (RED) | Failing tests for consume + peek + list + revoke | `3ea2ff3` | tests/test_auth_store_users.py |
| 2 (GREEN) | Extend consume_and_create_user + add 3 invite helpers | `57f6f07` | auth_store/_users.py, auth_store/__init__.py, tests/test_auth_store_users.py |

---

## bcrypt 5.0.0 Install + Version Pin

- `requirements.txt`: `bcrypt==5.0.0` pinned alphabetically after PyYAML
- Installed via `.venv/bin/pip install bcrypt==5.0.0`
- `bcrypt.__version__` verified: `5.0.0`

---

## User TypedDict Diff

```python
# Before (Phase 34):
class User(TypedDict):
  uid: str
  email: str
  role: str
  created_at: str
  disabled: bool

# After (Phase 37 D-06):
class User(TypedDict):
  uid: str
  email: str
  role: str
  created_at: str
  disabled: bool
  password_hash: str | None  # Phase 37 D-06: optional; None for legacy admin row
```

Backward compat: all reads use `.get('password_hash')` — no KeyError on legacy admin row.

---

## 5 New Public Functions in auth_store

| Function | Module | Signature | Notes |
|----------|--------|-----------|-------|
| `hash_password` | `_users.py` | `(plaintext: str) -> str` | 72-byte cap (review #9); bcrypt rounds=12 |
| `verify_password` | `_users.py` | `(plaintext: str, stored_hash: str | None) -> bool` | Fail-closed on any Exception |
| `_peek_invite_token` | `_users.py` | `(unhashed_token: str, path=None) -> str` | Returns email; raises InviteAlreadyConsumed/InviteExpired |
| `list_pending_invites` | `_users.py` | `(path=None) -> list` | Returns all rows (consumed + active) |
| `revoke_invite` | `_users.py` | `(token_hash: str, path=None) -> bool` | No flock; idempotent; returns False if not found |

Plus: `consume_and_create_user` extended with `password_hash: str | None = None` kwarg.

---

## 72-Byte Cap Enforced in hash_password (review #9)

```python
encoded = plaintext.encode('utf-8')
if len(encoded) > 72:
    raise ValueError(
      f'password byte length {len(encoded)} exceeds 72 (bcrypt limit); shorten the password'
    )
```

Key behaviors verified:
- `hash_password('a' * 72)` succeeds
- `hash_password('a' * 73)` raises `ValueError: ... exceeds 72 ...`
- `hash_password('🦀' * 19)` raises (76 UTF-8 bytes from 4-byte emoji × 19)
- bcrypt does NOT silently truncate — cap is at bytes, not characters

---

## revoke_invite Flock-Safety Rationale (review #12)

Docstring in `auth_store/_users.py::revoke_invite` contains explicit flock rationale per review consensus #12:

1. **Idempotent** — revoking an already-consumed row returns False; no side effects
2. **Single-field overwrite** — `consumed=True` + `consumed_at=<iso>` converge under any concurrent revoke interleaving
3. **Atomic at OS level** — `save_auth` uses `os.replace` (inode-atomic); lost-update from concurrent unflocked writes produces the same final `consumed=True` state
4. **Security boundary preserved** — `consume_and_create_user` still uses LOCK_EX for the critical token→user transition

Acceptance criterion: `'does not acquire flock' in inspect.getdoc(revoke_invite).lower()` — passes.

---

## Test Classes Added

| Class | Methods | Coverage |
|-------|---------|----------|
| `TestPasswordHashing` | 9 | hash_password + verify_password behaviors 1-8 |
| `TestUserSchemaPasswordHashField` | 3 | User TypedDict annotation + legacy admin row compat |
| `TestPasswordHash72ByteCap` | 4 | Review #9: 72-byte enforcement (ASCII + emoji) |
| `TestPasswordHashOnConsume` | 3 | consume_and_create_user password_hash kwarg |
| `TestPeekInviteToken` | 8 | _peek_invite_token peek/consumed/expired/unknown/timing |
| `TestListPendingInvites` | 2 | list_pending_invites returns all rows |
| `TestRevokeInvite` | 4 | revoke_invite success/unknown/idempotent + review #12 docstring |
| **Total new** | **33** | |

Full test file: 87 tests total in test_auth_store_users.py (all pass).

---

## Admin Login Path Unaffected

Existing admin row (no `password_hash` key) round-trips via `load_auth` → `save_auth` without error. `.get('password_hash')` returns `None` for the legacy admin row. Verified by `TestUserSchemaPasswordHashField` + full test suite (2273 passed, 0 failures).

---

## Pointer to Plans 04 and 05

| Consumer | Plan | Usage |
|----------|------|-------|
| `GET /accept-invite` | Plan 04 | calls `_peek_invite_token` to validate without consuming |
| `POST /accept-invite` | Plan 04 | calls `hash_password` then `consume_and_create_user(password_hash=...)` |
| `DELETE /admin/invites/{hash}` | Plan 05 | calls `revoke_invite(token_hash)` |
| `GET /admin/invites` (HTML) | Plan 05 | calls `list_pending_invites()` |

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] docstring string wrap caused test failure**
- **Found during:** Task 2 GREEN phase
- **Issue:** `revoke_invite` docstring had line break mid-phrase: "does NOT acquire\nflock" — test's `doc.lower()` check for `'does not acquire flock'` (space) failed because newline != space
- **Fix:** Moved the phrase onto one line in the docstring; test assertion already uses `.lower()` correctly
- **Files modified:** `auth_store/_users.py`, `tests/test_auth_store_users.py`
- **Commit:** `57f6f07`

None beyond the above.

---

## Known Stubs

None. All functions are fully implemented. No placeholder data or TODO markers in production code.

---

## Threat Surface Scan

No new network endpoints or auth paths introduced. Only auth_store internal helpers added. Threat mitigations from plan register:

| Threat ID | Status |
|-----------|--------|
| T-37-03-01 | Mitigated — `_verify_token` uses `hmac.compare_digest`; `_peek_invite_token` walks full list |
| T-37-03-02 | Mitigated — no log/print of `$2b$12$` hash in hash_password or verify_password |
| T-37-03-03 | Mitigated — `_peek_invite_token` timing-safe walk (T-37-03-03) |
| T-37-03-04 | Mitigated — Phase 34 sha256: prefix enforcement still in place |
| T-37-03-05 | Mitigated — `user.get('password_hash')` pattern; TestUserSchemaPasswordHashField |
| T-37-03-06 | Accepted — `consumed_at` ISO timestamp is the audit trail |
| T-37-03-07 | Accepted — bcrypt cost=12 per OWASP; F&F login infrequent |
| T-37-03-08 | Mitigated — no log statements in hash_password or verify_password |
| T-37-03-09 | Mitigated — `hash_password` raises ValueError on >72 bytes; TestPasswordHash72ByteCap |
| T-37-03-10 | Accepted — documented in revoke_invite docstring; idempotent race-safe |

---

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| requirements.txt has bcrypt==5.0.0 | FOUND |
| bcrypt.__version__ == 5.0.0 | PASS |
| auth_store/_schema.py has password_hash annotation | FOUND |
| auth_store/_users.py has exceeds 72 | FOUND |
| auth_store/_users.py has _peek_invite_token | FOUND |
| auth_store/_users.py has list_pending_invites | FOUND |
| auth_store/_users.py has revoke_invite | FOUND |
| revoke_invite docstring has flock rationale | PASS |
| consume_and_create_user has password_hash param | PASS |
| All 33 new tests GREEN | PASS |
| Full suite 2273 passed, 0 failed | PASS |
| Commit 62904e3 exists | FOUND |
| Commit 0836af9 exists | FOUND |
| Commit 3ea2ff3 exists | FOUND |
| Commit 57f6f07 exists | FOUND |
