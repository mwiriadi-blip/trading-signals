---
phase: 29
plan_id: 29-13-UAT-23-1-YFINANCE-SPIKE
plan: 13
type: execute
wave: 4
depends_on: []
requirements: []
files_modified:
  - .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md
  - .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md
autonomous: false
must_haves:
  truths:
    - "Time-boxed ≤1 day root-cause spike for Phase 28 FAIL UAT-23-1 (yfinance 0-trades over 5 years on live data)."
    - "Diagnostic doc captures verbose-logged backtest output and identifies (a) yfinance schema change OR (b) signal-engine RVol gate regression."
    - "Branch on classification: if (a) AND fix-shape is one schema branch → land fix here; otherwise produce RCA writeup + spawn Phase 29.5 handoff."
    - "Spike-only artefact preserved: `29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` (always) + either inline fix OR `29-13-YFINANCE-SPIKE-RCA.md` (escape hatch)."
  artifacts:
    - path: ".planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md"
      provides: "Verbose-logged backtest output, root-cause classification (a/b)"
      contains: "Root cause classification"
    - path: ".planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md (CONDITIONAL)"
      provides: "If branch is wide blast radius: RCA writeup naming files affected, blast radius, recommended Phase 29.5 shape"
      contains: "Phase 29.5"
  key_links:
    - from: "live yfinance fetch (data_fetcher.py)"
      to: "signal_engine RVol gate"
      via: "diagnostic logging exposing column shape + RVol intermediate values"
      pattern: "RVol\\|Volume\\|column"
---

<objective>
Time-boxed ≤1 day root-cause spike for Phase 28 FAIL UAT-23-1 per D-02. NOT a fix-first plan — a diagnostic-first plan with conditional inline fix OR escape-hatch handoff to Phase 29.5.

Purpose: 28-VERIFICATION.md UAT-23-1 evidence: `python -m backtest --years 5` → rc=1, gate triggered (cum_return=0.00%), SPI200=1265 bars 0 trades, AUDUSD=1300 bars 0 trades. Suspected: (a) yfinance Volume schema drift breaking RVol gate, OR (b) signal-engine RVol regression on live (vs fixture) data.

Output: ALWAYS a diagnostic doc; CONDITIONALLY either an inline fix (if shape (a) AND tight-radius) or an RCA writeup (if shape (b) OR wide-radius) + Phase 29.5 handoff.

`autonomous: false` — Task 3 has a `checkpoint:decision` gate where the executor presents the diagnostic findings and the user picks the branch.
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
- `28-VERIFICATION.md` UAT-23-1 row (full evidence + repro: `python -m backtest --years 5`)
- `backtest/data_fetcher.py` — yfinance call site, response normalisation, cache shape
- `backtest/cli.py` — entry point + arg parsing
- `backtest/simulator.py` — signal-engine + sizing-engine consumption
- `signal_engine.py` — RVol computation (`grep -n "rvol\\|RVol\\|volume" signal_engine.py`)
- `tests/test_backtest_data_fetcher.py` (deterministic fixtures — these PASS, the fail is on live data only)
- 29-CONTEXT.md §D-02, §<specifics> "Yfinance spike scope" paragraph
- Project-local LEARNING — none specific yet, but the failure-mode is similar to "Refactor that adds return values must update every caller" pattern (silently-wrong intermediate values)
</read_first>

<interfaces>
The escape-hatch contract per D-02 is:

- **Branch (a) — yfinance schema change AND fix-shape is one schema branch (e.g., a new column name or nested envelope):** Land the fix in this plan. Add a regression test in `tests/test_backtest_data_fetcher.py` that asserts both old and new schemas normalise to the same internal model. Done within Phase 29.
- **Branch (a) — yfinance schema change BUT fix-shape is wide (multiple normalisation sites, cache invalidation, retroactive backfill):** RCA writeup, hand off to Phase 29.5.
- **Branch (b) — signal-engine RVol gate regression:** RCA writeup, hand off to Phase 29.5 (touching signal_engine has wide blast radius — the 5-year backtest gate must re-pass and the signal contract must stay deterministic).

Phase 29.5 spawn = create `.planning/phases/29-5-yfinance-regression-fix/29-5-CONTEXT.md` from RCA writeup. Phase 29.5 owns the actual fix; Phase 29 retains only the diagnostic + RCA artefacts.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Run verbose-logged backtest, capture diagnostic</name>
  <files>.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md</files>
  <read_first>
    - `backtest/data_fetcher.py` — current logging level, what gets printed
    - `backtest/cli.py` — `--verbose` / log-level flags if any
    - `signal_engine.py` lines around RVol computation (find via grep)
    - 28-VERIFICATION.md UAT-23-1 evidence (the symptom: 0 trades over 5y, gate triggered)
  </read_first>
  <action>
    1. Enable verbose logging on `backtest/data_fetcher.py` AND on the signal-engine RVol gate path. Either:
       - Add `logger.setLevel(logging.DEBUG)` in a one-shot diagnostic harness script (NOT committed to source — paste the harness inline in the diagnostic doc), OR
       - Set `PYTHONLOGLEVEL=DEBUG` and run via `python -m backtest --years 5 2>&1 | tee /tmp/spike-output.log`.

    2. Capture in the diagnostic harness: for each market, the first 5 fetched OHLCV rows including all column names + dtypes. The bar count. The RVol numerator/denominator at first 10 bars. The per-bar signal vote. The gate disposition (pass/fail) per bar.

    3. Run the diagnostic against live yfinance (be courteous — one run, not a tight loop). Save the resulting log to a working scratch file.

    4. Create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` with:
       - **Frontmatter**: `phase: 29`, `plan: 13`, `kind: spike-diagnostic`, `created: 2026-05-10`, `time_box_remaining: <hours>`.
       - **§Symptom**: copy from 28-VERIFICATION.md UAT-23-1.
       - **§Repro Command**: `python -m backtest --years 5` + the verbose-logging harness used.
       - **§Yfinance Schema Snapshot**: column names + dtypes from the first row of fetched OHLCV per market. Compare against `tests/test_backtest_data_fetcher.py` fixtures.
       - **§RVol Diagnostic**: per-bar numerator/denominator/RVol value at the first 10 trade-eligible bars. Compare against fixture values.
       - **§Signal Engine Trace**: per-bar vote disposition for those same 10 bars.
       - **§Initial Hypothesis**: branch (a) yfinance schema change OR (b) signal-engine RVol regression — supported by the data above.
       - **§Time-Box Status**: hours used / 8 hours total (D-02 cap).

    Do NOT fix anything yet. Diagnostic only.
  </action>
  <acceptance_criteria>
    - `test -f .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` succeeds.
    - `grep -q "## Yfinance Schema Snapshot\\|## Schema Snapshot" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` succeeds.
    - `grep -q "## RVol Diagnostic" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` succeeds.
    - `grep -qE "## (Initial )?Hypothesis" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` succeeds.
    - Doc contains observed column names from live yfinance + observed RVol values for ≥10 bars.
    - No source code committed in this task.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && test -f .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md && grep -qE "## (Yfinance )?Schema Snapshot" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md && grep -q "## RVol Diagnostic" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md && grep -qE "## (Initial )?Hypothesis" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md && echo OK</automated>
  </verify>
  <done>Diagnostic doc captures live-vs-fixture schema delta + RVol intermediates; initial hypothesis recorded with data backing.</done>
</task>

<task type="auto">
  <name>Task 2: Classify root cause</name>
  <files>.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md</files>
  <read_first>
    - `29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` (Task 1's output)
    - `tests/test_backtest_data_fetcher.py` fixture values to compare
  </read_first>
  <action>
    Append a `## Root Cause Classification` section to the diagnostic doc. Record:

    - **Branch (a) — yfinance schema change**: TRUE/FALSE. Evidence: column names match fixtures (T) or differ (F). Specific column delta if F.
    - **Branch (b) — signal-engine RVol regression**: TRUE/FALSE. Evidence: RVol values produced by signal_engine on live data match what the gate expects (T) or fall systematically below threshold (F).

    Then determine the **fix-shape**:
    - If (a) AND single schema branch (one normalisation site touches): **TIGHT** → land fix in this plan.
    - If (a) AND multiple normalisation sites OR cache invalidation needed OR retroactive backfill: **WIDE** → escape hatch.
    - If (b): **WIDE** → escape hatch (signal engine has the strongest blast-radius constraint in the codebase per AST hex boundary).

    Append a `## Recommended Branch` section: explicit "Land in 29-13" OR "Escape to Phase 29.5" with rationale.

    Update the time-box status.
  </action>
  <acceptance_criteria>
    - `grep -q "## Root Cause Classification" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` succeeds.
    - `grep -q "## Recommended Branch" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` succeeds.
    - `grep -qE "(TIGHT|WIDE|tight|wide)" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` succeeds.
    - `grep -qE "(Land in 29-13|Escape to Phase 29\\.5)" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` succeeds.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -q "## Root Cause Classification" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md && grep -q "## Recommended Branch" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md && grep -qE "(TIGHT|WIDE)" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md && echo OK</automated>
  </verify>
  <done>Classification recorded; recommended branch explicit; time-box status current.</done>
</task>

<task type="checkpoint:decision" gate="blocking">
  <name>Task 3: Operator confirms branch decision</name>
  <decision>Land yfinance fix inline (TIGHT branch) OR escape to Phase 29.5 (WIDE branch)</decision>
  <context>
    The diagnostic + classification doc identifies which path the spike should take. Per D-02, this is an explicit operator gate — Claude does not unilaterally decide whether to grow Phase 29's scope or hand off to Phase 29.5. The operator reads the diagnostic and confirms.
  </context>
  <options>
    <option id="land-inline">
      <name>Land fix in 29-13 (TIGHT)</name>
      <pros>One commit, Phase 29 closes UAT-23-1 directly, no Phase 29.5 spawn.</pros>
      <cons>Only viable if branch (a) AND single normalisation site. Going TIGHT on a WIDE shape regresses Phase 29 budget.</cons>
    </option>
    <option id="escape-29-5">
      <name>Escape to Phase 29.5 (WIDE)</name>
      <pros>Preserves Phase 29's debt-closure focus. Phase 29.5 owns the actual fix with proper context. Diagnostic + RCA artefact preserved.</pros>
      <cons>Phase 29 closes with UAT-23-1 still open (status: deferred to 29.5 in 28-VERIFICATION.md closure note).</cons>
    </option>
  </options>
  <resume-signal>Select: land-inline OR escape-29-5</resume-signal>
</task>

<task type="auto">
  <name>Task 4: Execute branch — inline fix OR RCA writeup + Phase 29.5 handoff</name>
  <files>(BRANCH-DEPENDENT — see action)</files>
  <read_first>
    - 29-13-YFINANCE-SPIKE-DIAGNOSTIC.md (the classification + recommended branch)
    - The user's resume-signal from Task 3
  </read_first>
  <action>
    Branch on Task 3 outcome.

    **If `land-inline`:**
    - Files modified: `backtest/data_fetcher.py` (or wherever the schema branch lives) + `tests/test_backtest_data_fetcher.py` (regression test for the new schema branch).
    - Apply the fix per the diagnostic. Add a fixture for the new yfinance schema. Add a test asserting both old and new schemas normalise to the same internal model.
    - Acceptance: `python -m backtest --years 1` (or `--years 5` if test budget allows) produces non-zero trades on live data; `pytest tests/test_backtest_data_fetcher.py -q` rc=0.
    - File-size cap: ≤500 LOC each.

    **If `escape-29-5`:**
    - Files created: `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md` AND `.planning/phases/29-5-yfinance-regression-fix/29-5-CONTEXT.md`.
    - `29-13-YFINANCE-SPIKE-RCA.md` content:
      - Frontmatter: `phase: 29`, `plan: 13`, `kind: spike-rca`, `created: 2026-05-10`.
      - §Root Cause (the verified branch from Task 2).
      - §Files Affected (each file path with the role it plays).
      - §Blast Radius (which phases of v1.2 it would touch; whether AST hex boundary is involved; whether deterministic-fixture tests would need regeneration).
      - §Recommended Phase 29.5 Shape (1-3 plans; depends_on ordering; expected file_modified surface).
      - §Time-Box Final (hours used).
    - `29-5-CONTEXT.md` content (this is the explicit handoff per D-02):
      - Frontmatter for Phase 29.5 phase context (mirror Phase 29's CONTEXT.md frontmatter shape).
      - Reference to `29-13-YFINANCE-SPIKE-RCA.md` as canonical input.
      - Phase 29.5 boundary: ONLY the yfinance regression fix; no Phase 29 debt-closure work.
      - Phase 29 leaves Phase 29.5 with the spike artefact only — no fix attempts.
      - Acceptance: ≤2 plans, fix-and-test, locked by `python -m backtest --years 5` rc=0.
    - Update 28-VERIFICATION.md note in Plan 29-14 to reflect "UAT-23-1 deferred to Phase 29.5".

    File-size cap: each new doc ≤500 LOC. Realistic ~150 LOC for RCA, ~80 LOC for 29-5-CONTEXT.md.

    Do NOT design Phase 29.5's plans — D-02 forbids; just hand off the writeup.
  </action>
  <acceptance_criteria>
    - **If land-inline:** `python -m backtest --years 1 2>&1 | grep -E "trades|rc=0"` shows non-zero trades; `pytest tests/test_backtest_data_fetcher.py -q` rc=0; full default suite green.
    - **If escape-29-5:** `test -f .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md` succeeds; `test -f .planning/phases/29-5-yfinance-regression-fix/29-5-CONTEXT.md` succeeds; `grep -q "Phase 29.5" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md` succeeds; `grep -q "phase: 29.5\\|Phase 29.5" .planning/phases/29-5-yfinance-regression-fix/29-5-CONTEXT.md` succeeds.
    - In either branch, `29-13-YFINANCE-SPIKE-DIAGNOSTIC.md` exists and is unchanged from end of Task 2.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && (test -f .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md && grep -q "Phase 29.5" .planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md && test -f .planning/phases/29-5-yfinance-regression-fix/29-5-CONTEXT.md && echo "BRANCH=escape-29-5 OK") || (.venv/bin/pytest tests/test_backtest_data_fetcher.py -q && echo "BRANCH=land-inline OK")</automated>
  </verify>
  <done>Either: (a) inline fix lands + test green; OR (b) RCA + Phase 29.5 CONTEXT.md handoff in place with diagnostic preserved.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| live yfinance API ↔ data_fetcher | external schema can drift; cached fixtures are not enough |
| signal_engine RVol gate ↔ live OHLCV | regression on live data not caught by deterministic fixtures |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-29-13-01 | DoS / silent failure | Live yfinance schema change → 0 trades over 5y silently | mitigate (TIGHT) or defer-to-29.5 (WIDE) | Diagnostic identifies schema delta; fix lands schema-branch test if TIGHT |
| T-29-13-02 | Tampering (drift) | Signal-engine RVol regression on live (vs fixture) data | mitigate (deferred) | RCA + Phase 29.5 plans the fix with full hex-boundary care |
| T-29-13-03 | Time-box overrun | Spike grows beyond 1 day | mitigate | D-02 explicit cap; checkpoint:decision gate forces operator awareness |
</threat_model>

<verification>
- Diagnostic doc exists with classification.
- Either inline fix is green OR Phase 29.5 handoff is complete.
- Time-box ≤1 day honoured.
</verification>

<success_criteria>
Phase 28 FAIL UAT-23-1 either resolved inline (Plan 29-14 appends PASS row) or explicitly deferred to Phase 29.5 with full RCA + handoff artefact (Plan 29-14 records the deferral).
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-SUMMARY.md`. The SUMMARY records the branch taken (TIGHT or WIDE-deferred) and the artefacts produced.
</output>