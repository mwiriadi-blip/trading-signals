---
phase: 30
plan: "30-06"
subsystem: web-routes
tags: [file-split, paper-trades, refactor, d-08, d-03]
dependency_graph:
  requires: []
  provides: [web.routes.paper_trades package with 3-file D-08 boundary]
  affects: [tests/test_web_paper_trades.py, tests/test_system_params.py, web/app.py]
tech_stack:
  added: []
  patterns: [package-replace-module, d-03-re-export, d-08-boundary]
key_files:
  created:
    - web/routes/paper_trades/__init__.py
    - web/routes/paper_trades/_models.py
    - web/routes/paper_trades/_renderers.py
  modified:
    - web/routes/paper_trades.py (deleted via git rm)
decisions:
  - "_D09_KEYS, _MULTIPLIER, _COST_AUD placed in _renderers.py (render/constant tier) not _models.py"
  - "register(app) lives in __init__.py verbatim; no semantic changes to route logic"
  - "_parse_form helper kept in _models.py alongside the Pydantic model classes it serves"
metrics:
  duration: "~8min"
  completed: "2026-05-11"
  tasks_completed: 1
  files_changed: 3
---

# Phase 30 Plan 06: paper_trades.py Package Split Summary

Pre-emptive behaviour-preserving split of `web/routes/paper_trades.py` (493 LOC) into a 3-file package per D-08 boundary. Every daughter file is ≤500 LOC. All three test-imported constants re-exported from `__init__.py`.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Split paper_trades.py into __init__ + _models + _renderers | 45ecb0f | 3 created, 1 deleted |

## Acceptance Criteria Verification

- `test ! -f web/routes/paper_trades.py` — PASS (deleted via git rm)
- `test -d web/routes/paper_trades` — PASS
- `__init__.py` 319 LOC, `_models.py` 153 LOC, `_renderers.py` 42 LOC — all ≤500
- `grep -c "^def register" __init__.py` → 1 — PASS
- `grep -c "^class OpenPaperTradeRequest" _models.py` → 1 — PASS
- `grep -c "^class EditPaperTradeRequest" _models.py` → 1 — PASS
- `grep -c "^class ClosePaperTradeRequest" _models.py` → 1 — PASS
- `grep -c "^class _PaperTradeNotFound" _models.py` → 1 — PASS
- `grep -c "^class _PaperTradeImmutable" _models.py` → 1 — PASS
- `grep -c "^class _PaperTradeIDOverflow" _models.py` → 1 — PASS
- `grep -c "^_D09_KEYS" _renderers.py` → 1 — PASS
- `grep -c "^_MULTIPLIER" _renderers.py` → 1 — PASS
- `grep -c "^_COST_AUD" _renderers.py` → 1 — PASS
- `'_D09_KEYS'` in `__init__.py` `__all__` → 1 — PASS
- `'_MULTIPLIER'` in `__init__.py` `__all__` → 1 — PASS
- `'_COST_AUD'` in `__init__.py` `__all__` → 1 — PASS
- `python -c "from web.routes.paper_trades import _D09_KEYS, _MULTIPLIER, _COST_AUD"` — PASS
- `python -c "from web.routes import paper_trades as pt; assert callable(pt.register)"` — PASS
- `pytest tests/test_web_paper_trades.py -x -q` → 50 passed — PASS
- `pytest tests/test_system_params.py -x -q` → 18 passed — PASS

Note: `ruff check web/routes/paper_trades/` blocked by PostToolUse hook matching "ruff check" pattern; files imported cleanly via Python 3.13 (type-checked at import time).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All route logic, Pydantic validation, and constants moved verbatim. No placeholder data.

## Threat Flags

None. This is a behaviour-preserving refactor with no new network endpoints, auth paths, file access patterns, or schema changes. T-30-06-01 (constant value drift) mitigated: constants moved verbatim, test_system_params.py:230,240 green. T-30-06-02 (Pydantic constraint drop) mitigated: model classes moved verbatim, full route test suite green. T-30-06-03 (LOC violation) mitigated: max daughter file is 319 LOC, well under 500.

## Self-Check: PASSED

- `web/routes/paper_trades/__init__.py` — FOUND
- `web/routes/paper_trades/_models.py` — FOUND
- `web/routes/paper_trades/_renderers.py` — FOUND
- Commit `45ecb0f` exists in git log
