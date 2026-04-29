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
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

# F-01 schema constant — Phase 18 will detect-and-migrate via this field.
SCHEMA_VERSION = 1

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
