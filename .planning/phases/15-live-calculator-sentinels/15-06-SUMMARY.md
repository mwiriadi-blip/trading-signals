---
phase: 15
plan: 06
subsystem: web
tags:
  - phase15
  - web
  - htmx-fragment
  - forward-look
  - drift-sentinel

dependency_graph:
  requires:
    - 15-02  # detect_drift shipped
    - 15-03  # clear_warnings_by_source shipped
    - 15-05  # side-by-side stop cell in dashboard.py
  provides:
    - forward-stop fragment GET endpoint (CALC-03)
    - drift recompute in all 3 trade mutators (D-02)
    - 16 passing tests (forward-stop + side-by-side + drift lifecycle)
  affects:
    - web/routes/dashboard.py
    - web/routes/trades.py
    - tests/test_web_dashboard.py

tech_stack:
  added: []
  patterns:
    - FastAPI Request injection for query_params in fragment handler
    - LOCAL imports inside _apply closures for hex boundary compliance

key_files:
  created: []
  modified:
    - web/routes/dashboard.py
    - web/routes/trades.py
    - tests/test_web_dashboard.py

decisions:
  - set_state() used inside tests to inject AUDUSD SHORT positions and manual_stop (no new conftest fixture)
  - forward-stop branch placed BEFORE dashboard.html file-read path (does not need on-disk file)
  - AUDUSD used for open-drift test (not SPI200) to avoid position-already-exists conflict

metrics:
  duration: ~20min
  completed: 2026-04-26
  tasks: 3
  files: 3
---

# Phase 15 Plan 06: Forward-Stop Fragment + Drift Lifecycle Summary

Forward-look HTMX fragment endpoint, drift recompute in all trade mutators, and 16 new passing tests closing CALC-03, SENTINEL-01/02 (web layer), REVIEWS L-1, L-2, H-4.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Forward-stop fragment + drift recompute in mutators | 474ab19 | web/routes/dashboard.py, web/routes/trades.py |
| 2 | TestForwardStopFragment + TestSideBySideStopDisplay (13 tests) | f86c459 | tests/test_web_dashboard.py |
| 3 | TestTradesDriftLifecycle (3 tests, REVIEWS H-4) | c1ef70d | tests/test_web_dashboard.py |

## Artifact Details

### web/routes/dashboard.py — forward-stop branch

- **Line 120:** `if fragment == 'forward-stop':` — EXACT match (REVIEWS L-1 satisfied)
- Branch inserted BEFORE the dashboard.html file-read path (does not require on-disk file)
- `Request` parameter added to `get_dashboard` for `request.query_params` access
- Synthesizes position: LONG uses `max(peak, z)`, SHORT uses `min(trough, z)`
- Calls `get_trailing_stop(synth, 0.0, 0.0)` — honors `manual_stop` (D-09 precedence)
- Degenerate Z (empty, `<=0`, non-finite, non-numeric) returns `<span ...>—</span>`, never 4xx
- Missing instrument position returns em-dash span
- All sizing_engine + state_manager + dashboard imports LOCAL inside the branch (C-2)
- Confirmation: `grep -c "fragment.startswith('forward-stop')" web/routes/dashboard.py` returns 0

### web/routes/trades.py — drift recompute blocks

Three identical drift blocks inserted AFTER position mutation in each `_apply` closure:

| Mutator | Location | Lines |
|---------|----------|-------|
| open_trade `_apply` | After fresh-open position set | 531–540 |
| close_trade `_apply` | After `record_trade(state, trade)` | 607–616 |
| modify_trade `_apply` | After `pos['pyramid_level'] = 0` | 654–663 |

Each block:
```
clear_warnings_by_source(state, 'drift')
for ev in detect_drift(state.get('positions', {}), state.get('signals', {})):
  append_warning(state, source='drift', message=ev.message)
```

All imports LOCAL (C-2). `append_warning` is the sole writer to `state['warnings']` (TRADE-06 / TestSoleWriterInvariant still green).

## Test Pass Counts

| Class | Count | Notes |
|-------|-------|-------|
| TestForwardStopFragment | 10 | Includes REVIEWS L-2 auth-header regression |
| TestSideBySideStopDisplay | 3 | D-10 side-by-side markup |
| TestTradesDriftLifecycle | 3 | REVIEWS H-4 — open/close/modify drift lifecycle |
| **Total** | **16** | 0 skips, 0 failures |

## Key Decisions and Fixture Choices

**Manual-stop test fixture:** `test_manual_stop_overrides_z_input` uses `set_state()` to inject `manual_stop=7700.0` onto the SPI200 LONG position inside the test body. No new conftest fixture (`client_with_state_v3_with_manual_stop`) was added — `set_state()` already provides this capability.

**AUDUSD SHORT position tests:** `test_short_z_below_trough_updates_w`, `test_short_z_above_trough_w_unchanged`, and `test_forward_stop_matches_sizing_engine_bit_for_bit` inject an AUDUSD SHORT position via `set_state()` before the request.

**Drift open test instrument choice:** `test_open_trade_creates_drift_when_signal_mismatch` opens AUDUSD (not SPI200) to avoid the D-01 "position already exists" conflict — the default `client_with_state_v3` state has SPI200 LONG already present.

**Signal injection for drift tests:** Default state's `signals['AUDUSD']` is `{}` (empty, no `signal` key). The open and modify drift tests inject proper signal dicts (`{'signal': LONG_INT, 'last_scalars': {'atr': ...}, ...}`) via `set_state()`.

## REVIEWS Compliance

| Review | Status |
|--------|--------|
| L-1: exact `fragment == 'forward-stop'` match | `grep -c "fragment.startswith" web/routes/dashboard.py` returns 0 |
| L-2: auth-header regression test | `test_forward_stop_fragment_requires_auth_header` asserts 401 with empty headers |
| H-4: drift lifecycle tests | 3 tests cover open/close/modify; all green |

## Deviations from Plan

None — plan executed exactly as written. The `set_state()` fixture approach for `test_manual_stop_overrides_z_input` was the explicitly documented alternative in the plan ("inject the manual_stop via direct save_state mutation inside the test before the GET").

## Pre-existing Failures (not made worse)

- `tests/test_dashboard.py::TestEmptyState::test_empty_state_matches_committed` — golden file mismatch, pre-existed Phase 15-05
- Multiple `tests/test_main.py` failures — weekend-skip-related (today=Saturday 2026-04-26), pre-existing

## Self-Check: PASSED

- `474ab19` exists: `git log --oneline | grep 474ab19` ✓
- `f86c459` exists: `git log --oneline | grep f86c459` ✓
- `c1ef70d` exists: `git log --oneline | grep c1ef70d` ✓
- `grep -c "fragment == 'forward-stop'" web/routes/dashboard.py` returns 1 ✓
- `grep -c "fragment.startswith('forward-stop')" web/routes/dashboard.py` returns 0 ✓
- `grep -E "^from sizing_engine|^from state_manager" web/routes/dashboard.py web/routes/trades.py | wc -l` returns 0 ✓
- All 16 tests pass: `pytest tests/test_web_dashboard.py::TestForwardStopFragment tests/test_web_dashboard.py::TestSideBySideStopDisplay tests/test_web_dashboard.py::TestTradesDriftLifecycle -q` exits 0 ✓
