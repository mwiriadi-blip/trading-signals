---
phase: 29
plan: 11
plan_id: 29-11-UAT-17-1-ATR-SEED-EXPOSURE
subsystem: signal-engine, trace-panel
tags: [atr-seed, trace, uat-closure, phase-28-fail]
status: complete
created: 2026-05-10

dependency_graph:
  requires: []
  provides:
    - signal_engine.atr_seed_for_window
    - daily_run.py atr_seed persistence
    - dashboard_legacy/trace_panels.py ATR seed row
    - tests/test_trace_atr_seed.py
  affects:
    - signal_engine.py
    - daily_run.py
    - dashboard_legacy/trace_panels.py

key_files:
  created:
    - tests/test_trace_atr_seed.py
  modified:
    - signal_engine.py
    - daily_run.py
    - dashboard_legacy/trace_panels.py
    - tests/fixtures/dashboard/golden.html
    - tests/fixtures/dashboard/golden_empty.html
    - tests/fixtures/dashboard_canonical.html

decisions:
  - "atr_seed_for_window re-uses _wilder_smooth for bit-identical seed — no tolerance fudging"
  - "Stale-row fallback matches bb780af discipline (same UX copy)"
  - "Column-name normalisation inside atr_seed_for_window (title-case) keeps the public API flexible without touching _true_range internals"
  - "Dashboard golden snapshots regenerated via existing regen scripts + manual render for dashboard_canonical.html"

metrics:
  duration_minutes: 30
  completed_date: 2026-05-10
  tasks_completed: 2
  files_created: 1
  files_modified: 3
---

# Phase 29 Plan 11: ATR Seed Exposure

## One-liner

Expose engine-persisted Wilder ATR seed in trace panel; hand-recalc convergence test asserts <1e-6 against synthetic fixture. Closes UAT-17-1 (Phase 28 FAIL).

## What was built

### signal_engine.py
- `atr_seed_for_window(history_df, window_start_index, period=14) -> float` helper
- Re-uses `_wilder_smooth` for bit-identical result; returns NaN if window starts within warmup
- Normalises column names to title-case so callers may pass either lowercase ('high') or title-case ('High') DataFrames

### daily_run.py
- Signal-row write site now persists `sig['atr_seed']` alongside `indicator_scalars` and `vote_params`
- `_window_start_index = len(df) - len(ohlc_window)` derives the index from the already-built ohlc_window list

### dashboard_legacy/trace_panels.py
- `_render_trace_panels` extracts `atr_seed` from sig_dict and threads through to `_render_trace_indicators`
- `_render_trace_indicators` signature extended with `atr_seed: float | None = None`
- Renders "ATR seed (bar -1)" row with 6dp value and tooltip before the main indicator rows
- Legacy-row fallback: `<em>(stale row — refresh after next 08:00 cycle)</em>`

### tests/test_trace_atr_seed.py
- 4 tests: seed persistence, hand-recalc <1e-6 convergence, stale-row fallback, panel renders seed value

### Golden snapshots
- `tests/fixtures/dashboard/golden.html` and `golden_empty.html` regenerated via `tests/regenerate_dashboard_golden.py`
- `tests/fixtures/dashboard_canonical.html` regenerated via inline render (preserving SHA-header comment line)

## Self-Check

- [x] `def atr_seed_for_window` present in signal_engine.py
- [x] `atr_seed` present in daily_run.py write site
- [x] `atr_seed` present in dashboard_legacy/trace_panels.py
- [x] `ATR seed` label present in trace_panels.py
- [x] tests/test_trace_atr_seed.py created with 4 tests
- [x] `test_handcalc_converges_to_displayed_atr_within_1e6` present
- [x] All tests pass: `.venv/bin/pytest -q` green (2052 passed)
- [x] STATE.md and ROADMAP.md not modified

## Self-Check: PASSED
