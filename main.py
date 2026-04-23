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
+ _closed_trade_to_record (04-03-PLAN.md). Wave 3 added the top-level
typed-exception boundary inside main() + _handle_reset + DATA-05
stale-bar detection (04-04-PLAN.md). Phase 6 Wave 2 (06-03) deleted
the Phase 4 _force_email_stub and wired _send_email_never_crash via the
D-15 compute-then-email path — `run_daily_check` now returns a 4-tuple
(rc, state, old_signals, run_date) consumed by the dispatch ladder.
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
import system_params
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

# Phase 8 D-01 (ERR-05 staleness classifier): if (run_date - last_run).days > 2
# the next email's header banner labels the state 'Stale'.
STALENESS_DAYS_THRESHOLD: int = 2

# Phase 8 review-driven amendment (2026-04-23 Codex MEDIUM): cache the most
# recently loaded state so main()'s outer `except Exception` (crash handler)
# can pass a real state summary into the crash email instead of None.
# Previous draft passed state=None into _send_crash_email, which weakened
# ROADMAP SC-3 ("crash email with last-known state summary"). Module-level
# assignment is safe because this process runs single-threaded in both GHA
# one-shot and Replit schedule modes; no concurrency hazard.
_LAST_LOADED_STATE: 'dict | None' = None

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
# Email integration (Phase 6 D-15) — mirror of _render_dashboard_never_crash
# =========================================================================

def _send_email_never_crash(
  state: dict,
  old_signals: dict,
  run_date: datetime,
  is_test: bool = False,
) -> 'object':
  '''D-15 + NOTF-07/NOTF-08 + Phase 8 D-08 consumer bridge.

  C-2 reviews (Phase 5 precedent): `import notifier` lives INSIDE the
  helper body (not at module top) so import-time errors in notifier.py
  — syntax errors, bad sub-imports, circular-import bugs — are caught
  by the SAME `except Exception` that catches runtime dispatch failures.
  Without this, an import-time notifier error takes down main.py at
  module load time, before the helper even runs.

  Phase 8 D-08: returns the notifier.SendStatus verbatim on the happy
  path; caller (_dispatch_email_and_maintain_warnings) translates
  ok=False into a state_manager.append_warning.

  Phase 8 IN-04: on import-time or pre-SendStatus exception, also
  returns a SendStatus(ok=False, reason='<ExceptionType>: <msg>')
  sentinel so the contract is "always returns a SendStatus-shaped
  value". _dispatch_email_and_maintain_warnings keeps the historical
  `if status is None` guard as belt-and-suspenders for any future
  regression (truly impossible today).

  The ONLY place in this codebase where `except Exception:` is correct —
  alongside _render_dashboard_never_crash. NOTF-07 + NOTF-08: email
  failures NEVER crash the workflow. State is already saved; dashboard
  already rendered. Never abort the run on a send failure.
  '''
  try:
    import notifier  # local import — C-2 isolates import-time failures
    return notifier.send_daily_email(state, old_signals, run_date, is_test=is_test)
  except Exception as e:
    logger.warning('[Email] send failed: %s: %s', type(e).__name__, e)
    # IN-04: import-time or pre-SendStatus exception — return a
    # SendStatus sentinel instead of None. Local import matches the
    # C-2 pattern used for notifier itself (and falls back to returning
    # None only if THAT import also fails — caller's `status is None`
    # guard handles that pathological case).
    try:
      from notifier import SendStatus  # noqa: PLC0415 — C-2 local import
      return SendStatus(
        ok=False,
        reason=f'{type(e).__name__}: {e}'[:200],
      )
    except Exception:
      return None


# =========================================================================
# Phase 8 D-05/D-06/D-07 crash-email helpers — outer safety net
# =========================================================================

def _build_crash_state_summary(state: 'dict | None') -> str:
  '''D-06 (Phase 8): build bounded text/plain state summary for crash
  email body. Excludes trade_log, equity_history, warnings (would
  leak thousands of lines in a crash mail; operator has dashboard.html
  for forensic recovery).

  On `state is None` (crash before load_state) returns a short
  placeholder so the crash email still has a concrete state block.
  '''
  if state is None:
    return '(state not loaded — crash before load_state)'
  sig_spi = state.get('signals', {}).get('^AXJO', {})
  sig_aud = state.get('signals', {}).get('AUDUSD=X', {})
  # signals may also be keyed by state_key (SPI200 / AUDUSD) instead of
  # yfinance symbol, depending on where the crash occurred mid-flow.
  if not sig_spi:
    sig_spi = state.get('signals', {}).get('SPI200', {})
  if not sig_aud:
    sig_aud = state.get('signals', {}).get('AUDUSD', {})
  sig_spi_val = sig_spi.get('signal') if isinstance(sig_spi, dict) else sig_spi
  sig_aud_val = sig_aud.get('signal') if isinstance(sig_aud, dict) else sig_aud
  label = {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}
  sig_spi_str = label.get(sig_spi_val, '(none)')
  sig_aud_str = label.get(sig_aud_val, '(none)')
  account = state.get('account', 0.0)
  positions = state.get('positions', {})

  def _pos_line(symbol: str) -> str:
    p = positions.get(symbol)
    if not p:
      return f'{symbol}: (none)'
    return (
      f'{symbol}: {p.get("direction")} '
      f'{p.get("n_contracts")}@{p.get("entry_price")}'
    )

  lines = [
    f'signals: SPI200={sig_spi_str}, AUDUSD={sig_aud_str}',
    f'account: ${account:,.2f}',
    'positions:',
    f'  {_pos_line("SPI200")}',
    f'  {_pos_line("AUDUSD")}',
  ]
  return '\n'.join(lines)


def _send_crash_email(
  exc: BaseException,
  state: 'dict | None' = None,
  now: 'datetime | None' = None,
) -> 'object | None':
  '''D-05/D-06/D-07 (Phase 8): bridge to notifier.send_crash_email.

  Local notifier import (C-2 precedent) so a notifier import-time
  failure is captured here rather than inside main()'s except block.
  Never raises.
  '''
  try:
    import notifier
    summary = _build_crash_state_summary(state)
    return notifier.send_crash_email(exc, summary, now=now)
  except Exception as e:
    logger.error(
      '[Email] ERROR: crash-email dispatch wrapper failed: %s: %s',
      type(e).__name__, e,
    )
    return None


# =========================================================================
# Phase 8 D-02/D-08 + B1 revision: warning carry-over dispatch helper
# =========================================================================

def _maybe_set_stale_info(state: dict, run_date: datetime) -> None:
  '''Phase 8 ERR-05 + B3 revision: if state['last_run'] exists AND is
  > STALENESS_DAYS_THRESHOLD days before run_date, set a TRANSIENT
  state['_stale_info'] dict. Plan 02's _render_header_email reads this
  to render the red stale banner at top of email. NEVER persisted
  (D-14 underscore filter + explicit pop in
  _dispatch_email_and_maintain_warnings).
  '''
  last_run_iso = state.get('last_run')
  if not last_run_iso:
    return
  try:
    last_dt = datetime.strptime(last_run_iso, '%Y-%m-%d')
  except (TypeError, ValueError):
    return
  # Compare AWST dates (run_date is AWST via _compute_run_date)
  delta_days = (run_date.date() - last_dt.date()).days
  if delta_days > STALENESS_DAYS_THRESHOLD:
    state['_stale_info'] = {
      'days_stale': delta_days,
      'last_run_date': last_run_iso,
    }


def _dispatch_email_and_maintain_warnings(
  state: dict,
  old_signals: dict,
  now: datetime,
  is_test: bool,
  persist: bool,
) -> None:
  '''Phase 8 D-02/D-08 + B1 revision: CANONICAL ORDER:

    1. dispatch — notifier reads state['warnings'] (N-1 entries) + any
       transient _stale_info to render the header banner.
    2. clear_warnings(state) — wipe N-1 warnings first. If we appended
       a notifier-failure warning BEFORE clearing, clear_warnings
       would wipe it and the next run would never surface it.
    3. IF dispatch failed AND reason != 'no_api_key' (no_api_key is
       intentional operator configuration, not a failure):
         append_warning with notifier-sourced message —
         this warning is tagged with the CURRENT run's AWST date.
         It will be surfaced by next run's email via the routine-row
         age filter (w['date'] == prior_run_date).
       Review-driven amendment (2026-04-23, Codex MEDIUM):
       status is None (notifier import failure caught by
       _send_email_never_crash) also counts as a dispatch failure
       — append a dedicated warning so operator sees it next run.
    4. state.pop('_stale_info', None) — belt-and-suspenders clear of
       the transient signalling key before save (D-14 filter also
       strips it; explicit pop keeps in-memory dict clean).
    5. save_state(state) — single post-dispatch save.

  W3: total per-run save_state calls = 2 (end of run_daily_check step 5,
  plus this single post-dispatch save).

  Must be called AFTER run_daily_check's own save_state.
  '''
  status = _send_email_never_crash(state, old_signals, now, is_test=is_test)
  if not persist:
    # --test path: structural read-only. Do not mutate warnings or
    # persist. Still pop _stale_info from the in-memory dict for
    # cleanliness, but do NOT save.
    state.pop('_stale_info', None)
    return
  # B1 canonical order:
  # (a) wipe N-1 warnings FIRST.
  state_manager.clear_warnings(state)
  # (b) classify dispatch outcome and append-if-failed.
  #     Review-driven amendment (2026-04-23, Codex MEDIUM):
  #     `status is None` = _send_email_never_crash caught an
  #     import-time or pre-SendStatus exception. Operator must
  #     see this on the next run, so append a dedicated warning
  #     rather than silently skipping.
  #     Phase 8 IN-04 amendment (2026-04-23, iteration 2):
  #     _send_email_never_crash now returns a SendStatus(ok=False,
  #     reason='<ExcType>: <msg>') sentinel on exception, so this
  #     branch is belt-and-suspenders for a truly pathological case
  #     (SendStatus itself fails to import). Kept green for the
  #     existing R2 regression test and defense-in-depth.
  if status is None:
    state_manager.append_warning(
      state, source='notifier',
      message='Previous email dispatch failed to return status (import or runtime error)',
      now=now,
    )
  elif not status.ok and status.reason != 'no_api_key':
    state_manager.append_warning(
      state, source='notifier',
      message=f'Previous email send failed: {status.reason or "unknown"}',
      now=now,
    )
  # (c) belt + suspenders: clear the transient _stale_info key
  #     before save (D-14 filter also handles this).
  state.pop('_stale_info', None)
  # (d) single post-dispatch save.
  state_manager.save_state(state)


# =========================================================================
# Phase 7 scheduler helpers — Wave 0 stubs + tz wrapper. Wave 1
# (07-02-PLAN.md) fills the stub bodies. The _get_process_tzname wrapper
# is fully functional in Wave 0: Wave 1 uses it in _run_schedule_loop's
# UTC assertion. Signatures are part of the CONTEXT locked contract
# (D-01 + D-02) and must not change between Wave 0 and Wave 1.
# =========================================================================


def _get_process_tzname() -> str:
  '''Return the process-local timezone abbreviation (e.g. "UTC", "AEST").

  Thin wrapper around `time.tzname[0]` so Wave 1's UTC assertion inside
  `_run_schedule_loop` is patchable in tests without touching the `time`
  module's attributes (07-REVIEWS.md Codex MEDIUM-fix: `time.tzname` is
  platform-dependent and not always writable, whereas a module-level
  function in `main` is always patchable via `monkeypatch.setattr`).

  Production behaviour: identical to `time.tzname[0]`.
  Test behaviour: `monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')`.
  '''
  import time as _time  # LOCAL — keep stdlib import graph tidy
  return _time.tzname[0]


def _run_daily_check_caught(job, args) -> None:
  '''D-02 (Phase 7 Wave 1): never-crash wrapper for scheduled run_daily_check.

  Third instance of the never-crash pattern after _render_dashboard_never_crash
  and _send_email_never_crash. Schedule loop survives one bad run — next cron
  fire retries. ONLY valid `except Exception:` site in the loop path. Phase 8
  (ERR-04) adds crash-email dispatch on top of this net.

  Catches:
    - typed DataFetchError / ShortFrameError -> WARN [Sched] data-layer failure
    - catch-all Exception -> WARN [Sched] unexpected error (loop continues)
    - rc != 0 return (happy-path non-zero) -> WARN [Sched] rc=N (loop continues)
  '''
  try:
    rc, _, _, _ = job(args)
    if rc != 0:
      logger.warning(
        '[Sched] daily check returned rc=%d (loop continues)', rc,
      )
  except (DataFetchError, ShortFrameError) as e:
    logger.warning('[Sched] data-layer failure caught in loop: %s', e)
  except Exception as e:
    logger.warning(
      '[Sched] unexpected error caught in loop: %s: %s (loop continues)',
      type(e).__name__, e,
    )


def _run_schedule_loop(
  job,
  args,
  scheduler=None,
  sleep_fn=None,
  tick_budget_s: float = float(system_params.LOOP_SLEEP_S),
  max_ticks: int | None = None,
) -> int:
  '''D-01 (Phase 7 Wave 1): factored schedule loop driver with injectable fakes.

  Production call: `_run_schedule_loop(run_daily_check, args)` — defaults flow.
  Test call: `_run_schedule_loop(..., scheduler=fake, sleep_fn=fake_sleep,
  max_ticks=1)` — one tick, no real sleep, no real scheduler thread.

  Pitfall 1 mitigation: the `schedule` library's `.at()` without tz arg uses
  process-local time. We rely on UTC. Fail fast if the process runs in any
  other tz — Replit or GHA runner misconfiguration would otherwise silently
  fire at the wrong wall-clock moment. The check goes through the
  `_get_process_tzname()` wrapper (Wave 0) so tests can patch
  `main._get_process_tzname` cleanly (07-REVIEWS.md Codex MEDIUM-fix:
  `time.tzname` is platform-dependent and sometimes frozen).

  Pitfall 7 mitigation: max_ticks=None means infinite loop (production). Tests
  MUST pass a finite max_ticks to avoid hanging.
  '''
  import time as _time

  import schedule  # LOCAL — C-2 / hex-lite / AST blocklist discipline

  tzname = _get_process_tzname()
  assert tzname == 'UTC', (
    f'[Sched] process tz must be UTC; got {tzname!r}. '
    f'Set TZ=UTC in the deploy environment.'
  )

  _scheduler = scheduler or schedule
  _sleep = sleep_fn or _time.sleep

  logger.info(
    '[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon\u2013Fri'
  )
  _scheduler.every().day.at(system_params.SCHEDULE_TIME_UTC).do(_run_daily_check_caught, job, args)

  ticks = 0
  while max_ticks is None or ticks < max_ticks:
    _scheduler.run_pending()
    _sleep(tick_budget_s)
    ticks += 1
  return 0


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
         'Phase 6: runs full compute then dispatches via notifier.send_daily_email.',
  )
  p.add_argument(
    '--once', action='store_true',
    help='Run one daily check and exit (CLI-04, GHA mode). '
         'Phase 4: alias for default; scheduler loop arrives in Phase 7.',
  )
  # Phase 8 CONF-01 / CONF-02 — --reset companion flags (D-09..D-13).
  p.add_argument(
    '--initial-account',
    type=float,
    default=None,
    help=(
      'Starting account balance for --reset (Phase 8 CONF-01). '
      'Min $1,000, no ceiling, must be finite. If omitted on TTY, '
      'prompts interactively; on non-TTY, requires the other two '
      '--*-contract flags alongside.'
    ),
  )
  p.add_argument(
    '--spi-contract',
    type=str,
    default=None,
    choices=list(system_params.SPI_CONTRACTS.keys()),
    help=(
      'SPI 200 contract preset for --reset (Phase 8 CONF-02). '
      f'Choices: {", ".join(system_params.SPI_CONTRACTS.keys())}. '
      'Interactive prompt if omitted on TTY.'
    ),
  )
  p.add_argument(
    '--audusd-contract',
    type=str,
    default=None,
    choices=list(system_params.AUDUSD_CONTRACTS.keys()),
    help=(
      'AUD/USD contract preset for --reset (Phase 8 CONF-02). '
      f'Choices: {", ".join(system_params.AUDUSD_CONTRACTS.keys())}.'
    ),
  )
  return p


def _validate_flag_combo(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
  '''D-05 (Phase 4): --reset is strictly exclusive with --test /
  --force-email / --once. D-09 (Phase 8): --initial-account,
  --spi-contract, --audusd-contract ARE allowed alongside --reset
  but MUST NOT appear without it.

  Using post-parse parser.error() (exits with code 2, matching argparse
  convention) because argparse's mutually_exclusive_group would also block
  --test + --once etc. which D-05 allows.
  '''
  if args.reset and (args.test or args.force_email or args.once):
    parser.error('--reset cannot be combined with --test/--force-email/--once')
  reset_companions_present = (
    args.initial_account is not None
    or args.spi_contract is not None
    or args.audusd_contract is not None
  )
  if reset_companions_present and not args.reset:
    parser.error(
      '--initial-account / --spi-contract / --audusd-contract '
      'require --reset'
    )


def _stdin_isatty() -> bool:
  '''D-13 (Phase 8): thin wrapper around sys.stdin.isatty() for
  test-patchability. Mirrors Phase 7 _get_process_tzname precedent.
  '''
  return sys.stdin.isatty()


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

def run_daily_check(
  args: argparse.Namespace,
) -> tuple[int, dict | None, dict | None, datetime | None]:
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

  Phase 6 refactor (D-05 + RESEARCH §9): returns (rc, state, old_signals,
  run_date) 4-tuple so main() can dispatch email without re-reading state
  or re-reading the clock. --test path returns (0, state_in_memory,
  old_signals, run_date) WITHOUT calling save_state — CLI-01 structural
  read-only contract preserved.

  On the happy path returns (0, state, old_signals, run_date).
  On failure, exceptions (DataFetchError, ShortFrameError, or anything
  unexpected) propagate up and are caught by main()'s typed-exception
  boundary. The None-guard in main()'s dispatch ladder is
  defense-in-depth for any future non-exception failure return.
  '''
  # Step 1: opening log line. D-07: one-shot mode acknowledgement emitted
  # BEFORE the per-symbol loop so CLI-04/CLI-05 smoke tests see the line
  # even if a later step raises.
  run_date = _compute_run_date()

  # D-03 (Phase 7): weekday gate — short-circuits BEFORE any fetch, compute,
  # or state mutation. Applies to ALL invocation modes (default, --once,
  # --test, --force-email). `run_date.weekday()` returns 0=Mon..6=Sun
  # (Python stdlib contract); 5=Sat, 6=Sun. Preserves the 4-tuple contract
  # so main()'s dispatch ladder None-guard absorbs the state=None case
  # without a second code path.
  if run_date.weekday() >= system_params.WEEKDAY_SKIP_THRESHOLD:
    logger.info(
      '[Sched] weekend skip %s (weekday=%d) — no fetch, no state mutation',
      run_date.strftime('%Y-%m-%d'), run_date.weekday(),
    )
    return 0, None, None, run_date

  run_date_iso = run_date.strftime('%Y-%m-%d')
  run_date_display = run_date.strftime('%Y-%m-%d %H:%M:%S AWST')
  run_start_monotonic = time.perf_counter()
  logger.info(
    '[Sched] Run %s mode=%s', run_date_display, _mode_label(args),
  )

  # Step 2: load state.
  state = state_manager.load_state()

  # Phase 8 review-driven amendment (Codex MEDIUM): refresh the module-level
  # cache as soon as load_state returns. The outer crash handler in main()
  # reads this via _LAST_LOADED_STATE to build the crash-email state summary
  # (_build_crash_state_summary already handles state=None gracefully for
  # crashes BEFORE load_state).
  global _LAST_LOADED_STATE
  _LAST_LOADED_STATE = state

  # Phase 8 ERR-05 (B3 revision): staleness signalled via transient
  # state['_stale_info']. Set BEFORE dispatch, popped BEFORE save_state
  # by _dispatch_email_and_maintain_warnings. NOT stored in state['warnings']
  # because Plan 02's routine age filter would drop it (date mismatch
  # between tag-time and prior_run_date).
  _maybe_set_stale_info(state, run_date)

  # D-05 (Phase 6): capture old_signals BEFORE the per-symbol loop mutates
  # state['signals']. Keyed by yfinance symbol per notifier's expectation.
  # Handles BOTH Phase 3 int-shape AND Phase 4 D-08 dict-shape per Pitfall 7.
  old_signals: dict = {
    yf_sym: (
      state['signals'].get(state_key, {}).get('signal')
      if isinstance(state['signals'].get(state_key), dict)
      else state['signals'].get(state_key)
    )
    for state_key, yf_sym in SYMBOL_MAP.items()
  }

  # Step 3: per-symbol loop — fetch + indicators + signal + size + persist.
  trades_recorded = 0
  pending_warnings: list[tuple[str, str]] = []  # Wave 3 DATA-05 appends; empty in Wave 2.
  last_close_by_state_key: dict[str, float] = {}  # reused in step 4 equity rollup.

  for state_key, yf_symbol in SYMBOL_MAP.items():
    # Phase 8 D-17: resolve tier from state['_resolved_contracts'] materialised
    # by state_manager.load_state (Plan 01). sizing_engine never imports the
    # contract dicts — orchestrator passes multiplier + cost_aud_open through.
    # Round-trip is split half-on-open (here) / half-on-close (via
    # _closed_trade_to_record → state_manager.record_trade) per Phase 2 D-13.
    resolved = state['_resolved_contracts'][state_key]
    multiplier = resolved['multiplier']
    cost_aud_round_trip = resolved['cost_aud']
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
  # Phase 8 D-17: resolve tier from state['_resolved_contracts'] (per-symbol
  # tier from operator --reset config), not scalar system_params imports.
  equity = state['account']
  for sk, pos in state['positions'].items():
    if pos is not None:
      resolved = state['_resolved_contracts'][sk]
      equity += sizing_engine.compute_unrealised_pnl(
        pos,
        last_close_by_state_key[sk],
        resolved['multiplier'],
        resolved['cost_aud'] / 2,
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
    return 0, state, old_signals, run_date

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
  return 0, state, old_signals, run_date


# =========================================================================
# CLI-02 / CLI-03 handlers (Wave 3)
# =========================================================================

def _prompt_or_default(
  prompt_text: str,
  default_value,
  validator,
):
  '''Phase 8 WR-02: shared interactive-prompt helper for _handle_reset.

  Consolidates the prompt/blank-accepts-default/q-cancels/invalid-rejects
  cycle that repeated 3× verbatim in _handle_reset. Public behavior is
  unchanged from the pre-refactor inline blocks — existing interactive-
  path tests (TestResetInteractive) continue to pass without modification.

  Contract:
    - Prints prompt_text via input() (already spelled with trailing ': ').
    - Returns (rc, value):
        rc=0 + the parsed value, OR
        rc=1 + None when cancelled ('q'/EOF) or invalid.
    - Blank input → default_value returned with rc=0.
    - 'q' (case-insensitive) or EOFError on input() → log 'cancelled',
      return (1, None).
    - validator(raw) is called with the stripped raw string for non-
      blank, non-q inputs. It MUST return (ok: bool, value_or_err):
        ok=True  → value used; helper returns (0, value)
        ok=False → value_or_err is the stderr error message;
                   helper prints '[State] ERROR: {msg}' and returns (1, None).
  '''
  try:
    raw = input(prompt_text).strip()
  except EOFError:
    raw = 'q'
  if raw.lower() == 'q':
    logger.info('[State] --reset cancelled by operator')
    return 1, None
  if raw == '':
    return 0, default_value
  ok, parsed_or_err = validator(raw)
  if not ok:
    print(f'[State] ERROR: {parsed_or_err}', file=sys.stderr)
    return 1, None
  return 0, parsed_or_err


def _handle_reset(args: argparse.Namespace) -> int:
  '''CLI-02 + Phase 8 D-09/D-10/D-11/D-12/D-13:

  Accepts --initial-account / --spi-contract / --audusd-contract
  OR prompts interactively on TTY. Non-TTY + missing flags → exit 2.

  Flow:
    1. D-13 non-TTY guard (must be first).
    2. D-09 interactive Q&A for each missing flag (or q to quit) via
       _prompt_or_default (Phase 8 WR-02 refactor).
    3. D-10 min-$1000 validation (float, $/comma-stripped) + isfinite check.
    4. D-11 label validation (argparse choices handles explicit flags;
       interactive path re-validates against SPI_CONTRACTS/AUDUSD_CONTRACTS).
    5. D-12 preview block: print new values + current state.json values.
    6. YES confirmation (RESET_CONFIRM env override preserved).
    7. Build state + save.

  Return codes:
    0 — reset written
    1 — operator cancelled (EOF, blank YES, q, invalid input, non-finite)
    2 — non-TTY without companion flags OR argparse-level error

  Note: this function contains its OWN state_manager.save_state call,
  distinct from the one inside run_daily_check. The C-7 AST gate
  (revision 2026-04-22) is scoped to run_daily_check only; this second
  site at module level is expected and valid.
  '''
  import math

  has_explicit_flags = (
    args.initial_account is not None
    and args.spi_contract is not None
    and args.audusd_contract is not None
  )
  if not has_explicit_flags and not _stdin_isatty():
    print(
      '[State] ERROR: Non-interactive shell detected. Pass '
      '--initial-account <N> --spi-contract <label> '
      '--audusd-contract <label> explicitly.',
      file=sys.stderr,
    )
    return 2

  # --- D-09 interactive Q&A ---
  initial_account = args.initial_account
  if initial_account is None:
    def _validate_account(raw: str):
      cleaned = raw.lstrip('$').replace(',', '')
      try:
        return True, float(cleaned)
      except ValueError:
        return False, f'invalid account value {raw!r}'

    rc, initial_account = _prompt_or_default(
      'Starting account [$100,000]: ',
      float(system_params.INITIAL_ACCOUNT),
      _validate_account,
    )
    if rc != 0:
      return rc
  # T-08-12 mitigation: reject NaN/inf/-inf (argparse type=float accepts them).
  if not math.isfinite(initial_account):
    print(
      '[State] ERROR: --initial-account must be a finite number '
      '(not NaN/inf/-inf)',
      file=sys.stderr,
    )
    return 1
  if initial_account < 1000:
    print(
      '[State] ERROR: --initial-account must be at least $1,000',
      file=sys.stderr,
    )
    return 1

  spi_contract = args.spi_contract
  if spi_contract is None:
    default_label = system_params._DEFAULT_SPI_LABEL
    choices = ', '.join(system_params.SPI_CONTRACTS.keys())

    def _validate_spi(raw: str):
      if raw not in system_params.SPI_CONTRACTS:
        return False, f'invalid SPI label {raw!r} — choices: {choices}'
      return True, raw

    rc, spi_contract = _prompt_or_default(
      f'SPI200 contract preset [{default_label}] (choices: {choices}): ',
      default_label,
      _validate_spi,
    )
    if rc != 0:
      return rc

  audusd_contract = args.audusd_contract
  if audusd_contract is None:
    default_label = system_params._DEFAULT_AUDUSD_LABEL
    choices = ', '.join(system_params.AUDUSD_CONTRACTS.keys())

    def _validate_audusd(raw: str):
      if raw not in system_params.AUDUSD_CONTRACTS:
        return False, f'invalid AUDUSD label {raw!r} — choices: {choices}'
      return True, raw

    rc, audusd_contract = _prompt_or_default(
      f'AUDUSD contract preset [{default_label}] (choices: {choices}): ',
      default_label,
      _validate_audusd,
    )
    if rc != 0:
      return rc

  # --- D-12 preview ---
  print('This will replace state.json. New values:')
  print(f'  initial_account: ${initial_account:,.2f}')
  print('  contracts:')
  print(f'    SPI200:  {spi_contract}')
  print(f'    AUDUSD:  {audusd_contract}')
  try:
    current = state_manager.load_state()
  except Exception as e:
    # Phase 8 IN-02: surface the swallowed error at DEBUG so an operator
    # running `--reset` because their state is already broken can see WHY
    # the preview block is empty when running with --log-level DEBUG.
    # The swallow itself is intentional — the preview must still proceed
    # even if the existing state.json is unreadable.
    logger.debug(
      '[State] reset preview: failed to read existing state (%s: %s)',
      type(e).__name__, e,
    )
    current = None
  if current is not None:
    print('Current state.json:')
    cur_ia = current.get('initial_account', system_params.INITIAL_ACCOUNT)
    tag = 'migrated default' if 'initial_account' not in current else 'on disk'
    print(f'  initial_account: ${cur_ia:,.2f} ({tag})')
    print(f'  last_run: {current.get("last_run")}')
    print(f'  trades: {len(current.get("trade_log", []))}')

  # --- YES confirm (RESET_CONFIRM env override preserved) ---
  confirm = os.getenv('RESET_CONFIRM', '').strip()
  if confirm != 'YES':
    try:
      confirm = input('Type YES to confirm, anything else to cancel: ').strip()
    except EOFError:
      confirm = ''
  if confirm != 'YES':
    logger.info('[State] --reset cancelled by operator')
    return 1

  # --- Build + save ---
  state = state_manager.reset_state()
  state['initial_account'] = float(initial_account)
  state['contracts'] = {'SPI200': spi_contract, 'AUDUSD': audusd_contract}
  state_manager.save_state(state)
  logger.info(
    '[State] state.json reset (initial_account=$%.2f, SPI200=%s, AUDUSD=%s)',
    initial_account, spi_contract, audusd_contract,
  )
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

  Dispatch ladder (D-05 / D-06 / D-07 / D-15):
    - --reset  → _handle_reset() (D-05: mutually exclusive with other flags;
                 enforced by _validate_flag_combo pre-parse).
    - --force-email OR --test → run_daily_check(args) (with --test
                 structurally skipping save_state per CLI-01); then
                 _send_email_never_crash(state, old_signals, run_date,
                 is_test=args.test). Phase 6 wiring: --test alone now
                 sends a [TEST]-prefixed email (previously logged only).
    - --once | default → run_daily_check(args) (no email). D-07 default
                 == --once in Phase 4; scheduler loop lands Phase 7.

  Exit-code mapping (Wave 3):
    0 — run_daily_check returned 0 (happy path) OR --reset confirmed.
    1 — operator cancelled --reset (returned from _handle_reset);
        OR unexpected Exception bubbled into the catch-all.
    2 — DataFetchError / ShortFrameError — data-layer failure (ERR-01 /
        D-03); argparse error (from _validate_flag_combo.parser.error).

  ERR-04 (crash-email) is Phase 8 scope. Wave 3's `except Exception` ONLY
  logs + returns 1.
  '''
  # D-06 (Phase 7): load .env into os.environ BEFORE parsing args.
  # Local import keeps `dotenv` off module-top imports so the AST blocklist
  # on every non-main module stays meaningful; main.py is the sole consumer.
  from dotenv import load_dotenv  # noqa: PLC0415 — C-2 local-import pattern
  load_dotenv()  # no-op when .env absent; env vars take precedence (override=False default)

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
      return _handle_reset(args)
    if args.force_email or args.test:
      # D-15 Phase 6: shared compute-then-email path. --test structurally
      # skips save_state inside run_daily_check; --force-email persists.
      # Both invoke the email with is_test=args.test. Fix 10 None-guard is
      # defense-in-depth for any future non-exception failure return from
      # run_daily_check — today all failure paths propagate exceptions to
      # the typed-exception boundary below, so the guard is not reachable.
      rc, state, old_signals, run_date = run_daily_check(args)
      if (
        rc == 0
        and state is not None
        and old_signals is not None
        and run_date is not None
      ):
        # Phase 8 D-02/D-08 + B1 revision: dispatch → clear → maybe-append
        # → single save. `persist=not args.test` preserves --test structural
        # read-only (CLI-01) — --test dispatches (so operator sees preview)
        # but never calls save_state or mutates warnings.
        _dispatch_email_and_maintain_warnings(
          state, old_signals, run_date,
          is_test=args.test,
          persist=not args.test,
        )
      return rc
    # CLI-04: --once is a one-shot for GHA mode. No loop.
    if args.once:
      rc, _state, _old_signals, _run_date = run_daily_check(args)
      return rc
    # Default (no flag): Phase 7 D-04 + D-05 — immediate first run, then loop.
    _run_daily_check_caught(run_daily_check, args)
    return _run_schedule_loop(run_daily_check, args)
  except (DataFetchError, ShortFrameError) as e:
    logger.error('[Fetch] ERROR: %s', e)
    return 2
  except Exception as e:
    logger.error(
      '[Sched] ERROR: unexpected crash: %s: %s', type(e).__name__, e,
    )
    # D-05 / D-06 / D-07 (Phase 8): fire one last crash email before exit.
    # Reuses notifier.send_crash_email retry loop per D-07. Wrapped in a
    # nested try/except so a crash-email dispatch failure does NOT mask
    # the original error's exit code.
    try:
      # Review-driven amendment (2026-04-23, Codex MEDIUM on SC-3):
      # read the module-level _LAST_LOADED_STATE cache written by
      # run_daily_check. If the crash occurred BEFORE load_state
      # ever returned (e.g. import failure inside _run_schedule_loop),
      # _LAST_LOADED_STATE is still None, and _build_crash_state_summary
      # renders the graceful '(state not loaded — crash before load_state)'
      # placeholder. Otherwise the crash email includes the
      # signals/account/positions summary required by ROADMAP SC-3.
      _send_crash_email(e, state=_LAST_LOADED_STATE)
    except Exception as crash_email_err:
      logger.error(
        '[Email] ERROR: crash-email dispatch also failed: %s: %s',
        type(crash_email_err).__name__, crash_email_err,
      )
    return 1


if __name__ == '__main__':
  sys.exit(main())
