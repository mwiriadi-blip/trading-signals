'''auth_store._io — atomic-write kernel and load/save helpers.

F-01 atomic-write contract: tempfile + fsync(file) + os.replace +
fsync(parent dir) — copied verbatim from state_manager._atomic_write_unlocked.

Log prefix: [Auth]
'''
import json
import logging
import os
import tempfile
import time
from pathlib import Path

from auth_store._schema import (
  SCHEMA_VERSION,
  AuthData,
  _normalize_v2,
)

logger = logging.getLogger(__name__)


def _default_auth_data() -> AuthData:
  '''Fresh default — v2 schema with empty lists per call so callers can
  not share refs. SCHEMA_VERSION is 2 per Phase 34 Plan 01.
  '''
  return {
    'schema_version': SCHEMA_VERSION,
    'totp_secret': None,
    'totp_enrolled': False,
    'totp_enrolled_at': None,
    'trusted_devices': [],
    'pending_magic_links': [],
    'users': [],
    'pending_invites': [],
  }


# =========================================================================
# Atomic-write kernel
# =========================================================================

# No flock — caller is responsible for serialization
# (see auth_store._users.consume_and_create_user for the canonical flock window).
def _atomic_write_unlocked(data: str, path: Path) -> None:
  '''STATE-02 / D-08 (D-17 amendment): tempfile + fsync(file) + os.replace +
  fsync(parent dir). NO LOCK ACQUISITION — caller is responsible for holding
  any serialization lock if cross-process safety is required.

  Durability sequence (D-17 ordering):
    1. write data to tempfile in same directory as target
    2. flush + fsync(tempfile.fileno())  -- data durable on disk
    3. close tempfile
    4. os.replace(tempfile, target)      -- atomic rename
    5. fsync(parent dir fd) on POSIX     -- rename itself durable on disk
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


def _atomic_write(data: str, path: Path) -> None:
  '''F-01 / state_manager D-08 (D-17 amendment): tempfile + fsync(file) +
  os.replace + fsync(parent dir). NO LOCK ACQUISITION — auth_store is a
  low-mutation-rate operator-driven flow, single process.
  '''
  _atomic_write_unlocked(data, path)


# =========================================================================
# Path resolution
# =========================================================================


def _resolve_path(path: Path | None) -> Path:
  '''Pick the runtime auth.json path.

  Helpers accept `path: Path | None = None` rather than baking
  DEFAULT_AUTH_PATH into the kwarg default at function-definition time.
  Tests monkeypatch the module-level DEFAULT_AUTH_PATH; resolving inside
  the function body picks up the monkeypatched value.

  Lazy import of DEFAULT_AUTH_PATH — must NOT be at module top level to
  avoid circular-import between auth_store/__init__.py and this module.
  See auth_store/__init__.py file-ordering comment.
  '''
  from auth_store import DEFAULT_AUTH_PATH  # lazy — avoids circular init
  return path if path is not None else DEFAULT_AUTH_PATH


# =========================================================================
# Corruption recovery
# =========================================================================


def _quarantine_corrupt_auth_file(path: Path) -> None:
  '''Best-effort quarantine of a corrupt auth.json payload.

  Moves the unreadable file aside so subsequent writes can succeed cleanly.
  Any failure here is logged but does not block fallback to default auth data.
  '''
  suffix = time.strftime('%Y%m%dT%H%M%S', time.gmtime())
  quarantine_path = path.with_name(f'{path.name}.corrupt-{suffix}')
  try:
    os.replace(path, quarantine_path)
    logger.warning(
      '[Auth] moved corrupt auth store to %s; using defaults',
      quarantine_path,
    )
  except OSError as exc:
    logger.warning(
      '[Auth] failed to quarantine corrupt auth store %s: %s',
      path,
      exc,
    )


# =========================================================================
# Public load / save
# =========================================================================


def load_auth(path: Path | None = None) -> AuthData:
  '''Load auth.json from disk and return AuthData. Migrates v1 -> v2 on first read.

  WARNING: This function performs disk I/O via save_auth() during migration and
  cannot safely be called inside a LOCK_EX window — save_auth() acquires LOCK_EX,
  which will deadlock against an already-held lock. Callers inside a flock window
  must use _read_auth_unlocked + _normalize_v2 directly (see auth_store._users).
  '''
  resolved = _resolve_path(path)
  if not resolved.exists():
    return _default_auth_data()
  try:
    payload = json.loads(resolved.read_text(encoding='utf-8'))
  except (json.JSONDecodeError, UnicodeDecodeError) as exc:
    logger.warning('[Auth] corrupt auth store %s: %s', resolved, exc)
    _quarantine_corrupt_auth_file(resolved)
    return _default_auth_data()
  if not isinstance(payload, dict):
    logger.warning('[Auth] invalid auth store shape in %s: expected object', resolved)
    _quarantine_corrupt_auth_file(resolved)
    return _default_auth_data()
  # v1 -> v2 migration (D-09): upgrade in memory then write back immediately.
  was_v1 = payload.get('schema_version') == 1
  payload = _normalize_v2(payload)
  if was_v1:
    save_auth(payload, path=path)
  return payload


def save_auth(data: AuthData, path: Path | None = None) -> None:
  '''Atomic write of auth.json. Re-raises OSError on disk failure.'''
  payload = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
  _atomic_write(payload, _resolve_path(path))
