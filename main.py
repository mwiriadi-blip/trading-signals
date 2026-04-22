'''Main — daily orchestrator + CLI.

Wires data_fetcher + signal_engine + sizing_engine + state_manager behind
argparse. Implements run_daily_check(args) per D-11 step sequence (Wave 2),
and the top-level typed-exception boundary + --reset confirmation +
--force-email stub + DATA-05 stale-bar path (Wave 3).

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

Wave 0 (argparse skeleton + module constants + bootstrap
logging.basicConfig(force=True) in main() [Pitfall 4] + stubs for the
Wave 2 targets) is done. Wave 2 filled run_daily_check + _compute_run_date
+ _closed_trade_to_record (04-03-PLAN.md). Wave 3 (this commit) adds the
top-level typed-exception boundary inside main() + _handle_reset +
_force_email_stub + DATA-05 stale-bar detection (04-04-PLAN.md).
'''
import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import data_fetcher
import signal_engine
import sizing_engine
import state_manager
from data_fetcher import DataFetchError, ShortFrameError
from sizing_engine import ClosedTrade
from system_params import (
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  SPI_COST_AUD,
  SPI_MULT,
)

# NOTE (C-2 reviews Phase 5 D-06): `import dashboard` DELIBERATELY does NOT
# appear here at module top. The dashboard import lives INSIDE the helper
# below so that import-time failures in dashboard.py (syntax errors, missing
# sub-imports, circular imports during a debug session) are caught by the
# same `except Exception` net as runtime render failures. Without this, an
# import-time dashboard error would crash main.py at module load, breaking
# the daily run including state.json save and email dispatch.

# =========================================================================
# Module-level constants
# =========================================================================

AWST = ZoneInfo('Australia/Perth')

# Instrument keys in state.json <-> yfinance tickers (CLAUDE.md §Conventions)
SYMBOL_MAP: dict = {
  'SPI200': '^AXJO',
  'AUDUSD': 'AUDUSD=X',
}

# Per-instrument contract specs (CLAUDE.md Phase 2 D-11 + system_params.py).
# multiplier = point-value (AUD per price-point per contract)
# cost_aud   = ROUND-TRIP cost (split half-on-open / half-on-close per D-13)
_SYMBOL_CONTRACT_SPECS: dict = {
  'SPI200': {'multiplier': SPI_MULT, 'cost_aud': SPI_COST_AUD},
  'AUDUSD': {'multiplier': AUDUSD_NOTIONAL, 'cost_aud': AUDUSD_COST_AUD},
}

# DATA-04 (Pitfall 6): minimum bars required before compute_indicators.
_MIN_BARS_REQUIRED = 300

# DATA-05 (D-09): stale when (run_date - signal_as_of).days > this.
_STALE_THRESHOLD_DAYS = 3

logger = logging.getLogger(__name__)


# =========================================================================
# Dashboard integration (Phase 5 D-06)
# =========================================================================

def _render_dashboard_never_crash(state: dict, out_path: Path, now: datetime) -> None:
  '''D-06: dashboard render failure never crashes the run.

  C-2 reviews: `import dashboard` lives INSIDE the helper body (not at
  module top) so import-time errors in dashboard.py — syntax errors,
  bad sub-imports, circular-import bugs — are caught by the SAME
  `except Exception` that catches runtime render failures. Without
  this, an import-time dashboard error takes down main.py at module
  load time, before the helper even runs.

  The ONLY place in this codebase where `except Exception:` is correct —
  dashboard.html is a cosmetic artefact. State is already saved; email
  still dispatches (Phase 6). Never abort the run on a render failure.
  '''
  try:
    import dashboard  # local import — C-2 isolates import-time failures
    dashboard.render_dashboard(state, out_path, now=now)
  except Exception as e:
    logger.warning('[Dashboard] render failed: %s: %s', type(e).__name__, e)


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
  Orchestrator is the only module allowed to read the wall clock (D-13).

  Returns a timezone-aware datetime; callers derive run_date_iso
  (YYYY-MM-DD) via strftime and run_date_display (full AWST string)
  separately.
  '''
  return datetime.now(tz=AWST)


def _mode_label(args: argparse.Namespace) -> str:
  '''Render the opening [Sched] Run line's mode label.

  D-07: --once and default are both 'once' in Phase 4.
  '''
  if args.test:
    return 'test'
  if args.reset:
    return 'reset'
  if args.force_email:
    return 'force_email'
  return 'once'


def _closed_trade_to_record(
  ct: ClosedTrade,
  symbol: str,
  multiplier: float,
  cost_aud: float,
  entry_date: str,
  run_date_iso: str,
) -> dict:
  '''D-12: translate Phase 2 ClosedTrade dataclass -> Phase 3 record_trade dict.

  CRITICAL PITFALL 8 (see state_manager.record_trade docstring + 04-RESEARCH):
    trade['gross_pnl'] MUST be raw price-delta P&L:
      (exit_price - entry_price) * n_contracts * multiplier  (LONG)
      (entry_price - exit_price) * n_contracts * multiplier  (SHORT)
    It MUST NOT be ClosedTrade's post-close net (which already has the
    closing-half cost deducted in sizing_engine._close_position). Reusing
    that post-close net as gross_pnl would double-count the close cost -
    running balance drifts below expected by ~$3-$6 per trade.

  This function is deliberately kept free of any reference to the Phase 2
  post-close net attribute name: a project verification gate greps the
  function source for that token and fails the build on match.

  record_trade validates all 11 fields per _validate_trade (D-15 + D-19):
    instrument, direction, entry_date, exit_date, entry_price, exit_price,
    gross_pnl, n_contracts, exit_reason, multiplier, cost_aud.
  '''
  direction_mult = 1.0 if ct.direction == 'LONG' else -1.0
  gross_pnl = (
    direction_mult * (ct.exit_price - ct.entry_price)
    * ct.n_contracts * multiplier
  )
  return {
    'instrument': symbol,
    'direction': ct.direction,
    'entry_date': entry_date,
    'exit_date': run_date_iso,
    'entry_price': ct.entry_price,
    'exit_price': ct.exit_price,
    'gross_pnl': gross_pnl,
    'n_contracts': ct.n_contracts,
    'exit_reason': ct.exit_reason,
    'multiplier': multiplier,
    'cost_aud': cost_aud,
  }


# =========================================================================
# D-14 log formatters
# =========================================================================

_SIGNAL_LABELS = {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}


def _fmt_moms(scalars: dict) -> str:
  '''Compact momentum triple for the [Signal] log line: +0.012/+0.034/+0.056.'''
  return (
    f'{scalars["mom1"]:+.3f}/{scalars["mom3"]:+.3f}/{scalars["mom12"]:+.3f}'
  )


def _format_per_instrument_log_block(
  log: logging.Logger,
  yf_symbol: str,
  df_len: int,
  signal_as_of: str,
  fetch_elapsed: float,
  new_signal: int,
  scalars: dict,
  result: sizing_engine.StepResult,
  bar: dict,
  closed_pnl_display: float | None,
) -> None:
  '''D-14 per-instrument log block.

  Emits the [Fetch] / [Signal] / [State position] / [State trade] lines in
  the verbatim shape from 04-RESEARCH §Example 4, followed by any warnings
  from result.warnings (G-4 revision 2026-04-22, emitted at WARNING level
  with the [State] prefix), followed by a trailing blank line.

  closed_pnl_display is the post-close NET P&L for display in the
  [State] trade-closed line. It is computed by the caller (see
  run_daily_check) from price-delta minus close-half-cost — this function
  does NOT reference the Phase 2 post-close net attribute on ClosedTrade,
  to satisfy the Pitfall 8 "no raw Phase 2 pnl in main.py" gate.
  '''
  log.info(
    '[Fetch] %s ok: %d bars, last_bar=%s, fetched_in=%.1fs',
    yf_symbol, df_len, signal_as_of, fetch_elapsed,
  )
  log.info(
    '[Signal] %s signal=%s signal_as_of=%s (ADX=%.1f, moms=%s, rvol=%.2f)',
    yf_symbol, _SIGNAL_LABELS[new_signal],
    signal_as_of, scalars['adx'], _fmt_moms(scalars), scalars['rvol'],
  )
  if result.position_after is not None:
    trail_stop = sizing_engine.get_trailing_stop(
      result.position_after, bar['close'], scalars['atr'],
    )
    log.info(
      '[State] %s position: %s %d contracts @ entry=%.1f, '
      'pyramid=%d, trail_stop=%.1f, unrealised=%+.0f',
      yf_symbol,
      result.position_after['direction'],
      result.position_after['n_contracts'],
      result.position_after['entry_price'],
      result.position_after['pyramid_level'],
      trail_stop,
      result.unrealised_pnl,
    )
  else:
    log.info('[State] %s no position', yf_symbol)
  if result.closed_trade is not None:
    log.info(
      '[State] %s trade closed: %s exit=%.1f P&L=%+.2f reason=%s',
      yf_symbol,
      result.closed_trade.direction,
      result.closed_trade.exit_price,
      closed_pnl_display if closed_pnl_display is not None else 0.0,
      result.closed_trade.exit_reason,
    )
  else:
    log.info('[State] %s no trades closed this run', yf_symbol)
  # G-4 revision 2026-04-22: emit sizing_engine warnings with [State] prefix.
  for warning_msg in result.warnings:
    log.warning('[State] %s WARNING: %s', yf_symbol, warning_msg)
  log.info('')  # blank line between instruments


def _format_run_summary_footer(
  log: logging.Logger,
  run_date: datetime,
  elapsed_s: float,
  instruments: int,
  trades_recorded: int,
  warnings: int,
  state_saved: bool,
) -> None:
  '''D-14 run-summary footer.

  [Sched] Run <YYYY-MM-DD HH:MM:SS> AWST done in <X.Xs> —
    instruments=<N>, trades_recorded=<N>, warnings=<N>, state_saved=<...>
  state_saved=False under --test (structural read-only guarantee).
  '''
  state_saved_label = 'true' if state_saved else 'false (--test)'
  log.info(
    '[Sched] Run %s AWST done in %.1fs — '
    'instruments=%d, trades_recorded=%d, warnings=%d, state_saved=%s',
    run_date.strftime('%Y-%m-%d %H:%M:%S'),
    elapsed_s,
    instruments,
    trades_recorded,
    warnings,
    state_saved_label,
  )


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

  AC-1 revision 2026-04-22: inside the per-symbol loop, record_trade is
  called BEFORE `state['positions'][state_key] = result.position_after`.
  record_trade sets state['positions'][instrument] = None as part of
  closing a trade; assigning position_after AFTER that call preserves a
  freshly-opened reversal position (e.g. LONG->SHORT) that would otherwise
  be wiped.

  G-2 revision 2026-04-22: state['signals'][state_key] update includes
  last_scalars=scalars so Phase 5 (dashboard) and Phase 6 (email) can
  render ADX/Mom/RVol for the current signal without re-fetching.
  '''
  # Step 1: opening log line. D-07: one-shot mode acknowledgement emitted
  # BEFORE the per-symbol loop so CLI-04/CLI-05 smoke tests see the line
  # even if a later step raises.
  run_date = _compute_run_date()
  run_date_iso = run_date.strftime('%Y-%m-%d')
  run_date_display = run_date.strftime('%Y-%m-%d %H:%M:%S AWST')
  run_start_monotonic = time.perf_counter()
  logger.info(
    '[Sched] Run %s mode=%s', run_date_display, _mode_label(args),
  )
  logger.info('[Sched] One-shot mode (scheduler wiring lands in Phase 7)')

  # Step 2: load state.
  state = state_manager.load_state()

  # Step 3: per-symbol loop — fetch + indicators + signal + size + persist.
  trades_recorded = 0
  pending_warnings: list[tuple[str, str]] = []  # Wave 3 DATA-05 appends; empty in Wave 2.
  last_close_by_state_key: dict[str, float] = {}  # reused in step 4 equity rollup.

  for state_key, yf_symbol in SYMBOL_MAP.items():
    spec = _SYMBOL_CONTRACT_SPECS[state_key]
    multiplier = spec['multiplier']
    cost_aud_round_trip = spec['cost_aud']
    cost_aud_open = cost_aud_round_trip / 2

    # 3.a: fetch — DataFetchError propagates (Wave 3 catches at top level).
    fetch_start = time.perf_counter()
    df = data_fetcher.fetch_ohlcv(
      yf_symbol, days=400, retries=3, backoff_s=10.0,
    )
    fetch_elapsed = time.perf_counter() - fetch_start

    # 3.b: short-frame check BEFORE compute_indicators (DATA-04 / Pitfall 6).
    if len(df) < _MIN_BARS_REQUIRED:
      raise ShortFrameError(
        f'{yf_symbol}: only {len(df)} bars, need >= {_MIN_BARS_REQUIRED}',
      )

    # 3.c: signal_as_of from last-bar date — NO tz conversion (D-13, Pitfall 3).
    signal_as_of = df.index[-1].strftime('%Y-%m-%d')

    # 3.c.i: DATA-05 stale-bar check — RESEARCH §Example 5 lines 880-897.
    # AFTER fetch + signal_as_of, BEFORE compute_indicators (D-11 step 3.c).
    # last_bar in market-local tz date; run_date in AWST wall-clock date —
    # naive subtraction per Pitfall 3 (do NOT tz_convert the index).
    last_bar_date = df.index[-1].date()
    today_awst_date = run_date.date()
    days_old = (today_awst_date - last_bar_date).days
    if days_old > _STALE_THRESHOLD_DAYS:
      logger.warning(
        '[Fetch] WARN %s stale: signal_as_of=%s is %dd old (threshold=%dd)',
        yf_symbol, signal_as_of, days_old, _STALE_THRESHOLD_DAYS,
      )
      # D-10: queue for end-of-run flush so warnings land in state.json even
      # if later steps fail. append_warning takes POSITIONAL (source, message)
      # — the tuple `('fetch', f'...')` unpacks via `append_warning(state, *tup)`.
      pending_warnings.append((
        'fetch',
        f'{yf_symbol} stale: signal_as_of={signal_as_of} is {days_old}d old '
        f'(threshold={_STALE_THRESHOLD_DAYS}d)',
      ))

    # 3.d-f: indicators + signal. Scalars feed sizing_engine AND get
    # persisted under state[signals][state_key][last_scalars] (G-2).
    df_with_indicators = signal_engine.compute_indicators(df)
    scalars = signal_engine.get_latest_indicators(df_with_indicators)
    new_signal = signal_engine.get_signal(df_with_indicators)

    # 3.g: D-08 backward-compat read — accept int OR dict shape.
    raw = state['signals'].get(state_key)
    old_signal = raw if isinstance(raw, int) else raw.get('signal', 0)

    # 3.h: current position (may be None on flat).
    position = state['positions'].get(state_key)

    # 3.i: build bar dict for sizing_engine.step. Use last-row OHLC.
    last_row = df.iloc[-1]
    bar = {
      'open': float(last_row['Open']),
      'high': float(last_row['High']),
      'low': float(last_row['Low']),
      'close': float(last_row['Close']),
      'date': signal_as_of,
    }
    last_close_by_state_key[state_key] = bar['close']

    # 3.j-k: sizing_engine.step — exit/entry/pyramid state machine.
    result = sizing_engine.step(
      position=position,
      bar=bar,
      indicators=scalars,
      old_signal=old_signal,
      new_signal=new_signal,
      account=state['account'],
      multiplier=multiplier,
      cost_aud_open=cost_aud_open,
    )

    # 3.l: compute display P&L for closed trade. Pitfall 8: do NOT reference
    # the Phase 2 post-close-net attribute on ClosedTrade — recompute the
    # net from price-delta minus close-half-cost so the log line mirrors
    # what record_trade is about to credit.
    closed_pnl_display: float | None = None
    if result.closed_trade is not None:
      ct = result.closed_trade
      direction_mult = 1.0 if ct.direction == 'LONG' else -1.0
      gross = (
        direction_mult * (ct.exit_price - ct.entry_price)
        * ct.n_contracts * multiplier
      )
      # D-13: close-half cost is deducted by record_trade; compute display
      # net here so the log line reflects what record_trade will credit.
      closed_pnl_display = gross - (cost_aud_round_trip * ct.n_contracts / 2)

    # D-14 per-instrument log block (G-4: warnings emitted inside).
    _format_per_instrument_log_block(
      logger, yf_symbol, len(df), signal_as_of, fetch_elapsed,
      new_signal, scalars, result, bar, closed_pnl_display,
    )

    # 3.m AC-1 revision 2026-04-22: record_trade FIRST (mutates
    # state['positions'][state_key] = None as part of atomic close), THEN
    # assign result.position_after (which may be a new reversal position
    # that would otherwise be wiped to None).
    if result.closed_trade is not None:
      # Capture entry_date BEFORE record_trade so the trade dict carries the
      # ORIGINAL entry_date (state['positions'][state_key] is about to be
      # cleared and the info would be unrecoverable afterwards).
      entry_date_pre_close = (
        position['entry_date'] if position is not None else run_date_iso
      )
      trade_dict = _closed_trade_to_record(
        result.closed_trade, state_key,
        multiplier, cost_aud_round_trip,
        entry_date_pre_close, run_date_iso,
      )
      state = state_manager.record_trade(state, trade_dict)
      trades_recorded += 1

    # 3.n AC-1 revision 2026-04-22: position assignment AFTER record_trade.
    # On a reversal, record_trade cleared state['positions'][state_key] to
    # None; this line overwrites that None with the new reversal position.
    state['positions'][state_key] = result.position_after

    # 3.o G-2 revision 2026-04-22: signal state update always dict shape
    # AND always carries last_scalars for Phase 5/6 rendering.
    # B-1 revision 2026-04-22 (Phase 5 Wave 0): last_close added alongside
    # last_scalars for UI-SPEC §Positions table Current-price column.
    state['signals'][state_key] = {
      'signal': new_signal,
      'signal_as_of': signal_as_of,
      'as_of_run': run_date_iso,
      'last_scalars': scalars,
      'last_close': bar['close'],
    }

  # Step 4: total equity = account + sum(unrealised_pnl across active positions).
  equity = state['account']
  for sk, pos in state['positions'].items():
    if pos is not None:
      spec = _SYMBOL_CONTRACT_SPECS[sk]
      equity += sizing_engine.compute_unrealised_pnl(
        pos,
        last_close_by_state_key[sk],
        spec['multiplier'],
        spec['cost_aud'] / 2,
      )

  # Step 5: update equity history (STATE-06).
  state = state_manager.update_equity_history(state, run_date_iso, equity)

  # Step 6: flush queued warnings (empty in Wave 2; Wave 3 DATA-05 appends).
  for source, message in pending_warnings:
    state = state_manager.append_warning(state, source, message)

  # Step 7: bookkeeping — last_run.
  state['last_run'] = run_date_iso

  # Step 8: structural read-only guard for --test (CLI-01 D-11).
  elapsed_total = time.perf_counter() - run_start_monotonic
  if args.test:
    logger.info('[Sched] --test mode: skipping save_state (state.json unchanged)')
    _format_run_summary_footer(
      logger, run_date, elapsed_total,
      instruments=len(SYMBOL_MAP),
      trades_recorded=trades_recorded,
      warnings=len(pending_warnings),
      state_saved=False,
    )
    return 0

  # Step 9: atomic save_state + success footer.
  state_manager.save_state(state)
  logger.info(
    '[State] state.json saved (account=$%.2f, trades=%d, positions=%d)',
    state['account'],
    len(state['trade_log']),
    sum(1 for p in state['positions'].values() if p is not None),
  )
  # Step 9.5 (Phase 5 D-06): render dashboard.html; never crash on failure.
  # C-3 reviews Option A LOCKED: ONLY on the non-test path (after
  # `if args.test: return 0` above). --test is structurally read-only per
  # CLI-01 + CLAUDE.md — dashboard.html is a disk mutation and must not
  # happen under --test. Phase 6 may revisit if operator wants --test to
  # render a preview dashboard.
  _render_dashboard_never_crash(state, Path('dashboard.html'), run_date)
  elapsed_total = time.perf_counter() - run_start_monotonic
  _format_run_summary_footer(
    logger, run_date, elapsed_total,
    instruments=len(SYMBOL_MAP),
    trades_recorded=trades_recorded,
    warnings=len(pending_warnings),
    state_saved=True,
  )
  return 0


# =========================================================================
# CLI-02 / CLI-03 handlers (Wave 3)
# =========================================================================

def _handle_reset() -> int:
  '''CLI-02: reinitialise state.json to fresh $100k after operator confirmation.

  Confirmation rules (RESEARCH §Pitfall 5 lines 542-553):
    - If env var RESET_CONFIRM=='YES' (stripped), skip the interactive prompt.
      (Used by CI + tests.)
    - Else interactive: input('Type YES to confirm reset: '); catch EOFError
      (non-interactive stdin = cancellation, not a crash).

  Exit codes:
    0 — confirmed + reset + save_state succeeded.
    1 — operator cancelled (input != 'YES'); distinct from argparse=2 and
        success=0.

  Note: this function contains its OWN state_manager.save_state call,
  distinct from the one inside run_daily_check. The C-7 AST gate
  (revision 2026-04-22) is scoped to run_daily_check only; this second
  site at module level is expected and valid.
  '''
  confirm = os.getenv('RESET_CONFIRM', '').strip()
  if confirm != 'YES':
    try:
      confirm = input('Type YES to confirm reset: ').strip()
    except EOFError:
      confirm = ''
  if confirm != 'YES':
    logger.info('[State] --reset cancelled by operator')
    return 1
  state = state_manager.reset_state()
  state_manager.save_state(state)
  logger.info('[State] state.json reset to fresh $100k account')
  return 0


def _force_email_stub() -> int:
  '''CLI-03: Phase 4 stub — logs an [Email] line and returns 0.

  Phase 6 replaces this with the Resend notifier dispatch. The planned
  Phase 6 shape (C-8 revision 2026-04-22 per 04-REVIEWS.md) is:

    rc = run_daily_check(args)
    if rc == 0:
      notifier.send_daily_email(state, signals, positions)
    return rc

  The --test + --force-email combination ALREADY lands the
  compute-then-dispatch pattern in Phase 4 (see main()'s dispatch ladder:
  if args.force_email and args.test: run_daily_check(args); _force_email_stub()).
  Phase 6 generalises the same fresh-compute-then-dispatch shape to the
  non-test path so operators get fresh data in the "send today's email
  right now" flow.
  '''
  logger.info('[Email] --force-email received; notifier wiring arrives in Phase 6')
  return 0


# =========================================================================
# Entry point
# =========================================================================

def main(argv: list[str] | None = None) -> int:
  '''Parse CLI args + configure logging + dispatch under a typed-exception
  boundary.

  Pitfall 4: logging.basicConfig MUST use force=True — pytest and other
  plugins may have already added handlers to the root logger; without
  force=True the call is a silent no-op and our format/stream are ignored.

  Dispatch ladder (D-05 / D-06 / D-07):
    - --reset  → _handle_reset() (D-05: mutually exclusive with other flags;
                 enforced by _validate_flag_combo pre-parse).
    - --force-email + --test → run_daily_check(args) first (no save_state
                 due to --test), then _force_email_stub().
    - --force-email (no --test) → _force_email_stub() alone (no compute).
    - --once | default | --test alone → run_daily_check(args) (D-07: default
                 == --once in Phase 4; scheduler loop lands Phase 7).

  Exit-code mapping (Wave 3):
    0 — run_daily_check returned 0 (happy path) OR --reset confirmed OR
        --force-email stub.
    1 — operator cancelled --reset (returned from _handle_reset);
        OR unexpected Exception bubbled into the catch-all.
    2 — DataFetchError / ShortFrameError — data-layer failure (ERR-01 /
        D-03); argparse error (from _validate_flag_combo.parser.error).

  ERR-04 (crash-email) is Phase 8 scope. Wave 3's `except Exception` ONLY
  logs + returns 1.
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
  try:
    if args.reset:
      return _handle_reset()
    if args.force_email:
      # D-05: --test + --force-email is allowed. --test runs full compute
      # structurally-read-only; --force-email-alone skips compute (Phase 4
      # stub only; Phase 6 will generalise compute-then-dispatch per C-8).
      rc = run_daily_check(args) if args.test else 0
      stub_rc = _force_email_stub()
      return rc if rc != 0 else stub_rc
    return run_daily_check(args)
  except (DataFetchError, ShortFrameError) as e:
    logger.error('[Fetch] ERROR: %s', e)
    return 2
  except Exception as e:
    logger.error(
      '[Sched] ERROR: unexpected crash: %s: %s', type(e).__name__, e,
    )
    return 1


if __name__ == '__main__':
  sys.exit(main())
