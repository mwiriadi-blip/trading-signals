'''Paper-trade stop-alert evaluator seam — Phase 27 Plan 13 main.py split.

Owns:
  - _is_email_worthy: D-12 transition classifier (CLEAR->APPROACHING, *->HIT,
    HIT->CLEAR are email-worthy; APPROACHING->CLEAR + same-state are not).
  - _evaluate_paper_trade_alerts_impl: Phase 20 D-12/D-18 two-phase commit
    evaluator (eval -> send -> conditional persist).

Hex discipline: stdlib (logging) + alert_engine + state_manager +
(local) notifier. No transport / data libs.

Re-exported by main.py shim via the SignalEvaluationService wrapper:
main._evaluate_paper_trade_alerts. Tests use this surface heavily
(tests/test_main_alerts.py — 30+ test cases).
'''
import logging
import math

from alert_engine import compute_alert_state, compute_atr_distance
import state_manager


def _is_email_worthy(old_state: str | None, new_state: str) -> bool:
  '''D-12: returns True for email-worthy transitions only.
  Email-worthy: CLEAR->APPROACHING, *->HIT, HIT->CLEAR.
  NOT email-worthy: APPROACHING->CLEAR, same->same (dedup).
  '''
  if new_state == 'HIT':
    return True
  if new_state == 'APPROACHING' and old_state != 'APPROACHING':
    return True
  if new_state == 'CLEAR' and old_state == 'HIT':
    return True
  return False


def _evaluate_paper_trade_alerts_impl(state: dict, dashboard_url: str) -> dict:
  '''Phase 20 D-12/D-18: two-phase stop-alert evaluator.

  Phase 1 (eval): iterate open paper_trades, compute new alert state via
  alert_engine, classify into email-worthy transitions vs no-op writes.

  Phase 2 (send + conditional commit): call send_stop_alert_email for
  email-worthy transitions; commit transitioning rows only if email sent;
  commit no-op writes unconditionally.

  D-18: MUST be called AFTER mutate_state(_apply_daily_run) returns —
  never inside the _apply_daily_run closure (non-reentrant lock).

  Returns: {'transitions': list[dict], 'emailed': bool}
    transitions: only the email-worthy rows (empty list if none).
  '''
  from notifier import send_stop_alert_email  # local import — see hex note

  logger = logging.getLogger(__name__)

  # ---- Phase 1: eval -------------------------------------------------------
  transitions: list[dict] = []
  no_op_writes: dict[str, str] = {}  # id -> new_state (persisted unconditionally)

  for row in state.get('paper_trades', []):
    if not isinstance(row, dict):
      continue
    if row.get('status') != 'open':
      continue
    stop_price = row.get('stop_price')
    if stop_price is None:
      continue

    instrument = row.get('instrument', '')
    sig = state.get('signals', {}).get(instrument, {})
    ohlc = sig.get('ohlc_window', [])
    if not ohlc:
      logger.warning('[Alert] WARN no ohlc_window for %s; treating as CLEAR', instrument)
      new_state = 'CLEAR'
      atr = float('nan')
    else:
      bar = ohlc[-1]
      scalars = sig.get('indicator_scalars', {})
      atr = scalars.get('atr', float('nan'))
      if math.isnan(atr):  # IN-01: math.isnan is the standard idiom
        logger.warning('[Alert] WARN no ATR for %s; treating as CLEAR', instrument)
        new_state = 'CLEAR'
      else:
        new_state = compute_alert_state(
          side=row.get('side', ''),
          today_low=float(bar.get('low', float('nan'))),
          today_high=float(bar.get('high', float('nan'))),
          today_close=float(bar.get('close', float('nan'))),
          stop_price=float(stop_price),
          atr=float(atr),
        )

    old_state = row.get('last_alert_state')  # str | None

    # Dedup: same state -> no write (nothing to do)
    if old_state == new_state:
      continue

    today_close_val = float(ohlc[-1].get('close', float('nan'))) if ohlc else float('nan')
    atr_distance = compute_atr_distance(today_close_val, float(stop_price), float(atr))

    transition_record = {
      'id': row.get('id'),
      'instrument': instrument,
      'side': row.get('side', ''),
      'entry_price': row.get('entry_price'),
      'stop_price': stop_price,
      'today_close': today_close_val,
      'atr_distance': atr_distance,
      'new_state': new_state,
      'old_state': old_state,
    }

    if _is_email_worthy(old_state, new_state):
      transitions.append(transition_record)
    else:
      # Not email-worthy — goes to no-op write (e.g. APPROACHING->CLEAR for badge refresh)
      no_op_writes[row['id']] = new_state

  # ---- Phase 2: send + conditional commit ----------------------------------
  emailed = False
  if transitions:
    emailed = send_stop_alert_email(transitions, dashboard_url)

  # Build commit_map: two independent decisions
  commit_map: dict[str, str] = {}
  if emailed:
    # Commit transitioning rows only when email was successfully sent (D-06)
    commit_map.update({t['id']: t['new_state'] for t in transitions})
    logger.info(
      '[Alert] %d transition(s) emailed and committed',
      len(transitions),
    )
  else:
    if transitions:
      logger.warning(
        '[Alert] WARN stop alert email failed — %d transitioning row(s) NOT committed',
        len(transitions),
      )
  # No-op writes are committed unconditionally regardless of send outcome
  commit_map.update(no_op_writes)

  # Atomic persist via second mutate_state call (D-18)
  if commit_map:
    def _apply_alert_states(fresh_state: dict) -> None:
      for row in fresh_state.get('paper_trades', []):
        if isinstance(row, dict) and row.get('id') in commit_map:
          row['last_alert_state'] = commit_map[row['id']]
    state_manager.mutate_state(_apply_alert_states)

  return {'transitions': transitions, 'emailed': emailed}
