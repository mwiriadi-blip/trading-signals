---
phase: 23
plan: 04
subsystem: backtest-metrics
tags: [pure-math, sharpe, drawdown, pass-criterion, hex-boundary]
requires:
  - backtest/metrics.py (Wave 0 stub from 23-01)
  - tests/test_backtest_metrics.py (Wave 0 skeleton from 23-01)
provides:
  - backtest.metrics.compute_metrics(equity_curve, trades) -> dict (8 fields)
  - 18 passing tests across 5 named test classes (TestCumulativeReturn / TestSharpe / TestMaxDrawdown / TestWinRateExpectancy / TestPassCriterion)
affects:
  - backtest/metrics.py
  - tests/test_backtest_metrics.py
  - .planning/phases/23-five-year-backtest-validation-gate/deferred-items.md
tech-stack:
  added: []
  patterns:
    - pandas Series.cummax() peak-to-trough drawdown idiom (RESEARCH §Pattern 7)
    - statistics.stdev (ddof=1) for raw daily Sharpe (RESEARCH A1)
    - sharpe_annualized = sharpe_daily * sqrt(252) dual-emit (planner D-19)
    - STRICT > pass criterion (D-16; equality at 100.0 = FAIL)
    - hex-pure module (allowed: math, statistics, typing, pandas, numpy)
key-files:
  created: []
  modified:
    - backtest/metrics.py
    - tests/test_backtest_metrics.py
    - .planning/phases/23-five-year-backtest-validation-gate/deferred-items.md
decisions:
  - D-16 STRICT > pass criterion implemented via `cum_return > _PASS_THRESHOLD_PCT` (not >=); test_exactly_100_fails enforces the boundary
  - D-19 dual-Sharpe (sharpe_daily raw + sharpe_annualized = daily * sqrt(252)) emitted in metrics dict
  - cummax() peak-to-trough idiom (not global min/max) for max_drawdown_pct — anti-pattern test ensures regression catch
  - Edge cases: zero trades → (0.0, 0.0, 0); single bar → cum_return=0.0; flat equity → sharpe=0.0
metrics:
  duration: ~5 minutes
  completed: 2026-05-01
  tasks: 2
  files: 3 (2 modified plan files + 1 deferred-items entry)
  commits: 2
---

# Phase 23 Plan 04: Wave 1C — backtest/metrics.py Summary

Pure-math aggregator: BACKTEST-02 metrics block per CONTEXT D-05 (extended with planner D-19 sharpe_annualized). Replaces Wave 0 NotImplementedError stub. Drives the BACKTEST-03 pass/fail badge — gating metric is `cumulative_return_pct > 100.0` STRICT (D-16; equality at exactly 100.0 = FAIL).

## Tasks Completed

| Task | Name | Commit |
|------|------|--------|
| 1 | Implement backtest/metrics.py compute_metrics | 639c33a |
| 2 | Implement tests/test_backtest_metrics.py (5 test classes, 18 tests) | ac3a3c9 |

## compute_metrics Signature Finalized

```python
def compute_metrics(equity_curve: Sequence[float], trades: list[dict]) -> dict:
  """Returns:
    cumulative_return_pct: float (4dp; signed)
    sharpe_daily: float (4dp; raw mean/stdev ddof=1)
    sharpe_annualized: float (4dp; daily * sqrt(252))
    max_drawdown_pct: float (4dp; negative; cummax peak-to-trough)
    win_rate: float (4dp; 0.0 if no trades)
    expectancy_aud: float (4dp; mean net_pnl_aud; 0.0 if no trades)
    total_trades: int
    pass: bool (cum_return > 100.0 STRICT per D-16)
  """
```

## Verification Results

### 1. compute_metrics callable with D-05 schema
```
$ .venv/bin/python -c "from backtest.metrics import compute_metrics; m = compute_metrics([10000.0, 12000.0, 21000.0], [{'net_pnl_aud': 376.50}]); assert m['cumulative_return_pct'] == 110.0; assert m['pass'] is True; assert m['total_trades'] == 1; assert m['sharpe_annualized'] != m['sharpe_daily']; print('ok')"
ok
```

### 2. Acceptance grep checks (Task 1)
```
grep -c '^def compute_metrics' backtest/metrics.py        → 1
grep -c "'sharpe_daily':" backtest/metrics.py             → 1
grep -c "'sharpe_annualized':" backtest/metrics.py        → 1  (planner D-19)
grep -c "cum_return > _PASS_THRESHOLD_PCT" backtest/metrics.py → 1  (STRICT > per D-16)
grep -c 'cummax()' backtest/metrics.py                    → 1  (RESEARCH §Pattern 7)
grep -c '^import (json|html|os|datetime|yfinance|pyarrow|requests|state_manager...)' → 0
```

### 3. Test suite (Task 2)
```
$ .venv/bin/pytest tests/test_backtest_metrics.py -x -q
..................                                                       [100%]
18 passed in 1.31s
```

5 test classes × 3-4 tests each:
- TestCumulativeReturn (4): doubling, 127% pass, loss, single-bar
- TestSharpe (3): sqrt(252) ratio, zero-variance, single-return
- TestMaxDrawdown (4): peak-to-trough, monotonic, decline, cummax-not-global anti-pattern
- TestWinRateExpectancy (4): zero, all-wins, all-losses, mixed-50pct
- TestPassCriterion (3): strictly-above, exactly-100-fails (D-16 boundary), below-100

### 4. Pass criterion D-16 boundary verified
```
$ .venv/bin/pytest tests/test_backtest_metrics.py::TestPassCriterion::test_exactly_100_fails -x -q
1 passed
```
Equity [10_000, 20_000] → cum_return = 100.0 exactly → `pass = False`. Strict `>` (not `>=`) enforced.

### 5. Sharpe annualization √252 ratio verified
```
$ .venv/bin/pytest tests/test_backtest_metrics.py::TestSharpe::test_annualized_is_sqrt252_times_daily -x -q
1 passed
```
Ratio `sharpe_annualized / sharpe_daily` matches `math.sqrt(252) ≈ 15.874` within 1e-4.

### 6. Max DD anti-pattern caught
```
$ .venv/bin/pytest tests/test_backtest_metrics.py::TestMaxDrawdown::test_dd_uses_cummax_not_global_min_over_max -x -q
1 passed
```
Equity [100, 120, 80, 200]: cummax peak-to-trough = -33.33% (not the global min/max anti-pattern's -60%).

### 7. AST hex-boundary guard regression-free
```
$ .venv/bin/pytest tests/test_signal_engine.py::TestDeterminism -x -q
55 passed in 5.51s
```

### 8. Full suite excluding pre-existing unrelated failures
```
$ .venv/bin/pytest --ignore=tests/test_nginx_signals_conf.py --ignore=tests/test_notifier.py --ignore=tests/test_setup_https_doc.py -q
1378 passed, 16 skipped
```

## Decisions Made

- **D-16 STRICT enforced:** `cum_return > _PASS_THRESHOLD_PCT` (Python strict greater-than, not `>=`). Test `test_exactly_100_fails` is the regression guard.
- **D-19 dual-Sharpe emitted:** `sharpe_daily` (raw) AND `sharpe_annualized = daily × √252`. Backward-compatible with D-05 schema field name; UI can re-label to "Sharpe (annualised)" without schema migration.
- **cummax peak-to-trough max DD:** Anti-pattern (`equity.min() / equity.max() - 1`) is explicitly tested against — sequence [100, 120, 80, 200] gives -33.33% (correct) vs -60% (wrong global formula).
- **Edge cases handled:** zero trades, single bar, flat equity, all-wins, all-losses, single-return point. All return safe values (0.0 / negatives / valid floats), never NaN or exception.
- **4-decimal rounding:** All float metrics rounded to 4dp at dict-construction time. `total_trades` is int; `pass` is bool.

## Deviations from Plan

None — plan executed exactly as written. Both tasks completed in order. All acceptance criteria met. All 18 new tests + 55 AST guard tests passing.

## Auth Gates

None — pure-math hex module with no I/O surface.

## Threat Flags

None — no new external trust boundaries. Module consumes primitives (list of floats + list of dicts) and returns a dict. No new attack surface beyond what was documented in the plan's `<threat_model>` (which was empty by design — pure-math hex).

## Deferred Issues (out-of-scope, pre-existing)

3 test failures observed during regression check pre-existed on the worktree base commit (26021b4). None touch backtest/metrics.py code paths. Logged to `.planning/phases/23-five-year-backtest-validation-gate/deferred-items.md`:

- `tests/test_nginx_signals_conf.py::TestNginxConfStructure::test_listen_443_ssl` — nginx deploy config drift
- `tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression` — notifier ruff regression
- `tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard::test_owned_domain_placeholder_matches_nginx_conf` — HTTPS doc cross-artifact drift

## TDD Gate Compliance

Both tasks marked `tdd="true"`. Plan ordering: Task 1 (`feat:` GREEN) implements `compute_metrics`; Task 2 (`test:` covers RED→GREEN paired) adds the 5 test classes. The Wave 0 skeleton (raising NotImplementedError) served as the implicit RED gate before Task 1; Task 2's tests then provide the durable test suite.

Note on RED-first strictness: The pre-existing Wave 0 stub already failed any meaningful invocation (NotImplementedError), so any test against `compute_metrics` in its stub form would automatically RED. Task 1 transitioned that stub to a working implementation (GREEN). Task 2 then formalized 18 named tests that all PASS against the GREEN implementation. No standalone RED commit was created for the formal test file because the stub itself was the RED. This matches the plan-as-written ordering and acceptance criteria.

## Self-Check: PASSED

All claimed files verified to exist:
```
backtest/metrics.py                                          FOUND
tests/test_backtest_metrics.py                               FOUND
.planning/phases/23-five-year-backtest-validation-gate/deferred-items.md  FOUND
```

All claimed commits verified in git log:
```
639c33a  FOUND  feat(23-04): implement backtest/metrics.py compute_metrics (BACKTEST-02)
ac3a3c9  FOUND  test(23-04): implement 5 test classes for backtest/metrics.py (18 tests)
```

Wave 1C (metrics) complete. Wave 2 plans (23-05 render, 23-06 cli, 23-07 web routes) remain blocked only on each other's intra-Wave-2 ordering — Wave 1C unblocks render's downstream metric consumption.
