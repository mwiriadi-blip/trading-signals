'''Phase 20 D-10/D-11: pure-math alert engine.

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY alongside signal_engine,
sizing_engine, pnl_engine. NO I/O. NO datetime / os / requests.
Imports stdlib only (math + typing).

Forbidden imports (enforced by tests/test_signal_engine.py
FORBIDDEN_MODULES_STDLIB_ONLY AST guard): state_manager, notifier,
dashboard, main, requests, urllib, http, schedule, dotenv, pytz,
yfinance, datetime, os, sys, subprocess, socket, time, json, pathlib, io,
numpy, pandas.

Functions:
  compute_alert_state(side, today_low, today_high, today_close,
                      stop_price, atr) -> str
  compute_atr_distance(today_close, stop_price, atr) -> float
'''
from __future__ import annotations

import math
from typing import Literal


def compute_alert_state(
  side: str,
  today_low: float,
  today_high: float,
  today_close: float,
  stop_price: float,
  atr: float,
) -> str:
  '''D-10: returns HIT / APPROACHING / CLEAR.

  HIT precedence (REQ-01 ordering -- checked BEFORE APPROACHING):
    LONG:  today_low  <= stop_price
    SHORT: today_high >= stop_price

  APPROACHING:
    abs(today_close - stop_price) <= 0.5 * atr

  CLEAR otherwise.

  NaN handling (Phase 17 D-06 NaN policy + RESEARCH §Pattern 5):
    any NaN input returns CLEAR (no false-positive email).
    atr <= 0 returns CLEAR (divide-by-zero guard).
  '''
  # NaN guard FIRST -- before any arithmetic (per project LEARNINGS Phase 17 D-06).
  if any(math.isnan(v) for v in (today_low, today_high, today_close, stop_price, atr)):
    return 'CLEAR'
  if atr <= 0:
    return 'CLEAR'
  # HIT precedence -- checked BEFORE APPROACHING per D-10.
  if side == 'LONG' and today_low <= stop_price:
    return 'HIT'
  if side == 'SHORT' and today_high >= stop_price:
    return 'HIT'
  if abs(today_close - stop_price) <= 0.5 * atr:
    return 'APPROACHING'
  return 'CLEAR'


def compute_atr_distance(today_close: float, stop_price: float, atr: float) -> float:
  '''D-10: returns abs(today_close - stop_price) / atr.

  Used for email body distance text. Returns float('nan') if atr <= 0 or
  any NaN input (caller-side render treats NaN as 'distance unknown').
  '''
  if any(math.isnan(v) for v in (today_close, stop_price, atr)):
    return float('nan')
  if atr <= 0:
    return float('nan')
  return abs(today_close - stop_price) / atr
