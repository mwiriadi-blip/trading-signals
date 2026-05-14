'''Phase 37 fan-out orchestrator (D-14). Top-level peer of daily_run.py.

Per review consensus #10: dispatch helpers (send_per_user_email,
send_invite_email, send_cycle_summary_email) live HERE — co-located with
the orchestrator — NOT in notifier/dispatch.py. This keeps notifier/dispatch.py
under the 500-line CLAUDE.md hard limit and makes the orchestrator self-contained.

last_cycle schema (overwrite-only single dict per cycle — review consensus #5 + #7):
  state['last_cycle'] = {
    'date': 'YYYY-MM-DD',                    # cycle run_date
    'total': int,                             # total active F&F users considered
    'ok': int,                               # successful dispatches (skips count as ok)
    'failed': int,                           # failed dispatches
    'users': list[{'uid', 'ok', 'reason'}],  # per-user outcomes for /healthz/last-cycle
    'errors': list[{'uid', 'reason'}],       # only the failing rows; convenience for admin
    'crash': str | None,                     # populated by main.py wrapper on total fan-out crash
  }

MUST NOT be called from inside an existing event loop (e.g., a FastAPI route)
— asyncio.run() rejects nested loops. Synchronous orchestration only (main.py).
'''
import asyncio
import email.utils
import html
import logging
import os
from datetime import date
from zoneinfo import ZoneInfo

from notifier.transport import (
  ResendError,
  SendStatus,
  _post_to_resend,
)
from state_manager import load_user_state, mutate_state
from system_params import FANOUT_SEMAPHORE_LIMIT

logger = logging.getLogger(__name__)
_AWST = ZoneInfo('Australia/Perth')


# =============================================================================
# HTML render helpers (private — minimal placeholder HTML per plan spec)
# =============================================================================

def _render_per_user_email_html(
  uid: str,
  user_state: dict,
  shared_signals: dict,
  run_date: str,
) -> str:
  '''Minimal placeholder HTML for per-user email body.

  Content is contract-stable: uid, run_date, shared_signals stringified.
  Full template wired in a future plan.
  '''
  safe_uid = html.escape(uid)
  safe_date = html.escape(run_date)
  signals_text = html.escape(str(shared_signals))
  return (
    f'<!DOCTYPE html><html><body>'
    f'<p>uid={safe_uid}</p>'
    f'<p>Date: {safe_date}</p>'
    f'<p>Signals: {signals_text}</p>'
    f'</body></html>'
  )


def _render_invite_email_html(invite_url: str) -> str:
  '''Minimal invite email body with a single accept link.'''
  safe_url = html.escape(invite_url, quote=True)
  return (
    f'<!DOCTYPE html><html><body>'
    f'<p>You have been invited to Trading Signals.</p>'
    f'<p><a href="{safe_url}">Accept your invite</a></p>'
    f'</body></html>'
  )


# =============================================================================
# Dispatch helpers — co-located per review #10
# =============================================================================

def send_per_user_email(
  uid: str,
  user_state: dict,
  shared_signals: dict,
  run_date: str,
) -> SendStatus:
  '''Send personalized daily email to a single F&F user. NEVER raises.

  Injects RFC 8058 List-Unsubscribe + List-Unsubscribe-Post headers on every call.
  Logs [Fan-out] uid=... ok=... reason=... on every dispatch attempt (review #13).

  Args:
    uid: user identifier (auth-store-trusted)
    user_state: per-user state slice — must contain 'email' key
    shared_signals: market signals slice from state['signals']
    run_date: YYYY-MM-DD cycle date string
  '''
  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    logger.error(
      '[Fan-out] SIGNALS_EMAIL_FROM not set — per-user email skipped uid=%s', uid,
    )
    status = SendStatus(ok=False, reason='missing_sender')
    logger.info('[Fan-out] uid=%s ok=%s reason=%s', uid, status.ok, status.reason)
    return status

  api_key = os.environ.get('RESEND_API_KEY', '').strip()
  if not api_key:
    logger.warning('[Fan-out] RESEND_API_KEY missing uid=%s', uid)
    status = SendStatus(ok=True, reason='no_api_key')
    logger.info('[Fan-out] uid=%s ok=%s reason=%s', uid, status.ok, status.reason)
    return status

  to_addr = user_state.get('email', '') or ''
  if not to_addr:
    status = SendStatus(ok=False, reason='missing_recipient')
    logger.info('[Fan-out] uid=%s ok=%s reason=%s', uid, status.ok, status.reason)
    return status

  # Optional display name encoding (RFC 2047 UTF-8 via email.utils.formataddr)
  display_name = user_state.get('display_name', '') or ''
  if display_name:
    to_header = email.utils.formataddr((display_name, to_addr))
  else:
    to_header = to_addr

  base_url = os.environ.get('BASE_URL', '').strip()
  extra_headers = {
    'List-Unsubscribe': f'<{base_url}/settings>',
    'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
  }

  subject = f'Trading Signals — {run_date}'
  html_body = _render_per_user_email_html(uid, user_state, shared_signals, run_date)

  try:
    _post_to_resend(
      api_key,
      from_addr,
      to_header,
      subject,
      html_body,
      email_headers=extra_headers,
    )
    status = SendStatus(ok=True, reason=None)
  except ResendError as e:
    status = SendStatus(ok=False, reason=f'ResendError: {e}'[:200])
  except Exception as e:  # noqa: BLE001 — never-raise dispatch
    status = SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])

  # review #13: per-user log on EVERY attempt
  logger.info('[Fan-out] uid=%s ok=%s reason=%s', uid, status.ok, status.reason)
  return status


def send_invite_email(
  to_email: str,
  invite_url: str,
) -> SendStatus:
  '''Send invite acceptance email to invitee. NEVER raises.

  Never logs raw token/URL — only logs to_email.
  '''
  if not to_email:
    return SendStatus(ok=False, reason='missing_recipient')

  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    logger.error('[Invite] SIGNALS_EMAIL_FROM not set — invite email skipped')
    return SendStatus(ok=False, reason='missing_sender')

  api_key = os.environ.get('RESEND_API_KEY', '').strip()
  if not api_key:
    logger.warning('[Invite] RESEND_API_KEY missing')
    return SendStatus(ok=False, reason='no_api_key')

  subject = "You're invited to Trading Signals"
  html_body = _render_invite_email_html(invite_url)

  try:
    _post_to_resend(api_key, from_addr, to_email, subject, html_body)
    logger.info('[Invite] sent to=%s', to_email)
    return SendStatus(ok=True, reason=None)
  except ResendError as e:
    logger.warning('[Invite] send failed: %s', e)
    return SendStatus(ok=False, reason=f'ResendError: {e}'[:200])
  except Exception as e:  # noqa: BLE001
    logger.warning('[Invite] unexpected: %s: %s', type(e).__name__, e)
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])


def send_cycle_summary_email(
  outcomes: list[dict],
  run_date: str,
  crash: str | None = None,
) -> SendStatus:
  '''Send end-of-cycle admin summary email. NEVER raises.

  Sent every cycle (D-03). Supports crash kwarg for total fan-out failure
  reporting (review #5).
  '''
  from notifier.transport import _resolve_email_to_or_skip

  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    logger.error('[Cycle] SIGNALS_EMAIL_FROM not set — cycle summary skipped')
    return SendStatus(ok=False, reason='missing_sender')

  to_addr = _resolve_email_to_or_skip(state=None, context='send_cycle_summary_email')
  if to_addr is None:
    return SendStatus(ok=False, reason='missing_recipient')

  api_key = os.environ.get('RESEND_API_KEY', '').strip()
  if not api_key:
    logger.warning('[Cycle] RESEND_API_KEY missing')
    return SendStatus(ok=False, reason='no_api_key')

  if crash is not None:
    subject = f'[Cycle {run_date}] CRASH'
    lines = [f'Fan-out crashed: {crash}', '']
    failed = [o for o in outcomes if not o.get('ok')]
    if failed:
      for o in failed:
        lines.append(f"  FAILED uid={o['uid']}: {o.get('reason', 'unknown')}")
    text_body = '\n'.join(lines) + '\n'
  else:
    ok_count = sum(1 for o in outcomes if o.get('ok'))
    total = len(outcomes)
    subject = f'[Cycle {run_date}] {ok_count}/{total} OK'
    lines = [f'Cycle {run_date}: {ok_count}/{total} users OK']
    for o in outcomes:
      if not o.get('ok'):
        lines.append(f"  FAILED uid={o['uid']}: {o.get('reason', 'unknown')}")
      else:
        lines.append(f"  OK uid={o['uid']}")
    text_body = '\n'.join(lines) + '\n'

  try:
    _post_to_resend(
      api_key,
      from_addr,
      to_addr,
      subject,
      html_body=None,
      text_body=text_body,
    )
    return SendStatus(ok=True, reason=None)
  except ResendError as e:
    logger.warning('[Cycle] send failed: %s', e)
    return SendStatus(ok=False, reason=f'ResendError: {e}'[:200])
  except Exception as e:  # noqa: BLE001
    logger.warning('[Cycle] unexpected: %s: %s', type(e).__name__, e)
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])


# =============================================================================
# Async fan-out machinery
# =============================================================================

async def _send_one(
  sem: asyncio.Semaphore,
  uid: str,
  user_row: dict,
  shared_signals: dict,
  run_date: str,
) -> dict:
  '''Per-user crash boundary + semaphore throttle. NEVER raises.

  Semaphore slot held across the ENTIRE blocking _post_to_resend call
  (including retry backoff) to prevent Resend rate-limit bursts.
  '''
  async with sem:
    today = date.today()
    email_enabled = user_row.get('email_enabled', True)
    if not email_enabled:
      logger.info('[Fan-out] uid=%s ok=True reason=skipped:disabled', uid)
      return {'uid': uid, 'ok': True, 'reason': 'skipped:disabled'}

    pause_until = user_row.get('pause_until')
    if pause_until and today <= date.fromisoformat(pause_until):
      logger.info('[Fan-out] uid=%s ok=True reason=skipped:paused', uid)
      return {'uid': uid, 'ok': True, 'reason': 'skipped:paused'}

    try:
      user_state = load_user_state(uid)
      result = await asyncio.to_thread(
        send_per_user_email, uid, user_state, shared_signals, run_date,
      )
      return {'uid': uid, 'ok': result.ok, 'reason': result.reason}
    except Exception as exc:  # noqa: BLE001 — per-user crash boundary
      reason = f'{type(exc).__name__}: {exc}'[:200]
      logger.warning('[Fan-out] uid=%s exception in _send_one: %s', uid, reason)
      return {'uid': uid, 'ok': False, 'reason': reason}


async def _fan_out_all(
  users: list[dict],
  shared_signals: dict,
  run_date: str,
) -> list[dict]:
  '''Async gather over all F&F users with Semaphore(FANOUT_SEMAPHORE_LIMIT) throttle.

  Each task self-catches internally so return_exceptions=False is safe.
  '''
  sem = asyncio.Semaphore(FANOUT_SEMAPHORE_LIMIT)
  tasks = [
    _send_one(sem, u['uid'], u, shared_signals, run_date)
    for u in users
  ]
  return list(await asyncio.gather(*tasks, return_exceptions=False))


# =============================================================================
# Synchronous entry point
# =============================================================================

def run(state: dict, run_date: str) -> list[dict]:
  '''Synchronous entry point called from main.py after daily_run returns.

  W3 invariant: exactly ONE terminal mutate_state call here is the W3 #2 write.
  Do NOT call mutate_state inside asyncio tasks (flock deadlock from thread ctx).

  Args:
    state: post-cycle state dict (passed by main.py after daily_run.run_daily_check)
    run_date: YYYY-MM-DD string

  Returns:
    list of per-user outcome dicts: [{'uid': str, 'ok': bool, 'reason': str | None}]
  '''
  from auth_store import list_users

  all_users = list_users()
  users_map = state.get('users', {})

  # Filter active F&F users; merge per-user state fields into user_row
  active_ff = []
  for u in all_users:
    if u.get('role') == 'ff' and not u.get('disabled'):
      per_user = users_map.get(u['uid'], {})
      row = {
        **u,
        'email_enabled': per_user.get('email_enabled', True),
        'pause_until': per_user.get('pause_until'),
        'email': per_user.get('email') or u.get('email', ''),
        'display_name': per_user.get('display_name') or u.get('display_name', ''),
      }
      active_ff.append(row)

  shared_signals = dict(state.get('signals', {}))

  outcomes = asyncio.run(_fan_out_all(active_ff, shared_signals, run_date))

  ok_count = sum(1 for o in outcomes if o.get('ok'))
  failed_count = len(outcomes) - ok_count
  errors = [
    {'uid': o['uid'], 'reason': o.get('reason')}
    for o in outcomes
    if not o.get('ok')
  ]

  def _batch_write(s: dict) -> None:
    '''Phase 37 _batch_write writes last_cycle ONLY; overwrite-only single dict
    (NOT list — review consensus #7); no per-user alert state mutations in fan-out
    (stop-loss alerts are read-only in this phase).
    '''
    s['last_cycle'] = {
      'date': run_date,
      'total': len(outcomes),
      'ok': ok_count,
      'failed': failed_count,
      'users': outcomes,
      'errors': errors,
      'crash': None,  # populated by main.py wrapper on total fan-out crash
    }

  # W3 #2: exactly ONE terminal mutate_state call (after asyncio.run completes)
  mutate_state(_batch_write)

  # Admin cycle summary AFTER mutate_state (never inside the callback — flock rule)
  send_cycle_summary_email(outcomes, run_date)

  return outcomes
