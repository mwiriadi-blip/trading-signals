---
phase: 15
plan: 01
subsystem: testing
tags:
  - phase15
  - testing
  - scaffolding
  - hex-boundary
  - wave0-gate
dependency_graph:
  requires: []
  provides:
    - FORBIDDEN_MODULES_DASHBOARD without sizing_engine (gate for Plan 05)
    - test_dashboard_no_module_top_sizing_engine_import AST guard (REVIEWS M-2)
    - TestDetectDrift skeleton in tests/test_sizing_engine.py (gate for Plan 02)
    - TestClearWarningsBySource skeleton in tests/test_state_manager.py (gate for Plan 03)
    - TestRenderCalculatorRow + TestRenderDriftBanner + TestBannerStackOrder skeletons in tests/test_dashboard.py (gate for Plan 05)
    - TestForwardStopFragment + TestSideBySideStopDisplay + TestTradesDriftLifecycle skeletons in tests/test_web_dashboard.py (gate for Plan 06)
    - TestDriftBanner + TestBannerStackOrder skeletons in tests/test_notifier.py (gate for Plan 07)
    - TestDriftWarningLifecycle skeleton in tests/test_main.py (gate for Plan 04)
  affects:
    - tests/test_signal_engine.py
    - tests/test_sizing_engine.py
    - tests/test_state_manager.py
    - tests/test_dashboard.py
    - tests/test_web_dashboard.py
    - tests/test_notifier.py
    - tests/test_main.py
tech_stack:
  added: []
  patterns:
    - pytest.skip skeleton pattern for Wave 0 class stubs
    - ast.parse + tree.body (module-top-only) AST guard pattern
key_files:
  created: []
  modified:
    - tests/test_signal_engine.py
    - tests/test_sizing_engine.py
    - tests/test_state_manager.py
    - tests/test_dashboard.py
    - tests/test_web_dashboard.py
    - tests/test_notifier.py
    - tests/test_main.py
decisions:
  - sizing_engine removed from FORBIDDEN_MODULES_DASHBOARD per Phase 15 D-01 (CALC calculator sub-row will use local imports per C-2)
  - New module-top AST guard replaces the blocklist protection (REVIEWS M-2) — walks tree.body only, not ast.walk, so local function-body imports stay green
  - All 11 skeleton classes use pytest.skip with plan number to keep incremental test-count growth clean across waves
metrics:
  duration: ~22 minutes
  completed: '2026-04-26'
  tasks_completed: 4
  files_modified: 7
  new_skipped_tests: 65
  new_green_tests: 1
  new_failed_tests: 0
requirements:
  - CALC-01
  - CALC-02
  - CALC-03
  - CALC-04
  - SENTINEL-01
  - SENTINEL-02
  - SENTINEL-03
---

# Phase 15 Plan 01: Wave 0 Gate — FORBIDDEN_MODULES_DASHBOARD + AST Guard + Test Skeletons Summary

**One-liner:** Dropped `sizing_engine` from `FORBIDDEN_MODULES_DASHBOARD`, added explicit module-top AST guard (`tree.body` walk, REVIEWS M-2), and scaffolded 11 skeleton test classes (65 skipped + 1 new green) across 7 test files as Wave 0 gate for Plans 02–07.

## Tasks Completed

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Update FORBIDDEN_MODULES_DASHBOARD | 8c86a4b | Removed `'sizing_engine'` from frozenset; added 4-line comment with M-2 cross-reference |
| 2 | Add AST guard test_dashboard_no_module_top_sizing_engine_import | e74c8a3 | New method in TestDeterminism at line 888; walks tree.body only; GREEN at Wave 0 |
| 3 | Skeleton classes in test_sizing_engine.py + test_state_manager.py | 11baf1c | TestDetectDrift (12 methods) + TestClearWarningsBySource (5 methods) |
| 4 | Skeleton classes in 4 remaining test files | 57f4628 | 9 classes across test_dashboard, test_web_dashboard, test_notifier, test_main |

## FORBIDDEN_MODULES_DASHBOARD Change (Task 1)

**File:** `tests/test_signal_engine.py`, lines 556–565

**Before:**
```python
FORBIDDEN_MODULES_DASHBOARD = frozenset({
  # Sibling hexes — dashboard.py is a peer, never imports them
  'signal_engine', 'sizing_engine', 'data_fetcher', 'notifier', 'main',
  ...
})
```

**After:**
```python
FORBIDDEN_MODULES_DASHBOARD = frozenset({
  # Sibling hexes — dashboard.py is a peer, never imports them
  # NOTE: sizing_engine is ALLOWED as of Phase 15 (CALC-01..04 calculator
  # sub-row uses sizing_engine LOCALLY per C-2; CONTEXT D-01 explicit approval).
  # MODULE-TOP imports of sizing_engine in dashboard.py remain forbidden
  # (enforced by test_dashboard_no_module_top_sizing_engine_import — REVIEWS M-2).
  'signal_engine', 'data_fetcher', 'notifier', 'main',
  ...
})
```

`grep -A 8 "FORBIDDEN_MODULES_DASHBOARD = frozenset" | grep -c "'sizing_engine'"` returns 0. ✓

## New AST Guard (Task 2)

**File:** `tests/test_signal_engine.py`, lines 888–926 (inside `TestDeterminism` class, after `test_dashboard_no_forbidden_imports`)

**Method:** `test_dashboard_no_module_top_sizing_engine_import`

Key design decisions:
- Walks `tree.body` (module-top statements only) — NOT `ast.walk` — so local function-body imports that Plan 05 will add do NOT trigger the assertion
- Checks both `ast.ImportFrom` (e.g. `from sizing_engine import ...`) and `ast.Import` (e.g. `import sizing_engine`)
- Assertion message names C-2 + REVIEWS M-2 + Phase 15 D-01 for future revisers
- GREEN at Wave 0: `dashboard.py` has zero `sizing_engine` import statements (only comments referencing the name)

`pytest tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_module_top_sizing_engine_import -x -q` → 1 passed ✓

## Skeleton Classes Added (Tasks 3 + 4)

### tests/test_sizing_engine.py — TestDetectDrift
12 methods matching VALIDATION.md exactly:
`test_drift_long_vs_flat`, `test_drift_short_vs_flat`, `test_reversal_long_vs_short`, `test_reversal_short_vs_long`, `test_no_event_when_position_flat`, `test_no_event_when_signal_missing`, `test_no_event_when_signal_dict_signal_is_none`, `test_signal_int_shape_compat`, `test_drift_event_message_long_vs_flat_exact`, `test_drift_event_message_reversal_long_to_short_exact`, `test_two_instruments_both_drift`, `test_returns_empty_list_when_no_positions`
→ 12 skipped | Plan 02 populates

### tests/test_state_manager.py — TestClearWarningsBySource
5 methods: `test_removes_matching_source`, `test_leaves_other_sources_intact`, `test_idempotent_on_no_match`, `test_returns_same_state_reference`, `test_handles_missing_warnings_key`
→ 5 skipped | Plan 03 populates

### tests/test_dashboard.py — TestRenderCalculatorRow + TestRenderDriftBanner + TestBannerStackOrder
- TestRenderCalculatorRow: 10 methods (CALC-01/02/04 + REVIEWS H-1 `test_pyramid_section_includes_new_stop_after_add`)
- TestRenderDriftBanner: 5 methods (SENTINEL-01/02)
- **TestBannerStackOrder (NEW per REVIEWS H-2):** 3 methods asserting dashboard banner hierarchy (corruption > stale > drift ordering + drift banner placement before positions heading)
→ 18 skipped | Plan 05 populates

### tests/test_web_dashboard.py — TestForwardStopFragment + TestSideBySideStopDisplay + TestTradesDriftLifecycle
- TestForwardStopFragment: 10 methods (CALC-03 + REVIEWS L-2 `test_forward_stop_fragment_requires_auth_header`)
- TestSideBySideStopDisplay: 3 methods (D-10)
- **TestTradesDriftLifecycle (NEW per REVIEWS H-4):** 3 methods covering open/close/modify drift recompute lifecycle
→ 16 skipped | Plans 05/06 populate

### tests/test_notifier.py — TestDriftBanner + TestBannerStackOrder
- TestDriftBanner: 7 methods (SENTINEL-03 + D-03/D-12 + inline-CSS border color)
- TestBannerStackOrder: 3 methods (D-13 hierarchy: corruption > stale > drift)
→ 10 skipped | Plan 07 populates

### tests/test_main.py — TestDriftWarningLifecycle
4 methods: `test_drift_cleared_then_recomputed`, `test_w3_invariant_preserved`, `test_drift_warnings_present_in_dispatched_state`, `test_no_drift_warning_when_signals_match_positions`
→ 4 skipped | Plan 04 populates (REVIEWS M-1: no skip-test escape hatches; all 4 MUST be green after Plan 04)

## Test Count Delta

- **New skipped:** 65 (12 + 5 + 18 + 16 + 10 + 4)
- **New green:** 1 (`test_dashboard_no_module_top_sizing_engine_import`)
- **New failed:** 0
- **Pre-existing failures:** 16 tests in `tests/test_main.py` fail due to weekend-skip behavior (today is Sunday 2026-04-26); these are pre-existing and out of scope for this plan (confirmed via `git stash` before/after comparison)

`pytest tests/test_signal_engine.py::TestDeterminism -x -q` → 45 passed ✓
`pytest tests/test_signal_engine.py -x -q` → 109 passed ✓

## Deviations from Plan

None — plan executed exactly as written. All 4 tasks completed in sequence. The REVIEWS H-2 (TestBannerStackOrder dashboard) and REVIEWS H-4 (TestTradesDriftLifecycle) classes were included as specified in the plan's critical invariants.

## Known Stubs

None. This plan only adds test skeleton files; no production code was modified. All new test methods use `pytest.skip()` placeholders by design — this is the intended Wave 0 scaffolding pattern.

## Threat Flags

None. No new production code, no new network endpoints, no new file access patterns, no schema changes. The only code added is test infrastructure (pytest skip stubs + one AST guard test).

## Self-Check

Files created/modified:
- FOUND: tests/test_signal_engine.py
- FOUND: tests/test_sizing_engine.py
- FOUND: tests/test_state_manager.py
- FOUND: tests/test_dashboard.py
- FOUND: tests/test_web_dashboard.py
- FOUND: tests/test_notifier.py
- FOUND: tests/test_main.py

Commits verified:
- FOUND: 8c86a4b (chore — FORBIDDEN_MODULES_DASHBOARD)
- FOUND: e74c8a3 (test — AST guard)
- FOUND: 11baf1c (test — TestDetectDrift + TestClearWarningsBySource)
- FOUND: 57f4628 (test — 9 skeleton classes across 4 files)

## Self-Check: PASSED
