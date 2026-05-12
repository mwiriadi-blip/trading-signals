'''auth_store._magic_links — magic-link helpers.

Phase 16.1 Plan 03 (F-01 + F-02 + F-08).

Token storage (T-16.1-19): callers pass the UNHASHED token to
add_magic_link as a sha256 hex hash; consume_magic_link sha256-hashes
the unhashed token on receipt and compares. A leaked auth.json reveals
only one-way hashes, never live tokens.

Atomic semantics: each helper follows the load -> mutate -> save pattern.
consume_magic_link's flip-and-save is atomic per F-01 atomic-write contract.
'''
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from auth_store._io import load_auth, save_auth
from auth_store._schema import PendingMagicLink, _ensure_aware

logger = logging.getLogger(__name__)


def add_magic_link(
  token_hash: str,
  action: str,
  expires_at: str,
  email: str | None = None,
  path: Path | None = None,
) -> None:
  '''Append a new pending_magic_links row.

  Row shape (F-01 PendingMagicLink):
    token_hash, email, action, created_at (now-iso), expires_at,
    consumed=False, consumed_at=None.

  email defaults to OPERATOR_RECOVERY_EMAIL env var (or 'mwiriadi@gmail.com'
  if unset — caller is responsible for boot-validating the env var; we
  fall back here so the helper is callable in test code without that gate).
  '''
  resolved_email = (
    email if email is not None
    else os.environ.get('OPERATOR_RECOVERY_EMAIL', 'mwiriadi@gmail.com')
  )
  now_iso = datetime.now(timezone.utc).isoformat()
  data = load_auth(path=path)
  data['pending_magic_links'].append({
    'token_hash': token_hash,
    'email': resolved_email,
    'action': action,
    'created_at': now_iso,
    'expires_at': expires_at,
    'consumed': False,
    'consumed_at': None,
  })
  save_auth(data, path=path)
  logger.info('[Auth] magic_link added: action=%s expires=%s', action, expires_at)


def consume_magic_link(
  unhashed_token: str, path: Path | None = None,
) -> tuple[bool, str | None]:
  '''Find the row whose token_hash matches sha256(unhashed_token), validate
  unconsumed + unexpired, flip consumed=True + consumed_at=now-iso, save.

  Returns (True, action) on success, (False, None) on any failure mode
  (unknown token, expired, already consumed, hash mismatch). Failure mode
  is NOT distinguishable to the caller — Plan 03 callers render the same
  generic invalid-link page for every failure (E-07 no-leak).

  Token hash never logged — leaked log file should not enable replay
  against a still-unexpired but as-yet-unclicked token.
  '''
  token_hash = hashlib.sha256(
    unhashed_token.encode('utf-8'),
  ).hexdigest()
  data = load_auth(path=path)
  now = datetime.now(timezone.utc)
  for row in data['pending_magic_links']:
    if not hmac.compare_digest(row['token_hash'], token_hash):
      continue
    if row['consumed']:
      return (False, None)
    try:
      expires_at_dt = _ensure_aware(datetime.fromisoformat(row['expires_at']))
    except (TypeError, ValueError):
      return (False, None)
    if expires_at_dt < now:
      return (False, None)
    row['consumed'] = True
    row['consumed_at'] = now.isoformat()
    save_auth(data, path=path)
    logger.info('[Auth] magic_link consumed: action=%s', row['action'])
    return (True, row['action'])
  return (False, None)


def count_recent_magic_links(
  within_seconds: int = 86400, path: Path | None = None,
) -> int:
  '''Return count of pending_magic_links rows whose created_at is more
  recent than (now - within_seconds). Used by F-08 per-account rate check
  ("3 magic links per 24h per account") — caller compares against the
  RATE_LIMIT_MAGIC_LINKS_PER_24H constant.
  '''
  data = load_auth(path=path)
  cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
  count = 0
  for row in data['pending_magic_links']:
    try:
      created_at_dt = _ensure_aware(datetime.fromisoformat(row['created_at']))
    except (TypeError, ValueError):
      continue
    if created_at_dt > cutoff:
      count += 1
  return count


def purge_expired_magic_links(
  retention_seconds: int = 604800, path: Path | None = None,
) -> int:
  '''Drop rows whose expires_at is older than (now - retention_seconds).
  Default retention = 7 days (audit trail window).

  Returns count of rows dropped. Called opportunistically from POST
  /forgot-2fa before adding a new row (keeps auth.json bounded). NOT
  auto-scheduled in v1.0 — Phase 18 (v1.2) candidate for a daily cron.
  '''
  data = load_auth(path=path)
  cutoff = datetime.now(timezone.utc) - timedelta(seconds=retention_seconds)
  before = len(data['pending_magic_links'])
  kept: list[PendingMagicLink] = []
  for row in data['pending_magic_links']:
    try:
      expires_at_dt = _ensure_aware(datetime.fromisoformat(row['expires_at']))
    except (TypeError, ValueError):
      kept.append(row)
      continue
    if expires_at_dt > cutoff:
      kept.append(row)
  dropped = before - len(kept)
  if dropped:
    data['pending_magic_links'] = kept
    save_auth(data, path=path)
    logger.info('[Auth] purge_expired_magic_links: dropped=%d', dropped)
  return dropped
