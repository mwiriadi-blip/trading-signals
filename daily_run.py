'''Daily-run orchestration seam — Phase 27 Plan 13 main.py split.

Owns the daily orchestration body and service wiring:
  - _compute_run_date: AWST wall-clock reader (orchestrator-only privilege).
  - _run_daily_check_impl: the 9-step daily orchestration sequence.
  - Service singletons (DailyRunService / SignalEvaluationService /
    PostRunService) wired to their *_impl callables.
  - Public service-backed wrappers consumed by main.py + scheduler_driver:
    run_daily_check, _evaluate_paper_trade_alerts,
    _dispatch_email_and_maintain_warnings, _push_state_to_git.

Hex discipline: stdlib (argparse, copy, logging, os, time, datetime,
zoneinfo) + state_manager + signal_engine + sizing_engine + system_params +
data_fetcher + pnl_engine + sibling seams (daily_run_helpers,
paper_trade_alerts, state_actions, crash_boundary). No transport / data libs.

Re-exported by main.py shim: main.run_daily_check,
main._evaluate_paper_trade_alerts, main._dispatch_email_and_maintain_warnings,
main._push_state_to_git.
'''
import argparse
import copy
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import data_fetcher
import signal_engine
import sizing_engine
import state_manager
import system_params
from data_fetcher import DataFetchError, ShortFrameError  # noqa: F401 — kept for hex audit symmetry
from pnl_engine import entry_side_cost  # Phase 27 #7: half-cost helper

import state_actions
import daily_run_helpers
import news_fetcher
import news_filter

logger = logging.getLogger(__name__)

# =========================================================================
# Module-level constants (echoed from main.py header for orchestration use)
# =========================================================================

AWST = ZoneInfo('Australia/Perth')

# Instrument keys in state.json <-> yfinance tickers (CLAUDE.md §Conventions)
SYMBOL_MAP: dict = {
  'SPI200': '^AXJO',
  'AUDUSD': 'AUDUSD=X',
}

# DATA-04 (Pitfall 6): minimum bars required before compute_indicators.
_MIN_BARS_REQUIRED = 300

# DATA-05 (D-09): stale when (run_date - signal_as_of).days > this.
_STALE_THRESHOLD_DAYS = 3


def _compute_run_date() -> datetime:
  '''CLAUDE.md: run_date always in Australia/Perth. No DST in Perth.
  Orchestrator is the only module allowed to read the wall clock (D-13).

  Returns a timezone-aware datetime; callers derive run_date_iso
  (YYYY-MM-DD) via strftime and run_date_display (full AWST string)
  separately.
  '''
  return datetime.now(tz=AWST)


# =========================================================================
# Orchestrator (D-11 nine-step sequence)
# =========================================================================

def _run_daily_check_impl(
  args: argparse.Namespace,
) -> tuple[int, dict | None, dict | None, datetime | None]:
  '''D-11 daily orchestration sequence (9 steps): load_state -> for each
  instrument fetch + compute indicators + signal + size + persist -> equity
  rollup -> warning flush -> drift recompute -> save -> alerts -> dashboard
  + state push.

  Returns (rc, state, old_signals, run_date) 4-tuple. --test path returns
  (0, state_in_memory, old_signals, run_date) WITHOUT save_state (CLI-01
  structural read-only). Weekend-skip returns (0, None, None, run_date).
  Exceptions (DataFetchError, ShortFrameError, anything unexpected)
  propagate to main()'s typed-exception boundary.

  Key invariants (preserved across the Plan 27-13 split — see git history
  on the original main.py for full revision context):
    - D-08 (Pitfall 7): state['signals'][symbol] read tolerates int OR
      dict shape; always writes the nested dict.
    - AC-1: per-symbol loop calls record_trade BEFORE assigning
      result.position_after (preserves reversal positions).
    - G-2: state['signals'][state_key] update carries last_scalars +
      indicator_scalars + ohlc_window for Phase 5/6/17 rendering.
    - W3: exactly 2 mutate_state calls per run (save here + warning-flush
      save inside _dispatch_email_and_maintain_warnings).
    - CLI-01: --test is STRUCTURALLY read-only; save call is conditional.
    - Phase 27 #7: entry/close-half costs via pnl_engine.entry_side_cost.
  '''
  # Step 1: opening log line (D-07 — before loop so tests see it even on raise).
  run_date = _compute_run_date()

  # D-03: weekday gate — short-circuits before fetch/compute/mutation on Sat/Sun.
  if run_date.weekday() >= system_params.WEEKDAY_SKIP_THRESHOLD:
    logger.info(
      '[Sched] weekend skip %s (weekday=%d) — no fetch, no state mutation',
      run_date.strftime('%Y-%m-%d'), run_date.weekday(),
    )
    return 0, None, None, run_date

  run_date_iso = run_date.strftime('%Y-%m-%d')
  run_date_display = run_date.strftime('%Y-%m-%d %H:%M:%S AWST')
  run_start_monotonic = time.perf_counter()
  # Canonical run-date marker (locked-in shape for journalctl grep — D-13).
  logger.info('[Daily] run-date %s', run_date_iso)
  # Late-bind _mode_label via main so test patches propagate.
  import main as _main_pkg
  logger.info(
    '[Sched] Run %s mode=%s', run_date_display, _main_pkg._mode_label(args),
  )

  # Step 2: load state.
  state = state_manager.load_state()
  # Phase 33 TENANT-01: per-user state bucket (v12 shape).
  # _user is a live reference to state['users'][_ADMIN_UID]; mutations
  # to _user propagate back to state automatically (same dict).
  _ADMIN_UID = state_manager._ADMIN_UID
  _user = state['users'][_ADMIN_UID]
  baseline_state = copy.deepcopy(state)
  enabled_markets = dict(sorted(
    (
      (key, market)
      for key, market in state.get('markets', {}).items()
      if isinstance(market, dict) and market.get('enabled', True)
    ),
    key=lambda item: (item[1].get('sort_order', 999), item[0]),
  ))
  if not enabled_markets:
    enabled_markets = {
      key: {'symbol': value}
      for key, value in SYMBOL_MAP.items()
    }

  # Refresh singleton cache for crash handler (ERR-05).
  state_actions._set_last_loaded_state(state)

  # ERR-05: transient _stale_info set here, popped in _dispatch before save.
  daily_run_helpers._maybe_set_stale_info(state, run_date)

  # D-05: capture old_signals before loop mutations; handles int/dict shape.
  old_signals: dict = {
    yf_sym: (
      state['signals'].get(state_key, {}).get('signal')
      if isinstance(state['signals'].get(state_key), dict)
      else state['signals'].get(state_key)
    )
    for state_key, market in enabled_markets.items()
    for yf_sym in [market.get('symbol', SYMBOL_MAP.get(state_key, state_key))]
  }

  # Step 3: per-symbol loop — fetch + indicators + signal + size + persist.
  trades_recorded = 0
  pending_warnings: list[tuple[str, str]] = []  # Wave 3 DATA-05 appends; empty in Wave 2.
  last_close_by_state_key: dict[str, float] = {}  # reused in step 4 equity rollup.

  for state_key, market in enabled_markets.items():
    yf_symbol = market.get('symbol', SYMBOL_MAP.get(state_key, state_key))
    strategy_settings = state.get('strategy_settings', {}).get(state_key, {})
    # D-17: tier from _resolved_contracts; split cost half-open/half-close (D-13).
    resolved = state['_resolved_contracts'][state_key]
    multiplier = resolved['multiplier']
    cost_aud_round_trip = resolved['cost_aud']
    # Phase 27 #7: entry-side cost via canonical helper. Float() at the
    # boundary because sizing_engine.step() expects float cost_aud_open;
    # pnl_engine remains the Decimal authority via compute_*_pnl returns.
    cost_aud_open = float(entry_side_cost(cost_aud_round_trip))

    # 3.a: fetch — DataFetchError propagates (Wave 3 catches at top level).
    fetch_start = time.perf_counter()
    df = data_fetcher.fetch_ohlcv(
      yf_symbol, days=400, retries=3, backoff_s=10.0,
    )
    fetch_elapsed = time.perf_counter() - fetch_start
    if data_fetcher.LAST_FETCH_SOURCE.get(yf_symbol) == 'yfinance_fallback':  # Phase 41 D-02
      pending_warnings.append(('fetch', f'IG fetch failed for {yf_symbol} — yfinance fallback used'))  # noqa: E501
    # 3.b: short-frame check BEFORE compute_indicators (DATA-04 / Pitfall 6).
    if len(df) < _MIN_BARS_REQUIRED:
      raise ShortFrameError(
        f'{yf_symbol}: only {len(df)} bars, need >= {_MIN_BARS_REQUIRED}',
      )

    # 3.c: signal_as_of from last-bar date — NO tz conversion (D-13, Pitfall 3).
    signal_as_of = df.index[-1].strftime('%Y-%m-%d')

    # 3.c.i: DATA-05 stale-bar — naive date diff, no tz_convert (D-11/Pitfall 3).
    last_bar_date = df.index[-1].date()
    today_awst_date = run_date.date()
    days_old = (today_awst_date - last_bar_date).days
    if days_old > _STALE_THRESHOLD_DAYS:
      logger.warning(
        '[Fetch] WARN %s stale: signal_as_of=%s is %dd old (threshold=%dd)',
        yf_symbol, signal_as_of, days_old, _STALE_THRESHOLD_DAYS,
      )
      # D-10: queue for end-of-run flush (append_warning takes positional args).
      pending_warnings.append((
        'fetch',
        f'{yf_symbol} stale: signal_as_of={signal_as_of} is {days_old}d old '
        f'(threshold={_STALE_THRESHOLD_DAYS}d)',
      ))

    # 3.c.ii: news gate — BLOCK_ON_FAILURE (D-02).
    _sym_news = market.get('symbol', SYMBOL_MAP.get(state_key, state_key))
    _event = news_filter.has_critical_event(
      news_fetcher.fetch_news(state_key, _sym_news), state_key)
    if _event.gate_status in ('blocked', 'unknown'):
      logger.warning('[News] SKIP %s gate=%r err=%r (D-02)',
        state_key, _event.gate_status, _event.fetch_error)
      daily_run_helpers.record_news_gate_skip(state, state_key, run_date_iso, _event)
      continue

    # 3.d-f: indicators + signal. Scalars feed sizing_engine AND get
    # persisted under state[signals][state_key][last_scalars] (G-2).
    df_with_indicators = signal_engine.compute_indicators(df)
    scalars = signal_engine.get_latest_indicators(df_with_indicators)
    try:
      new_signal = signal_engine.get_signal(
        df_with_indicators, settings=strategy_settings,
      )
    except TypeError as exc:
      if 'settings' not in str(exc):
        raise
      # Backward-compatible test/adapter path for monkeypatched get_signal
      # callables that still expose the original one-argument signature.
      new_signal = signal_engine.get_signal(df_with_indicators)
    step_scalars = dict(scalars)
    step_scalars['_settings'] = strategy_settings

    # 3.g: D-08 backward-compat read — accept int OR dict shape.
    raw = state['signals'].get(state_key)
    old_signal = raw if isinstance(raw, int) else raw.get('signal', 0)

    # 3.h: current position (may be None on flat).
    position = _user['positions'].get(state_key)

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
      indicators=step_scalars,
      old_signal=old_signal,
      new_signal=new_signal,
      account=_user['account'],
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
      # Phase 27 #7: close-side share via canonical helper (symmetric with
      # entry-side under the symmetric-broker assumption).
      closed_pnl_display = gross - float(entry_side_cost(cost_aud_round_trip)) * ct.n_contracts

    # D-14 per-instrument log block (G-4: warnings emitted inside).
    daily_run_helpers._format_per_instrument_log_block(
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
      trade_dict = daily_run_helpers._closed_trade_to_record(
        result.closed_trade, state_key,
        multiplier, cost_aud_round_trip,
        entry_date_pre_close, run_date_iso,
      )
      state = state_manager.record_trade(state, trade_dict)
      trades_recorded += 1

    # 3.n AC-1 revision 2026-04-22: position assignment AFTER record_trade.
    # On a reversal, record_trade cleared state['users'][_ADMIN_UID]['positions'][state_key]
    # to None; this line overwrites that None with the new reversal position.
    _user['positions'][state_key] = result.position_after

    # 3.o G-2 revision 2026-04-22: signal state update always dict shape
    # AND always carries last_scalars for Phase 5/6 rendering.
    # B-1 revision 2026-04-22 (Phase 5 Wave 0): last_close added alongside
    # last_scalars for UI-SPEC §Positions table Current-price column.
    # Phase 22 VERSION-02: tag every fresh write with the current
    # STRATEGY_VERSION. Use a fresh attribute access on system_params here
    # — do NOT bind to a kwarg default or a module-local alias. Global
    # LEARNINGS 2026-04-29 documents the kwarg-default capture trap that
    # would silently bypass monkeypatch + freeze the version at import.
    #
    # Phase 17 D-09: persist last 40 OHLC bars for the dashboard trace
    # panels. Build from `df` (NOT df_with_indicators) so the bar dicts
    # carry only OHLC + date — same shape sizing_engine consumes. Keys are
    # lowercased to match state.json convention. Same fresh-attribute-access
    # discipline as Phase 22 strategy_version per LEARNINGS 2026-04-29.
    ohlc_window: list[dict] = []
    for _, row in df.tail(40).iterrows():
      ohlc_window.append({
        'date': row.name.strftime('%Y-%m-%d')
          if hasattr(row.name, 'strftime') else str(row.name),
        'open': float(row['Open']),
        'high': float(row['High']),
        'low': float(row['Low']),
        'close': float(row['Close']),
      })
    # Phase 17 D-09: build the 9-key indicator_scalars with canonical Phase 17
    # key names (tr, atr, plus_di, minus_di, adx, mom1, mom3, mom12, rvol).
    # Note: get_latest_indicators (scalars) uses legacy key names pdi/ndi and
    # omits tr — indicator_scalars is built fresh from df_with_indicators so
    # key names match the _TRACE_FORMULAS catalogue in dashboard.py (D-13).
    # TR for the last bar: max(H-L, |H-Cprev|, |L-Cprev|).
    # Same formula as signal_engine._true_range (D-10 forbids importing it;
    # two-line arithmetic keeps hex-boundary intact).
    _last = df_with_indicators.iloc[-1]
    if len(df_with_indicators) >= 2:
      _prev_close = float(df_with_indicators['Close'].iloc[-2])
      _tr_last = max(
        float(_last['High']) - float(_last['Low']),
        abs(float(_last['High']) - _prev_close),
        abs(float(_last['Low']) - _prev_close),
      )
    else:
      _tr_last = float('nan')
    indicator_scalars: dict = {
      'tr': _tr_last,
      'atr': float(_last['ATR']),
      'plus_di': float(_last['PDI']),
      'minus_di': float(_last['NDI']),
      'adx': float(_last['ADX']),
      'mom1': float(_last['Mom1']),
      'mom3': float(_last['Mom3']),
      'mom12': float(_last['Mom12']),
      'rvol': float(_last['RVol']),
    }
    # Phase 29 Plan 11 (UAT-17-1 closure): persist Wilder ATR seed at the bar
    # immediately before the displayed 40-bar window so the trace panel can
    # surface a deterministic anchor for hand-recalc convergence checks.
    # window_start_index = len(df) - len(ohlc_window) (i.e. len(df) - 40).
    _window_start_index = len(df) - len(ohlc_window)
    _atr_seed = signal_engine.atr_seed_for_window(df, _window_start_index)
    state['signals'][state_key] = {
      'signal': new_signal,
      'signal_as_of': signal_as_of,
      'as_of_run': run_date_iso,
      'last_scalars': scalars,
      'last_close': bar['close'],
      'strategy_version': system_params.STRATEGY_VERSION,
      # Phase 17 D-09: trace payload — ohlc_window built from df.tail(40);
      # indicator_scalars uses canonical Phase 17 key names (plus_di/minus_di/tr).
      # last_scalars kept verbatim for backwards-compat notifier readers (D-09).
      'ohlc_window': ohlc_window,
      'indicator_scalars': indicator_scalars,
      # Resolved per-trade params actually fed to get_signal — recorded so the
      # dashboard trace renders the same gate the engine decided on.
      'vote_params': signal_engine.resolve_vote_params(strategy_settings),
      # Phase 29 Plan 11: Wilder ATR seed at bar before window (UAT-17-1).
      'atr_seed': _atr_seed,
    }

  # Step 4: total equity = account + sum(unrealised_pnl across active positions).
  # Phase 8 D-17: resolve tier from state['_resolved_contracts'] (per-symbol
  # tier from operator --reset config), not scalar system_params imports.
  equity = _user['account']
  for sk, pos in _user['positions'].items():
    if pos is not None and sk in last_close_by_state_key:
      resolved = state['_resolved_contracts'][sk]
      equity += sizing_engine.compute_unrealised_pnl(
        pos,
        last_close_by_state_key[sk],
        resolved['multiplier'],
        # Phase 27 #7: entry-side cost via canonical helper. Float() at
        # the sizing_engine boundary (per-contract cost_aud_open).
        float(entry_side_cost(resolved['cost_aud'])),
      )

  # Step 5: update equity history (STATE-06).
  state = state_manager.update_equity_history(state, run_date_iso, equity)

  # Step 6: flush queued pending_warnings into state (DATA-05; Phase 41 D-02).
  for source, message in pending_warnings:
    state = state_manager.append_warning(state, source, message)

  # Step 6b: drift recompute (Phase 15 D-02 + SENTINEL-01..03)
  # Sequence: clear stale drift warnings -> detect fresh drift events ->
  # append each as a 'drift'-source warning. ALL in-memory mutations only —
  # NO additional mutate_state call. The terminal mutate_state at step 9
  # captures these changes via _accumulated. (Pitfall 5 in 15-RESEARCH.md;
  # W3 invariant: exactly 2 mutate_state calls per run.)
  state = state_manager.clear_warnings_by_source(state, 'drift')
  drift_events = sizing_engine.detect_drift(_user['positions'], state['signals'])
  for ev in drift_events:
    state = state_manager.append_warning(state, 'drift', ev.message)
    logger.info(
      '[Sched] drift detected for %s: held=%s signal=%s severity=%s',
      ev.instrument, ev.held_direction, ev.signal_direction, ev.severity,
    )

  # Step 7: bookkeeping — last_run.
  state['last_run'] = run_date_iso

  # Step 8: structural read-only guard for --test (CLI-01 D-11).
  elapsed_total = time.perf_counter() - run_start_monotonic
  if args.test:
    logger.info('[Sched] --test mode: skipping save_state (state.json unchanged)')
    daily_run_helpers._format_run_summary_footer(
      logger, run_date, elapsed_total,
      instruments=len(SYMBOL_MAP),
      trades_recorded=trades_recorded,
      warnings=len(pending_warnings),
      state_saved=False,
    )
    return 0, state, old_signals, run_date

  # Step 9: atomic save via mutate_state.
  # Phase 14 REVIEWS HIGH #1: mutate_state holds the lock across read-modify-write.
  # The captured `state` from step 2's load_state is REPLACED by mutate_state's
  # fresh load under fcntl.LOCK_EX; we re-apply the daily run's accumulated
  # mutations to that fresh state. Costs one extra load (~5ms) and pays for
  # itself by closing the cross-process lost-update race against web POST
  # handlers (Plan 14-04). W3 invariant preserved: this counts as save #1
  # of the 2-saves-per-run contract.
  _accumulated = state
  _baseline = baseline_state
  def _apply_daily_run(fresh_state: dict) -> None:
    '''Replay the daily run's accumulated mutations onto fresh_state.
    Phase 33 TENANT-01: per-user keys (positions, account, trade_log,
    equity_history) are in state['users'][_ADMIN_UID]; top-level keys
    (signals, last_run, warnings) remain top-level.
    '''
    _uid = state_manager._ADMIN_UID
    _fresh_user = fresh_state['users'][_uid]
    _acc_user = _accumulated['users'][_uid]
    _base_user = _baseline['users'][_uid]
    # Per-user keys: replay into the user bucket.
    for key in ('positions', 'account', 'trade_log', 'equity_history'):
      if _acc_user.get(key) != _base_user.get(key):
        _fresh_user[key] = _acc_user[key]
    # Top-level keys: replay at state root.
    for key in ('signals', 'last_run', 'warnings'):
      if (
        key in _accumulated
        and _accumulated.get(key) != _baseline.get(key)
      ):
        fresh_state[key] = _accumulated[key]
  state = state_manager.mutate_state(_apply_daily_run)
  # Phase 8 review-driven amendment: refresh singleton cache to post-save state
  # (mutate_state returns it); crash-email path reads via state_actions.
  state_actions._set_last_loaded_state(state)
  # Phase 33 TENANT-01: per-user keys in user bucket
  _saved_user = state['users'][_ADMIN_UID]
  logger.info(
    '[State] state.json saved (account=$%.2f, trades=%d, positions=%d)',
    _saved_user['account'],
    len(_saved_user['trade_log']),
    sum(1 for p in _saved_user['positions'].values() if p is not None),
  )
  # Step 9.6 (Phase 20 D-12/D-18): evaluate stop-loss alerts and email.
  # MUST be called AFTER mutate_state(_apply_daily_run) returns — the
  # fcntl.LOCK_EX lock is non-reentrant; calling inside _apply_daily_run
  # would deadlock. _evaluate_paper_trade_alerts uses a SECOND mutate_state
  # call for the alert commit (two-phase commit pattern per D-18).
  # Reads dashboard_url from env; fall back to empty string (notifier
  # tolerates missing URL gracefully).
  _dashboard_url = os.environ.get('SIGNALS_DASHBOARD_URL', '')
  try:
    # Late-bind via main package so tests can monkeypatch
    # main._evaluate_paper_trade_alerts.
    _main_pkg._evaluate_paper_trade_alerts(state, _dashboard_url)
  except Exception as _exc:  # noqa: BLE001
    logger.exception('[Alert] WARN _evaluate_paper_trade_alerts failed: %s', _exc)

  # Step 9.5 (Phase 5 D-06): render dashboard.html; never crash on failure.
  # C-3 reviews Option A LOCKED: ONLY on the non-test path (after
  # `if args.test: return 0` above). --test is structurally read-only per
  # CLI-01 + CLAUDE.md — dashboard.html is a disk mutation and must not
  # happen under --test. Phase 6 may revisit if operator wants --test to
  # render a preview dashboard.
  from pathlib import Path
  daily_run_helpers._render_dashboard_never_crash(state, Path('dashboard.html'), run_date)
  # Phase 10 INFRA-02 / D-08: push state.json to origin/main via deploy
  # key; never crashes on failure.
  # Late-bind via main package so monkeypatch of main._push_state_to_git
  # propagates to the daily-run path.
  _main_pkg._push_state_to_git(state, run_date)
  elapsed_total = time.perf_counter() - run_start_monotonic
  daily_run_helpers._format_run_summary_footer(
    logger, run_date, elapsed_total,
    instruments=len(SYMBOL_MAP),
    trades_recorded=trades_recorded,
    warnings=len(pending_warnings),
    state_saved=True,
  )
  return 0, state, old_signals, run_date
