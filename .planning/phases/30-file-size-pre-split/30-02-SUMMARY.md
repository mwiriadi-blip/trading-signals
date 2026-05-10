---
phase: 30
plan: "30-02"
subsystem: web-routes
tags: [refactor, file-split, package, trades]
dependency_graph:
  requires: []
  provides: [web.routes.trades package]
  affects: [web/app.py, tests/test_web_trades.py]
tech_stack:
  added: []
  patterns: [package-per-route (D-04), re-export via __all__]
key_files:
  created:
    - web/routes/trades/__init__.py
    - web/routes/trades/_models.py
    - web/routes/trades/_renderers.py
  modified: []
  deleted:
    - web/routes/trades.py
decisions:
  - Remove _AWST and _format_pydantic_errors from __init__.py imports (unused there; ruff F401)
  - Remove _render_positions_tbody_partial from __init__.py imports (only called internally by _renderers.py)
  - Remove _OPERATOR_CLOSE from _renderers.py imports (not used in any renderer function)
metrics:
  duration: ~10min
  completed: "2026-05-11"
  tasks: 1
  files: 4
---

# Phase 30 Plan 02: Split trades.py into Package Summary

Behaviour-preserving split of `web/routes/trades.py` (746 LOC single file) into a `web/routes/trades/` package with three daughter files, each under 500 LOC. Preserves all import paths that callers and tests depend on.

## What Was Built

Split `web/routes/trades.py` into:

- `web/routes/trades/_models.py` (247 LOC) — Pydantic request models (`OpenTradeRequest`, `CloseTradeRequest`, `ModifyTradeRequest`), `_OpenConflict` exception, `_AWST`/`_OPERATOR_CLOSE` constants, `_now_awst`, `_format_pydantic_errors`, `_build_position_dict`, `_validation_exception_handler`
- `web/routes/trades/_renderers.py` (174 LOC) — All seven HTML partial helpers (`_render_position_row_partial`, `_render_positions_tbody_partial`, `_render_close_form_partial`, `_render_modify_form_partial`, `_render_open_success_partial`, `_render_close_success_partial`, `_render_modify_success_partial`)
- `web/routes/trades/__init__.py` (340 LOC) — `register(app)` function with all six endpoint handlers; imports from siblings; `__all__` re-export block for test/caller import surface preservation

## Commits

| Hash | Description |
|------|-------------|
| 501e6c9 | refactor(30-02): split trades.py into 3-file package |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Ruff Cleanup] Removed unused imports from __init__.py**
- **Found during:** Implementation review
- **Issue:** `_AWST`, `_format_pydantic_errors`, `_render_positions_tbody_partial` were imported into `__init__.py` per the plan's template, but none are directly used within `register()` — they're either used inside `_models.py`/`_renderers.py` internally, or the plan over-specified the import list
- **Fix:** Removed those three from `__init__.py` imports; `_render_positions_tbody_partial` is still accessible via `_renderers.py` internally; `_AWST` stays in `_models.py` for `_now_awst`; `_format_pydantic_errors` stays in `_models.py` for `_validation_exception_handler`
- **Files modified:** web/routes/trades/__init__.py

**2. [Rule 1 - Ruff Cleanup] Removed spurious _OPERATOR_CLOSE import from _renderers.py**
- **Found during:** Implementation review
- **Issue:** Plan note said "If any renderer references `_OPERATOR_CLOSE`, add import" — but no renderer function actually uses it; the constant is only used in the close trade handler in `__init__.py`
- **Fix:** Removed the `# noqa: F401`-commented import from `_renderers.py`
- **Files modified:** web/routes/trades/_renderers.py

## Known Stubs

None. This is a behaviour-preserving mechanical split — no logic changed.

## Threat Flags

None. No new network endpoints, auth paths, or trust-boundary changes introduced. This is a pure file reorganization.

## Verification Status

Structural checks passed (grep-based):
- `test ! -f web/routes/trades.py` — PASS (single-file removed)
- `test -d web/routes/trades` — PASS (package exists)
- All three daughter files exist — PASS
- `__init__.py` LOC: 340 (<=500) — PASS
- `_models.py` LOC: 247 (<=500) — PASS
- `_renderers.py` LOC: 174 (<=500) — PASS
- `grep -c "^def register"` in `__init__.py`: 1 — PASS
- `grep -c "^class OpenTradeRequest"` in `_models.py`: 1 — PASS
- `grep -c "^class CloseTradeRequest"` in `_models.py`: 1 — PASS
- `grep -c "^class ModifyTradeRequest"` in `_models.py`: 1 — PASS
- `grep -c "^class _OpenConflict"` in `_models.py`: 1 — PASS
- `grep -c "^def _render_position_row_partial"` in `_renderers.py`: 1 — PASS
- `grep -c "^def _render_close_form_partial"` in `_renderers.py`: 1 — PASS
- `grep -c "^def _render_modify_form_partial"` in `_renderers.py`: 1 — PASS

Note: pytest and ruff could not be executed in the worktree agent sandbox (Bash sandbox blocks Python execution). The Wave 2 integration gate (plan 30-07) covers full test suite verification before merge.

## Self-Check: PASSED

Files confirmed created:
- web/routes/trades/__init__.py — FOUND
- web/routes/trades/_models.py — FOUND
- web/routes/trades/_renderers.py — FOUND
- web/routes/trades.py — REMOVED (confirmed via git status)

Commit 501e6c9 confirmed in git log.
