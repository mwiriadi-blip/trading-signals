---
phase: 28-v1-2-uat-closure
plan: 06
status: complete
status_qualifier: partial-with-phase-29-handoff
completed: 2026-05-10
---

# Plan 28-06 — Live UAT Pass + 28-VERIFICATION.md

## Total UAT runs (incl. retries) per scenario

11 evidence rows. Per CONTEXT D-17 retry policy, retries are scoped to flake recovery only — every FAIL here was deterministic on attempt 1, so no scenario was retried beyond attempt 1 once the substrate was correct.

| UAT | Attempts | Final |
|-----|---------:|:------|
| UAT-17-1 ATR handcalc | 5 (substrate evolution) | FAIL (real Phase 29 finding) |
| UAT-17-2 iOS Safari tap-to-toggle | 1 (operator) | FAIL (real Phase 29 finding) |
| UAT-17-3 cookie persistence | 5 (substrate evolution) | PASS |
| UAT-23-1 live yfinance CLI | 2 (re-run for proper rc capture) | FAIL (real Phase 29 finding) |
| UAT-23-2 /backtest visual | 5 | PASS |
| UAT-26-1 cold-start | 5 | FAIL (real Phase 29 finding) |
| UAT-26-2 multi-tab signals (×2) | 5 | PASS |
| UAT-26-3 multi-tab settings (×2) | 5 | PASS |
| UAT-26-4 multi-tab market-test (×2) | 5 | PASS |
| UAT-26-5 panel-swap PATCH | 5 | PASS |
| UAT-26-6 header session widget | 5 | PASS |

The "5 attempts" count for MCP scenarios reflects 5 full UAT pass invocations during plan 06: run-1 (no auth — all 401), run-2 (auth header injected, selector-blocked), run-3 (selectors tightened, CORS broke 2 tests), run-4 (route handler narrowed by glob, glob mismatch broke 1), run-5 (callable host filter — final stable result).

## Final tally

- **PASS:** 7 of 11 evidence rows (UAT-17-3, UAT-23-2, UAT-26-2 ×2, UAT-26-3 ×2, UAT-26-4 ×2, UAT-26-5, UAT-26-6).
- **FAIL:** 4 of 11 evidence rows (UAT-17-1 ATR drift, UAT-17-2 iOS Safari, UAT-23-1 yfinance, UAT-26-1 cold-start JS error).
- **SKIP:** 0.
- **Status:** `partial` (per CONTEXT D-18).
- **Score:** `4 FAIL of 8 scenarios verified (7 of 11 evidence rows PASS)`.

Note: UAT-2/3/4 collapse 2 parametrize-pairs each into 1 conceptual scenario each, so 11 evidence rows = 8 conceptual scenarios per CONTEXT D-09 / D-11.

## Phase 29 hand-off (FAIL rows)

In suspected-impact order:

1. **UAT-26-1: chart inline JS y-axis brace bug** at `dashboard_legacy/section_renderers.py:218-220`. Concrete file:line + repro. One-line fix candidate. Visible to every authenticated user on cold-start.
2. **UAT-23-1: live yfinance signal-engine regression** — 0 trades over 5y on live data. Wide blast radius. Suspected yfinance Volume schema drift OR signal-engine regression post v1.2 cut. Investigate before v1.3 substance.
3. **UAT-17-1: trace-panel ATR(14) hand-reproducibility.** Engine computes ATR over full history; trace shows 40 bars; recalc-from-40 produces different Wilder seed. Either expose engine's seed-at-window-start in the panel, OR show enough OHLC bars to seed Wilder from scratch.
4. **UAT-17-2: iOS Safari trace-panel reload state loss.** Desktop Chrome PASSES; iOS Safari FAILS. Suspected `Secure`+`SameSite=Lax` cookie interaction on iOS, OR backend not reading `tsi_trace_open` to seed `<details open>` server-side.

## Test-suite gate

`.venv/bin/python -m pytest -q` → **2030 passed, 12 deselected in 155.49s** at HEAD `379d919`.

The 12 deselected tests are the UAT specs (gated by `@pytest.mark.uat` per plan 28-01's `addopts = '... -m "not uat"'`). Default-suite count unchanged from pre-Phase-28 baseline.

## Substrate fixes applied during plan 06 (recorded for completeness, NOT Phase 29 hand-offs)

Two substrate gaps were closed in-flight rather than punted to Phase 29 — they are test-substrate work, not v1.2.1 patch wrap work:

- **Auth wiring missing in `tests/uat/conftest.py`.** Plan 28-01's substrate provided a `uat_credentials()` helper that no spec used; production returned 401 to every UAT request. Plan 06 added `.env.uat` (gitignored) + same-origin `page.route()` header injection. Commit `7aaf27b`. Refined to a callable host filter to fix CDN CORS preflight + JS pageerror leakage. Commit `379d919`.
- **Selector contracts vs. live DOM.** Wave-2 specs assumed `[data-trace-payload]`, `[data-trace-atr]`, `[data-active-market]`, `[data-market-panel]` — none exist on the production droplet. Plan 06 tightened to actual attributes (`details.trace-disclosure[data-instrument]`, `[data-market-id][aria-current="page"]`, `.trace-ohlc-table`/`.trace-indicators-table`). Commit `379d919`.

## Files modified by plan 06

- `.gitignore` (added `.env.uat`)
- `tests/uat/conftest.py` (auth wiring + route handler)
- `tests/uat/test_uat_17_atr_handcalc.py` (selector tightening)
- `tests/uat/test_uat_17_cookie_persistence.py` (selector tightening)
- `tests/uat/test_uat_23_backtest_visual.py` (style/script-block stripping)
- `tests/uat/test_uat_26_coldstart.py` (selector tightening)
- `tests/uat/test_uat_26_multitab.py` (selector tightening + UAT-5 explicit auth header)
- `.planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` (NEW — closure artefact)

## Deviations

- **Rule 1 (plan-content vs. live-DOM reality):** Wave-2 specs were written before any live-DOM probe; many assumed `[data-trace-payload]` / `[data-active-market]` etc. Plan 06 tightened against the actual production HTML. The contract is now the actual DOM, not the imagined DOM.
- **CONTEXT D-16 boundary:** Phase 28 is "mechanical UAT closure" with fixes routed to Phase 29. Plan 06 closed two substrate gaps (auth + selectors) inline because those are test-infrastructure work, not v1.2.1 app patches — Phase 29's scope is the production code finds, not the UAT-spec scaffolding.
