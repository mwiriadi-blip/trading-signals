'''Crash boundary seam — Phase 27 Plan 13 main.py split.

Owns:
  - _send_email_never_crash: import-isolation wrapper around notifier.send_daily_email
    (D-15 + NOTF-07/NOTF-08 + Phase 8 D-08 consumer bridge).
  - _build_crash_state_summary: bounded text/plain state summary for crash mail.
  - _send_crash_email: bridge to notifier.send_crash_email.
  - _dispatch_email_and_maintain_warnings_impl: B1 canonical-order dispatch helper
    (relocated from main.py per Plan 27-12 agreed-3).

Hex discipline: stdlib (logging, datetime) + state_manager + (local) notifier.
No transport / data libs.

Re-exported by main.py shim: main._send_email_never_crash, main._send_crash_email,
main._build_crash_state_summary, main._dispatch_email_and_maintain_warnings (via
the daily_run service wrapper that delegates here).
'''
import logging
from datetime import datetime

import state_manager

logger = logging.getLogger(__name__)


# =========================================================================
# Email integration (Phase 6 D-15) — never-crash wrapper
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
  # Phase 8 IN-01: state['signals'] is canonically keyed by state_key
  # ('SPI200' / 'AUDUSD') per Phase 3 reset_state and run_daily_check's
  # write pattern. The earlier yfinance-keyed lookup branch was dead code
  # (state is never dual-keyed mid-flow); removed for clarity.
  sig_spi = state.get('signals', {}).get('SPI200', {})
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
# (relocated from main.py per Plan 27-12 agreed-3 — was at main.py:1638)
# =========================================================================

def _dispatch_email_and_maintain_warnings_impl(
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

  Late-bind discipline (Plan 27-12 + 27-13): tests do
  `monkeypatch.setattr(main, '_send_email_never_crash', fake)` and expect
  the dispatcher to call the fake. A direct local reference would capture
  the original at import time and bypass the monkeypatch. Resolve via the
  `main` package on every call so the patch propagates here.
  '''
  import main as _main_pkg
  status = _main_pkg._send_email_never_crash(state, old_signals, now, is_test=is_test)
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
  # (d) single post-dispatch save via mutate_state.
  # Phase 14 REVIEWS HIGH #1: mutate_state holds the lock across
  # read-modify-write. Same key-replay shape as run_daily_check step 9 —
  # the post-dispatch state's `warnings` key may have been touched by
  # clear_warnings/append_warning above (TRADE-06 sole-writer preserved).
  # W3 invariant preserved: this counts as save #2 of the 2-saves-per-run
  # contract.
  _final = state
  def _apply_warning_flush(fresh_state: dict) -> None:
    '''Replay the post-dispatch state onto fresh_state. Same set of
    mutated keys as the run_daily_check save, plus the cleared/appended
    warnings list.
    '''
    for key in (
      'positions', 'signals', 'account', 'trade_log',
      'equity_history', 'last_run', 'warnings',
    ):
      if key in _final:
        fresh_state[key] = _final[key]
  state_manager.mutate_state(_apply_warning_flush)
