---
phase: 27
plan: 10
type: execute
wave: 2A
parallel: true
depends_on: [27-01, 27-02, 27-03, 27-04, 27-05, 27-06, 27-07]  # <!-- revision-fix: blocker-2 — Wave 2A must follow Wave 1; encode full Wave 1 list. system_params.py / notifier.py / state_manager.py / main.py are touched by Wave 1 plans. -->
files_modified:
  - system_params.py  # <!-- review-fix: agreed-4 — change MAX_WARNINGS value (no new constant) -->
  - notifier.py
  - main.py
  - state_manager.py  # <!-- review-fix: agreed-4 — append_warning enforces same MAX_WARNINGS -->
  - tests/test_warnings_fifo.py
  - tests/test_run_date_logging.py
  - tests/test_lookahead_bias.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Single warnings-FIFO bound constant: MAX_WARNINGS in system_params.py (existing — value changed from 100 → 50)."
    - "WARNINGS_FIFO_MAX_LEN is NOT introduced (would duplicate existing MAX_WARNINGS — review-fix agreed-4)."
    - "Both notifier._dispatch_email_and_maintain_warnings AND state_manager.append_warning use the SAME MAX_WARNINGS constant."
    - "AST/grep regression test fails if both MAX_WARNINGS and WARNINGS_FIFO_MAX_LEN exist simultaneously."
    - "Daily run logs run-date YYYY-MM-DD AWST at INFO level once per execution."
    - "Backtest test PROVES Day-N's signal does NOT depend on Day-N's CLOSE. If the test surfaces a real look-ahead bug, the test FAILS THE SUITE — no xfail. Look-ahead is escalated as a [BLOCKING] task."
  artifacts:
    - path: tests/test_warnings_fifo.py
      provides: "FIFO max-length + overflow eviction-order regression"
      contains: "MAX_WARNINGS"
    - path: tests/test_run_date_logging.py
      provides: "run-date INFO log assertion via caplog"
      contains: "caplog"
    - path: tests/test_lookahead_bias.py
      provides: "look-ahead bias proof on backtest — FAILS suite if bug present"
      contains: "lookahead"
  key_links:
    - from: "notifier._dispatch_email_and_maintain_warnings"
      to: "system_params.MAX_WARNINGS"
      via: "len-bound enforcement"
      pattern: "MAX_WARNINGS"
    - from: "state_manager.append_warning"
      to: "system_params.MAX_WARNINGS"
      via: "len-bound enforcement"
      pattern: "MAX_WARNINGS"
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `2` → `2A`; depends_on remains empty.
- [x] agreed-4 (constant collision MAX_WARNINGS vs WARNINGS_FIFO_MAX_LEN) — chose option: KEEP existing `MAX_WARNINGS` and CHANGE its value 100 → 50. WARNINGS_FIFO_MAX_LEN is NOT introduced. Rationale: avoids constant proliferation; respects existing code organization (state_manager.append_warning at line 803 already uses MAX_WARNINGS); single source of truth. Value change to 50 is the operative new behavior.
- [x] agreed-4 (regression test for collision) — added AST/grep test asserting `WARNINGS_FIFO_MAX_LEN` does NOT exist anywhere in the codebase. Fails if both are present.
- [x] agreed-4 (Codex HIGH lookahead xfail) — escalation language added: if look-ahead-bias proof fails, the test FAILS the suite (no `xfail`). The lookahead test becomes a [BLOCKING] task. Real trading bug must NOT be silently marked expected-fail.
- [x] M1 (brittle implementation tests) — FIFO canonical-ordering test rewritten to assert the OBSERVABLE invariant ("after N>50 warnings, exactly the latest 50 remain in FIFO order") rather than the call-sequence trace.
- [x] M2 (doc rule) — SUMMARY artifact stays inside `.planning/phases/27-.../`.
- [x] revision blocker-2 — depends_on populated with full Wave 1 list ([27-01..27-07]) for correct Wave 2A sequencing (Wave 1 touches system_params.py / notifier.py / state_manager.py / main.py).

<objective>
Three test additions bundled (review items #16 + run-date logging + look-ahead-bias). All three are pure test-additions or guard-clauses.

1. **Warnings-FIFO bound (item #16) — review-fix agreed-4:** change existing `MAX_WARNINGS` value 100 → 50 in system_params.py. Both notifier._dispatch_email_and_maintain_warnings AND state_manager.append_warning enforce this bound. Do NOT introduce a duplicate `WARNINGS_FIFO_MAX_LEN`.
2. **Run-date logging assertion:** integration test that the daily run logs run-date YYYY-MM-DD AWST at INFO level (verified via caplog).
3. **Look-ahead-bias backtest test — review-fix agreed-4:** assert Day-N's signal does NOT depend on Day-N's CLOSE. If the test fails because a real look-ahead bug surfaces, the test FAILS THE SUITE (no `xfail`). The find is escalated to a [BLOCKING] follow-up task.

Bundled because all three are <100 LOC test additions.

Purpose: lock in invariants that already (mostly) hold; FAIL LOUD on any regression OR real bug.
Output: 3 new test files + MAX_WARNINGS value-change + collision regression test.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@system_params.py
@notifier.py
@main.py
@state_manager.py
@backtest/

<interfaces>
# Existing constant (review-fix agreed-4 — KEEP, change value):
#   system_params.py:120 — MAX_WARNINGS: int = 100   →   change to 50
#   state_manager.py:803 — append_warning(state, w):
#                            state['warnings'].append(w)
#                            while len(state['warnings']) > MAX_WARNINGS:
#                              state['warnings'].pop(0)
#
# notifier._dispatch_email_and_maintain_warnings — already-existing FIFO maintenance:
#   Add (or verify): the maintenance step uses the SAME MAX_WARNINGS constant from system_params.
#   Single import at top: `from system_params import MAX_WARNINGS`.
#
# Run-date log: main.run_daily_check writes log lines. If existing INFO line names run-date, lock in.
#   Else add: `logger.info(f'[Daily] run-date {run_date_aws}')` near function entry.
#
# Look-ahead-bias proof — FAIL LOUD policy (agreed-4):
#   Construct fake df with Day-N OHLC. Compute signal for Day-N. Mutate Day-N's CLOSE to a
#   shock value. Compute again. Assert: same signal output regardless of today's close.
#   IF assertion fails: real bug. Test FAILS THE SUITE (no xfail). Escalates to a follow-up
#   [BLOCKING] task. Do NOT marshal as expected-fail.
#   Read signal_engine.get_signal source FIRST to determine actual contract; lock in WHAT IT DOES.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: MAX_WARNINGS value change (100 → 50) + collision regression + FIFO bound</name>
  <!-- review-fix: agreed-4 -->
  <read_first>
    - system_params.py line 120
    - state_manager.py line 803 (append_warning)
    - notifier.py — search for `state['warnings']` and `_dispatch_email_and_maintain_warnings`
  </read_first>
  <behavior>
    - test_max_warnings_value_is_50: system_params.MAX_WARNINGS == 50.  <!-- review-fix: agreed-4 (value change) -->
    - test_no_duplicate_fifo_constant: AST/grep — `WARNINGS_FIFO_MAX_LEN` does NOT appear anywhere in the codebase (system_params.py, notifier.py, state_manager.py, tests/).  <!-- review-fix: agreed-4 -->
    - test_warnings_fifo_does_not_exceed_max: build state with 60 warnings; call append_warning OR _dispatch_email_and_maintain_warnings; assert len(state['warnings']) <= 50.
    - test_warnings_fifo_eviction_order: append 60 numbered warnings (0..59); FIFO evicts 0..9, keeps 10..59. Assert state['warnings'] == [w_10, ..., w_59].
    - test_dispatch_uses_max_warnings_constant: grep notifier.py — _dispatch_email_and_maintain_warnings imports/uses MAX_WARNINGS (not a hardcoded 100 or new WARNINGS_FIFO_MAX_LEN).
  </behavior>
  <action>
1. **system_params.py:** change line 120 from `MAX_WARNINGS: int = 100` to `MAX_WARNINGS: int = 50`. Add inline comment: `# Phase 27 #16 (review-fix agreed-4): tightened from 100 to 50 — FIFO bound`.

2. **state_manager.py:803 (append_warning):** verify it uses `MAX_WARNINGS` from system_params. If currently hardcoded — change to import. The behavior `while len(state['warnings']) > MAX_WARNINGS: state['warnings'].pop(0)` should already be present.

3. **notifier.py — _dispatch_email_and_maintain_warnings:**
   - At top: ensure `from system_params import MAX_WARNINGS` (add to existing import block).
   - In the maintenance step, ensure FIFO bound enforcement uses MAX_WARNINGS:
     ```python
     while len(state['warnings']) > MAX_WARNINGS:
       state['warnings'].pop(0)
     ```
   - Verify no hardcoded 100 or 50 literal remains.

4. **tests/test_warnings_fifo.py (NEW):** 5 tests per behavior block. Collision-detection test:
   ```python
   def test_no_duplicate_fifo_constant():
     '''review-fix agreed-4: WARNINGS_FIFO_MAX_LEN must not exist anywhere — single source of truth is MAX_WARNINGS.'''
     import pathlib, ast
     prod_dirs = [pathlib.Path('.'), pathlib.Path('tests')]
     for root in prod_dirs:
       for f in root.rglob('*.py'):
         text = f.read_text()
         assert 'WARNINGS_FIFO_MAX_LEN' not in text, f'{f}: WARNINGS_FIFO_MAX_LEN duplicates MAX_WARNINGS'
   ```
  </action>
  <verify>
    <automated>pytest tests/test_warnings_fifo.py -x -v</automated>
  </verify>
  <done>
    - MAX_WARNINGS = 50 in system_params.py.
    - WARNINGS_FIFO_MAX_LEN does NOT exist (AST/grep test green).
    - Both append_warning + _dispatch_email_and_maintain_warnings enforce MAX_WARNINGS.
    - 5 tests green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Run-date logging assertion</name>
  <read_first>
    - main.py — run_daily_check function body
  </read_first>
  <behavior>
    - test_daily_run_logs_run_date: invoke run_daily_check on stub state; capture caplog at INFO; assert at least one record matches r'\[Daily\] run-date \d{4}-\d{2}-\d{2}'.
  </behavior>
  <action>
1. Inspect run_daily_check for existing run-date log line. If present + INFO-level, the test locks it in. Else add `logger.info(f'[Daily] run-date {run_date_aws}')`.

2. **tests/test_run_date_logging.py (NEW):** 1 test per behavior block.
  </action>
  <verify>
    <automated>pytest tests/test_run_date_logging.py -x -v</automated>
  </verify>
  <done>
    - 1 test green.
    - INFO log line present + asserted.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Look-ahead-bias backtest test — FAIL LOUD (no xfail)</name>
  <!-- review-fix: agreed-4 — Codex HIGH escalation policy -->
  <read_first>
    - backtest/simulator.py
    - signal_engine.get_signal (read source FIRST to determine actual contract)
    - tests/test_backtest_simulator.py (existing patterns)
  </read_first>
  <behavior>
    - test_signal_independent_of_today_close: construct 30-bar OHLC ending Day-N. Run signal_engine.get_signal. Mutate Day-N's CLOSE to shock value (1.5×, 0.5×). Run again. Assert two signals are identical — Day-N close did not influence the vote.
    - test_signal_independent_of_today_high_low_open: shock OPEN, HIGH, LOW (one at a time). Confirm get_signal uses ONLY prior bars.
    - **POLICY (review-fix agreed-4):** if these assertions fail, it means a real look-ahead bug exists. The test FAILS the suite — NO xfail, NO skip, NO "documented as known issue". Phase 27 must fix it (escalate to a follow-up [BLOCKING] task within this phase) before the phase closes.
  </behavior>
  <action>
1. Read `signal_engine.get_signal` source FIRST. Determine actual contract: which row's data feeds the signal decision? `df.iloc[-1]` (today) → look-ahead by definition; `df.iloc[-2]` (yesterday) → no look-ahead.

2. Write test to lock in the EXPECTED contract (no look-ahead):
   ```python
   def test_signal_independent_of_today_close(canonical_30bar_df):
     baseline = signal_engine.get_signal(canonical_30bar_df)
     # Mutate today's close
     shocked = canonical_30bar_df.copy()
     shocked.iloc[-1, shocked.columns.get_loc('Close')] *= 1.5
     shocked_sig = signal_engine.get_signal(shocked)
     assert baseline == shocked_sig, 'LOOK-AHEAD BIAS: today close influenced signal'
   ```

3. **review-fix agreed-4 — FAIL LOUD policy:**
   - If test passes → invariant proven, suite green.
   - If test fails → real look-ahead bug. The test FAILS the suite. Phase 27 must add a follow-up [BLOCKING] task to fix the bug (revise plan in-flight: append a 27-15 plan). DO NOT mark xfail.
   - In task action header, add explicit "if assertion fails, FIX IT — do not xfail" note for the executor.

4. **tests/test_lookahead_bias.py (NEW):** 2 tests per behavior block.

5. Run: `pytest tests/test_lookahead_bias.py -x -v`. If either fails, IMMEDIATELY escalate to revise-plan with a 27-15 fix plan; do not commit a passing-via-xfail workaround.
  </action>
  <verify>
    <automated>pytest tests/test_lookahead_bias.py -x -v</automated>
  </verify>
  <done>
    - Look-ahead-bias test green (invariant proven), OR
    - If failed: real bug found → escalate to follow-up [BLOCKING] task; do NOT mark xfail.
  </done>
</task>

</tasks>

<threat_model>
| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-10-01 | DoS (self) | Unbounded warnings list grows → state.json bloats | mitigate | MAX_WARNINGS = 50 enforced at append_warning + _dispatch_email_and_maintain_warnings. |
| T-27-10-02 | Data integrity (trading) | Look-ahead bias → backtests give optimistic results that don't replicate live | mitigate | Look-ahead-bias test FAILS LOUD on real bug; phase blocks until fixed. |
</threat_model>

<verification>
```
pytest tests/test_warnings_fifo.py tests/test_run_date_logging.py tests/test_lookahead_bias.py -x -v
grep -rn 'WARNINGS_FIFO_MAX_LEN' .   # expected: zero
grep -n 'MAX_WARNINGS' system_params.py notifier.py state_manager.py
# expected: defined in system_params (value 50); consumed in notifier + state_manager
pytest -x   # full suite
```
</verification>

<success_criteria>
- MAX_WARNINGS = 50 (single source).
- WARNINGS_FIFO_MAX_LEN does NOT exist anywhere.
- Both notifier + state_manager enforce MAX_WARNINGS.
- Run-date logged at INFO; asserted.
- Look-ahead-bias test green (or real bug fixed in follow-up [BLOCKING] task).
- 8 new tests green.
</success_criteria>

<output>
Create `27-10-SUMMARY.md` with: MAX_WARNINGS value-change rationale, look-ahead-bias finding (clean / bug surfaced + follow-up plan id), test count.
</output>
