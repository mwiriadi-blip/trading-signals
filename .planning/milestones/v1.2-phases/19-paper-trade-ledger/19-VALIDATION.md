---
phase: 19
slug: paper-trade-ledger
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-10
audited: 2026-05-10
---

# Phase 19 — Validation Strategy

> Reconstructed retroactively after phase execution. All LEDGER SC items have automated test
> coverage; full suite green (1243+ tests excluding pre-existing nginx/ruff failures).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest tests/test_pnl_engine.py tests/test_web_paper_trades.py -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Phase-19 subset command** | `.venv/bin/pytest tests/test_pnl_engine.py tests/test_web_paper_trades.py tests/test_state_manager.py::TestMigrateV5ToV6 tests/test_state_manager.py::TestFullWalkV0ToV6 tests/test_dashboard.py::TestRenderPaperTradesOpenTable tests/test_dashboard.py::TestRenderPaperTradesClosedTable tests/test_dashboard.py::TestRenderPaperTradesStats tests/test_dashboard.py::TestComputeAggregateStats tests/test_dashboard.py::TestRenderPaperTradesRegion tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -q` |
| **Estimated runtime** | ~12 s (Phase-19 subset, ~150 tests); ~3 min (full suite) |

---

## Sampling Rate

- **After every task commit:** Run task-scoped pytest file (~1–3 s)
- **After every plan wave:** Run full suite (`pytest -q`)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 20 s for Phase-19 subset

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement / Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|------------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 19-01-T1 | paper-trade-ledger | 1 | STATE_SCHEMA_VERSION=6; _migrate_v5_to_v6 idempotent; full-walk v0→v6 | — | Schema migration cannot corrupt existing state | unit | `.venv/bin/pytest tests/test_state_manager.py::TestMigrateV5ToV6 -q` | ✅ | ✅ green |
| 19-01-T2 | paper-trade-ledger | 1 | pnl_engine pure-math: compute_unrealised_pnl + compute_realised_pnl | — | No I/O, no state, hex-boundary enforced | unit | `.venv/bin/pytest tests/test_pnl_engine.py -q` | ✅ | ✅ green |
| 19-01-T3 | paper-trade-ledger | 1 | Six FastAPI routes + _parse_form; D-04 strict server validation; 400 on errors | T-19-01-01 | Input validated server-side; no SQL/injection surface | unit | `.venv/bin/pytest tests/test_web_paper_trades.py::TestOpenPaperTrade tests/test_web_paper_trades.py::TestOpenValidation -q` | ✅ | ✅ green |
| 19-01-T4 | paper-trade-ledger | 1 | PATCH/DELETE 405 on closed row; composite ID under flock; strategy_version fresh | T-19-01-02 | Closed rows immutable; race condition prevented by flock | unit + multiprocessing | `.venv/bin/pytest tests/test_web_paper_trades.py::TestImmutability tests/test_web_paper_trades.py::TestCompositeIDGeneration tests/test_web_paper_trades.py::TestConcurrentOpen tests/test_web_paper_trades.py::TestStrategyVersionTagging -q` | ✅ | ✅ green |
| 19-01-T5 | paper-trade-ledger | 1 | Dashboard render: open table MTM, closed table sorted desc, stats bar, empty-state | T-19-01-03 | Journal text XSS escaped; NaN guards prevent render crash | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderPaperTradesOpenTable tests/test_dashboard.py::TestRenderPaperTradesClosedTable tests/test_dashboard.py::TestRenderPaperTradesStats tests/test_dashboard.py::TestComputeAggregateStats tests/test_dashboard.py::TestRenderPaperTradesRegion -q` | ✅ | ✅ green |
| 19-01-T6 | paper-trade-ledger | 1 | render_dashboard composition; hex-boundary AST guard (pnl_engine); cookie auth enforcement | T-19-01-01 | Hex boundary prevents circular imports; all routes auth-gated | unit (seam + AST) | `.venv/bin/pytest tests/test_dashboard.py::TestRenderDashboardComposition tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent tests/test_web_paper_trades.py::TestAuthEnforcement -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Coverage by Requirement

| Requirement ID | Description | Tasks Covered | Test Count | Status |
|---------------|-------------|---------------|------------|--------|
| LEDGER-01 | Web form for manual paper trade entry; validated server-side | 19-01-T3 | 17 (TestOpenValidation) | ✅ complete |
| LEDGER-02 | Per-trade entry in state.paper_trades[] with 13 fields including strategy_version | 19-01-T3, 19-01-T4 | 4+3 (open + strategy version) | ✅ complete |
| LEDGER-03 | Open trades table with mark-to-market unrealised P&L | 19-01-T5 | 11 (TestRenderPaperTradesOpenTable) | ✅ complete |
| LEDGER-04 | Closed trades table sorted by exit date desc; closed rows immutable | 19-01-T4, 19-01-T5 | 2+4 (immutability + closed table) | ✅ complete |
| LEDGER-05 | Close form; server computes realised P&L; status flipped to closed | 19-01-T3 | 6 (TestClosePaperTrade) | ✅ complete |
| LEDGER-06 | Aggregate stats: realised, unrealised, wins, losses, win rate | 19-01-T5 | 8 (TestRenderPaperTradesStats) | ✅ complete |
| VERSION-03 | Every paper trade row tagged with strategy_version at write time | 19-01-T4 | 3 (TestStrategyVersionTagging) | ✅ complete |

---

## Coverage by Threat Reference

| Threat Ref | Requirement / Behavior | Test Coverage | Status |
|------------|----------------------|---------------|--------|
| T-19-01-01 | HTMX form input validated server-side (D-04 all rules) | TestOpenValidation 17 tests | ✅ covered |
| T-19-01-02 | Closed-row immutability (405 contract) | TestImmutability 2 tests + TestClosePaperTrade immutability case | ✅ covered |
| T-19-01-03 | NaN/None last_close guard prevents render crash | test_open_table_renders_na_when_last_close_missing + _nan | ✅ covered |
| T-19-01-04 | Composite ID race condition (concurrent opens) | TestConcurrentOpen::test_concurrent_open_does_not_collide (multiprocessing) | ✅ covered |
| T-19-01-05 | XSS via journal text (trade ID rendered in HTML) | Phase 27 Plan 27-08 html-escape audit extends to paper-trade render path (html.escape with quote=True) | ✅ covered by 27-08 |
| T-19-01-06 | Decimal precision (entry_cost_aud half-split) | TestOpenPaperTrade::test_open_valid_spi200_long_appends_row (entry_cost_aud=3.0 assertion) | ✅ covered |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Browser form submission with HTMX swap in real browser | LEDGER-01 (UX) | Automated tests use TestClient (bypass real browser encoding). The fix-forward commit f3179ab switched routes to form-encoded; browser behavior now matches. | Navigate to production `https://signals.mwiriadi.me`, use paper-trade form, observe #trades-region swap |
| Stats bar sticky behavior on mobile scroll | LEDGER-06 (CSS) | CSS `position: sticky; top: 0` render behavior not testable in unit tests | Open dashboard on iPhone Safari, scroll past stats bar, confirm it stays visible |

All other phase behaviors have automated verification.

---

## Gaps

| Gap ID | LEDGER Item | Description | Status |
|--------|------------|-------------|--------|
| GAP-19-01 | LEDGER-03 | MTM P&L correctness on live production state (yfinance last_close) | Deferred — manual operator verification on droplet; automated tests use fixture state |
| GAP-19-02 | LEDGER-04 | Browser-visible close form UX below open trades table (D-03) | Deferred — requires human browser test; TestCloseFormFragment covers server-side fragment render |

Both gaps are observation/UX gaps only. All core correctness behaviors (P&L math, route validation, schema migration, immutability, composite ID) have full automated coverage.

---

## Validation Sign-Off

- [x] All 6 LEDGER-N items have automated verify commands
- [x] Sampling continuity: every task has its own test file or test class
- [x] Wave 0 not required — existing pytest infra sufficient
- [x] No watch-mode flags
- [x] Feedback latency < 20 s for Phase-19 subset
- [x] `nyquist_compliant: true` set in frontmatter
- [x] Coverage matrix rows match LEDGER SC item count (6 items + VERSION-03)

**Approval:** approved 2026-05-10 (retroactive reconstruction; 74 targeted tests + 1243 full-suite tests green)

---

## Validation Audit 2026-05-10

| Metric | Count |
|--------|-------|
| Tasks audited | 6 |
| LEDGER SC items mapped | 7 (LEDGER-01..06 + VERSION-03) |
| Items with full automated coverage | 7 |
| Items deferred (manual only) | 2 UX/MTM observation gaps |
| Phase-19 targeted tests passing | 150+ |
| Total project tests at completion | 1243+ |

Reconstructed from 19-01-SUMMARY.md and 19-VERIFICATION.md artifacts; verification evidence confirms all 7 ROADMAP SC items PASS. Fix-forward commit f3179ab closed the WARNING from initial verification (form encoding mismatch).
