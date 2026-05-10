---
phase: 29
plan_id: 29-06-VALIDATION-SECURITY-PHASE-20
plan: 06
type: execute
wave: 2
depends_on: []
requirements: [DEBT-03, DEBT-04]
files_modified:
  - .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-VALIDATION.md
  - .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-SECURITY.md
autonomous: true
must_haves:
  truths:
    - "`20-VALIDATION.md` exists in archive dir with Nyquist matrix per Phase 27 format."
    - "`20-SECURITY.md` exists in archive dir with threat-model per Phase 27 format."
    - "Coverage matrix maps every Phase 20 SC item (ALERT-1..4) to existing tests OR Deferred."
    - "Threat surface enumerates alert dedup state, two-phase commit pattern (mutate_state non-reentrant), Resend dispatch, alert state-transition determinism."
  artifacts:
    - path: ".planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-VALIDATION.md"
      provides: "Nyquist coverage retrofit for Phase 20"
      contains: "Per-Task Verification Map"
    - path: ".planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-SECURITY.md"
      provides: "Threat-model retrofit for Phase 20"
      contains: "Threat Register"
  key_links:
    - from: "20-VALIDATION.md Coverage Matrix"
      to: "tests/test_notifier_stop_alert.py + tests/test_main_alerts.py + related"
      via: "Automated Command column"
      pattern: ".venv/bin/pytest tests/test_"
    - from: "20-SECURITY.md Threat Register"
      to: "Phase 20 implementation files (alert dedup state, daily_run dispatch path)"
      via: "Mitigation column"
      pattern: "(mitigate|accept|transfer)"
---

<objective>
Mechanical retrofit per D-06/D-07/D-08: write `20-VALIDATION.md` + `20-SECURITY.md` for Phase 20 (stop-loss monitoring & alerts). Format from Phase 27. No new tests.

Closes DEBT-03 + DEBT-04 for Phase 20. ALERT-1..4 SC items.
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
- `.planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-CONTEXT.md`
- `.planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-01-PLAN.md` (ALERT-1..4)
- `.planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-01-SUMMARY.md`
- `.planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-VERIFICATION.md`
- 27-VALIDATION.md / 27-SECURITY.md (templates)
- 29-CONTEXT.md §D-06..D-09
- Project-local LEARNING "state_manager.mutate_state is non-reentrant" — directly relevant to Phase 20 two-phase commit threat
</read_first>

<interfaces>
Same column shapes as 29-04/29-05. Threat IDs `T-20-NN-NN`. Phase 20 surfaces: alert state-transition dedup, two-phase commit (eval-then-write outside `mutate_state` closure), Resend rate limit, alert race condition between daily run and HTMX trade close.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Enumerate Phase 20 ALERT-N SC items + map to existing tests</name>
  <files>(no files modified — discovery pass)</files>
  <read_first>
    - `20-01-PLAN.md` (ALERT-1..4)
    - `20-01-SUMMARY.md`
    - `20-VERIFICATION.md`
    - `tests/test_notifier_stop_alert.py`, `tests/test_main_alerts.py` — `grep -rln "ALERT\\|stop_alert\\|stop-loss\\|Phase 20" tests/`
  </read_first>
  <action>
    Discovery only. Map each ALERT-N → tests + threat surface (alert state machine, two-phase commit, Resend dispatch). Identify Deferred items.
  </action>
  <acceptance_criteria>
    - All 4 ALERT-N items enumerated.
    - Each mapped to test command OR "Deferred".
    - Threat surface identified.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -rln "stop_alert\\|stop-loss\\|ALERT" tests/ | head -10</automated>
  </verify>
  <done>SC↔test map and threat map ready.</done>
</task>

<task type="auto">
  <name>Task 2: Write 20-VALIDATION.md and 20-SECURITY.md (single commit)</name>
  <files>.planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-VALIDATION.md, .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-SECURITY.md</files>
  <read_first>
    - 27-VALIDATION.md and 27-SECURITY.md
  </read_first>
  <action>
    Per D-08: write both files in one task → committed together. Mirror Phase 27 format verbatim.

    **20-VALIDATION.md** frontmatter: `phase: 20`, `slug: stop-loss-monitoring-alerts`, `status: validated`, `nyquist_compliant: true`, `wave_0_complete: true`, `created: 2026-05-10`, `audited: 2026-05-10`.

    Sections: Test Infrastructure / Sampling Rate / Per-Task Verification Map (matrix from Task 1) / Coverage by Requirement (ALERT-1..4) / Coverage by Threat Reference / Manual-Only Verifications / Gaps / Validation Sign-Off.

    **20-SECURITY.md** frontmatter: `phase: 20`, `slug: stop-loss-monitoring-alerts`, `status: verified`, `threats_open: 0`, `asvs_level: 1`, `created: 2026-05-10`.

    Trust Boundaries — alert dedup state ↔ daily run, mutate_state non-reentrancy contract, Resend HTTPS dispatch. Threat Register with `T-20-NN-NN` rows: alert race vs HTMX close, two-phase-commit deadlock if violated (project LEARNING reference), Resend dispatch failure → silent loss (link to 27-11 fallback), state-transition dedup byass.

    Both files ≤500 LOC.
  </action>
  <acceptance_criteria>
    - `test -f .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-VALIDATION.md` succeeds.
    - `test -f .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-SECURITY.md` succeeds.
    - `grep -q "phase: 20" .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-VALIDATION.md` succeeds.
    - `grep -q "phase: 20" .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-SECURITY.md` succeeds.
    - `grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-VALIDATION.md` succeeds.
    - `grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-SECURITY.md` succeeds.
    - `grep -cE "^\\| T-20" .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-SECURITY.md` ≥ 1.
    - Matrix row count matches ALERT SC items from `20-01-PLAN.md`.
    - `wc -l` both ≤500.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && test -f .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-VALIDATION.md && test -f .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-SECURITY.md && grep -q "phase: 20" .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-VALIDATION.md && grep -q "phase: 20" .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-SECURITY.md && grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-VALIDATION.md && grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/20-SECURITY.md && echo OK</automated>
  </verify>
  <done>Both docs exist at archive paths; format mirrors Phase 27; coverage + threat register populated.</done>
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
| T-29-06-01 | Tampering (drift) | VALIDATION cites missing tests | mitigate | Task 1 discovery + grep gates |
| T-29-06-02 | Information Disclosure | SECURITY leaks attacker-useful detail | accept | Single-operator; threats already mitigated |
</threat_model>

<verification>
- Both files exist.
- ALERT SC items all Covered or Deferred.
</verification>

<success_criteria>
ROADMAP SC-2 + SC-3 advanced for Phase 20. Plan 29-06 closes 3 of 7 sweep targets.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-06-SUMMARY.md`.
</output>