---
phase: 1
reviewers: [gemini, codex]
reviewed_at: 2026-04-21T00:00:00+08:00
pass: 2
plans_reviewed: [01-01-PLAN.md, 01-02-PLAN.md, 01-03-PLAN.md, 01-04-PLAN.md, 01-05-PLAN.md, 01-06-PLAN.md]
post_execution: true
runtime: claude-code (claude skipped for self-review independence)
prior_pass: 01-REVIEWS-pass1.md
---

# Cross-AI Plan Review — Phase 1 (Second Pass, Post-Execution)

> **Context.** This is the second review of Phase 1, run AFTER execution completed successfully (99/99 tests passing). The first pass (preserved at `01-REVIEWS-pass1.md`) drove a plan revision via `/gsd-plan-phase 1 --reviews` that fixed a MUST FIX (split-vote scenario) and applied all STRONGLY RECOMMENDED + POLISH items. This pass asks reviewers to look retrospectively at the revised plans with fresh eyes and flag anything the first pass or the verifier missed.

## Gemini Review (Pass 2)

*Verdict: Proceed to Phase 2 — Risk **LOW***

### Summary
The revised plans successfully addressed all high-priority concerns from the first pass, most notably the Wilder/Pandas EWM discrepancy (R-01) and the split-vote scenario correction. The execution phase exceeded the 1e-9 tolerance target, achieving 5.7e-14 precision, which confirms that the SMA-seeded vectorised implementation in `signal_engine.py` is bit-compatible with the pure-loop oracle for all practical purposes. The addition of the AST-based blocklist and the tokenize-aware indent guard provides a robust defense against architectural and stylistic drift as the project scales.

### Residual Risks
- **Oracle-to-Production Hashing Asymmetry (Plan 06 Task 1).** Decision at execution time to hash the **oracle** rather than production. Scientifically sound (oracle is the bit-level truth), but `signal_engine.py` itself is not bit-locked by the SHA256 snapshot. A change in `signal_engine.py` that shifts a float bit but stays under 1e-9 will pass CI silently.
- **Fixture staleness (Pitfall 3 acknowledged).** yfinance retroactive adjustments mean re-running `regenerate_goldens.py` in 6 months could produce different baseline bars. The project treats committed CSVs as "fixed history," which is correct for testing but could cause "first-run differences" when Phase 4 goes live.
- **Extreme scale sensitivity.** Tested on index (~8000) and FX (~0.6) scales. Penny stock (~0.0001) or hyper-inflation scales are not exercised. The 1e-9 `atol` is absolute; at very small price scales, tolerance may be too loose relative to price.

### Second-Order Bugs
- **RVol single-value NaN case.** `rolling(period).std()` on a series with only one non-NaN value returns NaN. Phase 2's `SIZE-03` handles magnitude via the 1e-9 clamp, but the orchestrator must be prepared for RVol being NaN or 0.0.
- **Extremely short series.** `get_signal` uses `df.iloc[-1]`. For frames <20 bars, all indicators are NaN; system correctly returns FLAT (safest failure mode).

### Architectural Debt
- **Dict vs. Dataclass for `get_latest_indicators`.** Sufficient now; NamedTuple/Dataclass would give better IDE completion and type safety as Phase 2-8 pass the dict through multiple layers.
- **Global constants in `signal_engine.py`.** `ADX_GATE`, `MOM_THRESHOLD`, etc. are hardcoded. If configuration-driven tuning is ever desired, constants will need to move out of the pure-math module.

### Documentation Gaps
- **The "Why" of hashing oracle.** A new contributor seeing `test_snapshot_hash_stable` re-running oracle (not production) will be confused. Rationale is in Plan 06 SUMMARY but should be inlined as a comment block on the test.

### Risk Assessment
**LOW.** Phase 1 is a highly safe foundation. Separation of oracle from production + bit-level snapshots for the truth anchor is elite engineering for a financial system. 99/99 tests and 5.7e-14 precision margin give high confidence.

**Recommendation:** Proceed to Phase 2. `signal_engine.py` API is locked and mathematically verified.

---

## Codex Review (Pass 2)

*Verdict: Proceed — Risk **MEDIUM-LOW***

### Summary
The revised plans closed the first-pass concerns well. The split-vote bug was actually fixed end-to-end, the threshold-equality cases were added, the seed-window NaN rule was aligned, and the brittle whitelist was replaced with a blocklist. The only material thing that slipped in the post-execution state is that the Phase 1 "determinism" story changed shape: **the final gate now locks oracle bytes, not production bytes**, so cross-version drift in `signal_engine.py` can still sneak through as long as it stays within the 1e-9 tolerance envelope. That is not a Phase 1 blocker, but it is the main retrospective gap.

### Residual Risks

**1. Production-byte drift is no longer pinned** (biggest second-pass finding)
- Plan 06 originally hashed production output; post-execution, `TestDeterminism` hashes oracle output ([`tests/test_signal_engine.py:522-585`](tests/test_signal_engine.py#L522)).
- `TestIndicators` still compares production to oracle at `atol=1e-9` ([`tests/test_signal_engine.py:90-93`](tests/test_signal_engine.py#L90)).
- A future library bump could change production bits, leave oracle bits unchanged, and still pass Phase 1.
- Acceptable if intentional, but "bit-level determinism" now applies to oracle, not shipped engine.

**2. Empty/malformed DataFrame behavior is unpinned**
- `get_signal` and `get_latest_indicators` assume indicator columns exist ([`signal_engine.py:220-245`](signal_engine.py#L220)).
- Empty frame → `IndexError`; missing columns → `KeyError`; malformed fetch → raw pandas error.
- Fine for pure-math core, but **Phase 4 must guard this before calling Phase 1** to meet "handle Yahoo failures / corrupted state gracefully".

**3. Scenario regeneration is reproducible on paper, not scripted**
- Deliberate choice: commit fixture CSVs + README recipes, not a scenario generator.
- Trust surface stayed small, but contributors can regenerate goldens, not scenarios.
- Main doc/maintenance debt — the most delicate fixtures are the vote-logic-proof ones.

### Second-Order Bugs to Watch
- **Cross-version drift below tolerance.** A pandas/numpy change moving production by 1e-12 to 1e-10 fails no test, but subtly shifts state/email/dashboard values. Only visible because of the oracle-hash deviation.
- **Repeat-call idempotency not tested.** `compute_indicators(compute_indicators(df))` looks safe by implementation ([`signal_engine.py:183-193`](signal_engine.py#L183)) but Plan 04 only locked non-mutation on raw fixtures. If later phases rely on this, add a test.
- **Error-path robustness deferred.** Corrupted CSV, object-dtype columns, all-NaN input, zero-length frames are caller hazards, not engine-handled. Phase 4/8 must not assume the core is more defensive than it is.

### Architectural Debt
- **`get_latest_indicators` is brittle on caller discipline.** Lowercase key naming is correct. But callers must remember: input must be indicator-enriched; frame non-empty; NaN preserved as `float('nan')`. Phase 2/4 should wrap this behind orchestration contract, not pass raw frames.
- **Constants need a config boundary soon.** Fine for Phase 1; once Phase 2 adds sizing constants, stop multiples, pyramid thresholds, costs, instrument specs, one module block will get noisy. Recommend `system_params.py` before Phase 2/3 spreads constants.
- **Oracle maintenance is explicitly dual-track.** Formula changes require updating: oracle + production + goldens + snapshot + tolerance tests. Known, but confirmed by execution.

### Documentation Gaps
- Determinism gate changed from "hash production" to "hash oracle" — captured in Plan 06 summary + test docstring, but not in an obvious contributor-facing note.
- Scenario fixtures reproducible, but not via committed script.
- Pure layer's failure contract for empty/malformed data is undocumented; newcomer might assume Phase 1 handles bad input.

### Risk Assessment
**MEDIUM-LOW.** Safe foundation for Phase 2-8 from correctness standpoint. Earlier review's meaningful issues closed; numerical core strong; 99 tests not hollow. No hidden correctness bug in shipped math/vote logic.

Not pure LOW because of the determinism gap from Plan 06 deviation: production bytes not locked, only oracle. Survivable, but weakens cross-version drift story enough to tighten before later phases persist/render these values widely.

---

## Consensus Summary (Pass 2)

### Top Finding — Both Reviewers Agree

**Production-byte drift is no longer pinned.** The executor's Plan 06 deviation (hash oracle output instead of production, because production differs from oracle by ~5e-14) is semantically defensible but changes the determinism story. `TestDeterminism` now regression-tests oracle stability; production stability depends on `TestIndicators` at `atol=1e-9`. A numpy/pandas upgrade that drifts production by 1e-12 to 1e-10 passes all tests.

### Agreed Residual Risks
- Oracle-vs-production hashing asymmetry (primary finding from both)
- Empty/malformed DataFrame not guarded at Phase 1 layer (caller responsibility, but Phase 4 must handle)
- Constants layout will need a config boundary before Phase 2/3 expands the constant set

### Divergent Views
- **Overall risk:** Gemini **LOW** / Codex **MEDIUM-LOW**. Difference is driven by Codex's stronger concern about the production-byte determinism regression.
- **Scale sensitivity:** Gemini flags penny-stock/hyper-inflation scales as untested. Codex doesn't raise this — may be less concerned given Phase 1's committed fixtures span index + FX.
- **RVol NaN on single-value window:** Gemini calls out; Codex doesn't. Phase 2's SIZE-03 guard mitigates but doesn't fully close this.

### Previous Pass — MUST FIX Verified
All pass-1 items closed by the plan revision AND verified end-to-end by execution:
- ✓ Split-vote scenario FLAT (Mom=(+0.058, -0.043, -0.003) → FLAT)
- ✓ Threshold-equality tests (ADX=25.0 opens gate; Mom=±0.02 abstains)
- ✓ Wilder seed-window NaN rule identical in oracle + production
- ✓ Whitelist → blocklist AST guard
- ✓ Index-alignment assertion before `assert_allclose`
- ✓ `requirements.txt` trimmed to Phase 1 scope

---

## Recommended Follow-Up (Not Blocking Phase 1)

These can be addressed during Phase 2 planning or carried forward as explicit debt:

1. **[Low-effort, high-value]** Add a comment block to `TestDeterminism.test_snapshot_hash_stable` explaining why the test re-runs oracle (not production) — closes the documentation gap both reviewers flagged.

2. **[Low-effort]** Add `test_compute_indicators_is_idempotent` — call `compute_indicators` twice and assert identical output. Locks a property Phase 2/4 will likely rely on.

3. **[Phase 2 input guard]** Wrap `get_signal` / `get_latest_indicators` calls in Phase 4's orchestrator with a defensive contract check: non-empty frame, required columns present, float64 dtype. Matches REQUIREMENTS §ERR-04 spirit.

4. **[Phase 2/3 refactor]** Before Phase 2 adds its constants (risk_pct, trail_mult, pyramid thresholds, contract specs), decide whether to move `ADX_GATE` / `MOM_THRESHOLD` / periods to a `system_params.py`. Aligns the constant layout before it sprawls.

5. **[Nice to have]** Commit a `tests/regenerate_scenarios.py` script that regenerates scenario CSVs from the README recipes — closes Codex's "reproducible on paper, not scripted" gap.

6. **[Optional retrospective]** Add a second determinism test that hashes production output and freezes the current values. Acceptable if one wants to trade "now" production bytes against future floating-point drift; skip if tolerance-based comparison is enough.

---

**Pass-1 archive:** [01-REVIEWS-pass1.md](01-REVIEWS-pass1.md)
