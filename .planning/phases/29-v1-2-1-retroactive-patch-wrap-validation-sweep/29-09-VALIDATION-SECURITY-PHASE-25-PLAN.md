---
phase: 29
plan_id: 29-09-VALIDATION-SECURITY-PHASE-25
plan: 09
type: execute
wave: 2
depends_on: []
requirements: [DEBT-03, DEBT-04]
files_modified:
  - .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VALIDATION.md
  - .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-SECURITY.md
autonomous: true
must_haves:
  truths:
    - "`25-VALIDATION.md` exists in archive dir with Nyquist matrix per Phase 27 format."
    - "`25-SECURITY.md` exists in archive dir with threat-model per Phase 27 format."
    - "Coverage matrix maps Phase 25 SC items (D-06 two-axis nav + multi-tab persistence + 12 plan deliverables) to existing tests OR Deferred."
    - "Threat surface enumerates HTMX swap injection, cookie/URL tab persistence, equity-chart XSS gate, market_id allowlist."
  artifacts:
    - path: ".planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VALIDATION.md"
      provides: "Nyquist coverage retrofit for Phase 25"
      contains: "Per-Task Verification Map"
    - path: ".planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-SECURITY.md"
      provides: "Threat-model retrofit for Phase 25"
      contains: "Threat Register"
  key_links:
    - from: "25-VALIDATION.md Coverage Matrix"
      to: "tests/test_dashboard*.py + tests/test_web_*.py"
      via: "Automated Command column"
      pattern: ".venv/bin/pytest tests/test_"
    - from: "25-SECURITY.md Threat Register"
      to: "Phase 25 implementation files (multi-tab nav, cookie writers, render path)"
      via: "Mitigation column"
      pattern: "(mitigate|accept|transfer)"
---

<objective>
Mechanical retrofit per D-06/D-07/D-08: write `25-VALIDATION.md` + `25-SECURITY.md` for Phase 25 (dashboard UI/UX overhaul + true multi-tab market preferences). 12 plans + D-06 two-axis nav + multi-tab persistence.
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

<read_first>
- `.planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-CONTEXT.md` (D-01..D-NN)
- `.planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VERIFICATION.md`
- All 12 `25-NN-*-PLAN.md` files (each contains its own SC items)
- All 12 `25-NN-SUMMARY.md` files (test files committed per plan)
- `25-11-gap-closure-PLAN.md` and `25-11-gap-closure-SUMMARY.md` (the gap-closure D-14 / D-11 fixes — explicit Deferred-then-closed pattern)
- 27-VALIDATION.md / 27-SECURITY.md
- 29-CONTEXT.md §D-06..D-09
- Project-local LEARNING "Plan SUMMARY.md self-attestation is unreliable" (2026-05-06) — directly relevant, since Phase 25 was the case study; the retrofit must reflect what's ACTUALLY in code, not what SUMMARY narrated.
</read_first>

<interfaces>
Same shape as 29-04. Threat IDs `T-25-NN-NN`. Phase 25 has the largest SC surface in this sweep (12 plans + gap closure). Phase 25 SC sources: each plan's PLAN.md SC block + the D-06 two-axis nav decision.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Enumerate Phase 25 SC items across 12 plans + map to existing tests</name>
  <files>(no files modified — discovery pass)</files>
  <read_first>
    - All `25-*-PLAN.md` files (SC blocks)
    - All `25-*-SUMMARY.md` files (test files committed)
    - `25-VERIFICATION.md` (PASS evidence)
    - `25-DISCUSSION-LOG.md` (D-06 two-axis nav decision)
    - `grep -rln "Phase 25\\|multi-tab\\|two-axis\\|tab-strip" tests/`
  </read_first>
  <action>
    Discovery only. For each of the 12 plans (25-01..25-10 + 25-09b + 25-11) plus the cross-cutting D-06 + multi-tab persistence, list SC items → tests.

    Important: per project LEARNING 2026-05-06 (Plan 25-08 D-14 gap closure), DO NOT trust SUMMARY-level claims about coverage. Verify each test exists with `grep -ln "<test_function_name>" tests/`. Items where SUMMARY says "tested" but no test file exists → mark Deferred.

    The matrix will be larger than other Phase 17/19/20/22 retrofits — likely 20-40 rows.
  </action>
  <acceptance_criteria>
    - All 12 plans' SC items enumerated.
    - D-06 two-axis nav + multi-tab persistence SC explicitly listed.
    - Each SC item mapped to a test file:function OR explicitly Deferred (with rationale).
    - SUMMARY-claim verification done — no row trusts SUMMARY without grep.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && ls .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-*-PLAN.md | wc -l</automated>
  </verify>
  <done>Per-plan SC↔test map ready, with Deferred rows for SUMMARY-only claims.</done>
</task>

<task type="auto">
  <name>Task 2: Write 25-VALIDATION.md and 25-SECURITY.md (single commit)</name>
  <files>.planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VALIDATION.md, .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-SECURITY.md</files>
  <read_first>
    - 27-VALIDATION.md and 27-SECURITY.md
  </read_first>
  <action>
    Per D-08: write both files in one task. Mirror Phase 27 format.

    **25-VALIDATION.md** frontmatter: `phase: 25`, `slug: dashboard-ui-ux-overhaul-true-multi-tab-market-preferences`, `status: validated`, `nyquist_compliant: true`, `wave_0_complete: true`, `created: 2026-05-10`, `audited: 2026-05-10`.

    Standard sections. Note this matrix is the largest in the sweep.

    **25-SECURITY.md** frontmatter: `phase: 25`, `slug: dashboard-ui-ux-overhaul-true-multi-tab-market-preferences`, `status: verified`, `threats_open: 0`, `asvs_level: 1`, `created: 2026-05-10`.

    Trust Boundaries — HTMX swap target ↔ render, `selected_market` cookie ↔ allowlist, equity-chart payload ↔ XSS escape (Phase 27 cross-link T-27-08-03), URL tab param ↔ allowlist. Threat Register `T-25-NN-NN` rows per category.

    Both files ≤500 LOC.
  </action>
  <acceptance_criteria>
    - `test -f .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VALIDATION.md` succeeds.
    - `test -f .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-SECURITY.md` succeeds.
    - `grep -q "phase: 25" .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VALIDATION.md` succeeds.
    - `grep -q "phase: 25" .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-SECURITY.md` succeeds.
    - `grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VALIDATION.md` succeeds.
    - `grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-SECURITY.md` succeeds.
    - `grep -cE "^\\| T-25" .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-SECURITY.md` ≥ 1.
    - VALIDATION matrix row count ≥ 12 (one row per plan minimum; likely more once SC items expanded).
    - `wc -l` both ≤500.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && test -f .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VALIDATION.md && test -f .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-SECURITY.md && grep -q "phase: 25" .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VALIDATION.md && grep -q "phase: 25" .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-SECURITY.md && grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VALIDATION.md && grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-SECURITY.md && echo OK</automated>
  </verify>
  <done>Both docs exist; format mirrors Phase 27; matrix reflects actual code-verified test coverage (per LEARNING 2026-05-06).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| docs ↔ git history | retroactive doc must reflect shipped code |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-29-09-01 | Tampering (drift) | VALIDATION cites SUMMARY-claim tests not in code | mitigate | Task 1 grep-verifies every claim per LEARNING 2026-05-06 |
| T-29-09-02 | Information Disclosure | SECURITY leaks attacker-useful detail | accept | Single-operator; threats already mitigated |
</threat_model>

<verification>
- Both files exist.
- Phase 25 SC items all Covered or Deferred (with rationale).
- No SUMMARY-trust shortcut in matrix.
</verification>

<success_criteria>
ROADMAP SC-2 + SC-3 advanced for Phase 25. Plan 29-09 closes 6 of 7 sweep targets.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-09-SUMMARY.md`.
</output>