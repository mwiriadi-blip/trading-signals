"""Phase 23 — pure aggregation: Sharpe / max DD / win rate / expectancy / cum return.

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY.
Forbidden imports (BACKTEST_PATHS_PURE AST guard): same as simulator.py.
Allowed: math, statistics, typing, pandas, numpy.

Pass criterion (CONTEXT D-16): cumulative_return_pct > 100.0 STRICT.
"""
from __future__ import annotations


def compute_metrics(equity_curve: list[float], trades: list[dict]) -> dict:
  raise NotImplementedError('Phase 23 Wave 1 Plan 04 — to be implemented')
