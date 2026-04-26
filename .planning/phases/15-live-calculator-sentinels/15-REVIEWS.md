---
phase: 15
reviewers: [gemini, codex]
reviewed_at: 2026-04-26T01:24:44Z
plans_reviewed: [15-01-PLAN.md, 15-02-PLAN.md, 15-03-PLAN.md, 15-04-PLAN.md, 15-05-PLAN.md, 15-06-PLAN.md, 15-07-PLAN.md, 15-08-PLAN.md]
runtime_self: claude (skipped per workflow self-detection)
---

# Cross-AI Plan Review — Phase 15: Live Calculator + Sentinels

Two external AI reviewers (Gemini CLI, Codex CLI) independently reviewed the 8-plan phase package against PROJECT.md, ROADMAP.md, REQUIREMENTS.md, CONTEXT.md (D-01..D-14), RESEARCH.md, and all PLAN.md files. Claude was skipped because the orchestrator runs in claude-desktop (avoids self-review echo).

---

## Gemini Review

# Implementation Plan Review: Phase 15 — Live Calculator + Sentinels

Phase 15 is a high-impact enhancement that transforms the SPI 200 & AUD/USD Trading Signals dashboard from a passive record into an active workstation. The 8 plans provided are exceptionally detailed, demonstrating a deep understanding of the project's hexagonal architecture and strict state persistence invariants.

## Summary
The plans provide a robust, wave-based approach to implementing live stop-loss/pyramid calculations and position-vs-signal drift sentinels. By isolating the math logic in `sizing_engine` and surgical state mutations in `state_manager`, the plans ensure that the complex multi-surface rendering (dashboard, email, and HTMX fragments) remains consistent and deterministic. The strategy for preserving the **W3 invariant** (exactly 2 saves per run) and enforcing **hex-boundary discipline** via AST-gate updates and local imports is excellent.

## Strengths
- **W3 Invariant Integrity:** Plans 04 (signal loop) and 06 (web mutators) are meticulously designed to perform drift recomputations as in-memory mutations before the terminal `mutate_state` call. This prevents "save bloat" and maintains system performance.
- **Lockstep Copy Parity:** The decision to use `DriftEvent.message` as the single source of truth for both dashboard and email banners (D-12) effectively eliminates the risk of template drift between delivery channels.
- **Defensive HTMX Design:** Plan 06's handling of the `z` input (forward-look) is high-quality, using `math.isfinite` guards and returning an em-dash rather than a 4xx error on degenerate input, which avoids triggering HTMX's error machinery on partial-typed values.
- **Side-by-Side Stop Visualization:** The implementation of the side-by-side `manual | computed` display (Plan 05) provides essential transparency to the operator, clearly indicating which value the daily-loop exit detection will respect.
- **Testing Rigor:** The inclusion of Wave 0 skeletons and bit-identical parity tests (e.g., `test_forward_stop_matches_sizing_engine_bit_for_bit`) ensures that the new rendering logic perfectly mirrors the core engine math.

## Concerns
- **Incomplete Pyramid Display (Severity: MEDIUM):** Plan 05's `_render_calc_row` (Task 1, Part B) implementation computes `next_add_price` but appears to omit the "new stop after add" value required by Roadmap SC-4 and the UI-SPEC Copywriting table.
- **Missing Forward-Look Hint Logic (Severity: LOW):** The UI-SPEC suggests showing the `(enter high to project)` hint when the `W` result is an em-dash. The provided code in Plan 05 includes the hint text but lacks the conditional logic to hide it once a projection is rendered.
- **Hero-Card Marker Fragility (Severity: LOW):** Plan 07 Task 2 depends on the executor identifying a stable content marker for the hero card in `notifier.py`. If the marker is not found, the ordering assertion (`corruption > stale > drift > hero`) may remain skipped, weakening the hierarchy verification.

## Suggestions
- **Complete the Pyramid Cell:** In `dashboard.py::_render_calc_row` (Plan 05), calculate the projected stop price after a pyramid add by using the `next_add_price` as a synthetic peak/trough. This fulfills the "new stop after add: S" requirement.
- **Refine the Forward-Look HTMX Swap:** While Plan 06 uses explicit IDs, ensure the server-side `Response` in `web/routes/dashboard.py` returns the *entire* span including the ID (as shown in Pattern 3), rather than just the inner text, to ensure HTMX can perform the replacement reliably.
- **Audit `_apply` closures:** In `web/routes/trades.py` (Plan 06), double-check that the drift recompute block is placed *after* the `record_trade` or position mutation but *before* the closure returns, ensuring the drift detection sees the updated position set.

## Risk Assessment
**Overall Risk: LOW**

The architectural foundations (Phase 13/14) are solid, and the Phase 15 plans adhere strictly to established patterns (C-2 local imports, TRADE-06 sole-writer). The risks are primarily presentational and are mitigated by the Wave 4 "Golden Fixture" and "Human-UAT" checkpoints. The system's "never-crash" posture is maintained across all new render and fragment paths.

*Reviewer: Gemini CLI · Date: 2026-04-26*

---

## Codex Review

## Summary
The Phase 15 plan set is generally strong: the phase is decomposed into sensible waves, the core contracts are explicit, and the architecture mostly respects the existing hex-lite boundaries. The main weaknesses are a few plan-to-requirement mismatches, some dependency/test inconsistencies, and one important dashboard-ordering gap that could break the stated banner hierarchy. The biggest risk is not implementation complexity; it is shipping something that looks complete while missing parts of `CALC-04`, under-testing web drift recomputation, or silently violating the dashboard/email parity and stack-order guarantees.

## Strengths
- Clear wave structure with mostly good dependency isolation:
  - `15-02` pure math in `sizing_engine.py`
  - `15-03` warning filtering in `state_manager.py`
  - `15-04` orchestration in `main.py`
  - `15-05` render-only dashboard work in `dashboard.py`
  - `15-06` web interactivity in `web/routes/dashboard.py` and `web/routes/trades.py`
  - `15-07` email rendering in `notifier.py`
- Good respect for architectural invariants:
  - `detect_drift()` is kept pure.
  - `clear_warnings_by_source()` remains in `state_manager`.
  - `append_warning()` stays the warning writer.
  - Web-layer imports are explicitly intended to stay local.
- W3 risk is explicitly identified and handled in `15-04`; that is the right place to be strict.
- Input-validation posture for `z` is reasonable: finite/positive float checks, em-dash fallback instead of HTMX error spam, no intraday fetch or SSRF surface introduced.
- XSS posture is mostly sound: `DriftEvent.message` is server-constructed, render plans consistently mention `html.escape(..., quote=True)`.
- The plans correctly avoid scope creep into live execution, databases, or intraday data fetches.
- Wave 0 scaffolding is useful; it makes later plans easier to review and reduces "tests appeared from nowhere" drift.

## Concerns
- **HIGH** `CALC-04` is not fully implemented in `15-05`.
  - The proposed `_render_calc_row()` shows `NEXT ADD` and `LEVEL`, but not the required "new stop after add: S".
  - It also does not clearly surface the `(+Y×ATR_entry)` annotation required by the phase context.
  - `check_pyramid` is imported but effectively unused.
- **HIGH** Dashboard banner hierarchy looks under-specified/broken in `15-05`.
  - The requirement says corruption > stale > reversal > drift on dashboard and email.
  - `15-05` says `_render_positions_table` prepends `_render_drift_banner(state)` before "Open Positions", but does not clearly integrate with the existing dashboard critical-banner stack.
  - If corruption/stale banners are rendered elsewhere, drift may end up in the wrong DOM order.
- **HIGH** `15-07` is missing a real dependency on `15-05`.
  - Its tests reference dashboard parity (`_render_drift_banner`) but `depends_on` omits `15-05`.
  - That is a sequencing bug, not just documentation drift.
- **HIGH** Web drift recomputation in `web/routes/trades.py` is under-tested.
  - `15-06` adds the mutation-side drift lifecycle, but the test plan only populates `TestForwardStopFragment` and `TestSideBySideStopDisplay`.
  - There is no direct test coverage for open/close/modify recomputing `source='drift'` warnings correctly.
- **MEDIUM** `15-04` acceptance and execution instructions conflict.
  - Must-haves say `TestDriftWarningLifecycle` is fully populated and all 4 methods pass.
  - Task 2 allows 3 of 4 to remain skipped.
  - That weakens confidence in the main-loop drift lifecycle.
- **MEDIUM** `15-07` has the same inconsistency.
  - Must-haves say populated/passing tests.
  - Task 2 allows the hero-card ordering test to remain skipped.
- **MEDIUM** The "local imports only" invariant for `dashboard.py` is not actually locked well after `FORBIDDEN_MODULES_DASHBOARD` drops `sizing_engine`.
  - Once `sizing_engine` is removed from the forbidden set, a module-top import in `dashboard.py` would also pass that AST gate.
  - The plan states local-only, but the enforcement looks weak.
- **MEDIUM** Distance-to-stop semantics are ambiguous.
  - The plan computes distance from `entry_price` to stop.
  - Operators often expect distance from current price/mark to stop.
  - If entry-based distance is intended, it should be explicitly justified in the UI copy/tests.
- **LOW** Broad `except Exception` in dashboard/web render paths may hide real defects.
  - This is pragmatic for operator-facing rendering, but it makes debugging harder if formatting or state-shape regressions slip in.
- **LOW** `fragment.startswith('forward-stop')` is looser than necessary.
  - Exact match would be clearer unless future variants are expected.

## Suggestions
- Tighten `15-05` so `CALC-04` is actually met:
  - Render `new stop after add: S`
  - Render the ATR-step annotation like `(+1×ATR)` / `(+2×ATR)`
  - Either use `check_pyramid()` meaningfully or drop the import and compute exactly what the requirement needs
- Move dashboard drift rendering into the existing critical-banner stack rather than prepending it ad hoc in `_render_positions_table`.
  - That is the cleanest way to guarantee D-13 on dashboard, not just in email.
- Add `15-05` to `15-07.depends_on`.
- Add explicit web trade-mutation tests in `15-06` for:
  - open trade creates drift warning when position mismatches signal
  - close trade clears drift warning when mismatch disappears
  - modify trade recomputes drift without nuking non-drift warnings
- Remove the "may remain skipped" escape hatches from `15-04` and `15-07`, or downgrade the must-haves accordingly.
- Add an explicit test guarding `dashboard.py` local-import discipline.
  - Example: parse AST and fail if `from sizing_engine import ...` appears at module top in `dashboard.py`.
- Clarify the distance metric in the requirement/tests:
  - either "distance from entry to stop" or "distance from current price to stop"
  - right now the plan bakes in one interpretation without closing the ambiguity
- Prefer exact fragment matching in `web/routes/dashboard.py`: `fragment == 'forward-stop'`.
- In `15-06`, add one auth/header regression check for the HTMX path to ensure the fragment route stays behind the existing auth chokepoint.

## Risk Assessment
**Overall risk: MEDIUM**

The phase is implementable and mostly well-scoped, but there are enough plan inconsistencies that I would not call it low risk yet. The main risks are: incomplete delivery of `CALC-04`, missing direct tests for web drift recomputation, and a likely dashboard banner-ordering bug relative to D-13. Fix those, tighten the dependency graph, and remove the skipped-test escape hatches, and the execution risk drops materially.

*Reviewer: Codex CLI · Date: 2026-04-26*

---

## Consensus Summary

Two reviewers, one strong divergence on overall risk (Gemini: LOW; Codex: MEDIUM). Both agree the plan set is well-architected and respects hex boundaries; they disagree on whether the unresolved concerns are presentational (Gemini) or contract-level (Codex). Codex's concerns are more numerous and more concrete — they should be the primary input for the `--reviews` replan.

### Agreed Strengths (raised by both)

- **Wave structure is clean**, with mostly disjoint `files_modified` and clear dependency lineage from sizing_engine → state_manager → main → dashboard/web/notifier.
- **W3 invariant** is explicitly identified and locked in Plan 15-04 (in-memory drift mutations before the terminal `mutate_state` call).
- **Lockstep copy parity** via single `DriftEvent.message` consumed by both `dashboard._render_drift_banner` and `notifier._render_header_email` (D-12).
- **`z` input validation** in the forward-look fragment is defensive: `math.isfinite` guard, em-dash fallback, no HTMX error machinery, no SSRF surface.
- **XSS posture** is sound — `DriftEvent.message` is server-constructed and `html.escape(..., quote=True)` is applied at every render leaf.
- **Wave 0 scaffolding** in Plan 15-01 (test stubs + `FORBIDDEN_MODULES_DASHBOARD` update) makes downstream plans easier to read and reduces test-from-nowhere drift.

### Agreed Concerns (raised by both — highest priority to address)

1. **CALC-04 is incomplete in Plan 15-05** *(Gemini: MEDIUM, Codex: HIGH)*.
   `_render_calc_row` computes `NEXT ADD` and `LEVEL` but does NOT render "new stop after add: S" required by Roadmap SC-4 and UI-SPEC Copywriting table. `check_pyramid` is imported but underused. Both reviewers ask for this to be fixed before execution.

### Codex-Only Concerns (worth investigating — Gemini did not flag)

2. **Dashboard banner stack hierarchy may not actually enforce D-13** *(HIGH)*. Plan 15-05 prepends `_render_drift_banner(state)` ad-hoc to `_render_positions_table` but does not integrate with the existing critical-banner stack. If corruption/stale banners render elsewhere in the DOM, drift may land in the wrong DOM order on dashboard (email side is fine — Plan 15-07 is explicit there).
3. **Plan 15-07 is missing `depends_on: [15-05]`** *(HIGH — sequencing bug)*. Its parity test imports `dashboard._render_drift_banner` but Plan 15-07's frontmatter lists only `[15-02, 15-04]`.
4. **Web drift recomputation in `web/routes/trades.py` is under-tested** *(HIGH)*. Plan 15-06 adds the mutation-side drift lifecycle but only `TestForwardStopFragment` + `TestSideBySideStopDisplay` are populated — no direct test for "open trade creates drift warning when mismatched", "close clears drift", or "modify recomputes without nuking non-drift warnings".
5. **`15-04` and `15-07` have skip-test escape hatches conflicting with their `must_haves`** *(MEDIUM)*. Must-haves say "all 4 methods pass" but task instructions allow 3 of 4 to remain skipped. Either tighten the tasks or relax the must-haves.
6. **Local-import discipline weakens after FORBIDDEN_MODULES update** *(MEDIUM)*. Once `sizing_engine` is removed from `FORBIDDEN_MODULES_DASHBOARD`, a module-top `from sizing_engine import ...` in `dashboard.py` would also pass the AST gate. Need an additional AST guard that asserts no top-level sizing_engine import in dashboard.py.
7. **Distance-to-stop semantics ambiguous** *(MEDIUM)*. Plan computes distance from `entry_price` → stop; operators commonly expect distance from current price → stop. Decision needs to be locked explicitly.
8. **`fragment.startswith('forward-stop')` is looser than `fragment == 'forward-stop'`** *(LOW)*.
9. **Missing auth/header regression test for the HTMX fragment route** *(LOW — security adjacent)*.

### Gemini-Only Concerns (worth investigating — Codex did not flag)

10. **Forward-look hint conditional missing in Plan 15-05** *(LOW)*. UI-SPEC says the `(enter high to project)` hint should hide when W is rendered; Plan 15-05's markup includes the hint string but no conditional swap rule.
11. **Hero-card content marker fragility in Plan 15-07** *(LOW)*. If the executor can't find a stable text marker for the hero card in `notifier.py`, the `corruption > stale > drift > hero` ordering test gets skipped and the hierarchy assertion silently weakens.

### Divergent Views

- **Overall risk:** Gemini says LOW (architectural foundations from Phase 13/14 are solid; Wave 4 fixture + UAT checkpoints will catch presentational issues). Codex says MEDIUM (CALC-04 gap, banner hierarchy gap, missing test coverage on web drift, sequencing bug in 15-07 dependency, skip-test escape hatches all together raise the risk meaningfully).
- **Banner-stack handling:** Gemini accepts Plan 15-05's prepend-to-positions-table approach as adequate. Codex says it doesn't integrate with the existing critical-banner stack and may break D-13 on the dashboard surface specifically.
- **Skip-test escape hatches:** Gemini doesn't mention them. Codex flags them as MEDIUM-severity contract violations between `must_haves` and task instructions.

### Recommended Action

Run `/gsd-plan-phase 15 --reviews` to feed this REVIEWS.md back into the planner. The replan should prioritize, in order:

1. **(HIGH) CALC-04 completeness** — render "new stop after add: S" and the `(+1×ATR)` / `(+2×ATR)` annotation in `dashboard.py::_render_calc_row` (Plan 15-05).
2. **(HIGH) Dashboard banner stack integration** — move `_render_drift_banner` into the existing critical-banner stack so D-13 is enforced on dashboard the same way Plan 15-07 enforces it in email.
3. **(HIGH) Plan 15-07 `depends_on`** — add 15-05.
4. **(HIGH) Web mutation test coverage** — add three tests to Plan 15-06 covering open/close/modify drift lifecycle in `web/routes/trades.py`.
5. **(MEDIUM) Resolve must-haves vs skip-test conflict** in Plans 15-04 and 15-07 (tighten tasks or relax must-haves).
6. **(MEDIUM) AST guard for top-level sizing_engine import** in `dashboard.py` (replaces the protection lost when `FORBIDDEN_MODULES_DASHBOARD` drops `sizing_engine`).
7. **(MEDIUM) Lock distance-to-stop semantics** — decide entry-vs-current-price baseline and bake the choice into UI-SPEC and tests.
8. **(LOW) Tighten `fragment == 'forward-stop'`** exact match in `web/routes/dashboard.py`.
9. **(LOW) Add HTMX auth-header regression test** for the fragment route.
10. **(LOW) Add forward-look hint conditional** in Plan 15-05 markup.
11. **(LOW) Fix hero-card marker fragility** in Plan 15-07 (provide an executor-stable marker fallback or convert the test from "skipped if not found" to "executor must find or fail").
