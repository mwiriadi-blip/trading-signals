---
phase: 15
slug: live-calculator-sentinels
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-26
revised: 2026-04-26 (post-cross-AI review — REVIEWS H-1, H-2, H-3, H-4, M-1, M-2, M-3, L-1, L-2, L-4)
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: 15-RESEARCH.md `## Validation Architecture` section, augmented with cross-AI review additions per 15-REVIEWS.md.

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
| CALC-03 | W bit-identical to direct `get_trailing_stop(synthesized_pos)` (4 cases per D-07) | unit (parity) | `pytest tests/test_web_dashboard.py::TestForwardStopFragment::test_forward_stop_matches_sizing_engine_bit_for_bit -x` | ❌ W0 | ⬜ pending |
| CALC-03 | Z=empty/0/negative → W cell shows `—` (no HTMX error) | integration | `pytest tests/test_web_dashboard.py::TestForwardStopFragment::test_degenerate_z_returns_em_dash -x` | ❌ W0 | ⬜ pending |
| CALC-04 | Pyramid section: `level N/2 — next add at $P (+1×ATR), new stop $S` | unit | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_pyramid_section_level_1 -x` | ❌ W0 | ⬜ pending |
| CALC-04 | Pyramid at MAX: `level 2/2 — fully pyramided` | unit | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_pyramid_section_at_max -x` | ❌ W0 | ⬜ pending |
| **CALC-04 (REVIEWS H-1)** | **Pyramid section renders BOTH `next add at $` AND `NEW STOP` (projected stop after add); S = get_trailing_stop on synthesized position with peak/trough = next_add_price** | **unit** | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_pyramid_section_includes_new_stop_after_add -x` | **❌ W0** | **⬜ pending** |
| **CALC-01 (REVIEWS M-3)** | **Distance-to-stop uses current_close baseline (state['signals'][X]['last_close']), NOT entry_price; fixture pins current_close ≠ entry_price to prove the semantic** | **unit** | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_distance_dollar_and_percent_formatting -x` | **❌ W0** | **⬜ pending** |
| SENTINEL-01 | `detect_drift({SPI200: LONG pos}, {SPI200: FLAT})` → `DriftEvent(severity='drift')` | unit (pure-math) | `pytest tests/test_sizing_engine.py::TestDetectDrift::test_drift_long_vs_flat -x` | ❌ W0 | ⬜ pending |
| SENTINEL-01 | Amber drift banner renders with `.sentinel-drift` class | unit | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_amber_drift_banner -x` | ❌ W0 | ⬜ pending |
| SENTINEL-01 | No banner when no drift events | unit | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_no_banner_when_no_drift -x` | ❌ W0 | ⬜ pending |
| SENTINEL-02 | LONG position + SHORT signal → `DriftEvent(severity='reversal')` | unit (pure-math) | `pytest tests/test_sizing_engine.py::TestDetectDrift::test_reversal_long_vs_short -x` | ❌ W0 | ⬜ pending |
| SENTINEL-02 | Red reversal banner renders with `.sentinel-reversal` class | unit | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_red_reversal_banner -x` | ❌ W0 | ⬜ pending |
| SENTINEL-02 | Mixed drift+reversal events: single merged banner uses red border | unit | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_mixed_drift_reversal_uses_reversal_color -x` | ❌ W0 | ⬜ pending |
| SENTINEL-03 | Drift warning in `state['warnings']` causes `_has_critical_banner` to return True | unit (notifier) | `pytest tests/test_notifier.py::TestDriftBanner::test_has_critical_banner_drift_source -x` | ❌ W0 | ⬜ pending |
| SENTINEL-03 | Email body drift banner text byte-for-byte parity with dashboard text | unit (notifier parity) | `pytest tests/test_notifier.py::TestDriftBanner::test_drift_banner_body_parity_with_dashboard -x` | ❌ W0 | ⬜ pending |
| SENTINEL-03 | Email subject `[!]` prefix when drift warning present | unit (notifier subject) | `pytest tests/test_notifier.py::TestDriftBanner::test_drift_banner_in_email_body_and_subject_critical_prefix -x` | ❌ W0 | ⬜ pending |
| D-13 (notifier) | Corruption + drift coexisting → corruption banner first | unit (banner hierarchy) | `pytest tests/test_notifier.py::TestBannerStackOrder::test_banner_hierarchy_corruption_beats_drift -x` | ❌ W0 | ⬜ pending |
| D-13 (notifier) | Stale + drift coexisting → stale banner first | unit (banner hierarchy) | `pytest tests/test_notifier.py::TestBannerStackOrder::test_banner_hierarchy_stale_beats_drift -x` | ❌ W0 | ⬜ pending |
| D-13 (notifier) + Pitfall 4 + REVIEWS L-4 | Drift banner inserted BEFORE hero card; uses stable `>Trading Signals</h1>` marker | unit | `pytest tests/test_notifier.py::TestBannerStackOrder::test_drift_banner_inserted_before_hero_card -x` | ❌ W0 | ⬜ pending |
| **D-13 (dashboard, REVIEWS H-2)** | **Dashboard render places drift banner BEFORE Open Positions heading; corruption (when added) sits above drift in same composition** | **integration** | `pytest tests/test_dashboard.py::TestBannerStackOrder::test_dashboard_banner_hierarchy_corruption_beats_drift -x` | **❌ W0** | **⬜ pending** |
| **D-13 (dashboard, REVIEWS H-2)** | **Dashboard drift banner sits below equity-chart slot, above positions section, even when stale info is present** | **integration** | `pytest tests/test_dashboard.py::TestBannerStackOrder::test_dashboard_banner_hierarchy_stale_beats_drift -x` | **❌ W0** | **⬜ pending** |
| **D-13 (dashboard, REVIEWS H-2)** | **Dashboard drift banner string-position < heading-positions string-position (proves top-level slot, not inside _render_positions_table)** | **integration** | `pytest tests/test_dashboard.py::TestBannerStackOrder::test_drift_banner_renders_before_positions_heading -x` | **❌ W0** | **⬜ pending** |
| D-02 | `clear_warnings_by_source('drift')` removes only drift, leaves others intact | unit (state_manager) | `pytest tests/test_state_manager.py::TestClearWarningsBySource -x` | ❌ W0 | ⬜ pending |
| D-02 | Drift cleared+recomputed at signal-loop start (W3 invariant: mutate_state called exactly twice per run) | integration (main) | `pytest tests/test_main.py::TestDriftWarningLifecycle -x` | ❌ W0 | ⬜ pending |
| D-07 (sub) | Side-by-side `manual:|computed:` stop cell renders correctly when manual_stop set | unit | `pytest tests/test_web_dashboard.py::TestSideBySideStopDisplay::test_manual_stop_side_by_side -x` | ❌ W0 | ⬜ pending |
| D-07 (sub) | manual_stop=None → single computed stop cell (no Phase 14 regression) | unit | `pytest tests/test_web_dashboard.py::TestSideBySideStopDisplay::test_no_manual_stop_single_cell -x` | ❌ W0 | ⬜ pending |
| **REVIEWS L-2 (auth chokepoint)** | **GET /?fragment=forward-stop without X-Trading-Signals-Auth header returns 401 (AuthMiddleware regression lock)** | **integration** | `pytest tests/test_web_dashboard.py::TestForwardStopFragment::test_forward_stop_fragment_requires_auth_header -x` | **❌ W0** | **⬜ pending** |
| **REVIEWS H-4 (web mutation drift)** | **POST /trades/open with signal mismatch creates a fresh `source='drift'` warning** | **integration** | `pytest tests/test_web_dashboard.py::TestTradesDriftLifecycle::test_open_trade_creates_drift_when_signal_mismatch -x` | **❌ W0** | **⬜ pending** |
| **REVIEWS H-4 (web mutation drift)** | **POST /trades/close clears drift warnings when no positions remain; non-drift warnings (corruption etc.) preserved** | **integration** | `pytest tests/test_web_dashboard.py::TestTradesDriftLifecycle::test_close_trade_clears_drift -x` | **❌ W0** | **⬜ pending** |
| **REVIEWS H-4 (web mutation drift)** | **POST /trades/modify recomputes drift; non-drift warnings preserved** | **integration** | `pytest tests/test_web_dashboard.py::TestTradesDriftLifecycle::test_modify_trade_recomputes_drift_preserves_non_drift_warnings -x` | **❌ W0** | **⬜ pending** |
| **REVIEWS M-2 (hex discipline)** | **dashboard.py has zero MODULE-TOP imports of sizing_engine; AST guard walks tree.body and asserts no top-level Import / ImportFrom matches sizing_engine** | **unit (AST guard)** | `pytest tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_module_top_sizing_engine_import -x` | **❌ W0 (Wave 0 GREEN)** | **⬜ pending** |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_sizing_engine.py::TestDetectDrift` — covers SENTINEL-01, SENTINEL-02, D-04 conservatism
- [ ] `tests/test_state_manager.py::TestClearWarningsBySource` — covers D-02 partial-clear behavior
- [ ] `tests/test_dashboard.py::TestRenderCalculatorRow` — covers CALC-01, CALC-02, CALC-04 (incl. REVIEWS H-1 + M-3 tests)
- [ ] `tests/test_dashboard.py::TestRenderDriftBanner` — covers SENTINEL-01, SENTINEL-02 dashboard rendering
- [ ] **`tests/test_dashboard.py::TestBannerStackOrder` — covers REVIEWS H-2 dashboard banner hierarchy ordering (3 methods)**
- [ ] `tests/test_notifier.py::TestDriftBanner` — covers SENTINEL-03 email rendering + parity (depends_on 15-05 for parity import; REVIEWS H-3)
- [ ] `tests/test_notifier.py::TestBannerStackOrder` — covers D-13 hierarchy (incl. REVIEWS L-4 stable hero-card marker)
- [ ] `tests/test_web_dashboard.py::TestForwardStopFragment` — covers CALC-03 fragment route + parity + REVIEWS L-2 auth-header regression (10 methods)
- [ ] `tests/test_web_dashboard.py::TestSideBySideStopDisplay` — covers D-07 side-by-side stop cell
- [ ] **`tests/test_web_dashboard.py::TestTradesDriftLifecycle` — covers REVIEWS H-4 web mutation drift coverage (3 methods)**
- [ ] `tests/test_main.py::TestDriftWarningLifecycle` — covers D-02 lifecycle + W3 invariant (REVIEWS M-1 Path A: ALL 4 methods MUST pass — no skips)
- [ ] **Update `FORBIDDEN_MODULES_DASHBOARD` in `tests/test_signal_engine.py`** to remove `sizing_engine` (Wave 0 gating task — without this, `dashboard.py` cannot import `sizing_engine` and CI fails)
- [ ] **Add `test_dashboard_no_module_top_sizing_engine_import` AST guard inside TestDeterminism (REVIEWS M-2 — must pass GREEN at Wave 0; dashboard.py has zero sizing_engine imports right now)**
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
- [ ] All REVIEWS additions (H-1, H-2, H-3, H-4, M-1, M-2, M-3, L-1, L-2, L-4) have at least one automated test target (see bolded rows in the per-requirement map above)
- [ ] Sampling continuity: per-task verify command (quick) covers all 6 modified test files
- [ ] No watch-mode flags (pytest invoked with `-x -q`, not `-f` or `--ff`)
- [ ] Feedback latency < 30s (quick), < 90s (full)
- [ ] `nyquist_compliant: true` set in frontmatter once Wave 0 stubs land
- [ ] `wave_0_complete: true` set in frontmatter once all Wave 0 stubs are committed

**Approval:** pending

---

## Cross-AI Review Coverage Map (REVIEWS.md → tests)

| REVIEWS Finding | Severity | Plan(s) | Test target |
|-----------------|----------|---------|-------------|
| H-1: CALC-04 must render `new stop after add: $S` + `(+1×ATR)` annotation | HIGH | 15-05 | `TestRenderCalculatorRow::test_pyramid_section_includes_new_stop_after_add` |
| H-2: dashboard banner stack hierarchy — drift banner at render_dashboard top-level slot | HIGH | 15-05 | `TestBannerStackOrder` (3 methods, dashboard side) |
| H-3: Plan 15-07 depends_on must include 15-05 | HIGH | 15-07 | depends_on frontmatter (no test — dependency graph correctness) |
| H-4: web mutation drift recomputation under-tested | HIGH | 15-06 | `TestTradesDriftLifecycle` (3 methods) |
| M-1: must_haves vs skip-test escape hatches conflict | MEDIUM | 15-04, 15-07 | Path A — all tests in TestDriftWarningLifecycle (15-04) and TestDriftBanner+TestBannerStackOrder (15-07) MUST pass; no skip bodies |
| M-2: AST guard against module-top sizing_engine import in dashboard.py | MEDIUM | 15-01 | `TestDeterminism::test_dashboard_no_module_top_sizing_engine_import` |
| M-3: distance-to-stop semantics use current_close (not entry_price) | MEDIUM | 15-05 | `TestRenderCalculatorRow::test_distance_dollar_and_percent_formatting` |
| L-1: tighten fragment match to `fragment == 'forward-stop'` | LOW | 15-06 | grep AC: `fragment == 'forward-stop'` returns 1; `fragment.startswith('forward-stop')` returns 0 |
| L-2: HTMX auth-header regression test | LOW | 15-06 | `TestForwardStopFragment::test_forward_stop_fragment_requires_auth_header` |
| L-3: forward-look hint conditional rendering | LOW | 15-05 | covered indirectly via the W em-dash render path on initial dashboard load (the hint span has explicit id="forward-stop-{X}-hint" so Plan 06 can hx-swap-oob it out) |
| L-4: hero-card marker fragility | LOW | 15-07 | `TestBannerStackOrder::test_drift_banner_inserted_before_hero_card` uses literal `>Trading Signals</h1>` marker (verified by direct read of notifier.py:530-531) |
