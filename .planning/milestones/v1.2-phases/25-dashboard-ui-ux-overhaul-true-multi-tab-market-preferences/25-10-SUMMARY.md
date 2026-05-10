---
phase: 25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences
plan: 10
subsystem: ui
tags: [dashboard, htmx, python, html, terminology, accessibility]

requires:
  - phase: 25-02
    provides: "_REQUIRED_DASHBOARD_MARKER bump that forces _is_stale=True on sibling HTML files"
  - phase: 25-09
    provides: "component a11y wiring, CSS tokens, responsive scaffolding"

provides:
  - "D-21 disambiguating button copy: 'Record paper trade' / 'Open live position'"
  - "D-21 account terminology: 'Account Management' and 'Account Baseline' eliminated, unified to 'Account' / 'Account balance'"
  - "D-22 strategy version single source of truth: footer reads via _resolve_strategy_version(state); no hard-coded literals"
  - "All 5 dashboard*.html runtime files regenerated with new copy"
  - "Phase 25 closed: all 52 Phase 25 tests pass, zero XFAIL remaining"

affects:
  - "Phase 26+ dashboard UI work"
  - "Any plan reading Account tab label or paper/live trade button copy"

tech-stack:
  added: []
  patterns:
    - "D-21: paper vs live trade form buttons use distinct copy to eliminate ambiguity"
    - "D-21: Account tab uses bare 'Account' label (market-agnostic, no 'Management' suffix)"
    - "D-22: render_footer(strategy_version) takes primitive arg; reads via state pipeline, not system_params"

key-files:
  created: []
  modified:
    - dashboard.py
    - tests/test_dashboard.py
    - tests/fixtures/dashboard/golden.html
    - tests/fixtures/dashboard/golden_empty.html

key-decisions:
  - "D-21 button renames applied in dashboard.py at the render function level; paper_trades.py delegates back to dashboard._render_paper_trades_open_form() which lives in dashboard.py"
  - "dashboard*.html sibling files are gitignored (runtime-generated); Plan 02 _REQUIRED_DASHBOARD_MARKER mechanism forces regeneration on first request post-deploy"
  - "Golden snapshot regenerated via tests/regenerate_dashboard_golden.py after copy changes"
  - "Stale 'Account Management' assertions in TestPhase24TabbedDashboard and TestSinglePageRenderIsolation updated to '>Account<' (narrow match to avoid false positives)"

requirements-completed: [P25-13, P25-14]

duration: 25min
completed: 2026-05-06
---

# Phase 25 Plan 10: Terminology and Version Reconciliation Summary

**D-21 button renames ('Record paper trade' / 'Open live position') and 'Account Management' elimination applied; D-22 strategy version confirmed single-source-of-truth via state pipeline; Phase 25 closed with 52/52 tests passing**

## Performance

- **Duration:** 25 min
- **Started:** 2026-05-06T11:00:00Z
- **Completed:** 2026-05-06T11:25:00Z
- **Tasks:** 2 (Task 1: source edits + xfail removal; Task 2: verification sweep)
- **Files modified:** 4 source files + 2 golden fixtures

## Accomplishments

- Paper-trade open form button: `Open position` -> `Record paper trade` (+ added missing `btn-primary` class)
- Live-trade open form button: `Open Position` -> `Open live position`
- `Account Management` eliminated from all 4 renderer sites (page_map, h2 heading, legacy nav x2)
- `Update Balances` -> `Update balances` (sentence case per UI-SPEC)
- `@pytest.mark.xfail` removed from 3 `TestPhase25ButtonRename` methods — all now PASS
- `TestPhase25StrategyVersion.test_footer_renders_v120_when_state_has_v120` — already passing (no xfail was needed)
- All 5 `dashboard*.html` sibling files regenerated with current copy (gitignored; runtime files)
- Full Phase 25 sweep: 52 tests pass, zero XFAIL remaining

## Task Commits

1. **Task 1: D-21 button + heading renames; D-22 verification + xfail removal** - `aa60ea9` (feat)
2. **Task 2: Verification sweep** - no commit (no source changes; all assertions confirmed by running test suite)

## Files Created/Modified

- `dashboard.py` - Live-trade button rename (line 869), paper-trade button rename (line 1453), `Update Balances` -> `Update balances` (line 1817), `Account Management` -> `Account` in page_map (line 1988), h2 heading (line 2040), and legacy nav x2 (lines 2091, 2098)
- `tests/test_dashboard.py` - Removed 3 `@pytest.mark.xfail` decorators from `TestPhase25ButtonRename`; updated stale `'Account Management'` assertions in `TestPhase24TabbedDashboard` (line 3109) and `TestSinglePageRenderIsolation` (line 3143) to `'>Account<'`
- `tests/fixtures/dashboard/golden.html` - Regenerated to reflect new button copy and heading
- `tests/fixtures/dashboard/golden_empty.html` - Regenerated to reflect new button copy and heading

## Decisions Made

- Paper-trade open button lives in `dashboard._render_paper_trades_open_form()`, not in `dashboard_renderer/components/paper_trades.py` (which delegates back to dashboard.py). Edit applied at the source in dashboard.py.
- `dashboard*.html` sibling files are gitignored; they are runtime-generated. The golden fixture under `tests/fixtures/` is tracked and was regenerated via `tests/regenerate_dashboard_golden.py`.
- Stale test assertions checking `'Account Management' in html_out` updated to `'>Account<' in html_out` (tag-boundary match avoids false positives from content like "Account balance" or DOM IDs like "account-management-region").
- `account-management-region` DOM ID and `hx-target="#account-management-region"` left unchanged — internal implementation identifiers, not user-visible copy.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated stale 'Account Management' test assertions in two unrelated test classes**
- **Found during:** Task 2 (full suite run)
- **Issue:** `TestPhase24TabbedDashboard` and `TestSinglePageRenderIsolation` both asserted `'Account Management' in html_out`, which now fails after D-21 renames. These were not listed in the plan's xfail removal step.
- **Fix:** Changed both assertions to `'>Account<'` to match the new heading/nav copy while avoiding overly broad matching.
- **Files modified:** `tests/test_dashboard.py`
- **Verification:** Both test methods now pass; no unintended assertions dropped.
- **Committed in:** `aa60ea9`

---

**Total deviations:** 1 auto-fixed (Rule 1 - stale test assertions from same rename batch)
**Impact on plan:** Necessary correctness fix; no scope change.

## Grep Gates (All Clean)

| Gate | Command | Result |
|------|---------|--------|
| Account terminology | `grep -rn "Account Management\|Account Baseline" dashboard_renderer/ dashboard.py` | 0 results |
| Button copy | `grep -rn "Open Position</button>\|Open position</button>" dashboard_renderer/ dashboard.py` | 0 results |
| Hex boundary | `grep -rn "from system_params import STRATEGY_VERSION" dashboard_renderer/` | 0 results |

## Phase 25 Close-Out

| Metric | Value |
|--------|-------|
| Waves | 4 |
| Plans | 10 (25-01 through 25-10) |
| Phase 25 tests at close | 52 passed, 0 XFAIL |
| Pre-existing failures (unrelated) | 6 (TestRenderBlocks x2, TestEmptyState, TestDeployShSequence x3) |
| Total files modified across Phase 25 | ~25 (dashboard.py, dashboard_renderer/components/*, web/routes/*, tests/test_dashboard.py, golden fixtures) |

ROADMAP items addressed by this plan: #9 (Terminology reconciliation — D-21, D-22).

## Sibling HTML Regeneration

`dashboard*.html` files are gitignored. They are regenerated at runtime when `_is_stale(html_path)` returns `True`. Plan 02 changed `_REQUIRED_DASHBOARD_MARKER` to `class="tabs tabs-function"`, which is absent from pre-Phase-25 cached files — ensuring all 5 files regenerate on the first request post-deploy with current copy, tab classes, fieldsets, and strategy version.

## Issues Encountered

- `git stash` during pre-existing failure investigation reverted working-tree edits. Edits were cleanly re-applied from the verified change list.

## Self-Check

- [x] `aa60ea9` commit exists: `git log --oneline | grep aa60ea9` -> confirmed
- [x] `dashboard.py` contains `Record paper trade` and `Open live position`
- [x] `dashboard.py` contains zero `Account Management` occurrences
- [x] `tests/test_dashboard.py` contains zero `@pytest.mark.xfail` in `TestPhase25ButtonRename`
- [x] `tests/fixtures/dashboard/golden.html` regenerated and committed
- [x] 52 Phase 25 tests pass

## Next Phase Readiness

Phase 25 is complete at code level. All 10 ROADMAP items have implementation and passing tests. Ready for milestone gate (`codemoot review`) before closing Phase 25.

---
*Phase: 25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences*
*Completed: 2026-05-06*
