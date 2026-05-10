---
phase: 30
plan: "30-05"
subsystem: web/routes/login
tags: [refactor, file-split, package, import-surface]
dependency_graph:
  requires: []
  provides:
    - web.routes.login.register
    - web.routes.login._is_safe_next
  affects:
    - web/routes/totp.py (cross-route import _is_safe_next)
    - web/app.py (from web.routes import login as login_route)
tech_stack:
  added: []
  patterns:
    - Python package split (single-file → __init__.py + _renderers.py)
    - D-03 import-surface re-export via __all__
    - D-05 render-helper boundary separation
key_files:
  created:
    - web/routes/login/__init__.py
    - web/routes/login/_renderers.py
  modified: []
  deleted:
    - web/routes/login.py
decisions:
  - _is_safe_next placed in _renderers.py and re-exported from __init__.py via __all__ (D-03 contract)
  - session_serializer kept in register() verbatim (unused in login handlers but present in original; behaviour-preserving)
  - BadSignature/SignatureExpired imports from original omitted (were unused in login.py body; ruff would flag)
metrics:
  duration: "~10 minutes"
  completed: "2026-05-11"
  tasks_completed: 1
  tasks_total: 1
  files_created: 2
  files_deleted: 1
---

# Phase 30 Plan 05: Split web/routes/login.py into Package Summary

Behaviour-preserving split of 608-LOC `web/routes/login.py` into a two-file package: `_renderers.py` (render helpers + `_is_safe_next`) and `__init__.py` (`register(app)` + D-03 re-export surface).

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Split web/routes/login.py into 2-file package (D-05) | 75d162c | web/routes/login/__init__.py, web/routes/login/_renderers.py, -web/routes/login.py |

## LOC Budget

| File | LOC | Budget |
|------|-----|--------|
| web/routes/login/__init__.py | 260 | ≤500 |
| web/routes/login/_renderers.py | 359 | ≤500 |

Both files within budget.

## Import Surface Preserved (D-03)

- `from web.routes import login as login_route` → resolves via `__init__.py` (web/app.py:43)
- `from web.routes.login import _is_safe_next` → resolves via `__init__.py` re-export (web/routes/totp.py:43)
- `__all__ = ['register', '_is_safe_next']` in `__init__.py`

## Closure-Freeness Verification

All moved helpers (`_is_safe_next`, `_render_login_form`, `_render_forgot_2fa_form`, `_render_check_email_page`, `_render_logout_confirmation`, `_log_login_failure`) confirmed module-level in the original — none capture variables from `register()` closure. Safe to move verbatim.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. This is a pure structural refactor. All STRIDE mitigations from the threat register remain intact:
- T-30-05-01: `_is_safe_next` body moved verbatim; semantics unchanged
- T-30-05-02: `__all__` includes `_is_safe_next`; cross-route import resolves
- T-30-05-03: `_log_login_failure` body moved verbatim; log text unchanged

## Self-Check

- [x] `web/routes/login/__init__.py` exists (260 LOC)
- [x] `web/routes/login/_renderers.py` exists (359 LOC)
- [x] `web/routes/login.py` deleted via `git rm`
- [x] commit 75d162c exists
- [x] `grep -c "^def register"` → 1 in __init__.py
- [x] `grep -c "^def _is_safe_next"` → 1 in _renderers.py
- [x] `grep "'_is_safe_next'" __init__.py` → in __all__
- [x] `grep -rn "from web.routes.login import"` → still 1 (totp.py:43 unchanged)

## Self-Check: PASSED
