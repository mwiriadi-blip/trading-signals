# Phase 2: Signal Engine — Sizing, Exits, Pyramiding — Research

**Researched:** 2026-04-21
**Domain:** Pure-Python position sizing, trailing-stop exits, pyramid state machine
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01** — Introduce `system_params.py` before Phase 2 code; move ADX_GATE, MOM_THRESHOLD, periods from `signal_engine.py` into it; LONG/SHORT/FLAT stay in `signal_engine.py`.
- **D-02** — Phase 2 functions accept scalar inputs (atr: float, rvol: float, etc.), NOT raw DataFrames. Phase 1's `get_latest_indicators` dict is the boundary.
- **D-03** — All Phase 2 public functions explicitly guard against NaN inputs; RVol NaN → vol_scale = 2.0; ATR NaN raises or returns sentinel per function contract.
- **D-04** — Reuse Phase 1's pure-loop oracle pattern where the math warrants it; skip for pure arithmetic.
- **D-05** — 9-cell signal-transition truth table gets named scenario fixtures in Phase 1 TestVote style.
- **D-06** — Extend determinism snapshot from Phase 1: JSON goldens per fixture, SHA256-hashed, committed at `tests/determinism/phase2_snapshot.json`.
- **D-07** — Phase 2 code lives in `sizing_engine.py` at repo root. SPEC.md amendment required at Wave 0 (currently lists these functions under `signal_engine.py`).
- **D-08** — `Position` is a `TypedDict` in `system_params.py`. Fields: `direction: Literal['LONG', 'SHORT']`, `entry_price: float`, `entry_date: str`, `n_contracts: int`, `pyramid_level: int`, `peak_price: float | None`, `trough_price: float | None`, `atr_entry: float`.
- **D-09** — Return types: `SizingDecision(contracts: int, warning: str | None)` and `PyramidDecision(add_contracts: int, new_level: int)` as `@dataclass(frozen=True, slots=True)`. Primitives for stop/pnl. Dataclasses live in `sizing_engine.py`.
- **D-10** — Both individual callables AND a thin `step()` wrapper. `step()` composes; does not duplicate logic. `StepResult` dataclass captures updated position, closed trade, sizing decision, pyramid decision, unrealised pnl, warnings.
- **D-11** — SPI mini: `SPI_MULT = 5`, `SPI_COST_AUD = 6.0`. AUD/USD unchanged: `AUDUSD_NOTIONAL = 10000`, `AUDUSD_COST_AUD = 5.0`. Wave 0 task amends SPEC.md §6 and CLAUDE.md.
- **D-12** — PYRA-05 enforced statelessly: `check_pyramid` reads `position.pyramid_level` and evaluates ONLY the trigger for the next level. Never returns `add_contracts=2`.
- **D-13** — Round-trip cost split: half on open, half on close. `compute_unrealised_pnl` deducts `open_cost_half = instrument_cost_aud * n_contracts / 2`.
- **D-14** — 15 scenario fixtures: 9 transition cells + 6 edge cases (names listed in CONTEXT.md §Decisions).

### Claude's Discretion

- Exact `SizingDecision` / `PyramidDecision` / `StepResult` field ordering + docstring style — match Phase 1's pattern.
- Whether `step()` returns `StepResult` or a plain tuple — prefer `StepResult` for parity with D-09.
- Whether scenario fixtures use CSV or JSON — recommended: JSON per fixture (multiple dataclass-shaped objects).
- Exact `Position` field name for SHORT's trough — `trough_price` per D-08 (not reusing `peak_price`).

### Deferred Ideas (OUT OF SCOPE)

- Phase 1 optional polish follow-up #6 (hash production output).
- Phase 4 orchestrator defensive contract check (REVIEWS #3).
- Phase 3 schema coordination detail.
- Extreme price-scale sensitivity testing (penny stocks).
- RVol single-value NaN window edge case (partially addressed by D-03).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SIZE-01 | `risk_pct` = 1.0% for LONG, 0.5% for SHORT | §Sizing formula derivation |
| SIZE-02 | `trail_mult` = 3.0 for LONG, 2.0 for SHORT | §Trailing stop mechanics |
| SIZE-03 | `vol_scale = clip(0.12 / RVol, 0.3, 2.0)` (guard RVol ≤ 1e-9 as 2.0) | §NaN guard patterns |
| SIZE-04 | `n_contracts = int((account × risk_pct / stop_dist) × vol_scale)`, no floor | §Sizing formula derivation |
| SIZE-05 | If sized `n_contracts == 0`, skip trade + surface "size=0" warning | §SizingDecision contract |
| SIZE-06 | SPI $25/pt, $30 RT [superseded by D-11]; AUD/USD $10k notional, $5 RT | §Contract constants |
| EXIT-01 | LONG→FLAT closes the open LONG | §9-cell truth table |
| EXIT-02 | SHORT→FLAT closes the open SHORT | §9-cell truth table |
| EXIT-03 | LONG→SHORT in one run: close LONG then open SHORT | §step() logic and two-phase eval |
| EXIT-04 | SHORT→LONG in one run: close SHORT then open LONG | §step() logic and two-phase eval |
| EXIT-05 | ADX < 20 while in trade closes immediately | §step() evaluation order |
| EXIT-06 | LONG trail stop = peak − (3×ATR); peak updates with today's HIGH | §Trailing stop mechanics |
| EXIT-07 | SHORT trail stop = trough + (2×ATR); trough updates with today's LOW | §Trailing stop mechanics |
| EXIT-08 | LONG stop hit if today's LOW ≤ stop | §stop-hit detection |
| EXIT-09 | SHORT stop hit if today's HIGH ≥ stop | §stop-hit detection |
| PYRA-01 | Pyramid level persists in state per position | §Position TypedDict — `pyramid_level` field |
| PYRA-02 | Level 0 → 1 when unrealised ≥ 1×ATR_entry | §Pyramid state machine |
| PYRA-03 | Level 1 → 2 when unrealised ≥ 2×ATR_entry | §Pyramid state machine |
| PYRA-04 | Never beyond 3 total contracts (level ≤ 2) | §Pyramid state machine |
| PYRA-05 | Max 1 pyramid step per daily run | §Stateless level-check mechanism |
</phase_requirements>

---

## Summary

Phase 2 implements the pure-math position management layer that sits between Phase 1's signal engine and Phase 3's state persistence. It is entirely scalar-in, scalar-out or dataclass-out — no DataFrames, no I/O, no network. The math itself is uncomplicated (3–5 floating-point operations per function), but the correctness story is demanding: 20 requirements, a 9-cell transition truth table with exit-before-entry sequencing, trailing stops driven by intraday HIGH/LOW (not close), and a pyramid state machine that must cap at one step per call even on gap days.

The primary design discipline is the hexagonal boundary: `sizing_engine.py` must not import state I/O siblings (enforced by the same AST blocklist already in `TestDeterminism`). The three callable groups — sizing, exits, pyramid — are orthogonal enough to implement and test independently, then composed into the optional `step()` wrapper. Phase 2 should be planned in exactly that order.

The most important planning landmines are: (1) `ADX_GATE` and other Phase 1 constants must be migrated to `system_params.py` BEFORE any Phase 2 code references them — tests currently only import the three signal constants and `compute_indicators`, so the migration is safe; (2) gap-through-stop accounting is a Phase 2 detection concern only (`check_stop_hit` returns a bool), not a fill-price concern — fill price is Phase 3/4's problem; (3) `frozen=True, slots=True` dataclasses are immutable at runtime in Python 3.11, which is the correct choice but means the Phase 4 orchestrator must build new Position dicts rather than mutating in place.

**Primary recommendation:** Wave 0 = doc amendments (SPEC.md §6, CLAUDE.md) + system_params.py scaffold + AST blocklist extension. Wave 1 = sizing functions + tests. Wave 2 = exit functions + tests. Wave 3 = pyramid + step() + 15 fixtures. Wave 4 = determinism snapshot + Phase 2 gate.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ATR-based position sizing | Pure-math module (`sizing_engine.py`) | None | Scalar inputs in, `SizingDecision` out; no I/O, no state |
| Vol-scale clip (SIZE-03) | `sizing_engine.py` | None | Pure arithmetic; NaN guard is math-layer responsibility |
| Trailing stop computation | `sizing_engine.py` | None | `get_trailing_stop` reads position + bar scalars, returns float |
| Stop-hit detection | `sizing_engine.py` | None | `check_stop_hit` reads intraday H/L, returns bool |
| Pyramid level check | `sizing_engine.py` | None | `check_pyramid` reads position state, returns `PyramidDecision` |
| Unrealised PnL | `sizing_engine.py` | None | `compute_unrealised_pnl` includes half-cost-on-open |
| Transition orchestration | `step()` in `sizing_engine.py` | Phase 4 orchestrator (primary path) | `step()` is a convenience composer; Phase 4 sequences the individual calls with logging |
| Position mutation + persistence | Phase 3 (`state_manager.py`) | None | Phase 2 consumes `Position` as input, never persists |
| Fill price on gap-through-stop | Phase 3/4 | None | Phase 2 only detects stop hit (bool); Phase 3 `record_trade` owns fill price |
| Constants (policy parameters) | `system_params.py` | None | Separates trading policy from pure-math logic |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python 3.11 | 3.11.8 (pinned in `.python-version`) | Runtime | Project-pinned; already installed via pyenv |
| `dataclasses` (stdlib) | 3.11 stdlib | `SizingDecision`, `PyramidDecision`, `StepResult` | `frozen=True, slots=True` gives immutability + memory efficiency; no deps |
| `typing` (stdlib) | 3.11 stdlib | `TypedDict`, `Literal`, `Optional` for `Position` | Python 3.11 TypedDict is solid; JSON-round-trip compatible with Phase 3 |
| `math` (stdlib) | 3.11 stdlib | `math.isnan`, `math.isfinite` for NaN guards | Safer than `numpy.isnan` in a module that must not import numpy |
| `pytest` | 8.3.3 (pinned) | Test framework | Already installed; same version as Phase 1 |

[VERIFIED: `.venv/bin/python3 --version` confirms 3.11.8; `pip show pytest` confirms 8.3.3; `dataclasses.dataclass(frozen=True, slots=True)` confirmed working at runtime]

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` (stdlib) | 3.11 stdlib | Fixture serialization for JSON goldens | In test helpers and regeneration scripts only — NOT in `sizing_engine.py` itself |
| `hashlib` (stdlib) | 3.11 stdlib | SHA256 determinism snapshot | In `TestDeterminism` only — NOT in `sizing_engine.py` |

**No new pip packages are required for Phase 2.** The 5 deps from `requirements.txt` (numpy, pandas, pytest, yfinance, ruff) are not used by `sizing_engine.py` or `system_params.py` — those modules are stdlib-only. Phase 2 test helpers load JSON fixtures but do not require pandas.

[VERIFIED: `requirements.txt` current at 5 deps; confirmed no new package needed]

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `math.isnan` for NaN guards | `numpy.isnan` or `pd.isna` | numpy/pandas would require importing them into `sizing_engine.py`; math is stdlib and keeps the AST blocklist clean |
| `TypedDict` for Position | `@dataclass` for Position | TypedDict serializes directly to a plain dict for Phase 3's JSON state; dataclass would require custom serialization |
| `frozen=True, slots=True` dataclasses | Plain dataclasses | frozen prevents accidental mutation in tests; slots reduces memory overhead — negligible gain here but is a Phase 1 established pattern |
| JSON fixtures | CSV fixtures (Phase 1 style) | Phase 2 fixtures contain multiple structured objects (position, bar, indicators, expected); CSV would awkwardly flatten these into wide rows with manual column parsing |

**Installation:** No new packages needed.

---

## Architecture Patterns

### System Architecture Diagram

```
Phase 1 Output
  get_latest_indicators(df) → dict of scalars
  get_signal(df) → int (LONG/SHORT/FLAT)
        │
        ▼
Phase 2 Inputs (scalars extracted by Phase 4 orchestrator)
  atr: float, rvol: float, adx: float
  bar: {open, high, low, close}
  account: float
  old_signal: int, new_signal: int
  position: Position TypedDict | None
        │
        ├──► calc_position_size(account, signal, atr, rvol, multiplier)
        │         └──► SizingDecision(contracts, warning)
        │
        ├──► get_trailing_stop(position, current_price, atr)
        │         └──► float (stop price)
        │
        ├──► check_stop_hit(position, high, low, atr)
        │         └──► bool
        │
        ├──► check_pyramid(position, current_price, atr_entry)
        │         └──► PyramidDecision(add_contracts, new_level)
        │
        ├──► compute_unrealised_pnl(position, current_price, multiplier)
        │         └──► float (gross - half open cost)
        │
        └──► step(position, bar, indicators, old_signal, new_signal)
                  └──► StepResult(
                         position: Position | None,
                         closed_trade: ClosedTrade | None,
                         sizing_decision: SizingDecision | None,
                         pyramid_decision: PyramidDecision | None,
                         unrealised_pnl: float,
                         warnings: list[str]
                       )
        │
        ▼
Phase 3 Input
  StepResult or individual decisions → state_manager.record_trade / save_state
```

### Recommended Project Structure
```
/
├── signal_engine.py       # Phase 1 (LONG/SHORT/FLAT constants stay here)
├── system_params.py       # NEW — Phase 2: Position TypedDict + all policy constants
├── sizing_engine.py       # NEW — Phase 2: pure-math sizing/exit/pyramid functions
├── tests/
│   ├── test_signal_engine.py  # Phase 1 tests (extended in Wave 0 for AST guard)
│   ├── test_sizing_engine.py  # NEW — Phase 2 test suite
│   ├── fixtures/
│   │   ├── scenario_*.csv     # Phase 1 fixtures (unchanged)
│   │   └── phase2/            # NEW — 15 JSON scenario fixtures
│   │       ├── transition_long_to_long.json
│   │       ├── transition_long_to_short.json
│   │       ├── ... (9 transition cells)
│   │       ├── pyramid_gap_crosses_both_levels_caps_at_1.json
│   │       ├── adx_drop_below_20_while_in_trade.json
│   │       ├── long_trail_stop_hit_intraday_low.json
│   │       ├── short_trail_stop_hit_intraday_high.json
│   │       ├── long_gap_through_stop.json
│   │       └── n_contracts_zero_skip_warning.json
│   ├── determinism/
│   │   ├── snapshot.json         # Phase 1 SHA256 hashes (unchanged)
│   │   └── phase2_snapshot.json  # NEW — Phase 2 JSON golden hashes (D-06)
│   └── regenerate_phase2_fixtures.py  # NEW — offline fixture regenerator
```

### Pattern 1: Sizing Formula — SIZE-04 with vol-scale clip

**What:** ATR-based position size = `int((account * risk_pct / stop_dist) * vol_scale)`, where `stop_dist = trail_mult * atr * multiplier` and `vol_scale = clip(0.12 / rvol, 0.3, 2.0)`.

**When to use:** New entry sizing only. Never called on hold cells.

**Key verified numbers (SPI mini, account=$100k):**

| ATR | RVol | stop_dist (LONG) | vol_scale | n_raw | n_contracts |
|-----|------|-----------------|-----------|-------|-------------|
| 53 | 0.15 | 795 | 0.8 | ~1.007 | 1 |
| 80 | 0.15 | 1200 | 0.8 | ~0.667 | 0 (SIZE-05 warning) |
| 20 | 0.15 | 300 | 0.8 | ~2.667 | 2 |

[VERIFIED: computed live at research time]

**Example (production pattern):**
```python
# Source: system_params.py constants + CONTEXT.md D-11/D-01
def calc_position_size(
  account: float,
  signal: int,
  atr: float,
  rvol: float,
  multiplier: float,
) -> 'SizingDecision':
  '''SIZE-01..05. Returns SizingDecision with contracts=0 + warning if undersized.'''
  risk_pct = RISK_PCT_LONG if signal == LONG else RISK_PCT_SHORT
  trail_mult = TRAIL_MULT_LONG if signal == LONG else TRAIL_MULT_SHORT
  # SIZE-03: NaN/zero RVol guard
  if not math.isfinite(rvol) or rvol <= 1e-9:
    vol_scale = VOL_SCALE_MAX
  else:
    vol_scale = max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, VOL_SCALE_TARGET / rvol))
  # SIZE-04: stop distance in AUD
  stop_dist = trail_mult * atr * multiplier
  n_raw = (account * risk_pct / stop_dist) * vol_scale
  n_contracts = int(n_raw)
  # SIZE-05: no max(1, ...) floor
  warning = None
  if n_contracts == 0:
    warning = (
      f'size=0: account={account:.0f}, atr={atr:.4f}, '
      f'rvol={rvol:.4f}, vol_scale={vol_scale:.4f}, '
      f'stop_dist={stop_dist:.4f}'
    )
  return SizingDecision(contracts=n_contracts, warning=warning)
```

### Pattern 2: Trailing Stop — EXIT-06/07 with intraday peak/trough update

**What:** Two distinct operations: (1) update peak/trough from today's intraday bar, (2) compute current stop price, (3) detect stop hit.

**When to use:** Every bar while a position is open, BEFORE evaluating signal transitions.

```python
# Source: CONTEXT.md D-08, CLAUDE.md Operator Decisions, SPEC.md §7

def get_trailing_stop(position: 'Position', current_price: float, atr: float) -> float:
  '''EXIT-06/07: compute current stop price from peak/trough.

  LONG: stop = peak_price - TRAIL_MULT_LONG * atr
  SHORT: stop = trough_price + TRAIL_MULT_SHORT * atr
  current_price is used to initialize peak/trough on first call if None.
  '''
  if position['direction'] == 'LONG':
    peak = position['peak_price'] if position['peak_price'] is not None else current_price
    return peak - TRAIL_MULT_LONG * atr
  else:
    trough = position['trough_price'] if position['trough_price'] is not None else current_price
    return trough + TRAIL_MULT_SHORT * atr

def check_stop_hit(position: 'Position', high: float, low: float, atr: float) -> bool:
  '''EXIT-08/09: True if today's intraday bar hits the trailing stop.

  LONG: hit if low <= stop (stop = peak - 3*ATR)
  SHORT: hit if high >= stop (stop = trough + 2*ATR)
  Intraday HIGH/LOW convention per CLAUDE.md Operator Decisions.
  '''
  if position['direction'] == 'LONG':
    peak = position['peak_price'] or position['entry_price']
    stop = peak - TRAIL_MULT_LONG * atr
    return low <= stop
  else:
    trough = position['trough_price'] or position['entry_price']
    stop = trough + TRAIL_MULT_SHORT * atr
    return high >= stop
```

### Pattern 3: Pyramid State Machine — PYRA-01..05 stateless check

**What:** Read `position.pyramid_level`, evaluate only the next-level trigger, return `PyramidDecision`.

**Unrealised distance convention:** Use CLOSE price (not HIGH) for pyramid trigger — avoids false triggers from intraday spikes. Phase 4 orchestrator passes `bar['close']` as `current_price`.

```python
# Source: CONTEXT.md D-12

def check_pyramid(
  position: 'Position', current_price: float, atr_entry: float
) -> 'PyramidDecision':
  '''PYRA-01..05. Advances at most 1 level per call.

  At level 0: add if unrealised_distance >= 1 * atr_entry -> level 1
  At level 1: add if unrealised_distance >= 2 * atr_entry -> level 2
  At level 2: never add (capped)
  Gap-day that crosses both thresholds still returns add_contracts=1 because
  only the CURRENT level's trigger is evaluated (D-12: stateless PYRA-05).
  '''
  level = position['pyramid_level']
  if level >= MAX_PYRAMID_LEVEL:  # 2
    return PyramidDecision(add_contracts=0, new_level=level)
  # Unrealised distance: price moved in profit direction from entry
  if position['direction'] == 'LONG':
    dist = current_price - position['entry_price']
  else:
    dist = position['entry_price'] - current_price
  threshold = (level + 1) * atr_entry  # 1*atr at level 0, 2*atr at level 1
  if dist >= threshold:
    return PyramidDecision(add_contracts=1, new_level=level + 1)
  return PyramidDecision(add_contracts=0, new_level=level)
```

### Pattern 4: step() Two-Phase Evaluation — EXIT-03/04

**What:** `step()` chains exits-first-then-entries per EXIT-03/04 so a reversal (LONG→SHORT) fires both legs atomically.

**Evaluation order (verified from SPEC.md §7 + EXIT-03/04):**
1. EXIT-05: `adx < ADX_EXIT_GATE (20)` → close position regardless of signals
2. Stop hit: `check_stop_hit(bar.high, bar.low)` → close position
3. Signal transition: if close triggered by 1 or 2, no entry leg possible (position cleared); otherwise apply 9-cell table
4. Pyramid: only if position still open after all above
5. Unrealised PnL: `compute_unrealised_pnl` on final position state

```python
# Source: CONTEXT.md D-10, D-13, EXIT-03, EXIT-04
# step() pseudocode — full implementation is planner's detail
def step(position, bar, indicators, old_signal, new_signal) -> StepResult:
  warnings = []
  closed_trade = None
  new_position = position  # may be mutated (new dict) during step

  # Phase 1: exit checks (EXIT-05, stop hit)
  if position is not None:
    adx = indicators['adx']
    if not math.isnan(adx) and adx < ADX_EXIT_GATE:
      # EXIT-05: close immediately
      closed_trade = _close_position(position, bar, 'adx_exit')
      new_position = None
    elif check_stop_hit(position, bar['high'], bar['low'], indicators['atr']):
      # EXIT-08/09
      closed_trade = _close_position(position, bar, 'stop_hit')
      new_position = None

  # Phase 2: signal transition (EXIT-01..04)
  if new_position is not None:  # not already closed by phase 1
    ...  # 9-cell table

  # Phase 3: pyramid (only if position open)
  ...
  # Phase 4: PnL
  ...
  return StepResult(...)
```

### Pattern 5: compute_unrealised_pnl — D-13 half-cost split

**What:** Deducts opening-half cost from gross mark-to-market PnL.

```python
# Source: CONTEXT.md D-13
def compute_unrealised_pnl(
  position: 'Position', current_price: float, multiplier: float
) -> float:
  '''Unrealised P&L minus half-cost-on-open (D-13).

  formula: (current - entry) * n_contracts * multiplier - open_cost_half
  open_cost_half = instrument_cost_aud * n_contracts / 2
  (SPI: 6.0/2 = 3.0 per contract; AUDUSD: 5.0/2 = 2.5 per contract)
  Caller supplies multiplier; instrument_cost derived from multiplier lookup
  OR caller supplies cost_per_contract_open as an additional arg.
  '''
  direction_mult = 1 if position['direction'] == 'LONG' else -1
  gross = direction_mult * (current_price - position['entry_price']) * position['n_contracts'] * multiplier
  # cost lookup: caller passes multiplier; derive instrument from multiplier
  # OR: add cost_aud_open as a separate parameter (planner decides)
  open_cost_half = _instrument_open_cost(multiplier) * position['n_contracts']
  return gross - open_cost_half
```

**Planner decision needed:** `compute_unrealised_pnl` signature — does it take `cost_aud_open` as an explicit parameter, or does it look up the instrument cost from `multiplier` (coupling it to the two-instrument constant table)? Explicit parameter is cleaner and more testable.

### Pattern 6: Constant Migration from signal_engine.py to system_params.py

**Migration safety verified:** Phase 1 tests only import `compute_indicators`, `get_signal`, `get_latest_indicators`, `LONG`, `SHORT`, `FLAT` from `signal_engine`. No test imports `ADX_GATE`, `MOM_THRESHOLD`, or period constants by name. The constants appear only in docstring text, not as imported names.

[VERIFIED: `grep -n "from signal_engine import" tests/test_signal_engine.py` — zero imports of policy constants]

**Migration steps:**
1. Create `system_params.py` with all Phase 1 policy constants (moved) + Phase 2 new constants
2. Update `signal_engine.py` to `from system_params import ADX_GATE, MOM_THRESHOLD, ATR_PERIOD, ADX_PERIOD, MOM_PERIODS, RVOL_PERIOD, ANNUALISATION_FACTOR`
3. Confirm `pytest tests/test_signal_engine.py` still passes green (99/99)

**system_params.py constant catalogue:**
```python
# Source: CONTEXT.md D-01, D-11
# --- Phase 1 constants (moved from signal_engine.py) ---
ATR_PERIOD: int = 14
ADX_PERIOD: int = 20
MOM_PERIODS: tuple[int, int, int] = (21, 63, 252)
RVOL_PERIOD: int = 20
ANNUALISATION_FACTOR: int = 252
ADX_GATE: float = 25.0          # entry gate
MOM_THRESHOLD: float = 0.02

# --- Phase 2 new constants ---
RISK_PCT_LONG: float = 0.01
RISK_PCT_SHORT: float = 0.005
TRAIL_MULT_LONG: float = 3.0
TRAIL_MULT_SHORT: float = 2.0
VOL_SCALE_TARGET: float = 0.12
VOL_SCALE_MIN: float = 0.3
VOL_SCALE_MAX: float = 2.0
PYRAMID_TRIGGERS: tuple[float, float] = (1.0, 2.0)  # multiples of atr_entry
MAX_PYRAMID_LEVEL: int = 2      # cap at 3 total contracts (0=1, 1=2, 2=3)
ADX_EXIT_GATE: float = 20.0     # close if ADX drops below this

# --- Contract specs (D-11 operator-confirmed) ---
SPI_MULT: float = 5.0           # AUD per point, SPI mini
SPI_COST_AUD: float = 6.0       # round-trip AUD (3.0 on open, 3.0 on close)
AUDUSD_NOTIONAL: float = 10000.0
AUDUSD_COST_AUD: float = 5.0    # round-trip AUD (2.5 on open, 2.5 on close)

# --- Position TypedDict (D-08) ---
from typing import TypedDict, Literal, Optional
class Position(TypedDict):
    direction: Literal['LONG', 'SHORT']
    entry_price: float
    entry_date: str
    n_contracts: int
    pyramid_level: int
    peak_price: float | None    # LONG: highest HIGH since entry; None for SHORT
    trough_price: float | None  # SHORT: lowest LOW since entry; None for LONG
    atr_entry: float            # ATR at time of entry (used for pyramid thresholds)
```

### Anti-Patterns to Avoid

- **Hand-rolling vol-scale clip with multiple if/else branches:** Use `max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, VOL_SCALE_TARGET / rvol))`. Only the NaN/zero guard should be separate.
- **Using `max(1, n_contracts)` floor (explicit CLAUDE.md operator decision):** SIZE-05 requires skip + warning, not floor.
- **Pyramid returning `add_contracts=2` on gap days (PYRA-05):** `check_pyramid` reads current level and evaluates only that level's threshold. The function never returns 2.
- **Importing pandas, numpy, or requests into sizing_engine.py:** The AST blocklist in `TestDeterminism` will catch this at CI time. Use `math.isnan` not `numpy.isnan`.
- **Using CLOSE for trailing-stop peak/trough updates:** Operator-locked decision: use intraday HIGH (LONG) and LOW (SHORT) for updates AND hit detection.
- **Implementing fill price for gap-through-stop in Phase 2:** `check_stop_hit` returns `bool` only. Fill price is a Phase 3 `record_trade` concern.
- **Adding `trough_price` to LONG positions or `peak_price` to SHORT positions:** D-08 specifies `peak_price = None` for SHORT, `trough_price = None` for LONG. No dual-field pattern.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Frozen immutable return types | Custom `__setattr__` override | `@dataclass(frozen=True, slots=True)` | Python 3.11 stdlib; test equality with `==`, hashable |
| Clipping vol_scale | Custom range-check function | `max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, ...))` | Python built-in; one line |
| NaN detection | Epsilon comparisons | `math.isnan()` / `math.isfinite()` | stdlib, reliable |
| JSON fixture loading in tests | Custom parser | `json.loads(Path('...').read_text())` | stdlib, one line |
| SHA256 of expected-dict output | Custom hash | `hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()` | Phase 1 pattern |
| Position dict round-trip | Custom serializer | TypedDict + plain `dict` | TypedDict IS a dict; no serialization needed |

---

## The 9-Cell Signal-Transition Truth Table

[VERIFIED: derived from SPEC.md §7 + EXIT-01..04 + CONTEXT.md D-10]

| prev_position | new_signal | Action | Notes |
|---------------|------------|--------|-------|
| LONG | LONG | Hold: check stop + pyramid + pnl | No exit/entry unless stop hit or ADX exit |
| LONG | SHORT | EXIT-03: close LONG then open SHORT | Two-phase: realised PnL on close, new sizing on entry |
| LONG | FLAT | EXIT-01: close LONG, go flat | No new position |
| SHORT | LONG | EXIT-04: close SHORT then open LONG | Two-phase: realised PnL on close, new sizing on entry |
| SHORT | SHORT | Hold: check stop + pyramid + pnl | Same as LONG→LONG mirror |
| SHORT | FLAT | EXIT-02: close SHORT, go flat | No new position |
| none | LONG | New entry: calc_position_size + open LONG | No exit leg |
| none | SHORT | New entry: calc_position_size + open SHORT | No exit leg |
| none | FLAT | No action, stay flat | No position, no signal to act on |

**EXIT-05 + stop-hit override:** If ADX < 20 OR stop hit is detected, the position closes REGARDLESS of where the new signal maps in the table. Exit-phase runs BEFORE signal-transition evaluation in `step()`.

**Two-phase sequencing for reversal cells (LONG→SHORT, SHORT→LONG):**
1. Close existing position: realised PnL = `(exit_price - entry_price) * n_contracts * multiplier - close_cost_half`
2. Account updated (Phase 3 concern, but `StepResult.closed_trade` carries the data)
3. Size new position using `calc_position_size` with post-close account value
4. Open new position with `open_cost_half` deducted from `compute_unrealised_pnl`

---

## 15 Named Scenario Fixtures

[VERIFIED: D-14 from CONTEXT.md]

### 9 Transition Cells
1. `transition_long_to_long.json` — LONG hold, price rises, pyramid triggers, stop not hit
2. `transition_long_to_short.json` — Reversal: EXIT LONG + ENTER SHORT in one step
3. `transition_long_to_flat.json` — EXIT-01: close LONG, go flat
4. `transition_short_to_long.json` — Reversal: EXIT SHORT + ENTER LONG in one step
5. `transition_short_to_short.json` — SHORT hold, price falls, pyramid triggers
6. `transition_short_to_flat.json` — EXIT-02: close SHORT, go flat
7. `transition_none_to_long.json` — New LONG entry: sizing + position creation
8. `transition_none_to_short.json` — New SHORT entry: sizing + position creation
9. `transition_none_to_flat.json` — No position, FLAT signal: no action

### 6 Edge Cases
10. `pyramid_gap_crosses_both_levels_caps_at_1.json` — PYRA-05: gap day where close is past 2×ATR but only 1 contract added (stateless D-12)
11. `adx_drop_below_20_while_in_trade.json` — EXIT-05: ADX falls to 18 during a LONG, closes regardless of new_signal=LONG
12. `long_trail_stop_hit_intraday_low.json` — EXIT-08: today's LOW is exactly at or below the LONG stop
13. `short_trail_stop_hit_intraday_high.json` — EXIT-09: today's HIGH is exactly at or above the SHORT stop
14. `long_gap_through_stop.json` — LONG stop hit where open gaps below stop; LOW also below stop; stop detection fires
15. `n_contracts_zero_skip_warning.json` — SIZE-05: account + ATR combination yields n_raw < 1; SizingDecision(contracts=0, warning='size=0: ...')

**Each JSON fixture schema:**
```json
{
  "description": "...",
  "prev_position": { "direction": "...", "entry_price": ..., ... } | null,
  "bar": { "open": ..., "high": ..., "low": ..., "close": ..., "volume": ..., "date": "..." },
  "indicators": { "atr": ..., "adx": ..., "pdi": ..., "ndi": ..., "mom1": ..., "mom3": ..., "mom12": ..., "rvol": ... },
  "account": ...,
  "old_signal": ...,
  "new_signal": ...,
  "multiplier": ...,
  "instrument_cost_aud": ...,
  "expected": {
    "sizing_decision": { "contracts": ..., "warning": ... } | null,
    "trail_stop": ...,
    "stop_hit": ...,
    "pyramid_decision": { "add_contracts": ..., "new_level": ... } | null,
    "unrealised_pnl": ...,
    "position_after": { ... } | null
  }
}
```

---

## Common Pitfalls

### Pitfall 1: stop_dist Uses the ENTRY ATR, Not Today's ATR
**What goes wrong:** `calc_position_size` computes the stop distance as `trail_mult * atr * multiplier`. If `atr` is today's live ATR (not the entry ATR), the position size changes on every re-call, breaking sizing reproducibility.
**Why it happens:** Phase 4 orchestrator might pass the latest ATR to both sizing and stop functions. They use ATR differently: `calc_position_size` uses TODAY's ATR at entry time; `get_trailing_stop` uses today's ATR (which may differ from entry ATR) for the stop level.
**How to avoid:** `calc_position_size` takes the ATR at entry as input; `position.atr_entry` stores it; `check_pyramid` uses `atr_entry` (not today's ATR) for threshold calculations.
**Warning signs:** Pyramid thresholds drift after the first day in a position; sizes change when recomputed.

### Pitfall 2: Gap-Through-Stop Fill Price Confused with Hit Detection
**What goes wrong:** Implementing fill price logic (e.g., "execute at open if gapped through stop") inside `check_stop_hit` or `get_trailing_stop`.
**Why it happens:** The gap-through case is intuitive but its resolution is a trade-record concern, not a detection concern.
**How to avoid:** `check_stop_hit` returns `bool` ONLY. The fill price question (stop vs open) is Phase 3 `record_trade` territory.
**Warning signs:** `check_stop_hit` signature grows to return `(bool, float)` or includes `bar['open']` logic.

### Pitfall 3: NaN in Position Fields Propagates Through Arithmetic
**What goes wrong:** If `position['peak_price']` is `None` and code does `position['peak_price'] - 3 * atr`, Python raises `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'`.
**Why it happens:** `peak_price` starts as `None` (D-08) and is set to entry price or first HIGH on the day of entry. If Phase 4 doesn't initialize it correctly, Phase 2 arithmetic fails.
**How to avoid:** `get_trailing_stop` and `check_stop_hit` guard: `peak = position['peak_price'] if position['peak_price'] is not None else position['entry_price']`. Document this explicitly in the docstring.
**Warning signs:** `TypeError` on first bar of a new position.

### Pitfall 4: Double-Checking Both Pyramid Thresholds in One Call (PYRA-05 violation)
**What goes wrong:** `check_pyramid` checks BOTH `dist >= 1*atr` AND `dist >= 2*atr` and returns `add_contracts=2` when both are true.
**Why it happens:** Reading SPEC.md §8 literally ("when unrealised >= 1×ATR → add 1; when unrealised >= 2×ATR → add another") without the D-12 stateless clarification.
**How to avoid:** Only evaluate the threshold corresponding to `position.pyramid_level`. Gap days that cross both are intentionally handled by returning `add_contracts=1` (D-12 operator decision).
**Warning signs:** `fixture pyramid_gap_crosses_both_levels_caps_at_1` returns `add_contracts=2`.

### Pitfall 5: Constant Migration Breaks signal_engine.py
**What goes wrong:** Moving `ADX_GATE`, `MOM_THRESHOLD`, periods from `signal_engine.py` to `system_params.py` without updating the `signal_engine.py` import causes `NameError` on `get_signal`.
**Why it happens:** The move-then-import pattern is easy to partially execute.
**How to avoid:** In `signal_engine.py`, add `from system_params import ADX_GATE, MOM_THRESHOLD, ATR_PERIOD, ADX_PERIOD, MOM_PERIODS, RVOL_PERIOD, ANNUALISATION_FACTOR` immediately after removing the constant definitions. Run full test suite before committing.
**Warning signs:** Phase 1 test suite fails after the migration task.

### Pitfall 6: cost_aud_open Parameter Coupling to Instrument Lookup
**What goes wrong:** `compute_unrealised_pnl` takes `multiplier` and internally looks up the instrument cost by matching multiplier to SPI_MULT or AUDUSD_NOTIONAL. This works for two instruments but is fragile (both happen to have unique multipliers, but this is coincidental).
**How to avoid:** Accept `cost_aud_open: float` as an explicit parameter. Caller (Phase 4 orchestrator) knows which instrument it is and supplies the pre-computed half-cost.
**Warning signs:** Function contains `if multiplier == SPI_MULT: ... elif multiplier == AUDUSD_NOTIONAL: ...` branching.

### Pitfall 7: AUDUSD PnL Calculation — Direction Multiplier
**What goes wrong:** For SHORT positions, `(current_price - entry_price)` is negative when position is profitable. Forgetting the direction multiplier produces negative unrealised PnL for a winning SHORT.
**How to avoid:** `direction_mult = 1 if position['direction'] == 'LONG' else -1; gross = direction_mult * (current_price - entry_price) * n_contracts * multiplier`.
**Warning signs:** `transition_short_to_short` fixture returns negative PnL when price has fallen.

---

## Code Examples

### Example 1: vol_scale with NaN guard
```python
# Source: CONTEXT.md D-03, SIZE-03
import math
VOL_SCALE_TARGET = 0.12; VOL_SCALE_MIN = 0.3; VOL_SCALE_MAX = 2.0

def _vol_scale(rvol: float) -> float:
  '''SIZE-03: clip(0.12/rvol, 0.3, 2.0). Guard rvol <= 1e-9 as 2.0.'''
  if not math.isfinite(rvol) or rvol <= 1e-9:
    return VOL_SCALE_MAX
  return max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, VOL_SCALE_TARGET / rvol))
```

### Example 2: TypedDict Position with None guard
```python
# Source: CONTEXT.md D-08
from typing import TypedDict, Literal
class Position(TypedDict):
    direction: Literal['LONG', 'SHORT']
    entry_price: float
    entry_date: str
    n_contracts: int
    pyramid_level: int
    peak_price: float | None   # only LONG uses this; SHORT has None
    trough_price: float | None # only SHORT uses this; LONG has None
    atr_entry: float
```

### Example 3: Frozen dataclass with slots
```python
# Source: CONTEXT.md D-09 + verified working at Python 3.11.8
import dataclasses

@dataclasses.dataclass(frozen=True, slots=True)
class SizingDecision:
    contracts: int
    warning: str | None = None

@dataclasses.dataclass(frozen=True, slots=True)
class PyramidDecision:
    add_contracts: int
    new_level: int
```

### Example 4: JSON golden fixture generation (Phase 2 determinism approach)
```python
# Source: CONTEXT.md D-06, Phase 1 regenerate_goldens.py pattern
import json, hashlib
from pathlib import Path

def _hash_fixture_expected(expected: dict) -> str:
  '''SHA256 of JSON-serialized expected dict (sort_keys for stability).'''
  canonical = json.dumps(expected, sort_keys=True, separators=(',', ':'))
  return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

### Example 5: AST blocklist extension (Wave 0 test amendment)
```python
# Source: Phase 1 TestDeterminism pattern — extend parametrize list
import ast
from pathlib import Path

FORBIDDEN_MODULES = frozenset({
  'datetime', 'os', 'subprocess', 'socket', 'time', 'json', 'pathlib',
  'requests', 'urllib', 'http', 'state_manager', 'notifier', 'dashboard',
  'main', 'schedule', 'dotenv', 'pytz', 'yfinance',
})

HEX_MODULES = [
  Path('signal_engine.py'),    # Phase 1 (existing)
  Path('system_params.py'),    # Phase 2 — typing only
  Path('sizing_engine.py'),    # Phase 2 — dataclasses, typing, math, system_params, signal_engine
]

@pytest.mark.parametrize('module_path', HEX_MODULES)
def test_hex_forbidden_imports_absent(self, module_path: Path) -> None:
  imports = _top_level_imports(module_path)
  leaked = imports & FORBIDDEN_MODULES
  assert not leaked, f'{module_path} illegally imports: {sorted(leaked)}'
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SPEC.md §6: SPI $25/pt full contract | SPI mini $5/pt (D-11, operator confirmed) | 2026-04-21 discuss-phase 2 | All sizing/PnL math uses $5/pt; SPEC.md §6 and CLAUDE.md §Stack require Wave 0 amendments |
| SPEC.md: sizing in signal_engine.py | sizing in sizing_engine.py (D-07) | 2026-04-21 discuss-phase 2 | SPEC.md module layout section requires Wave 0 amendment |
| Phase 1: constants in signal_engine.py | Phase 2: policy constants in system_params.py (D-01) | 2026-04-21 discuss-phase 2 | signal_engine.py gains import from system_params; no test breakage (verified) |
| SPEC.md implicit convention: full round-trip at close | D-13: half on open, half on close | 2026-04-21 discuss-phase 2 | compute_unrealised_pnl deducts open-half; Phase 3 record_trade deducts close-half |

**Still SPEC.md-accurate (no amendment needed):**
- EXIT-01..05, EXIT-06..09 mechanics (SPEC.md §7 matches CONTEXT.md decisions)
- PYRA-01..05 (SPEC.md §8 matches D-12 stateless interpretation)
- AUD/USD notional=$10,000, cost=$5 RT (unchanged by D-11)
- Vol-scale formula `clip(0.12/RVol, 0.3, 2.0)` (unchanged)

---

## Open Questions

1. **`compute_unrealised_pnl` signature — explicit `cost_aud_open` parameter vs multiplier lookup?**
   - What we know: D-13 splits cost half on open, half on close. The function needs to know the open half cost.
   - What's unclear: Is it cleaner to accept `cost_aud_open: float` (caller knows the instrument) or derive it from `multiplier` (function knows the constant table)?
   - Recommendation: Add `cost_aud_open: float` as an explicit parameter. This is more testable, avoids coupling to the constant table, and works for any future instrument without code changes. Planner documents this in the task `<acceptance_criteria>`.

2. **Pyramid `current_price` — CLOSE or something else?**
   - What we know: D-12 says "check unrealised distance"; SPEC.md says "unrealised profit". Neither specifies OHLC field.
   - What's unclear: Phase 4 orchestrator decides what to pass. The fixture schema should make this explicit.
   - Recommendation: Use CLOSE price for pyramid triggers (standard for EOD mark-to-market). Document in `check_pyramid` docstring and fixture schema. The gap fixture tests PYRA-05 with a CLOSE that's past the 2×ATR threshold.

3. **Step() evaluation order: stop-hit THEN signal transition, or simultaneous?**
   - What we know: EXIT-03/04 say "two-phase eval: exits before entries." EXIT-05/08/09 are exit conditions.
   - What's unclear: If stop hits on the same day a signal reverses (e.g., LONG stop hits AND new signal is SHORT), does `step()` produce a LONG-close only, or close LONG + open SHORT?
   - Recommendation: Stop hit closes position only; no new entry on the same stop-hit day. This is the safer default (realistic: can't open new position after being stopped out in the same bar without knowing the bar's close timing). Document in `step()` docstring. The `adx_drop_below_20_while_in_trade` fixture captures EXIT-05 override.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All Phase 2 code | ✓ | 3.11.8 via pyenv | None needed |
| pytest | Test suite | ✓ | 8.3.3 (pinned) | None needed |
| dataclasses (stdlib) | SizingDecision, PyramidDecision | ✓ | 3.11 stdlib | None |
| typing (stdlib) | TypedDict, Literal | ✓ | 3.11 stdlib | None |
| math (stdlib) | NaN guards | ✓ | 3.11 stdlib | None |
| ruff | Lint gate | ✓ | 0.6.9 (pinned) | None |

[VERIFIED: `python3 --version` → 3.11.8; `pip show pytest` → 8.3.3; `pip show ruff` → 0.6.9; `dataclasses.dataclass(frozen=True, slots=True)` confirmed working]

**No missing dependencies.** Phase 2 requires zero new packages.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, testpaths=["tests"]) |
| Quick run command | `.venv/bin/python -m pytest tests/test_sizing_engine.py -x -q` |
| Full suite command | `.venv/bin/python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SIZE-01 | risk_pct=1.0% LONG, 0.5% SHORT | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_risk_pct_long_is_1pct -x` | ❌ Wave 0 |
| SIZE-02 | trail_mult=3.0 LONG, 2.0 SHORT | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_trail_mult_by_direction -x` | ❌ Wave 0 |
| SIZE-03 | vol_scale clip + NaN guard | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_vol_scale_nan_guard -x` | ❌ Wave 0 |
| SIZE-04 | n_contracts formula, no floor | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_calc_position_size_formula -x` | ❌ Wave 0 |
| SIZE-05 | n_contracts=0 → warning | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_zero_contracts_warning -x` | ❌ Wave 0 |
| EXIT-01 | LONG→FLAT closes LONG | scenario | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_long_to_flat -x` | ❌ Wave 0 |
| EXIT-02 | SHORT→FLAT closes SHORT | scenario | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_short_to_flat -x` | ❌ Wave 0 |
| EXIT-03 | LONG→SHORT two-phase | scenario | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_long_to_short -x` | ❌ Wave 0 |
| EXIT-04 | SHORT→LONG two-phase | scenario | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_short_to_long -x` | ❌ Wave 0 |
| EXIT-05 | ADX<20 closes position | scenario | `pytest tests/test_sizing_engine.py::TestEdgeCases::test_adx_drop_below_20_while_in_trade -x` | ❌ Wave 0 |
| EXIT-06 | LONG trail stop, peak via HIGH | unit | `pytest tests/test_sizing_engine.py::TestExits::test_long_trailing_stop_peak_update -x` | ❌ Wave 0 |
| EXIT-07 | SHORT trail stop, trough via LOW | unit | `pytest tests/test_sizing_engine.py::TestExits::test_short_trailing_stop_trough_update -x` | ❌ Wave 0 |
| EXIT-08 | LONG stop hit LOW<=stop | unit | `pytest tests/test_sizing_engine.py::TestExits::test_long_stop_hit_intraday_low -x` | ❌ Wave 0 |
| EXIT-09 | SHORT stop hit HIGH>=stop | unit | `pytest tests/test_sizing_engine.py::TestExits::test_short_stop_hit_intraday_high -x` | ❌ Wave 0 |
| PYRA-01 | pyramid_level persists in Position TypedDict | unit | `pytest tests/test_sizing_engine.py::TestPyramid::test_position_carries_pyramid_level -x` | ❌ Wave 0 |
| PYRA-02 | Level 0→1 at 1×ATR | unit | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_level_0_to_1 -x` | ❌ Wave 0 |
| PYRA-03 | Level 1→2 at 2×ATR | unit | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_level_1_to_2 -x` | ❌ Wave 0 |
| PYRA-04 | Cap at level 2 | unit | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_capped_at_level_2 -x` | ❌ Wave 0 |
| PYRA-05 | Max 1 step per call (gap fixture) | scenario | `pytest tests/test_sizing_engine.py::TestEdgeCases::test_pyramid_gap_crosses_both_levels_caps_at_1 -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/test_sizing_engine.py -x -q`
- **Per wave merge:** `.venv/bin/python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work 2`

### Wave 0 Gaps
- [ ] `tests/test_sizing_engine.py` — Phase 2 test module (all classes listed above)
- [ ] `tests/fixtures/phase2/` directory — 15 JSON fixture files
- [ ] `tests/regenerate_phase2_fixtures.py` — offline fixture regenerator
- [ ] `tests/determinism/phase2_snapshot.json` — SHA256 golden hashes
- [ ] `system_params.py` — constants + Position TypedDict
- [ ] `sizing_engine.py` — stub with public API signatures only (code in later waves)

---

## Security Domain

All Phase 2 code is pure math — no network, no filesystem, no user input, no authentication. ASVS categories V2 (Authentication), V3 (Session Management), V4 (Access Control), V6 (Cryptography) do not apply. V5 (Input Validation) applies only in the sense that NaN guards are input-validity checks, which are documented and tested.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | Partial | math.isnan / math.isfinite guards on ATR, RVol, account |
| V6 Cryptography | No | — |

**No threat patterns apply to Phase 2's pure-math scope.** The SHA256 in `TestDeterminism` is for tamper detection of committed test data, not cryptographic security.

---

## Project Constraints (from CLAUDE.md)

All constraints inherited from Phase 1 apply unchanged:

- **2-space indent, single quotes, snake_case, PEP 8 via `ruff check`** (not `ruff format`)
- **Hand-roll all math** — no pandas-ta, TA-Lib, or TA libraries
- **Hexagonal-lite:** `sizing_engine.py` and `system_params.py` must NOT import `state_manager`, `notifier`, `dashboard`, `main`, `requests`, `datetime`, `os`, `schedule`, `dotenv`, `pytz`, `yfinance`
- **All pure functions take plain args, return plain values** — no `datetime.now()`, no env-var reads inside them
- **No `max(1, …)` floor on sizing** — operator decision; SIZE-05 skip + warn instead
- **FLAT closes the open position** — LONG→FLAT closes LONG; SHORT→FLAT closes SHORT
- **Trailing stops use intraday HIGH/LOW** for both peak/trough updates AND stop-hit detection
- **Signal integers: LONG=1, SHORT=-1, FLAT=0** (from `signal_engine.py`)
- **pytest + ruff gate** before every commit
- **NEVER place live trades** — signal-only system

**New constraints specific to Phase 2:**
- SPEC.md §6 and CLAUDE.md §Stack are out-of-date — Wave 0 must amend them before code tasks (SPI $5/pt D-11; sizing_engine.py D-07)
- `SPI_MULT = 5`, `SPI_COST_AUD = 6.0` are the canonical contract constants — any test expecting $25/pt is wrong

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Pyramid `current_price` for trigger check is CLOSE, not HIGH | Pattern 3, Open Questions #2 | Fixture expected values wrong; test will fail but catch it immediately |
| A2 | On stop-hit day, no new entry leg fires (step() returns close-only) | Open Questions #3, Pattern 4 | Reversal+stop-hit same day would have wrong StepResult; fixable at Phase 4 integration |
| A3 | `compute_unrealised_pnl` signature takes explicit `cost_aud_open` param | Open Questions #1 | Minor signature change; fixable without affecting any other module |
| A4 | ADX_EXIT_GATE = 20 is checked against today's ADX (from indicators dict), not lagged | Pattern 4 | If EXIT-05 uses yesterday's ADX, the check fires on the wrong day; fixable but would change fixture expected values |

**If this table is not empty:** Items A1–A4 are Claude's discretion areas or open questions that are low-risk and verifiable by fixture tests on first run. No user confirmation needed before planning; planner documents chosen resolution.

---

## Sources

### Primary (HIGH confidence)
- [VERIFIED: codebase] `signal_engine.py` — Phase 1 production API (254 lines, 3.11.8)
- [VERIFIED: codebase] `tests/oracle/wilder.py` — pure-loop oracle pattern to reuse
- [VERIFIED: codebase] `tests/test_signal_engine.py` — existing AST guard and test structure to extend
- [VERIFIED: codebase] `tests/regenerate_scenarios.py` — Phase 2 regenerator should mirror this shape
- [VERIFIED: codebase] `pyproject.toml` — pytest config; testpaths=["tests"]
- [VERIFIED: codebase] `.planning/phases/02-signal-engine-sizing-exits-pyramiding/02-CONTEXT.md` — all 14 locked decisions
- [VERIFIED: codebase] `SPEC.md` §5–8 — canonical formulas (with D-11/D-13 overrides documented)
- [VERIFIED: codebase] `CLAUDE.md` §Operator Decisions — no floor, intraday H/L, FLAT closes
- [VERIFIED: runtime] Python 3.11.8 `dataclasses.dataclass(frozen=True, slots=True)` + `typing.TypedDict` — confirmed working
- [VERIFIED: math] All sizing formulas, trailing stop values, pyramid thresholds, unrealised PnL values — computed live at research time

### Secondary (MEDIUM confidence)
- [CITED: SPEC.md §7] Trailing stop: "peak_price − (3 × ATR)" for LONG, "peak_price + (2 × ATR)" for SHORT — though spec uses "peak_price" for both; D-08 clarifies `trough_price` field for SHORT
- [CITED: CONTEXT.md D-12] Pyramid stateless single-step logic — D-12 is explicit but untested until Phase 2 fixtures run
- [CITED: CONTEXT.md D-13] Half-cost-on-open — D-13 is operator-confirmed but formulas not previously implemented

### Tertiary (LOW confidence)
None — all key claims are verified against the codebase or CONTEXT.md locked decisions.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — stdlib only, already installed and tested
- Architecture: HIGH — derived from locked decisions D-01..D-14 in CONTEXT.md
- Math formulas: HIGH — computed live and cross-checked against SPEC.md + CONTEXT.md
- Pitfalls: HIGH — verified through codebase analysis and runtime checks
- Fixture schema: MEDIUM — schema proposed but not yet validated against planner constraints
- Open questions (A1-A4): LOW — Claude's discretion; resolvable during planning

**Research date:** 2026-04-21
**Valid until:** 2026-05-21 (stable Python stdlib; no external library dependency)
