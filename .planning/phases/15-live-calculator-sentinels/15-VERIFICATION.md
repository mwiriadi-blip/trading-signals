---
phase: 15-live-calculator-sentinels
verified: 2026-04-26T10:00:00+08:00
re_verified: 2026-04-26T12:30:00+08:00
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/6 must-haves verified
  gaps_closed:
    - truth: "Entry-target row wired into render path (CALC-02)"
      closure_commit: "f591197"
      closure_evidence: "dashboard.py::_render_positions_table now has a second loop that calls _render_entry_target_row(state, state_key) for each FLAT-position instrument and wraps non-empty output in <tbody id=\"entry-target-{state_key_esc}\">"
    - truth: "Pyramid level reads correct field (CALC-04)"
      closure_commit: "f591197"
      closure_evidence: "dashboard.py line 1214: current_level = int(pos.get('pyramid_level', pos.get('current_level', 0))) — dual-key fallback wrapped in try/except (TypeError, ValueError) for defensive int conversion"
    - truth: "Golden snapshot byte-matches committed golden.html"
      closure_commit: "f591197"
      closure_evidence: "tests/regenerate_dashboard_golden.py re-run after the H-1/H-2/M-3/L-3 fixes landed; golden.html and golden_empty.html updated; TestGoldenSnapshot + TestEmptyState pass."
  gaps_remaining: []
  regressions: []
gaps: []
---

# Phase 15: Live Calculator + Sentinels Verification Report

**Phase Goal:** Turn the dashboard from a passive log into an active decision-support tool — surface the current trailing stop, next pyramid-add price, forward-looking peak stop, and entry target from `sizing_engine`; flag drift when `state.positions` disagrees with today's signal on dashboard AND in the daily email.
**Verified:** 2026-04-26T10:00:00+08:00 (initial: gaps_found)
**Re-verified:** 2026-04-26T12:30:00+08:00 (passed)
**Status:** passed (was gaps_found; all 3 gaps closed in commit `f591197` — entry-target wiring, pyramid_level dual-key fallback, golden regen)
**Re-verification:** Yes — closing 3 gaps from initial pass

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Per-instrument calc-row shows trail stop, distance $+%, next pyramid trigger price — from sizing_engine LOCAL imports | ✓ VERIFIED | `_render_calc_row` in dashboard.py (line 1186) imports `get_trailing_stop` locally (C-2), renders STOP/DIST/NEXT ADD/IF HIGH cells. All 10 TestRenderCalculatorRow tests pass. |
| 2 | FLAT position + LONG/SHORT signal → entry target row with calc_position_size contracts + initial trailing stop | ✗ FAILED | `_render_entry_target_row` defined (line 1366) and unit-tested but NEVER CALLED from `_render_positions_table` or any render path. The function is an orphaned helper. |
| 3 | Open position → forward-looking line "at current bar high Z, stop would rise to W" via get_trailing_stop on synth peak; bit-for-bit parity proven by test | ✓ VERIFIED | `web/routes/dashboard.py` fragment=forward-stop branch (lines 120-172) synthesizes peak/trough with Z input, calls `get_trailing_stop` locally. 10 TestForwardStopFragment tests pass including bit-for-bit parity test. |
| 4 | Pyramid section: "level N active; next add at price P (+Y×ATR_entry)" and "new stop after add: S" — REVIEWS H-1 fix | ✗ FAILED | `_render_calc_row` uses `pos.get('current_level', 0)` (line 1211) but real Position TypedDict uses `pyramid_level`. Level always shows 0/2 in production. Unit tests mask the bug by injecting `current_level` directly. |
| 5 | Position-vs-signal mismatch → amber drift banner (dashboard); opposite-direction → red reversal banner | ✓ VERIFIED | `_render_drift_banner` (line 1446) reads `state['warnings'][source='drift']`, uses `sentinel-drift` (amber) or `sentinel-reversal` (red). Inserted BEFORE positions table in `render_dashboard()` body composition (line 1930). TestBannerStackOrder confirms DOM ordering. |
| 6 | Same drift/reversal banner in daily email as critical; `_has_critical_banner` via 'drift' source key; regression test asserts body + subject `[!]` prefix | ✓ VERIFIED | `notifier._has_critical_banner` (line 564) returns True for source='drift'. Drift banner block in `_render_header_email` (lines 645-678). TestDriftBanner (10 tests), TestBannerStackOrder (3 tests) all pass. D-12 parity test passes. |

**Score:** 4/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sizing_engine.py` | `DriftEvent` dataclass + `detect_drift()` | ✓ VERIFIED | Lines 97-185. DriftEvent frozen+slots, detect_drift iterates SPI200/AUDUSD, returns drift/reversal events with D-14 message templates. |
| `state_manager.py` | `clear_warnings_by_source()` | ✓ VERIFIED | Lines 646-666. Mutates `state['warnings']` in-place, returns state for chaining. |
| `main.py` | Drift recompute block in `run_daily_check` | ✓ VERIFIED | Lines 1274-1285. Sequence: clear → detect → append_warning loop. No extra `mutate_state` call (W3 preserved). |
| `dashboard.py` | `_render_calc_row` wired into positions table | ✓ VERIFIED | Line 1536: `sub_row = _render_calc_row(state, state_key, pos)` called for every position. |
| `dashboard.py` | `_render_entry_target_row` wired into positions table | ✗ ORPHANED | Function defined (line 1366), tested in isolation, but zero call sites in production rendering code. |
| `dashboard.py` | `_render_drift_banner` wired in render_dashboard | ✓ VERIFIED | Line 1930: `+ _render_drift_banner(state)` before `_render_positions_table`. |
| `web/routes/dashboard.py` | forward-stop fragment handler | ✓ VERIFIED | Lines 120-172. Exact L-1 match, synth peak/trough update, `get_trailing_stop` LOCAL import. |
| `web/routes/trades.py` | drift recompute in open/close/modify mutators | ✓ VERIFIED | Lines 537-541, 613-617, 660-664. All three mutators clear → detect → append_warning. |
| `notifier.py` | `_has_critical_banner` extended with 'drift' source | ✓ VERIFIED | Line 564: `if w.get('source') == 'drift': return True`. |
| `notifier.py` | Drift banner in `_render_header_email` | ✓ VERIFIED | Lines 645-678. Amber/red border per has_reversal. Positioned before hero card per D-13. |
| `tests/fixtures/dashboard/golden.html` | Byte-matches current render output | ✗ STALE | Golden regenerated before UAT fix `name="z"` (6ad306e). Test FAILS: `TestGoldenSnapshot::test_golden_snapshot_matches_committed`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `dashboard._render_calc_row` | `sizing_engine.get_trailing_stop` | LOCAL import inside function body | ✓ WIRED | Line 1204: `from sizing_engine import get_trailing_stop  # LOCAL — C-2` |
| `dashboard._render_entry_target_row` | `sizing_engine.calc_position_size` | LOCAL import | ✓ WIRED (function) | Line 1406: import exists inside the function. But the function itself is never called. |
| `dashboard.render_dashboard` | `dashboard._render_drift_banner` | top-level body composition | ✓ WIRED | Line 1930 |
| `dashboard._render_positions_table` | `dashboard._render_calc_row` | function call during table render | ✓ WIRED | Line 1536 |
| `dashboard._render_positions_table` | `dashboard._render_entry_target_row` | function call for flat-position instruments | ✗ NOT_WIRED | No call site exists. Function is orphaned. |
| `web/routes/dashboard.py` | `sizing_engine.get_trailing_stop` | LOCAL import in fragment handler | ✓ WIRED | Line 125: `from sizing_engine import get_trailing_stop  # LOCAL — C-2` |
| `notifier._has_critical_banner` | `state['warnings'][source='drift']` | filter check | ✓ WIRED | Line 564 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `dashboard._render_calc_row` | `trail_stop` | `_compute_trail_stop_display(pos)` → `get_trailing_stop` | Yes — reads `pos['atr_entry']`, `pos['peak_price']` | ✓ FLOWING |
| `dashboard._render_calc_row` | `current_level` | `pos.get('current_level', 0)` | NO — TypedDict uses `pyramid_level`, not `current_level`. Always returns 0 for real positions. | ✗ DISCONNECTED |
| `dashboard._render_drift_banner` | `drift_warnings` | `state['warnings'][source='drift']` | Yes — populated by `detect_drift` via main.py or web/routes/trades.py | ✓ FLOWING |
| `web/routes/dashboard.py` forward-stop | `w` | `get_trailing_stop(synth, 0.0, 0.0)` | Yes — reads position from `load_state()`, synthesizes with Z input | ✓ FLOWING |
| `notifier._render_header_email` | `drift_warnings` | `state['warnings'][source='drift']` | Yes — same source as dashboard | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| detect_drift returns drift event for LONG position + FLAT signal | pytest TestDetectDrift (12 tests) | 12 passed | ✓ PASS |
| W3 invariant — mutate_state called exactly 2 times | pytest TestDriftWarningLifecycle::test_w3_invariant_preserved | 1 passed | ✓ PASS |
| Drift lifecycle — stale cleared, fresh appended | pytest TestDriftWarningLifecycle (4 tests) | 4 passed | ✓ PASS |
| Forward-stop fragment bit-parity | pytest TestForwardStopFragment::test_forward_stop_matches_sizing_engine_bit_for_bit | 1 passed | ✓ PASS |
| Golden snapshot byte-match | pytest TestGoldenSnapshot::test_golden_snapshot_matches_committed | FAILED | ✗ FAIL |
| M-2 AST guard: no module-top sizing_engine import in dashboard.py | pytest TestDeterminism::test_dashboard_no_module_top_sizing_engine_import | 1 passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CALC-01 | 15-05 | Per-instrument trail stop + distance on dashboard | ✓ SATISFIED | `_render_calc_row` STOP/DIST cells verified |
| CALC-02 | 15-05 | Entry target block for flat-position + directional signal | ✗ BLOCKED | `_render_entry_target_row` orphaned — never called from render path |
| CALC-03 | 15-06 | Forward-looking peak-stop calculator | ✓ SATISFIED | `web/routes/dashboard.py` fragment=forward-stop with bit-parity test |
| CALC-04 | 15-05 | Pyramid next-add price + new stop after add | ✗ BLOCKED | Pyramid level always reads 0 (wrong field name `current_level` vs `pyramid_level`); LEVEL and NEXT ADD cells are functionally wrong for pyramid_level > 0 |
| SENTINEL-01 | 15-02/15-04/15-05 | Amber drift banner on dashboard | ✓ SATISFIED | `_render_drift_banner` amber path verified |
| SENTINEL-02 | 15-02/15-04/15-05 | Red reversal banner on dashboard | ✓ SATISFIED | `_render_drift_banner` reversal path (`sentinel-reversal` class) verified |
| SENTINEL-03 | 15-07 | Drift banner in email as critical (reuses `_has_critical_banner` + `[!]` subject) | ✓ SATISFIED | `_has_critical_banner` extended, drift banner in `_render_header_email`, test asserts `[!]` |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `dashboard.py` | 1211 | `pos.get('current_level', 0)` — wrong field name for Position TypedDict | Blocker | Pyramid LEVEL cell always shows `level 0/2`; NEXT ADD always computed at level 0 formula; NEW STOP projected for wrong pyramid level |
| `tests/test_dashboard.py` | 1675,1701,1769+ | Fixtures inject `'current_level'` key instead of `'pyramid_level'` | Blocker | Masks the production bug — tests pass but real positions are broken |
| `tests/fixtures/dashboard/golden.html` | — | Stale golden — missing `name="z"` on forward-stop input | Blocker | `TestGoldenSnapshot::test_golden_snapshot_matches_committed` FAILS |

### Human Verification Required

None identified for automated portion. The following were noted as human-only in Phase 16 (UAT scenarios):

1. **Forward-look UX in browser** — operator verified visually per 15-08 operator checkpoint 1
2. **Drift banner in real Gmail** — operator checkpoint 2 (Phase 16 UAT scope)

### Gaps Summary

Three gaps block full goal achievement:

**Gap 1 — CALC-02 Entry Target Row Not Wired (SC-2):** `_render_entry_target_row` was implemented and unit-tested but never connected to the rendering pipeline. `_render_positions_table` skips instruments where `positions[key] is None` with no fallback loop. When a position is flat and the signal is LONG or SHORT, no entry target row appears. The fix is a second loop after the existing position loop (see worktree version at `.claude/worktrees/agent-ad87c846b0fdd71e1/dashboard.py` lines 1543-1562).

**Gap 2 — Wrong Field Name for Pyramid Level (SC-4):** `_render_calc_row` reads `pos.get('current_level', 0)` but the `Position` TypedDict (system_params.py line 158) defines `pyramid_level`. Every real position dict has `pyramid_level` but never `current_level`, so the LEVEL cell always shows `level 0/2` and NEXT ADD is always computed at the level-0 formula regardless of the actual pyramid level. The fix is a two-key fallback: `pos.get('current_level', pos.get('pyramid_level', 0))`. The unit test fixtures also need to switch from `'current_level'` to `'pyramid_level'` to catch regressions.

**Gap 3 — Stale Golden Fixture (test failure):** The golden HTML snapshot was regenerated (commit `8bbb1f6`) before the UAT fix `name="z"` (commit `6ad306e`) was added to the forward-stop input. The rendered output now includes `name="z"` but the golden does not. `TestGoldenSnapshot::test_golden_snapshot_matches_committed` fails. Fix: re-run `python tests/regenerate_dashboard_golden.py` and commit the updated golden.

The three gaps are independent and can be closed in a single plan. Gaps 1 and 2 are pure `dashboard.py` fixes; Gap 3 is a regeneration step that must follow Gap 2 (since the fix to Gap 2 also changes the rendered output).

---

_Verified: 2026-04-26T10:00:00+08:00_
_Verifier: Claude (gsd-verifier)_
