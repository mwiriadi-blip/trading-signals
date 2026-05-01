'''Auth Store — atomic JSON persistence for auth.json (Phase 16.1 F-01).

Owns auth.json at the repo root and exposes the helpers Plan 16.1-01 needs:
  load_auth, save_auth, get_totp_secret, set_totp_secret, mark_enrolled.

Plan 16.1-02 will extend this module with trusted-device helpers
(add_trusted_device, revoke_device, revoke_all_other_devices, get_trusted_device,
update_last_seen). Plan 16.1-03 will add magic-link helpers (add_magic_link,
consume_magic_link, purge_expired_magic_links).

Architecture (CLAUDE.md hex-lite):
  auth_store.py is a peer of state_manager.py — both are I/O hex adapters
  living at the repo root. Allowed imports: stdlib only (NOT itsdangerous —
  cookie signing belongs to web/ adapters; not pyotp — TOTP verification
  is a web/-layer concern; auth_store only persists the secret).
  Forbidden imports: web/, signal_engine, sizing_engine, notifier, dashboard,
  main. Enforced by tests/test_auth_store.py::TestForbiddenImports AST guard.

F-01 atomic-write contract: tempfile + fsync(file) + os.replace +
fsync(parent dir) — copied verbatim from state_manager._atomic_write_unlocked.
NO fcntl.LOCK_EX — auth_store mutations are operator-driven (low-rate,
single-process); the lock complexity belongs to state.json's high-mutation-rate
flow (Phase 14 D-13). Phase 18 (v1.2) will migrate auth.json to SQLite.

Failure semantics: save_auth re-raises OSError on disk failure. Silent save
failures cause auth state loss (mirrors state_manager.save_state per
CLAUDE.md "data integrity > silent failure" stance).

Log prefix: [Auth] for any log lines (NOT [Web] — auth_store is hex-peer
of web/, not inside it).
'''
import hashlib
import json
import logging
import os
import tempfile
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

# F-01 schema constant — Phase 18 will detect-and-migrate via this field.
SCHEMA_VERSION = 1


def _ensure_aware(dt: datetime) -> datetime:
  '''Coerce naive datetime to UTC. All auth_store writes use UTC;
  naive values come from manual edits or pre-timezone-aware code.
  '''
  if dt.tzinfo is None:
    return dt.replace(tzinfo=timezone.utc)
  return dt

# Default path. auth_store helpers accept `path: Path = ...` kwarg so tests
# can redirect writes to tmp_path. Production callers omit the kwarg.
DEFAULT_AUTH_PATH = Path('auth.json')


# =========================================================================
# F-01 Schema TypedDicts
# =========================================================================


class TrustedDevice(TypedDict):
  '''Plan 16.1-02 will populate this. Fields per F-01:
    uuid, label, granted_at, last_seen, revoked, revoked_at.
  '''

  uuid: str
  label: str
  granted_at: str
  last_seen: str
  revoked: bool
  revoked_at: str | None


class PendingMagicLink(TypedDict):
  '''Plan 16.1-03 will populate this. Fields per F-01:
    token_hash, email, action, created_at, expires_at, consumed, consumed_at.
  '''

  token_hash: str
  email: str
  action: str
  created_at: str
  expires_at: str
  consumed: bool
  consumed_at: str | None


class AuthData(TypedDict):
  '''Top-level auth.json shape (F-01).'''

  schema_version: int
  totp_secret: str | None
  totp_enrolled: bool
  totp_enrolled_at: str | None
  trusted_devices: list[TrustedDevice]
  pending_magic_links: list[PendingMagicLink]


def _default_auth_data() -> AuthData:
  '''Fresh default — fresh empty lists per call so callers can't share refs.'''
  return {
    'schema_version': SCHEMA_VERSION,
    'totp_secret': None,
    'totp_enrolled': False,
    'totp_enrolled_at': None,
    'trusted_devices': [],
    'pending_magic_links': [],
  }


# =========================================================================
# Atomic-write kernel — copy of state_manager._atomic_write_unlocked
# =========================================================================


def _atomic_write(data: str, path: Path) -> None:
  '''F-01 / state_manager D-08 (D-17 amendment): tempfile + fsync(file) +
  os.replace + fsync(parent dir). NO LOCK ACQUISITION — auth_store is a
  low-mutation-rate operator-driven flow, single process.

  Durability sequence (D-17 ordering):
    1. write data to tempfile in same directory as target
    2. flush + fsync(tempfile.fileno())  -- data durable on disk
    3. close tempfile
    4. os.replace(tempfile, target)      -- atomic rename
    5. fsync(parent dir fd) on POSIX     -- rename itself durable on disk

  Tempfile cleanup: try/finally unlinks the tempfile if any step before
  os.replace raises. On success, tmp_path_str is set to None so the
  finally clause is a no-op.
  '''
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass


# =========================================================================
# Public API — Plan 16.1-01 (Plans 02 + 03 add more)
# =========================================================================


def _resolve_path(path: Path | None) -> Path:
  '''Pick the runtime auth.json path.

  Helpers accept `path: Path | None = None` rather than baking
  `DEFAULT_AUTH_PATH` into the kwarg default at function-definition time.
  Tests monkeypatch the module-level `DEFAULT_AUTH_PATH`; resolving inside
  the function body picks up the monkeypatched value (the kwarg-default
  pattern would freeze at import time and ignore the patch).
  '''
  return path if path is not None else DEFAULT_AUTH_PATH


def load_auth(path: Path | None = None) -> AuthData:
  '''Read auth.json. Returns a fresh default dict if the file is missing.

  No corruption recovery (mirrors state_manager simplicity for low-mutation
  state). If the file is truncated/corrupt, json.loads will raise — the
  operator must restore from backup OR delete the file to re-init.
  '''
  resolved = _resolve_path(path)
  if not resolved.exists():
    return _default_auth_data()
  return json.loads(resolved.read_text(encoding='utf-8'))


def save_auth(data: AuthData, path: Path | None = None) -> None:
  '''Atomic write of auth.json. Re-raises OSError on disk failure.'''
  payload = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
  _atomic_write(payload, _resolve_path(path))


def get_totp_secret(path: Path | None = None) -> str | None:
  '''F-01: read totp_secret. None if not yet enrolled.'''
  return load_auth(path=path)['totp_secret']


def set_totp_secret(secret: str, path: Path | None = None) -> None:
  '''F-01: write totp_secret AND reset enrolled=False.

  Used in two flows:
    1. First-login enrollment — operator hits POST /login with no totp_secret
       on file, server generates pyotp.random_base32() and persists here.
    2. Reset via magic link (Plan 16.1-03) — operator chose 'set up new
       authenticator', regenerate secret, persist via this helper.
  '''
  data = load_auth(path=path)
  data['totp_secret'] = secret
  data['totp_enrolled'] = False
  data['totp_enrolled_at'] = None
  save_auth(data, path=path)
  logger.info('[Auth] totp secret persisted (enrolled=False)')


def mark_enrolled(path: Path | None = None) -> None:
  '''F-01 E-03: flip totp_enrolled=True after successful TOTP code verification.

  Stamps totp_enrolled_at with the current UTC ISO 8601 timestamp.
  '''
  data = load_auth(path=path)
  data['totp_enrolled'] = True
  data['totp_enrolled_at'] = datetime.now(timezone.utc).isoformat()
  save_auth(data, path=path)
  logger.info('[Auth] totp enrollment finalised at=%s', data['totp_enrolled_at'])


# =========================================================================
# Trusted-device helpers — Phase 16.1 Plan 02 (F-01 + E-05 + E-06)
# =========================================================================
#
# Each helper follows the load -> mutate -> save pattern; mutations are
# idempotent (revoke-already-revoked is a no-op, update-last-seen on unknown
# uuid is a no-op). Revoked rows are RETAINED in auth.json for audit per
# E-06 — never deleted.
#
# All helpers accept the path kwarg via _resolve_path to honour test
# monkeypatching of DEFAULT_AUTH_PATH.


def add_trusted_device(label: str, path: Path | None = None) -> str:
  '''Append a new trusted-device row, return the uuid.

  Row shape (F-01 TrustedDevice):
    uuid, label, granted_at, last_seen (== granted_at on creation),
    revoked=False, revoked_at=None.
  '''
  new_uuid = _uuid.uuid4().hex
  now_iso = datetime.now(timezone.utc).isoformat()
  data = load_auth(path=path)
  data['trusted_devices'].append({
    'uuid': new_uuid,
    'label': label,
    'granted_at': now_iso,
    'last_seen': now_iso,
    'revoked': False,
    'revoked_at': None,
  })
  save_auth(data, path=path)
  logger.info('[Auth] trusted_device added: uuid=%s label=%s', new_uuid, label)
  return new_uuid


def revoke_device(uuid_value: str, path: Path | None = None) -> None:
  '''Flip revoked=True + stamp revoked_at on the matching uuid.

  Idempotent: unknown uuid is a no-op; already-revoked uuid is a no-op
  (preserves the original revoked_at timestamp).
  '''
  data = load_auth(path=path)
  changed = False
  for row in data['trusted_devices']:
    if row['uuid'] == uuid_value and not row['revoked']:
      row['revoked'] = True
      row['revoked_at'] = datetime.now(timezone.utc).isoformat()
      changed = True
      break
  if changed:
    save_auth(data, path=path)
    logger.info('[Auth] trusted_device revoked: uuid=%s', uuid_value)


def revoke_all_other_devices(
  except_uuid: str, path: Path | None = None,
) -> int:
  '''Flip revoked=True on every row whose uuid != except_uuid AND not already
  revoked. Returns count of rows newly flipped (excludes already-revoked rows).
  '''
  data = load_auth(path=path)
  now_iso = datetime.now(timezone.utc).isoformat()
  count = 0
  for row in data['trusted_devices']:
    if row['uuid'] != except_uuid and not row['revoked']:
      row['revoked'] = True
      row['revoked_at'] = now_iso
      count += 1
  if count:
    save_auth(data, path=path)
    logger.info(
      '[Auth] revoke_all_other_devices: count=%d except=%s', count, except_uuid,
    )
  return count


def get_trusted_device(
  uuid_value: str, path: Path | None = None,
) -> TrustedDevice | None:
  '''Return the row matching uuid OR None.'''
  data = load_auth(path=path)
  for row in data['trusted_devices']:
    if row['uuid'] == uuid_value:
      return row
  return None


def update_last_seen(uuid_value: str, path: Path | None = None) -> None:
  '''Bump the last_seen timestamp on the matching row.

  No-op if uuid not found (validation is the middleware's job — auth_store
  stays silent for unknown uuids per the same idempotency stance as
  revoke_device).
  '''
  data = load_auth(path=path)
  changed = False
  for row in data['trusted_devices']:
    if row['uuid'] == uuid_value:
      row['last_seen'] = datetime.now(timezone.utc).isoformat()
      changed = True
      break
  if changed:
    save_auth(data, path=path)


def is_uuid_active(uuid_value: str, path: Path | None = None) -> bool:
  '''True iff a row matches uuid AND row.revoked is False.

  Used by middleware._try_cookie to gate tsi_trusted cookie acceptance —
  signature alone is not sufficient; the uuid must still be unrevoked.
  '''
  data = load_auth(path=path)
  for row in data['trusted_devices']:
    if row['uuid'] == uuid_value:
      return row['revoked'] is False
  return False


# =========================================================================
# Magic-link helpers — Phase 16.1 Plan 03 (F-01 + F-02 + F-08)
# =========================================================================
#
# Token storage (T-16.1-19): callers pass the UNHASHED token to
# add_magic_link as a sha256 hex hash; consume_magic_link sha256-hashes
# the unhashed token on receipt and compares. A leaked auth.json reveals
# only one-way hashes, never live tokens.
#
# Atomic semantics: each helper follows the load -> mutate -> save pattern.
# consume_magic_link's flip-and-save is atomic per F-01 atomic-write contract.


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
    if row['token_hash'] != token_hash:
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
