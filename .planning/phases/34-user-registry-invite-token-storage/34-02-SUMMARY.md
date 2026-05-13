---
phase: "34"
plan: "02"
subsystem: auth_store
tags: [user-registry, invite-tokens, flock, hmac, concurrency, rbac]
dependency_graph:
  requires: [34-01]
  provides: [auth_store._users, InviteAlreadyConsumed, InviteExpired, create_user, mint_invite_token, consume_and_create_user]
  affects: [Phase 35 login enforcement, Phase 37 invite routes]
tech_stack:
  added: []
  patterns: [fcntl-LOCK_EX-flock-window, hmac-compare_digest-timing-safe, sha256-prefix-tagged-hash, threading-Barrier-concurrency-test]
key_files:
  created:
    - auth_store/_users.py
    - tests/test_auth_store_users.py
  modified:
    - auth_store/__init__.py
    - tests/test_secret_redaction.py
decisions:
  - "_read_auth_unlocked renamed from _load_raw (OpenCode/Codex review consensus) to match _atomic_write_unlocked convention"
  - "_normalize_v2 called inside LOCK_EX window before scanning pending_invites (Codex HIGH fix)"
  - "schema_version >= 2 assertion inside flock window as migration-bypass tripwire (OpenCode suggestion)"
  - "_verify_token fails closed on all malformed hashes — missing prefix, invalid hex, wrong algorithm"
  - "_validate_user_fields rejects caller-supplied uid, empty email, invalid role at storage boundary (Codex MEDIUM)"
  - "_verify_token and _read_auth_unlocked are module-private; NOT re-exported from auth_store.__init__"
  - "consume_and_create_user docstring documents flock-on-inode vs os.replace semantics"
metrics:
  duration: "~15min"
  completed: "2026-05-13"
  tasks: 2
  files: 4
requirements: [RBAC-03, RBAC-04]
---

# Phase 34 Plan 02: auth_store/_users.py — User Registry + Invite Token Storage Summary

JWT-free invite token flow: sha256-prefix-tagged hash storage, LOCK_EX single-use consume guarantee, typed InviteAlreadyConsumed/InviteExpired exceptions, RBAC-04 soft-disable, 24 tests (5 classes) including real threading.Barrier concurrency test.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement auth_store/_users.py + wire into __init__.py | fe0bdfc | auth_store/_users.py, auth_store/__init__.py |
| 2 | Write tests/test_auth_store_users.py (5 classes, real concurrency) | e788ad8 | tests/test_auth_store_users.py, tests/test_secret_redaction.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] test_secret_redaction.py referenced deleted auth_store.py**
- **Found during:** Task 2 full-suite run
- **Issue:** `TestSecretRedactionGrepGate.COVERED_FILES` listed `'auth_store.py'` (flat file deleted in Plan 01 Task 2). Running the full suite after adding the new test file revealed this pre-existing breakage: `FileNotFoundError: auth_store.py`.
- **Fix:** `tests/test_secret_redaction.py` — replaced `'auth_store.py'` literal with `[str(p) for p in Path('auth_store').glob('*.py')]` to scan the package directory.
- **Files modified:** `tests/test_secret_redaction.py`
- **Commit:** e788ad8

## Threat Surface Scan

T-34-02-01 through T-34-02-12 all mitigated as designed:

- **T-34-02-01 (token replay):** consumed=True flip inside LOCK_EX; TestInviteConsumeConcurrency.test_two_threads_consuming_same_token_only_one_succeeds verifies under real contention.
- **T-34-02-02 (timing oracle):** hmac.compare_digest used throughout _verify_token.
- **T-34-02-03 (raw token persisted):** Only sha256 hash stored; test_raw_token_verifies_against_stored_hash_and_is_not_persisted uses programmatic regex (not shell grep).
- **T-34-02-04 (expired invite):** expires_at checked inside lock before marking consumed; raises InviteExpired (distinct type per SC-4).
- **T-34-02-06 (flock deadlock):** consume uses _atomic_write_unlocked + _read_auth_unlocked only; save_auth never called inside lock.
- **T-34-02-07 (malformed hash):** _verify_token returns False on missing prefix, invalid hex, wrong algorithm; TestMalformedHash covers all 3.
- **T-34-02-08 (pre-v2 file):** _normalize_v2 called inside lock; schema_version >= 2 assertion as tripwire.
- **T-34-02-10/11 (caller uid / invalid role):** _validate_user_fields rejects both.
- **T-34-02-12 (_verify_token re-exported):** `assert not hasattr(auth_store, '_verify_token')` in AC verification.

## Self-Check: PASSED

- [x] auth_store/_users.py exists: FOUND
- [x] tests/test_auth_store_users.py exists: FOUND
- [x] Task 1 commit fe0bdfc: FOUND
- [x] Task 2 commit e788ad8: FOUND
- [x] 2151 tests green: CONFIRMED
- [x] auth_store/_users.py under 250 LOC (246): CONFIRMED
- [x] tests/test_auth_store_users.py under 350 LOC (297): CONFIRMED
- [x] InviteAlreadyConsumed, InviteExpired importable from auth_store: CONFIRMED
- [x] _verify_token, _read_auth_unlocked NOT in auth_store namespace: CONFIRMED
