'''System-wide trading parameters — shared constants and Position TypedDict.

All policy constants for Phase 1 indicator logic and Phase 2 sizing/exit/pyramid
logic live here. Pure module: no I/O, no network, no clock reads.

Architecture (hexagonal-lite, CLAUDE.md): shared by signal_engine.py (Phase 1
indicator periods + vote thresholds), sizing_engine.py (Phase 2 sizing/exit
constants), and state_manager.py (Phase 3 I/O hex). Must NOT import notifier,
dashboard, main, requests, datetime, os, or any I/O/network module.

D-01: Phase 1 policy constants migrated from signal_engine.py (ADX_GATE,
MOM_THRESHOLD, periods). LONG/SHORT/FLAT signal encoding stays in signal_engine.py.
D-08: Position TypedDict lives here so Phase 3 state.json round-trips directly.
D-11: SPI mini $5/pt, $6 AUD RT (operator confirmed at /gsd-discuss-phase 2).
D-XX (Phase 3): INITIAL_ACCOUNT, MAX_WARNINGS, STATE_SCHEMA_VERSION, STATE_FILE added.
'''
from typing import Literal, TypedDict

# =========================================================================
# Phase 1 constants — migrated from signal_engine.py (D-01)
# =========================================================================

# --- Indicator periods (locked) ---
ATR_PERIOD: int = 14
ADX_PERIOD: int = 20
MOM_PERIODS: tuple[int, int, int] = (21, 63, 252)
RVOL_PERIOD: int = 20
ANNUALISATION_FACTOR: int = 252

# --- Vote thresholds (SPEC.md §3) ---
ADX_GATE: float = 25.0          # entry gate; FLAT if ADX < ADX_GATE
MOM_THRESHOLD: float = 0.02     # |mom| > threshold counts as a vote

# =========================================================================
# Phase 2 constants — sizing, exits, pyramid (D-01, SPEC.md §5/7/8)
# =========================================================================

# --- Position sizing (SIZE-01..04) ---
RISK_PCT_LONG: float = 0.01      # 1.0% account risk per LONG entry
RISK_PCT_SHORT: float = 0.005    # 0.5% account risk per SHORT entry

# --- Trailing stop multipliers (EXIT-06/07, SIZE-02) ---
TRAIL_MULT_LONG: float = 3.0    # LONG stop = peak - 3 * atr_entry
TRAIL_MULT_SHORT: float = 2.0   # SHORT stop = trough + 2 * atr_entry

# --- Vol-scaling clip (SIZE-03) ---
VOL_SCALE_TARGET: float = 0.12
VOL_SCALE_MIN: float = 0.3
VOL_SCALE_MAX: float = 2.0

# --- Pyramid triggers (PYRA-01..04, D-12) ---
PYRAMID_TRIGGERS: tuple[float, float] = (1.0, 2.0)  # multiples of atr_entry
MAX_PYRAMID_LEVEL: int = 2       # cap at 3 total contracts (level 0=1, 1=2, 2=3)

# --- ADX exit gate (EXIT-05) ---
ADX_EXIT_GATE: float = 20.0     # close position if ADX drops below this

# =========================================================================
# Contract specs — D-11 (operator confirmed, overrides SPEC.md original)
# =========================================================================

# SPI 200 mini: $5/pt, $6 AUD RT (split $3 on open + $3 on close per D-13)
SPI_MULT: float = 5.0
SPI_COST_AUD: float = 6.0       # round-trip; half deducted on open, half on close

# AUD/USD: $10,000 notional, $5 AUD RT (split $2.50 on open + $2.50 on close)
AUDUSD_NOTIONAL: float = 10000.0
AUDUSD_COST_AUD: float = 5.0    # round-trip; half deducted on open, half on close

# =========================================================================
# Phase 3 constants — state persistence (STATE-01, STATE-07, D-11)
# =========================================================================

INITIAL_ACCOUNT: float = 100_000.0  # starting account balance (STATE-07, reset_state)
MAX_WARNINGS: int = 100             # FIFO bound on state['warnings'] (D-11)
STATE_SCHEMA_VERSION: int = 1       # bump on each schema change (STATE-04)
STATE_FILE: str = 'state.json'      # repo-root state file path (SPEC.md §FILE STRUCTURE)

# =========================================================================
# Palette constants — Phase 5 + Phase 6 shared (D-02 retrofit)
# =========================================================================
# Originally defined in dashboard.py module-level; migrated here so
# notifier.py can import the same palette without cross-hex import (hex
# fence D-01). Underscore prefix preserves "shared-implementation-detail"
# semantics rather than "stable public API".

_COLOR_BG: str = '#0f1117'
_COLOR_SURFACE: str = '#161a24'
_COLOR_BORDER: str = '#252a36'
_COLOR_TEXT: str = '#e5e7eb'
_COLOR_TEXT_MUTED: str = '#cbd5e1'
_COLOR_TEXT_DIM: str = '#64748b'
_COLOR_LONG: str = '#22c55e'
_COLOR_SHORT: str = '#ef4444'
_COLOR_FLAT: str = '#eab308'

# =========================================================================
# Position TypedDict — D-08
# =========================================================================


class Position(TypedDict):
  '''Open position state. Round-trips directly to/from Phase 3 state.json.

  Fields:
    direction:     'LONG' or 'SHORT'
    entry_price:   Fill price at position open
    entry_date:    ISO YYYY-MM-DD of entry bar
    n_contracts:   Current contract count (may increase via pyramid)
    pyramid_level: 0 = initial, 1 = added once, 2 = added twice (cap, PYRA-04)
    peak_price:    Highest HIGH since entry for LONG; None for SHORT (D-08)
    trough_price:  Lowest LOW since entry for SHORT; None for LONG (D-08)
    atr_entry:     ATR at time of entry — used for stop distance + pyramid
                   thresholds (D-15: stop anchored to entry ATR, not today's)
  '''
  direction: Literal['LONG', 'SHORT']
  entry_price: float
  entry_date: str
  n_contracts: int
  pyramid_level: int
  peak_price: float | None       # LONG: highest HIGH since entry; None for SHORT
  trough_price: float | None     # SHORT: lowest LOW since entry; None for LONG
  atr_entry: float
