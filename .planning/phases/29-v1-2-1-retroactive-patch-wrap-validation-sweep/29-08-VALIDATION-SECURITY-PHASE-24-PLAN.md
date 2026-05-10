---
phase: 29
plan_id: 29-08-VALIDATION-SECURITY-PHASE-24
plan: 08
type: execute
wave: 2
depends_on: []
requirements: [DEBT-03, DEBT-04]
files_modified:
  - .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-VALIDATION.md
  - .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-SECURITY.md
autonomous: true
must_haves:
  truths:
    - "`24-VALIDATION.md` exists in archive dir with Nyquist matrix per Phase 27 format."
    - "`24-SECURITY.md` exists in archive dir with threat-model per Phase 27 format."
    - "Coverage matrix maps every Phase 24 codemoot finding fix to existing tests OR Deferred."
    - "Threat surface enumerates the codemoot-driven security/correctness threats addressed by this phase."
  artifacts:
    - path: ".planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-VALIDATION.md"
      provides: "Nyquist coverage retrofit for Phase 24"
      contains: "Per-Task Verification Map"
    - path: ".planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-SECURITY.md"
      provides: "Threat-model retrofit for Phase 24"
      contains: "Threat Register"
  key_links:
    - from: "24-VALIDATION.md Coverage Matrix"
      to: "tests/ files exercising codemoot-finding fixes"
      via: "Automated Command column"
      pattern: ".venv/bin/pytest tests/test_"
    - from: "24-SECURITY.md Threat Register"
      to: "Phase 24 fixed-finding implementation files"
      via: "Mitigation column"
      pattern: "(mitigate|accept|transfer)"
---

<objective>
Mechanical retrofit per D-06/D-07/D-08: write `24-VALIDATION.md` + `24-SECURITY.md` for Phase 24 (v1.2 codemoot fix phase). Codemoot-driven SC items (varies — read 24-REVIEW.md and PLAN.md for the per-finding list).
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
- `.planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-REVIEW.md` (the codemoot findings list)
- `.planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/PLAN.md` (the fix tasks per finding)
- `.planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/SUMMARY.md` (what shipped)
- `.planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-VERIFICATION.md`
- 27-VALIDATION.md / 27-SECURITY.md
- 29-CONTEXT.md §D-06..D-09
</read_first>

<interfaces>
Same shape as 29-04. Threat IDs `T-24-NN-NN`. Phase 24 SC list = the codemoot finding fixes; enumerate from `24-REVIEW.md` per-finding rows.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Enumerate Phase 24 codemoot findings + map to existing tests</name>
  <files>(no files modified — discovery pass)</files>
  <read_first>
    - `24-REVIEW.md` (codemoot findings)
    - `PLAN.md` (fix tasks)
    - `SUMMARY.md` (what landed)
    - `24-VERIFICATION.md`
    - `grep -rln "Phase 24\\|codemoot" tests/`
  </read_first>
  <action>
    Discovery only. List each codemoot finding from `24-REVIEW.md` → fix task in `PLAN.md` → test that locks the fix.

    Identify Deferred items (findings closed without an automated test, e.g., docs-only or false-positives that needed no fix).
  </action>
  <acceptance_criteria>
    - All Phase 24 codemoot findings enumerated.
    - Each mapped to test command OR "Deferred — no test (rationale)".
    - Threat surface per finding identified.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -c "^### " .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-REVIEW.md 2>/dev/null || echo "review_present_else_check_PLAN.md"</automated>
  </verify>
  <done>Finding↔test map ready.</done>
</task>

<task type="auto">
  <name>Task 2: Write 24-VALIDATION.md and 24-SECURITY.md (single commit)</name>
  <files>.planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-VALIDATION.md, .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-SECURITY.md</files>
  <read_first>
    - 27-VALIDATION.md and 27-SECURITY.md
  </read_first>
  <action>
    Per D-08: write both files in one task. Mirror Phase 27 format.

    **24-VALIDATION.md** frontmatter: `phase: 24`, `slug: v1-2-codemoot-fix-phase`, `status: validated`, `nyquist_compliant: true`, `wave_0_complete: true`, `created: 2026-05-10`, `audited: 2026-05-10`.

    **24-SECURITY.md** frontmatter: `phase: 24`, `slug: v1-2-codemoot-fix-phase`, `status: verified`, `threats_open: 0`, `asvs_level: 1`, `created: 2026-05-10`.

    Trust Boundaries — codemoot finding categories represented (likely subset of Phase 27's: Tampering / DoS / Info Disclosure). Threat Register `T-24-NN-NN` rows per finding fix.

    Both files ≤500 LOC.
  </action>
  <acceptance_criteria>
    - `test -f .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-VALIDATION.md` succeeds.
    - `test -f .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-SECURITY.md` succeeds.
    - `grep -q "phase: 24" .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-VALIDATION.md` succeeds.
    - `grep -q "phase: 24" .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-SECURITY.md` succeeds.
    - `grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-VALIDATION.md` succeeds.
    - `grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-SECURITY.md` succeeds.
    - `grep -cE "^\\| T-24" .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-SECURITY.md` ≥ 1.
    - `wc -l` both ≤500.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && test -f .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-VALIDATION.md && test -f .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-SECURITY.md && grep -q "phase: 24" .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-VALIDATION.md && grep -q "phase: 24" .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-SECURITY.md && grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-VALIDATION.md && grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/24-SECURITY.md && echo OK</automated>
  </verify>
  <done>Both docs exist; format mirrors Phase 27.</done>
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
| T-29-08-01 | Tampering (drift) | VALIDATION cites missing tests | mitigate | Task 1 discovery + grep gates |
| T-29-08-02 | Information Disclosure | SECURITY leaks attacker-useful detail | accept | Single-operator; threats already mitigated |
</threat_model>

<verification>
- Both files exist.
- Codemoot findings all Covered or Deferred.
</verification>

<success_criteria>
ROADMAP SC-2 + SC-3 advanced for Phase 24. Plan 29-08 closes 5 of 7 sweep targets.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-08-SUMMARY.md`.
</output>