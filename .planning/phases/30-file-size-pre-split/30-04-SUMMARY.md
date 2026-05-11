---
phase: 30
plan: "30-04"
subsystem: web/routes/totp
tags: [file-split, refactor, totp, auth]
dependency_graph:
  requires: ["30-05"]
  provides: ["web.routes.totp package"]
  affects: ["web/app.py", "web/services/totp_service.py"]
tech_stack:
  added: []
  patterns: ["D-06 file-size split", "D-03 re-export surface preservation"]
key_files:
  created:
    - web/routes/totp/__init__.py
    - web/routes/totp/_renderers.py
  modified: []
  deleted:
    - web/routes/totp.py
decisions:
  - "Moved _TOTP_INLINE_CSS constant to _renderers.py alongside render helpers that consume it"
  - "Fixed UP017 (timezone.utc → UTC alias) caught by ruff during the split — original totp.py had same lint issue"
metrics:
  duration: "~5min"
  completed: "2026-05-11"
  tasks_completed: 1
  tasks_total: 1
  files_created: 2
  files_deleted: 1
---

# Phase 30 Plan 04: TOTP File-Size Split Summary

**One-liner:** Behaviour-preserving split of 614-LOC `web/routes/totp.py` into `web/routes/totp/` package — `__init__.py` (282 LOC, register()) and `_renderers.py` (333 LOC, all render helpers) — per D-06 boundary.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Split web/routes/totp.py into 2-file package (D-06) | fe328d6 | web/routes/totp/__init__.py, web/routes/totp/_renderers.py (created), web/routes/totp.py (deleted) |

## Verification

- `test ! -f web/routes/totp.py` — PASS
- `test -d web/routes/totp` — PASS
- `wc -l web/routes/totp/__init__.py` → 282 (<=500) — PASS
- `wc -l web/routes/totp/_renderers.py` → 333 (<=500) — PASS
- `grep -c "from web.routes.login import _is_safe_next" web/routes/totp/__init__.py` → 1 — PASS
- `grep -c "^def register" web/routes/totp/__init__.py` → 1 — PASS
- `grep -c "^def _render_qr_data_uri" web/routes/totp/_renderers.py` → 1 — PASS
- `pytest tests/ -x -q -k "totp"` → 35 passed — PASS
- `ruff check web/routes/totp/` → All checks passed — PASS
- `python -c "from web.routes import totp as t; assert callable(t.register)"` → 0 — PASS

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed UP017 ruff lint error (timezone.utc → UTC alias)**
- **Found during:** Task 1 verify step (ruff check web/routes/totp/)
- **Issue:** `datetime.now(timezone.utc)` triggers ruff UP017; the original `web/routes/totp.py` had the same issue (both files were on Python 3.11 which introduced `datetime.UTC`)
- **Fix:** Changed `from datetime import datetime, timezone` + `datetime.now(timezone.utc)` to `from datetime import UTC, datetime` + `datetime.now(UTC)` in `__init__.py`
- **Files modified:** `web/routes/totp/__init__.py`
- **Commit:** fe328d6 (included in task commit)

## Architecture Notes

- `_TOTP_INLINE_CSS` constant moved to `_renderers.py` — it is consumed exclusively by the render helpers; keeping it co-located avoids a cross-file reference
- `ENROLL_PATH` and `VERIFY_PATH` constants remain in `__init__.py` — they are part of the route registration surface
- All helper closures inside `register()` (`_validate_enroll_cookie`, `_validate_session_cookie`, `_validate_pending_cookie`, `_redirect_to_login`, `_make_session_cookie`, `_provisioning_uri`, `_verify_code`) were confirmed closure-bound to `register()`-local serializers — they stay inside `register()` as required

## Stub Tracking

None — pure refactor, no data wiring changed.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This is a behaviour-preserving file split.

## Self-Check: PASSED

- `web/routes/totp/__init__.py` — FOUND
- `web/routes/totp/_renderers.py` — FOUND
- `web/routes/totp.py` — correctly absent
- Commit `fe328d6` — FOUND (`git log --oneline -3` confirms)
