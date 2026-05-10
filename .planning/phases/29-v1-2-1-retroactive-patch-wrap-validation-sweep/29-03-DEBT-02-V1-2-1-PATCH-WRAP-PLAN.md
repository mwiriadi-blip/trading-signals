---
phase: 29
plan_id: 29-03-DEBT-02-V1-2-1-PATCH-WRAP
plan: 03
type: execute
wave: 1
depends_on: []
requirements: [DEBT-02]
files_modified:
  - .planning/MILESTONES.md
  - tests/test_scheduler.py
  - tests/test_signals_status_ladder.py
  - tests/test_trace_vote_params.py
autonomous: true
must_haves:
  truths:
    - "`.planning/MILESTONES.md` v1.2 entry has a `### v1.2.1 — Retroactive Patch Wrap (2026-05-10)` sub-section with a 5-row table `| Commit | Behaviour | Test | Note |` per D-13."
    - "Scheduler tz fix (`05a4c0c`) is locked by a regression test asserting daily run fires at 08:00 Sydney AEST/AEDT including a DST transition case."
    - "Signal status ladder trigger (`da31412`) is locked by a regression test asserting trigger ladder + trailing-stop line render on the Signal Status card."
    - "Trace vote_params backfill (`587b6f0` + `bb780af`) is locked by a regression test asserting the trace renders engine-resolved params and falls back at render time for stale state rows."
    - "Market tab strip refresh (`878199c`) is documented as UX-only with `Test: none — UX` annotation in the table."
    - "v1.1 backtested per-market defaults (`b7ed1f2`) is documented with a pointer to existing `tests/test_backtest_*` fixture coverage; no new test."
  artifacts:
    - path: ".planning/MILESTONES.md"
      provides: "v1.2.1 sub-entry under v1.2 with 5-row commit table"
      contains: "v1.2.1 — Retroactive Patch Wrap"
    - path: "tests/test_scheduler.py"
      provides: "Tz-fix regression test (08:00 Sydney AEST/AEDT)"
      contains: "test_daily_run_fires_at_0800_sydney"
    - path: "tests/test_signals_status_ladder.py"
      provides: "Status-card ladder + trailing-stop line regression test"
      exports: []
    - path: "tests/test_trace_vote_params.py"
      provides: "Trace vote_params engine-resolved + stale-state fallback regression"
      exports: []
  key_links:
    - from: ".planning/MILESTONES.md v1.2.1 row"
      to: "regression test pointers"
      via: "Test column names test file"
      pattern: "tests/test_"
---

<objective>
Close DEBT-02 per D-11/D-12/D-13: formalise the 5 ad-hoc post-v1.2 polish commits as a single v1.2.1 sub-section in `.planning/MILESTONES.md` with targeted regression tests where behaviour needs locking. NO per-commit retroactive PLAN.md files (D-11 forbids).

Purpose: ROADMAP SC-1 — `MILESTONES.md` has v1.2.1 patch-phase entry naming each of the 5 commits with one-line behaviour note + regression-test pointer. Without locking tests, these polish fixes can silently regress in v1.3.
Output: 1 MILESTONES.md edit + 3 new test files (scheduler tz, status ladder, trace vote_params).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/MILESTONES.md
@.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-CONTEXT.md
@.claude/LEARNINGS.md

<read_first>
- `.planning/MILESTONES.md` (the v1.2 entry section to extend — read existing tag/scope/highlights/known-deferred shape)
- 29-CONTEXT.md §D-11, D-12, D-13 + §<specifics> (table shape `| Commit | Behaviour | Test | Note |`)
- Read each commit message via `git show --no-patch <sha>` for: 05a4c0c, da31412, b7ed1f2, 587b6f0, bb780af, 878199c
- Project-local LEARNINGS 2026-05-10 trace-panel-drift entry (the locality-discipline that drove the trace vote_params commits)
- Existing patterns in `tests/test_scheduler.py` if file exists; otherwise `tests/test_main.py` scheduler-related tests
- Existing trace-render tests under `tests/test_trace_*.py` or `tests/test_dashboard*.py` (find patterns for `vote_params`)
</read_first>

<interfaces>
The 5 commits + their test policy per D-12:

| Commit | Subject | Test policy |
|--------|---------|-------------|
| `05a4c0c` | feat(sched): fire daily run at 08:00 Sydney (AEST/AEDT, DST-aware) | NEW regression test |
| `da31412` | feat(signals): trigger ladder + trailing-stop line on Signal Status card | NEW regression test |
| `b7ed1f2` | feat(v11): backtested per-market defaults, $10K baseline, contract type + financing UI | EXISTING `tests/test_backtest_*` covers — pointer only |
| `587b6f0` | fix(trace): render engine-resolved vote params instead of re-derived defaults | NEW regression test |
| `bb780af` | fix(trace): backfill vote_params at render time for stale state rows | LOCK BY SAME test as 587b6f0 (pair) |
| `878199c` | fix(ui): refresh market tab strip on tab click so active underline tracks selection | UX-only — `Test: none — UX` |

Three new test files cover four commits (587b6f0 + bb780af share). One test file already covers b7ed1f2 by pointer. One commit (878199c) is documented as UX-only.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Append v1.2.1 sub-section to MILESTONES.md</name>
  <files>.planning/MILESTONES.md</files>
  <read_first>
    - .planning/MILESTONES.md (entire file; identify exact insertion point — under the v1.2 entry, AFTER its "Known Deferred Items" sub-section but BEFORE the v1.2-MILESTONE-AUDIT pointer line)
    - 29-CONTEXT.md §D-11, D-13 + §<specifics> (table shape, 5 rows)
    - Each commit's full message via `git show --no-patch 05a4c0c da31412 b7ed1f2 587b6f0 bb780af 878199c`
  </read_first>
  <action>
    Per D-13: insert a new sub-section under the v1.2 entry (single source of truth — do NOT duplicate to `milestones/v1.2-ROADMAP.md`).

    The sub-section structure:
    ```markdown
    ### v1.2.1 — Retroactive Patch Wrap (2026-05-10)

    Five ad-hoc post-ship polish commits (2026-05-08..05-10) formalised as a single retroactive patch phase per Phase 29 D-11/D-13. Behaviour-locking regression tests added in Phase 29 plan 29-03 where the commit changed observable behaviour; UX-only and existing-fixture-covered commits get pointer rows.

    | Commit | Behaviour | Test | Note |
    |--------|-----------|------|------|
    | `05a4c0c` | Daily run fires at 08:00 Sydney (AEST/AEDT, DST-aware) | `tests/test_scheduler.py::test_daily_run_fires_at_0800_sydney` | DST transition case included |
    | `da31412` | Signal Status card renders trigger ladder + trailing-stop line | `tests/test_signals_status_ladder.py` | New regression suite |
    | `b7ed1f2` | v11 backtested per-market defaults, $10K baseline, contract+financing UI | `tests/test_backtest_*` (existing fixture suite) | Pointer only — covered by deterministic backtest fixtures |
    | `587b6f0` + `bb780af` | Trace panel renders engine-resolved vote params; backfill at render time for stale state rows | `tests/test_trace_vote_params.py` | Locality discipline per project LEARNING 2026-05-10 |
    | `878199c` | Market tab strip refresh on tab click (active underline tracks selection) | none — UX | Visual-only fix, no behaviour contract |
    ```

    Insertion point inside the v1.2 entry: after the existing "Known Deferred Items (carried into v1.3 as Phase 28 backlog)" sub-section and BEFORE the `See ['milestones/v1.2-MILESTONE-AUDIT.md']...` audit-pointer paragraph. If the layout is different from what 29-CONTEXT.md describes, follow the actual file structure — keep the sub-section heading at `###` level (one level deeper than the v1.2 `## v1.2 ...` heading).

    Refine the "Behaviour" cell wording to the real commit subject lines if they diverge from the table above (use `git show --no-patch <sha>`).

    Do NOT edit any other section of MILESTONES.md. Do NOT touch `milestones/v1.2-ROADMAP.md` (D-13 forbids duplication).
  </action>
  <acceptance_criteria>
    - `grep -q "### v1.2.1 — Retroactive Patch Wrap" .planning/MILESTONES.md` succeeds.
    - `grep -q "05a4c0c" .planning/MILESTONES.md` succeeds.
    - `grep -q "da31412" .planning/MILESTONES.md` succeeds.
    - `grep -q "b7ed1f2" .planning/MILESTONES.md` succeeds.
    - `grep -q "587b6f0" .planning/MILESTONES.md` succeeds.
    - `grep -q "bb780af" .planning/MILESTONES.md` succeeds.
    - `grep -q "878199c" .planning/MILESTONES.md` succeeds.
    - `grep -c "^| \`" .planning/MILESTONES.md` increases by exactly 5 vs the pre-edit count (5 commit rows added).
    - `grep -q "v1.2.1" .planning/milestones/v1.2-ROADMAP.md` returns NO match (D-13 — no duplication).
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -q "### v1.2.1 — Retroactive Patch Wrap" .planning/MILESTONES.md && grep -q "05a4c0c" .planning/MILESTONES.md && grep -q "da31412" .planning/MILESTONES.md && grep -q "b7ed1f2" .planning/MILESTONES.md && grep -q "587b6f0" .planning/MILESTONES.md && grep -q "bb780af" .planning/MILESTONES.md && grep -q "878199c" .planning/MILESTONES.md && ! grep -q "v1.2.1" .planning/milestones/v1.2-ROADMAP.md && echo OK</automated>
  </verify>
  <done>v1.2.1 sub-section present in MILESTONES.md with all 5 commit shas, 5-row table, behaviour notes, and test pointers. ROADMAP.md not duplicated.</done>
</task>

<task type="auto">
  <name>Task 2: Regression test for scheduler tz fix (05a4c0c)</name>
  <files>tests/test_scheduler.py</files>
  <read_first>
    - `git show --stat 05a4c0c` and `git show 05a4c0c` (locate the changed file + the function/method that resolves the next 08:00 Sydney run)
    - Existing `tests/test_scheduler.py` if it exists; if not, follow patterns in `tests/test_main.py` for scheduler tests
    - 29-CONTEXT.md §D-12 (this is in the "tested" group — must be behaviour-locking)
  </read_first>
  <action>
    Add (or extend) `tests/test_scheduler.py` with a `TestSchedulerTimezone` class containing at minimum:

    1. `test_daily_run_fires_at_0800_sydney_aest` — pin a winter date (e.g., 2026-06-15 — AEST = UTC+10), call the scheduler's "next run" resolver, assert the result is 08:00 Sydney = 22:00 UTC the previous day OR the same-day equivalent depending on the implementation's contract.
    2. `test_daily_run_fires_at_0800_sydney_aedt` — pin a summer date (e.g., 2026-12-15 — AEDT = UTC+11), assert next run is 08:00 Sydney = 21:00 UTC.
    3. `test_dst_transition_handled` — pin a date straddling the AEST↔AEDT transition (e.g., first Sunday in October for AEDT start, first Sunday in April for AEST start; use the relevant project tz library — `zoneinfo.ZoneInfo('Australia/Sydney')` is the stdlib choice). Assert the next run resolves to the correct local 08:00 across the transition.

    Use `freezegun` / `freeze_time` if the project already does (per global LEARNING — calendar-sensitive tests must use freeze_time for weekday gates; same discipline applies for tz-sensitive tests). If the project's scheduler reads `datetime.now(tz=...)`, a frozen clock + `zoneinfo` is sufficient.

    The test does NOT need to start a real `apscheduler` thread; it asserts the resolution function's output. If the commit's actual API differs, follow the API.

    File-size cap: ≤500 LOC.
  </action>
  <acceptance_criteria>
    - `test -f tests/test_scheduler.py` succeeds (file exists, may be new or extended).
    - `grep -q "test_daily_run_fires_at_0800_sydney" tests/test_scheduler.py` succeeds.
    - `grep -q "AEST\\|AEDT\\|Australia/Sydney" tests/test_scheduler.py` succeeds.
    - `grep -q "DST\\|dst_transition\\|aedt\\|aest" tests/test_scheduler.py` succeeds (DST coverage).
    - `pytest tests/test_scheduler.py -x -q` rc=0.
    - `wc -l tests/test_scheduler.py` ≤500.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && .venv/bin/pytest tests/test_scheduler.py -x -q -k "0800_sydney or dst"</automated>
  </verify>
  <done>Scheduler tz fix locked by AEST + AEDT + DST-transition tests. Future regression that breaks 08:00 Sydney behaviour fails CI.</done>
</task>

<task type="auto">
  <name>Task 3: Regression tests for status ladder + trace vote_params</name>
  <files>tests/test_signals_status_ladder.py, tests/test_trace_vote_params.py</files>
  <read_first>
    - `git show --stat da31412` + `git show da31412` (the file/function that renders the Signal Status card; identify the trigger-ladder + trailing-stop-line render path)
    - `git show --stat 587b6f0 bb780af` (the trace render path — `dashboard_legacy/trace_panels.py` `_render_trace_panels`, signal_engine `resolve_vote_params`, `daily_run.py` `vote_params` persistence, render-time fallback)
    - `dashboard_legacy/trace_panels.py:184-217` (the `_render_trace_panels` function)
    - `signal_engine.resolve_vote_params` definition (read with `grep -n "def resolve_vote_params" signal_engine.py`)
    - Project-local LEARNINGS 2026-05-10 trace-panel-drift entry (the failure mode the test must lock out)
    - Existing trace-related tests via `grep -rn "trace_vote\\|render_trace" tests/`
    - 29-CONTEXT.md §D-12 (both are in "tested" group; 587b6f0 + bb780af share one suite)
  </read_first>
  <action>
    **Sub-task A: `tests/test_signals_status_ladder.py`**

    Create new test file with `TestSignalStatusLadder` class:
    1. `test_status_card_includes_trigger_ladder` — render the Signal Status card with a fixture signal whose `signal == 1` (LONG); assert the rendered HTML contains the trigger-ladder block (a sequence of pyramid threshold lines per the implementation in commit `da31412`).
    2. `test_status_card_includes_trailing_stop_line` — same fixture; assert the rendered HTML contains a trailing-stop line annotated with the current trailing-stop level.
    3. `test_status_card_no_ladder_for_flat_signal` — fixture with `signal == 0`; assert ladder + trailing-stop line are NOT rendered (status card stays minimal).

    Use whatever fixture loader / render helper the existing dashboard tests use (`tests/test_dashboard*.py` patterns). Touch the public render function the commit modifies — read commit diff to identify it.

    **Sub-task B: `tests/test_trace_vote_params.py`**

    Create new test file with `TestTraceVoteParams` class:
    1. `test_trace_renders_engine_resolved_vote_params` — build a signal dict with `vote_params={'adx_gate': 20.0, 'momentum_threshold': 0.02, ...}` and `indicator_scalars` containing an ADX value of 18.66; render via `_render_trace_panels`; assert the gate badge text matches what the engine would say with `adx_gate=20.0` (NOT a hardcoded 25.0 from defaults). The exact assertion: parse the rendered HTML for the gate-line, assert the comparison threshold shown matches the persisted `vote_params['adx_gate']`.
    2. `test_trace_falls_back_at_render_time_for_stale_signal_row` — build a signal dict WITHOUT `vote_params` (legacy state.json shape); render; assert the trace renders without crashing AND uses the render-time-resolved fallback per `bb780af`. Confirm the fallback yields the same value as `signal_engine.resolve_vote_params({})` would for the empty-settings case.
    3. `test_trace_prelim_vote_uses_resolved_momentum_threshold` — fixture with `Mom1=0.0074` and `vote_params['momentum_threshold']=0.02`; assert the prelim Vote line in the rendered trace counts Mom1 as `not voting` (since `0.0074 < 0.02`), NOT as a positive vote (which is the bug locked out by `587b6f0`).

    Reference the project-local LEARNING 2026-05-10 verbatim in a docstring on the test class (one-line note that this suite locks the locality-discipline failure mode).

    Both files ≤500 LOC each.
  </action>
  <acceptance_criteria>
    - `test -f tests/test_signals_status_ladder.py` succeeds.
    - `test -f tests/test_trace_vote_params.py` succeeds.
    - `grep -q "test_status_card_includes_trigger_ladder" tests/test_signals_status_ladder.py` succeeds.
    - `grep -q "test_status_card_includes_trailing_stop_line" tests/test_signals_status_ladder.py` succeeds.
    - `grep -q "test_trace_renders_engine_resolved_vote_params" tests/test_trace_vote_params.py` succeeds.
    - `grep -q "test_trace_falls_back_at_render_time_for_stale_signal_row" tests/test_trace_vote_params.py` succeeds.
    - `grep -q "test_trace_prelim_vote_uses_resolved_momentum_threshold" tests/test_trace_vote_params.py` succeeds.
    - `pytest tests/test_signals_status_ladder.py tests/test_trace_vote_params.py -x -q` rc=0.
    - `wc -l tests/test_signals_status_ladder.py tests/test_trace_vote_params.py` both ≤500.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && .venv/bin/pytest tests/test_signals_status_ladder.py tests/test_trace_vote_params.py -x -q</automated>
  </verify>
  <done>3 commits (da31412, 587b6f0, bb780af) locked by behaviour-binding regression tests. Trace locality-discipline (per project LEARNING) cannot regress silently.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MILESTONES.md ↔ git history | docs must stay synchronised with retroactive patch shape |
| persisted state row ↔ trace renderer | trace must read engine-recorded vote_params, never re-derive |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-29-03-01 | Tampering (drift) | Future commit reverts trace to re-derive vote_params from defaults | mitigate | `test_trace_renders_engine_resolved_vote_params` + locality discipline LEARNING reference |
| T-29-03-02 | Tampering (drift) | Future commit silently changes daily-run firing time off 08:00 Sydney | mitigate | `test_daily_run_fires_at_0800_sydney_aest/aedt/dst_transition` |
| T-29-03-03 | Information Disclosure | MILESTONES.md duplication leaks divergent v1.2.1 spec | mitigate | D-13 single-source rule; grep gate confirms `milestones/v1.2-ROADMAP.md` does NOT mention v1.2.1 |
</threat_model>

<verification>
- Full default suite green: `.venv/bin/pytest -q` rc=0.
- Targeted: `pytest tests/test_scheduler.py tests/test_signals_status_ladder.py tests/test_trace_vote_params.py -q` rc=0.
- `grep -q "v1.2.1" .planning/MILESTONES.md && ! grep -q "v1.2.1" .planning/milestones/v1.2-ROADMAP.md`.
</verification>

<success_criteria>
ROADMAP SC-1 satisfied: `MILESTONES.md` v1.2.1 entry names each of the 5 commits with one-line behaviour note + regression-test pointer (or "UX-only" annotation). 4 of 5 commits behaviour-locked by tests; 1 (UX) explicitly UX-only; 1 (b7ed1f2) covered by existing fixture suite.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-03-SUMMARY.md`.
</output>