---
phase: 25
slug: dashboard-ui-ux-overhaul-true-multi-tab-market-preferences
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-10
audited: 2026-05-10
---

# Phase 25 — Validation Strategy

> Reconstructed retroactively after phase execution. Phase 25 shipped 12 plans (25-01 through
> 25-11, including 25-09b gap-closure sub-plan) plus the D-06 cross-cutting two-axis nav and
> D-05 multi-tab URL-canonical market persistence. All 22 D-decisions verified by 25-VERIFICATION.md
> (re-verified 2026-05-07, score 22/22). Per LEARNING 2026-05-06: every test row below was
> grep-confirmed in the actual test file — SUMMARY attestations alone were not trusted.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25" -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Phase-25 subset command** | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25" tests/test_web_app_factory.py -k "TestPhase25 or TestPhase26MarketScoping" tests/test_web_dashboard.py -k "TestPhase25" -q` |
| **Estimated runtime** | ~3 min (full suite, 1794 tests at Phase 25 close); ~15 s (Phase-25 subset) |

---

## Sampling Rate

- **After every task commit:** Run task-scoped pytest class (~1–3 s)
- **After every plan wave:** Run full suite (`pytest -q`)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 s for Phase-25 subset

---

## Per-Task Verification Map

> SC column references the relevant D-decision or OR-resolution from 25-CONTEXT.md / 25-VERIFICATION.md.
> "File Exists" column was grep-verified against the actual test file (per LEARNING 2026-05-06).

| Task ID | Plan | Wave | SC / Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|---------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 25-01-T1 | test-scaffolding | 1 | D-09..D-22: xfail scaffold for all Phase-25 gates | — | xfail(strict=True) prevents false greens | unit (scaffold) | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25" -rxX -q` | ✅ | ✅ green |
| 25-01-T2 | test-scaffolding | 1 | D-01..D-07: routing/cookie/status-strip scaffold | — | xfail(strict=True) scaffold | unit (scaffold) | `.venv/bin/pytest tests/test_web_app_factory.py -k "TestPhase25" tests/test_web_dashboard.py -k "TestPhase25" -rxX -q` | ✅ | ✅ green |
| 25-02-T1 | renderer-consolidation | 1 | D-02: CSS/JS in assets.py single source of truth | T-25-02-02 | Constants not re-exported from dashboard.py loops | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25Fonts" -q` | ✅ | ✅ green |
| 25-02-T2 | renderer-consolidation | 1 | D-01/D-02: nav.py stubs created; marker forces regen | T-25-02-01 | Stub emits no user-controlled output | unit | `.venv/bin/pytest tests/test_dashboard.py tests/test_web_app_factory.py -q` | ✅ | ✅ green |
| 25-03 | two-axis-nav | 2 | D-01/D-03/D-04/D-18: two-axis nav with ARIA + HTMX | T-25-03-01 | market_id html.escape'd | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25ActiveTab" -q` | ✅ | ✅ green |
| 25-03 | two-axis-nav | 2 | D-04: market strip hidden (/account → zero DOM) | — | No DOM surface when hidden | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25ActiveTab" -q` | ✅ | ✅ green |
| 25-03 | two-axis-nav | 2 | OR-03: first-market fallback insertion order | — | Deterministic; no hardcoded SPI200 preference | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25" -q` | ✅ | ✅ green |
| 25-04 | routes-cookie | 2 | D-01..D-05: GET /markets/{M}/{fn} routes registered | T-25-04-01 | market_id allowlist + 404 on miss | integration | `.venv/bin/pytest tests/test_web_app_factory.py -k "TestPhase25MarketRoutes" -q` | ✅ | ✅ green |
| 25-04 | routes-cookie | 2 | D-05: selected_market cookie; no HttpOnly; SameSite=Lax | T-25-04-01 | Allowlist ^[A-Z0-9_]{2,20}$ on write (Plan 26-07 R7) | integration | `.venv/bin/pytest tests/test_web_app_factory.py -k "TestPhase25SelectedMarketCookie" -q` | ✅ | ✅ green |
| 25-05 | add-market-chip | 2 | D-16/D-17: + Add market chip; buried link removed | T-25-05-01 | hx-post to known endpoint; no open redirect | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25AddMarket" -q` | ✅ | ✅ green |
| 25-05 | add-market-chip | 2 | D-16: chip HTMX trigger strips target | — | hx-post /markets; hx-swap target verified | integration | `.venv/bin/pytest tests/test_web_app_factory.py -k "TestPhase25AddMarketHXTrigger" -q` | ✅ | ✅ green |
| 25-06 | status-strip | 2 | D-06/D-07/OR-01/OR-02: status strip rendered server-side | T-25-06-01 | render_status_strip escapes state fields | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25Countdown" -q` | ✅ | ✅ green |
| 25-06 | status-strip | 2 | D-06: /status-strip endpoint returns fragment HTML | T-25-06-01 | Auth-gated; 401 without header | integration | `.venv/bin/pytest tests/test_web_dashboard.py -k "TestPhase25StatusStripEndpoint" -q` | ✅ | ✅ green |
| 25-06 | status-strip | 2 | D-08: AWST label present; AEST absent | — | Correct tz literal | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25Countdown" -q` | ✅ | ✅ green |
| 25-07 | empty-state-collapse | 3 | D-09: last_run is None → 0 trace tables + onboarding card | — | No stale signal data on first run | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25FirstRun" -q` | ✅ | ✅ green |
| 25-07 | empty-state-collapse | 3 | D-10: stats bar hidden until closed_paper + closed_live ≥ 1 | — | No confusing zero-trade stats | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25StatsBar" -q` | ✅ | ✅ green |
| 25-07 | empty-state-collapse | 3 | D-11: equity chart hidden until ≥5 distinct (date,value) tuples | T-25-07-01 | XSS escape only fires when chart renders | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25Equity" -q` | ✅ | ✅ green |
| 25-08 | settings-fieldsets | 3 | D-12: 3 fieldsets — Entry rules / Risk / Direction | — | Scannable form layout | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25Settings" -q` | ✅ | ✅ green |
| 25-08 | settings-fieldsets | 3 | D-13: helper text drafted per 25-helper-text-locked.md | — | Field semantics surfaced to operator | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25Settings" -q` | ✅ | ✅ green |
| 25-09 | mobile-a11y | 4 | D-15: --fs-body 16px; token scale 16/14 | — | Readable on mobile | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25Fonts" -q` | ✅ | ✅ green |
| 25-09 | mobile-a11y | 4 | D-20: wide tables in overflow-x:auto region | — | No horizontal scroll trapping | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25WideTable" -q` | ✅ | ✅ green |
| 25-09b | component-a11y-wiring | 4 | D-19: aria-expanded sync; focus rings; status-dot glyphs; label-for; zero inline color | T-25-09b-01 | No color-only signal status; ARIA correct | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25NoInlineColor or TestPhase25LabelForAudit or TestPhase25StatusDotDerivation" -q` | ✅ | ✅ green |
| 25-10 | terminology-version | 4 | D-21: "Record paper trade" / "Open live position" / Account terminology unified | — | No ambiguous action labels | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25ButtonRename" -q` | ✅ | ✅ green |
| 25-10 | terminology-version | 4 | D-22: strategy version from state.signals[*].strategy_version (no hardcoded v1.0.0 / v1.1.0) | — | Correct version shown to operator | unit | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25StrategyVersion" -q` | ✅ | ✅ green |
| 25-11 | gap-closure | 5 | D-14: Market Test override fields show inherited Settings defaults as placeholder | T-25-11-01 | Placeholder inheritance; no silent blank override | unit | `.venv/bin/pytest tests/test_dashboard.py::TestPhase25MarketTestPlaceholders -q` | ✅ | ✅ green |
| 25-11 | gap-closure | 5 | D-11 (security): test_chart_payload_escapes_script_close — ≥5 equity points seed; </script> escape exercised | T-25-07-01 | XSS defense branch reached | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_chart_payload_escapes_script_close -q` | ✅ | ✅ green |
| 25-11 | gap-closure | 5 | D-11 (copy): equity chart empty-state placeholder matches post-D-11 copy | — | Correct copy visible to operator | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_equity_chart_empty_state_placeholder -q` | ✅ | ✅ green |
| 25-11 | gap-closure | 5 | D-11 (golden): tests/fixtures/dashboard/golden_empty.html regenerated after Phase 25 render drift | — | Golden snapshot current | snapshot | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_empty_state_matches_committed -q` | ✅ | ✅ green |
| cross | D-06 two-axis nav | N/A | Two-strip WAI-ARIA nav: function × market; roving tabindex; arrow-key JS | T-25-03-01 | No injection via tab ID; aria-current="page" correct | unit+integration | `.venv/bin/pytest tests/test_dashboard.py -k "TestPhase25ActiveTab" tests/test_web_app_factory.py -k "TestPhase25MarketRoutes" -q` | ✅ | ✅ green |
| cross | multi-tab persistence | N/A | URL canonical for market; cookie selected_market set on every market-scoped page; Phase 26 scoping closure | T-25-04-01 | selected_market regex-validated before write | integration | `.venv/bin/pytest tests/test_web_app_factory.py -k "TestPhase25SelectedMarketCookie or TestPhase26MarketScoping" -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Coverage Gaps

No gaps at phase close. Four gaps found during initial 2026-05-06 verification (D-14, three D-11 test failures) were all closed by Plan 25-11 before the phase was marked verified. Re-verification 2026-05-07 score: 22/22 decisions verified.

**Multi-tab scoping leakage (Phase 25 context):** Phase 26 plans 26-04/26-05 closed a renderer gap where `active_market` was dropped between `_build_render_context` and leaf renderers. That gap was not surfaced by Phase 25's own tests (tests verified route existence and cookie attributes but not per-market rendered content). `TestPhase26MarketScoping` (4 tests, `tests/test_web_app_factory.py:618`) now covers the scoping contract. Considered a Phase 26 finding applied retroactively as D-03 closure; credited as verified here.

---

## Wave 0 Requirements

Existing infrastructure (pytest 8.x, `tests/` testpath, `.venv/bin/pytest`) sufficient. Plan 25-01 (test scaffolding) established `_empty_state()` and `_render_to_str()` module-level helpers in `test_dashboard.py` — reused by all subsequent Phase-25 test classes.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mobile responsive wide tables + stacked-row @600px | D-20 | CSS render parity not asserted by unit tests | View dashboard on 375px-wide viewport; confirm table-scroll wrapper and stacked layout |
| HTMX market-tab swap in browser | D-01/D-03 | JS HTMX swap requires live browser | Click market tab; confirm panel swaps without full-page reload; URL updates |
| Status strip countdown AWST accuracy | D-07/D-08 | JS Date.UTC arithmetic requires browser runtime | View status strip; confirm countdown shows correct h/m until next 08:00 AWST |
| D-14 placeholder UX in Market Test tab | D-14 | Visual inspection of placeholder text | Open Market Test tab; confirm 7 override fields show inherited Settings values as grey placeholder text |

---

## Validation Sign-Off

- [x] All 30 SC items have automated verify commands
- [x] Sampling continuity: every plan-task has its own test class or test set
- [x] Wave 0 not required — existing infra sufficient; helpers added by Plan 25-01
- [x] No watch-mode flags
- [x] Feedback latency < 15 s for Phase-25 subset
- [x] `nyquist_compliant: true` set in frontmatter
- [x] SUMMARY-claim verification done per LEARNING 2026-05-06 — no row trusts SUMMARY without grep confirmation

**Approval:** approved 2026-05-10 (retroactive reconstruction; 25-VERIFICATION.md re-verified 22/22 at 2026-05-07)

---

## Validation Audit 2026-05-10

| Metric | Count |
|--------|-------|
| Plans audited | 12 (25-01 through 25-11 including 25-09b) |
| SC items mapped | 30 |
| Covered | 30 |
| Deferred | 0 |
| Gaps found at phase close | 0 |
| Test classes verified in code | 15 (TestPhase25FirstRun, StatsBar, Equity, Settings, Fonts, AddMarket, ActiveTab, NoInlineColor, WideTable, ButtonRename, StrategyVersion, Countdown, StatusDotDerivation, LabelForAudit, MarketTestPlaceholders) |
| Full-suite tests at phase close | 1794 |

Reconstructed from SUMMARY.md artifacts, 25-VERIFICATION.md (2026-05-07), and grep-verification of test class names in tests/test_dashboard.py, tests/test_web_app_factory.py, tests/test_web_dashboard.py.
