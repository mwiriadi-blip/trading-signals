'''state_manager.trades — record helpers for state mutation.

Functions:
  append_warning: append {date, source, message}; FIFO trim to MAX_WARNINGS.
  clear_warnings: clear state['warnings'] (post-email-dispatch).
  clear_warnings_by_source: filter warnings by source key.
  record_trade: validate + record a closed trade; adjust account.
  update_equity_history: append {date, equity} with boundary validation.

All functions follow the same pattern: take a state dict, mutate it,
return the same dict for chaining. state_manager is the SOLE writer to
state['warnings'] (D-10 sole-writer invariant).
'''
import math
import zoneinfo
from datetime import datetime, UTC, timezone

from system_params import MAX_WARNINGS

from state_manager.migrations import _ADMIN_UID
from state_manager.validation import _assert_tz_aware, _validate_trade


def _admin_user(state: dict) -> dict:
  '''Phase 33 TENANT-01: return the admin user's state bucket.

  Centralises access to state['users'][_ADMIN_UID] so all record helpers
  use a single accessor. Falls back to `state` itself if 'users' is absent
  (pre-v12 state dicts in tests that build dicts directly without migration).
  '''
  users = state.get('users')
  if isinstance(users, dict) and _ADMIN_UID in users:
    return users[_ADMIN_UID]
  # Pre-v12 fallback: state dict itself is the user bucket.
  return state

_AWST = zoneinfo.ZoneInfo('Australia/Perth')


def append_warning(state: dict, source: str, message: str, now=None) -> dict:
  '''D-09 / D-10 / D-11: append {date, source, message}; FIFO trim to MAX_WARNINGS.

  Date format: ISO YYYY-MM-DD in AWST (Australia/Perth) per CLAUDE.md
  "Times always AWST in user-facing output" (RESEARCH §Open Question 3 / A1).

  State_manager is the SOLE writer to state['warnings'] (D-10). All other
  subsystems must call this helper rather than directly appending.

  `now` defaults to datetime.now(timezone.utc); tests inject a fixed UTC
  datetime for determinism without pytest-freezer.

  MAX_WARNINGS rationale (B-5 reviews-revision pass; tightened in
  Phase 27 #16 review-fix agreed-4 from prior 100 baseline):
    MAX_WARNINGS = 50 is intentionally conservative for v1's daily cadence
    (~7 weeks of warnings at 1/day average). A bad-day loop generating
    25+ warnings in one run fills half the bound. Chronic high-warning
    regimes (e.g., a bug emitting hundreds per day) should bump
    MAX_WARNINGS in system_params.py rather than expanding the contract
    here. The FIFO drop-oldest discipline ensures the bound is
    best-effort history — operators see the most recent 50 events, which
    is the actionable window for a daily-cadence system.
  '''
  if now is None:
    now = datetime.now(UTC)
  # Phase 27 #6 fail-closed: caller-provided naive datetimes raise here
  # BEFORE any FIFO mutation, so the write path is rejected pre-mutation.
  _assert_tz_aware(now, context='append_warning')
  today_awst = now.astimezone(_AWST).strftime('%Y-%m-%d')
  entry = {'date': today_awst, 'source': source, 'message': message}
  # FIFO trim: keep last (MAX_WARNINGS - 1) + new entry = MAX_WARNINGS total
  state['warnings'] = state['warnings'][-(MAX_WARNINGS - 1):] + [entry]
  return state


def clear_warnings(state: dict) -> dict:
  '''D-02 (Phase 8): clear state['warnings'] after the current run's
  email has been built and dispatched. Preserves D-10 sole-writer
  invariant — state_manager is the ONLY module that mutates
  state['warnings']; notifier reads but never writes.

  Intended flow in main.run_daily_check (canonical sequence per
  Plan 03 revision):
    1. Build email payload reading state['warnings'] as-of run start.
    2. save_state(state) to persist the run's mutations (end of
       run_daily_check step 5).
    3. notifier.send_daily_email(...) — dispatch.
    4. clear_warnings(state) — empty N-1 warnings list FIRST.
    5. If dispatch failed (SendStatus.ok is False), append_warning
       with source='notifier' so NEXT run surfaces the missed send —
       tagged with THIS run's AWST date.
    6. save_state(state) — single post-dispatch save (W3: total
       per-run save count = 2).

  In-place mutation; returns the same dict for chaining.
  '''
  state['warnings'] = []
  return state


def clear_warnings_by_source(state: dict, source: str) -> dict:
  '''Phase 15 D-02: filter out warnings whose `source` key matches the
  argument. Pure dict operation — no I/O. Caller wraps in mutate_state
  for persistence atomicity. Returns the same state dict for chaining.

  Preserves D-10 sole-writer invariant — state_manager is the ONLY
  module that mutates state['warnings']; notifier reads but never writes.

  Use case (Phase 15 SENTINEL-01..03): drift warnings lifecycle —
  clear_warnings_by_source(state, 'drift') then re-append fresh events
  from sizing_engine.detect_drift. Surgical, leaves corruption/stale/
  sizing_engine warnings intact.

  NOTE: This is DIFFERENT from clear_warnings(state) — that one wipes
  ALL warnings (used post-email-dispatch). Pitfall 8 in 15-RESEARCH.md.
  '''
  state['warnings'] = [
    w for w in state.get('warnings', [])
    if w.get('source') != source
  ]
  return state


def record_trade(state: dict, trade: dict) -> dict:
  '''STATE-05 / D-13 / D-14 / D-15 / D-16 / D-19 / D-20: record a closed trade.

  D-15 + D-19: validates trade shape and field types; raises ValueError
    on missing/wrong fields (extended to all 11 fields per D-19).
  D-14: deducts CLOSING-HALF cost (cost_aud * n_contracts / 2) from
    trade['gross_pnl']; computes net_pnl.
  D-13: appends to trade_log (as a copy with net_pnl per D-20), adjusts
    state['account'], sets state['positions'][trade['instrument']] = None
    (atomic mutation).
  D-16: NOT idempotent — caller must call exactly once per closed_trade.
  D-20 (reviews-revision pass): does NOT mutate caller's trade dict.
    The trade_log entry is built via dict(trade, net_pnl=net_pnl).

  CRITICAL Phase 4 boundary (RESEARCH §Pitfall 3):
    trade['gross_pnl'] MUST be raw price-delta P&L:
      (exit_price - entry_price) * n_contracts * multiplier  (LONG)
      (entry_price - exit_price) * n_contracts * multiplier  (SHORT)
    It MUST NOT be Phase 2's ClosedTrade.realised_pnl — that already has
    the closing cost deducted by Phase 2 _close_position. Passing
    realised_pnl as gross_pnl causes double-counting of the closing cost.
    Phase 4 orchestrator is responsible for this projection.
  '''
  # Phase 33 TENANT-01: per-user state bucket (v12 shape).
  user = _admin_user(state)
  _validate_trade(trade, allowed_instruments=set(user.get('positions', {}).keys()))
  # D-14: closing-half cost split. Phase 2 deducted opening half via
  # compute_unrealised_pnl during the position's lifetime. Phase 3 deducts
  # the closing half here at trade close.
  closing_cost_half = trade['cost_aud'] * trade['n_contracts'] / 2
  net_pnl = trade['gross_pnl'] - closing_cost_half
  user['account'] += net_pnl
  # D-20: append a copy of trade WITH net_pnl, do NOT mutate caller's dict.
  user['trade_log'].append(dict(trade, net_pnl=net_pnl))
  # D-13 / D-01: position is closed atomically with the trade record.
  user['positions'][trade['instrument']] = None
  return state


def update_equity_history(state: dict, date: str, equity: float) -> dict:
  '''STATE-06 / D-04 / B-4: append {date, equity} to equity_history.

  D-04: equity is caller-computed (state_manager is pure I/O hex; must NOT
  import sizing_engine to compute unrealised_pnl — that would break
  hexagonal-lite). Phase 4 orchestrator computes:
    equity = state['account'] + sum(unrealised_pnl across active positions)
  using sizing_engine.compute_unrealised_pnl per active position, then
  passes the total here.

  B-4 (reviews-revision pass, 2026-04-21): minimal boundary validation.
    - date must be str of length 10 (ISO YYYY-MM-DD shape; not a full
      format check — that's the orchestrator's job)
    - equity must be finite numeric (int or float, not bool, not NaN/inf)
    Catches Phase 4 wire-up bugs (e.g., passing a datetime object instead
    of a string, or a NaN that leaked from a sizing edge case) immediately
    rather than relying on save_state's allow_nan=False catch later.

  Date format per CLAUDE.md: ISO YYYY-MM-DD (no time component for
  equity_history entries; daily-cadence system).

  Returns the mutated state dict.

  Raises:
    ValueError: on malformed date (not str / wrong length) or non-finite
                equity (NaN, ±inf, bool, non-numeric).
  '''
  # B-4: validate date shape
  if not isinstance(date, str) or len(date) != 10:
    raise ValueError(
      f'update_equity_history: date must be str of length 10 '
      f'(ISO YYYY-MM-DD), got {date!r}'
    )
  # B-4: validate equity is finite numeric (rejecting bool, NaN, ±inf)
  if (
    not isinstance(equity, int | float)
    or isinstance(equity, bool)
    or not math.isfinite(equity)
  ):
    raise ValueError(
      f'update_equity_history: equity must be finite numeric '
      f'(int or float, not bool, not NaN/inf), got {equity!r}'
    )
  entry = {'date': date, 'equity': equity}
  # Phase 33 TENANT-01: equity_history now lives in user bucket (v12 shape).
  _admin_user(state)['equity_history'].append(entry)
  return state
