---
phase: 28-v1-2-uat-closure
verified: 2026-05-10T13:30:00+08:00
status: partial
score: 7 PASS + 1 DEFERRED-to-29.5 of 8 scenarios (3 of 4 Phase 28 FAILs resolved by Phase 29)
overrides_applied: 0
test_suite: 2030/2030 green at HEAD (379d919, 2m35s)
notes: |
  Phase 28 closes DEBT-01 by signing off the 8 deferred v1.2 UAT scenarios
  from Phases 17, 23, and 26. Verification target: live production droplet
  https://signals.mwiriadi.me. Persisted Playwright specs under tests/uat/
  gated by `@pytest.mark.uat` (run with `pytest -m uat`). Phase 23 live
  yfinance CLI scenario is intentionally NOT persisted as a test (D-15);
  run-once via Bash. iOS Safari row is operator-driven (D-03).

  Status `partial` is an intentional vocabulary extension over the Phase 27
  precedent (which only used `passed`). Per D-18, `partial` is more honest
  than `passed-with-deferrals` but does not block the v1.3 substance roadmap
  the way `failed` would. FAIL rows below carry symptom + suspected layer +
  repro command per D-19 — Phase 29 reads this file as input per D-20.

  Substrate fix during plan 06: tests/uat/conftest.py originally had no
  auth wiring; the production droplet returned 401 to every UAT request.
  Plan 06 wired WEB_AUTH_SECRET injection via .env.uat (gitignored) +
  same-origin route handler. Recorded in commits 7aaf27b and 379d919.

  Closure update 2026-05-10: see ## Phase 29 Closure section. UAT-23-1 deferred to Phase 29.5.
---

# Phase 28: v1.2 UAT Closure — Verification Report

**Phase Goal:** Operator can verify all 8 deferred v1.2 UAT scenarios end-to-end against the production droplet + browser/phone, and sign them off so v1.2 closes cleanly before v1.3 substance lands.

**Verified:** 2026-05-10T13:30:00+08:00
**Status:** PARTIAL — 4 FAIL of 8 scenarios

## Test-suite gate

`.venv/bin/python -m pytest -q` → **2030/2030 green at HEAD (`379d919`, 2m35s)**. UAT specs (under `tests/uat/`) are excluded by default via `addopts = '... -m "not uat"'` in `pyproject.toml` — they are run only via `pytest -m uat`. Default-suite count is unchanged from the pre-Phase-28 baseline.

## Phase 17 Scenarios

| Scenario | Source | Mode | Status | Evidence |
|----------|--------|------|--------|----------|
| ATR(14) hand-recalc to 1e-6 | 17 / UAT-1 | MCP | FAIL | symptom: ATR drift 1.22730353 — displayed=88.888811 vs 40-bar-window-recalc=87.66150746868470815084506843 (period=14, ohlc_bars=40); suspected: trace panel shows 40 OHLC bars but `signal_engine` computes ATR over full history — Wilder seed at the start of the displayed window does not match engine's seed many bars earlier; repro: `pytest -m uat tests/uat/test_uat_17_atr_handcalc.py` |
| ATR(14) hand-recalc to 1e-6 | 17 / UAT-1 | MCP | PASS (Phase 29 closure — 29-11) | engine ATR seed exposed via signal_engine.atr_seed_for_window + sig['atr_seed'] persistence (commit af93de1); hand-recalc from persisted seed converges within 1e-6; regression: tests/test_trace_atr_seed.py::test_handcalc_converges_to_displayed_atr_within_1e-6; repro: .venv/bin/pytest tests/test_trace_atr_seed.py -q |
| iOS Safari tap-to-toggle | 17 / UAT-2 | Manual | FAIL | Operator (iPhone Safari, 2026-05-10): tap toggled, reload does NOT preserve state — panel minimises and operator has to re-tap "Show calculations". Desktop Chrome via Playwright PASSES the same flow (UAT-17-3 below) — iOS-specific divergence; suspected: cookie-write inline JS at root.html script[0] (`document.cookie = 'tsi_trace_open=...; Secure'`) — likely Secure+SameSite=Lax interaction on iOS Safari, OR backend not reading `tsi_trace_open` to seed `<details open>` on render; repro: iPhone Safari → `/markets/SPI200/signals` → tap "Show calculations" → pull-to-refresh → panel collapsed |
| iOS Safari tap-to-toggle | 17 / UAT-2 | Manual | PASS (Phase 29 closure — 29-12) | server-side <details open> rendering from tsi_trace_open cookie (commit 8e83a44); two root causes fixed: _resolve_trace_open used static frozenset (now regex allowlist) + _TRACE_OPEN_PLACEHOLDER was static dict (now dynamic shim); regression: tests/test_trace_details_open_serverside.py::test_details_open_when_cookie_includes_instrument; operator manual re-test: PASS — iPhone 17 Pro Max, 2026-05-10 |
| Cookie persistence across reload | 17 / UAT-3 | MCP | PASS | toggle flipped (closed→open); cookie `tsi_trace_open` written with `SPI200` value; state preserved across `page.reload()`; tablist (auth indicator) still rendered. Desktop Chrome only — iOS Safari divergence captured separately under UAT-17-2. |

## Phase 23 Scenarios

| Scenario | Source | Mode | Status | Evidence |
|----------|--------|------|--------|----------|
| Live yfinance 5y backtest CLI | 23 / UAT-1 | CLI | FAIL | rc=1; gate=triggered (cum_return=0.00% ≤ 100% threshold); SPI200=1265 bars 0 trades, AUDUSD=1300 bars 0 trades; tail: `[Backtest] FAIL (>100% threshold)`; symptom: zero trades over 5 years on live data; suspected: yfinance schema drift (Volume column shape) breaking RVol gate, OR signal-engine regression on live (vs fixture) data; repro: `python -m backtest --years 5` |
| Live yfinance 5y backtest CLI | 23 / UAT-1 | CLI | DEFERRED to Phase 29.5 | spike (29-13) root cause: backtest/cli.py calls simulate() with no settings= arg → n_contracts=0 on every signal; fix shape TIGHT (1 call site) but operator chose to defer to Phase 29.5 to keep Phase 29 scope clean; full RCA at .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md; Phase 29.5 context at .planning/phases/29-5-yfinance-regression-fix/29-5-CONTEXT.md; original FAIL evidence preserved above |
| /backtest browser visual smoke | 23 / UAT-2 | MCP | PASS | no template-leak literals (`{{`, `}}`, `Undefined`, `None None`) outside `<style>`/`<script>` blocks; inline `<style>` present (asset pipeline OK); 96,743-byte rendered HTML. |

## Phase 26 Scenarios

| Scenario | Source | Mode | Status | Evidence |
|----------|--------|------|--------|----------|
| Cold-start smoke | 26 / UAT-1 | MCP | FAIL | symptom: JS `pageerror` on first paint: `missing ) after argument list`; suspected: `dashboard_legacy/section_renderers.py:218-220` — equityChart inline JS has malformed y-axis brace structure (`y: { ticks: {...} }, grid: {...} }` closes `y` after `ticks` and leaves `grid` as a stray sibling with an unmatched closing `}`); repro: `pytest -m uat tests/uat/test_uat_26_coldstart.py`. Selectors render OK (market-strip + trace-disclosure both present); the failure is the JS error, not chrome rendering. |
| Cold-start smoke | 26 / UAT-1 | MCP | PASS (Phase 29 closure — 29-02) | brace-rebalance fix at dashboard_legacy/section_renderers.py:218-220 (commit 73a8bc9); zero pageerror on first paint locked by tests/uat/test_uat_26_coldstart.py::test_no_pageerror_on_coldstart; repro: .venv/bin/pytest -m uat tests/uat/test_uat_26_coldstart.py |
| Multi-tab signals scoping | 26 / UAT-2 | MCP | PASS | SPI200 + AUDUSD scoping correct via `[data-market-id][aria-current="page"]`; no cross-market leak. |
| Multi-tab settings scoping | 26 / UAT-3 | MCP | PASS | SPI200 + AUDUSD settings scoped correctly. |
| Multi-tab market-test scoping | 26 / UAT-4 | MCP | PASS | SPI200 + AUDUSD market-test scoped correctly. |
| Panel-swap PATCH no 401 | 26 / UAT-5 | MCP | PASS | PATCH `https://signals.mwiriadi.me/markets/settings` returned non-401 (auth header survived form context); validation-layer 4xx is acceptable per the spec contract. |
| Header session widget | 26 / UAT-6 | MCP | PASS | `<header>` rendered with non-empty content; no literal placeholder leaks (`{{`, `}}`, `Undefined`, `WEB_AUTH_SECRET`). |

## Hand-off to Phase 29

Phase 29 (v1.2.1 Retroactive Patch Wrap + Validation Sweep) reads this file as required input per D-20. The 4 FAIL rows above each carry symptom + suspected layer + repro command — those become Phase 29 leads on top of its existing DEBT-02/03/04 + OPS-02 scope.

**Phase 29 leads from this verification (in suspected-impact order):**

1. **`dashboard_legacy/section_renderers.py:218-220` — equityChart inline JS y-axis brace bug.** Concrete file:line + repro. Root cause is pasted into UAT-26-1 evidence cell; one-line fix candidate. Visible to every authenticated user on cold-start.
2. **Live yfinance signal-engine regression (0 trades over 5y).** Wide blast radius — the signal pipeline isn't generating trades on live data. Could be yfinance Volume schema change OR a regression introduced post v1.2 cut. Investigate before any v1.3 substance lands.
3. **Trace-panel ATR(14) hand-reproducibility (UAT-17-1).** The trace panel shows 40 OHLC bars but the displayed ATR was computed against full history; recalc from 40 bars produces a different Wilder seed. Either (a) expose the engine's ATR seed-at-window-start in the trace panel so a hand-recalc can pick up from there, or (b) show enough OHLC bars to seed Wilder ATR(14) from scratch (≥ ~28 bars to produce a seed plus ≥ ~50–100 to converge).
4. **iOS Safari trace-panel reload state loss (UAT-17-2).** Desktop passes, iOS fails. Suspected `Secure`+`SameSite=Lax` cookie interaction on iOS Safari, OR backend not reading `tsi_trace_open` to seed `<details open>` on server-side render (currently relies on client-side JS to re-open after load — fragile on iOS).

## Substrate notes (plan 06)

Two substrate gaps were closed during plan 06 — neither is a Phase 29 hand-off, both are recorded here for traceability:

- **Auth wiring missing in `tests/uat/conftest.py`.** Plan 28-01's UAT substrate provided a `uat_credentials()` helper that no spec used; the production droplet returned 401 to every request. Plan 06 added `.env.uat` (gitignored) loader + same-origin `page.route()` header injection. Commits `7aaf27b`, `379d919`.
- **Selector contracts vs. live DOM.** Wave-2 specs assumed `[data-trace-payload]`, `[data-trace-atr]`, `[data-active-market]`, `[data-market-panel]` — none of which exist. Plan 06 tightened to actual production attributes (`details.trace-disclosure[data-instrument]`, `[data-market-id][aria-current="page"]`, `.trace-ohlc-table`/`.trace-indicators-table`). Commit `379d919`.

---

*DEBT-01 partially discharged: 7 PASS, 4 FAIL. v1.2 sign-off proceeds with Phase 29 absorbing the FAIL set.*

## Phase 29 Closure

Phase 29 (v1.2.1 Retroactive Patch Wrap + Validation Sweep) closed against this VERIFICATION report on 2026-05-10. Disposition of Phase 28 FAIL rows:

- **UAT-26-1 cold-start JS:** PASS — resolved by Plan 29-02 (commit `73a8bc9`); regression test `tests/uat/test_uat_26_coldstart.py::test_no_pageerror_on_coldstart`.
- **UAT-17-1 ATR(14) hand-recalc:** PASS — resolved by Plan 29-11 (commit `af93de1`); engine ATR seed exposure + persistence + 1e-6 hand-recalc convergence test `tests/test_trace_atr_seed.py::test_handcalc_converges_to_displayed_atr_within_1e-6`.
- **UAT-17-2 iOS Safari `<details open>`:** PASS — resolved by Plan 29-12 (commit `8e83a44`); server-side cookie-driven `<details open>` rendering + integration test `tests/test_trace_details_open_serverside.py`; operator iPhone 17 Pro Max re-test: PASS 2026-05-10.
- **UAT-23-1 live yfinance 5y backtest:** DEFERRED to Phase 29.5 — spike (Plan 29-13) identified root cause: `backtest/cli.py` calls `simulate()` with no `settings=` argument; operator chose escape-29-5 to keep Phase 29 scope clean; RCA at `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md`; Phase 29.5 context at `.planning/phases/29-5-yfinance-regression-fix/29-5-CONTEXT.md`.

`status` remains `partial` (1 of 4 Phase 28 FAILs deferred to Phase 29.5). `score` updated to 7 PASS + 1 DEFERRED-to-29.5 of 8 scenarios.
