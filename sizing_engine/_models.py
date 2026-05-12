'''Sizing Engine — return-type dataclasses (D-09).

All 5 dataclasses used as return types across the sizing_engine package.
Imports: dataclasses only (hex boundary — no I/O, no external deps).
'''
import dataclasses


# =========================================================================
# Return-type dataclasses (D-09)
# =========================================================================


@dataclasses.dataclass(frozen=True, slots=True)
class SizingDecision:
  '''Result of calc_position_size.

  contracts: number of contracts to trade (0 = skip, SIZE-05)
  warning:   human-readable explanation when contracts == 0, else None
  '''
  contracts: int
  warning: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class PyramidDecision:
  '''Result of check_pyramid.

  add_contracts: 0 or 1 (never 2 per D-12 / PYRA-05)
  new_level:     pyramid level after this decision is applied
  '''
  add_contracts: int
  new_level: int


@dataclasses.dataclass(frozen=True, slots=True)
class ClosedTrade:
  '''Realised trade record populated by step() on close/reversal.

  exit_reason: one of 'flat_signal', 'signal_reversal', 'stop_hit', 'adx_exit'
  realised_pnl: gross PnL minus closing-half cost (close-half deducted here;
                open-half was already deducted in compute_unrealised_pnl)
  '''
  direction: str           # 'LONG' or 'SHORT'
  entry_price: float
  exit_price: float
  n_contracts: int
  realised_pnl: float
  exit_reason: str


@dataclasses.dataclass(frozen=True, slots=True)
class StepResult:
  '''Complete result of one step() call.

  position_after:   updated position after all exit/entry/pyramid logic (None = flat)
  closed_trade:     populated if a position was closed in this step (None if no close)
  sizing_decision:  populated when a new entry was sized (None if no new entry)
  pyramid_decision: populated when pyramid was evaluated on an open position (None if flat)
  unrealised_pnl:   mark-to-market PnL on position_after (0.0 if flat)
  warnings:         list of human-readable warnings surfaced during step (e.g. size=0)
  '''
  position_after: object  # Position | None — avoid cross-import; typed at usage site
  closed_trade: object    # ClosedTrade | None
  sizing_decision: object  # SizingDecision | None
  pyramid_decision: object  # PyramidDecision | None
  unrealised_pnl: float
  warnings: list


@dataclasses.dataclass(frozen=True, slots=True)
class DriftEvent:
  '''Phase 15 D-01 (SENTINEL-01/02): position-vs-signal drift event.

  Fields:
    instrument: 'SPI200' or 'AUDUSD' (state_key, not yfinance symbol).
    held_direction: 'LONG' or 'SHORT' (the position's direction).
    signal_direction: 'LONG', 'SHORT', or 'FLAT' (today's signal).
    severity: 'drift' (held vs FLAT) or 'reversal' (held vs opposite directional).
    message: operator-facing copy from D-14 template; the SHARED string between
             dashboard and email renderers (D-12 lockstep parity).
  '''
  instrument: str
  held_direction: str
  signal_direction: str
  severity: str
  message: str
