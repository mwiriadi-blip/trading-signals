'''Resend HTTPS transport — SendStatus / ResendError / _post_to_resend / _atomic_write_html.

Extracted from notifier.py in Plan 27-12 (notifier package split).

Re-exports `requests` at module level so `notifier.requests.post` and
`notifier.transport.requests.post` monkeypatch paths continue to work
(see tests/test_notifier.py — `monkeypatch.setattr('notifier.requests.post', ...)`).

Phase 27 #5: HTTP_TIMEOUT_S imported from system_params (single source of
truth). The previous local _RESEND_TIMEOUT_S = 30 was deleted to avoid
constant drift.

Phase 27 #13: redact_secret(api_key) prefix surfaced in ResendError so
operator triage can correlate which key blew up without exposing the
full token. Defense-in-depth body.replace stays.
'''
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

import requests  # noqa: F401 — re-exported for monkeypatch.setattr('notifier.requests.post', ...)

from system_params import (
  HTTP_TIMEOUT_S,
  redact_secret,
)

logger = logging.getLogger(__name__)


# =========================================================================
# SendStatus — Phase 8 D-08 dispatch-result discriminator
# =========================================================================

class SendStatus(NamedTuple):
  '''Phase 8 D-08: dispatch-result discriminator returned by send_daily_email
  and send_crash_email. Orchestrator (main.run_daily_check) translates
  `ok=False` into state_manager.append_warning for surfacing on the next
  run. NamedTuple chosen over dataclass for immutability + positional
  unpacking: `ok, reason = send_daily_email(...)`.
  '''
  ok: bool
  reason: str | None   # None on success; <=200-char human-readable on failure


# =========================================================================
# Email recipient resolution (Phase 27 #9 / D-14)
# =========================================================================

def _resolve_email_to_or_skip(
  state: dict | None = None,
  *,
  context: str,
):
  '''Phase 27 #9: resolve SIGNALS_EMAIL_TO or signal skip.

  Returns the recipient address as a non-empty stripped string when set;
  returns None when missing/blank (caller must skip dispatch).

  Side effects on missing env var:
    1. Log an ERROR via the module logger naming `context` (one of
       'send_daily_email', 'send_crash_email', 'send_stop_alert_email').
    2. If `state` is provided, append a marker entry to state['warnings']
       via state_manager.append_warning so the dashboard health strip
       surfaces the misconfiguration. Wrapped in try/except so notifier
       NEVER crashes the daily run on append-warning failure.

  Empty/whitespace-only env var ('   ') is treated identically to unset —
  matches a common deploy-typo failure mode (export SIGNALS_EMAIL_TO=).
  '''
  to_addr = os.environ.get('SIGNALS_EMAIL_TO', '').strip()
  if to_addr:
    return to_addr
  logger.error(
    '[Email] SIGNALS_EMAIL_TO env var required — %s skipped', context,
  )
  if state is not None:
    try:
      from state_manager import append_warning
      append_warning(
        state,
        'email',
        'SIGNALS_EMAIL_TO env var missing — emails disabled',
      )
    except Exception as e:  # noqa: BLE001 — never-crash invariant
      logger.error(
        '[Email] could not append SIGNALS_EMAIL_TO health warning: %s: %s',
        type(e).__name__, e,
      )
  return None


# =========================================================================
# Retry policy (D-12 — mirror data_fetcher.fetch_ohlcv)
# =========================================================================

_RESEND_RETRIES = 3
_RESEND_BACKOFF_S = 10

# D-12 retry-eligible transient exceptions (mirror data_fetcher:40-44).
# 429 + 5xx raise HTTPError via resp.raise_for_status() and flow through
# this tuple into the retry branch. 4xx (other than 429) fails fast with
# ResendError directly (no HTTPError raise, no retry).
_RESEND_RETRY_EXCEPTIONS = (
  requests.exceptions.Timeout,
  requests.exceptions.ConnectionError,
  requests.exceptions.HTTPError,
)


# =========================================================================
# Exception class
# =========================================================================

class ResendError(Exception):
  '''Raised when Resend POST fails after retries exhaust or returns non-retryable 4xx.

  NOT propagated past send_daily_email — caught by the outer try/except
  and logged at WARNING. Phase 8 may revisit if crash-email path needs
  discrimination.
  '''


# =========================================================================
# _atomic_write_html — D-13 durability sequence
# =========================================================================

def _atomic_write_html(data: str, path: Path) -> None:
  '''Mirror of state_manager._atomic_write + dashboard._atomic_write_html.

  D-13 durability sequence:
    1. write data to tempfile in same directory as target
    2. flush + fsync(tempfile.fileno()) — data durable on disk
    3. close tempfile (NamedTemporaryFile context exit)
    4. os.replace(tempfile, target) — atomic rename
    5. fsync(parent dir fd) on POSIX — rename itself durable on disk

  C-7 reviews (Phase 5): `newline='\\n'` on tempfile forces LF regardless
  of platform — text-mode default on Windows translates \\n → \\r\\n
  which would drift committed goldens (byte-stability gate).
  '''
  parent = path.parent
  tmp_path_str: str | None = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
      newline='\n',  # C-7: force LF regardless of platform
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    # D-17: os.replace BEFORE parent-dir fsync (rename durability).
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None  # success: do not delete in finally
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass


# =========================================================================
# _post_to_resend — POST + retry-on-transient (D-12 + RESEARCH §1)
# =========================================================================

def _post_to_resend(
  api_key: str,
  from_addr: str,
  to_addr: str,
  subject: str,
  html_body: str | None = None,
  timeout_s: int = HTTP_TIMEOUT_S,
  retries: int = _RESEND_RETRIES,
  backoff_s: int = _RESEND_BACKOFF_S,
  text_body: str | None = None,
) -> None:
  '''POST to Resend with retry-on-transient (D-12 + RESEARCH §1).

  Mirrors data_fetcher.fetch_ohlcv retry policy. 4xx except 429 fails fast;
  429 + 5xx + network errors retry up to `retries` times with flat
  `backoff_s` sleep (RESEARCH §1 — 429 IS retryable per Resend guidance).

  Raises ResendError after retries exhaust OR on non-retryable 4xx
  (400/401/403/422/etc., but NOT 429).

  Phase 8: accepts either `html_body` (existing callers) or `text_body`
  (Phase 8 `send_crash_email`) or both. Raises `ValueError` if both are
  None. Resend API accepts both keys simultaneously; the server picks
  the correct MIME part per recipient client.

  REVIEWS.md Fix 1 (HIGH): api_key MUST be actively redacted from any
  error message built from resp.text OR an exception repr. We replace the
  literal api_key with '[REDACTED]' before raising — defense-in-depth
  against Resend echoing the Authorization header back in its error body.

  REVIEWS.md Fix 2 (MEDIUM): timeout uses tuple (5, timeout_s) — 5s
  connect-phase + `timeout_s` read-phase. Prevents hung DNS/TCP handshake
  from consuming the full read budget.
  '''
  if html_body is None and text_body is None:
    raise ValueError('_post_to_resend requires html_body OR text_body')
  payload: dict = {
    'from': from_addr,
    'to': [to_addr],
    'subject': subject,
  }
  if html_body is not None:
    payload['html'] = html_body
  if text_body is not None:
    payload['text'] = text_body
  headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
  }
  last_err: Exception | None = None
  for attempt in range(1, retries + 1):
    try:
      resp = requests.post(
        'https://api.resend.com/emails',
        headers=headers,
        json=payload,
        timeout=(5, timeout_s),  # Fix 2: (connect, read) tuple
      )
      # RESEARCH §1: 429 IS retryable per Resend — special-case BEFORE
      # the 4xx fail-fast band. Raise HTTPError → caught by the retry
      # branch below.
      if resp.status_code == 429:
        raise requests.exceptions.HTTPError('429 rate-limit', response=resp)
      if 400 <= resp.status_code < 500:
        # Fix 1 (T-06-02): redact api_key from any echo, THEN truncate.
        # Phase 8 IN-03 ordering fix: truncating first risks leaking a
        # partial key that straddles the 200-char boundary (first N
        # chars of the key would survive the .replace() call). Redact
        # on the full body first so any occurrence — whole or partial
        # if echoed multiple times — is scrubbed before truncation.
        # Phase 27 #13 (T-27-03-01): also surface redact_secret(api_key)
        # prefix so operator triage can correlate which key without
        # exposing the full token. Defense-in-depth body.replace stays.
        safe_body = resp.text
        if api_key:
          safe_body = safe_body.replace(api_key, '[REDACTED]')
        safe_body = safe_body[:200]
        raise ResendError(
          f'4xx from Resend (key={redact_secret(api_key)}): '
          f'{resp.status_code} {safe_body}',
        )
      resp.raise_for_status()  # 5xx → HTTPError → retry branch
      return
    except _RESEND_RETRY_EXCEPTIONS as e:
      last_err = e
      logger.warning(
        '[Email] Resend attempt %d/%d failed: %s: %s',
        attempt, retries, type(e).__name__, e,
      )
      if attempt < retries:
        time.sleep(backoff_s)
  # Fix 1 (T-06-02): redact api_key from exhausted-retries message too —
  # last_err.__str__ may include response bodies or header echoes.
  # Phase 27 #13 (T-27-03-01): surface redact_secret(api_key) prefix so
  # operator can correlate which key blew up without exposing full token.
  err_repr = f'{type(last_err).__name__}: {last_err}'
  if api_key:
    err_repr = err_repr.replace(api_key, '[REDACTED]')
  raise ResendError(
    f'retries exhausted after {retries} attempts (key={redact_secret(api_key)}); '
    f'last error: {err_repr[:200]}',
  ) from last_err
