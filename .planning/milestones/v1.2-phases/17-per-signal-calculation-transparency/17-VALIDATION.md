---
phase: 17
slug: per-signal-calculation-transparency
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-10
audited: 2026-05-10
---

# Phase 17 — Validation Strategy

> Reconstructed retroactively per Phase 29 D-06 mechanical retrofit.
> Phase 17 shipped 2026-04-30. All automated tests were verified green at that time.
> Three manual UAT items were deferred (live ohlc_window, iOS Safari, cookie round-trip);
> UAT-17-1 and UAT-17-2 were absorbed as Phase 29 scope per Phase 28 D-20.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest tests/test_<task>.py -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Phase-17 subset command** | `.venv/bin/pytest tests/test_system_params.py tests/test_state_manager.py tests/test_main.py tests/test_dashboard.py tests/test_web_dashboard.py tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -q` |
| **Estimated runtime** | ~2 min (full suite, ~1380 tests at ship time) |

---

## Sampling Rate

- **After every task commit:** Run task-scoped pytest file (~1–3 s)
- **After every plan wave:** Run full suite (`pytest -q`)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 s for Phase-17 subset

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement / Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|------------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 17-T1 | 17-01 | 1 | STATE_SCHEMA_VERSION bumped 4→5; migration key 5 registered | — | Schema bump is atomic; migration dispatch table contiguous | unit | `.venv/bin/pytest tests/test_system_params.py tests/test_state_manager.py -q` | ✅ | ✅ green |
| 17-T2 | 17-01 | 1 | `_migrate_v4_to_v5`: backfill ohlc_window=[] + indicator_scalars={} on dict-shaped rows; idempotent; additive; skips int-shape legacy rows | — | Migration does not overwrite populated fields; does not touch int-shape legacy rows | unit | `.venv/bin/pytest tests/test_state_manager.py::TestMigrateV4ToV5 tests/test_state_manager.py::TestFullWalkV0ToV5 -q` | ✅ | ✅ green |
| 17-T3 | 17-01 | 1 | `main.py` signal-row writer populates 40-entry ohlc_window + 9-key indicator_scalars on every daily run | — | Canonical key names used (plus_di/minus_di, not pdi/ndi); TR computed inline | unit | `.venv/bin/pytest tests/test_main.py::TestRunDailyCheckPersistsTracePayload -q` | ✅ | ✅ green |
| 17-T4 | 17-01 | 1 | `dashboard.py` trace render helpers: `_render_trace_inputs`, `_render_trace_indicators`, `_render_trace_vote`, `_render_trace_panels`; `_TRACE_FORMULAS` (9 keys); `_format_indicator_value`; `_TRACE_TOGGLE_JS`; CSS for `.trace-*` selectors | T-17-01, T-17-02, T-17-03 | Formula text inlined, no forbidden imports; empty-state renders "Awaiting first daily run"; NaN reason-text correct | unit | `.venv/bin/pytest tests/test_dashboard.py::TestTracePanels tests/test_dashboard.py::TestFormatIndicatorValue -q` | ✅ | ✅ green |
| 17-T5 | 17-01 | 1 | `web/routes/dashboard.py` reads `tsi_trace_open` cookie; applies allowlist filter (`_VALID_TRACE_INSTRUMENT_KEYS`); substitutes `{{TRACE_OPEN_SPI200}}`/`{{TRACE_OPEN_AUDUSD}}` placeholders; tampered keys silently dropped | T-17-04 | Cookie carries UI preference only; allowlist prevents attribute injection | unit | `.venv/bin/pytest tests/test_web_dashboard.py::TestTraceCookieAllowlist -q` | ✅ | ✅ green |
| 17-T-FI | 17-01 | 1 | `test_forbidden_imports_absent` covers new `dashboard.py` code paths; no signal_engine/data_fetcher/state_manager imports introduced | T-17-05 | Hex-boundary preserved: dashboard reads primitives only | unit (AST) | `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent tests/test_dashboard.py::TestTracePanels::test_dashboard_no_forbidden_imports -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Coverage by Requirement

| Requirement | Description | Covering Tasks | Test Classes | Status |
|-------------|-------------|----------------|--------------|--------|
| TRACE-01 | Inputs panel: 40-bar OHLC window per instrument | 17-T3, 17-T4 | `TestRunDailyCheckPersistsTracePayload`, `TestTracePanels::test_inputs_panel_renders_40_rows` | ✅ covered |
| TRACE-02 | Indicators panel: TR/ATR/+DI/-DI/ADX/Mom1/3/12/RVol with formula text | 17-T4 | `TestTracePanels::test_all_formula_strings_present`, `TestFormatIndicatorValue` | ✅ covered |
| TRACE-03 | Vote panel: 2-of-3 vote + ADX gate breakdown; badge colors | 17-T4 | `TestTracePanels` (ADX gate pass/fail, badge class tests) | ✅ covered |
| TRACE-04 | Pure read path — no state mutation in render | 17-T4 | `TestTracePanels::test_render_does_not_mutate_state` | ✅ covered |
| TRACE-05 | Forbidden-imports AST guard extended to cover new dashboard helpers | 17-T-FI | `TestDeterminism::test_forbidden_imports_absent`, `test_dashboard_no_forbidden_imports` | ✅ covered |

---

## Coverage by Threat Reference

| Threat Ref | Covering Task | Test | Status |
|------------|---------------|------|--------|
| T-17-01 (XSS via OHLC scalars — render injection) | 17-T4 | `TestTracePanels` formula/badge render tests; `_e()` escape discipline from Phase 27-08 | ✅ closed |
| T-17-02 (formula text drift — dashboard shows wrong formula) | 17-T4 | `TestTracePanels::test_all_formula_strings_present` | ✅ closed |
| T-17-03 (empty-state render confusion — "awaiting first run") | 17-T4 | `TestTracePanels::test_inputs_panel_empty_state` | ✅ closed |
| T-17-04 (cookie tampering — attribute injection via tsi_trace_open) | 17-T5 | `TestTraceCookieAllowlist::test_tsi_trace_open_cookie_tampered_unknown_keys_filtered` | ✅ closed |
| T-17-05 (hex-boundary breach — dashboard imports forbidden module) | 17-T-FI | `test_forbidden_imports_absent` (3 parametrize), `test_dashboard_no_forbidden_imports` | ✅ closed |

---

## Manual-Only Verifications

Three items required a live browser session and/or a populated ohlc_window after the first daily run. These were filed as human-verification items at Phase 17 close (17-VERIFICATION.md) and deferred as UAT items.

| ID | Behavior | Requirement | Why Manual | Resolution |
|----|----------|-------------|------------|------------|
| UAT-17-1 | Hand-recalc ATR(14) from displayed OHLC values matches Indicators panel to 1e-6 | TRACE-01 / ROADMAP SC-5 | Requires live populated ohlc_window; can't verify with fixture data | Phase 29 scope (D-03) — ATR seed exposure fix |
| UAT-17-2 | iOS Safari: tapping indicator name reveals/hides formula row; no silently-dropped taps | TRACE-02 | Requires real iOS Safari device; cursor:pointer CSS present and tested but device verification can't be automated | Phase 29 scope (D-04) — server-side tsi_trace_open cookie render |
| UAT-17-3 | Cookie persistence: expand/collapse SPI200 disclosure, reload page — state preserved; AUDUSD independent | TRACE-04 (cookie round-trip) | Full browser cookie round-trip (JS write → HTTP read → substitution) can't be simulated end-to-end | Phase 29 scope (D-04) — server-side render of `<details open>` from cookie |

---

## Gaps

| Gap ID | SC Item | Reason | Test Gap | Owner | Deferred To |
|--------|---------|--------|----------|-------|-------------|
| GAP-17-01 | ROADMAP SC-5: ATR(14) hand-recalc matches to 1e-6 | Requires live ohlc_window populated by a daily run; fixture data only covers render logic, not actual Wilder accumulator round-trip via display | No automated test for 1e-6 tolerance on live engine output | v1.2.1 / Phase 29 | Phase 29 D-03 (ATR seed exposure) |
| GAP-17-02 | iOS Safari tap-to-toggle formula reveal | Device-specific click-event behavior on non-interactive elements requires physical device | No automated iOS Safari test | v1.3.x | Phase 29 D-04 (server-side cookie render partially resolves) |

---

## Validation Sign-Off

- [x] All 5 TRACE requirements have automated test coverage
- [x] Sampling continuity: every task has its own test class
- [x] 37 new tests shipped with Phase 17, all green at ship time (2026-04-30)
- [x] Wave 0 not required — existing pytest infra sufficient
- [x] No watch-mode flags
- [x] `nyquist_compliant: true` set in frontmatter
- [x] Gaps documented: 2 deferred items (GAP-17-01, GAP-17-02)

**Approval:** approved 2026-05-10 (retroactive reconstruction per Phase 29 D-06 mechanical retrofit)

---

## Validation Audit 2026-05-10

| Metric | Count |
|--------|-------|
| Tasks audited | 5 (+ 1 AST guard) |
| TRACE requirements covered | 5 / 5 |
| Gaps found | 2 |
| Deferred | 2 |
| Escalated | 0 |
| Phase-17 tests passing at ship | 37 / 37 |
| Total project tests at ship | ~1380 |

Reconstructed from 17-01-SUMMARY.md and 17-VERIFICATION.md; no auditor agent spawned.
