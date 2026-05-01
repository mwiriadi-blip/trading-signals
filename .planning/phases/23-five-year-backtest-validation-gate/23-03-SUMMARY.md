---
phase: 23
plan: 03
subsystem: backtest
tags: [backtest, simulator, replay, hexagonal, signal-engine-reuse, sizing-engine-reuse]
requires: [23-01]
provides:
  - backtest.simulator.simulate
  - backtest.simulator.SimResult
affects:
  - tests/test_backtest_simulator.py
tech-stack:
  added: []
  patterns: [O(n)-signal-extraction, dataclass-result, half-half-cost-split]
key-files:
  created: []
  modified:
    - backtest/simulator.py
    - tests/test_backtest_simulator.py
    - .planning/phases/23-five-year-backtest-validation-gate/deferred-items.md
decisions:
  - "Inline get_signal logic in _extract_signals to keep replay O(n) (RESEARCH §Pattern 2)"
  - "Snapshot position_before step() so trade-log can carry entry_date/atr_entry/pyramid_level (RESEARCH §Pitfall 7)"
  - "exit_reason emitted verbatim from sizing_engine.ClosedTrade (planner D-20, NOT D-05's illustrative 'signal_change')"
  - "Pre-existing failures (nginx/notifier/setup_https) treated as out-of-scope per executor scope-boundary"
metrics:
  duration: ~6 minutes
  tasks: 2
  files_created: 0
  files_modified: 3
completed: 2026-05-01
---

# Phase 23 Plan 03: Wave 1B — backtest/simulator.py Summary

Implemented bar-by-bar replay simulator (`backtest/simulator.simulate`) that reuses `signal_engine.compute_indicators` and `sizing_engine.step` verbatim, producing a deterministic trade log + equity curve aligned to input OHLCV bars. 8/8 tests pass; AST hex-boundary guard regression-free.

## Tasks Executed

| # | Task | Type | Status | Commit |
|---|------|------|--------|--------|
| 1 | Implement `tests/test_backtest_simulator.py` (RED) | tdd-red | done | `e9ac573` |
| 2 | Implement `backtest/simulator.py` (GREEN) + fixture refinement | tdd-green | done | `83a2d81` |

## What Was Built

### `backtest/simulator.py` (~140 LOC)

Public surface:

```python
@dataclasses.dataclass(frozen=True)
class SimResult:
  trades: list[dict]
  equity_curve: list[float]
  dates: list[str]
  final_account: float

def simulate(
  df: pd.DataFrame,
  instrument: str,                   # 'SPI200' | 'AUDUSD'
  multiplier: float,                 # SPI_MULT (5.0) | AUDUSD_MULT (10_000.0)
  cost_round_trip_aud: float,        # 6.0 (SPI) | 5.0 (AUDUSD)
  initial_account_aud: float,        # default 10_000.0 per CONTEXT D-02
) -> SimResult: ...
```

Internal helpers:
- `_extract_signals(df_ind)` — O(n) per-bar signal extraction (LONG/SHORT/FLAT) by inlining `get_signal` logic against pre-computed indicators; avoids the slice anti-pattern that would make replay O(n²).
- `_row_to_bar(row, idx)` / `_row_to_indicators(row)` — pandas → step() dict adapters; preserve NaN ATR/ADX so step's NaN policy (Phase 2 B-1) drives warmup behavior.

### Cost reconstruction (CONTEXT D-05 + Phase 2 D-13)

Step takes `cost_aud_open = round_trip / 2` (open-half charged via `compute_unrealised_pnl`). `ClosedTrade.realised_pnl` already has the close-half deducted. Trade-log emits:

- `cost_aud` = full round-trip (display field)
- `net_pnl_aud` = `realised_pnl` (close-half already deducted)
- `gross_pnl_aud` = `realised_pnl + close_half × n_contracts`

**Canonical proof from a passing test trade** (TestCostModel · `_bull_to_bear_df`, drift=10/day):

| Field | Value |
|-------|-------|
| side | LONG |
| contracts | 8 |
| net_pnl_aud (=`realised_pnl`) | 132376.0 |
| close_half × n | 3.0 × 8 = 24.0 |
| gross_pnl_aud | 132400.0 ✓ (=132376 + 24) |
| cost_aud | 6.0 (full round-trip) |

`abs(gross - (net + close_half × n)) < 1e-6` holds for every trade in the suite.

### exit_reason verbatim (planner D-20)

`exit_reason` field passes `ClosedTrade.exit_reason` straight through — no remapping to D-05's illustrative `'signal_change'`. The whitelist in `TestExitReasons` covers all sizing-engine values (`flat_signal`, `signal_reversal`, `trailing_stop`, `adx_drop`, `manual_stop`, `stop_hit`, `adx_exit`).

### Determinism evidence

`TestDeterminism::test_two_runs_identical` (1300-bar bull frame) asserts:
```
a.trades == b.trades
a.equity_curve == b.equity_curve
a.dates == b.dates
a.final_account == b.final_account
```
Two consecutive `simulate(...)` invocations on the same input produce byte-equal Python lists/floats. Pure-math composition with no clock or env reads guarantees this.

## Test Suite

```
tests/test_backtest_simulator.py — 8 passed in 1.84s

TestDeterminism
  ✓ test_simulate_returns_simresult
  ✓ test_two_runs_identical
  ✓ test_initial_account_validation
TestCostModel
  ✓ test_cost_aud_in_trade_log_is_full_round_trip
  ✓ test_gross_minus_cost_equals_net
TestExitReasons
  ✓ test_exit_reason_verbatim_from_sizing_engine
TestNanSafety
  ✓ test_warmup_bars_produce_no_trades
  ✓ test_short_frame_does_not_crash
```

AST hex-boundary regression: `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` and `::test_backtest_pure_no_pyarrow_import` both green (10 passed).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] `_bear_to_bull_df` fixture produced 0 trades, skipping cost-model + exit-reason assertions**
- **Found during:** Task 2 verification — initial green run reported `2 skipped` ("no trades closed in this synthetic frame").
- **Issue:** Original drift (1.0 / 1.5 per bar) kept Mom1(21-bar) and Mom3(63-bar) below MOM_THRESHOLD=0.02. With base=8000 + drift=1.0, Mom1 ≈ 21/8000 ≈ 0.0026 — far below the 2% gate. Only Mom12 cleared the threshold; 2-of-3 vote never fired, so `_extract_signals` returned all-FLAT and the simulator never opened a position.
- **Fix:** Replaced fixture with `_bull_to_bear_df(drift=10.0, base=7000.0)` so Mom1 21-bar return ≈ 21·10/7000 ≈ 0.030 clears the gate. Increased starting account to 100_000.0 so sized contracts ≥ 1 (otherwise no-trade-when-zero-contracts policy applies).
- **Files modified:** `tests/test_backtest_simulator.py` (fixture body + initial_account in 5 callsites + `final_account` assertion in `test_short_frame_does_not_crash`).
- **Commit:** `83a2d81`
- **Why this is a Rule 1 bug, not a plan deviation:** the plan's behavior contracts (cost reconstruction, exit-reason verbatim) require trades to exist. A fixture that silently skips is the same shape as the `does_NOT_` test fossil pattern in CLAUDE.md/LEARNINGS — the test passes but the assertion never runs. Fixing the fixture restores the intended assertion coverage.

### Out-of-scope failures observed (NOT fixed — logged only)

Per executor scope-boundary rule, three pre-existing test failures observed on the worktree base commit `71b6494` are out of scope and logged to `deferred-items.md`:

- `tests/test_nginx_signals_conf.py::TestNginxConfStructure::test_listen_443_ssl`
- `tests/test_notifier.py::test_ruff_clean_notifier`
- `tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard::test_owned_domain_placeholder_matches_nginx_conf`

Confirmed via `git stash && pytest && git stash pop` that they fail without any 23-03 changes.

## Authentication Gates

None — no network or auth surface in this plan.

## Threat Flags

None — simulator is pure-math hex composition; introduces no external trust boundary. Threat register inheritance from data_fetcher (T-23-cache-tamper) and CLI/web routes is mitigated upstream per CONTEXT.

## Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| `grep -c '^def simulate' backtest/simulator.py` returns 1 | ✓ |
| `grep -c '^class SimResult\|^@dataclasses.dataclass' backtest/simulator.py` ≥ 1 | ✓ (2) |
| `grep -c 'from signal_engine import' backtest/simulator.py` returns 1 | ✓ |
| `grep -c 'from sizing_engine import step' backtest/simulator.py` returns 1 | ✓ |
| `grep -c 'cost_open = cost_round_trip_aud / 2' backtest/simulator.py` returns 1 | ✓ |
| `grep -c "'cost_aud': float(cost_round_trip_aud)" backtest/simulator.py` returns 1 | ✓ |
| `grep -c "'exit_reason': ct.exit_reason" backtest/simulator.py` returns 1 | ✓ |
| Forbidden imports (datetime/os/json/html/yfinance/requests/state_manager/notifier/dashboard/main) | 0 ✓ |
| `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` | ✓ |
| `pytest tests/test_signal_engine.py::TestDeterminism::test_backtest_pure_no_pyarrow_import` | ✓ |
| `pytest tests/test_backtest_simulator.py -x -q` (8 tests) | ✓ |

## Self-Check: PASSED

- `backtest/simulator.py` exists ✓ (commit `83a2d81`)
- `tests/test_backtest_simulator.py` exists ✓ (commits `e9ac573`, `83a2d81`)
- `.planning/phases/23-five-year-backtest-validation-gate/deferred-items.md` exists ✓ (commit `83a2d81`)
- Commit `e9ac573` (RED) found in `git log` ✓
- Commit `83a2d81` (GREEN) found in `git log` ✓
