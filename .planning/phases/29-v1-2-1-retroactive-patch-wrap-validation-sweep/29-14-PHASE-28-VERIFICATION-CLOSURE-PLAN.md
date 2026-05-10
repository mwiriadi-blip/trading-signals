---
phase: 29
plan_id: 29-14-PHASE-28-VERIFICATION-CLOSURE
plan: 14
type: execute
wave: 5
depends_on:
  - 29-02-UAT-26-1-COLDSTART-JS-FIX
  - 29-11-UAT-17-1-ATR-SEED-EXPOSURE
  - 29-12-UAT-17-2-IOS-SAFARI-DETAILS-OPEN
  - 29-13-UAT-23-1-YFINANCE-SPIKE
requirements: []
files_modified:
  - .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md
autonomous: false
must_haves:
  truths:
    - "`28-VERIFICATION.md` retains all original FAIL rows + evidence verbatim (history preserved per D-17)."
    - "PASS rows are APPENDED for each Phase 28 FAIL that Phase 29 resolved (UAT-26-1, UAT-17-1, UAT-17-2; UAT-23-1 if TIGHT branch in plan 29-13, else deferred-to-29.5 row)."
    - "Frontmatter `status: partial` flips to `status: passed` IFF all 4 FAILs are resolved in Phase 29; otherwise stays `partial` with a note pointing to Phase 29.5."
    - "A `## Phase 29 Closure` notes paragraph names the resolving plans + commit shas."
    - "Operator iPhone Safari re-test for UAT-17-2 captured as a one-line PASS note in the appended row (per Phase 28 D-03 manual-only pattern)."
  artifacts:
    - path: ".planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md"
      provides: "Append-only update with PASS rows + closure notes"
      contains: "Phase 29 Closure"
  key_links:
    - from: "Phase 29 plans 02/11/12/13"
      to: "28-VERIFICATION.md PASS rows"
      via: "Appended rows naming resolving plan_id + commit"
      pattern: "29-02|29-11|29-12|29-13"
---

<objective>
Per D-17: append PASS rows to `28-VERIFICATION.md` for each Phase 28 FAIL that Phase 29 resolved. Preserve original FAIL evidence (don't rewrite history). Flip frontmatter `status: partial` → `status: passed` IFF all 4 FAILs closed in Phase 29; otherwise stay `partial` with a Phase 29.5 deferral note. Add a Phase 29 closure notes paragraph naming resolving plans + commits.

`autonomous: false` — Task 2 has a `checkpoint:human-verify` gate where the operator runs the iPhone Safari scenario manually for UAT-17-2 and reports PASS/FAIL inline (mirrors Phase 28 D-03 / D-14 pattern).

depends_on: all FAIL-fix plans (29-02, 29-11, 29-12, 29-13) — wave 5 runs only after their fixes verify.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-CONTEXT.md
@.planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md

<read_first>
- `28-VERIFICATION.md` (the file being appended to — read frontmatter shape + existing table structure)
- `29-02-SUMMARY.md` (cold-start JS fix — for the closure-row commit reference)
- `29-11-SUMMARY.md` (ATR seed exposure — for the closure-row commit reference)
- `29-12-SUMMARY.md` (iOS Safari `<details open>` server-side fix — for the closure-row commit reference)
- `29-13-SUMMARY.md` (yfinance spike — branch outcome: TIGHT or WIDE-deferred)
- 29-CONTEXT.md §D-17 (the append-only contract)
- Phase 28 28-CONTEXT.md §D-03 (operator iPhone Safari manual scenario shape)
</read_first>

<interfaces>
28-VERIFICATION.md current shape:
- Frontmatter (`phase: 28-v1-2-uat-closure`, `verified: 2026-05-10T13:30:00+08:00`, `status: partial`, `score: 4 FAIL of 8 scenarios verified (7 of 11 evidence rows PASS)`, `overrides_applied: 0`, `test_suite: 2030/2030 green at HEAD (379d919, 2m35s)`, `notes: |...`).
- 3 sections: Phase 17 / Phase 23 / Phase 26 Scenarios — each with the same 5-column table (Scenario | Source | Mode | Status | Evidence).

Appended PASS rows go into the SAME table for each phase. Don't move the existing FAIL rows; add NEW rows below them with `Status: PASS (Phase 29 closure — <plan_id>)` and the resolving evidence command.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Append PASS rows for code-resolved FAILs (UAT-26-1, UAT-17-1, UAT-23-1 if TIGHT)</name>
  <files>.planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md</files>
  <read_first>
    - 28-VERIFICATION.md (entire file — locate the 3 phase tables; identify exact insertion point per phase)
    - 29-02-SUMMARY.md, 29-11-SUMMARY.md, 29-13-SUMMARY.md (commit shas + branch outcome)
    - 29-CONTEXT.md §D-17
  </read_first>
  <action>
    Per D-17: APPEND new PASS rows. Do NOT rewrite or delete the existing FAIL rows.

    For each of these scenarios, append a PASS row to the appropriate phase table:

    **§Phase 26 Scenarios — Cold-start (UAT-26-1):**
    Append after the existing FAIL row:
    ```
    | Cold-start smoke | 26 / UAT-1 | MCP | PASS (Phase 29 closure — 29-02) | symptom resolved by brace-rebalance fix at dashboard_legacy/section_renderers.py:218-220 (commit <sha>); regression test tests/uat/test_uat_26_coldstart.py::test_no_pageerror_on_coldstart asserts zero pageerror on first paint; repro: pytest -m uat tests/uat/test_uat_26_coldstart.py |
    ```

    **§Phase 17 Scenarios — ATR(14) hand-recalc (UAT-17-1):**
    Append after the existing FAIL row:
    ```
    | ATR(14) hand-recalc to 1e-6 | 17 / UAT-1 | MCP | PASS (Phase 29 closure — 29-11) | engine ATR seed exposed in trace panel via signal_engine.atr_seed_for_window + sig['atr_seed'] persistence (commit <sha>); hand-recalc starts from persisted seed and converges within 1e-6; regression test tests/test_trace_atr_seed.py::test_handcalc_converges_to_displayed_atr_within_1e-6; UAT regression tests/uat/test_uat_17_atr_handcalc.py PASSES; repro: pytest -m uat tests/uat/test_uat_17_atr_handcalc.py |
    ```

    **§Phase 23 Scenarios — Live yfinance 5y backtest CLI (UAT-23-1):**
    BRANCH on plan 29-13 outcome (read 29-13-SUMMARY.md):
    - **TIGHT (inline fix landed)**: append PASS row referencing 29-13 plan + commit + the regression test added in 29-13.
    - **WIDE (escape to Phase 29.5)**: append a DEFERRED row (status: `DEFERRED to Phase 29.5`):
      ```
      | Live yfinance 5y backtest CLI | 23 / UAT-1 | CLI | DEFERRED to Phase 29.5 | spike (29-13) classified as <branch (a) WIDE | branch (b)>; full RCA at .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md; Phase 29.5 owns the fix; original FAIL evidence preserved above |
      ```

    Use the actual commit shas from each plan's commit history (look up via `git log --oneline -- <files_modified>`).

    Do NOT touch any existing FAIL row. Do NOT touch the frontmatter yet — that's Task 3 (depends on Task 2 outcome).
  </action>
  <acceptance_criteria>
    - Original FAIL rows still present: `grep -c "^| Cold-start smoke | 26 / UAT-1 | MCP | FAIL " .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` returns 1 (the original row).
    - New PASS row(s) present: `grep -c "PASS (Phase 29 closure — 29-02)" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` returns 1.
    - `grep -c "PASS (Phase 29 closure — 29-11)" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` returns 1.
    - For UAT-23-1: either `grep -c "PASS (Phase 29 closure — 29-13)" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` returns 1 (TIGHT) OR `grep -c "DEFERRED to Phase 29.5" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` returns 1 (WIDE).
    - Total table-row count increases by exactly 3 (UAT-26-1 + UAT-17-1 + UAT-23-1 — UAT-17-2 added in Task 2).
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -q "PASS (Phase 29 closure — 29-02)" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md && grep -q "PASS (Phase 29 closure — 29-11)" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md && (grep -q "PASS (Phase 29 closure — 29-13)" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md || grep -q "DEFERRED to Phase 29.5" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md) && grep -q "FAIL.*Cold-start smoke" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md && echo OK</automated>
  </verify>
  <done>3 of 4 FAIL rows updated with appended PASS or DEFERRED rows; original FAIL evidence preserved.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Operator iPhone Safari re-test for UAT-17-2</name>
  <what-built>
    Plan 29-12 server-side `<details open>` cookie path fix has shipped. Server-side rendering has been verified by `tests/test_trace_details_open_serverside.py` (integration test). The remaining check is real iOS Safari behaviour — desktop integration test is necessary but not sufficient (Phase 28 D-03 pattern; iOS Safari needs a human eye).
  </what-built>
  <how-to-verify>
    1. Open `https://signals.mwiriadi.me/markets/SPI200/dashboard` on your iPhone in Safari.
    2. Tap the "Show calculations" trace panel toggle. Confirm the panel expands.
    3. Pull-to-refresh OR navigate away and back to the same URL.
    4. Confirm the trace panel is STILL expanded after reload (the `<details>` element is rendered with the `open` attribute server-side from the cookie).
    5. If PASS: paste a one-line note like "PASS — iPhone 14 Safari 17.2, panel preserved across reload, 2026-05-10HH:MM" into the chat.
    6. If FAIL: paste symptom + iOS version + Safari version. Do NOT type "approved" until either PASS line is captured OR a FAIL is recorded for re-investigation.
  </how-to-verify>
  <resume-signal>Type "approved: <PASS-note-line>" OR "fail: <symptom>"</resume-signal>
</task>

<task type="auto">
  <name>Task 3: Append UAT-17-2 PASS row + flip frontmatter status if all 4 FAILs closed</name>
  <files>.planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md</files>
  <read_first>
    - 28-VERIFICATION.md current state (post Task 1)
    - The operator's resume-signal from Task 2 (PASS note OR fail report)
    - 29-CONTEXT.md §D-17
  </read_first>
  <action>
    1. **Append UAT-17-2 row** to §Phase 17 Scenarios:
       - If Task 2 PASS: `| iOS Safari tap-to-toggle | 17 / UAT-2 | Manual | PASS (Phase 29 closure — 29-12) | server-side <details open> rendering from tsi_trace_open cookie shipped (commit <sha>); regression test tests/test_trace_details_open_serverside.py::test_details_open_when_cookie_includes_instrument; operator manual re-test: <PASS-note-from-Task-2> |`
       - If Task 2 FAIL: `| iOS Safari tap-to-toggle | 17 / UAT-2 | Manual | FAIL (Phase 29 attempted, still open) | <FAIL-symptom-from-Task-2>; Phase 29 plan 29-12 server-side fix shipped but operator iPhone retest still fails; deferred to follow-up |`

    2. **Compute new status:**
       - Count FAILs after appends: original 4 minus those resolved with PASS rows.
       - If 0 FAILs remain (all 4 resolved): flip frontmatter `status: partial` → `status: passed`; update `score` to `8/8 scenarios verified (4 originally PASS + 4 closed by Phase 29)`.
       - If any FAIL or DEFERRED remains (e.g., UAT-23-1 escape-to-29.5 OR UAT-17-2 still failing): keep `status: partial`; update `score` to reflect current state e.g. `score: 7 PASS + 1 DEFERRED-to-29.5 of 8 scenarios`. Update `notes:` to point to Phase 29 closure + naming the deferral target.

    3. **Append `## Phase 29 Closure` section** at the bottom of the document (BEFORE the `*DEBT-01...` italics line at the very end). Format:
       ```markdown
       ## Phase 29 Closure

       Phase 29 (v1.2.1 Retroactive Patch Wrap + Validation Sweep) closed against this VERIFICATION report on 2026-05-10. Disposition of Phase 28 FAIL rows:

       - **UAT-26-1 cold-start JS:** PASS — resolved by Plan 29-02 (commit `<sha>`); regression test `tests/uat/test_uat_26_coldstart.py::test_no_pageerror_on_coldstart`.
       - **UAT-17-1 ATR(14) hand-recalc:** PASS — resolved by Plan 29-11 (commit `<sha>`); engine ATR seed exposure + persistence + 1e-6 hand-recalc convergence test.
       - **UAT-17-2 iOS Safari `<details open>`:** {PASS|FAIL} — resolved by Plan 29-12 (commit `<sha>`); server-side cookie-driven `<details open>` rendering + integration test + operator iPhone Safari re-test {PASS-note | failure-note}.
       - **UAT-23-1 live yfinance 5y backtest:** {PASS|DEFERRED to Phase 29.5} — handled by Plan 29-13 ({TIGHT inline fix at commit `<sha>` | WIDE escape; RCA at `29-13-YFINANCE-SPIKE-RCA.md`; Phase 29.5 spawned at `.planning/phases/29-5-yfinance-regression-fix/`}).

       Updated `status` to `<passed | partial>` and `score` to `<new-score>` per D-17.
       ```

       Replace `<sha>`, `{PASS|FAIL}`, etc., with actual values.

    4. Update the existing `notes:` block in frontmatter to add a one-line "Closure update 2026-05-10: see ## Phase 29 Closure section" so the YAML reads alongside the new section.
  </action>
  <acceptance_criteria>
    - `grep -c "^## Phase 29 Closure" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` returns 1.
    - `grep -c "Plan 29-02\\|29-02-UAT-26" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` ≥ 1.
    - `grep -c "Plan 29-11\\|29-11-UAT-17" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` ≥ 1.
    - `grep -c "Plan 29-12\\|29-12-UAT-17" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` ≥ 1.
    - `grep -c "Plan 29-13\\|29-13-UAT-23" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` ≥ 1.
    - `grep -E "^status: (passed|partial)" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` (the value depends on outcomes; either is acceptable per D-17 logic).
    - Original FAIL rows preserved (all 4): `grep -c "FAIL " .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` ≥ 4 (original FAIL evidence cells contain the literal "FAIL " — the appended PASS rows say "PASS" so they don't double-count).
    - If `status: passed`: `grep -q "8/8\\|all 8" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` succeeds.
    - If `status: partial`: `grep -qE "(DEFERRED|deferred|Phase 29\\.5)" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` succeeds.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -c "^## Phase 29 Closure" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md | grep -q 1 && grep -qE "Plan 29-02|29-02-UAT-26" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md && grep -qE "Plan 29-11|29-11-UAT-17" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md && grep -qE "Plan 29-12|29-12-UAT-17" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md && grep -qE "Plan 29-13|29-13-UAT-23" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md && grep -qE "^status: (passed|partial)" .planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md && echo OK</automated>
  </verify>
  <done>UAT-17-2 row appended with operator manual evidence; frontmatter status reflects current state; Phase 29 Closure section present and complete; all original FAIL evidence preserved.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| 28-VERIFICATION.md history | append-only contract — original evidence must survive |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-29-14-01 | Repudiation | Original FAIL evidence overwritten | mitigate | D-17 append-only rule + grep gate that asserts original FAIL rows survive |
| T-29-14-02 | Tampering | Frontmatter status flipped to passed while FAILs remain | mitigate | Task 3 status logic conditioned on FAIL count after appends |
</threat_model>

<verification>
- 28-VERIFICATION.md retains all original FAIL rows.
- New PASS / DEFERRED rows appended for all 4 Phase 28 FAILs.
- Phase 29 Closure section present.
- Frontmatter status correct per resolution count.
- Full default suite green: `.venv/bin/pytest -q` rc=0 (sanity — closure plan itself doesn't change code, but verifies prior plans didn't regress).
</verification>

<success_criteria>
Phase 28 FAIL rows have explicit closure (PASS or DEFERRED-to-29.5). Frontmatter reflects current sign-off state per D-17. Phase 29 closes its share of DEBT-01 hand-off without rewriting Phase 28 history.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-14-SUMMARY.md`. The SUMMARY records resolution disposition for each of the 4 Phase 28 FAILs.
</output>