---
phase: 30
plan: "30-01"
subsystem: test-boundary
tags: [hex-boundary, ast-guard, forbidden-modules, ops-03]
dependency_graph:
  requires: []
  provides: [OPS-03]
  affects: [tests/test_signal_engine.py]
tech_stack:
  added: []
  patterns: [AST-blocklist extension, frozenset cluster convention]
key_files:
  created: []
  modified:
    - tests/test_signal_engine.py
decisions:
  - "Forward-looking guard added before v1.3 I/O modules exist — test passes immediately because no hex imports them yet"
  - "Single new cluster comment block groups the 4 v1.3 names together (consistent with existing per-group comments)"
  - "FORBIDDEN_MODULES_BACKTEST_PURE inherits via set union — no separate edit required (D-11/D-12)"
metrics:
  duration: "~3min"
  completed: "2026-05-11"
  tasks_completed: 2
  files_modified: 1
---

# Phase 30 Plan 01: Extend FORBIDDEN_MODULES with v1.3 I/O Names Summary

AST hex-boundary blocklist extended with 4 forward-looking v1.3 I/O module names (`web`, `news_fetcher`, `news_filter`, `auth_store`) so any future Phase 31+ import of these modules from a pure-math hex fails CI immediately.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 0 | Pre-flight — verify 'web' safe to add | (no commit — verification only) | — |
| 1 | Extend FORBIDDEN_MODULES with 4 v1.3 I/O module names | 4ce73df | tests/test_signal_engine.py |

## Verification Results

- `rg "from web[\. ]|import web" signal_engine.py sizing_engine.py system_params.py pnl_engine.py alert_engine.py backtest/ -g '*.py'` — empty output (pre-flight pass)
- AST check confirms all 4 names present in `FORBIDDEN_MODULES` frozenset
- `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x -q` — 7 passed (parametrized over all `_HEX_PATHS_ALL`)
- `pytest tests/test_signal_engine.py -x -q` — 127 passed, 0 failed
- `FORBIDDEN_MODULES_BACKTEST_PURE` inherits `{'web', 'news_fetcher', 'news_filter', 'auth_store'}` via set union without separate edit

## Deviations from Plan

None — plan executed exactly as written.

The plan specified `rg --include='*.py'` but that flag is not valid in this version of ripgrep; switched to `-g '*.py'` (equivalent glob pattern). This is a plan-spec cosmetic error, not a code deviation.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan only modifies a test file adding names to a frozenset constant.

## Self-Check: PASSED

- [x] `tests/test_signal_engine.py` modified and committed at 4ce73df
- [x] Commit 4ce73df exists: `git log --oneline | grep 4ce73df` → confirmed
- [x] 127 tests green, 0 failed
- [x] FORBIDDEN_MODULES_BACKTEST_PURE inheritance verified
