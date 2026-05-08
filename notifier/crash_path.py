'''Phase 27 #15 (Plan 27-11) — second-line crash fallback to last_crash.json.

Extracted from notifier.py in Plan 27-12 (notifier package split).

When notifier.send_crash_email's outbound dispatch fails (Resend down,
network outage), the crash payload still reaches the operator on next
dashboard visit via LAST_CRASH_PATH on disk.

  - Path is configurable (LAST_CRASH_PATH env var); defaults to
    LAST_CRASH_FILE next to STATE_FILE.
  - Traceback + exception_message walk through pattern-redaction +
    redact_secret BEFORE the disk write — secrets NEVER reach disk.
  - The write is atomic (tempfile + os.replace) and NEVER raises.
'''
import json as _json_phase27_11
import logging
import os
import re as _re_phase27_11
from datetime import datetime
from pathlib import Path

import pytz

from system_params import (
  LAST_CRASH_FILE,
  STATE_FILE,
  redact_secret,
)

logger = logging.getLogger(__name__)


def _resolve_last_crash_path() -> Path:
  '''Resolve LAST_CRASH_PATH for this process.

  Priority:
    1. LAST_CRASH_PATH env var (operator override; configurable).
    2. Default: LAST_CRASH_FILE in the same directory as STATE_FILE.

  Returns a pathlib.Path. Resolution lives here (NOT in system_params)
  because system_params is stdlib-only — no os/pathlib imports allowed
  per the FORBIDDEN_MODULES_STDLIB_ONLY hex constraint.
  '''
  override = os.environ.get('LAST_CRASH_PATH', '').strip()
  if override:
    return Path(override)
  state_path = Path(STATE_FILE)
  return state_path.parent / LAST_CRASH_FILE


# Pattern catalog for in-text secret scrubbing. Tightly scoped to the
# token shapes the codebase actually emits today (Resend, Stripe-style,
# Bearer tokens). We deliberately do NOT add a generic api_key="..." kwarg
# pattern — the more-specific token patterns below already match the
# secret bodies inside such kwargs. A second-pass kwarg sweep would
# double-substitute already-redacted content (e.g. `api_key="re_tes..."`
# would re-match and emit `api_ke...`, destroying the triage prefix).
_SECRET_PATTERNS_PHASE27_11 = (
  # Resend API keys — `re_<token>`. Real Resend keys are base62 + underscores
  # (e.g. `re_AbC123xyz_456...`). We accept underscores in the body so a key
  # like `re_test_abc123def456ghi789` is matched as one token, not split at
  # the first underscore. >= 16 chars after the prefix.
  _re_phase27_11.compile(r're_[A-Za-z0-9_]{16,}'),
  # Stripe-style sk_ keys (defensive — operator may add a paid tier later).
  _re_phase27_11.compile(r'sk_[A-Za-z0-9_]{16,}'),
  # Bearer tokens echoed in headers / error bodies.
  _re_phase27_11.compile(r'Bearer\s+[A-Za-z0-9._\-]+'),
)


def _redact_secrets_in_text(text: str) -> str:
  '''Walk known secret patterns; replace each match with redact_secret(match).

  redact_secret returns 6-char prefix + ellipsis (system_params Plan 27-03)
  so operator triage stays possible while the raw token never reaches disk.
  Defensive: returns text unchanged if it isn't a string.
  '''
  if not isinstance(text, str):
    return text
  out = text
  for pat in _SECRET_PATTERNS_PHASE27_11:
    out = pat.sub(lambda m: redact_secret(m.group(0)), out)
  return out


def _build_last_crash_payload(
  exc: BaseException,
  now: datetime,
  tb_text_list: list,
) -> dict:
  '''Build the canonical crash payload schema for last_crash.json.

  Schema (Phase 27 #15):
    timestamp_utc: str           ISO 8601 UTC of when the crash was caught
    run_date_aws: str            YYYY-MM-DD AWST (operator timezone)
    exception_type: str          fully-qualified class name (str(type(exc).__name__))
    exception_message: str       str(exc) — REDACTED before write
    traceback: str               last 50 lines of traceback — REDACTED before write
    send_email_failure: bool     always True (this is the crash-email fallback path)
  '''
  awst = pytz.timezone('Australia/Perth')
  utc_now = now if now.tzinfo is not None else pytz.UTC.localize(now)
  return {
    'timestamp_utc': utc_now.astimezone(pytz.UTC).isoformat(),
    'run_date_aws': utc_now.astimezone(awst).strftime('%Y-%m-%d'),
    'exception_type': type(exc).__name__,
    'exception_message': str(exc),
    # Cap at last 50 lines per the plan schema (size guard).
    'traceback': '\n'.join(''.join(tb_text_list).splitlines()[-50:]),
    'send_email_failure': True,
  }


def _write_last_crash(payload: dict) -> None:
  '''Atomic write of the crash payload to LAST_CRASH_PATH. NEVER raises.

  Pre-write redaction (review-fix agreed-5):
    - payload['traceback'] -> _redact_secrets_in_text
    - payload['exception_message'] -> _redact_secrets_in_text

  Atomic shape: write to <path>.tmp THEN os.replace. Tempfile leftovers are
  cleaned up on write failure.
  '''
  try:
    redacted = dict(payload)
    if 'traceback' in redacted:
      redacted['traceback'] = _redact_secrets_in_text(redacted['traceback'])
    if 'exception_message' in redacted:
      redacted['exception_message'] = _redact_secrets_in_text(
        redacted['exception_message'],
      )
    path = _resolve_last_crash_path()
    tmp = path.with_suffix(path.suffix + '.tmp')
    try:
      tmp.write_text(_json_phase27_11.dumps(redacted, indent=2, default=str))
      os.replace(tmp, path)
    finally:
      # Best-effort cleanup if .tmp was created but os.replace did not run
      # (e.g. write_text raised mid-flight).
      try:
        if tmp.exists():
          tmp.unlink()
      except Exception:  # noqa: BLE001 — never-crash invariant
        pass
  except Exception as e:  # noqa: BLE001 — never-crash invariant
    logger.error(
      '[Crash] last_crash.json write failed: %s: %s',
      type(e).__name__, e,
    )
