---
phase: 17-per-signal-calculation-transparency
verified: 2026-04-30T14:00:00+10:00
status: human_needed
score: 16/17 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Open the dashboard at https://signals.mwiriadi.me/ after the next 08:00 AWST daily run. Expand each instrument's 'Show calculations' disclosure. Open Excel or similar. Using the 40 OHLC rows in the Inputs panel, hand-compute ATR(14) from scratch using Wilder smoothing."
    expected: "Computed ATR(14) matches the displayed ATR value in the Indicators panel to within 1e-6 tolerance (ROADMAP SC-5)."
    why_human: "Requires live state populated by a daily run (ohlc_window is currently empty — migration ran, first daily run pending). Cannot verify the 1e-6 match claim programmatically without live data."
  - test: "On an iPhone (Safari), expand the SPI200 'Show calculations' disclosure. Tap each indicator name in the Indicators panel."
    expected: "Each indicator name reveals its formula text row on first tap, collapses it on second tap. No tap events are silently dropped."
    why_human: "iOS Safari click-event on non-interactive elements requires cursor:pointer (D-15). CSS is present and test passes, but actual mobile device verification cannot be automated."
  - test: "Open the dashboard in a browser. Expand the SPI200 disclosure. Refresh the page."
    expected: "SPI200 disclosure stays open after refresh. Close SPI200 disclosure, refresh — it stays closed. Expand AUDUSD independently — each instrument's state is independently persisted via the tsi_trace_open cookie."
    why_human: "Cookie persistence across page loads requires a live browser session. The route-layer substitution tests cover the logic, but the full cookie round-trip (write on toggle, read on load) cannot be verified without a real browser."
---

# Phase 17: Per-signal Calculation Transparency Verification Report

**Phase Goal:** Operator re-derives today's signal by hand from the dashboard alone — no source code reading, no shell access. Three new panels per instrument (Inputs / Indicators / Vote) expose the OHLC bars, every intermediate indicator with its formula, and the final 2-of-3 vote + ADX gate.
**Verified:** 2026-04-30T14:00:00+10:00
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | STATE_SCHEMA_VERSION is integer 5 | ✓ VERIFIED | `python3.11 -c "import system_params; print(system_params.STATE_SCHEMA_VERSION)"` prints `5`; system_params.py line 121 |
| 2 | MIGRATIONS dict key 5 maps to _migrate_v4_to_v5 | ✓ VERIFIED | state_manager.py line 220: `5: _migrate_v4_to_v5,` |
| 3 | Loading v4 state.json walks to v5 and stamps ohlc_window=[] + indicator_scalars={} on dict-shaped signal rows | ✓ VERIFIED | `TestMigrateV4ToV5` (7 tests) + `TestFullWalkV0ToV5` (1 test): all 8 pass |
| 4 | Migration is idempotent — re-running on already-v5 data does not overwrite populated fields | ✓ VERIFIED | `test_migrate_v4_to_v5_idempotent_ohlc_window_already_populated`, `test_migrate_v4_to_v5_idempotent_indicator_scalars_already_populated`, `test_migrate_v4_to_v5_idempotent_partial_state`: all PASS |
| 5 | Migration is additive — all pre-existing signal row fields preserved on round-trip | ✓ VERIFIED | `test_migrate_v4_to_v5_preserves_other_signal_fields`: PASS |
| 6 | Migration skips legacy int-shape signal rows | ✓ VERIFIED | `test_migrate_v4_to_v5_skips_int_legacy_shape`: PASS |
| 7 | After daily run, signal rows carry 40-entry ohlc_window + 9-key indicator_scalars | ✓ VERIFIED | `TestRunDailyCheckPersistsTracePayload` (5 tests): all PASS; main.py lines 1279-1329 implement the writer |
| 8 | dashboard.py defines all required module-level symbols and helpers | ✓ VERIFIED | `_TRACE_FORMULAS` (9 keys, line 984), `_SEED_LENGTHS` (line 999), `_TRACE_TOGGLE_JS` (line 1022), `_format_indicator_value` (line 791), `_resolve_trace_open_keys` (line 1089), `_render_trace_inputs/indicators/vote/panels` (lines 1199/1249/1290/1361); `render_dashboard` signature has `trace_open_keys: list | None = None` (line 2393) |
| 9 | dashboard.py emits {{TRACE_OPEN_SPI200}} / {{TRACE_OPEN_AUDUSD}} placeholder strings at write time; route layer substitutes with ' open' or '' per cookie | ✓ VERIFIED | `_TRACE_OPEN_PLACEHOLDER` dict at lines 1015-1016; route substitution at web/routes/dashboard.py lines 276-284; `TestTraceCookieAllowlist` (4 tests): all PASS |
| 10 | Route layer reads tsi_trace_open cookie and applies allowlist filter (SPI200/AUDUSD only); tampered keys silently dropped | ✓ VERIFIED | `_VALID_TRACE_INSTRUMENT_KEYS = frozenset({'SPI200', 'AUDUSD'})` at line 89; `_resolve_trace_open()` at line 138; `test_tsi_trace_open_cookie_tampered_unknown_keys_filtered`: PASS |
| 11 | Rendered HTML contains all 9 formula strings + exactly two details data-instrument blocks + 40 ohlc rows per instrument when populated | ✓ VERIFIED | `test_all_formula_strings_present`, `test_details_blocks_one_per_instrument`, `test_inputs_panel_renders_40_rows` (80 total rows): all PASS |
| 12 | Empty ohlc_window renders 'Awaiting first daily run'; indicator rows render n/a(need N bars, have 0) | ✓ VERIFIED | `test_inputs_panel_empty_state`: PASS; `_render_trace_inputs` D-11 branch at line 1206 |
| 13 | _format_indicator_value: 6 decimals for finite floats; n/a(need N bars, have M) for NaN+seed-short; n/a(flat price) for NaN+seed-satisfied | ✓ VERIFIED | `TestFormatIndicatorValue` (3 tests): all PASS |
| 14 | cursor: pointer on .trace-indicator-name CSS (D-15 iOS Safari fix) | ✓ VERIFIED | dashboard.py line 697: `.trace-indicator-name {{ cursor: pointer; }}`; `test_dashboard_indicator_name_has_cursor_pointer_css`: PASS |
| 15 | Hex-boundary: dashboard.py does not import signal_engine, data_fetcher, notifier, main, numpy, pandas, yfinance, requests, schedule, dotenv | ✓ VERIFIED | `test_forbidden_imports_absent` (3/3) + `test_dashboard_no_forbidden_imports`: all PASS; formula text inlined as `_TRACE_FORMULAS` constants per D-10/D-13 |
| 16 | Render path is pure read — no state mutation in dashboard.py trace helpers | ✓ VERIFIED | `test_render_does_not_mutate_state`: PASS; grep for `state[.*]=` in dashboard.py returns zero results |
| 17 | Operator can hand-recalc ATR(14) from displayed OHLC values and match to 1e-6 (ROADMAP SC-5) | ? UNCERTAIN | Logic correct (values persisted from engine at 6-decimal precision, D-05); cannot verify numerically without a live populated ohlc_window. Live state.json currently has ohlc_window=[] (migration ran; awaiting first daily run). Human verification required. |

**Score:** 16/17 truths verified (1 UNCERTAIN — human verification required)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `system_params.py` | STATE_SCHEMA_VERSION=5 | ✓ VERIFIED | Line 121 confirmed |
| `state_manager.py` | _migrate_v4_to_v5 + MIGRATIONS[5] | ✓ VERIFIED | Lines 185, 220 |
| `main.py` | Signal-row writer persists ohlc_window + indicator_scalars | ✓ VERIFIED | Lines 1279-1329 |
| `dashboard.py` | _TRACE_FORMULAS, helpers, render_dashboard(trace_open_keys) | ✓ VERIFIED | All symbols present and substantive |
| `web/routes/dashboard.py` | tsi_trace_open cookie + allowlist + placeholder substitution | ✓ VERIFIED | Lines 89, 138-150, 276-284 |
| `tests/test_system_params.py` | TestStateSchemaVersionV5 | ✓ VERIFIED | 3 new tests: all PASS |
| `tests/test_state_manager.py` | TestMigrateV4ToV5 | ✓ VERIFIED | 7 tests: all PASS |
| `tests/test_main.py` | TestRunDailyCheckPersistsTracePayload | ✓ VERIFIED | 5 tests: all PASS |
| `tests/test_dashboard.py` | TestTracePanels + TestFormatIndicatorValue | ✓ VERIFIED | 14 + 3 = 17 tests: all PASS |
| `tests/test_web_dashboard.py` | TestTraceCookieAllowlist | ✓ VERIFIED | 4 tests: all PASS |
| `tests/fixtures/dashboard/sample_state_v5.json` | schema_version=5, 40-entry ohlc_window, 9-key indicator_scalars | ✓ VERIFIED | Programmatically confirmed |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| system_params.STATE_SCHEMA_VERSION=5 | state_manager.MIGRATIONS[5] | _migrate_v4_to_v5 registered | ✓ WIRED | state_manager.py line 220 |
| main.py signal-row writer | state.signals[inst].ohlc_window + indicator_scalars | df.tail(40) iter + inline TR build | ✓ WIRED | main.py lines 1279-1329 |
| dashboard.render_dashboard(trace_open_keys) | _render_trace_panels via _render_signal_cards | _resolve_trace_open_keys computed and passed | ✓ WIRED | dashboard.py lines 2429, 1459-1465 |
| `<details data-instrument="SPI200"{{TRACE_OPEN_SPI200}}>` | route layer per-request substitution | content.replace(_TRACE_OPEN_PLACEHOLDER_SPI200, b' open' or b'') | ✓ WIRED | web/routes/dashboard.py lines 276-284 |
| request.cookies.get('tsi_trace_open') | allowlist-filtered frozenset | frozenset(parts & _VALID_TRACE_INSTRUMENT_KEYS) | ✓ WIRED | web/routes/dashboard.py lines 146-150 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| dashboard.py _render_trace_inputs | ohlc_window | sig_dict.get('ohlc_window', []) from state.json | Yes (populated by main.py from df.tail(40) on daily run; empty[] on migration-only state) | ✓ FLOWING (logic correct; live data pending first daily run) |
| dashboard.py _render_trace_indicators | indicator_scalars | sig_dict.get('indicator_scalars', {}) from state.json | Yes (9-key dict built from df_with_indicators columns in main.py) | ✓ FLOWING |
| dashboard.py _render_trace_vote | signal + indicator_scalars | same dict | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

Step 7b: SKIPPED for live-data checks (no daily run has populated ohlc_window yet — migration backfilled empty lists). Test-suite spot-checks substituted:

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 40 OHLC rows rendered per instrument | pytest TestTracePanels::test_inputs_panel_renders_40_rows | 80 total rows asserted | ✓ PASS |
| All 9 formula strings in rendered HTML | pytest TestTracePanels::test_all_formula_strings_present | PASS | ✓ PASS |
| ADX gate badge PASS/FAIL dispatch | pytest test_adx_gate_badge_pass/fail | both PASS | ✓ PASS |
| Cookie tamper protection | pytest TestTraceCookieAllowlist::test_...tampered... | PASS | ✓ PASS |
| Mutable-default avoidance on kwarg | pytest test_render_dashboard_default_trace_open_keys_is_none | PASS | ✓ PASS |
| Hex-boundary AST guard | pytest TestDeterminism::test_forbidden_imports_absent (3 parametrize) | PASS | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TRACE-01 | 17-01 | Inputs panel with OHLC bars per instrument | ✓ SATISFIED | _render_trace_inputs, 40-row fixture test, sample_state_v5.json |
| TRACE-02 | 17-01 | Indicators panel: TR/ATR/+DI/-DI/ADX/Mom1/3/12/RVol with formula | ✓ SATISFIED | _render_trace_indicators, _TRACE_FORMULAS (9 keys), formula presence test |
| TRACE-03 | 17-01 | Vote panel: 2-of-3 vote + ADX gate breakdown | ✓ SATISFIED | _render_trace_vote, badge class tests, ADX gate tests |
| TRACE-04 | 17-01 | Pure read — no state mutation in render | ✓ SATISFIED | test_render_does_not_mutate_state PASS; grep confirms no state writes in dashboard.py |
| TRACE-05 | 17-01 | Forbidden-imports AST guard extended for new dashboard.py code paths | ✓ SATISFIED | test_dashboard_no_forbidden_imports PASS; FORBIDDEN_MODULES_DASHBOARD covers new helpers (no new imports introduced) |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| dashboard.py | 79, 82 | `from state_manager import` and `from system_params import` | ℹ️ Info | Pre-existing imports from Phases 1-6; explicitly permitted by FORBIDDEN_MODULES_DASHBOARD (state_manager/system_params are allowed for dashboard). Not introduced by Phase 17. Not a violation. |
| state.json (live) | — | ohlc_window=[] and indicator_scalars={} (empty) | ℹ️ Info | Expected post-migration-pre-first-run state per D-08/D-11. Will be populated on next 08:00 AWST daily run. Not a stub. |

No blockers found.

### Test Count Reconciliation

SUMMARY claimed: 1155 passed, 9 pre-existing nginx failures.
Actual (2026-04-30): **1380 passed, 12 failed** (all pre-existing).

**Pre-existing failures (12, confirmed unrelated to Phase 17):**
- `tests/test_nginx_signals_conf.py` × 9 (structure + placeholder + forbidden patterns)
- `tests/test_notifier.py` × 2 (`ruff` binary not in PATH on this machine — CI env only)
- `tests/test_setup_https_doc.py` × 1 (cross-artifact drift guard)

The SUMMARY's 1155 count reflects a local pytest run that may have used `--ignore` flags or an earlier snapshot before Phase 17 tests were added. The additional ~225 passing tests beyond 1155 include all Phase 17 additions (30 new tests) plus tests from prior phases in the current suite. No phase-17 test is failing.

### Phase 17-specific tests: ALL PASS

- `TestMigrateV4ToV5` (7 tests): PASS
- `TestFullWalkV0ToV5` (1 test): PASS
- `TestRunDailyCheckPersistsTracePayload` (5 tests): PASS
- `TestTracePanels` (14 tests): PASS
- `TestFormatIndicatorValue` (3 tests): PASS
- `TestTraceCookieAllowlist` (4 tests): PASS
- `TestDeterminism::test_forbidden_imports_absent` (3 parametrize, covers dashboard.py): PASS

**Total Phase 17 new tests:** 37 (7+1+5+14+3+4+3), all passing.

### Decision Verification: D-14..D-17

| Decision | Verification | Result |
|----------|-------------|--------|
| D-14: render_dashboard gains trace_open_keys kwarg | `grep -n "trace_open_keys" dashboard.py` returns 7 matches (signature + body + docstring) | ✓ |
| D-15: cursor:pointer on .trace-indicator-name | Line 697 in dashboard.py f-string CSS; test_dashboard_indicator_name_has_cursor_pointer_css PASS | ✓ |
| D-16: route-layer cookie allowlist frozenset intersection | `_VALID_TRACE_INSTRUMENT_KEYS = frozenset({'SPI200', 'AUDUSD'})` at line 89; intersection at line 150 | ✓ |
| D-17: attribute-level placeholder substitution | `{{TRACE_OPEN_SPI200}}` / `{{TRACE_OPEN_AUDUSD}}` emitted by dashboard.py; route replaces with b' open' or b'' per cookie | ✓ |

### Human Verification Required

Three items require a live browser session and/or a populated ohlc_window after the next 08:00 AWST daily run:

**1. Hand-recalc match-to-1e-6 (ROADMAP SC-5)**

**Test:** After the next 08:00 AWST daily run, open the dashboard. From the SPI200 Inputs panel, copy the 40 OHLC rows into Excel. Compute ATR(14) from scratch using Wilder smoothing (initial seed = SMA of first 14 TR values, then Wilder-smooth). Compare to the displayed ATR value in the Indicators panel.
**Expected:** Match to 1e-6 tolerance (the engine uses `%.17g` round-trip precision and displays 6 decimals — drift below 1e-6 threshold).
**Why human:** Requires live populated ohlc_window data. Cannot verify with fixture data since the 1e-6 claim depends on the actual engine computation matching the displayed value on a real trading day.

**2. iOS Safari tap-to-toggle (D-15)**

**Test:** On an iPhone running Safari, open `https://signals.mwiriadi.me/`. Expand an instrument's "Show calculations" disclosure. Tap each indicator name cell.
**Expected:** Formula row appears on tap; disappears on second tap. No silently-missed taps.
**Why human:** cursor:pointer CSS is present and tested, but device-specific click-event behavior on non-interactive elements requires actual iOS Safari device testing.

**3. Cookie persistence across page reload (D-04, D-12)**

**Test:** In a browser, expand the SPI200 disclosure. Hard-refresh the page (Cmd+Shift+R). Verify SPI200 disclosure reopens automatically. Close SPI200, refresh — verify it stays closed. Test AUDUSD independently.
**Expected:** Each instrument's disclosure state is independently persisted in tsi_trace_open cookie and survives reload.
**Why human:** Full browser cookie round-trip (JS write on toggle event, HTTP read on next request, route substitution) cannot be simulated end-to-end without a real browser.

---

_Verified: 2026-04-30T14:00:00+10:00_
_Verifier: Claude (gsd-verifier)_
