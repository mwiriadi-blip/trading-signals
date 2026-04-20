---
phase: 1
reviewers: [gemini, codex]
reviewed_at: 2026-04-21T00:00:00+08:00
plans_reviewed: [01-01-PLAN.md, 01-02-PLAN.md, 01-03-PLAN.md, 01-04-PLAN.md, 01-05-PLAN.md, 01-06-PLAN.md]
runtime: claude-code (claude skipped for self-review independence)
skipped_reviewers: [claude, coderabbit, opencode, qwen, cursor]
---

# Cross-AI Plan Review — Phase 1

> Two external reviewers (Gemini CLI and Codex CLI) independently audited the 6-plan package. Claude CLI was skipped because the review orchestration ran inside Claude Code. The other reviewers (coderabbit, opencode, qwen, cursor) are not installed on this machine.

## Gemini Review

*Verdict: **APPROVED** — Risk **LOW***

### Summary
The implementation strategy for Phase 1 is exceptionally rigorous, prioritizing numerical reproducibility and architectural purity. By establishing a "ground truth" through a pure-Python oracle (Plan 02) and enforcing bit-level determinism with SHA256 snapshots (Plan 06), the plan effectively mitigates the risks of floating-point drift and library-induced discrepancies. The resolution of the Wilder/Pandas EWM discrepancy (R-01) is a highlight, demonstrating deep research into financial math conventions.

### Strengths
- **Trust Anchor Design (Plan 02):** Pure-loop Python oracle (D-02) as truth anchor ensures production optimizations are always validated against an unambiguous reference.
- **Wilder EWM Idiom (Plan 04, R-01):** SMA-seeded EWM is mathematically superior to literal spec text and aligns with standard charting packages.
- **Bit-Level Regression (Plan 06, D-14):** SHA256 hashing is the gold standard for determinism across environments.
- **Surgical Fixture Design (Plan 03, D-16):** 9 specific scenario fixtures exercise the vote truth table at its boundaries.
- **Architectural Guardrails (Plan 06):** AST walk enforcing hexagonal boundary prevents import leakage before it can pollute the codebase.

### Concerns
- **MEDIUM — Plan 01 Task 2 (ruff format vs 2-space convention):** `ruff format` forces 4-space indent, conflicting with project's 2-space rule. Relying on `.editorconfig` + author discipline without automated lint gate may cause style drift.
- **LOW — Plan 03 Task 1 (ADX warmup in scenarios):** 280-bar fixtures need precise construction to clear both Mom12 (252) and ADX (38) warmup AND trigger signal logic on the exact last bar.
- **LOW — Plan 03 Task 1 (yfinance retroactive adjustments):** Pitfall 3 noted but depends on future developers reading the fixture README.

### Suggestions
- **Automate indent check:** Add a grep-based task in Plan 06 to assert no `.py` files contain 4-space leading indent.
- **Explicit scalar casting:** In `get_latest_indicators`, explicitly cast to Python `float` so numpy types don't leak into downstream JSON serialization (Phase 3).
- **Pyenv preflight:** In Plan 01 Task 1, verify pyenv/Python 3.11 exists before attempting venv creation with a clear error message.

### Risk Assessment
**LOW.** Front-loading the oracle and fixtures reduces execution to a "matching" exercise — the most robust way to build a deterministic signal engine.

---

## Codex Review

*Verdict: **PROCEED AFTER EDITS** — Risk **MEDIUM***

### Summary
The plan set is substantially above average: explicit about formulas, determinism, fixture strategy, and verification, and it directly addresses the main failure mode for this phase (silently implementing "pandas-ish ATR/ADX" instead of Wilder-canonical math). Strongest part is the separation between oracle, fixtures, production implementation, and determinism guards. Weakest part is operational realism in Wave 0 and Wave 1: several tasks assume network/package/install capabilities and exact tool behavior that are brittle, and a few acceptance criteria are internally inconsistent or over-constrained enough to create false failures.

### Strengths
- **Plan 02 Task 1** correctly treats the ATR spec ambiguity as a real risk and locks the oracle to SMA-seeded Wilder recursion. Single most important numerical decision.
- **Plan 02 overall** preserves real oracle independence — pure loops, no pandas, no shared helper import from `signal_engine.py`.
- **Plan 03 Task 2** is well-designed as an offline regeneration path (D-04).
- **Plan 04 Task 2** compares production against committed oracle goldens rather than recalculating in the same test path.
- **Plan 05** cleanly separates signal semantics from indicator calculation and explicitly tests D-09 through D-12.
- **Plan 06 Task 1** uses AST guards — stronger than grep-only checks.
- **Plan 06 Task 2** traces to ROADMAP success criteria rather than inventing parallel "done" definitions.

### Concerns
- **HIGH — Plan 03 Task 1 (split-vote scenario definition is self-contradictory):** Line 174 states `Mom1 > +0.02, Mom3 < -0.02, Mom12 > +0.02 — votes 2 up 1 down → FLAT per SIG-08`. That's actually **2 up / 1 down → LONG** per SIG-06, not FLAT. When `regenerate_goldens.py` runs, the computed `expected_signal` will be `1` (LONG), contradicting the fixture's name and the SIG-08 label. **This will fail at Wave 1 execution.** (Verified at Plan 03 line 174.)
- **HIGH — Plans 01 Task 1 / Task 2 / 03 Task 1 (network and local-env assumptions):** Plans assume internet access and mutable env setup (pyenv, brew, pip, yfinance fetch) as guaranteed. If the execution environment lacks network or install rights, Wave 0 stalls before any math work begins.
- **HIGH — Plan 01 Task 2 (ruff format convention mismatch):** `ruff format` does not support the 2-space Python indent contract the task implies; `indent-width = 2` is enforced only partially. Will create formatting churn.
- **HIGH — Plan 03 Task 1 (scenario generation underspecified):** Several fixtures described with qualitative recipes ("gentle downtrend", "final sharp uptrend") without deterministic construction algorithms. Invites hand-tuning loops and unstable fixtures.
- **HIGH — Plan 03 Task 2 / Plan 06 Task 2 (determinism sources beyond packages):** Snapshot is strong, but lower-level drift sources (locale, NaN bit patterns, pandas serialization) are assumed stable without explicit normalization.
- **MEDIUM — Plan 02 Task 1 + Plan 04 Task 1 (oracle/production seed-window NaN handling):** Oracle uses `sum(series[0:period]) / period`; production uses `.iloc[:period].mean()`. Behaviors diverge if NaNs enter the seed window. Plan should force equivalence, not assume it.
- **MEDIUM — Plan 04 Task 2 (index alignment):** Tests compare float arrays at 1e-9 but don't explicitly assert index or row-count equality before `.to_numpy()`. Date-index mismatch would fail opaquely.
- **MEDIUM — Plan 05 Task 1 (missing-column defensive contract):** `get_signal(df)` assumes indicator columns exist; no contract test for the missing-column case.
- **MEDIUM — Plan 06 Task 1 (whitelist brittleness):** `test_allowed_imports_only` whitelisting only `{numpy, pandas, typing, math}` will fail on innocuous future additions like `__future__`, `dataclasses`, `collections` even if purity preserved.
- **MEDIUM — Plan 06 Task 2 (≥88 tests assertion is fragile bookkeeping):** Parametrization changes can alter counts without changing coverage quality.
- **LOW — Plan 01 Task 1 (later-phase deps in requirements.txt):** Pinning `requests`, `schedule`, `pytz`, `python-dotenv` now increases Wave 0 failure surface for no immediate Phase 1 value.
- **LOW — Threat model across plans:** "N/A" is slightly overstated — the offline regenerate script does introduce supply-chain surface through PyPI and Yahoo.

### Suggestions
- **Fix split-vote scenario:** Replace with `Mom1 > +0.02, Mom3 < -0.02, Mom12 between -0.02 and +0.02` → 1 up / 1 down / 1 abstain → FLAT.
- **Add Wave 0 execution preflight task:** Verify `python3.11`, network, and package install capability before env mutation; if unavailable, switch to artifact-only planning mode.
- **Make scenario generation deterministic:** Commit a generator spec with exact bar counts, percentage changes, volatility perturbations per segment.
- **Tighten oracle/production Wilder smoothing equivalence:** State explicitly in Plans 02+04: "Seed windows for Wilder smoothing must contain no NaN values; if they do, return NaN until a full non-NaN seed window exists."
- **Add fixture integrity assertions:** In Plan 04 Task 2, assert index equality, row-count equality, and OHLCV column presence.
- **Relax whitelist guard:** Replace with forbid-known-impure-modules (datetime, os, requests, yfinance, signal_engine cross-hex imports).
- **Remove false-precision count assertions:** Replace "≥88 tests passing" with behavior-based checks.
- **Add threshold-equality edge tests to Plan 05:** `ADX == 25.0` → gate open; `Mom == ±0.02` → abstains (rules use `>`/`<`, not `>=`/`<=`).
- **Add `get_latest_indicators` contract test:** Verify NaN preserved as `float('nan')`, not `None`; verify values match `df.iloc[-1]` exactly.

### Risk Assessment
**MEDIUM.** Numerical core is sound. Main risks are execution risks from brittle Wave 0 assumptions, one outright scenario-definition bug, and a few overly rigid acceptance criteria. With those corrected, the phase becomes low-risk.

---

## Consensus Summary

### Agreed Strengths
- **Pure-loop oracle as trust anchor** (Plan 02) — both reviewers call this the strongest design choice in the phase
- **SMA-seeded Wilder (R-01)** — both reviewers explicitly praise the resolution of the SIG-01 formula ambiguity
- **SHA256 determinism snapshot** (Plan 06 / D-14) — both reviewers flag this as best-practice regression defense
- **AST-based architectural guards** (Plan 06 Task 1) — both reviewers prefer this over grep-only
- **9-case scenario fixture coverage** (Plan 03 / D-16) — both reviewers approve boundary-exercising test design

### Agreed Concerns

1. **[HIGH — codex only; not flagged by gemini] Plan 03 Task 1 line 174 — split-vote scenario is self-contradictory.** The described moms produce LONG, not FLAT. This will fail at execution when `regenerate_goldens.py` computes the wrong `expected_signal`. **Must fix before execution.**

2. **[MEDIUM from both] `ruff format` vs 2-space convention mismatch (Plan 01 Task 2).** `ruff format` defaults to 4-space/double-quotes; the config key `indent-width = 2` is supported but the author-discipline fallback creates drift risk. Both reviewers suggest automated indent-enforcement in Plan 06.

3. **[Gemini: LOW / Codex: MEDIUM] Scenario fixture construction is qualitative rather than deterministic.** 280-bar recipes use prose ("gentle downtrend", "final sharp uptrend") without exact bar-count + percentage specifications. Codex flags as HIGH; Gemini flags as needing "precise construction."

4. **[MEDIUM — both] numpy/pandas/seed-window NaN handling convention not explicit.** Oracle and production may diverge on how they handle NaNs inside the SMA seed window. Both reviewers want an explicit rule.

5. **[LOW from both] Explicit float/dtype casting.** Gemini flags `get_latest_indicators` scalar casting for future JSON serialization; Codex flags preserving `float('nan')` (not `None`).

### Divergent Views

- **Overall risk:** Gemini LOW / Codex MEDIUM. The difference is driven by Codex's identification of the split-vote scenario bug (which Gemini didn't catch) and Codex's pickier stance on Wave 0 environmental assumptions.
- **Pinning later-phase deps in `requirements.txt`:** Codex flags as LOW concern (Wave 0 surface bloat); Gemini doesn't mention it. Suggests trimming to Phase 1 needs only (pandas, numpy, pytest, yfinance, ruff) and letting Phase 4+ add its own.
- **Whitelist vs blocklist for architectural imports (Plan 06 Task 1):** Codex wants blocklist ("forbid known impure modules"); Gemini accepts the whitelist as-is. Blocklist is more resilient to benign additions.

### Codex-Only Findings Worth Escalating
These are not in Gemini's review but worth addressing because they're specific and verifiable:
- **Threshold-equality tests** (ADX == 25.0 at gate; Mom == ±0.02 at threshold) — SIG-05/06/07 use strict `<`/`>`. Missing from current Plan 05 test enumeration.
- **Index-alignment assertion** in golden-vs-computed comparison (Plan 04 Task 2).
- **Seed-window NaN equivalence rule** for Wilder smoothing (Plans 02 + 04).

---

## Recommended Action

1. **Before execution — MANDATORY fix:**
   - Plan 03 line 174: correct the split-vote scenario recipe to produce a true FLAT outcome (1 up / 1 down / 1 abstain).

2. **Strongly recommended before execution:**
   - Add threshold-equality tests to Plan 05 (ADX=25.0, Mom=±0.02).
   - State the Wilder seed-window NaN rule explicitly in Plans 02 + 04.
   - Convert Plan 06 whitelist to blocklist.
   - Add index-alignment assertion in Plan 04 Task 2.
   - Trim `requirements.txt` in Plan 01 Task 1 to Phase 1 deps only.

3. **Optional polish:**
   - Deterministic scenario generator spec (Codex's suggested generator algorithm).
   - Indent-enforcement lint rule in Plan 06.
   - Explicit `float()` cast on `get_latest_indicators` values.
   - Revise "N/A" threat model to mention offline-regenerate supply-chain surface.

**Incorporate via:** `/gsd-plan-phase 1 --reviews`
