---
phase: 27
plan: 10
type: execute
wave: 2
parallel: true
depends_on: []
files_modified:
  - system_params.py
  - notifier.py
  - main.py
  - tests/test_warnings_fifo.py
  - tests/test_run_date_logging.py
  - tests/test_lookahead_bias.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "WARNINGS_FIFO_MAX_LEN constant defined in system_params (suggested 50)."
    - "Warnings-FIFO maintenance (B1 canonical: dispatch → clear → maybe-append → single save) NEVER exceeds WARNINGS_FIFO_MAX_LEN."
    - "Daily run logs run-date YYYY-MM-DD AWST at INFO level once per execution."
    - "Backtest test asserts Day-N's signal does NOT depend on Day-N's CLOSE — only on Day-N-1 and earlier bars."
  artifacts:
    - path: tests/test_warnings_fifo.py
      provides: "FIFO max-length + overflow eviction-order regression"
      contains: "WARNINGS_FIFO_MAX_LEN"
    - path: tests/test_run_date_logging.py
      provides: "run-date INFO log assertion via caplog"
      contains: "caplog"
    - path: tests/test_lookahead_bias.py
      provides: "look-ahead bias proof on backtest"
      contains: "lookahead"
  key_links:
    - from: "notifier._dispatch_email_and_maintain_warnings"
      to: "system_params.WARNINGS_FIFO_MAX_LEN"
      via: "len-bound enforcement"
      pattern: "WARNINGS_FIFO_MAX_LEN"
---

<objective>
Three test additions bundled (review items #16 + ALSO-mentioned: run-date logging + look-ahead-bias). All three are pure test-additions or guard-clauses; small individually, related thematically (all are regression-tests for invariants the system already mostly upholds — just unprotected today).

1. **Warnings-FIFO test (item #16):** assert FIFO never exceeds WARNINGS_FIFO_MAX_LEN; cover overflow eviction order.
2. **Run-date logging assertion:** integration test that the daily run logs the run-date YYYY-MM-DD AWST at INFO level (verified via caplog).
3. **Look-ahead-bias backtest test:** assert Day-N's signal does NOT depend on Day-N's CLOSE — only Day-N-1 and earlier.

Bundled because all three are <100 LOC test additions with no production-code coupling beyond the WARNINGS_FIFO_MAX_LEN constant.

Purpose: lock in invariants that already (mostly) hold, prevent regression.
Output: 3 new test files + 1 system_params constant.
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
@backtest/

<interfaces>
# WARNINGS_FIFO_MAX_LEN — define if absent; suggested 50.
# Find the existing FIFO maintenance code (per STATE.md Plan 03 reference: B1 canonical ordering
# in notifier._dispatch_email_and_maintain_warnings). The function manages state['warnings'] as a list.
# Add a guard at the maybe-append step:
#   while len(state['warnings']) >= WARNINGS_FIFO_MAX_LEN:
#     state['warnings'].pop(0)  # FIFO eviction
#   state['warnings'].append(new_warning)
#
# Run-date log: main.py run_daily_check writes log lines. Identify the existing INFO-level
# entry that names the run date (likely something like `[Daily] run for 2026-05-07`). If absent,
# add: `logger.info(f'[Daily] run-date {run_date_aws}')` near the top of run_daily_check.
#
# Look-ahead-bias: backtest/simulator.py per Phase 23 plan was designed correctly. The test:
#   - Build a fake df with Day-N OHLC where C is a shock value (e.g. close +50%)
#   - Compute signal for Day-N
#   - Compare to signal for Day-N with a different Day-N CLOSE (same prior days, different today close)
#   - Assert: same signal output regardless of today's close — proves no look-ahead.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Warnings-FIFO test + WARNINGS_FIFO_MAX_LEN constant</name>
  <read_first>
    - system_params.py
    - notifier.py — search for `state['warnings']` and `_dispatch_email_and_maintain_warnings`
  </read_first>
  <behavior>
    - test_warnings_fifo_max_len_constant: WARNINGS_FIFO_MAX_LEN == 50 (or whatever value chosen).
    - test_warnings_fifo_does_not_exceed_max: build a state with 60 pending warnings; call the FIFO maintenance helper; assert len(state['warnings']) <= 50.
    - test_warnings_fifo_eviction_order: append 60 numbered warnings (0..59); FIFO should evict 0..9, keeping 10..59. Assert state['warnings'] == [w_10, w_11, ..., w_59].
    - test_dispatch_invariant_canonical_ordering: monkey-trace the call sequence in _dispatch_email_and_maintain_warnings — assert dispatch → clear → maybe-append → single save (one call to mutate_state per dispatch).
  </behavior>
  <action>
1. **system_params.py:** add `WARNINGS_FIFO_MAX_LEN: int = 50  # Phase 27 #16`.
2. **notifier.py:** locate _dispatch_email_and_maintain_warnings. Add the bound-enforcing while-pop loop at the maybe-append step. Import WARNINGS_FIFO_MAX_LEN.
3. **tests/test_warnings_fifo.py (NEW):** 4 tests per behavior block.
  </action>
  <verify>
    <automated>pytest tests/test_warnings_fifo.py -x -v</automated>
  </verify>
  <done>
    - Constant defined; helper enforces bound.
    - 4 tests green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Run-date logging assertion</name>
  <read_first>
    - main.py — run_daily_check function body
  </read_first>
  <behavior>
    - test_daily_run_logs_run_date: invoke run_daily_check on a stub state; capture caplog at INFO; assert at least one record matches r'\[Daily\] run-date \d{4}-\d{2}-\d{2}'.
  </behavior>
  <action>
1. Inspect run_daily_check for any existing run-date log line. If present and INFO-level, the test just locks it in. If missing/wrong-level, add `logger.info(f'[Daily] run-date {run_date_aws}')` near the function entry (right after computing run_date).
2. **tests/test_run_date_logging.py (NEW):** 1 test (could merge with another file but keep separate for grep-ability).
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
  <name>Task 3: Look-ahead-bias backtest test</name>
  <read_first>
    - backtest/simulator.py
    - tests/test_backtest_simulator.py (existing patterns)
  </read_first>
  <behavior>
    - test_signal_independent_of_today_close: construct a 30-bar OHLC df ending on Day-N. Run signal_engine.get_signal. Then mutate Day-N's CLOSE to a shock value (1.5×, 0.5×). Run get_signal again. Assert the two signals are identical — Day-N close did not influence the vote.
    - Variant: shock the OPEN, HIGH, LOW (one at a time) — confirm get_signal uses ONLY prior bars in its indicator computation. (Caveat: Mom-1 etc. legitimately use today's close in the formula? — Read signal_engine.compute_indicators to confirm the indicator boundary. If today's close IS used in Mom-1, then the assertion is actually "signal uses Day-N's close at INDICATOR level — but get_signal at trading-loop level evaluates the PRIOR ROW's row.signal because today's bar isn't complete at signal time". Either way, the test pins the actual semantics.)
    - The eloquent path: read signal_engine.get_signal source; if it indexes `df.iloc[-1]`, today's bar IS used → look-ahead by definition for live trading. If it indexes `df.iloc[-2]`, prior bar — no look-ahead. Test the actually-implemented contract.
    > **Most eloquent:** read the source first, write the test to lock in WHAT IT ACTUALLY DOES, not what we assume. If the implementation uses today's close, that's a real bug — escalate to a separate fix plan rather than silently asserting it.
  </behavior>
  <action>
1. Read `backtest/simulator.py` and `signal_engine.get_signal` to determine which row's data feeds the signal decision.
2. Write the test to lock in the actual contract: "Day-N signal uses bars [Day-(N-K) ... Day-(N-1)] for K=20-bar window, NOT Day-N close" — adjust the index slice based on what the source says.
3. If the source DOES use Day-N close in any way, document in 27-DEBT.md as a separate finding (do NOT silently fix here — orchestrator-flagged item is the TEST not the FIX).
4. **tests/test_lookahead_bias.py (NEW):** at least 1 strong test asserting the boundary.
  </action>
  <verify>
    <automated>pytest tests/test_lookahead_bias.py -x -v</automated>
  </verify>
  <done>
    - Look-ahead-bias test green (or, if a real bug surfaces, documented in 27-DEBT.md and marked xfail with strict=True for follow-up).
  </done>
</task>

</tasks>

<threat_model>
N/A — pure test additions; the WARNINGS_FIFO_MAX_LEN bound is a DoS-prevention guard (unbounded warnings list could grow over months) but the bound enforcement is mechanical.

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-10-01 | DoS (self) | Unbounded warnings list grows with every error → state.json bloats → load/save slows | mitigate | WARNINGS_FIFO_MAX_LEN bound enforced at maintenance helper. |
</threat_model>

<verification>
```
pytest tests/test_warnings_fifo.py tests/test_run_date_logging.py tests/test_lookahead_bias.py -x -v
grep -n 'WARNINGS_FIFO_MAX_LEN' system_params.py notifier.py
# expected: defined + consumed
pytest -x   # full suite
```
</verification>

<success_criteria>
- WARNINGS_FIFO_MAX_LEN defined + enforced.
- 4 + 1 + 1 = 6 new tests green.
- Run-date logged at INFO; look-ahead-bias asserted (or documented bug if surfaced).
</success_criteria>

<output>
Create `27-10-SUMMARY.md` with: WARNINGS_FIFO_MAX_LEN value, look-ahead-bias finding (clean / bug surfaced), test count.
</output>
