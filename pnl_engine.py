'''Pnl Engine — pure-math paper-trade P&L (Phase 19 D-11).

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY. Imports math + typing only.
Multiplier and round-trip cost are explicit float args (per Phase 2 D-17 anti-coupling
rule; Phase 19 planner D-19). No system_params imports — caller-side adapters supply
the constants.

Forbidden imports (enforced by tests/test_signal_engine.py::TestDeterminism):
  state_manager, notifier, dashboard, main, requests, datetime, os, numpy, pandas,
  yfinance, schedule, dotenv.

Functions:
  compute_unrealised_pnl(side, entry_price, last_close, contracts, multiplier,
                         entry_cost_aud) -> float
  compute_realised_pnl(side, entry_price, exit_price, contracts, multiplier,
                       round_trip_cost_aud) -> float
'''
import math  # noqa: F401 — used for NaN propagation detection by callers


def compute_unrealised_pnl(
  side: str,
  entry_price: float,
  last_close: float,
  contracts: float,
  multiplier: float,
  entry_cost_aud: float,
) -> float:
  '''D-11 unrealised. LONG: (last_close - entry) * contracts * multiplier - entry_cost_aud.
  SHORT: (entry - last_close) * contracts * multiplier - entry_cost_aud.
  NaN last_close propagates naturally; caller checks math.isnan on the result.
  '''
  if side == 'LONG':
    gross = (last_close - entry_price) * contracts * multiplier
  else:  # SHORT
    gross = (entry_price - last_close) * contracts * multiplier
  return gross - entry_cost_aud


def compute_realised_pnl(
  side: str,
  entry_price: float,
  exit_price: float,
  contracts: float,
  multiplier: float,
  round_trip_cost_aud: float,
) -> float:
  '''D-11 realised. Full round-trip cost deducted at close (both halves applied here,
  per Phase 19 D-11 — diverges from sizing_engine which splits across record_trade D-14).
  '''
  if side == 'LONG':
    gross = (exit_price - entry_price) * contracts * multiplier
  else:  # SHORT
    gross = (entry_price - exit_price) * contracts * multiplier
  return gross - round_trip_cost_aud
