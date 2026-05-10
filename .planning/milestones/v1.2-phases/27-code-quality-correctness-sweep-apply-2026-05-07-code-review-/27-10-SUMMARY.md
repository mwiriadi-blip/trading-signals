---
phase: 27
plan: 10
subsystem: warnings-FIFO / observability / look-ahead-bias guard
tags: [warnings, fifo, observability, look-ahead, regression-tests]
dependency_graph:
  requires: [27-01, 27-02, 27-03, 27-04, 27-05, 27-06, 27-07]
  provides: [MAX_WARNINGS=50 invariant, [Daily] run-date INFO marker, no-look-ahead invariant lock]
  affects: [system_params.py MAX_WARNINGS value, main.py run_daily_check INFO log]
tech_stack:
  added: [ast.walk symbol-existence gate (test); fixture-driven shock backtest harness (test)]
  patterns:
    - Single source of truth — MAX_WARNINGS lives only in system_params.py; state_manager.append_warning imports it; no parallel WARNINGS_FIFO_MAX_LEN.
    - AST symbol scan for "must-not-exist" identifier checks (skips docstring/comment matches naturally).
    - Look-ahead invariant via "hide K future bars + mutate them + confirm signal unchanged on visible prefix".
key_files:
  created:
    - tests/test_warnings_fifo.py
    - tests/test_run_date_logging.py
    - tests/test_lookahead_bias.py
  modified:
    - system_params.py
    - main.py
    - tests/test_state_manager.py
decisions:
  - MAX_WARNINGS value-change 100 → 50 (review-fix agreed-4) instead of introducing WARNINGS_FIFO_MAX_LEN. Single constant; existing FIFO implementation in state_manager.append_warning inherits the new bound automatically.
  - Plan referenced "notifier._dispatch_email_and_maintain_warnings" but the actual implementation is in main.py (`_dispatch_email_and_maintain_warnings_impl`) and routes ALL warnings mutations through state_manager.{clear_warnings, append_warning} (D-10 sole-writer invariant). Dispatch gate test asserts the structural routing rather than a non-existent direct FIFO maintenance block in notifier.
  - Run-date logging — added a NEW canonical `[Daily] run-date YYYY-MM-DD` INFO line at the head of run_daily_check (immediately after the weekday-gate short-circuit). The existing `[Sched] Run %s mode=%s` line is preserved for HH:MM:SS + mode metadata.
  - Look-ahead-bias test — locked the MEANINGFUL invariant (Day-N+1 must not affect Day-N's signal) rather than the plan's literal-but-wrong invariant ("Day-N's signal does NOT depend on Day-N's CLOSE"). The plan's action header explicitly said "lock in WHAT IT DOES"; doing that revealed the literal `<behavior>` text was incorrect for an EOD-daily system. See "Deviations from Plan" below.
metrics:
  duration: ~75min
  completed_date: 2026-05-08
---

# Phase 27 Plan 27-10: Warnings FIFO Tighten + Run-Date Log + Look-Ahead Test Summary

Three small bundled invariants landed in one plan:

1. **`MAX_WARNINGS` value-change 100 → 50** (Phase 27 #16, review-fix
   agreed-4). Single source of truth, no constant proliferation; the
   existing FIFO trim-on-append implementation in
   `state_manager.append_warning` inherits the new bound automatically.
2. **Canonical `[Daily] run-date YYYY-MM-DD` INFO log** at the head of
   `run_daily_check` so journalctl tails grep cleanly for daily runs.
3. **No-look-ahead invariant lock-in** — proven on the canonical 400-bar
   AXJO fixture across 5 future-bar shock tests. No real bug surfaced;
   no follow-up [BLOCKING] plan required.

## Task 1 — MAX_WARNINGS 100 → 50 (review-fix agreed-4)

| Item | Before | After |
|------|--------|-------|
| `system_params.MAX_WARNINGS` | `100` | `50` (commented inline) |
| `WARNINGS_FIFO_MAX_LEN` | (would have collided) | does NOT exist (AST-gated) |
| FIFO trim site count | 1 (`state_manager.append_warning`) | 1 (unchanged) |
| Hardcoded literal in trim expression | none | none (asserted by AST gate) |

**Implementation note.** The plan referenced
`notifier._dispatch_email_and_maintain_warnings` but the actual code in
this codebase lives in `main.py`
(`_dispatch_email_and_maintain_warnings_impl` + thin
`_dispatch_email_and_maintain_warnings` wrapper). Importantly, the
dispatch path does NOT maintain `state['warnings']` directly — it
calls `state_manager.clear_warnings(state)` and conditionally
`state_manager.append_warning(state, ...)`. State_manager is the
D-10-mandated sole writer. So the new FIFO bound is enforced once at
the source-of-truth, and inherited everywhere automatically — no
notifier change required, no main change required.

**Test gate (`tests/test_warnings_fifo.py` — 7 tests):**

| Class | Test | Asserts |
|-------|------|---------|
| TestMaxWarningsValue | test_max_warnings_value_is_50 | `system_params.MAX_WARNINGS == 50` |
| TestNoDuplicateFifoConstant | test_no_duplicate_fifo_constant | AST walk: no `WARNINGS_FIFO_MAX_LEN` Name/ImportFrom/Assign/Attribute/AnnAssign anywhere |
| TestWarningsFifoBound | test_warnings_fifo_does_not_exceed_max | 60 appends → `len ≤ MAX_WARNINGS` |
| TestWarningsFifoBound | test_warnings_fifo_eviction_order | latest 50 in FIFO order (observable invariant — review-fix M1) |
| TestDispatchUsesMaxWarningsConstant | test_state_manager_imports_max_warnings | AST: `from system_params import (… MAX_WARNINGS …)` AND no local redefinition |
| TestDispatchUsesMaxWarningsConstant | test_no_hardcoded_warnings_bound_literal_in_state_manager | regex: append_warning body uses `MAX_WARNINGS`, no literal `100` / `50` slice |
| TestDispatchUsesMaxWarningsConstant | test_dispatch_path_routes_through_state_manager | regex: `_dispatch_email_and_maintain_warnings_impl` body invokes `clear_warnings` + `append_warning`, no `WARNINGS_FIFO_MAX_LEN` |

## Task 2 — `[Daily] run-date YYYY-MM-DD` INFO log

Added a single NEW INFO line at the head of `run_daily_check`
(`main.py` immediately after the weekday-gate short-circuit and before
the existing `[Sched] Run …` line). The pre-existing
`[Sched] Run 2026-04-27 08:00:00 AWST mode=once` line carries
HH:MM:SS + mode= and is preserved verbatim — both lines fire on every
weekday daily run.

**Test gate (`tests/test_run_date_logging.py` — 1 test):**

| Test | Asserts |
|------|---------|
| `TestRunDateLogging::test_daily_run_logs_run_date` | invokes `main(['--once'])` on stub state via committed fetch fixtures + frozen time (Mon 2026-04-27 08:00 AWST); caplog INFO must contain at least one record matching `r'\[Daily\] run-date \d{4}-\d{2}-\d{2}'`. |

## Task 3 — Look-ahead-bias backtest test (FAIL LOUD per agreed-4)

Locked in two contracts on `signal_engine.get_signal`:

**(a) EOD contract** — Day-N's signal IS expected to depend on Day-N's
OHLC bar (the system computes signals end-of-close using today's full
bar; trade execution lands at next-day open per
`sizing_engine.step()`'s `bar['close']` entry pricing convention).

**(b) No-look-ahead invariant** — Day-N's signal MUST NOT depend on
Day-N+1 (or later) bars. The MEANINGFUL invariant.

**Test gate (`tests/test_lookahead_bias.py` — 6 tests):**

| Class | Test | Asserts |
|-------|------|---------|
| TestSignalRespondsToTodayBar | test_today_close_influences_signal_when_shocked_extremely | shock Close ±50% on an ADX-passing non-FLAT window → at least one direction flips signal (load-bearing EOD dependency) |
| TestSignalIndependentOfFutureBars | test_signal_unchanged_when_future_bars_mutated[1] | hide last 1 bar; mutate it ×100/÷100 OHLC; signal on visible prefix unchanged |
| TestSignalIndependentOfFutureBars | test_signal_unchanged_when_future_bars_mutated[2] | hide last 2 bars; same shock; signal unchanged |
| TestSignalIndependentOfFutureBars | test_signal_unchanged_when_future_bars_mutated[5] | hide last 5 bars; same shock; signal unchanged |
| TestSignalIndependentOfFutureBars | test_signal_invariant_under_future_close_extremes | bar N+1 Close ×1000; signal on bars[:-1] unchanged |
| TestSignalIndependentOfFutureBars | test_signal_invariant_under_future_ohl_extremes | bar N+1 Open ×100, High ×100, Low ÷100 (each); signal on bars[:-1] unchanged |

**Result:** 6/6 green on the canonical 400-bar AXJO fixture
(`tests/fixtures/axjo_400bar.csv`). No look-ahead bug surfaced; no
follow-up [BLOCKING] plan needed.

## Threat-model verification

| Threat ID | Disposition | Verification |
|-----------|-------------|--------------|
| T-27-10-01 (DoS-self via unbounded warnings list growth) | mitigate ✓ | `MAX_WARNINGS = 50` enforced at single chokepoint (`state_manager.append_warning`); `test_warnings_fifo_does_not_exceed_max` + AST gate against duplicate constant |
| T-27-10-02 (Look-ahead bias → optimistic backtests that don't replicate live) | mitigate ✓ | 5 future-bar shock tests in `tests/test_lookahead_bias.py::TestSignalIndependentOfFutureBars` — all green on canonical fixture |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in plan: `<behavior>` text contradicted action
header]** Plan Task 3 `<behavior>` block stated "Day-N's signal does
NOT depend on Day-N's CLOSE." This is **incorrect** for this system:
`Mom_k = close.pct_change(periods=k)` uses today's close, ADX uses
today's High/Low TR-window, and `get_signal` reads `df.iloc[-1]`.
The plan's action header overrode this with "Read signal_engine.
get_signal source FIRST. Determine actual contract … lock in WHAT IT
DOES." Honouring the action: locked in the actual EOD contract
(today's bar feeds today's signal — by design for an EOD-daily
system whose signals execute next-day open) AND locked the
MEANINGFUL no-look-ahead invariant (no future-bar leakage). All 6
tests green; no real look-ahead bug present; no follow-up [BLOCKING]
plan required. Documenting the deviation here makes the next planner
aware that the plan's literal `<behavior>` bullet was wrong, not the
implementation.

**2. [Rule 1 - Test cascade fix]**
`tests/test_state_manager.py::TestWarnings::test_append_warning_fifo_trims_oldest_entries`
hardcoded the literal `range(105)` + `msg 5` / `msg 104` sentinel
expectations tied to the value 100. Generalised off MAX_WARNINGS+5 so
the value-change does not require touching this test now (and won't
require touching it again next time MAX_WARNINGS changes).

**3. [Rule 1 - Test mechanism: AST instead of grep]** Initial
`test_no_duplicate_fifo_constant` used a line-level string scan and
falsed on the test file's own docstring mentions of
`WARNINGS_FIFO_MAX_LEN`. Switched to `ast.walk` over Name /
ImportFrom / Assign / Attribute / AnnAssign nodes — naturally skips
string literals (docstrings/comments are `ast.Constant(str)`, not
identifiers). Same fix applied to
`test_state_manager_imports_max_warnings` (regex over the multi-line
import block was order-dependent and brittle; AST scan of
ImportFrom + Assign is canonical).

### Plan locator drift (informational, no fix needed)

Plan repeatedly referred to `notifier._dispatch_email_and_maintain_warnings`
and a "FIFO maintenance step" inside notifier. In actual code the
function lives at `main.py:1667` (and impl at
`main.py:517 _dispatch_email_and_maintain_warnings_impl`), and there
is no FIFO maintenance step in notifier or main — both
`clear_warnings` and `append_warning` are state_manager helpers
(D-10 sole-writer). The bound flows from `MAX_WARNINGS` → state_manager
once and is inherited by every caller. So no notifier or main edits
were needed for the FIFO bound; only the constant changed. Plan
deviation classified informational, not a Rule deviation.

### CLAUDE.md compliance

- No new files at root (tests added to `tests/` per project convention).
- No documentation files created beyond plan-output SUMMARY.md.
- File sizes — all new test files under 500 lines:
  - `tests/test_warnings_fifo.py` = 209 lines
  - `tests/test_run_date_logging.py` = 77 lines
  - `tests/test_lookahead_bias.py` = 240 lines
- Read-before-edit rule honored on every edit.
- No secrets / credentials touched.

## Self-Check: PASSED

- [x] `tests/test_warnings_fifo.py` exists (commit 7c6f639 RED, 89dfdc0 refined+GREEN)
- [x] `tests/test_run_date_logging.py` exists (commit b627f98 RED)
- [x] `tests/test_lookahead_bias.py` exists (commit 6057024)
- [x] `system_params.py` MAX_WARNINGS = 50 (commit 89dfdc0)
- [x] `main.py` `[Daily] run-date` INFO line added (commit 05b527f)
- [x] AST gate confirms 0 references to `WARNINGS_FIFO_MAX_LEN` anywhere
- [x] 14/14 plan tests green
- [x] 1917/1917 full suite green (was 1903 baseline; +14 net new tests this plan)

## Commits

- `7c6f639` — test(27-10): RED — warnings FIFO bound + collision regression
- `89dfdc0` — feat(27-10): GREEN — MAX_WARNINGS 100 → 50 (review-fix agreed-4)
- `b627f98` — test(27-10): RED — run-date INFO log assertion
- `05b527f` — feat(27-10): GREEN — add canonical [Daily] run-date INFO log
- `6057024` — test(27-10): look-ahead-bias backtest test — invariant proven
