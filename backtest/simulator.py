"""Phase 23 — bar-by-bar replay simulator.

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY.
Reuses signal_engine.compute_indicators + sizing_engine.step verbatim per CONTEXT D-10.

Forbidden imports (enforced by tests/test_signal_engine.py BACKTEST_PATHS_PURE AST guard):
  state_manager, notifier, dashboard, main, requests, datetime, os, yfinance, schedule.
Allowed: math, typing, system_params, signal_engine, sizing_engine, pandas, numpy.
"""
from __future__ import annotations


def simulate(df, instrument: str, multiplier: float, cost_round_trip_aud: float,
             initial_account_aud: float):
  raise NotImplementedError('Phase 23 Wave 1 Plan 03 — to be implemented')
