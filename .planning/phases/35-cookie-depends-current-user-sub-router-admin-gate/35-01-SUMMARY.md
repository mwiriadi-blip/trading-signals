---
phase: 35
plan: 01
subsystem: auth_store
tags: [auth, lookup, email, case-insensitive]
dependency_graph:
  requires: []
  provides: [auth_store.get_user_by_email]
  affects: [web/middleware/auth.py, web/routes/totp/__init__.py]
tech_stack:
  added: []
  patterns: [linear-scan, case-insensitive-comparison, re-export]
key_files:
  created: []
  modified:
    - auth_store/_users.py
    - auth_store/__init__.py
    - tests/test_auth_store.py
decisions:
  - get_user_by_email lowercases both sides (needle and stored) for case-insensitive email matching
  - Non-str email collapses to empty needle so None is returned without raising
  - First-match duplicate behaviour documented in docstring (Phase 34 no-uniqueness invariant)
metrics:
  duration: 479s
  completed: 2026-05-13
  tasks_completed: 2
  files_modified: 3
---

# Phase 35 Plan 01: get_user_by_email helper + re-export + tests Summary

**One-liner:** Case-insensitive `get_user_by_email` added to `auth_store._users`, re-exported from `auth_store.__init__`, locked with 9-case `TestGetUserByEmail` unit tests.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| T1 RED | get_user_by_email RED gate | 9190717 | tests/test_auth_store.py |
| T1 GREEN | Implement get_user_by_email + re-export | 1f89d40 | auth_store/_users.py, auth_store/__init__.py |
| T2 | TestGetUserByEmail — 9 cases | 7b8ea7f | tests/test_auth_store.py |

## What Was Built

- `auth_store/_users.py`: `get_user_by_email(email, path=None) -> dict | None` added immediately after `get_user` (line 134). Mirrors the linear-scan pattern of `get_user`. Case-insensitive: `needle = email.lower() if isinstance(email, str) else ''`; stored email lowercased before equality. Returns first match when duplicates exist.
- `auth_store/__init__.py`: `get_user_by_email` added to the `from auth_store._users import (...)` block and to `__all__`. DEFAULT_AUTH_PATH ordering invariant (lines 1-22) untouched.
- `tests/test_auth_store.py`: `TestGetUserByEmail` class with 9 named tests replacing the 2-test RED gate skeleton.

## Verification

- `pytest tests/test_auth_store.py::TestGetUserByEmail` → 9 passed
- `python -c "from auth_store import get_user_by_email; print(callable(get_user_by_email))"` → True
- `python -c "import auth_store; assert 'get_user_by_email' in auth_store.__all__"` → exits 0
- Full suite: 2160 passed, 13 deselected (was 2151 pre-plan; +9 new tests)
- Pre-existing intermittent failure: `test_tampered_tsi_trusted_does_NOT_grant` fails when run after the full suite in a specific ordering but passes in isolation — out of scope (Rule 3 boundary; pre-dates this plan).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

No new network endpoints, auth paths, or file access patterns introduced. `get_user_by_email` is a pure read helper. T-35-01-02 (Tampering) mitigated: strict lowercased equality, no regex/fnmatch/SQL. T-35-01-04 (Elevation of Privilege) mitigated: helper returns the row but does not grant access — role checks live in `require_admin` (Plan 03).

## Self-Check: PASSED

- `auth_store/_users.py` exists and contains `def get_user_by_email(`: confirmed
- `auth_store/__init__.py` contains `get_user_by_email,` in import block and `'get_user_by_email',` in `__all__`: confirmed
- `tests/test_auth_store.py` contains `class TestGetUserByEmail`: confirmed (9 tests collected and passing)
- Commits 9190717, 1f89d40, 7b8ea7f exist in git log: confirmed
