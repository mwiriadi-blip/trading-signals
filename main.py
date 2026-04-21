'''Main — daily orchestrator + CLI.

Wires data_fetcher + signal_engine + sizing_engine + state_manager behind
argparse. Implements run_daily_check(args) per D-11 step sequence (Wave 2).

Architecture (hexagonal-lite, CLAUDE.md): main.py is the ONLY module allowed
to import from all sides of the hex. Pure-math modules (signal_engine,
sizing_engine, system_params) and I/O hex modules (state_manager,
data_fetcher) remain isolated; main.py is the adapter that crosses
boundaries. main.py must NOT reach directly into transport/data libraries
(yfinance / requests / pandas / numpy) — AST blocklist in
tests/test_signal_engine.py::TestDeterminism::test_main_no_forbidden_imports
enforces this via FORBIDDEN_MODULES_MAIN (C-5 revision 2026-04-22).

Reads the wall clock via datetime.now(ZoneInfo('Australia/Perth')) — the ONLY
module permitted to do so per CLAUDE.md. Pure-math modules receive run_date
as a scalar argument.

run_date (AWST wall-clock) and signal_as_of (market-local last-bar date)
are NEVER substituted for each other — both logged on every run (D-13).

Wave 0 (this commit): argparse skeleton + module constants + bootstrap
logging.basicConfig(force=True) in main() (Pitfall 4) + NotImplementedError
stubs for run_daily_check, _compute_run_date, and _closed_trade_to_record.
Wave 2 fills run_daily_check + _compute_run_date + _closed_trade_to_record
(04-03-PLAN.md); Wave 3 adds the top-level typed-exception boundary in
`if __name__ == '__main__'` (04-04-PLAN.md).
'''
import argparse
import logging
import sys
import time  # noqa: F401 — used in Wave 2 run_daily_check (time.perf_counter fetch_elapsed + total run elapsed)
from datetime import datetime  # noqa: F401 — used in Wave 2 _compute_run_date
from zoneinfo import ZoneInfo

import data_fetcher  # noqa: F401 — used in Wave 2 run_daily_check (fetch_ohlcv calls)
import signal_engine  # noqa: F401 — used in Wave 2 run_daily_check (compute_indicators / get_signal)
import sizing_engine  # noqa: F401 — used in Wave 2 run_daily_check (step())
import state_manager  # noqa: F401 — used in Wave 2 run_daily_check (load_state / save_state / record_trade)
from sizing_engine import ClosedTrade  # noqa: F401 — used in Wave 2 _closed_trade_to_record
from system_params import (  # noqa: F401 — used in Wave 2 run_daily_check
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  SPI_COST_AUD,
  SPI_MULT,
)

# =========================================================================
# Module-level constants
# =========================================================================

AWST = ZoneInfo('Australia/Perth')

# Instrument keys in state.json <-> yfinance tickers (CLAUDE.md §Conventions)
SYMBOL_MAP: dict = {
  'SPI200': '^AXJO',
  'AUDUSD': 'AUDUSD=X',
}

logger = logging.getLogger(__name__)


# =========================================================================
# Argparse (D-05, RESEARCH §Example 2)
# =========================================================================

def _build_parser() -> argparse.ArgumentParser:
  '''CLI-01..CLI-05: four boolean flags + CLI-02 --reset exclusivity enforced
  in _validate_flag_combo. Help strings spell out each flag's Phase 4 scope
  vs Phase 6/7 deferred wiring (C-1 revision — amended upstream docs).
  '''
  p = argparse.ArgumentParser(
    prog='python main.py',
    description='Trading Signals — SPI 200 & AUD/USD mechanical system',
  )
  p.add_argument(
    '--test', action='store_true',
    help='Run full signal check, print report, do NOT mutate state.json (CLI-01)',
  )
  p.add_argument(
    '--reset', action='store_true',
    help='Reinitialise state.json to $100k after confirmation (CLI-02). '
         'Cannot be combined with other flags.',
  )
  p.add_argument(
    '--force-email', action='store_true',
    help="Send today's email immediately (CLI-03). "
         'Phase 4: logs stub; wiring arrives in Phase 6.',
  )
  p.add_argument(
    '--once', action='store_true',
    help='Run one daily check and exit (CLI-04, GHA mode). '
         'Phase 4: alias for default; scheduler loop arrives in Phase 7.',
  )
  return p


def _validate_flag_combo(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
  '''D-05: --reset is strictly exclusive. --test + --force-email is allowed.

  Using post-parse parser.error() (exits with code 2, matching argparse
  convention) because argparse's mutually_exclusive_group would also block
  --test + --once etc. which D-05 allows.
  '''
  if args.reset and (args.test or args.force_email or args.once):
    parser.error('--reset cannot be combined with other flags')


# =========================================================================
# Clock reader + hex-boundary translator stubs (Wave 2 fills)
# =========================================================================

def _compute_run_date() -> datetime:
  '''CLAUDE.md: run_date always in Australia/Perth. No DST in Perth.
  Orchestrator is the only module allowed to read the wall clock.

  Returns a timezone-aware datetime; callers derive run_date_iso
  (YYYY-MM-DD) via strftime and run_date_display (full AWST string)
  separately.
  '''
  raise NotImplementedError('Wave 2 implements _compute_run_date — see 04-03-PLAN.md')


def _closed_trade_to_record(
  ct: ClosedTrade,
  symbol: str,
  multiplier: float,
  cost_aud: float,
  entry_date: str,
  run_date_iso: str,
) -> dict:
  '''D-12: translate Phase 2 ClosedTrade dataclass → Phase 3 record_trade dict.

  CRITICAL PITFALL (state_manager.py record_trade docstring lines 415-422):
    trade['gross_pnl'] MUST be raw price-delta P&L:
      (exit_price - entry_price) * n_contracts * multiplier  (LONG)
      (entry_price - exit_price) * n_contracts * multiplier  (SHORT)
    NOT ClosedTrade.realised_pnl (which already deducted the closing-half
    cost in sizing_engine._close_position). Passing realised_pnl as
    gross_pnl would double-count the close cost — running balance drifts
    below expected by ~$3-$6 per trade.

  record_trade validates all 11 fields per _validate_trade (D-15 + D-19):
    instrument, direction, entry_date, exit_date, entry_price, exit_price,
    gross_pnl, n_contracts, exit_reason, multiplier, cost_aud.
  '''
  raise NotImplementedError('Wave 2 implements _closed_trade_to_record — see 04-03-PLAN.md')


# =========================================================================
# Orchestrator (Wave 2 fills body)
# =========================================================================

def run_daily_check(args: argparse.Namespace) -> int:
  '''D-11 daily orchestration sequence (9 steps):
    1. load_state (Phase 3)
    2. compute run_date (AWST wall-clock via _compute_run_date)
    3. for each instrument in SYMBOL_MAP:
       a. data_fetcher.fetch_ohlcv(yf_symbol) (DATA-01/02)
       b. assert len(df) >= 300 else raise ShortFrameError (DATA-04)
       c. stale-bar check vs run_date (DATA-05 → warning only)
       d. signal_engine.compute_indicators(df) + get_signal(df)
       e. read old_signal from state['signals'][symbol] — handle BOTH int
          and dict shape per D-08 upgrade branch (Pitfall 7):
            raw = state['signals'].get(symbol)
            old_signal = raw if isinstance(raw, int) else raw.get('signal', 0)
          Always WRITE the nested dict:
            state['signals'][symbol] = {
              'signal': new_signal,
              'signal_as_of': signal_as_of,
              'as_of_run': run_date_iso,
            }
       f. sizing_engine.step(position, bar, indicators, old_signal, new_signal, ...)
       g. If step produced a closed_trade: record_trade BEFORE assigning
          position_after (AC-1 ordering fix — 04-03-PLAN.md).
       h. state['positions'][state_key] = result.position_after
       i. update_equity_history for the instrument (STATE-06)
    4. Structural --test guard (CLI-01): if args.test, SKIP save_state and
       return 0. This is the STRUCTURAL read-only guarantee — no runtime
       test-mode flag in state_manager.
    5. state_manager.save_state(state) exactly ONCE at end (D-11).
    6. return 0 on success; exceptions bubble to top-level boundary
       (Wave 3 adds the typed-exception handler in `if __name__ == '__main__'`).

  CLI-01 guarantee: --test is STRUCTURALLY read-only — compute mutates the
  in-memory `state` dict freely; the save_state call is conditional on
  `not args.test`. state.json mtime is therefore unchanged under --test.

  D-08 upgrade branch (Pitfall 7): state['signals'][symbol] may be either
  an int (Phase 3 reset_state shape) or a dict (Phase 4 nested shape).
  Orchestrator reads both; always writes the dict. No schema bump (D-08).
  '''
  raise NotImplementedError('Wave 2 implements run_daily_check — see 04-03-PLAN.md')


# =========================================================================
# Entry point
# =========================================================================

def main(argv: list[str] | None = None) -> int:
  '''Parse CLI args + configure logging + dispatch to run_daily_check.

  Pitfall 4: logging.basicConfig MUST use force=True — pytest and other
  plugins may have already added handlers to the root logger; without
  force=True the call is a silent no-op and our format/stream are ignored.

  Wave 3 wraps `return run_daily_check(args)` with a typed-exception
  boundary in `if __name__ == '__main__'` (DataFetchError / ShortFrameError
  → exit 2; unexpected → exit 1). Wave 2 adds --reset confirmation +
  --force-email stub dispatch.
  '''
  parser = _build_parser()
  args = parser.parse_args(argv)
  _validate_flag_combo(args, parser)
  logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stderr,
    force=True,
  )
  return run_daily_check(args)


if __name__ == '__main__':
  sys.exit(main())
