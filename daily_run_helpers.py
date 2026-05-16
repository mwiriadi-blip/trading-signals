'''Daily-run helpers seam — Phase 27 Plan 13 main.py split.

Owns helpers used by daily_run._run_daily_check_impl:
  - _render_dashboard_never_crash: dashboard render with import isolation.
  - _push_state_to_git_impl: nightly state.json git deploy-key push.
  - _maybe_set_stale_info: ERR-05 stale-state classifier.
  - _closed_trade_to_record: Phase 2 ClosedTrade -> Phase 3 record_trade dict.
  - _fmt_moms / _SIGNAL_LABELS: small log-line formatters.
  - _format_per_instrument_log_block: D-14 per-instrument log block.
  - _format_run_summary_footer: D-14 run-summary footer.

Hex discipline: stdlib (logging, datetime, pathlib) + state_manager +
sizing_engine + system_params (indirectly via STALENESS_DAYS_THRESHOLD which
this module re-defines — same value as the original main.py constant).
No transport / data libs.

Re-exported by main.py shim for tests via main._closed_trade_to_record.
'''
import logging
from datetime import datetime
from pathlib import Path

import sizing_engine
import state_manager
from sizing_engine import ClosedTrade

logger = logging.getLogger(__name__)

# Phase 8 D-01 (ERR-05 staleness classifier): if (run_date - last_run).days > 2
# the next email's header banner labels the state 'Stale'.
STALENESS_DAYS_THRESHOLD: int = 2


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
    dashboard.render_dashboard_files(state, out_path, now=now)
  except Exception as e:
    logger.warning('[Dashboard] render failed: %s: %s', type(e).__name__, e)


# =========================================================================
# Phase 10 INFRA-02 / D-07..D-15 — nightly state.json deploy-key git push
# =========================================================================

def _push_state_to_git_impl(state: dict, now: datetime) -> None:
  '''Phase 10 INFRA-02 / D-07..D-12 — nightly state.json commit + push via
  deploy-key-authenticated git remote. Never crashes the daily run.

  Uses local `import subprocess` to keep module-level import surface
  lean — this mirrors the `_send_email_never_crash` pattern established
  earlier. Although subprocess is stdlib (import failure is implausible),
  the local-import idiom is the project convention for never-crash
  wrappers and keeps the AST blocklist grep-auditable (REVIEW-LOW
  Option A; see 10-REVIEWS.md).

  Architecture:
    [save_state completed] -> [_push_state_to_git]
      -> `git diff --quiet state.json`
          rc=0 -> log [State] skip + return
          rc=1 -> continue to commit+push
          rc>=128 -> fail-loud path
      -> `git -c user.email=droplet@trading-signals
              -c user.name=DO Droplet
              commit -m 'chore(state): daily signal update [skip ci]'
              state.json`   (check=True)
      -> `git push origin main`   (check=True)

  D-07: lives in main.py (not state_manager) — preserves hex-lite
    boundary; state_manager stays I/O-narrow (disk only, no subprocess).
  D-09: skip-if-unchanged via git diff --quiet exit codes.
  D-10: inline -c flags (do NOT mutate .git/config).
  D-11: commit message verbatim from v1.0 Phase 7 convention.
  D-12: fail-loud — log ERROR + append_warning(source='state_pusher').
    Does NOT call save_state a third time (preserves Phase 8 W3
    two-saves-per-run invariant); warning persists via next run's
    normal save cycle.
  D-15: --test and weekend-skip never reach this helper (caller
    returns before save_state on both paths). Structurally guaranteed
    by the placement AFTER save_state in run_daily_check; verified
    by TestRunDailyCheckPushesState weekend + test-mode tests.

  COMMIT-vs-PUSH LOG DISTINCTION (REVIEW LOW): commit and push each
  have their OWN try/except clause so the emitted log verb names the
  failing subcommand unambiguously. Previously both paths shared an
  '[State] git push failed' message, which misled debugging.
  '''
  try:
    import subprocess  # local — C-2 pattern; see docstring rationale
    # D-09 three-way rc branch on `git diff --quiet state.json`.
    diff_result = subprocess.run(
      ['git', 'diff', '--quiet', 'state.json'],
      capture_output=True,
      timeout=30,
    )
    diff_rc = diff_result.returncode
    if diff_rc == 0:
      logger.info('[State] state.json unchanged — skipping git push')
      return
    if diff_rc >= 128:
      stderr_excerpt = (diff_result.stderr or b'').decode('utf-8', errors='replace')[:200]
      logger.error('[State] git diff failed (rc=%d): %s', diff_rc, stderr_excerpt)
      state_manager.append_warning(
        state,
        source='state_pusher',
        message=f'git diff failed rc={diff_rc}: {stderr_excerpt}',
        now=now,
      )
      return
  except subprocess.TimeoutExpired as e:
    logger.error('[State] git diff subprocess timeout: %s', e)
    try:
      state_manager.append_warning(
        state,
        source='state_pusher',
        message=f'Nightly git diff timed out: {e}',
        now=now,
      )
    except Exception as append_err:
      logger.error('[State] append_warning also failed: %s: %s',
                   type(append_err).__name__, append_err)
    return
  except Exception as e:
    logger.error('[State] git diff unexpected error: %s: %s',
                 type(e).__name__, e)
    try:
      state_manager.append_warning(
        state,
        source='state_pusher',
        message=f'Nightly git diff error: {type(e).__name__}: {e}',
        now=now,
      )
    except Exception as append_err:
      logger.error('[State] append_warning also failed: %s: %s',
                   type(append_err).__name__, append_err)
    return

  # D-10 inline identity flags; D-11 verbatim commit message;
  # explicit 'state.json' positional arg scopes the commit precisely.
  # OWN try/except so commit failures log '[State] git commit failed'
  # — distinct from push failures (REVIEW LOW).
  try:
    subprocess.run(
      [
        'git',
        '-c', 'user.email=droplet@trading-signals',
        '-c', 'user.name=DO Droplet',
        'commit',
        '-m', 'chore(state): daily signal update [skip ci]',
        'state.json',
      ],
      check=True,
      capture_output=True,
      timeout=30,
    )
  except subprocess.CalledProcessError as e:
    stderr_excerpt = (e.stderr or b'').decode('utf-8', errors='replace')[:200]
    logger.error(
      '[State] git commit failed (rc=%d): %s',
      e.returncode, stderr_excerpt,
    )
    try:
      state_manager.append_warning(
        state,
        source='state_pusher',
        message=f'Nightly state.json commit failed: rc={e.returncode} stderr={stderr_excerpt}',
        now=now,
      )
    except Exception as append_err:
      logger.error('[State] append_warning also failed: %s: %s',
                   type(append_err).__name__, append_err)
    return
  except subprocess.TimeoutExpired as e:
    logger.error('[State] git commit subprocess timeout: %s', e)
    try:
      state_manager.append_warning(
        state,
        source='state_pusher',
        message=f'Nightly state.json commit timed out: {e}',
        now=now,
      )
    except Exception as append_err:
      logger.error('[State] append_warning also failed: %s: %s',
                   type(append_err).__name__, append_err)
    return
  except Exception as e:
    logger.error('[State] git commit unexpected error: %s: %s',
                 type(e).__name__, e)
    try:
      state_manager.append_warning(
        state,
        source='state_pusher',
        message=f'Nightly state.json commit error: {type(e).__name__}: {e}',
        now=now,
      )
    except Exception as append_err:
      logger.error('[State] append_warning also failed: %s: %s',
                   type(append_err).__name__, append_err)
    return

  # D-13 no auto-rebase retry; fail-loud on push.
  # OWN try/except so push failures log '[State] git push failed'
  # — distinct from commit failures (REVIEW LOW).
  try:
    subprocess.run(
      ['git', 'push', 'origin', 'main'],
      check=True,
      capture_output=True,
      timeout=60,
    )
    logger.info('[State] state.json pushed to origin/main')
  except subprocess.CalledProcessError as e:
    stderr_excerpt = (e.stderr or b'').decode('utf-8', errors='replace')[:200]
    logger.error(
      '[State] git push failed (rc=%d): %s',
      e.returncode, stderr_excerpt,
    )
    try:
      state_manager.append_warning(
        state,
        source='state_pusher',
        message=f'Nightly state.json push failed: rc={e.returncode} stderr={stderr_excerpt}',
        now=now,
      )
    except Exception as append_err:
      logger.error('[State] append_warning also failed: %s: %s',
                   type(append_err).__name__, append_err)
  except subprocess.TimeoutExpired as e:
    logger.error('[State] git push subprocess timeout: %s', e)
    try:
      state_manager.append_warning(
        state,
        source='state_pusher',
        message=f'Nightly state.json push timed out: {e}',
        now=now,
      )
    except Exception as append_err:
      logger.error('[State] append_warning also failed: %s: %s',
                   type(append_err).__name__, append_err)
  except Exception as e:
    logger.error('[State] git push unexpected error: %s: %s',
                 type(e).__name__, e)
    try:
      state_manager.append_warning(
        state,
        source='state_pusher',
        message=f'Nightly state.json push error: {type(e).__name__}: {e}',
        now=now,
      )
    except Exception as append_err:
      logger.error('[State] append_warning also failed: %s: %s',
                   type(append_err).__name__, append_err)


# =========================================================================
# Phase 8 ERR-05 stale-info classifier
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


# =========================================================================
# D-12 closed-trade record translator
# =========================================================================

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


def record_news_gate_skip(state, state_key, run_date_iso, event):
  """Record a news gate skip in state for dashboard display (D-02)."""
  state.setdefault('news_gate_skips', {})[state_key] = {
    'run_date': run_date_iso,
    'gate_status': event.gate_status,
    'fetch_error': event.fetch_error,
  }
