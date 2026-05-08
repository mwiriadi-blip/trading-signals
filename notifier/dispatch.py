'''Email dispatch orchestrators — send_daily_email, send_crash_email,
send_magic_link_email, send_stop_alert_email.

Extracted from notifier.py in Plan 27-12 (notifier package split).

NEVER raises (CLAUDE.md "Email sends NEVER crash the workflow"). Every
dispatch function returns a SendStatus(ok, reason) (or bool for the
legacy stop-alert API) on every code path.
'''
import logging
import os
from datetime import datetime
from pathlib import Path

import pytz

from .crash_path import _build_last_crash_payload, _write_last_crash
from .templates_alerts import (
  _build_alert_subject,
  _render_alert_email_html,
  _render_alert_email_text,
  _render_magic_link_html,
  _render_magic_link_text,
)
from .transport import (
  ResendError,
  SendStatus,
  _atomic_write_html,
  _resolve_email_to_or_skip,
)

# Phase 27 #2 (Plan 27-12) — monkeypatch parity. Tests rely on the
# legacy single-file behaviour where a name like `_post_to_resend` is
# mutable at the `notifier.<name>` package attribute and the call sites
# read it by name from the same module. After the package split each
# call site would otherwise capture a private reference at import time
# (via `from .transport import _post_to_resend`), making
# `monkeypatch.setattr(notifier, '_post_to_resend', ...)` invisible to
# the dispatcher. The proxies below resolve the names from the parent
# `notifier` package on EVERY call so per-test monkeypatches take
# effect — preserving the historical mutability contract.
#
# Names proxied (extracted from `tests/test_notifier.py`):
#   - notifier._post_to_resend
#   - notifier.compose_email_body
#   - notifier.compose_email_subject
#   - notifier._has_critical_banner
#   - notifier._render_*  (proxy not needed — used inside compose_email_body
#                          which is itself proxied, so the chain stays mutable)

def _post_to_resend(*args, **kwargs):
  '''Late-bound proxy — see module-level monkeypatch-parity note.'''
  import notifier as _pkg  # noqa: PLC0415 — late lookup is the whole point
  return _pkg._post_to_resend(*args, **kwargs)


def _compose_email_body(*args, **kwargs):
  '''Late-bound proxy for compose_email_body.'''
  import notifier as _pkg  # noqa: PLC0415
  return _pkg.compose_email_body(*args, **kwargs)


def _compose_email_subject(*args, **kwargs):
  '''Late-bound proxy for compose_email_subject.'''
  import notifier as _pkg  # noqa: PLC0415
  return _pkg.compose_email_subject(*args, **kwargs)


def _has_critical_banner(state):
  '''Late-bound proxy for _has_critical_banner.'''
  import notifier as _pkg  # noqa: PLC0415
  return _pkg._has_critical_banner(state)

logger = logging.getLogger(__name__)


def send_daily_email(
  state: dict,
  old_signals: dict,
  now: datetime,
  is_test: bool = False,
) -> SendStatus:
  '''Public dispatch. NEVER raises. Returns SendStatus on every path.

  NOTF-01: POSTs to Resend via _post_to_resend when RESEND_API_KEY present.
  NOTF-07: Resend API failure logs warning, returns SendStatus(ok=False,
    reason=...). Orchestrator (main.run_daily_check) translates into
    state_manager.append_warning so the failure surfaces on the next run
    (D-08 / Phase 8).
  NOTF-08: Missing RESEND_API_KEY → log WARN + return
    SendStatus(ok=True, reason='no_api_key'). Graceful degradation is NOT
    a failure — operator chose to run without a dispatch path.
  D-02 (Phase 8): `last_email.html` written on EVERY dispatch path,
    regardless of RESEND_API_KEY presence or Resend success — operator
    grep-recovery source of truth. Disk-write failure is logged but does
    NOT abort Resend dispatch.
  D-04 (Phase 8): subject gets `[!]` prefix when `_has_critical_banner`
    returns True (stale state or corrupt-reset).

  Recipient: SIGNALS_EMAIL_TO env var (required — Phase 27 #9). Missing
  or empty → log ERROR + return SendStatus(ok=False) + append a
  state-health warning marker visible on the dashboard health strip.

  Phase 12 (D-14/D-15/D-16): SIGNALS_EMAIL_FROM read per-send. Missing
  or empty → log ERROR + return SendStatus(ok=False, reason='missing_sender');
  NO Resend call, NO last_email.html write (early return before any
  payload construction). Orchestrator (main._dispatch_email_and_maintain_warnings)
  translates ok=False into state_manager.append_warning (Phase 8 D-08).
  NEVER falls back to onboarding@resend.dev (SC-4).
  '''
  # Phase 12 D-15: per-send env read; D-14: missing → log ERROR + skip.
  # NEVER falls back to onboarding@resend.dev (SC-4). Early return
  # happens BEFORE compose_email_body + last_email.html write to keep
  # the missing-sender path side-effect-free (12-REVIEWS.md LOW).
  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    logger.error('[Email] SIGNALS_EMAIL_FROM not set — email skipped')
    return SendStatus(ok=False, reason='missing_sender')

  has_critical = _has_critical_banner(state)
  subject = _compose_email_subject(
    state, old_signals,
    is_test=is_test, has_critical_banner=has_critical,
  )
  try:
    html_body = _compose_email_body(
      state, old_signals, now, from_addr=from_addr,
    )
  except Exception as e:
    logger.warning(
      '[Email] WARN compose_email_body failed: %s: %s',
      type(e).__name__, e,
    )
    return SendStatus(
      ok=False,
      reason=f'compose_body_failed: {type(e).__name__}: {e}'[:200],
    )

  # D-02 (Phase 8): write last_email.html EVERY run, BEFORE any api_key
  # or dispatch branch. Operator grep-recovery source of truth.
  last_email_path = Path('last_email.html')
  try:
    _atomic_write_html(html_body, last_email_path)
  except Exception as e:
    logger.warning(
      '[Email] WARN last_email.html write failed: %s: %s',
      type(e).__name__, e,
    )
    # Continue — disk-write failure must not block Resend dispatch.

  api_key = os.environ.get('RESEND_API_KEY')
  if not api_key:
    logger.warning(
      '[Email] WARN RESEND_API_KEY missing — wrote %s (fallback)',
      last_email_path,
    )
    return SendStatus(ok=True, reason='no_api_key')

  # Phase 27 #9: SIGNALS_EMAIL_TO is required (no fallback). Missing →
  # log ERROR + state-health warning + early return.
  to_addr = _resolve_email_to_or_skip(state, context='send_daily_email')
  if to_addr is None:
    return SendStatus(ok=False, reason='missing_recipient')
  try:
    _post_to_resend(api_key, from_addr, to_addr, subject, html_body)
    logger.info('[Email] sent to %s subject=%r', to_addr, subject)
    return SendStatus(ok=True, reason=None)
  except ResendError as e:
    # NOTF-07: log + return failure status; orchestrator translates to warning.
    logger.warning('[Email] WARN send failed: %s', e)
    return SendStatus(ok=False, reason=str(e)[:200])
  except Exception as e:
    # Belt-and-braces: ANY unexpected exception logged not propagated.
    # The ONLY place this codebase allows a bare Exception catch — email
    # delivery is not worth crashing the daily run (state already saved).
    logger.warning(
      '[Email] WARN unexpected failure: %s: %s', type(e).__name__, e,
    )
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])


def send_crash_email(
  exc: BaseException,
  state_summary: str,
  now: datetime | None = None,
) -> SendStatus:
  '''D-05/D-06/D-07 (Phase 8): text/plain [CRASH] dispatch.

  Reuses `_post_to_resend` retry loop (3 retries, flat backoff) — accepts
  the 30s max hang on exit for parity with regular sends. NEVER raises.
  No last_crash.html disk fallback: crash emails are transient; operator
  has `journalctl` / GHA logs for traceback recovery.

  Body format (text/plain, D-06):
    Timestamp: <ISO AWST>
    Exception: <class>: <message>

    Traceback:
      <traceback.format_exception() output>

    State summary:
      <state_summary argument, verbatim>

  `state_summary` is built by the caller (main._build_crash_state_summary
  in Plan 03) so notifier never touches state.json. Keeps hex-boundary
  clean. Text/plain body means NO html escape on `state_summary`; it is
  rendered verbatim.

  Phase 12 (D-14/D-15/D-16): SIGNALS_EMAIL_FROM read per-send. Missing
  or empty → log ERROR + SendStatus(ok=False, reason='missing_sender');
  no Resend call. Crash email is best-effort; missing env var is the
  operator's responsibility (surfaced in next daily warning banner).
  '''
  import traceback as _tb  # local import: no hex-boundary change needed
  if now is None:
    now = datetime.now(pytz.UTC)
  awst = pytz.timezone('Australia/Perth')
  iso_awst = now.astimezone(awst).strftime('%Y-%m-%d %H:%M:%S %Z')
  date_only = now.astimezone(awst).strftime('%Y-%m-%d')
  subject = f'[CRASH] Trading Signals — {date_only}'
  tb_text = _tb.format_exception(type(exc), exc, exc.__traceback__)
  body = (
    f'Timestamp: {iso_awst}\n'
    f'Exception: {type(exc).__name__}: {exc}\n'
    f'\n'
    f'Traceback:\n'
    f'{"".join(tb_text)}\n'
    f'State summary:\n'
    f'{state_summary}\n'
  )

  # Phase 12 D-15: per-send env read; D-14: missing → log ERROR + skip.
  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    logger.error(
      '[Email] SIGNALS_EMAIL_FROM not set — crash email skipped',
    )
    return SendStatus(ok=False, reason='missing_sender')

  api_key = os.environ.get('RESEND_API_KEY')
  if not api_key:
    logger.warning(
      '[Email] WARN crash-email: RESEND_API_KEY missing — skipping dispatch',
    )
    return SendStatus(ok=False, reason='no_api_key')

  # Phase 27 #9: SIGNALS_EMAIL_TO is required (no fallback). Crash path
  # passes state=None — append_warning would need a loadable state and
  # the daemon may already be in a partially-corrupted state on the
  # crash-email path. Plan 27-11 last_crash.json is the additional
  # operator-recovery surface for the missing-env-var case.
  to_addr = _resolve_email_to_or_skip(state=None, context='send_crash_email')
  if to_addr is None:
    return SendStatus(ok=False, reason='missing_recipient')

  try:
    _post_to_resend(
      api_key=api_key,
      from_addr=from_addr,
      to_addr=to_addr,
      subject=subject,
      html_body=None,
      text_body=body,
    )
    logger.info('[Email] CRASH email sent to %s', to_addr)
    return SendStatus(ok=True, reason=None)
  except ResendError as e:
    logger.warning('[Email] WARN crash-email send failed: %s', e)
    # Phase 27 #15 (Plan 27-11) — second-line fallback. The crash email
    # never reached the operator; write the redacted payload to
    # LAST_CRASH_PATH so the dashboard banner surfaces it on next visit.
    _write_last_crash(_build_last_crash_payload(exc, now, tb_text))
    return SendStatus(ok=False, reason=str(e)[:200])
  except Exception as e:
    logger.warning(
      '[Email] WARN crash-email unexpected failure: %s: %s',
      type(e).__name__, e,
    )
    # Phase 27 #15 (Plan 27-11): same fallback for any unexpected failure
    # in the dispatch path (defense in depth — Resend client bug, payload
    # serialization fault, etc.).
    _write_last_crash(_build_last_crash_payload(exc, now, tb_text))
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])


def send_magic_link_email(
  to_email: str,
  link: str,
  action: str,
  expires_at: str,
) -> SendStatus:
  '''F-03: send a 2FA reset magic-link email via Resend.

  NEVER raises (CLAUDE.md "Email sends NEVER crash the workflow"). All
  failure modes return SendStatus(ok=False, reason=<short>) and log at
  ERROR/WARNING.

  Args:
    to_email: operator's recovery email (typically OPERATOR_RECOVERY_EMAIL).
    link: absolute URL with the unhashed token query param.
    action: 'totp-reset' (room for future actions; surfaced in log line).
    expires_at: ISO 8601 UTC timestamp; formatted to AWST in body.
  '''
  # Phase 12 D-15 parity: per-send env read; missing → log ERROR + skip.
  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    logger.error(
      '[Email] SIGNALS_EMAIL_FROM not set — magic-link email skipped',
    )
    return SendStatus(ok=False, reason='missing_sender')

  subject = 'Trading Signals — 2FA reset link (valid 1 hour)'
  html_body = _render_magic_link_html(link, action, expires_at)
  text_body = _render_magic_link_text(link, action, expires_at)

  api_key = os.environ.get('RESEND_API_KEY')
  if not api_key:
    # Mirror send_daily_email's last_email.html fallback so an operator
    # running locally without RESEND_API_KEY still has the rendered email
    # for grep-recovery.
    last_email_path = Path('last_email.html')
    try:
      last_email_path.write_text(html_body)
    except OSError as e:
      logger.warning(
        '[Email] WARN magic-link: last_email.html write failed: %s', e,
      )
    logger.warning(
      '[Email] WARN magic-link: RESEND_API_KEY missing — wrote %s (fallback)',
      last_email_path,
    )
    return SendStatus(ok=False, reason='no_api_key')

  try:
    _post_to_resend(
      api_key=api_key,
      from_addr=from_addr,
      to_addr=to_email,
      subject=subject,
      html_body=html_body,
      text_body=text_body,
    )
  except ResendError as e:
    logger.error('[Email] magic-link Resend failed: %s', e)
    return SendStatus(ok=False, reason=str(e)[:200])
  except Exception as e:
    # CLAUDE.md never-crash: belt-and-braces against unexpected exception
    # types from the transport (e.g. raw requests.ConnectionError if the
    # _post_to_resend retry loop is bypassed via monkeypatch in tests).
    logger.error(
      '[Email] magic-link unexpected failure: %s: %s',
      type(e).__name__, e,
    )
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])

  logger.info(
    '[Email] magic link sent to=%s action=%s expires=%s',
    to_email, action, expires_at,
  )
  return SendStatus(ok=True, reason=None)


def send_stop_alert_email(transitions: list[dict], dashboard_url: str) -> bool:
  '''Phase 20 D-02/D-13: send batched stop-alert email via Resend.

  transitions: list of dicts with keys id, instrument, side, entry_price,
    stop_price, today_close, atr_distance, new_state, old_state.

  Returns True on Resend 200, False on any failure (network, API error,
  quota). NEVER crashes (Phase 6 invariant + CLAUDE.md "Email sends NEVER
  crash the workflow").

  Subject: N==1 -> per-trade bracketed format; N>1 -> batched format (D-02).
  Body: HTML table per D-02 + identical plain-text fallback (D-02 parity).
  '''
  if not transitions:
    return False  # D-01: no zero-row email
  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    logger.warning('[Email] WARN send_stop_alert_email: missing SIGNALS_EMAIL_FROM')
    return False
  # Phase 27 #9: SIGNALS_EMAIL_TO is required (no fallback). The stop-alert
  # path doesn't take a state dict (transitions arg only) — pass state=None;
  # the next send_daily_email call appends the health-warning marker for
  # operator visibility on the dashboard health strip.
  to_addr = _resolve_email_to_or_skip(state=None, context='send_stop_alert_email')
  if to_addr is None:
    return False
  api_key = os.environ.get('RESEND_API_KEY', '').strip()
  if not api_key:
    logger.warning('[Email] WARN send_stop_alert_email: missing RESEND_API_KEY')
    return False
  subject = _build_alert_subject(transitions)
  html_body = _render_alert_email_html(transitions, dashboard_url)
  text_body = _render_alert_email_text(transitions, dashboard_url)
  try:
    _post_to_resend(
      api_key=api_key,
      from_addr=from_addr,
      to_addr=to_addr,
      subject=subject,
      html_body=html_body,
      text_body=text_body,
    )
    return True
  except ResendError as e:
    logger.warning('[Email] WARN send_stop_alert_email failed: %s', e)
    return False
  except Exception as e:  # noqa: BLE001 -- CLAUDE.md never-crash
    logger.warning(
      '[Email] WARN send_stop_alert_email unexpected: %s: %s',
      type(e).__name__, e,
    )
    return False
