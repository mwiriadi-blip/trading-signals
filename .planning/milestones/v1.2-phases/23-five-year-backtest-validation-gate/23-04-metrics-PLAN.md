---
id: 23-04
title: Wave 1C — backtest/metrics.py (Sharpe / max DD / win rate / expectancy / cum return)
phase: 23
plan: 04
type: execute
wave: 1
depends_on: [23-01]
files_modified:
  - backtest/metrics.py
  - tests/test_backtest_metrics.py
requirements: [BACKTEST-02]
threat_refs: []
autonomous: true
gap_closure: false

must_haves:
  truths:
    - "compute_metrics(equity_curve, trades) returns dict with all 7 D-05 metric fields PLUS sharpe_annualized (planner D-19)"
    - "cumulative_return_pct = (final - initial) / initial * 100 — strict; matches D-16 pass criterion"
    - "sharpe_daily = mean(daily_returns) / std(daily_returns) (raw, ddof=1) per RESEARCH A1 lower bound"
    - "sharpe_annualized = sharpe_daily * sqrt(252) per planner D-19"
    - "max_drawdown_pct uses pandas cummax() peak-to-trough idiom (RESEARCH §Pattern 7)"
    - "win_rate = wins / total_trades (0.0 if no trades)"
    - "expectancy_aud = sum(net_pnl_aud) / total_trades (0.0 if no trades)"
    - "pass = cumulative_return_pct > 100.0 (STRICT greater-than per CONTEXT D-16; equality at exactly 100.0 = FAIL)"
    - "Edge cases handled: zero trades, single bar, all-wins, all-losses, flat equity"
  artifacts:
    - path: "backtest/metrics.py"
      provides: "compute_metrics(equity_curve, trades) public function"
      exports: ["compute_metrics"]
    - path: "tests/test_backtest_metrics.py"
      provides: "TestCumulativeReturn + TestSharpe + TestMaxDrawdown + TestWinRateExpectancy + TestPassCriterion"
  key_links:
    - from: "backtest/metrics.py"
      to: "pandas.Series.cummax()"
      via: "max-drawdown idiom (RESEARCH §Pattern 7)"
      pattern: "cummax"
---

> **Operator confirmation required before /gsd-execute-phase 23:**
> This plan implements planner-derived locked decision D-19 (dual sharpe — emit
> both `sharpe_daily` raw and `sharpe_annualized = sharpe_daily × √252`).
> CONTEXT D-05's metrics field name `sharpe_daily` stays verbatim for backward
> compatibility; `sharpe_annualized` is added alongside it for display.
> Confirm or revise CONTEXT D-05 before execute.

<objective>
Implement `backtest/metrics.py` — pure aggregation of equity curve + trades into the 7-field metrics block per CONTEXT D-05 (extended with `sharpe_annualized` per planner D-19). Replaces Wave 0 NotImplementedError.

Purpose: Drive the BACKTEST-03 pass/fail badge — the single gating metric is `cumulative_return_pct > 100.0`. All other metrics are display-only.
Output: ~80 LOC pure-math module + edge-case-rich test suite (zero trades, single bar, all-wins, all-losses).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md
@.planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md
@.planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md
@CLAUDE.md
@pnl_engine.py
@tests/test_pnl_engine.py

<interfaces>
<!-- Metrics output dict (CONTEXT D-05 extended with planner D-19 sharpe_annualized) -->
{
  "cumulative_return_pct": float,   # signed, 4dp
  "sharpe_daily": float,            # raw mean/std (ddof=1), 4dp
  "sharpe_annualized": float,       # × sqrt(252), 4dp (planner D-19)
  "max_drawdown_pct": float,        # negative, 4dp
  "win_rate": float,                # 0.0 to 1.0, 4dp
  "expectancy_aud": float,          # mean net_pnl_aud per trade, 4dp
  "total_trades": int,
  "pass": bool,                     # cum_return > 100.0 STRICT (D-16)
}

<!-- Pure-math hex tier — same allowlist as simulator.py -->
Allowed imports: math, statistics, typing, pandas, numpy
Forbidden: state_manager, notifier, dashboard, main, requests, datetime, os, json, html, yfinance, pyarrow
</interfaces>
</context>

<threat_model>
No new external trust boundaries. Pure-math hex consumes primitives, returns a dict.
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement backtest/metrics.py</name>
  <read_first>
    - backtest/metrics.py (Wave 0 skeleton)
    - pnl_engine.py — pure-math hex docstring shape + NaN-safety pattern
    - .planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md §Pattern 6 (Sharpe), §Pattern 7 (max DD pandas cummax), §Code Examples §"Metrics computation" (lines 648-686)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"backtest/metrics.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md §D-05, §D-16
  </read_first>
  <behavior>
    - Test 1: cum_return_pct = ((eq[-1] - eq[0]) / eq[0]) * 100
    - Test 2: sharpe_daily uses statistics.stdev (ddof=1)
    - Test 3: sharpe_annualized = sharpe_daily * sqrt(252) — ratio exactly √252 ≈ 15.874
    - Test 4: max_drawdown_pct uses cummax peak-to-trough (NOT min/max)
    - Test 5: pass = True only when cum_return_pct STRICTLY > 100.0 (boundary at 100.0 = False per D-16)
    - Test 6: zero trades → expectancy=0, win_rate=0, total_trades=0
    - Test 7: all-wins → win_rate=1.0
    - Test 8: all-losses → expectancy < 0
  </behavior>
  <action>
    Replace `backtest/metrics.py` Wave 0 stub:

    ```python
    """Phase 23 — pure aggregation: Sharpe / max DD / win rate / expectancy / cum return.

    Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY.
    Forbidden imports (BACKTEST_PATHS_PURE AST guard): state_manager, notifier,
    dashboard, main, requests, datetime, os, json, html, yfinance, pyarrow.
    Allowed: math, statistics, typing, pandas, numpy.

    Pass criterion (CONTEXT D-16): cumulative_return_pct > 100.0 STRICT (greater-than,
    not greater-or-equal). Boundary at exactly 100.0 → pass=False.

    Sharpe convention (RESEARCH A1 + planner D-19): emit BOTH the raw daily ratio
    (sharpe_daily) AND the annualized form (sharpe_annualized = daily × √252). UI
    label corrects D-05's misleading 'sharpe_daily' name to 'Sharpe (annualised)'.
    """
    from __future__ import annotations
    import math
    import statistics
    from typing import Sequence

    import pandas as pd

    _TRADING_DAYS_PER_YEAR = 252
    _PASS_THRESHOLD_PCT = 100.0  # D-16 strict greater-than


    def _cumulative_return_pct(equity_curve: Sequence[float]) -> float:
      """((final - initial) / initial) * 100. Returns 0.0 if initial <= 0 or len < 2."""
      if len(equity_curve) < 2:
        return 0.0
      initial = equity_curve[0]
      final = equity_curve[-1]
      if initial <= 0:
        return 0.0
      return (final / initial - 1.0) * 100.0


    def _daily_returns(equity_curve: Sequence[float]) -> list[float]:
      """Per-bar simple returns; skips bars where prior equity <= 0."""
      out: list[float] = []
      for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev > 0:
          out.append(equity_curve[i] / prev - 1.0)
      return out


    def _sharpe_daily(returns: Sequence[float]) -> float:
      """Raw daily Sharpe = mean / std (ddof=1). Returns 0.0 if undefined."""
      if len(returns) < 2:
        return 0.0
      mean_r = statistics.mean(returns)
      std_r = statistics.stdev(returns)  # ddof=1
      if std_r <= 0 or not math.isfinite(std_r):
        return 0.0
      return mean_r / std_r


    def _max_drawdown_pct(equity_curve: Sequence[float]) -> float:
      """Peak-to-trough drawdown using pandas cummax idiom (RESEARCH §Pattern 7).

      Returns a negative percentage (e.g. -23.10 for a 23.10% drawdown). 0.0 if
      flat or len < 2.
      """
      if len(equity_curve) < 2:
        return 0.0
      eq = pd.Series(equity_curve, dtype='float64')
      rolling_max = eq.cummax()
      # Guard: divide-by-zero if rolling_max ever 0 (initial=0 already screened above)
      drawdown = (eq / rolling_max) - 1.0
      return float(drawdown.min()) * 100.0


    def _win_rate_expectancy(trades: list[dict]) -> tuple[float, float, int]:
      """Returns (win_rate, expectancy_aud, total_trades). Empty list → (0.0, 0.0, 0)."""
      n = len(trades)
      if n == 0:
        return 0.0, 0.0, 0
      pnls = [float(t['net_pnl_aud']) for t in trades]
      wins = sum(1 for p in pnls if p > 0)
      win_rate = wins / n
      expectancy = sum(pnls) / n
      return win_rate, expectancy, n


    def compute_metrics(equity_curve: Sequence[float], trades: list[dict]) -> dict:
      """Phase 23 BACKTEST-02 — aggregate equity curve + closed trades into D-05 metrics.

      Args:
        equity_curve: list of AUD account balances, ascending. equity_curve[0] = initial.
        trades: list of trade dicts (D-05 schema; only `net_pnl_aud` consumed here).

      Returns:
        dict with keys: cumulative_return_pct, sharpe_daily, sharpe_annualized,
        max_drawdown_pct, win_rate, expectancy_aud, total_trades, pass.
      """
      cum_return = _cumulative_return_pct(equity_curve)
      returns = _daily_returns(equity_curve)
      sharpe_d = _sharpe_daily(returns)
      sharpe_a = sharpe_d * math.sqrt(_TRADING_DAYS_PER_YEAR)
      max_dd = _max_drawdown_pct(equity_curve)
      win_rate, expectancy, total_trades = _win_rate_expectancy(trades)

      return {
        'cumulative_return_pct': round(cum_return, 4),
        'sharpe_daily': round(sharpe_d, 4),
        'sharpe_annualized': round(sharpe_a, 4),
        'max_drawdown_pct': round(max_dd, 4),
        'win_rate': round(win_rate, 4),
        'expectancy_aud': round(expectancy, 4),
        'total_trades': total_trades,
        'pass': cum_return > _PASS_THRESHOLD_PCT,  # STRICT (D-16)
      }
    ```
  </action>
  <verify>
    <automated>python -c "from backtest.metrics import compute_metrics; m = compute_metrics([10000.0, 12000.0, 21000.0], [{'net_pnl_aud': 376.50}]); assert m['cumulative_return_pct'] == 110.0; assert m['pass'] is True; assert m['total_trades'] == 1; assert m['sharpe_annualized'] != m['sharpe_daily']; print('ok')" 2>&1 | grep -c '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c '^def compute_metrics' backtest/metrics.py` returns 1
    - `grep -c "'sharpe_daily':" backtest/metrics.py` returns 1
    - `grep -c "'sharpe_annualized':" backtest/metrics.py` returns 1 (planner D-19)
    - `grep -c "cum_return > _PASS_THRESHOLD_PCT" backtest/metrics.py` returns 1 (STRICT > per D-16)
    - `grep -c 'cummax()' backtest/metrics.py` returns 1 (RESEARCH §Pattern 7)
    - `grep -c '^import json\|^import html\|^import os\|^import datetime\|^import yfinance\|^import pyarrow\|^import requests\|^import state_manager\|^from state_manager\|^import notifier\|^from notifier\|^import dashboard\|^from dashboard\|^import main\b\|^from main' backtest/metrics.py` returns 0
    - `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism -x -q` passes (metrics now in _HEX_PATHS_ALL)
  </acceptance_criteria>
  <done>compute_metrics callable; AST guard regression-free.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement tests/test_backtest_metrics.py (5 test classes)</name>
  <read_first>
    - backtest/metrics.py (just-implemented)
    - tests/test_pnl_engine.py — analog (parametrize-grid, edge-case coverage)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"tests/test_backtest_metrics.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-VALIDATION.md
  </read_first>
  <behavior>
    See task 1 behavior. Each test class covers one named metric area.
  </behavior>
  <action>
    Replace Wave 0 skeleton:

    ```python
    """Phase 23 — backtest/metrics.py tests (BACKTEST-02 formulas)."""
    from __future__ import annotations
    import math

    import pytest

    from backtest.metrics import compute_metrics


    class TestCumulativeReturn:
      def test_doubling_account_is_100pct(self):
        m = compute_metrics([10_000.0, 20_000.0], [])
        assert m['cumulative_return_pct'] == 100.0
        assert m['pass'] is False  # STRICT > 100.0 per D-16

      def test_127pct_passes(self):
        m = compute_metrics([10_000.0, 22_745.0], [])
        assert m['cumulative_return_pct'] == pytest.approx(127.45, abs=1e-4)
        assert m['pass'] is True

      def test_loss_negative(self):
        m = compute_metrics([10_000.0, 8_000.0], [])
        assert m['cumulative_return_pct'] == -20.0
        assert m['pass'] is False

      def test_single_bar_zero(self):
        m = compute_metrics([10_000.0], [])
        assert m['cumulative_return_pct'] == 0.0


    class TestSharpe:
      def test_annualized_is_sqrt252_times_daily(self):
        eq = [10_000.0, 10_100.0, 10_050.0, 10_200.0, 10_180.0, 10_300.0]
        m = compute_metrics(eq, [])
        if m['sharpe_daily'] == 0.0:
          pytest.skip('insufficient variance')
        ratio = m['sharpe_annualized'] / m['sharpe_daily']
        assert abs(ratio - math.sqrt(252)) < 1e-4

      def test_zero_variance_returns_zero(self):
        # Flat equity → all returns zero → std=0 → sharpe=0 (guarded)
        m = compute_metrics([10_000.0, 10_000.0, 10_000.0], [])
        assert m['sharpe_daily'] == 0.0
        assert m['sharpe_annualized'] == 0.0

      def test_single_return_returns_zero(self):
        # Only one return point → stdev undefined (needs 2+) → 0
        m = compute_metrics([10_000.0, 11_000.0], [])
        assert m['sharpe_daily'] == 0.0


    class TestMaxDrawdown:
      def test_peak_to_trough(self):
        # Rises to 12k, falls to 9k, recovers to 11k
        # Peak=12k, trough after peak = 9k → DD = (9-12)/12 = -25%
        m = compute_metrics([10_000.0, 12_000.0, 9_000.0, 11_000.0], [])
        assert m['max_drawdown_pct'] == pytest.approx(-25.0, abs=1e-4)

      def test_monotonic_rise_zero_dd(self):
        m = compute_metrics([10_000.0, 11_000.0, 12_000.0, 13_000.0], [])
        assert m['max_drawdown_pct'] == 0.0

      def test_strict_decline(self):
        # Pure decline: peak=initial, trough=final
        m = compute_metrics([10_000.0, 9_000.0, 8_000.0, 7_700.0], [])
        assert m['max_drawdown_pct'] == pytest.approx(-23.0, abs=1e-4)

      def test_dd_uses_cummax_not_global_min_over_max(self):
        """Anti-pattern from RESEARCH §Pattern 7: equity.min()/equity.max() - 1
        is WRONG (worst-point vs global-max). Must use cummax peak-to-trough."""
        # Sequence: 100 → 120 → 80 → 200. Global min=80, max=200.
        # Wrong formula would give 80/200 - 1 = -60%.
        # Correct cummax: peak-to-trough is 120 → 80 = -33.33%.
        m = compute_metrics([100.0, 120.0, 80.0, 200.0], [])
        assert m['max_drawdown_pct'] == pytest.approx(-33.3333, abs=1e-3)


    class TestWinRateExpectancy:
      def test_zero_trades(self):
        m = compute_metrics([10_000.0, 11_000.0], [])
        assert m['total_trades'] == 0
        assert m['win_rate'] == 0.0
        assert m['expectancy_aud'] == 0.0

      def test_all_wins(self):
        trades = [{'net_pnl_aud': 100.0}, {'net_pnl_aud': 200.0}, {'net_pnl_aud': 50.0}]
        m = compute_metrics([10_000.0, 10_350.0], trades)
        assert m['total_trades'] == 3
        assert m['win_rate'] == 1.0
        assert m['expectancy_aud'] == pytest.approx(116.6667, abs=1e-3)

      def test_all_losses(self):
        trades = [{'net_pnl_aud': -100.0}, {'net_pnl_aud': -50.0}]
        m = compute_metrics([10_000.0, 9_850.0], trades)
        assert m['win_rate'] == 0.0
        assert m['expectancy_aud'] == -75.0

      def test_mixed_50pct(self):
        trades = [{'net_pnl_aud': 100.0}, {'net_pnl_aud': -100.0},
                  {'net_pnl_aud': 200.0}, {'net_pnl_aud': -50.0}]
        m = compute_metrics([10_000.0, 10_150.0], trades)
        assert m['win_rate'] == 0.5
        assert m['expectancy_aud'] == pytest.approx(37.5, abs=1e-4)


    class TestPassCriterion:
      def test_strictly_above_100_passes(self):
        m = compute_metrics([10_000.0, 20_001.0], [])
        assert m['cumulative_return_pct'] > 100.0
        assert m['pass'] is True

      def test_exactly_100_fails(self):
        """D-16 STRICT greater-than: equality at exactly 100.0 = FAIL."""
        m = compute_metrics([10_000.0, 20_000.0], [])
        assert m['cumulative_return_pct'] == 100.0
        assert m['pass'] is False

      def test_below_100_fails(self):
        m = compute_metrics([10_000.0, 19_999.0], [])
        assert m['cumulative_return_pct'] < 100.0
        assert m['pass'] is False
    ```
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_backtest_metrics.py -x -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `.venv/bin/pytest tests/test_backtest_metrics.py -x -q` all green
    - `pytest tests/test_backtest_metrics.py::TestSharpe::test_annualized_is_sqrt252_times_daily -x` passes
    - `pytest tests/test_backtest_metrics.py::TestMaxDrawdown::test_dd_uses_cummax_not_global_min_over_max -x` passes
    - `pytest tests/test_backtest_metrics.py::TestPassCriterion::test_exactly_100_fails -x` passes (D-16 boundary check)
    - Full suite regression-free
  </acceptance_criteria>
  <done>All 5 test classes green; pass-criterion boundary at 100.0 is strict per D-16.</done>
</task>

</tasks>

<verification>
1. `python -c "from backtest.metrics import compute_metrics; m = compute_metrics([10000.0, 22745.0], []); assert m['pass']; print('ok')"` prints `ok`
2. `.venv/bin/pytest tests/test_backtest_metrics.py -x -q` passes
3. `.venv/bin/pytest -x -q` exits 0 (no regression)
</verification>

<success_criteria>
- compute_metrics returns dict matching D-05 schema + sharpe_annualized
- All 5 test classes green
- Pass criterion strictly enforces > 100.0
- Max DD uses cummax peak-to-trough (not min/max anti-pattern)
- Sharpe annualized = daily × √252
</success_criteria>

<output>
Create `.planning/phases/23-five-year-backtest-validation-gate/23-04-SUMMARY.md` with:
- compute_metrics signature finalized
- Pass criterion D-16 boundary verified
- Sharpe annualization √252 ratio verified
- Test count + pass status
</output>
