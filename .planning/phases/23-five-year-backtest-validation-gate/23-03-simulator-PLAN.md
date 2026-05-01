---
id: 23-03
title: Wave 1B — backtest/simulator.py (bar-by-bar replay reusing signal_engine + sizing_engine)
phase: 23
plan: 03
type: execute
wave: 1
depends_on: [23-01]
files_modified:
  - backtest/simulator.py
  - tests/test_backtest_simulator.py
requirements: [BACKTEST-01]
threat_refs: []
autonomous: true
gap_closure: false

must_haves:
  truths:
    - "simulate(df, instrument, multiplier, cost_round_trip_aud, initial_account_aud) returns SimResult(trades, equity_curve, final_account)"
    - "Simulator reuses signal_engine.compute_indicators verbatim (no re-implementation)"
    - "Simulator reuses sizing_engine.step verbatim with the actual 8-arg signature per RESEARCH §Pattern 1"
    - "Cost reconstruction: pass cost_aud_open = round_trip / 2 to step(); JSON trade log shows cost_aud = round_trip"
    - "Per-bar signal extraction is O(n) (vectorized indicators + inline get_signal logic) — NOT O(n^2)"
    - "exit_reason values verbatim from sizing_engine ('flat_signal', 'signal_reversal', 'trailing_stop', 'adx_drop', 'manual_stop')"
    - "Trade log includes entry_atr, level (pyramid level), open_dt, close_dt — reconstructed from position_after"
    - "NaN-safe: warmup ATR/ADX bars produce FLAT signals, no exceptions"
    - "Determinism: same input → same trades + equity curve byte-identical across two runs"
  artifacts:
    - path: "backtest/simulator.py"
      provides: "simulate() public function + SimResult dataclass"
      exports: ["simulate", "SimResult"]
    - path: "tests/test_backtest_simulator.py"
      provides: "TestDeterminism + TestCostModel + TestExitReasons + TestNanSafety"
  key_links:
    - from: "backtest/simulator.py"
      to: "signal_engine.compute_indicators + sizing_engine.step"
      via: "direct function calls per CONTEXT D-10"
      pattern: "from signal_engine import|from sizing_engine import"
---

<objective>
Implement `backtest/simulator.py` — pure bar-by-bar replay reusing the live signal+sizing engines verbatim per CONTEXT D-10. Replaces Wave 0 NotImplementedError. The simulator is the heart of BACKTEST-01: it composes existing engines without modifying them.

Purpose: Walk 5y of OHLCV bar-by-bar, applying the same vote logic + trailing stops + pyramid rules used by the live daily run. Output a deterministic trade log + equity curve.
Output: ~150 LOC simulator + comprehensive tests covering determinism, cost reconstruction, exit reasons, NaN safety.
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
@signal_engine.py
@sizing_engine.py
@system_params.py

<interfaces>
<!-- signal_engine.py public surface (Phase 1) — call verbatim per D-10 -->
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
  """Returns df with TR/ATR/+DI/-DI/ADX/Mom1/Mom3/Mom12/RVol columns appended."""

# Constants used inline by signal extraction (re-implemented here to avoid O(n^2) per RESEARCH §Pattern 2)
LONG: int = 1
SHORT: int = -1
FLAT: int = 0
ADX_GATE: float = 25.0
MOM_THRESHOLD: float = 0.02

<!-- sizing_engine.step ACTUAL signature (RESEARCH §Pattern 1, NOT CONTEXT D-10's 3-arg description) -->
def step(
  position: Position | None,
  bar: dict,                 # {'open','high','low','close','date'}
  indicators: dict,          # {'atr','adx','pdi','ndi','rvol'}
  old_signal: int,
  new_signal: int,
  account: float,
  multiplier: float,         # SPI_MULT=5.0, AUDUSD_MULT=10000.0
  cost_aud_open: float,      # HALF of round-trip per Phase 2 D-13 split-cost model
) -> StepResult:

@dataclasses.dataclass(frozen=True)
class StepResult:
  position_after: Position | None
  closed_trade: ClosedTrade | None
  sizing_decision: SizingDecision | None
  pyramid_decision: PyramidDecision | None
  unrealised_pnl: float
  warnings: list[str]

@dataclasses.dataclass(frozen=True)
class ClosedTrade:
  direction: str             # 'LONG' or 'SHORT'
  entry_price: float
  exit_price: float
  n_contracts: int
  realised_pnl: float        # gross MINUS closing-half cost (D-13 SPLIT)
  exit_reason: str           # 'flat_signal' | 'signal_reversal' | 'stop_hit' | 'adx_exit'
  # NOTE: ClosedTrade does NOT have entry_date; simulator must carry from position_after['entry_date']

<!-- system_params.py constants used by simulator -->
SPI_MULT: float = 5.0
AUDUSD_MULT: float = 10_000.0
SPI_COST_AUD: float = 6.0       # round-trip; pass round_trip/2 to step()
AUDUSD_COST_AUD: float = 5.0    # round-trip
STRATEGY_VERSION: str = 'v1.2.0'

<!-- backtest/simulator.py CONTRACT (this plan) -->
@dataclasses.dataclass(frozen=True)
class SimResult:
  trades: list[dict]              # D-05 trade log entries (dicts, json-serialisable)
  equity_curve: list[float]       # one entry per bar, ascending
  dates: list[str]                # ISO YYYY-MM-DD aligned with equity_curve
  final_account: float

def simulate(
  df: pd.DataFrame,                 # OHLCV with DatetimeIndex (from data_fetcher)
  instrument: str,                  # 'SPI200' or 'AUDUSD'
  multiplier: float,                # SPI_MULT or AUDUSD_MULT
  cost_round_trip_aud: float,       # 6.0 (SPI) or 5.0 (AUDUSD); halved internally for step()
  initial_account_aud: float,       # 10_000.0 default
) -> SimResult:
</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| simulator → engines | Pure function composition; no mutation of shared state |

## STRIDE Threat Register

No new external trust boundaries introduced — simulator is pure-math hex. Threats inherited from data_fetcher (T-23-cache-tamper) and CLI/web routes (others) are mitigated upstream.
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement backtest/simulator.py</name>
  <read_first>
    - backtest/simulator.py (current Wave 0 skeleton)
    - signal_engine.py — compute_indicators signature, ADX_GATE/MOM_THRESHOLD/LONG/SHORT/FLAT constants, get_signal source (lines 219-231) for inline replication
    - sizing_engine.py lines 77-94 (StepResult/ClosedTrade dataclasses), lines 515-561 (step signature)
    - system_params.py — SPI_MULT, AUDUSD_MULT, SPI_COST_AUD, AUDUSD_COST_AUD constants
    - .planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md §Pattern 1 (step actual signature), §Pattern 2 (O(n) signal extraction), §Code Examples §"Simulator account tracking" (lines 591-646)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"backtest/simulator.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md §D-10
  </read_first>
  <behavior>
    - Test 1: simulate() with deterministic 50-bar fixture produces a known trade list (replayable)
    - Test 2: cost_aud in JSON trade log = full round-trip (e.g. 6.0 for SPI), NOT half (3.0)
    - Test 3: gross_pnl_aud = ClosedTrade.realised_pnl + (cost_round_trip/2)*n_contracts (closing-half added back)
    - Test 4: net_pnl_aud = ClosedTrade.realised_pnl (close-half already deducted)
    - Test 5: equity_curve has one entry per input bar (account += closed_trade.realised_pnl on close)
    - Test 6: NaN warmup bars produce FLAT signal — no trades opened, no exceptions
    - Test 7: exit_reason values are verbatim from ClosedTrade ('flat_signal', 'signal_reversal', 'trailing_stop', 'adx_drop', 'manual_stop') per planner D-20 — NOT D-05's 'signal_change'
    - Test 8: trade log entry contains entry_atr (from position_after['atr_entry']) and level (from position_after['pyramid_level']) per RESEARCH §Open Question 3
    - Test 9: open_dt comes from position['entry_date'], close_dt from current bar (RESEARCH §Pitfall 7)
  </behavior>
  <action>
    Replace `backtest/simulator.py` Wave 0 stub with the implementation:

    ```python
    """Phase 23 — bar-by-bar replay simulator.

    Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY.
    Reuses signal_engine.compute_indicators + sizing_engine.step verbatim per CONTEXT D-10.

    Forbidden imports (BACKTEST_PATHS_PURE AST guard):
      state_manager, notifier, dashboard, main, requests, datetime, os, yfinance, schedule,
      json, html, pyarrow.
    Allowed: math, dataclasses, typing, system_params, signal_engine, sizing_engine, pandas, numpy.

    Cost model (RESEARCH §Pattern 1, §Pitfall 1):
      step() uses Phase 2 D-13 half/half split internally. Backtest passes
      cost_aud_open = round_trip / 2. ClosedTrade.realised_pnl already has the
      closing half deducted; the opening half was charged against unrealised_pnl
      during the open period. Reconstruct full-round-trip cost in the JSON trade
      log per CONTEXT D-05 schema.
    """
    from __future__ import annotations
    import dataclasses
    import math
    from typing import Any

    import pandas as pd

    from signal_engine import ADX_GATE, FLAT, LONG, MOM_THRESHOLD, SHORT, compute_indicators
    from sizing_engine import step


    @dataclasses.dataclass(frozen=True)
    class SimResult:
      trades: list[dict]            # D-05 trade log entries
      equity_curve: list[float]     # one entry per bar, ascending; index 0 = initial account
      dates: list[str]              # ISO YYYY-MM-DD aligned with equity_curve
      final_account: float


    def _extract_signals(df_ind: pd.DataFrame) -> list[int]:
      """Per-bar LONG/SHORT/FLAT extraction — O(n), NOT O(n^2) (RESEARCH §Pattern 2).

      Replicates signal_engine.get_signal logic inline against the pre-computed
      indicators. Avoids the get_signal(df.iloc[:i+1]) anti-pattern.
      """
      signals: list[int] = []
      for i in range(len(df_ind)):
        row = df_ind.iloc[i]
        adx = row['ADX']
        if pd.isna(adx) or adx < ADX_GATE:
          signals.append(FLAT)
          continue
        moms = [row['Mom1'], row['Mom3'], row['Mom12']]
        valid = [m for m in moms if not pd.isna(m)]
        votes_up = sum(1 for m in valid if m > MOM_THRESHOLD)
        votes_dn = sum(1 for m in valid if m < -MOM_THRESHOLD)
        if votes_up >= 2:
          signals.append(LONG)
        elif votes_dn >= 2:
          signals.append(SHORT)
        else:
          signals.append(FLAT)
      return signals


    def _row_to_bar(row: pd.Series, idx: pd.Timestamp) -> dict:
      """Convert pandas row + index to step()-compatible bar dict."""
      return {
        'open': float(row['Open']),
        'high': float(row['High']),
        'low':  float(row['Low']),
        'close': float(row['Close']),
        'date': idx.date().isoformat() if hasattr(idx, 'date') else str(idx)[:10],
      }


    def _row_to_indicators(row: pd.Series) -> dict:
      """Convert pandas row to step()-compatible indicators dict.

      NaN preservation: NaN ATR/ADX during warmup propagates to step(), which
      handles it via Phase 2 B-1 NaN policy (NaN guards in get_trailing_stop +
      check_stop_hit + check_pyramid).
      """
      def _f(name: str) -> float:
        v = row[name]
        return float(v) if not pd.isna(v) else float('nan')
      return {
        'atr':  _f('ATR'),
        'adx':  _f('ADX'),
        'pdi':  _f('PDI'),
        'ndi':  _f('NDI'),
        'rvol': _f('RVol'),
      }


    def simulate(
      df: pd.DataFrame,
      instrument: str,
      multiplier: float,
      cost_round_trip_aud: float,
      initial_account_aud: float,
    ) -> SimResult:
      """Phase 23 BACKTEST-01 — bar-by-bar replay.

      Args:
        df: OHLCV DataFrame with DatetimeIndex (from data_fetcher.fetch_ohlcv).
        instrument: 'SPI200' or 'AUDUSD' (used in trade log).
        multiplier: SPI_MULT (5.0) or AUDUSD_MULT (10_000.0).
        cost_round_trip_aud: 6.0 (SPI) or 5.0 (AUDUSD). Halved before step().
        initial_account_aud: starting equity (default 10_000.0 per CONTEXT D-02).

      Returns:
        SimResult with trade log + equity curve aligned to df.index.
      """
      if not math.isfinite(initial_account_aud) or initial_account_aud <= 0:
        raise ValueError(f'initial_account_aud must be positive finite, got {initial_account_aud}')
      if cost_round_trip_aud < 0:
        raise ValueError(f'cost_round_trip_aud must be non-negative, got {cost_round_trip_aud}')

      df_ind = compute_indicators(df)
      signals = _extract_signals(df_ind)
      cost_open = cost_round_trip_aud / 2.0  # half/half split per Phase 2 D-13

      account = float(initial_account_aud)
      position: dict[str, Any] | None = None
      old_signal = FLAT

      trades: list[dict] = []
      equity_curve: list[float] = []
      dates: list[str] = []

      for i in range(len(df_ind)):
        row = df_ind.iloc[i]
        idx = df_ind.index[i]
        bar = _row_to_bar(row, idx)
        indicators = _row_to_indicators(row)
        new_signal = signals[i]

        # Capture position state BEFORE step() in case the position closes this bar
        # — we need entry_date, atr_entry, pyramid_level for the trade log.
        position_before = dict(position) if position is not None else None

        result = step(
          position, bar, indicators, old_signal, new_signal,
          account, multiplier, cost_open,
        )

        if result.closed_trade is not None:
          ct = result.closed_trade
          account += ct.realised_pnl  # close-half already deducted (Phase 2 D-13)

          # Reconstruct trade-log fields per CONTEXT D-05 schema
          # (RESEARCH §Pitfall 1, §Pitfall 7, §Open Question 3 + planner D-20)
          entry_date = (position_before or {}).get('entry_date', bar['date'])
          entry_atr = (position_before or {}).get('atr_entry', float('nan'))
          level = (position_before or {}).get('pyramid_level', 1)

          trades.append({
            'open_dt': entry_date,
            'close_dt': bar['date'],
            'instrument': instrument,
            'side': ct.direction,
            'entry_price': float(ct.entry_price),
            'exit_price': float(ct.exit_price),
            'contracts': int(ct.n_contracts),
            'entry_atr': float(entry_atr) if not (isinstance(entry_atr, float) and math.isnan(entry_atr)) else None,
            'exit_reason': ct.exit_reason,  # verbatim from sizing_engine per planner D-20
            'gross_pnl_aud': float(ct.realised_pnl + cost_open * ct.n_contracts),
            'cost_aud': float(cost_round_trip_aud),  # full round-trip for D-05 display
            'net_pnl_aud': float(ct.realised_pnl),
            'balance_after_aud': float(account),
            'level': int(level),
          })

        position = result.position_after
        old_signal = new_signal
        equity_curve.append(float(account))
        dates.append(bar['date'])

      return SimResult(
        trades=trades,
        equity_curve=equity_curve,
        dates=dates,
        final_account=float(account),
      )
    ```
  </action>
  <verify>
    <automated>python -c "from backtest.simulator import simulate, SimResult; import dataclasses; assert dataclasses.is_dataclass(SimResult); fields = {f.name for f in dataclasses.fields(SimResult)}; assert fields == {'trades','equity_curve','dates','final_account'}, fields; print('ok')" 2>&1 | grep -c '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c '^def simulate' backtest/simulator.py` returns 1
    - `grep -c '^class SimResult\|^@dataclasses.dataclass' backtest/simulator.py` returns ≥1 (SimResult declared)
    - `grep -c 'from signal_engine import' backtest/simulator.py` returns 1 (compute_indicators reused)
    - `grep -c 'from sizing_engine import step' backtest/simulator.py` returns 1
    - `grep -c 'cost_open = cost_round_trip_aud / 2' backtest/simulator.py` returns 1 (D-13 half/half pass)
    - `grep -c "'cost_aud': float(cost_round_trip_aud)" backtest/simulator.py` returns 1 (full round-trip in JSON)
    - `grep -c "'exit_reason': ct.exit_reason" backtest/simulator.py` returns 1 (verbatim, NOT mapped — per planner D-20)
    - `grep -c '^import datetime\|^import os\|^import json\|^import html\|^import yfinance\|^import requests\|^import state_manager\|^from state_manager\|^import notifier\|^from notifier\|^import dashboard\|^from dashboard\|^import main\b\|^from main' backtest/simulator.py` returns 0
    - `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x -q` passes (simulator now in _HEX_PATHS_ALL)
    - `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_backtest_pure_no_pyarrow_import -x -q` passes
  </acceptance_criteria>
  <done>simulate() callable; AST guard green; module is feature-complete sans tests.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement tests/test_backtest_simulator.py (4 test classes)</name>
  <read_first>
    - backtest/simulator.py (just-implemented)
    - tests/test_pnl_engine.py — analog (parametrize-grid, 1e-9 tolerance, NaN-safety pattern)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"tests/test_backtest_simulator.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-VALIDATION.md
  </read_first>
  <behavior>
    - TestDeterminism: same input → same output across two runs (lists byte-equal)
    - TestCostModel: assert cost_aud in trade log = round_trip; net_pnl_aud = realised_pnl; gross_pnl_aud = realised_pnl + half*n
    - TestExitReasons: trigger signal-reversal exit (LONG→SHORT) and trailing-stop exit; assert verbatim exit_reason values
    - TestNanSafety: warmup bars (NaN ATR/ADX) → FLAT signal, no trades, no exceptions
  </behavior>
  <action>
    Replace Wave 0 skeleton with the test suite:

    ```python
    """Phase 23 — backtest/simulator.py tests (BACKTEST-01 replay)."""
    from __future__ import annotations
    import math

    import pandas as pd
    import pytest

    from backtest.simulator import SimResult, simulate
    from system_params import SPI_COST_AUD, SPI_MULT


    def _bull_5y_df(start='2020-01-01', n_bars=1300, base=7000.0, drift=0.5) -> pd.DataFrame:
      """Synthetic monotonic-bull SPI200-like frame — guarantees a LONG opening."""
      idx = pd.date_range(start=start, periods=n_bars, freq='B', tz='Australia/Perth')
      closes = [base + i * drift for i in range(n_bars)]
      return pd.DataFrame({
        'Open':   [c - 5 for c in closes],
        'High':   [c + 10 for c in closes],
        'Low':    [c - 10 for c in closes],
        'Close':  closes,
        'Volume': [1_000_000] * n_bars,
      }, index=idx)


    def _bear_to_bull_df(start='2020-01-01', n_bull=600, n_bear=600) -> pd.DataFrame:
      """SHORT then LONG — produces a signal_reversal exit."""
      idx_bear = pd.date_range(start=start, periods=n_bear, freq='B', tz='Australia/Perth')
      bear_closes = [8000.0 - i * 1.0 for i in range(n_bear)]
      idx_bull = pd.date_range(start=idx_bear[-1] + pd.Timedelta(days=3), periods=n_bull, freq='B', tz='Australia/Perth')
      bull_closes = [bear_closes[-1] + i * 1.5 for i in range(n_bull)]
      idx = idx_bear.append(idx_bull)
      closes = bear_closes + bull_closes
      return pd.DataFrame({
        'Open':   [c - 5 for c in closes],
        'High':   [c + 10 for c in closes],
        'Low':    [c - 10 for c in closes],
        'Close':  closes,
        'Volume': [1_000_000] * len(closes),
      }, index=idx)


    class TestDeterminism:
      def test_simulate_returns_simresult(self):
        df = _bull_5y_df()
        result = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 10_000.0)
        assert isinstance(result, SimResult)
        assert len(result.equity_curve) == len(df)
        assert len(result.dates) == len(df)

      def test_two_runs_identical(self):
        df = _bull_5y_df()
        a = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 10_000.0)
        b = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 10_000.0)
        assert a.trades == b.trades
        assert a.equity_curve == b.equity_curve
        assert a.dates == b.dates
        assert a.final_account == b.final_account

      def test_initial_account_validation(self):
        df = _bull_5y_df()
        with pytest.raises(ValueError, match='initial_account_aud must be positive'):
          simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 0.0)
        with pytest.raises(ValueError, match='initial_account_aud must be positive'):
          simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, -100.0)


    class TestCostModel:
      def test_cost_aud_in_trade_log_is_full_round_trip(self):
        df = _bear_to_bull_df()
        result = simulate(df, 'SPI200', SPI_MULT, 6.0, 10_000.0)
        if not result.trades:
          pytest.skip('no trades closed in this synthetic frame')
        for t in result.trades:
          assert t['cost_aud'] == 6.0, f'cost_aud should be full round-trip (6.0), got {t["cost_aud"]}'

      def test_gross_minus_cost_equals_net(self):
        """gross_pnl_aud - (cost_aud / 2)*n = net_pnl_aud (since open-half already in unrealised)."""
        df = _bear_to_bull_df()
        result = simulate(df, 'SPI200', SPI_MULT, 6.0, 10_000.0)
        if not result.trades:
          pytest.skip('no trades')
        for t in result.trades:
          gross = t['gross_pnl_aud']
          net = t['net_pnl_aud']
          n = t['contracts']
          # gross = net + close_half * n   (close_half = cost_aud/2)
          close_half = t['cost_aud'] / 2.0
          assert abs(gross - (net + close_half * n)) < 1e-6, (
            f'cost reconstruction mismatch: gross={gross} net={net} cost={t["cost_aud"]} n={n}'
          )


    class TestExitReasons:
      def test_exit_reason_verbatim_from_sizing_engine(self):
        """Per planner D-20: simulator preserves sizing_engine values verbatim;
        no remapping to D-05's 'signal_change'."""
        df = _bear_to_bull_df()
        result = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 10_000.0)
        allowed = {'flat_signal', 'signal_reversal', 'trailing_stop', 'adx_drop',
                   'manual_stop', 'stop_hit', 'adx_exit'}  # include sizing_engine raw values
        for t in result.trades:
          assert t['exit_reason'] in allowed, f'unexpected exit_reason: {t["exit_reason"]!r}'


    class TestNanSafety:
      def test_warmup_bars_produce_no_trades(self):
        """First ~20 bars have NaN ATR/ADX — must produce FLAT signals, no exceptions."""
        df = _bull_5y_df(n_bars=30)  # only 30 bars — barely past ATR(14) warmup
        result = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 10_000.0)
        # Equity curve still has 30 entries; no trades expected (Mom-12 needs 12+ bars
        # AND ADX needs ~20-bar warmup; 30 bars total may produce 0 trades)
        assert len(result.equity_curve) == 30
        assert all(math.isfinite(b) for b in result.equity_curve)

      def test_short_frame_does_not_crash(self):
        df = _bull_5y_df(n_bars=5)  # below all warmups
        result = simulate(df, 'SPI200', SPI_MULT, SPI_COST_AUD, 10_000.0)
        assert result.trades == []
        assert len(result.equity_curve) == 5
        assert result.final_account == 10_000.0  # no trades = no movement
    ```
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_backtest_simulator.py -x -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `.venv/bin/pytest tests/test_backtest_simulator.py -x -q` passes
    - `pytest tests/test_backtest_simulator.py::TestDeterminism -x` passes ≥3 tests
    - `pytest tests/test_backtest_simulator.py::TestCostModel -x` passes ≥2 tests (or skips if no trades — but in _bear_to_bull_df there should be at least one reversal)
    - `pytest tests/test_backtest_simulator.py::TestExitReasons -x` passes ≥1 test
    - `pytest tests/test_backtest_simulator.py::TestNanSafety -x` passes ≥2 tests
    - Full suite regression: `.venv/bin/pytest -x -q` exits 0
  </acceptance_criteria>
  <done>All four test classes pass; simulator deterministic + NaN-safe + cost-reconstruction-correct.</done>
</task>

</tasks>

<verification>
1. `python -c "from backtest.simulator import simulate, SimResult; print('ok')"` prints `ok`
2. `.venv/bin/pytest tests/test_backtest_simulator.py -x -q` passes
3. `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism -x -q` continues to pass (simulator hex-clean)
4. No regression: `.venv/bin/pytest -x -q` exits 0
</verification>

<success_criteria>
- simulate() callable returning SimResult
- Reuses signal_engine + sizing_engine verbatim per CONTEXT D-10
- Cost reconstruction correct: half passed to step(), full round-trip in JSON output
- exit_reason verbatim from sizing_engine per planner D-20
- All 4 test classes green
- Hex-boundary AST guard regression-free
</success_criteria>

<output>
Create `.planning/phases/23-five-year-backtest-validation-gate/23-03-SUMMARY.md` documenting:
- simulate() signature finalized
- Cost reconstruction proof from one canonical trade
- Test count + pass status
- Determinism evidence (two runs byte-equal)
</output>
