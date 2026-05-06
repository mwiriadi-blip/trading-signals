---
phase: 25
plan: "07"
subsystem: dashboard-empty-state-collapse
tags: [empty-state, d-09, d-10, d-11, first-run, equity-chart, stats-bar, wave-3]
dependency_graph:
  requires: [25-01, 25-02]
  provides:
    - "render_signal_cards gates on state['last_run'] is None — onboarding card when None, full trace tables otherwise"
    - "_distinct_equity_tuples(equity_history) -> list in dashboard.py — dedupes (date,equity) tuples"
    - "_render_equity_chart_container hidden when distinct tuples < 5"
    - "paper_trades_region omits stats-bar from DOM when closed_paper + closed_live < 1"
  affects: []
tech_stack:
  added: []
  patterns:
    - "Gate rendering on state field rather than CSS display:none (zero DOM, not hidden)"
    - "Deduplicate by (date, equity) key set before threshold check"
key_files:
  created: []
  modified:
    - dashboard_renderer/components/signals.py
    - dashboard_renderer/components/paper_trades.py
    - dashboard.py
    - tests/test_dashboard.py
decisions:
  - "D-09 gate placed in render_signal_cards (signals.py), not in _render_trace_panels — single card emitted once per page, not per instrument"
  - "D-10 gate placed in render_paper_trades_region (paper_trades.py) — closed_paper from paper_trades status field + closed_live from closed_trades list length"
  - "D-11 helper _distinct_equity_tuples added immediately above _render_equity_chart_container in dashboard.py — locality of behavior"
  - "Existing empty-state branch (empty list → no equity) superseded by distinct-tuple < 5 gate with locked copy from UI-SPEC"
metrics:
  duration: "~15 minutes"
  completed: "2026-05-05"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 4
---

# Phase 25 Plan 07: Empty State Collapse Summary

First-run empty-state collapse per D-09/D-10/D-11. Hides 11-table trace panels behind one onboarding card on first install; hides stats bar until closed trades exist; hides equity chart until >=5 distinct (date, equity) points.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Gate trace panels (D-09) and stats bar (D-10) | 70dcf64 | signals.py, paper_trades.py, test_dashboard.py |
| 2 | Gate equity chart (D-11) with distinct tuple count | 6792e71 | dashboard.py, test_dashboard.py |

## Implementation Notes

### D-09: Trace panel gate (signals.py)

Gate placed at top of `render_signal_cards` in `dashboard_renderer/components/signals.py`. When `state.get('last_run') is None`, the entire signal section (FLAT/LONG/SHORT cards + trace tables) collapses to a single `<section class="onboarding-card">` with the locked copy from UI-SPEC. Once `last_run` is set, full rendering resumes.

The single-gate-in-parent approach (rather than per-instrument in `_render_trace_panels`) ensures exactly one onboarding card is emitted per page, not one per instrument.

### D-10: Stats bar gate (paper_trades.py)

Gate placed in `render_paper_trades_region` in `dashboard_renderer/components/paper_trades.py`. Counts closed paper trades (status == 'closed') plus length of `closed_trades` list. If combined total < 1, `stats_html` is set to `''` — the `<aside class="stats-bar">` is absent from the DOM entirely (not `display:none`).

### D-11: Equity chart gate (dashboard.py)

Added `_distinct_equity_tuples(equity_history)` helper immediately above `_render_equity_chart_container`. Deduplicates by `(row['date'], float(row['equity']))` key — three identical points produce one distinct entry. `_render_equity_chart_container` now calls this helper first; if `len(distinct) < 5`, returns the UI-SPEC locked empty-state copy. When >= 5, the chart renders from the deduped `distinct` list (not raw `equity_history`).

The previous empty-state branch (checking `not equity_history`) is superseded — the distinct-tuple < 5 check covers the empty-list case (0 < 5) with the correct locked copy.

## Tests

All 7 tests pass across the three test classes:

- `TestPhase25FirstRun` (3 tests) — last_run=None renders onboarding card; last_run set renders trace tables
- `TestPhase25StatsBar` (2 tests) — zero trades omits stats bar; one closed paper trade renders stats bar
- `TestPhase25Equity` (2 tests) — three identical points hides chart; five distinct points renders chart

xfail decorators removed from all 4 previously-gated tests.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

None — pure render-side gating with no new external input surface. Locked copy strings contain no interpolation.

## Self-Check: PASSED

- `dashboard_renderer/components/signals.py` — modified, onboarding gate present
- `dashboard_renderer/components/paper_trades.py` — modified, stats-bar gate present
- `dashboard.py` — modified, `_distinct_equity_tuples` present
- Commits 70dcf64 and 6792e71 exist in git log
