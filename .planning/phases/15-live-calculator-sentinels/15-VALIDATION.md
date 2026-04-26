---
phase: 15
slug: live-calculator-sentinels
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-26
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: 15-RESEARCH.md `## Validation Architecture` section.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ (pinned in pyproject.toml) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/test_sizing_engine.py tests/test_state_manager.py tests/test_dashboard.py tests/test_notifier.py tests/test_web_dashboard.py tests/test_main.py -x -q` |
| **Full suite command** | `pytest -ra --strict-markers` |
| **Estimated runtime** | ~30 seconds (quick), ~90 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run quick command (above)
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds (quick), 90 seconds (full)

---

## Per-Requirement Verification Map

> Per-task IDs are populated by the planner once PLAN.md files exist. Until then, the table below maps each phase REQ-ID and architectural decision to its measurable test target. Wave 0 must create the test stubs marked ❌.

| REQ / Decision | Behavior | Test Type | Automated Command | File Exists | Status |
|----------------|----------|-----------|-------------------|-------------|--------|
| CALC-01 | Per-instrument calc-row renders trail stop, distance $+%, next-add price | unit | `pytest tests/test_dashboard.py::TestRenderCalculatorRow -x` | ❌ W0 | ⬜ pending |
| CALC-01 | Trail stop in calc-row matches `_compute_trail_stop_display` (parity) | unit | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_trail_stop_matches_display_helper -x` | ❌ W0 | ⬜ pending |
| CALC-02 | FLAT position + LONG/SHORT signal → entry-target row with calc_position_size contracts | unit | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_entry_target_row_flat_long -x` | ❌ W0 | ⬜ pending |
| CALC-02 | FLAT position + FLAT signal → no calc-row | unit | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_no_calc_row_when_flat_signal -x` | ❌ W0 | ⬜ pending |
| CALC-03 | Forward-look fragment GET returns `<span id="forward-stop-{instrument}-w">$X</span>` | integration | `pytest tests/test_web_dashboard.py::TestForwardStopFragment -x` | ❌ W0 | ⬜ pending |
| CALC-03 | W bit-identical to direct `get_trailing_stop(synthesized_pos)` (5 cases per D-07) | unit (parity) | `pytest tests/test_web_dashboard.py::TestForwardStopFragment::test_forward_stop_matches_sizing_engine_bit_for_bit -x` | ❌ W0 | ⬜ pending |
| CALC-03 | Z=empty/0/negative → W cell shows `—` (no HTMX error) | integration | `pytest tests/test_web_dashboard.py::TestForwardStopFragment::test_degenerate_z_returns_em_dash -x` | ❌ W0 | ⬜ pending |
| CALC-04 | Pyramid section: `Pyramid: level N/2 — next add at $P (+1×ATR), new stop $S` | unit | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_pyramid_section_level_1 -x` | ❌ W0 | ⬜ pending |
| CALC-04 | Pyramid at MAX: `Pyramid: level 2/2 — fully pyramided` | unit | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_pyramid_section_at_max -x` | ❌ W0 | ⬜ pending |
| SENTINEL-01 | `detect_drift({SPI200: LONG pos}, {SPI200: FLAT})` → `DriftEvent(severity='drift')` | unit (pure-math) | `pytest tests/test_sizing_engine.py::TestDetectDrift::test_drift_long_vs_flat -x` | ❌ W0 | ⬜ pending |
| SENTINEL-01 | Amber drift banner renders with `.sentinel-drift` class | unit | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_amber_drift_banner -x` | ❌ W0 | ⬜ pending |
| SENTINEL-01 | No banner when no drift events | unit | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_no_banner_when_no_drift -x` | ❌ W0 | ⬜ pending |
| SENTINEL-02 | LONG position + SHORT signal → `DriftEvent(severity='reversal')` | unit (pure-math) | `pytest tests/test_sizing_engine.py::TestDetectDrift::test_reversal_long_vs_short -x` | ❌ W0 | ⬜ pending |
| SENTINEL-02 | Red reversal banner renders with `.sentinel-reversal` class | unit | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_red_reversal_banner -x` | ❌ W0 | ⬜ pending |
| SENTINEL-02 | Mixed drift+reversal events: single merged banner uses red border | unit | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_mixed_drift_reversal_uses_reversal_color -x` | ❌ W0 | ⬜ pending |
| SENTINEL-03 | Drift warning in `state['warnings']` causes `_has_critical_banner` to return True | unit (notifier) | `pytest tests/test_notifier.py::TestDriftBanner::test_has_critical_banner_drift_source -x` | ❌ W0 | ⬜ pending |
| SENTINEL-03 | Email body drift banner text byte-for-byte parity with dashboard text | unit (notifier parity) | `pytest tests/test_notifier.py::TestDriftBanner::test_drift_banner_body_parity_with_dashboard -x` | ❌ W0 | ⬜ pending |
| SENTINEL-03 | Email subject `[!]` prefix when drift warning present | unit (notifier subject) | `pytest tests/test_notifier.py::TestDriftBanner::test_drift_banner_in_email_body_and_subject_critical_prefix -x` | ❌ W0 | ⬜ pending |
| D-13 | Corruption + drift coexisting → corruption banner first | unit (banner hierarchy) | `pytest tests/test_notifier.py::TestBannerStackOrder::test_banner_hierarchy_corruption_beats_drift -x` | ❌ W0 | ⬜ pending |
| D-13 | Stale + drift coexisting → stale banner first | unit (banner hierarchy) | `pytest tests/test_notifier.py::TestBannerStackOrder::test_banner_hierarchy_stale_beats_drift -x` | ❌ W0 | ⬜ pending |
| D-02 | `clear_warnings_by_source('drift')` removes only drift, leaves others intact | unit (state_manager) | `pytest tests/test_state_manager.py::TestClearWarningsBySource -x` | ❌ W0 | ⬜ pending |
| D-02 | Drift cleared+recomputed at signal-loop start (W3 invariant: mutate_state called exactly twice per run) | integration (main) | `pytest tests/test_main.py::TestDriftWarningLifecycle -x` | ❌ W0 | ⬜ pending |
| D-07 (sub) | Side-by-side `manual:|computed:` stop cell renders correctly when manual_stop set | unit | `pytest tests/test_web_dashboard.py::TestSideBySideStopDisplay::test_manual_stop_side_by_side -x` | ❌ W0 | ⬜ pending |
| D-07 (sub) | manual_stop=None → single computed stop cell (no Phase 14 regression) | unit | `pytest tests/test_web_dashboard.py::TestSideBySideStopDisplay::test_no_manual_stop_single_cell -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_sizing_engine.py::TestDetectDrift` — covers SENTINEL-01, SENTINEL-02, D-04 conservatism
- [ ] `tests/test_state_manager.py::TestClearWarningsBySource` — covers D-02 partial-clear behavior
- [ ] `tests/test_dashboard.py::TestRenderCalculatorRow` — covers CALC-01, CALC-02, CALC-04
- [ ] `tests/test_dashboard.py::TestRenderDriftBanner` — covers SENTINEL-01, SENTINEL-02 dashboard rendering
- [ ] `tests/test_notifier.py::TestDriftBanner` — covers SENTINEL-03 email rendering + parity
- [ ] `tests/test_notifier.py::TestBannerStackOrder` — covers D-13 hierarchy
- [ ] `tests/test_web_dashboard.py::TestForwardStopFragment` — covers CALC-03 fragment route + parity
- [ ] `tests/test_web_dashboard.py::TestSideBySideStopDisplay` — covers D-07 side-by-side stop cell
- [ ] `tests/test_main.py::TestDriftWarningLifecycle` — covers D-02 lifecycle + W3 invariant
- [ ] **Update `FORBIDDEN_MODULES_DASHBOARD` in `tests/test_signal_engine.py`** to remove `sizing_engine` (Wave 0 gating task — without this, `dashboard.py` cannot import `sizing_engine` and CI fails)
- [ ] Regenerate golden fixtures: `tests/fixtures/dashboard/golden.html`, `tests/fixtures/notifier/golden_*.html`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Forward-look HTMX UX feel (no flash, smooth swap) | CALC-03 | Visual smoothness not assertable in pytest | Open `/dashboard` in browser → enter Z in SPI200 row → verify W cell updates without visible page reload or layout shift |
| Email banner visual fidelity in Gmail | SENTINEL-03 | Email-client rendering not assertable in pytest | Trigger drift state via `/admin/test-state` → run `python -c "from main import run_daily_check; run_daily_check(test=True)"` (or equivalent dry-send path) → inspect rendered email in Gmail web client → confirm `━━━ Drift detected ━━━` block renders with correct font-weight, padding, color |

---

## Validation Sign-Off

- [ ] All Wave 0 stubs created and tracked
- [ ] All REQ-IDs (CALC-01..04, SENTINEL-01..03) and decisions (D-02, D-07, D-13) have at least one automated test target
- [ ] Sampling continuity: per-task verify command (quick) covers all 6 modified test files
- [ ] No watch-mode flags (pytest invoked with `-x -q`, not `-f` or `--ff`)
- [ ] Feedback latency < 30s (quick), < 90s (full)
- [ ] `nyquist_compliant: true` set in frontmatter once Wave 0 stubs land
- [ ] `wave_0_complete: true` set in frontmatter once all Wave 0 stubs are committed

**Approval:** pending
