---
phase: 29
plan: 02
plan_id: 29-02-UAT-26-1-COLDSTART-JS-FIX
subsystem: dashboard_legacy
tags: [bugfix, javascript, equity-chart, uat, regression-test]
dependency_graph:
  requires: []
  provides: [balanced-equitychart-js, uat-pageerror-regression]
  affects: [dashboard_legacy/section_renderers.py, tests/uat/test_uat_26_coldstart.py]
tech_stack:
  added: []
  patterns: [playwright-pageerror-collection, dashboard-golden-refresh]
key_files:
  created: []
  modified:
    - dashboard_legacy/section_renderers.py
    - tests/uat/test_uat_26_coldstart.py
    - tests/fixtures/dashboard/golden.html
    - tests/fixtures/dashboard_canonical.html
decisions:
  - "Fixed y-axis brace by removing one extra } on the ticks-close line (line 219); mirrors the correctly-structured x-axis above it"
  - "Added test_no_pageerror_on_coldstart targeting /markets/SPI200/dashboard with networkidle wait; leverages existing conftest.py page fixture and auth wiring"
  - "Refreshed golden.html and dashboard_canonical.html to reflect corrected JS output (1 byte shorter each)"
metrics:
  duration: ~15min
  completed_date: "2026-05-10"
  tasks_completed: 2
  files_modified: 4
---

# Phase 29 Plan 02: UAT-26-1 Cold-start JS Brace Fix Summary

**One-liner:** Rebalance equityChart y-axis brace in section_renderers.py line 219, eliminating the "missing ) after argument list" pageerror on every cold-start dashboard load.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix equityChart y-axis brace structure | 73a8bc9 | dashboard_legacy/section_renderers.py |
| 2 | UAT regression test + golden refresh | 954a4a9 | tests/uat/test_uat_26_coldstart.py, tests/fixtures/dashboard/golden.html, tests/fixtures/dashboard_canonical.html |

## What Was Done

### Task 1 — Brace fix

`dashboard_legacy/section_renderers.py` line 219 had `}},` in a plain (non-f) string:

```
f'            y: {{ ticks: {{ color: "{_COLOR_TEXT_MUTED}",\n'
'                         callback: (v) => "$" + v.toLocaleString() }},\n'  # BUG
f'               grid: {{ color: "{_COLOR_BORDER}" }} }}\n'
```

The `}}` on line 219 is a regular Python string (not an f-string), so it passes through as literal `}}` — two closing braces. This prematurely closed both `ticks` AND `y` after the ticks block, leaving `grid: { ... }` as a stray sibling with one unmatched `}` at scales level. Rendered JS:

```js
// BROKEN — y closes after ticks, grid is orphaned
y: { ticks: { color: "...", callback: ... }},
   grid: { color: "..." } }
```

Fix: changed `}},` → `},` on line 219. The outer `y` block is already properly closed by the `}} }}` → `} }` at the end of line 220 (the f-string). Resulting JS:

```js
// FIXED — mirrors x-axis structure
y: { ticks: { color: "...", callback: ... },
     grid: { color: "..." } }
```

Brace balance verified: `{` count == `}` count == 17 in rendered JS block.

### Task 2 — Regression test + golden refresh

Added `test_no_pageerror_on_coldstart` to `tests/uat/test_uat_26_coldstart.py`:
- Collects `pageerror` events via `page.on('pageerror', errors.append)`
- Navigates to `/markets/SPI200/dashboard` (the equity-chart route)
- Waits for `networkidle` so Chart.js initialisation can complete
- Asserts `errors == []` with descriptive failure message
- Decorated implicitly by module-level `pytestmark = pytest.mark.uat`

The brace fix also changed the byte output of render_dashboard by 1 byte (one fewer `}` in JS block). Two golden snapshot tests in the default suite (`test_golden_snapshot_matches_committed`, `test_dashboard_html_output_byte_identical`) caught this as expected failures. Refreshed:
- `tests/fixtures/dashboard/golden.html` via `tests/regenerate_dashboard_golden.py`
- `tests/fixtures/dashboard_canonical.html` via inline Python (prepend current HEAD SHA comment + render)

## Verification

### Automated (default suite)
```
2031 passed, 13 deselected in 154.89s
```

### Brace balance check
```python
balanced 17  # {count == }count in rendered JS block
```

### Acceptance criteria
- `wc -l dashboard_legacy/section_renderers.py` → 233 (≤500)
- `grep -nE "y: \{ ticks: \{"` → matches line 218
- `python -c "import ast; ast.parse(...)"` → syntax OK
- `wc -l tests/uat/test_uat_26_coldstart.py` → 69 (≤500)
- `grep -q "test_no_pageerror_on_coldstart"` → OK
- `grep -q "pageerror"` → OK
- `grep -q "@pytest.mark.uat"` → OK (module-level pytestmark)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Golden snapshot tests broke after brace fix**
- **Found during:** Task 2 (post-fix full suite run)
- **Issue:** `test_golden_snapshot_matches_committed` and `test_dashboard_html_output_byte_identical` compare rendered HTML byte-for-byte against committed goldens. The 1-byte change in JS output caused both to fail.
- **Fix:** Ran `tests/regenerate_dashboard_golden.py` to refresh `golden.html`; regenerated `dashboard_canonical.html` inline (same pattern — prepend SHA header + current render output).
- **Files modified:** tests/fixtures/dashboard/golden.html, tests/fixtures/dashboard_canonical.html
- **Commit:** 954a4a9 (included alongside UAT test)

Note: The function name in the acceptance criteria (`_render_equity_chart_section`) did not exist — the actual function is `_render_equity_chart_container`. AC verification adapted to use the correct name. Bug fixed inline.

## Known Stubs

None. The brace fix is a complete correctness fix; the regression test targets the live production droplet (UAT-gated).

## Threat Flags

None. This plan closes T-29-02-01 (DoS via inline JS syntax error). T-29-02-02 (XSS re-introduction) remains accepted per plan threat register.

## Self-Check: PASSED

- [x] dashboard_legacy/section_renderers.py modified (brace fix)
- [x] tests/uat/test_uat_26_coldstart.py modified (new test method)
- [x] tests/fixtures/dashboard/golden.html refreshed
- [x] tests/fixtures/dashboard_canonical.html refreshed
- [x] Commit 73a8bc9 exists (Task 1 brace fix)
- [x] Commit 954a4a9 exists (Task 2 regression test + goldens)
- [x] 2031 tests passed, 0 failed in default suite
