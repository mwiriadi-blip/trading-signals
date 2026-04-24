---
phase: 2
reviewers: [gemini, codex]
reviewed_at: 2026-04-21
plans_reviewed:
  - 02-01-PLAN.md
  - 02-02-PLAN.md
  - 02-03-PLAN.md
  - 02-04-PLAN.md
  - 02-05-PLAN.md
self_skipped: claude (running inside Claude Code for independence)
---

# Cross-AI Plan Review — Phase 2

> Independent review of the 5-plan, 5-wave Phase 2 set (Signal Engine — Sizing, Exits, Pyramiding) by external AI CLIs. Run via `/gsd-review --phase 2 --all` on 2026-04-21.

---

## Gemini Review

This review evaluates implementation plans **02-01 through 02-05** for the "Sizing, Exits, and Pyramiding" phase of the Trading Signals project.

### 1. Summary
The Phase 2 implementation plans are comprehensive, logically sequenced, and rigorously aligned with both the functional requirements and the architectural constraints established in Phase 1. The decision to split logic into `sizing_engine.py` and `system_params.py`, coupled with the extension of the hexagonal AST guards to enforce stdlib-only math in these modules, is an excellent design choice. The plan set thoroughly addresses complex areas such as the 9-cell transition matrix, intraday stop-hit detection, and stateless pyramid transitions. The use of 15 named JSON fixtures provides a high-signal verification layer that effectively treats "filenames as documentation."

### 2. Strengths
*   **Hexagonal Boundary Enforcement:** Wave 0 (02-01) proactively extends the AST blocklist to new modules, ensuring Phase 2 logic remains pure-math and stdlib-only (blocking `numpy` and `pandas`).
*   **Constant Management:** Migrating policy constants to `system_params.py` before implementation avoids hardcoding and separates trading parameters from calculation logic.
*   **Pyramid Statelessness:** The implementation of `check_pyramid` (02-03) to evaluate only the *next* level threshold is a clever, stateless way to satisfy the "max 1 step per call" requirement (PYRA-05) without needing complex state tracking.
*   **Test-Driven Infrastructure:** The plans feature a heavy emphasis on unit tests for every mathematical operation and scenario-driven integration tests for the `step()` orchestrator.
*   **Robust NaN/Error Handling:** All math functions (02-02, 02-03) include explicit guards for NaN inputs and division-by-zero, mapping degenerate data to safe "FLAT" or "size=0" outcomes.

### 3. Concerns
*   **Hypothetical Fill Price for Stop Hits (Low Severity):** In Plan 02-05, `_close_position` defaults to using `bar['close']` as the exit price for all reasons, including stop hits. If an intraday stop is hit at 6891 but the day closes at 6950, the `realised_pnl` in the `ClosedTrade` object will reflect the Close, which might be unrealistic. While the plans correctly defer "real" fill logic to Phase 3's `record_trade`, this placeholder P&L could mislead the dashboard in early integration.
*   **Trailing Stop "Ratchet" Logic (Medium Severity):** Plan 02-03 implements `get_trailing_stop` using the latest `atr` passed from the orchestrator. If today's ATR is significantly higher than entry ATR, the stop distance (`3 * ATR`) will widen. Because the engine does not store the `last_stop` price, the calculated stop level could theoretically move *away* from the price (down for LONG) if volatility spikes. Usually, trailing stops only move in the direction of the profit.

### 4. Suggestions
*   **Refine `ClosedTrade` Exit Price:** In `sizing_engine.py` (02-05), consider allowing `_close_position` to accept an `exit_price` override. For stop hits, the `step()` function could compute the stop level and pass it as the exit price, providing a more realistic "best case" P&L than simply using the Close.
*   **Clarify Trailing Stop ATR Anchor:** In `get_trailing_stop` (02-03), check if the operator prefers the stop distance to be anchored to volatility at entry (`position['atr_entry']`) rather than today's ATR. Using the entry ATR ensures the risk distance remains consistent with the original position sizing.
*   **Documentation for `StepResult`:** In `sizing_engine.py` (02-01/02-05), ensure the docstring for `StepResult` explicitly notes that `unrealised_pnl` is computed *after* any entry or pyramid additions have been applied for that bar.

### 5. Risk Assessment: LOW
The overall risk is **LOW**. The mathematical formulas are straightforward and have been cross-verified in research. The dependency ordering is solid, and the "Wave 0" scaffolding prevents architectural drift early. The use of SHA256 snapshots (D-06) for fixtures provides a strong regression gate that makes the phase highly verifiable. All open research questions (A1-A4) have been resolved with conservative, trade-safe defaults.

**The plan set is ready for execution.**

---

## Codex Review

### Summary

The Phase 2 plan set is strong overall: it is explicit, test-first, well-sequenced, and unusually good at locking down behavioral ambiguity before implementation. The wave ordering is mostly correct, the Phase 2 boundary is preserved, the fixture strategy is coherent, and the plans do address the major operator decisions around D-11, D-12, D-13, and D-14. The main risks are not missing coverage so much as a few contract inconsistencies and some over-specification in the later waves: `compute_unrealised_pnl`/`step()` signature drift versus the approved context, `step()` behavior around pyramid application and position state, some brittle test-count assertions, and a real risk that the fixture/regenerator layer becomes a second implementation rather than a spec. With a few corrections, this is a solid Phase 2 execution set.

### Strengths

- Wave ordering is mostly sound: `02-01` blocks on docs/constants/AST guard before implementation, which matches the stated need to prevent spec drift.
- Hexagonal-lite enforcement is treated seriously instead of aspirationally.
- The D-11 SPI mini change is propagated early and repeatedly validated.
- The D-12 pyramid invariant is captured in three layers:
  - unit math in `check_pyramid`
  - named gap-day tests
  - fixture-level scenario proof
- The 9-cell transition matrix is explicitly named and documented, which reduces ambiguity.
- The 6 edge-case fixtures are the right ones; they cover the highest-risk behavioral corners.
- The plans resolve A1-A4 consistently:
  - CLOSE for pyramid trigger
  - no re-entry on stop-hit/ADX-exit day
  - explicit `cost_aud_open` parameter
  - today's ADX for EXIT-05
- Determinism is treated as a first-class requirement, not an afterthought.
- The plans maintain the "pure math first, orchestration later" split well through Waves 1-3.
- The repeated acceptance criteria around "no `max(1, …)` floor" are exactly the right safeguard for this phase.

### Concerns

- **HIGH**: `compute_unrealised_pnl` and `step()` signatures drift from the locked context.
  - D-10 and the Phase 2 scope describe `compute_unrealised_pnl(position, current_price, multiplier) -> float`, but the plans change it to require `cost_aud_open`.
  - That may be a good design choice, but it is a public API change, not a minor implementation detail.
  - Same issue for `step()`: the approved context says `step(position, bar, indicators, old_signal, new_signal) -> StepResult`, but the plans expand it to also require `account`, `multiplier`, and `cost_aud_open`.
  - This is a plan-level contract deviation that should be explicitly reconciled in docs/context, not silently adopted.

- **HIGH**: `step()` as planned does not fully satisfy the phase goal of deterministic transitions for "any given (state, indicators, today's bar) input".
  - In `02-05`, `step()` returns `pyramid_decision` but intentionally does not apply the pyramid add to `position`.
  - That means `position_after` is not actually the post-step state if a pyramid add occurred.
  - This weakens the meaning of "step" and undercuts the "position_after fixture re-emission" objective.

- **HIGH**: The regenerator in `02-04`/`02-05` risks becoming a second production implementation.
  - It mirrors `_vol_scale`, sizing, trailing stop, stop-hit, pyramid, close logic, and full `step()` logic.
  - That helps independence, but it also creates dual-maintenance risk and can drift subtly from production.
  - For this phase, that is acceptable only if the oracle/spec logic is intentionally simpler and tightly documented. Right now it is becoming nearly full duplicate logic.

- **MEDIUM**: NaN handling is incomplete outside sizing.
  - D-03 says all public Phase 2 functions explicitly guard NaN inputs.
  - The plans are strong for `rvol`, but weaker for `atr`, `high`, `low`, `current_price`, `peak_price`, `trough_price`, and `adx`.
  - `get_trailing_stop`, `check_stop_hit`, and `check_pyramid` mostly assume finite numeric inputs.
  - Some docstrings say NaN should propagate; others imply explicit handling. That is not fully consistent.

- **MEDIUM**: `check_stop_hit(position, high, low, atr)` and `get_trailing_stop(position, current_price, atr)` assume peak/trough already updated with today's HIGH/LOW, but this update logic is not clearly owned.
  - The context says intraday HIGH/LOW drives updates.
  - The plans mention the orchestrator updates peak/trough before calling, but `step()` in `02-05` does not obviously do that before stop evaluation.
  - That is a correctness risk for EXIT-06..09.

- **MEDIUM**: The `step()` ordering around reversal sizing uses the input `account`, not post-close account.
  - The context and research imply reversal is close then re-open in one run.
  - If account is supposed to reflect realized P&L before sizing the new leg, Phase 2 either needs to compute that explicitly or document that account mutation belongs to Phase 3/4 and this is an approximation.
  - Right now that boundary is muddy.

- **MEDIUM**: Test-count assertions are too brittle throughout the plans.
  - Assertions like "102 passed", "119 passed, 4 skipped", etc. are likely to become stale from unrelated test additions.
  - That creates maintenance noise without improving correctness.

- **MEDIUM**: `02-01` lists Phase 2 requirements in its front matter (`SIZE-01`, `SIZE-02`, etc.) even though Wave 0 is scaffolding only.
  - That blurs traceability. Better to tag scaffolding as enabling work, not requirement delivery.

- **LOW**: Some acceptance criteria rely on grep/string literals rather than behavior.
  - Useful as scaffolding checks, but a bit overdone in later waves.

- **LOW**: There is some scope creep/over-engineering in the fixture stack.
  - 15 JSON fixtures, README, regenerator, snapshot, named tests, parametrized tests, and then `step()` tests on top may be more than Phase 2 strictly needs.
  - It is defensible, but expensive.

### Suggestions

- Resolve the API contract drift explicitly before execution.
  - Update `02-CONTEXT.md`, `SPEC.md`, and `02-01-PLAN.md` so `compute_unrealised_pnl` and `step()` signatures match the chosen design.
  - If `cost_aud_open`, `account`, and `multiplier` are required, make that a formal Phase 2 decision rather than a research-side recommendation.

- Tighten NaN policy across all public functions in `sizing_engine.py`.
  - In `02-03-PLAN.md` Task 1, add explicit acceptance criteria for NaN behavior in:
    - `get_trailing_stop`
    - `check_stop_hit`
    - `check_pyramid`
  - Decide whether each function should:
    - return sentinel values,
    - return `False`,
    - or raise `ValueError`.
  - Right now the policy is only fully nailed down for sizing.

- Clarify ownership of peak/trough updates.
  - In `02-05-PLAN.md` Task 1, specify whether `step()` itself updates `peak_price`/`trough_price` using today's HIGH/LOW before calling stop logic.
  - If not, then `step()` is not a complete daily transition wrapper.

- Decide whether `step()` returns a true post-step position or just a decision bundle.
  - If pyramid adds are not applied inside `step()`, rename `position_after` to something like `position_after_exits_entries_before_pyramid_apply`.
  - Better option: have `step()` apply the pyramid level transition to returned position so `position_after` means what it says.

- Make reversal sizing-account semantics explicit.
  - In `02-05-PLAN.md`, either:
    - compute a transient post-close account inside `step()` for reversal sizing, or
    - state clearly that Phase 2 does not own account mutation and sizes off input account by design.
  - This is currently an important ambiguity.

- Reduce brittleness in acceptance criteria.
  - Replace exact suite counts like `102 passed` with targeted assertions:
    - specific tests exist,
    - specific test selections pass,
    - no skips remain where expected.
  - This will age better.

- Add one explicit test for NaN ATR / NaN ADX in `step()`.
  - Suggested additions in `tests/test_sizing_engine.py`:
    - `test_step_nan_adx_does_not_trigger_exit_05`
    - `test_calc_position_size_nan_atr_returns_size_zero_warning`
  - This would close a real gap in "any input" determinism.

- Add one explicit test for inclusive stop boundary after peak/trough fallback.
  - Especially first-bar positions with `peak_price=None` / `trough_price=None`.

- In `02-04-PLAN.md`, consider trimming duplicate testing.
  - The named shortcut tests plus parametrized fixture tests may be enough without extra shape-only tests for every fixture.
  - If kept, explain why both are needed.

- In `02-01-PLAN.md`, separate scaffolding from requirement delivery in metadata.
  - Mark Wave 0 as "enables SIZE/EXIT/PYRA work" rather than directly satisfying those requirement IDs.

### Risk Assessment

**Overall risk: MEDIUM**

The plan set is high quality and likely executable, but not yet low-risk because a few design choices are still misaligned with the locked context, and the `step()`/`position_after` semantics are not fully coherent. The biggest danger is not implementation sloppiness; it is contract drift and subtle behavioral mismatch between the duplicated fixture oracle logic and production logic. If the API signatures, NaN policy, peak/trough update ownership, and post-pyramid position semantics are cleaned up first, the execution risk drops substantially.

---

## Consensus Summary

Both reviewers (Gemini, Codex) agree the plan set is **well-structured, test-first, and architecturally sound** — both single out the hexagonal-lite AST extension, stateless `check_pyramid`, and Wave 0 BLOCKING ordering as standout strengths. They diverge on overall risk: **Gemini = LOW** (formulas verified, dependency chain clean, A1-A4 conservatively resolved), **Codex = MEDIUM** (calls out specific contract-drift and semantic-coherence issues that should be reconciled before execution).

### Agreed Strengths

- **Hexagonal boundary enforcement via AST blocklist** (Wave 0 extension covers `sizing_engine.py` + `system_params.py` with stdlib-only constraint) — both reviewers flagged this as the right way to prevent architectural drift.
- **Stateless pyramid (D-12)** — both call out `check_pyramid` returning at most `add_contracts=1` as a clean way to satisfy PYRA-05 without orchestrator coordination.
- **9-cell truth table + 6 edge cases** — both agree the fixture taxonomy is the right shape.
- **Wave 0 BLOCKING ordering for D-11 SPI mini change** — both note that doc amendments running before any code reads `SPI_MULT` is the right sequencing.

### Agreed Concerns

1. **Trailing stop / peak-trough update ownership ambiguity** (Gemini MEDIUM "ratchet" concern, Codex MEDIUM "ownership not clearly specified"). Both reviewers independently flag that `get_trailing_stop` using today's ATR (vs. anchoring to `position['atr_entry']`) and the unclear ownership of when `peak_price`/`trough_price` get updated with today's HIGH/LOW could produce subtle EXIT-06..09 bugs. **This is the single most agreed-upon concern.**

2. **Stop-hit day exit price / fill semantics** — Gemini explicitly (LOW: `_close_position` uses `bar['close']` for stop hits when intraday stop level might be more realistic). Codex implicitly via "step() doesn't fully satisfy the phase goal" — both touch the same boundary between "what Phase 2 computes deterministically" vs. "what Phase 3/4 owns at fill time."

### Codex-Only Concerns (HIGH severity, not raised by Gemini)

3. **API contract drift from CONTEXT.md D-10** — `compute_unrealised_pnl` and `step()` signatures in plans expand beyond what D-10 locked (`compute_unrealised_pnl` adds `cost_aud_open`; `step()` adds `account`, `multiplier`, `cost_aud_open`). Codex flags this as a public API change that should either get folded back into D-10/CONTEXT.md as a formal amendment OR get reverted to match the locked signatures. Gemini did not catch this because it focused on fixture/test rigor over signature traceability.

4. **`step()` returns `pyramid_decision` but doesn't apply the add to `position`** — `position_after` therefore isn't the true post-step state if a pyramid add fires. Codex recommends either renaming the field or applying the pyramid transition inside `step()`. This conflicts with D-12's stateless intent — needs an explicit decision.

5. **Regenerator becoming a second production implementation** — Codex argues that `tests/regenerate_phase2_fixtures.py` mirrors `_vol_scale`, sizing, trailing stop, stop-hit, pyramid, close, AND full `step()` logic, creating dual-maintenance risk. This is the trade-off of having an independent oracle vs. fixture-only — worth an explicit decision.

6. **NaN policy uneven across functions** — Codex notes D-03 says "all public Phase 2 functions guard NaN" but the plans only fully nail this down for sizing. `get_trailing_stop`, `check_stop_hit`, `check_pyramid` should have explicit NaN behavior tests.

7. **Brittle test-count acceptance criteria** ("102 passed", "119 passed, 4 skipped") — will age poorly as unrelated tests are added. Replace with targeted `pytest -k` selections or "no skips in {class}" assertions.

8. **02-01 frontmatter claims SIZE-01..03,06 + PYRA-01,04** even though it's pure scaffolding — blurs requirement traceability. Suggest tagging Wave 0 as "enabling" rather than "delivering" these REQ-IDs.

### Gemini-Only Suggestions (not raised by Codex)

- **Allow `_close_position` to accept an `exit_price` override** so stop-hit fixtures can carry a more realistic intraday-stop fill price rather than always using `bar['close']`.
- **Clarify trailing-stop ATR anchor** — operator may prefer `position['atr_entry']` (consistent with sizing risk) over today's ATR (responsive to vol regime change).
- **Document that `StepResult.unrealised_pnl` is post-entry/post-pyramid** so callers don't misread it as pre-mutation.

### Divergent Views

- **Risk grade**: Gemini LOW vs Codex MEDIUM. The delta is mostly Codex's API-drift flag — Gemini did not weight signature deviations from D-10 because it accepts them as research-resolved, while Codex argues they should round-trip through CONTEXT.md as a formal amendment.
- **Fixture/regenerator stack weight**: Gemini sees the 15-fixture + SHA256 snapshot system as a *strength* ("strong regression gate"), Codex sees it as *over-engineering / dual-maintenance risk*. Both views are defensible — depends on whether you value independence-from-implementation oracle properties or DRY.
- **Stop-hit day fill price**: Gemini wants a richer price model (LOW), Codex wants explicit boundary documentation. Same underlying issue, different proposed remedies.

### Recommended Next Steps (ranked)

1. **Reconcile API contract drift** (Codex HIGH #3) — either amend CONTEXT.md D-10 to formalize the new signatures (`cost_aud_open`, `account`, `multiplier`) or revert plans to match the original D-10 signatures. **Block execution until decided.**
2. **Decide peak/trough update ownership** (both reviewers MEDIUM) — does `step()` update `peak_price`/`trough_price` from today's HIGH/LOW BEFORE calling `check_stop_hit`/`get_trailing_stop`, or does the orchestrator? Document explicitly in 02-05 Task 1 AC.
3. **Decide trailing-stop ATR anchor** (Gemini MEDIUM) — `position['atr_entry']` vs today's `atr`. Pick one and add a single-line comment in `get_trailing_stop` docstring naming the choice and why.
4. **Tighten NaN policy** (Codex MEDIUM) — add explicit AC rows in 02-03 Task 1 for NaN behavior in `get_trailing_stop`, `check_stop_hit`, `check_pyramid`.
5. **De-brittle test-count assertions** (Codex MEDIUM) — replace `102 passed` with targeted test-name selections.
6. **Fix 02-01 frontmatter requirements field** (Codex MEDIUM #8) — Wave 0 doesn't deliver SIZE-01..03,06 / PYRA-01,04; it enables them.
7. **Decide pyramid-add inside step()** (Codex HIGH #4) — apply the pyramid add to `position_after` (consistent semantics) OR rename the field (explicit semantics). Either is fine; muddy is not.
8. **Decide regenerator scope** (Codex HIGH #5) — either keep full duplicate oracle logic and document the dual-maintenance trade-off in 02-04, or trim regenerator to scenario inputs only and let pytest call production code for expected outputs.

These 8 items map cleanly into a `/gsd-plan-phase 2 --reviews` revision pass. Items 1, 4, 6, 7 are config/AC tweaks. Items 2, 3, 8 are formal design decisions that should round-trip through CONTEXT.md (D-15..D-17 candidates).
