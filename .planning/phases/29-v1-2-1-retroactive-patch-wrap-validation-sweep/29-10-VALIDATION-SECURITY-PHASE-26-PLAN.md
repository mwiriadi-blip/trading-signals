---
phase: 29
plan_id: 29-10-VALIDATION-SECURITY-PHASE-26
plan: 10
type: execute
wave: 2
depends_on: []
requirements: [DEBT-03, DEBT-04]
files_modified:
  - .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-VALIDATION.md
  - .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-SECURITY.md
autonomous: true
must_haves:
  truths:
    - "`26-VALIDATION.md` exists in archive dir with Nyquist matrix per Phase 27 format."
    - "`26-SECURITY.md` exists in archive dir with threat-model per Phase 27 format."
    - "Coverage matrix maps Phase 26 SC items (UAT-1..6 multi-tab scoping fixes + 8 plan deliverables) to existing tests OR Deferred."
    - "Threat surface enumerates secret-in-tracked-files audit, cache+cookie hardening, multi-tab scoping isolation."
  artifacts:
    - path: ".planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-VALIDATION.md"
      provides: "Nyquist coverage retrofit for Phase 26"
      contains: "Per-Task Verification Map"
    - path: ".planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-SECURITY.md"
      provides: "Threat-model retrofit for Phase 26"
      contains: "Threat Register"
  key_links:
    - from: "26-VALIDATION.md Coverage Matrix"
      to: "tests/ files exercising Phase 26 fixes"
      via: "Automated Command column"
      pattern: ".venv/bin/pytest tests/test_"
    - from: "26-SECURITY.md Threat Register"
      to: "Phase 26 implementation files (multi-tab scoping, cookie/cache, secret audit)"
      via: "Mitigation column"
      pattern: "(mitigate|accept|transfer)"
---

<objective>
Mechanical retrofit per D-06/D-07/D-08: write `26-VALIDATION.md` + `26-SECURITY.md` for Phase 26 (Phase 25 follow-up multi-tab scoping fixes). 8 plans + UAT-1..6 multi-tab scoping.
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
- `.planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md`
- `.planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-UAT.md` (UAT-1..6)
- `.planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-VERIFICATION.md`
- `.planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-DEBT.md`
- All 8 `26-NN-*-PLAN.md` and `26-NN-SUMMARY.md` files
- 27-VALIDATION.md / 27-SECURITY.md
- 29-CONTEXT.md §D-06..D-09
</read_first>

<interfaces>
Same shape as 29-04. Threat IDs `T-26-NN-NN`. Phase 26 has 8 plans (26-01..26-08) covering: secret audit + gitignore, deploy-test regex fix, failing-test scaffolding, template-substitute helper, active-market scoping, renderer API cleanup, cache+cookie hardening, dead code + doc cleanup.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Enumerate Phase 26 SC items across 8 plans + UAT-1..6 + map to existing tests</name>
  <files>(no files modified — discovery pass)</files>
  <read_first>
    - All `26-*-PLAN.md` files (SC blocks)
    - All `26-*-SUMMARY.md` files (tests committed)
    - `26-UAT.md` (UAT-1..6 enumeration — note xfail-flipped-green coverage Phase 28 D-01 chose NOT to rely on)
    - `26-VERIFICATION.md` (PASS evidence)
    - `26-DEBT.md` (any debt items closed in this phase)
    - `grep -rln "Phase 26\\|active.market\\|multi.tab\\|secret.audit" tests/`
  </read_first>
  <action>
    Discovery only. Map each of 8 plans + UAT-1..6 → tests + threat surface.

    Note Phase 28 D-01 stance: "Phase 26's automated coverage is treated as a regression net, not as the primary evidence" — VALIDATION matrix records the regression net as actual coverage; UAT-1..6 themselves are documented in Phase 28 28-VERIFICATION.md (cold-start = FAIL going into Phase 29 plan 02; UAT-2..6 = PASS at Phase 28 close).

    Identify Deferred items.
  </action>
  <acceptance_criteria>
    - All 8 plans' SC items + UAT-1..6 enumerated.
    - Each mapped to test command OR Deferred.
    - Threat surface per item identified.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && ls .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-*-PLAN.md | wc -l</automated>
  </verify>
  <done>SC↔test map ready.</done>
</task>

<task type="auto">
  <name>Task 2: Write 26-VALIDATION.md and 26-SECURITY.md (single commit)</name>
  <files>.planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-VALIDATION.md, .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-SECURITY.md</files>
  <read_first>
    - 27-VALIDATION.md and 27-SECURITY.md
  </read_first>
  <action>
    Per D-08: write both files in one task. Mirror Phase 27 format.

    **26-VALIDATION.md** frontmatter: `phase: 26`, `slug: phase-25-followup-multi-tab-scoping-fixes`, `status: validated`, `nyquist_compliant: true`, `wave_0_complete: true`, `created: 2026-05-10`, `audited: 2026-05-10`.

    **26-SECURITY.md** frontmatter: `phase: 26`, `slug: phase-25-followup-multi-tab-scoping-fixes`, `status: verified`, `threats_open: 0`, `asvs_level: 1`, `created: 2026-05-10`.

    Trust Boundaries — secret in tracked files (CI gate), cache validity ↔ cookie scope, active-market scoping ↔ tab isolation. Threat Register `T-26-NN-NN`: secret leak via tracked file (mitigate — gitignore + CI), cache poisoning via stale entries (mitigate via cookie+cache hardening), cross-tab scoping leak (mitigate via active-market scoping plan 26-05).

    Both files ≤500 LOC.
  </action>
  <acceptance_criteria>
    - `test -f .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-VALIDATION.md` succeeds.
    - `test -f .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-SECURITY.md` succeeds.
    - `grep -q "phase: 26" .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-VALIDATION.md` succeeds.
    - `grep -q "phase: 26" .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-SECURITY.md` succeeds.
    - `grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-VALIDATION.md` succeeds.
    - `grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-SECURITY.md` succeeds.
    - `grep -cE "^\\| T-26" .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-SECURITY.md` ≥ 1.
    - VALIDATION matrix row count ≥ 8 (one row per plan minimum, plus UAT-1..6 either as separate rows or noted in evidence).
    - `wc -l` both ≤500.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && test -f .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-VALIDATION.md && test -f .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-SECURITY.md && grep -q "phase: 26" .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-VALIDATION.md && grep -q "phase: 26" .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-SECURITY.md && grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-VALIDATION.md && grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-SECURITY.md && echo OK</automated>
  </verify>
  <done>Both docs exist; format mirrors Phase 27; matrix complete.</done>
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
| T-29-10-01 | Tampering (drift) | VALIDATION cites missing tests | mitigate | Task 1 discovery + grep gates |
| T-29-10-02 | Information Disclosure | SECURITY leaks attacker-useful detail | accept | Single-operator; threats already mitigated |
</threat_model>

<verification>
- Both files exist.
- Phase 26 SC items all Covered or Deferred.
</verification>

<success_criteria>
ROADMAP SC-2 + SC-3 advanced for Phase 26. Plan 29-10 closes 7 of 7 sweep targets — DEBT-03 + DEBT-04 fully closed.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-10-SUMMARY.md`.
</output>