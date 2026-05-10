---
phase: 29
plan_id: 29-04-VALIDATION-SECURITY-PHASE-17
plan: 04
type: execute
wave: 2
depends_on: []
requirements: [DEBT-03, DEBT-04]
files_modified:
  - .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VALIDATION.md
  - .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-SECURITY.md
autonomous: true
must_haves:
  truths:
    - "`17-VALIDATION.md` exists in archive dir with Nyquist coverage matrix matching Phase 23 + 27 format."
    - "`17-SECURITY.md` exists in archive dir with threat-model + mitigations matching Phase 27 format."
    - "Coverage matrix maps every Phase 17 Success Criteria item (TRACE-1..5) to existing tests in the suite OR to a Gaps row marked 'Deferred'."
    - "Threat surface enumerates auth/input/render boundaries for Phase 17; mitigations cite already-shipped code."
  artifacts:
    - path: ".planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VALIDATION.md"
      provides: "Nyquist coverage matrix retrofit for Phase 17"
      contains: "Per-Task Verification Map"
    - path: ".planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-SECURITY.md"
      provides: "Threat-model + mitigations retrofit for Phase 17"
      contains: "Threat Register"
  key_links:
    - from: "17-VALIDATION.md Coverage Matrix"
      to: "tests/ directory"
      via: "Automated Command column"
      pattern: ".venv/bin/pytest tests/test_"
    - from: "17-SECURITY.md Threat Register"
      to: "Phase 17 implementation files (signal_engine.py, dashboard_legacy/trace_panels.py, etc.)"
      via: "Mitigation column citing file:line"
      pattern: "(mitigate|accept|transfer)"
---

<objective>
Mechanical retrofit per D-06/D-07/D-08: write `17-VALIDATION.md` (Nyquist) + `17-SECURITY.md` (threat-model) for Phase 17 in a single commit. Format from Phase 27. No new tests written; coverage gaps surface as Deferred rows.

Purpose: Closes DEBT-03 + DEBT-04 for Phase 17. Phase 17 = per-signal calculation transparency (TRACE-1..5).
Output: 2 docs in `.planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-CONTEXT.md
@.planning/milestones/v1.2-phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-VALIDATION.md
@.planning/milestones/v1.2-phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-SECURITY.md
@.planning/milestones/v1.2-phases/23-five-year-backtest-validation-gate/23-VALIDATION.md

<read_first>
- `.planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-CONTEXT.md` (Phase 17 decisions D-01..D-NN)
- `.planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-01-PLAN.md` (Success Criteria items TRACE-1..5)
- `.planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-01-SUMMARY.md` (what shipped + tests)
- `.planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VERIFICATION.md` (existing PASS/FAIL evidence)
- 27-VALIDATION.md (verbatim format template — copy heading structure)
- 27-SECURITY.md (verbatim threat-register format)
- 23-VALIDATION.md (second Nyquist precedent for cross-reference)
- 29-CONTEXT.md §D-06, D-07, D-08, D-09 (mechanical retrofit; one plan per phase × 7; archive location)
</read_first>

<interfaces>
Phase 27's VALIDATION.md provides the column shape for the Per-Task Verification Map:
| Task ID | Plan | Wave | Requirement / Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |

Phase 27's SECURITY.md provides:
- Trust Boundaries table (`| Boundary | Description | Data Crossing |`)
- Threat Register (`| Threat ID | Category | Component | Disposition | Mitigation | Status |`)
- Accepted Risks Log (`| Risk ID | Threat Ref | Rationale | Accepted By | Date |`)
- Security Audit Trail

Copy both formats verbatim for Phase 17. Threat IDs use `T-17-NN-NN`. Risk IDs use `AR-17-NN`.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Enumerate Phase 17 SC items + map to existing tests</name>
  <files>(no files modified — discovery pass; output captured in Task 2's writes)</files>
  <read_first>
    - `17-01-PLAN.md` (Success Criteria block — TRACE-1..5)
    - `17-01-SUMMARY.md` (test files actually committed during execution)
    - `17-VERIFICATION.md` (PASS/FAIL evidence with test commands)
    - `tests/test_trace*.py`, `tests/test_signal_engine.py`, `tests/test_dashboard*.py` — grep for Phase-17-related tests via `grep -rln "Phase 17\\|TRACE-\\|trace_panel\\|trace-disclosure\\|tsi_trace_open" tests/`
  </read_first>
  <action>
    Discovery only. Build a working table mapping each TRACE-N requirement to:
    - Test file(s) that exercise it (path + test class/function names)
    - The exact `pytest` invocation that runs them
    - Threat surface (XSS, cookie tampering, render injection — read the existing implementation files at the call sites)
    - Status: green if the test exists in suite, "Deferred (no test)" if no coverage found

    No new tests written. If a TRACE-N item has no existing test, record it as a Gaps row in VALIDATION.md (Deferred) and as accepted risk in SECURITY.md if applicable.

    Capture the result in a working note (in-memory or scratch text) for Task 2 to consume. No file is created at this step — this is a discovery pass.
  </action>
  <acceptance_criteria>
    - All 5 TRACE-N items enumerated.
    - Each mapped to a test command OR explicitly marked "Deferred — no existing test".
    - Threat surface identified for each (auth, input, render, persistence).
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -ln "Phase 17\\|trace_panel\\|tsi_trace_open\\|trace-disclosure" tests/ -r | head -10</automated>
  </verify>
  <done>Working SC↔test map and threat surface map ready for VALIDATION.md/SECURITY.md authoring.</done>
</task>

<task type="auto">
  <name>Task 2: Write 17-VALIDATION.md and 17-SECURITY.md (single commit)</name>
  <files>.planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VALIDATION.md, .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-SECURITY.md</files>
  <read_first>
    - 27-VALIDATION.md (copy heading structure verbatim)
    - 27-SECURITY.md (copy threat-register, accepted-risks, audit-trail sections verbatim)
  </read_first>
  <action>
    Per D-08/D-09: write both files in one task → committed together by execute-plan.

    **17-VALIDATION.md** (mirror 27-VALIDATION.md structure):
    - Frontmatter: `phase: 17`, `slug: per-signal-calculation-transparency`, `status: validated`, `nyquist_compliant: true`, `wave_0_complete: true`, `created: 2026-05-10`, `audited: 2026-05-10`.
    - "# Phase 17 — Validation Strategy" with "> Reconstructed retroactively per Phase 29 D-06 mechanical retrofit." note.
    - "## Test Infrastructure" table (pytest version, config file, quick run cmd, full suite cmd, runtime).
    - "## Sampling Rate" (per-task, per-wave, pre-verify, max latency).
    - "## Per-Task Verification Map" (the matrix from Task 1).
    - "## Coverage by Requirement" (TRACE-1..5 → tasks).
    - "## Coverage by Threat Reference" (T-17-* → tasks).
    - "## Manual-Only Verifications" (any UAT or operator-only items — UAT-1 ATR hand-recalc, UAT-2 iOS Safari, UAT-3 cookie persistence — note these were the deferred items closed by Phase 28 + Phase 29).
    - "## Gaps" (any SC items with no existing automated test → "Deferred" status, owner: future v1.3.x).
    - "## Validation Sign-Off" with retroactive approval line "approved 2026-05-10 (retroactive reconstruction per Phase 29 D-06 mechanical retrofit)".

    **17-SECURITY.md** (mirror 27-SECURITY.md structure):
    - Frontmatter: `phase: 17`, `slug: per-signal-calculation-transparency`, `status: verified`, `threats_open: 0` (or remaining count if any are deferred), `asvs_level: 1`, `created: 2026-05-10`.
    - "# Phase 17 — Security" + "> Per-phase security contract: threat register, accepted risks, audit trail. Reconstructed retroactively per Phase 29 D-07 mechanical retrofit."
    - "## Trust Boundaries" — for Phase 17: cookie `tsi_trace_open` ↔ render path, persisted signal row ↔ trace renderer, attacker-controlled instrument id ↔ allowlist, OHLC scalar fields ↔ HTML render.
    - "## Threat Register" with `T-17-NN-NN` IDs for at least: cookie tampering (allowlist defence), XSS via OHLC scalar values (escape defence), trace-renderer drift / re-derivation from defaults (Phase 29 plan 03 lock-in via vote_params commits — reference). Each row: Category (STRIDE), Component, Disposition, Mitigation citing file:line OR test, Status.
    - "## Accepted Risks Log" with `AR-17-NN` rows for any deferred mitigations.
    - "## Security Audit Trail" with the 2026-05-10 retroactive audit row.
    - "## Sign-Off" checklist matching 27's.

    Both files ≤500 LOC each (CLAUDE.md cap). Realistic size: ~150-250 LOC for VALIDATION, ~100-180 LOC for SECURITY.

    Path discipline (D-09): files MUST be at `.planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VALIDATION.md` and `.../17-SECURITY.md` — same archive convention as 23 and 27.

    NO new tests, NO source code changes — docs-only retrofit.
  </action>
  <acceptance_criteria>
    - `test -f .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VALIDATION.md` succeeds.
    - `test -f .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-SECURITY.md` succeeds.
    - `grep -q "## Per-Task Verification Map\\|## Coverage Matrix" .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VALIDATION.md` succeeds.
    - `grep -q "## Threat Register\\|## Threat Surface" .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-SECURITY.md` succeeds.
    - `grep -q "phase: 17" .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VALIDATION.md` succeeds.
    - `grep -q "phase: 17" .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-SECURITY.md` succeeds.
    - `grep -cE "^\\| T-17" .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-SECURITY.md` ≥ 1 (at least one threat row).
    - VALIDATION matrix row count corresponds to TRACE SC-item count from `17-01-PLAN.md` (planner check at write time — count enumerated SC items, count matrix rows, log delta if any are Deferred).
    - `wc -l` both files ≤500.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && test -f .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VALIDATION.md && test -f .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-SECURITY.md && grep -q "phase: 17" .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VALIDATION.md && grep -q "phase: 17" .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-SECURITY.md && grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VALIDATION.md && grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-SECURITY.md && echo OK</automated>
  </verify>
  <done>Both docs exist at archive paths, frontmatter matches Phase 27 shape, coverage matrix + threat register populated from existing tests + code (no new tests). Format-precedent compliance against 27-VALIDATION.md / 27-SECURITY.md.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| docs ↔ git history | retroactive doc must reflect actually-shipped code, not aspirational state |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-29-04-01 | Tampering (drift) | VALIDATION.md cites tests that don't exist | mitigate | Task 1 discovery pass + grep gates in acceptance criteria |
| T-29-04-02 | Information Disclosure | SECURITY.md leaks threat detail attackers exploit | accept | Single-operator system; threats already shipped + mitigated; doc records public posture |
</threat_model>

<verification>
- Both files exist at the archive paths.
- Format mirrors Phase 27 verbatim where structure permits.
- Every TRACE SC item from 17-01-PLAN.md is either a green Coverage row OR a Deferred Gaps row.
- No new test files committed; no source code changes.
</verification>

<success_criteria>
ROADMAP SC-2 + SC-3 advanced for Phase 17. Plan 29-04 closes 1 of 7 sweep targets.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-04-SUMMARY.md`.
</output>