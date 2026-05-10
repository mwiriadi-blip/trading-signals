---
phase: 29
plan_id: 29-05-VALIDATION-SECURITY-PHASE-19
plan: 05
type: execute
wave: 2
depends_on: []
requirements: [DEBT-03, DEBT-04]
files_modified:
  - .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VALIDATION.md
  - .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-SECURITY.md
autonomous: true
must_haves:
  truths:
    - "`19-VALIDATION.md` exists in archive dir with Nyquist coverage matrix matching Phase 23 + 27 format."
    - "`19-SECURITY.md` exists in archive dir with threat-model + mitigations matching Phase 27 format."
    - "Coverage matrix maps every Phase 19 SC item (LEDGER-1..6) to existing tests OR to a Gaps row marked 'Deferred'."
    - "Threat surface enumerates HTMX form input, Decimal money math, state.json persistence boundaries; mitigations cite already-shipped code."
  artifacts:
    - path: ".planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VALIDATION.md"
      provides: "Nyquist coverage matrix retrofit for Phase 19"
      contains: "Per-Task Verification Map"
    - path: ".planning/milestones/v1.2-phases/19-paper-trade-ledger/19-SECURITY.md"
      provides: "Threat-model + mitigations retrofit for Phase 19"
      contains: "Threat Register"
  key_links:
    - from: "19-VALIDATION.md Coverage Matrix"
      to: "tests/test_paper_trades.py + tests/test_pnl_engine.py + tests/test_web_*"
      via: "Automated Command column"
      pattern: ".venv/bin/pytest tests/test_"
    - from: "19-SECURITY.md Threat Register"
      to: "Phase 19 implementation files (paper-trade routes, pnl_engine, state schema)"
      via: "Mitigation column citing file:line"
      pattern: "(mitigate|accept|transfer)"
---

<objective>
Mechanical retrofit per D-06/D-07/D-08: write `19-VALIDATION.md` + `19-SECURITY.md` for Phase 19 (paper-trade ledger). Format from Phase 27. No new tests.

Closes DEBT-03 + DEBT-04 for Phase 19. LEDGER-1..6 SC items.
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
- `.planning/milestones/v1.2-phases/19-paper-trade-ledger/19-CONTEXT.md`
- `.planning/milestones/v1.2-phases/19-paper-trade-ledger/19-01-PLAN.md` (LEDGER-1..6 SC items)
- `.planning/milestones/v1.2-phases/19-paper-trade-ledger/19-01-SUMMARY.md`
- `.planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VERIFICATION.md`
- 27-VALIDATION.md and 27-SECURITY.md (verbatim format templates)
- 29-CONTEXT.md §D-06, D-07, D-08, D-09
</read_first>

<interfaces>
Phase 27 column shapes (copy verbatim):
- Validation map: `| Task ID | Plan | Wave | Requirement / Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |`
- Threat register: `| Threat ID | Category | Component | Disposition | Mitigation | Status |`

Threat IDs `T-19-NN-NN`. Risk IDs `AR-19-NN`. Phase 19 likely surfaces: paper-trade form input → state.json (HTMX, Decimal money math), aggregate stats render (XSS via journal text), open-trade race vs daily run (lock kernel), entry-side cost helper.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Enumerate Phase 19 LEDGER-N SC items + map to existing tests</name>
  <files>(no files modified — discovery pass)</files>
  <read_first>
    - `19-01-PLAN.md` (LEDGER-1..6 SC block)
    - `19-01-SUMMARY.md` (test files committed)
    - `19-VERIFICATION.md` (PASS evidence with test commands)
    - `tests/test_paper_trades.py`, `tests/test_pnl_engine.py`, `tests/test_web_paper_trades*.py` — `grep -rln "LEDGER\\|paper_trade\\|paper-trade\\|Phase 19" tests/`
  </read_first>
  <action>
    Discovery only. Build SC↔test map and threat surface for LEDGER-1..6. Identify Deferred items (no existing test).

    For each LEDGER-N: test file paths + pytest invocation + threat surface (HTMX form, Decimal serialisation, journal text XSS, state lock contention).

    Capture working notes for Task 2.
  </action>
  <acceptance_criteria>
    - All 6 LEDGER-N items enumerated.
    - Each mapped to test command OR "Deferred — no test".
    - Threat surface identified per item.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -rln "paper_trade\\|paper-trade\\|LEDGER" tests/ | head -10</automated>
  </verify>
  <done>SC↔test map and threat map ready.</done>
</task>

<task type="auto">
  <name>Task 2: Write 19-VALIDATION.md and 19-SECURITY.md (single commit)</name>
  <files>.planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VALIDATION.md, .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-SECURITY.md</files>
  <read_first>
    - 27-VALIDATION.md and 27-SECURITY.md (verbatim format templates)
  </read_first>
  <action>
    Write both files in one task per D-08. Use Phase 27 format verbatim.

    **19-VALIDATION.md** sections (mirror 27):
    - Frontmatter (`phase: 19`, `slug: paper-trade-ledger`, `status: validated`, `nyquist_compliant: true`, `wave_0_complete: true`, `created: 2026-05-10`, `audited: 2026-05-10`).
    - Test Infrastructure / Sampling Rate / Per-Task Verification Map (the matrix from Task 1) / Coverage by Requirement (LEDGER-1..6 → tasks) / Coverage by Threat Reference / Manual-Only Verifications (if any) / Gaps (Deferred items) / Validation Sign-Off.

    **19-SECURITY.md** sections (mirror 27):
    - Frontmatter (`phase: 19`, `slug: paper-trade-ledger`, `status: verified`, `threats_open: 0`, `asvs_level: 1`, `created: 2026-05-10`).
    - Trust Boundaries — for Phase 19: HTMX form ↔ POST handler, money values ↔ Decimal serialisation ↔ state.json, journal text ↔ render escape, paper-trade form ↔ entry-side-cost helper.
    - Threat Register with `T-19-NN-NN` rows for at least: HTMX CSRF (cookie-session covers), Decimal precision drift (Phase 27 cross-link), journal XSS (Phase 27 cross-link if same render path), entry-side cost mismatch.
    - Accepted Risks Log + Security Audit Trail + Sign-Off.

    Both files ≤500 LOC. Path: `.planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VALIDATION.md` and `19-SECURITY.md`.
  </action>
  <acceptance_criteria>
    - `test -f .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VALIDATION.md` succeeds.
    - `test -f .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-SECURITY.md` succeeds.
    - `grep -q "phase: 19" .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VALIDATION.md` succeeds.
    - `grep -q "phase: 19" .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-SECURITY.md` succeeds.
    - `grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VALIDATION.md` succeeds.
    - `grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-SECURITY.md` succeeds.
    - `grep -cE "^\\| T-19" .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-SECURITY.md` ≥ 1.
    - VALIDATION matrix row count matches LEDGER SC item count from `19-01-PLAN.md` (Deferred rows count).
    - `wc -l` both files ≤500.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && test -f .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VALIDATION.md && test -f .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-SECURITY.md && grep -q "phase: 19" .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VALIDATION.md && grep -q "phase: 19" .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-SECURITY.md && grep -qE "## (Per-Task Verification Map|Coverage Matrix)" .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-VALIDATION.md && grep -qE "## Threat (Register|Surface)" .planning/milestones/v1.2-phases/19-paper-trade-ledger/19-SECURITY.md && echo OK</automated>
  </verify>
  <done>Both docs exist; format mirrors Phase 27; coverage matrix + threat register populated from existing artefacts.</done>
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
| T-29-05-01 | Tampering (drift) | VALIDATION.md cites tests that don't exist | mitigate | Task 1 discovery + grep gates |
| T-29-05-02 | Information Disclosure | SECURITY.md leaks threat detail attackers exploit | accept | Single-operator system; threats already shipped + mitigated |
</threat_model>

<verification>
- Both files exist at archive paths.
- Every LEDGER SC item is a Coverage row OR a Deferred Gaps row.
- No new test files; no source changes.
</verification>

<success_criteria>
ROADMAP SC-2 + SC-3 advanced for Phase 19. Plan 29-05 closes 2 of 7 sweep targets.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-05-SUMMARY.md`.
</output>