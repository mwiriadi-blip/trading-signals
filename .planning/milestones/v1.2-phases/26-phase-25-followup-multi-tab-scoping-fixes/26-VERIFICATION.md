---
phase: 26-phase-25-followup-multi-tab-scoping-fixes
verified: 2026-05-10T00:00:00+08:00
status: passed
score: 8/8 plans verified, 10/10 UAT tests resolved
overrides_applied: 0
test_suite: 1794/1794 green at last full-suite run (Plan 26-08, 110.25s)
verification_mode: retroactive
notes: |
  Phase 26 was executed and effectively closed on 2026-05-07 with 8/8 plan SUMMARYs,
  26-UAT.md (10 tests resolved: 2 auto-passed + 8 skipped-with-reason citing
  automated-coverage equivalents), 26-DEBT.md (2 documented deferrals to v1.3),
  26-CONTEXT.md, and 26-PATTERNS.md. The only artifact missing was this
  VERIFICATION.md — produced retroactively during /gsd-verify-work 26 on
  2026-05-10 as part of the v1.2 milestone close.

  No code changes were made. UAT frontmatter was flipped partial → complete
  (status was stale; per workflow rules with pending=0, blocked=0,
  skipped_no_reason=0, the correct status was always 'complete').
---

# Phase 26: Phase 25 Follow-up — Multi-tab Market Scoping Fixes — Verification Report (Retroactive)

**Phase Goal:** Fix 4 BROKEN items (multi-tab scoping non-functional, template-placeholder leak → 401s, header session widget unresolved, 3 red deploy tests), 7 RISKY items (cache invalidation, mixed return types, dead nav params, etc.), and 5 CLEANUP items (incl. `auth.json` audit + `.gitignore`) from the 2026-05-07 review of Phase 25.

**Verified:** 2026-05-10 (retroactive — work completed 2026-05-07)
**Status:** PASSED
**Verification mode:** Retroactive close during v1.2 milestone audit

## Why retroactive

The phase shipped on 2026-05-07 with all artifacts except VERIFICATION.md. The operator deferred browser-based UAT to deploy-time smoke (documented in 26-UAT.md), and the 26-UAT.md frontmatter was left at `status: partial` rather than being updated to `complete` when all tests resolved. This created a procedural gap surfaced by the v1.2 milestone audit on 2026-05-10. This file closes the gap; no code or test changes are introduced.

## Plan completion

| Plan | Subject | Status | Evidence |
|------|---------|--------|----------|
| 26-01 | Secret audit + .gitignore hardening | complete | 26-01-SUMMARY.md |
| 26-02 | Deploy-test regex fix (3 red tests → green) | complete | 26-02-SUMMARY.md |
| 26-03 | Failing-test scaffolding (xfail markers for B1/B2/B3 + PATCH-from-swap) | complete | 26-03-SUMMARY.md |
| 26-04 | Template `_substitute` helper (B2/B3/PATCH xfails → green) | complete | 26-04-SUMMARY.md |
| 26-05 | Active-market scoping (B1 xfail → green; TestPhase26MarketScoping 4/4 green) | complete | 26-05-SUMMARY.md |
| 26-06 | Renderer API cleanup | complete | 26-06-SUMMARY.md |
| 26-07 | Cache + cookie hardening (R1 stale-marker, R5 dict-shape, R6 active_function query, R7 cookie regex) | complete | 26-07-SUMMARY.md |
| 26-08 | Dead-code + doc cleanup (full suite 1794 passed in 110.25s) | complete | 26-08-SUMMARY.md |

## UAT outcome (from 26-UAT.md)

| # | Test | Result | Coverage |
|---|------|--------|----------|
| 1 | Cold start smoke | skipped | Operator deferred to deploy-time; 1794 pytest baseline |
| 2 | Multi-tab market scoping `/markets/{M}/signals` | skipped | TestPhase26MarketScoping (4 xfail → green, Plan 26-05) |
| 3 | Multi-tab market scoping `/markets/{M}/settings` | skipped | TestPhase26MarketScoping (same suite) |
| 4 | Multi-tab market scoping `/markets/{M}/market-test` | skipped | TestPhase26MarketScoping (same suite) |
| 5 | PATCH from panel-swapped form (no 401) | skipped | TestPhase26PanelPatchSurvives (xfail → green, Plan 26-04) |
| 6 | Header session widget renders correctly | skipped | TestPhase26HeaderSessionWidget + TestPhase26PlaceholderLeak (Plan 26-04) |
| 7 | Markets-strip works without Referer | skipped | Code audit: nav.py:103-110 hx-get with `?active_function={fn_q}`; allowlist on read |
| 8 | New market shows "Signal as of: never" | skipped | Code audit: web/routes/markets.py:158 writes 7-key dict matching run_daily_check |
| 9 | pytest full suite green | **pass** (auto) | 1794 passed in 110.25s (Plan 26-08) |
| 10 | Audit greps clean | **pass** (auto) | 4 grep gates clean (Plans 26-07/26-08) |

**Resolution:** 2 passed (auto) + 8 skipped-with-reason (automated coverage documented per skip) = 10/10 resolved. Per gsd-verify-work workflow rules (pending=0, blocked=0, skipped_no_reason=0), UAT status auto-resolves to `complete`.

## Cross-phase wiring (xfail flips)

Plans 26-03 / 26-04 / 26-05 used a deliberate test-first pattern: scaffolded xfail tests in Plan 26-03 that fail against pre-Phase-26 code, then flipped them green in 26-04 (B2/B3/PATCH-from-swap) and 26-05 (B1 multi-tab scoping). Each xfail-flip serves as the regression contract for the corresponding browser UAT scenario. This is why operator-deferred browser checks remain auto-covered: the xfail flip *is* the test that the live browser would have run, asserted at the request/response layer.

## Test suite

`.venv/bin/pytest -q` → **1794 passed in 110.25s** at the Plan 26-08 closure commit. Full suite has since grown to 2006 (Phase 27) and is currently green at HEAD per Phase 27 verification. No Phase 26 regressions introduced.

## Acknowledged Gaps (Tech Debt — deferred to v1.3)

Documented in 26-DEBT.md, restated here for audit traceability:

- **C5 Lazy-regen siblings:** `dashboard_renderer.api.render_dashboard_files` writes 4 sibling HTMLs on every state mutation (~5× I/O per run). Lazy-regen path is half-implemented in `_serve_dashboard_page`; complete in v1.3.
- **R5 Defensive `isinstance(int)` branch retained:** Plan 26-07 R5 fixed prod write paths to dict-shape, but renderer's defensive int-sentinel branch in `dashboard_renderer/components/signals.py:35-39` is kept because 38 test fixtures still seed `state['signals']['SPI200'] = 0`. Fold int-sentinel removal into the next renderer-touching phase.
- **Operator deploy-time smoke (UAT 1-8):** Browser-based UAT scenarios 1-8 were operator-deferred to opportunistic deploy-time runs. Production at `signals.mwiriadi.me` has been running cleanly post-deploy (daily emails since 2026-04-29; Phase 27 cleanup work since 2026-05-08).

## Conclusion

Phase 26 satisfies its goal: 4 BROKEN items closed, 7 RISKY items addressed, 5 CLEANUP items shipped, full suite stays green at 1794 with 4 xfail tests flipped + 3 deploy-test fixes. No requirements were assigned to Phase 26 (it was post-Phase-25 quality work). Phase is verified PASSED retroactively, completing the v1.2 milestone artifact set.
