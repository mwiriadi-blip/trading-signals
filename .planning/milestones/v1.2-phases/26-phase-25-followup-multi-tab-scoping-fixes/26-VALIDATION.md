---
phase: 26
slug: phase-25-followup-multi-tab-scoping-fixes
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-10
audited: 2026-05-10
---

# Phase 26 — Validation Strategy

> Reconstructed retroactively after phase execution (mechanical retrofit per Phase 29 D-06).
> All 8 plans have automated test coverage; full suite green (1794 passed).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest tests/test_web_dashboard.py tests/test_web_app_factory.py tests/test_deploy_sh.py -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Phase-26 subset command** | `.venv/bin/pytest tests/test_deploy_sh.py tests/test_web_dashboard.py tests/test_web_app_factory.py tests/test_dashboard.py -q` |
| **Estimated runtime** | ~3 s (Phase-26 subset, ~323 tests); ~110 s (full suite, 1794 tests) |

---

## Sampling Rate

- **After every task commit:** Run task-scoped pytest file (~0.2–3 s)
- **After every plan wave:** Run full suite (`pytest -q`)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~3 s for Phase-26 subset

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement / Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|------------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 26-01 | secret-audit-gitignore | 1 | `auth.json` never in git; 10 new `.gitignore` patterns cover agent dirs, macOS cruft | T-26-01 | Credentials never cross git boundary | audit + grep | `git log --all --full-history -- auth.json` (0 commits); `git check-ignore -v` hits all 10 patterns | — | ✅ green (audit) |
| 26-02 | deploy-test-regex-fix | 1 | 3 red deploy tests → green; relax pip-install regex to accept `python -m pip` form | — | No regression on deploy script checks | unit | `.venv/bin/pytest tests/test_deploy_sh.py -q` (41 passed) | ✅ | ✅ green |
| 26-03 | failing-test-scaffolding | 2 | 10 xfail(strict=True) tests scaffold B1/B2/B3/PATCH contracts (RED gate) | T-26-02, T-26-03, T-26-05 | Contract locked before fix; flip-green confirms fix | unit (xfail) | `.venv/bin/pytest tests/test_web_app_factory.py::TestPhase26MarketScoping tests/test_web_dashboard.py -k "Phase26" -v` (10 xfailed) | ✅ | ✅ green (xfail→pass by 26-04/26-05) |
| 26-04 | template-substitute-helper | 2 | `_substitute(content, request) -> bytes` helper eliminates `{{…}}` placeholder leak on all market-scoped routes (B2 + B3); 6 xfails flip green | T-26-02, T-26-03 | Zero `{{…}}` markers in any served HTML; auth secret never leaked as literal | unit (xfail→pass) | `.venv/bin/pytest tests/test_web_dashboard.py -k "Phase26 and not MarketScoping" -v` (6 passed); `TestAuthSecretPlaceholderSubstitution` (4 passed) | ✅ | ✅ green |
| 26-05 | active-market-scoping | 2 | `ctx.active_market` threaded through `_render_page_body` → signal cards / settings tab / market-test tab; 4 xfails flip green (B1) | T-26-04 | Each `/markets/{M}/{fn}` page renders only M's panels; no eyebrow leak | unit (xfail→pass) | `.venv/bin/pytest tests/test_web_app_factory.py::TestPhase26MarketScoping -v` (4 passed) | ✅ | ✅ green |
| 26-06 | renderer-api-cleanup | 3 | `render_dashboard()` split into `render_dashboard_files() -> None` + `render_panel_html() -> str`; `nav_mode` dead param removed; `_render_dashboard_page_nav` deleted (R2, R4) | — | No annotation lie; no `.encode()`-on-`None` NPE path | unit (seam) | `.venv/bin/pytest tests/test_web_app_factory.py tests/test_web_dashboard.py tests/test_dashboard.py -x` (323 passed) | ✅ | ✅ green |
| 26-07 | cache-cookie-hardening | 3 | Per-file `_is_stale_for()` (R1); `add_market` writes dict-shape signal (R5); `active_function` from query param not Referer (R6); `selected_market` cookie regex tightened to `^[A-Z0-9_]{2,20}$` (R7) | T-26-07, T-26-08, T-26-09 | Cookie forgery rejected; Referer-stripped browsers degrade gracefully | unit | `.venv/bin/pytest tests/test_web_dashboard.py tests/test_web_app_factory.py tests/test_dashboard.py -q` (323 passed) | ✅ | ✅ green |
| 26-08 | dead-code-doc-cleanup | 4 | `_render_market_selector` deleted; C4 `25-VERIFICATION.md` re-verified; C5 lazy-regen deferred; `26-DEBT.md` created | — | No dead code references; audit greps clean | audit + grep | `.venv/bin/pytest -q` (1794 passed); grep gates: `_render_market_selector\|_render_dashboard_page_nav` → 0 | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## UAT Coverage Map

Phase 26 UAT items (from `26-UAT.md`) are the primary verification targets. Per Phase 29 D-06 and Phase 28 D-01, these are treated as a regression net; browser-based UAT was operator-deferred to deploy-time smoke (documented in `26-UAT.md`).

| UAT # | Test | Result | Automated Coverage |
|-------|------|--------|--------------------|
| UAT-1 | Cold start smoke | skipped (operator-deferred) | 1794 pytest baseline; no cold-start xfail required |
| UAT-2 | Multi-tab `/markets/{M}/signals` renders only M | skipped (auto-covered) | `TestPhase26MarketScoping` (4 xfail → green, Plan 26-05) |
| UAT-3 | Multi-tab `/markets/{M}/settings` renders only M | skipped (auto-covered) | `TestPhase26MarketScoping` (same suite) |
| UAT-4 | Multi-tab `/markets/{M}/market-test` renders only M | skipped (auto-covered) | `TestPhase26MarketScoping` (same suite) |
| UAT-5 | PATCH from panel-swapped form, no 401 | skipped (auto-covered) | `TestPhase26PanelPatchSurvives` (xfail → green, Plan 26-04) |
| UAT-6 | Header session widget — signout or session note, never placeholder | skipped (auto-covered) | `TestPhase26HeaderSessionWidget` + `TestPhase26PlaceholderLeak` (Plan 26-04) |

**Note:** UAT-1 (cold start) is Deferred — no automated regression test locks the cold-start path. Operator deferred to deploy-time smoke. UAT-2..6 have xfail-flip coverage; the xfail flip *is* the test that the live browser would have run, asserted at the request/response layer (see `26-VERIFICATION.md §Cross-phase wiring`).

---

## Wave 0 Requirements

Existing infrastructure (pytest 8.x, `tests/` testpath, `.venv/bin/pytest`) covered all phase requirements. No new framework install or shared fixture additions needed — per-plan test files created during execution.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cold-start: GET / returns 200/503 with no tracebacks on fresh server start | UAT-1 | Physical server required; no fast equivalent | Kill service, clear dashboard*.html, start fresh, verify no tracebacks |
| Live PATCH from panel-swapped form on production droplet | UAT-5 (deploy-time) | Need live WEB_AUTH_SECRET env; xfail covers request-layer logic | GET `/markets/SPI200/settings`, extract auth secret, PATCH `/markets/settings`, expect 200 |

All other phase behaviors have automated verification.

---

## Coverage Gaps (Deferred)

| Gap | Item | Reason | Plan |
|-----|------|--------|------|
| UAT-1 cold-start | Plan 26 | Physical server required; operator deferred | Deferred to deploy-time smoke — tracked in `26-UAT.md` |
| C5 lazy-regen siblings | Plan 26-08 | Optional polish; not a correctness gap | Deferred to v1.3 — tracked in `26-DEBT.md` |
| R5 int-sentinel renderer branch | Plan 26-07 | 38 test fixtures still seed int sentinels; branch kept | Deferred to next renderer-touching phase — tracked in `26-DEBT.md` |

---

## Validation Sign-Off

- [x] All 8 plans have automated verify commands
- [x] UAT-1..6 mapped to automated coverage or marked Deferred with reason
- [x] Wave 0 not required — existing infra sufficient
- [x] No watch-mode flags
- [x] Full suite green at 1794 passed (Plan 26-08 closure)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-10 (retroactive reconstruction; full suite green at 1794)

---

## Validation Audit 2026-05-10

| Metric | Count |
|--------|-------|
| Plans audited | 8 |
| UAT items mapped | 6 / 6 |
| Coverage gaps | 3 (all Deferred with documented reasons) |
| Blocking gaps | 0 |
| Phase-26 tests passing | 323 / 323 (subset) |
| Total project tests at phase close | 1794 |

Reconstructed from SUMMARY.md and UAT.md artifacts; no auditor agent spawned (no blocking gaps).
