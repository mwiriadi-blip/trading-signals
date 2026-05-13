---
phase: 34-user-registry-invite-token-storage
verified: 2026-05-13T00:00:00Z
status: passed
score: 15/15 must-haves verified
overrides_applied: 0
deferred:
  - truth: "RBAC-04 full requirement (admin /admin/users route, login enforcement for disabled users)"
    addressed_in: "Phase 36"
    evidence: "ROADMAP.md Coverage Map: 'RBAC-04 | 36'; Phase 36 SC-6: 'Admin can reversibly disable any non-admin user from /admin/users; disabled users cannot log in'. Phase 34 explicitly scoped to pure storage layer (no routes)."
---

# Phase 34: User Registry + Invite-Token Storage — Verification Report

**Phase Goal:** `auth.json` holds the user list and pending invites alongside trusted_devices (single transactional file); invite tokens are minted with `secrets.token_urlsafe(32)`, stored as sha256 hashes only, verified via `hmac.compare_digest`, expire in 7 days, and consume single-use under `flock`. No routes yet — pure storage layer.
**Verified:** 2026-05-13
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | auth_store/ package exists; all callers import from auth_store unchanged | VERIFIED | `auth_store/` dir with 6 .py files; `auth_store.py` absent; all imports resolving |
| 2 | auth_store.DEFAULT_AUTH_PATH importable from auth_store; monkeypatch target intact | VERIFIED | `.venv/bin/python -c "from auth_store import DEFAULT_AUTH_PATH"` exits 0; defined at line 20 of `__init__.py` |
| 3 | DEFAULT_AUTH_PATH defined in __init__.py BEFORE any daughter import | VERIFIED | `grep -n '^DEFAULT_AUTH_PATH' auth_store/__init__.py` → line 20; `from auth_store._io import ...` is after |
| 4 | auth_store/_io.py imports DEFAULT_AUTH_PATH lazily inside _resolve_path() | VERIFIED | `grep -B3 'from auth_store import DEFAULT_AUTH_PATH' auth_store/_io.py` shows inside `def _resolve_path` body, line 109 |
| 5 | load_auth() on v1 file returns v2 shape (users=[], pending_invites=[]); migrates disk | VERIFIED | `was_v1` flag + `_normalize_v2` + `save_auth` wired in `_io.py` lines 167-170; `TestSchemaMigrationV1ToV2` passes (62 tests) |
| 6 | load_auth() on v2 file with users=[] does NOT auto-insert any user (D-07) | VERIFIED | `was_v1` gate prevents spurious save; mtime test in `TestSchemaMigrationV1ToV2.test_v2_file_does_not_re_migrate_or_re_save` passes |
| 7 | load_auth() on empty/corrupt file preserves quarantine behavior | VERIFIED | `TestSchemaV1Init.test_load_auth_corrupt_file_quarantines_and_returns_default` referenced at line 637; passes |
| 8 | load_auth() docstring explicitly warns: MUST NOT be called inside a LOCK_EX window | VERIFIED | `grep -A8 'def load_auth' auth_store/_io.py` → "cannot safely be called inside a LOCK_EX window" at lines 148-151 |
| 9 | _atomic_write_unlocked exists in auth_store/_io.py with "no flock" comment | VERIFIED | Line 44: `# No flock — caller is responsible for serialization`; line 46: `def _atomic_write_unlocked` |
| 10 | TestForbiddenImports walks auth_store/ package dir; asserts >= 5 files | VERIFIED | `tests/test_auth_store.py` line 27: `AUTH_STORE_PACKAGE = Path('auth_store')`; line 607: `assert len(py_files) >= 5` |
| 11 | mint_invite_token stores sha256:<hex> hash; raw token never in auth.json | VERIFIED | Live probe: `raw.encode() not in Path(tmp).read_bytes()` and regex check passed; `token_hash.startswith('sha256:')` confirmed |
| 12 | consume_and_create_user holds LOCK_EX; uses _read_auth_unlocked + _normalize_v2 + _atomic_write_unlocked inside window | VERIFIED | `_users.py` lines 208, 210-211, 241 confirmed; `save_auth` not present inside flock block |
| 13 | Two parallel consume calls: exactly one winner, one InviteAlreadyConsumed | VERIFIED | Live concurrent probe with `threading.Barrier(2)`: 1 success, 1 `InviteAlreadyConsumed`; `TestInviteConsumeConcurrency` passes |
| 14 | InviteExpired and InviteAlreadyConsumed are distinct ValueError subclasses; importable from auth_store | VERIFIED | `assert issubclass(InviteAlreadyConsumed, ValueError)` and `assert issubclass(InviteExpired, ValueError)` pass; live distinct-type probe passes |
| 15 | _verify_token and _read_auth_unlocked are module-private; NOT re-exported | VERIFIED | `assert not hasattr(auth_store, '_verify_token')` and `assert not hasattr(auth_store, '_read_auth_unlocked')` pass |

**Score:** 15/15 truths verified

---

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | RBAC-04 route layer: `/admin/users` view + login enforcement for disabled users | Phase 36 | ROADMAP Coverage Map: `RBAC-04 | 36`; Phase 36 SC-6: "Admin can reversibly disable any non-admin user from /admin/users; disabled users cannot log in". Phase 34 ROADMAP goal: "No routes yet — pure storage layer." |

Note: REQUIREMENTS.md traceability table incorrectly lists RBAC-04 as Phase 34 — this conflicts with ROADMAP.md Coverage Map which correctly maps it to Phase 36. The storage half of RBAC-04 (`set_user_disabled`, row retention, reversible flag) IS delivered in Phase 34 as designed.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `auth_store/__init__.py` | DEFAULT_AUTH_PATH first; re-exports all public API | VERIFIED | 138 LOC; DEFAULT_AUTH_PATH at line 20 before any daughter import |
| `auth_store/_io.py` | load_auth, save_auth, _atomic_write_unlocked, _normalize_v2 call, LOCK_EX warning | VERIFIED | 177 LOC; all functions present; migration logic at lines 167-170 |
| `auth_store/_schema.py` | SCHEMA_VERSION=2; AuthData, User, PendingInvite TypedDicts; _normalize_v2 | VERIFIED | 113 LOC; all TypedDicts and helper present |
| `auth_store/_devices.py` | Device helper functions moved verbatim | VERIFIED | 127 LOC |
| `auth_store/_magic_links.py` | Magic-link helpers moved verbatim | VERIFIED | 147 LOC |
| `auth_store/_users.py` | InviteAlreadyConsumed, InviteExpired, create_user, mint_invite_token, consume_and_create_user, get_user, list_users, set_user_disabled, _read_auth_unlocked, _verify_token | VERIFIED | 246 LOC (under 250 cap); all functions present |
| `tests/test_auth_store.py` | AUTH_STORE_PACKAGE walk; TestSchemaMigrationV1ToV2; >= 5 assertion | VERIFIED | Line 27 AUTH_STORE_PACKAGE; line 643 TestSchemaMigrationV1ToV2; line 607 >= 5 |
| `tests/test_auth_store_users.py` | 5 test classes; real threading.Barrier concurrency; isinstance checks | VERIFIED | 24 tests; all 5 classes present; barrier at lines 195, 226 |
| `auth_store.py` (deleted) | Absent after Plan 01 Task 2 | VERIFIED | `test ! -f auth_store.py` confirmed |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `auth_store/__init__.py` top | `DEFAULT_AUTH_PATH` constant | Defined at line 20 BEFORE `from auth_store._io import` | WIRED | Line 20: `DEFAULT_AUTH_PATH = Path('auth.json')`; daughter imports follow |
| `auth_store/_io.py::_resolve_path` | `auth_store.DEFAULT_AUTH_PATH` | Lazy import inside function body | WIRED | Line 109 inside `def _resolve_path`; no top-level import |
| `auth_store/_users.py::consume_and_create_user` | `auth_store/_io.py::_atomic_write_unlocked` | Inside LOCK_EX window | WIRED | Lines 208 (LOCK_EX), 241 (_atomic_write_unlocked); save_auth absent from window |
| `auth_store/_users.py::consume_and_create_user` | `auth_store/_schema.py::_normalize_v2` | Called inside flock window before scanning invites | WIRED | Line 211: `data = _normalize_v2(raw_data)` inside lock |
| `auth_store/_users.py::_verify_token` | `hmac.compare_digest` | Timing-safe compare of sha256:<hex> | WIRED | Line 75: `return hmac.compare_digest(stored_hash, expected)` |
| `tests/test_auth_store.py::TestForbiddenImports` | `auth_store/` package | `AUTH_STORE_PACKAGE.glob('*.py')` walk | WIRED | Line 605: `py_files = list(AUTH_STORE_PACKAGE.glob('*.py'))` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `_users.py::consume_and_create_user` | `data` (pending_invites, users) | `_read_auth_unlocked(resolved)` reads auth.json from disk | Yes — real file I/O inside flock window | FLOWING |
| `_io.py::load_auth` | `payload` | `json.loads(path.read_text())` | Yes — real file I/O | FLOWING |
| `_schema.py::_normalize_v2` | `data` dict mutation | Pure in-memory; no I/O (safe for flock window) | N/A — pure transform | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SC1: users[]+pending_invites[] exist; transactional consume+create | Live Python probe: mint+consume+assert arrays | SC1 PASS | PASS |
| SC2: raw token never in auth.json; sha256: prefix stored | Live Python probe: bytes check + regex check | SC2 PASS | PASS |
| SC3: two parallel consumes → exactly one winner | Live Python probe: threading.Barrier(2) + collect results | SC3 PASS | PASS |
| SC4: InviteExpired and InviteAlreadyConsumed are distinct types | Live Python probe: expired + double-consume paths | SC4 PASS | PASS |
| RBAC-04 storage: disabled flag, row retained, reversible, False on unknown | Live Python probe: set_user_disabled assertions | RBAC-04 storage PASS | PASS |

---

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes declared or present for Phase 34.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| RBAC-03 (storage half) | 34-01-PLAN.md, 34-02-PLAN.md | sha256 hash store, hmac.compare_digest verify, 7-day expiry, single-use flock | SATISFIED | SC1-SC4 live probes pass; `mint_invite_token`, `consume_and_create_user` fully implemented and tested |
| RBAC-04 (storage half) | 34-02-PLAN.md | set_user_disabled: reversible disable, row retained, data preserved | SATISFIED (storage) | `set_user_disabled` verified live; row retention confirmed; reversible; deferred route+enforcement to Phase 36 |
| RBAC-04 (route + login enforcement) | Phase 36 | `/admin/users` view, disabled users cannot log in | DEFERRED | Phase 36 SC-6; ROADMAP Coverage Map; Phase 34 explicitly "no routes yet" |

Note on RBAC-03 split: ROADMAP correctly splits RBAC-03 across Phase 34 (storage) and Phase 37 (acceptance flow). Plans claim RBAC-03 for Phase 34 — this is accurate for the storage deliverable; the acceptance flow routes land in Phase 37.

---

### Anti-Patterns Found

No debt markers (TBD, FIXME, XXX, TODO, HACK, PLACEHOLDER) found in any phase-modified file. No stub patterns detected. No empty implementations.

---

### Human Verification Required

None. All success criteria are programmatically verifiable and verified.

---

### Gaps Summary

No gaps. All 15 must-haves verified. All 4 roadmap success criteria confirmed via live behavioral probes. Full test suite green (2151 passed). RBAC-04 route layer deferred to Phase 36 per ROADMAP — this is expected and intentional, not a gap.

---

_Verified: 2026-05-13_
_Verifier: Claude (gsd-verifier)_
