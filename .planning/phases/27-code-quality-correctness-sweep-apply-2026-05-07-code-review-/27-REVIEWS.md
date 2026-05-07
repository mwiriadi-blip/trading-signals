---
phase: 27
reviewers: [codex, opencode]
reviewers_skipped:
  - claude (running inside Claude Code — skipped for independence)
  - gemini (failed — 429 rate limit on gemini-2.5-flash-lite)
  - qwen (failed — no auth type configured)
reviewed_at: 2026-05-07T11:39:21Z
plans_reviewed:
  - 27-01-decimal-money-math-PLAN.md
  - 27-02-http-timeout-standardization-PLAN.md
  - 27-03-api-key-redaction-PLAN.md
  - 27-04-instrument-regex-tightening-PLAN.md
  - 27-05-magic-cost-helper-and-fallback-email-PLAN.md
  - 27-06-deferred-yfinance-and-version-flag-PLAN.md
  - 27-07-naive-datetime-and-migration-contiguity-PLAN.md
  - 27-08-html-escape-audit-PLAN.md
  - 27-09-signal-shape-unification-PLAN.md
  - 27-10-warnings-fifo-rundate-lookahead-tests-PLAN.md
  - 27-11-crash-email-fallback-PLAN.md
  - 27-12-notifier-split-PLAN.md
  - 27-13-main-split-PLAN.md
  - 27-14-dashboard-split-PLAN.md
---

# Cross-AI Plan Review — Phase 27

## Codex Review

**Summary**

The phase is directionally strong: the plans target real correctness, security, and maintainability gaps, and most include concrete tests and verification gates. The biggest weakness is coordination: several "parallel" Wave 1 and Wave 2 plans modify the same high-churn files (`system_params.py`, `state_manager.py`, `notifier.py`, `main.py`, `dashboard.py`) and have implicit dependencies that are not reflected in `depends_on`. The other major risk is scope size: Decimal migration, signal schema migration, and three large file splits are each high-blast-radius changes. They should be sequenced with stricter integration checkpoints.

### Overall Concerns

- **HIGH: Wave dependency graph is inconsistent.**
  - `27-01` says Wave 1 but depends on `27-07`.
  - `27-05` says Wave 1 parallel but depends on `27-01`.
  - `27-11` needs `redact_secret` from `27-03` and HTML escaping from `27-08`, but has no dependency.
  - `27-10` touches `notifier.py` while other Wave 1/2 notifier plans also touch it.

- **HIGH: "Parallel" plans will conflict heavily.**
  - `system_params.py` is touched by 27-01, 27-02, 27-03, 27-04, 27-10.
  - `state_manager.py` is touched by 27-01, 27-07, 27-09.
  - `notifier.py` is touched by 27-02, 27-03, 27-05, 27-08, 27-10, 27-11, then split in 27-12.

- **MEDIUM: Some tests are brittle implementation tests.** Grep/AST tests checking literal strings like `timeout=HTTP_TIMEOUT_S`, `_e(`, "last line is `_assert_migration_chain_contiguous()`", or exact LOC thresholds can create noisy failures during harmless refactors.

- **MEDIUM: Many plans request summary/debt docs.** That is okay because the plans explicitly request them, but it conflicts with the repo rule "NEVER create documentation files unless explicitly requested." Keep these generated artifacts strictly inside the phase planning folder.

- **MEDIUM: Full-suite gates should be explicit after each wave.** Each plan says run `pytest -x`, but the milestone should add wave-level integration gates: after Wave 1, after Wave 2, and after each Wave 3 split.

### Plan-by-Plan Concerns (Codex)

**27-01 Decimal Money Math** — *Risk: HIGH*
- HIGH: Depends on `27-07` despite being Wave 1. Should not be marked parallel with its dependency.
- HIGH: Decimal in state is a broad behavioral change. Existing downstream code may expect floats for JSON, formatting, comparisons, aggregation, chart data.
- HIGH: Migration says store Decimal values as strings, but load path returns Decimal. That changes state shape and may break dashboard JSON/chart serialization.
- MEDIUM: Money-field inventory may be incomplete.
- MEDIUM: `to_aud(None)` / missing values need explicit behavior.
- Suggestion: split into PnL Decimal first, persisted-state Decimal second; explicit `ROUND_HALF_UP` vs default `ROUND_HALF_EVEN`.

**27-02 HTTP Timeout Standardization** — *Risk: MEDIUM*
- MEDIUM: AST test only catches `requests.get(...)`, not `Session.get`, aliases, imported `post`, urllib, or httpx.
- MEDIUM: yfinance session-injection may conflict with 27-06 deferred import.
- LOW: Monkeypatching `session.request` is fragile.
- Suggestion: Make 27-02 depend on or coordinate with 27-06 for yfinance import/session handling.

**27-03 API Key Redaction** — *Risk: LOW–MEDIUM*
- MEDIUM: `prefix[:6] + ...` may still reveal meaningful token prefixes.
- MEDIUM: Grep gate may miss `credential|password|otp|cookie|session_id` variables.
- LOW: Adding unused `redact_secret` import to `data_fetcher.py` for future-proofing creates lint noise.

**27-04 Instrument Regex Tightening** — *Risk: MEDIUM*
- HIGH: "`SPI200X` must not match an SPI200 regex" conflicts with generic `INSTRUMENT_ID_RE` — `SPI200X` is valid under `^[A-Z0-9_]{2,20}$`. Generic ID validation cannot reject unknown instruments.
- Suggestion: Add `KNOWN_MARKET_IDS = {'SPI200', 'AUDUSD'}`; separate "valid syntax" vs "known supported market".

**27-05 Magic Cost Helper And Fallback Email** — *Risk: MEDIUM–HIGH*
- HIGH: Plan depends on 27-01 but is listed Wave 1 parallel.
- MEDIUM: Behavior block says missing `SIGNALS_EMAIL_TO` raises `ValueError`, action says log and return. Pick one.
- MEDIUM: Silent email skip is risky for production. Should append bounded warning/state health marker.

**27-06 Deferred yfinance And --version Flag** — *Risk: LOW–MEDIUM*
- MEDIUM: `<500ms` cold-start may be flaky on CI/slow hosts.
- MEDIUM: Moving `YFRateLimitError` local may break exception references outside the fetch function.
- Suggestion: Add `--version` handling before importing heavy app modules.

**27-07 Naive Datetime And Migration Contiguity** — *Risk: MEDIUM*
- HIGH: Current state may store ISO strings, not datetime objects. "Save state with naive datetime nested somewhere" may be artificial unless save path currently accepts datetimes.
- MEDIUM: "Called at module bottom" source-position test is brittle. Test behavior, not exact source placement.

**27-08 HTML Escape Audit** — *Risk: MEDIUM–HIGH*
- HIGH: Mechanical escaping can double-escape already-safe HTML fragments or break intentional markup.
- MEDIUM: Local `_e` in every component may duplicate policy.
- MEDIUM: Grep for f-strings misses joins, list comprehensions, template constants, `.replace`, prebuilt fragments.
- Suggestion: Classify render variables as escaped text vs trusted HTML fragments; tests for "raw expected markup remains raw".

**27-09 Signal Shape Unification** — *Risk: MEDIUM–HIGH*
- HIGH: Depends on 27-01 and 27-07, so Wave 2 is appropriate, but schema version math must be deterministic after 27-01.
- MEDIUM: "All 38 test sites" may miss fixture JSON files or helper-generated state.
- MEDIUM: Renderer deleting defensive branch means any non-load path constructing state manually can now crash.

**27-10 Warnings FIFO, Run-Date, Lookahead Tests** — *Risk: MEDIUM*
- HIGH: Lookahead plan says "do not fix if bug found", but the phase goal includes correctness. A strict xfail may normalize a serious trading bug — escalate and block the phase rather than defer silently.
- MEDIUM: FIFO canonical-ordering test may overfit implementation.
- MEDIUM: Run-date log test may be hard to invoke without heavy daily-run mocking.

**27-11 Crash Email Fallback** — *Risk: HIGH*
- HIGH: Needs dependency on 27-03 (`redact_secret`) and 27-08 (escaping).
- HIGH: `last_crash.json` may contain secrets in traceback unless redaction is applied before write.
- MEDIUM: Writing to project root conflicts with repo rule against working files in root and may be awkward under systemd cwd.
- MEDIUM: Dashboard reading a fixed relative path may differ between tests, local, and droplet.
- Suggestion: `LAST_CRASH_PATH` config constant under same runtime dir as `state.json`; redact before write.

**27-12 Notifier Split** — *Risk: MEDIUM–HIGH*
- HIGH: "Delete `notifier.py` and create `notifier/`" risky in Python if stale `.pyc`, import resolution, or packaging assumptions exist.
- HIGH: Existing monkeypatch paths like `monkeypatch.setattr('notifier.requests.post', ...)` may break unless re-exported or tests are updated.
- MEDIUM: `templates.py` may still exceed 500 LOC.
- Suggestion: First create package modules while keeping `notifier.py` shim, then delete in a second commit.

**27-13 Main Split** — *Risk: HIGH*
- HIGH: `daily_loop.py` target is estimated ~700 LOC but must be under 500. Plan contradicts the success criterion.
- MEDIUM: `_LAST_LOADED_STATE` re-export may not preserve singleton behavior if imported by value and reassigned.
- MEDIUM: CLI dispatch can easily change behavior around validation, crash boundaries, scheduler setup.
- Suggestion: Split further into `daily_run.py`, `state_actions.py`, `crash_boundary.py`.

**27-14 Dashboard Split** — *Risk: MEDIUM–HIGH*
- HIGH: Byte-identical output is hard after 27-08 escaping and crash-banner changes unless the golden is captured immediately before the split.
- MEDIUM: Test fixture `tests/fixtures/dashboard_canonical.html` may not exist or may become high-maintenance.
- Suggestion: Add route-level smoke tests through FastAPI, not only renderer unit tests; prefer Strategy B unless Strategy A clearly reduces duplication.

### Codex Recommended Sequencing Fix

1. Wave 1A: 27-02, 27-03, 27-04, 27-06, 27-07
2. Wave 1B: 27-01
3. Wave 1C: 27-05
4. Wave 2A: 27-08, 27-10
5. Wave 2B: 27-09, 27-11
6. Wave 3 sequential (not parallel): 27-12 → 27-13 → 27-14

Run full suite + import smoke tests after each sub-wave.

### Codex Final Risk Assessment

**Overall risk: HIGH.** The phase goals are valid and mostly covered, but the current plan set is too optimistic about parallel execution. The functional changes touch shared core files, change persisted state schemas, alter money types, and then perform three large refactors. With dependency corrections, wave-level integration gates, and stricter state/rendering compatibility tests, the phase becomes achievable.

---

## OpenCode Review

### Overall Assessment: HIGH-quality plans with 3 critical location bugs and several gaps

The plans are very well-structured: clear dependency reasoning, explicit threat models, concrete verification steps, and good use of AST-driven regression tests. However, OpenCode found **3 HIGH** issues where plans made incorrect assumptions about where functions live, and **several MEDIUM** issues where existing constants were missed or duplicate coverage wasn't reconciled.

### Plan-by-Plan Findings (OpenCode)

**27-01 — Decimal Money Math**
- MEDIUM: `sizing_engine.py:493` has its own `compute_unrealised_pnl` that takes `cost_aud_open: float` and does `cost_aud_open * n_contracts` at line 525. Plan only mentions `pnl_engine.py`.
- MEDIUM: `sizing_engine._close_position` at line 789 does `close_cost = cost_aud_open * position['n_contracts']` — also money math, also missed.
- MEDIUM: `main.py:1514` does `resolved['cost_aud'] / 2` — Plan's `entry_side_cost` (27-05) should cover it, but the cost_aud/2 grep gate in 27-05 must explicitly include main.py.
- **Most eloquent fix:** Make sizing_engine's `compute_unrealised_pnl` delegate to pnl_engine's version (after Decimal conversion).

**27-02 — HTTP Timeout Standardization**
- HIGH: `notifier.py:106` already defines `_RESEND_TIMEOUT_S = 30`, and `_post_to_resend` at line 1371 already passes `timeout=(5, timeout_s)`. Plan proposes a NEW constant `HTTP_TIMEOUT_S = 30` without acknowledging the existing one. Should either refactor notifier to import canonical `HTTP_TIMEOUT_S`, or scope plan to only add it to `data_fetcher.py`.
- MEDIUM: yfinance 1.2.0 may not accept `Ticker(symbol, session=session)`. AST regression test for `timeout=` across all `requests.*` calls will spuriously FAIL on yfinance calls because yfinance wraps requests internally.

**27-03 — API Key Redaction**
- Clean. notifier.py already has manual redaction at lines 1385–1406; preserving `body.replace(api_key, '[REDACTED]')` as defense-in-depth alongside the new `redact_secret` helper is correct.

**27-04 — Instrument Regex Tightening**
- Minor: The AST walker heuristic `'[A-Z' in pat` may produce false positives — flagged as a fail flag rather than hard assertion, which is good.

**27-05 — Magic Cost Helper & Fallback Email**
- MEDIUM: `cost_aud / 2` grep gate lists `pnl_engine.py`, `sizing_engine.py`, `notifier.py` — but NOT `main.py`. `main.py:1514` has `resolved['cost_aud'] / 2`.
- LOW: `_EMAIL_TO_FALLBACK` deletion: `send_crash_email` at line 1576 ALSO uses `_EMAIL_TO_FALLBACK`. Plan only mentions the send_daily_email path (line 1492). Both sites must be updated.

**27-06 — Deferred yfinance & --version Flag**
- Clean. `--version` is genuinely absent. yfinance is genuinely imported at module top. `_get_yf()` accessor pattern is right choice.

**27-07 — Naive Datetime & Migration Contiguity**
- Clean. Correctly identifies state_manager.py already uses `datetime.now(UTC)` everywhere.
- Minor: Contiguity assertion ordering with Plan 27-01's schema bump is correctly analyzed; both orderings work.

**27-08 — HTML Escape Audit**
- Clean. `_e()` alias approach is clean and minimizes diff noise.
- Minor: notifier.py existing escape pattern from Phase 6 D-10 should be verified before choosing `_e` pattern.

**27-09 — Signal Shape Unification**
- LOW: Schema version will already be at 9 (from 27-01 Decimal migration) when this plan runs, so signal-shape migration will be v9→v10. Plan's `<interfaces>` section handles this correctly.

**27-10 — Warnings FIFO / Run-Date / Lookahead Tests**
- HIGH: `system_params.py:120` already defines `MAX_WARNINGS: int = 100` used by `state_manager.append_warning` (line 803). Plan proposes adding `WARNINGS_FIFO_MAX_LEN = 50` — different name, **different value**. Two constants governing the same FIFO bound with different values. Must either replace `MAX_WARNINGS`, change its value to 50, or clarify they govern different bounds.
- LOW: Lookahead-bias test correctly warns about reading the source first.

**27-11 — Crash Email Fallback**
- Minor: Dashboard banner integration mentions `render_status_strip` from Phase 25 D-15. Sequencing 27-08 → 27-11 → 27-14 is correct.

**27-12 — Notifier Split**
- HIGH (CRITICAL location error): Plan's `<interfaces>` section says `_dispatch_email_and_maintain_warnings` lives in `notifier/warnings_fifo.py`. **Wrong** — function is defined at `main.py:1638`. It's an orchestrator that calls into notifier functions, not a notifier internals function. Moving it would (a) create circular dependency, (b) break hex boundary, (c) break 10+ test references via `main._dispatch_email_and_maintain_warnings`.
- MEDIUM: `render_email_html` listed as template entry point — name doesn't appear in current notifier.py exports. Verify actual public name.
- MEDIUM: `_post_to_resend` is referenced by tests via `notifier._post_to_resend` — must be re-exported.
- **Fix:** Remove `_dispatch_email_and_maintain_warnings` from notifier split's remit. It stays in main.py (and will move to daily_loop.py in Plan 27-13).

**27-13 — Main Split**
- MEDIUM: `_LAST_LOADED_STATE` is a module-level global at `main.py:97`, written by `run_daily_check` (line 1265) and read by `_send_crash_email` (line 454) and `main()` exception handler (line 1986). Plan says it lives in `daily_loop.py` — but `_send_crash_email` is ALSO in main.py and crash dispatch reads it. Plan only lists `run_daily_check` + `_LAST_LOADED_STATE` + `_handle_reset` going into `daily_loop.py` — doesn't mention `_send_crash_email` or `_build_crash_state_summary`. These need a home.
- MEDIUM: Tests reference `main.data_fetcher`, `main.signal_engine` (module-level attributes). Re-export shim must preserve these.
- LOW: `main.logging.basicConfig` is monkeypatched in tests — re-export works.
- **Fix:** Add `_send_crash_email`, `_build_crash_state_summary` to `daily_loop.py` remit. Add `from main import logging` or equivalent to re-export manifest.

**27-14 — Dashboard Split**
- Clean. Manifest-first approach (Task 1) before executing the split (Task 2) is correct. Byte-identical HTML golden snapshot test is the right invariant.

### OpenCode Cross-Cutting Issues

- MEDIUM: Plan 27-05 lists `27-01-decimal-money-math` as a dependency but is itself Wave 1. `depends_on: [27-01]` contradicts `wave: 1` assignment. Should be Wave 2, or should NOT depend on 27-01.
- Test count inflation: ~80+ new tests across 14 new test files (~80% more on top of existing 1319). Fine for cleanup phase but worth noting.

### OpenCode Summary Table

| Plan | Overall | Key Issue |
|------|---------|-----------|
| 27-01 | MEDIUM | Misses sizing_engine.py duplicate `compute_unrealised_pnl` + `_close_position` |
| 27-02 | MEDIUM | Ignores existing `_RESEND_TIMEOUT_S = 30`; yfinance session workaround may not work |
| 27-03 | LOW | Clean |
| 27-04 | LOW | Clean |
| 27-05 | MEDIUM | `cost_aud/2` grep gate misses `main.py:1514`; `send_crash_email` fallback-email path missed |
| 27-06 | LOW | Clean |
| 27-07 | LOW | Clean |
| 27-08 | LOW | Clean |
| 27-09 | LOW | Clean |
| 27-10 | HIGH | `WARNINGS_FIFO_MAX_LEN` duplicates `MAX_WARNINGS=100` with different name AND value |
| 27-11 | LOW | Clean (codex disagrees — see Divergent Views) |
| 27-12 | HIGH | `_dispatch_email_and_maintain_warnings` assigned to notifier package — it's in main.py |
| 27-13 | MEDIUM | `_send_crash_email` + `_build_crash_state_summary` not assigned to any seam; module-level refs need re-export |
| 27-14 | LOW | Clean (codex disagrees — see Divergent Views) |

### OpenCode Risk Assessment: MEDIUM

3 HIGH issues will cause integration failures if not corrected before execution. Each is fixable with ~15 minutes of replanning:

1. Move `_dispatch_email_and_maintain_warnings` out of notifier split remit (27-12)
2. Reconcile MAX_WARNINGS vs WARNINGS_FIFO_MAX_LEN (27-10)
3. Add sizing_engine's duplicate `compute_unrealised_pnl` and `_close_position` to Decimal conversion scope (27-01)
4. Move 27-05 to Wave 2 (depends on 27-01 for Decimal type)
5. Reconcile `HTTP_TIMEOUT_S` with existing `_RESEND_TIMEOUT_S` (27-02)

**Most eloquent fix for all 5:** One cross-cutting alignment pass before Wave 1 starts: update `depends_on` metadata to reflect true dependencies, audit every function-ownership claim against the actual code, and grep for constant collisions before defining new ones.

---

## Consensus Summary

### Agreed Strengths

- Phase scope is directionally correct: real correctness/security/maintainability gaps targeted with concrete verification gates.
- Test discipline is strong: AST regression tests, threat models, byte-identical HTML invariants, explicit fail-closed behavior.
- 27-03 (API key redaction), 27-06 (deferred yfinance + --version), 27-07 (naive datetime + migration contiguity), 27-09 (signal shape unification): both reviewers found these clean / well-scoped.
- Manifest-first approach in 27-14 (capture before split) is the right invariant.

### Agreed Concerns (raised by both reviewers — highest priority to fix)

1. **Wave/dependency graph is broken.** Both flag that 27-05 is marked Wave 1 but depends on 27-01 (also Wave 1). Codex additionally flags 27-01→27-07 and 27-11→27-03/27-08 implicit deps. Fix: rebuild `depends_on` metadata and re-derive waves.
2. **27-13 `daily_loop.py` is overweight and missing pieces.** Codex: ~700 LOC contradicts <500 success criterion. OpenCode: missing assignments for `_send_crash_email`, `_build_crash_state_summary`, and module-level refs (`main.data_fetcher`, `main.signal_engine`, `main.logging`). Fix: split further (`daily_run.py`/`state_actions.py`/`crash_boundary.py`) and complete the function-ownership manifest.
3. **27-12 notifier split is risky.** OpenCode HIGH: `_dispatch_email_and_maintain_warnings` lives in `main.py:1638`, not notifier — moving it creates circular dep + breaks 10+ tests. Codex HIGH: monkeypatch paths like `notifier.requests.post` may break; deleting `notifier.py` outright is risky vs shim+delete two-commit approach.
4. **27-10 has a constant-naming/value collision.** OpenCode HIGH: `WARNINGS_FIFO_MAX_LEN=50` collides with existing `MAX_WARNINGS=100` (different name AND value). Codex HIGH: lookahead xfail without fix could normalize a real trading bug. Both: reconcile before executing.
5. **27-11 crash-email fallback needs dependencies on 27-03 + 27-08 and a configurable path.** Codex HIGH: traceback may contain secrets unless redaction applied before write; project-root path conflicts with repo rule. OpenCode confirms sequencing 27-08→27-11→27-14 is correct.
6. **27-02 HTTP timeout collides with existing infrastructure.** OpenCode HIGH: `_RESEND_TIMEOUT_S=30` already exists in notifier.py — the new `HTTP_TIMEOUT_S` constant duplicates it. Codex MEDIUM: AST test scope is too narrow (misses Session/aliases/imported post/urllib/httpx).
7. **27-01 Decimal scope is incomplete.** OpenCode: `sizing_engine.py` has its own `compute_unrealised_pnl` and `_close_position` doing AUD multiplication — both missed. Codex: persisted-Decimal-as-string + Decimal-on-load may break dashboard JSON serialization; split into PnL-Decimal first, persisted-Decimal second.

### Divergent Views (worth investigating)

- **27-04 instrument regex.** Codex flags HIGH logical contradiction: `INSTRUMENT_ID_RE = ^[A-Z0-9_]{2,20}$` cannot reject `SPI200X` because it's syntactically valid — needs separate `KNOWN_MARKET_IDS` set. OpenCode says clean. **Codex is right** — the test "SPI200X must not match SPI200 regex" is logically impossible against a generic ID regex. Plan needs a "known markets" membership concept.
- **27-08 HTML escape.** OpenCode says clean. Codex flags HIGH: mechanical escaping may double-escape already-safe HTML or break intentional markup; need classification of "escaped text vs trusted HTML fragments." **Codex's concern is valid** — worth adding "raw expected markup remains raw" tests.
- **27-14 dashboard split.** OpenCode says clean. Codex flags HIGH: byte-identical output is fragile after 27-08 escaping and 27-11 crash-banner changes unless golden captured immediately before the split. **Codex is right** — order of capture matters; manifest-first should pin to a specific commit, not before-Wave-2.
- **Overall risk.** Codex says HIGH. OpenCode says MEDIUM. The disagreement reduces to confidence in the parallel-execution model: with the fixes from agreed concerns 1–7 applied, MEDIUM is achievable; without them, HIGH.

### Recommended Action

Run `/gsd-plan-phase 27 --reviews` to incorporate these findings into a replan that:
1. Rebuilds `depends_on` metadata across all 14 plans and re-derives waves.
2. Splits 27-13's `daily_loop.py` into smaller seams and completes the function-ownership manifest.
3. Removes `_dispatch_email_and_maintain_warnings` from 27-12's remit.
4. Reconciles `MAX_WARNINGS` vs `WARNINGS_FIFO_MAX_LEN` in 27-10.
5. Adds dependencies on 27-03 + 27-08 to 27-11 and makes `last_crash.json` path configurable + redacted.
6. Reconciles `HTTP_TIMEOUT_S` with existing `_RESEND_TIMEOUT_S` in 27-02.
7. Extends 27-01's Decimal scope to `sizing_engine.py` and considers splitting into PnL-first / state-second.
8. Adds `KNOWN_MARKET_IDS` membership concept to 27-04.
9. Adds "trusted HTML fragments" classification to 27-08 with anti-double-escape tests.
10. Pins 27-14's golden-capture to immediately-pre-split (after 27-08 + 27-11 land).

Codex's stricter wave ordering (1A: 27-02/03/04/06/07; 1B: 27-01; 1C: 27-05; 2A: 27-08/10; 2B: 27-09/11; Wave 3 sequential) is a reasonable starting point.
