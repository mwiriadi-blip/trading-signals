---
phase: "34"
plan: "01"
subsystem: auth_store
tags: [package-split, schema-migration, auth, v2]
dependency_graph:
  requires: []
  provides: [auth_store-package, schema-v2, _normalize_v2, _atomic_write_unlocked]
  affects: [auth_store._users (Plan 02)]
tech_stack:
  added: []
  patterns: [lazy-import-circular-guard, was_v1-migration-gate, package-walk-ast-guard]
key_files:
  created:
    - auth_store/__init__.py
    - auth_store/_schema.py
    - auth_store/_io.py
    - auth_store/_devices.py
    - auth_store/_magic_links.py
  modified:
    - tests/test_auth_store.py
  deleted:
    - auth_store.py
decisions:
  - "DEFAULT_AUTH_PATH defined at top of auth_store/__init__.py BEFORE any daughter import to prevent circular-init"
  - "_io._resolve_path uses lazy 'from auth_store import DEFAULT_AUTH_PATH' inside function body (not top-level)"
  - "SCHEMA_VERSION bumped 1 -> 2; _default_auth_data() returns v2 with users=[], pending_invites=[]"
  - "_normalize_v2 is a pure in-memory helper (no I/O) shared with Plan 02 flock window"
  - "load_auth() v1->v2 migration guarded by was_v1 flag — v2 files never trigger extra save"
  - "_atomic_write_unlocked added to _io.py for Plan 02 flock window reuse"
metrics:
  duration: "9m 33s"
  completed: "2026-05-13"
  tasks: 2
  files: 7
requirements: [RBAC-03, RBAC-04]
---

# Phase 34 Plan 01: auth_store/ Package Split + Schema v2 Migration Summary

auth_store.py (520-LOC monolith) converted to auth_store/ package (5 daughter files, all under 500 LOC); SCHEMA_VERSION bumped to 2 with User + PendingInvite TypedDicts; v1->v2 migration wired into load_auth() via shared _normalize_v2 helper; circular-import risk eliminated via explicit init-time ordering + lazy _resolve_path import; TestForbiddenImports updated to walk package directory; 2127 tests green.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create auth_store/ package skeleton with schema v2 | ce8bec0 | auth_store/{__init__,_schema,_io,_devices,_magic_links}.py, tests/test_auth_store.py |
| 2 | TestForbiddenImports + migration tests + delete auth_store.py | 14eefd1 | tests/test_auth_store.py, auth_store.py (deleted) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test monkeypatched auth_store.os — not available on package**
- **Found during:** Task 1 test run
- **Issue:** `TestAtomicWriteCrash` patched `auth_store.os` which was a module-level attribute on the flat file. The package `auth_store.__init__` does not expose `os`. After split, `os` lives in `auth_store._io`.
- **Fix:** tests/test_auth_store.py — changed to `import auth_store._io as _auth_io; monkeypatch.setattr(_auth_io.os, 'fsync', ...)` to target the correct namespace per LEARNINGS G-68.
- **Commit:** ce8bec0

**2. [Rule 1 - Bug] v1 default assertions outdated after SCHEMA_VERSION bump**
- **Found during:** Task 1 test run
- **Issue:** Three tests in `TestSchemaV1Init` asserted `schema_version: 1` and no `users`/`pending_invites` keys. `_default_auth_data()` now returns v2 shape.
- **Fix:** tests/test_auth_store.py — updated assertions to expect `schema_version: 2` + `users: []` + `pending_invites: []`. Renamed round-trip test to `test_load_auth_round_trips_existing_v2_file` with v2 fixture.
- **Commit:** ce8bec0

## Threat Surface Scan

No new network endpoints, auth paths, or trust-boundary file access patterns introduced. This plan is a pure structural refactor + schema extension (no new I/O surfaces). Existing threat mitigations (T-34-01-01 through T-34-01-05) implemented as designed:

- T-34-01-01 (Tampering): migration writes via `_atomic_write` (tempfile+fsync+os.replace); corrupt-file quarantine preserved verbatim.
- T-34-01-03 (DoS/recursion): `was_v1` flag gates save_auth call — v2 files never trigger re-save; no recursion path.
- T-34-01-04 (DoS/circular-import): DEFAULT_AUTH_PATH at top of __init__.py; lazy import in _resolve_path body; verified by grep.
- T-34-01-05 (Tampering/corrupt): corruption-recovery path preserved verbatim; regression-tested by TestSchemaV1Init.test_load_auth_corrupt_file_quarantines_and_returns_default.

## Self-Check: PASSED

- [x] auth_store/__init__.py exists: FOUND
- [x] auth_store/_schema.py exists: FOUND
- [x] auth_store/_io.py exists: FOUND
- [x] auth_store/_devices.py exists: FOUND
- [x] auth_store/_magic_links.py exists: FOUND
- [x] auth_store.py absent: CONFIRMED
- [x] Task 1 commit ce8bec0: FOUND
- [x] Task 2 commit 14eefd1: FOUND
- [x] SCHEMA_VERSION == 2: CONFIRMED
- [x] 2127 tests green: CONFIRMED
